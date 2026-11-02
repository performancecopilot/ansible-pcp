# SPDX-License-Identifier: MIT
"""Exercise real curl probes against local HTTP and verified HTTPS endpoints."""

import datetime
import http.server
import shutil
import ssl
import subprocess
import threading

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from test_pcp_role_loading import AnsibleTestCase, ROOT


class PushProbe(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", role)
        tasks = role / "tasks/push_probe.yml"
        data = yaml.safe_load(tasks.read_text())
        # Keep the real probe and diagnostic tasks; curl is already installed.
        data[0]["block"].pop(0)
        tasks.write_text(yaml.safe_dump(data))
        self.status = 200
        self.requests = 0
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests += 1
                self.send_response(owner.status)
                self.send_header("Content-Length", "0")
                if owner.status == 302:
                    self.send_header("Location", "/redirect-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.http = self.server(Handler)
        self.https = self.server(Handler, tls=True)

    def server(self, handler, tls=False):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        if tls:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(1)
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            self.ca = self.root / "cert.pem"
            self.ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            private = self.root / "key.pem"
            private.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(self.ca), str(private))
            server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def probe(self, tls=False, error=None, trusted=True, check=False):
        server = self.https if tls else self.http
        url = ("https" if tls else "http") + "://localhost:" + str(server.server_port)
        client = {"enabled": True, "collector_url": url}
        if tls:
            client["ca_cert"] = str(self.ca if trusted else self.root / "missing-ca")
        play = self.root / "probe.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "__pcp_is_booted": True,
                            "pcp_push_client": client,
                            "__pcp_push_client_url": url,
                        },
                        "tasks": [
                            {
                                "include_role": {
                                    "name": "pcp",
                                    "tasks_from": "push_probe.yml",
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
            check=False,
        )
        if error:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stdout)
        else:
            self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def test_success_http_and_verified_https(self):
        self.probe()
        self.probe(tls=True)
        self.assertEqual(self.requests, 2)

    def test_rejection_and_redirect_diagnostics(self):
        for status, diagnostic in [
            (401, "rejected authentication"),
            (403, "rejected authentication"),
            (503, "authentication service unavailable"),
            (302, "redirected /logger/ping"),
        ]:
            with self.subTest(status=status):
                self.status = status
                self.probe(error=diagnostic)
        # Three attempts for HTTP 503, one each for 401/403/302; no redirects.
        self.assertEqual(self.requests, 6)

    def test_https_trust_failure_is_not_accepted(self):
        self.probe(tls=True, trusted=False, error="connection/TLS verification failed")
        self.assertEqual(self.requests, 0)

    def test_check_mode_skips_probe(self):
        self.assertIn("remains unverified", self.probe(check=True))
        self.assertEqual(self.requests, 0)
