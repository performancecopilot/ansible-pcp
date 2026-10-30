# SPDX-License-Identifier: MIT
"""Run the TLS tasks against generated certificates without changing host users."""

import datetime
import getpass
import os
import shutil
import subprocess

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from test_pcp_role_loading import AnsibleTestCase, ROOT


class TLSValidation(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", role)
        source = role / "tasks/push_tls_validate.yml"
        # Keep real stat/OpenSSL validation, substituting the test account for
        # the managed-host pcp user. Live tests exercise actual escalation.
        source.write_text(
            source.read_text()
            .replace("become_user: pcp", "become_user: " + getpass.getuser())
            .replace("become: true", "become: false")
        )
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.keypath = self.root / "key.pem"
        self.keypath.write_bytes(
            self.key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        self.certpath = self.root / "cert.pem"
        self.certificate(-1, 1)

    def certificate(self, start, end):
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(1)
            .not_valid_before(now + datetime.timedelta(days=start))
            .not_valid_after(now + datetime.timedelta(days=end))
            .sign(self.key, hashes.SHA256())
        )
        self.certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    def validate(self, error=None, check=False):
        play = self.root / "tls.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "pcp_secure_logging": True,
                            "__pcp_push_tls_config": {
                                "cert": str(self.certpath),
                                "private_key": str(self.keypath),
                            },
                        },
                        "tasks": [
                            {
                                "include_role": {
                                    "name": "pcp",
                                    "tasks_from": "push_tls_validate.yml",
                                }
                            }
                        ],
                    }
                ]
            )
        )
        args = ["ansible-playbook", "-i", "localhost,", str(play)]
        if check:
            args.append("--check")
        result = subprocess.run(
            args,
            env=self.environment,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
        )
        self.assertNotIn("BEGIN PUBLIC KEY", result.stdout)
        self.assertNotIn("BEGIN PRIVATE KEY", result.stdout)
        if error:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stdout)
        else:
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_valid_and_check_mode(self):
        original = self.keypath.stat()
        self.validate()
        self.validate(check=True)
        current = self.keypath.stat()
        self.assertEqual(
            (original.st_uid, original.st_gid, original.st_mode),
            (current.st_uid, current.st_gid, current.st_mode),
        )

    def test_missing_file(self):
        self.certpath.unlink()
        self.validate("does not exist or is not a regular file")

    def test_unreadable_file(self):
        if os.geteuid() == 0:
            self.skipTest("Root can read mode-000 files; live tests use pcp")
        self.keypath.chmod(0)
        self.addCleanup(self.keypath.chmod, 0o600)
        self.validate("not readable by service user pcp")

    def test_invalid_expired_and_future(self):
        self.certpath.write_text("invalid certificate")
        self.validate("expired or invalid")
        self.certificate(-2, -1)
        self.validate("expired or invalid")
        self.certificate(1, 2)
        self.validate("not yet valid")

    def test_mismatched_key(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.keypath.write_bytes(
            other.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        self.validate("Certificate and private key do not match")
