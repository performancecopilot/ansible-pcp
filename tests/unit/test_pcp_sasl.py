# SPDX-License-Identifier: MIT
"""Exercise account creation without rotating existing SASL credentials."""

import json
import os
import shutil

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class SaslAccounts(AnsibleTestCase):
    def test_create_once_with_literal_password(self):
        role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", role)
        # Substitute the external SASL tools; keep the real provisioning tasks.
        bindir = self.root / "bin"
        bindir.mkdir()
        database = self.root / "accounts.json"
        for name, body in {
            "sasldblistusers2": "print(json.loads(p.read_text())['user'] + '@test: userPassword') if p.exists() else None",
            "saslpasswd2": "p.write_text(json.dumps({'user': sys.argv[-1], 'password': sys.stdin.read()}))",
        }.items():
            tool = bindir / name
            tool.write_text(
                '#!/usr/bin/python3\nimport json, pathlib, sys\np = pathlib.Path(sys.argv[sys.argv.index("-f") + 1])\n'
                + body
                + "\n"
            )
            tool.chmod(0o755)
        tasks = yaml.safe_load((role / "tasks/sasl.yml").read_text())
        # Permission enforcement is tested on managed hosts, not this fixture.
        tasks = [task for task in tasks if "file" not in task]
        (role / "tasks/sasl.yml").write_text(yaml.safe_dump(tasks))
        password = "quotes'\";$(not-a-command)"
        include = {"include_tasks": "sasl.yml"}
        (role / "tasks/main.yml").write_text(
            yaml.safe_dump(
                [
                    include,
                    {"assert": {"that": "__pcp_sasl_changed"}},
                    {
                        "set_fact": {
                            "__pcp_sasl_changed": False,
                            "__pcp_account": {
                                "sasluser": "push",
                                "saslpassword": "different",
                            },
                        }
                    },
                    include,
                    {"assert": {"that": "not __pcp_sasl_changed"}},
                ]
            )
        )
        play = self.root / "play.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "environment": {"PATH": str(bindir) + ":" + os.environ["PATH"]},
                        "vars": {
                            "__pcp_pmcd_sasldb_path": str(database),
                            "__pcp_account": {
                                "sasluser": "push",
                                "saslpassword": password,
                            },
                        },
                        "roles": ["pcp"],
                    }
                ]
            )
        )
        self.run_command(
            "ansible-playbook",
            "-i",
            "localhost,",
            str(play),
            "--extra-vars",
            json.dumps({"__pcp_pmcd_sasldb_path": str(database)}),
        )
        self.assertEqual(
            json.loads(database.read_text()),
            {"user": "push", "password": password + "\n"},
        )
