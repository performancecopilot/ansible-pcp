# SPDX-License-Identifier: MIT
"""Test additive control entries and removal without touching local loggers."""

import json
import shutil

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class PushClient(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        self.role = self.root / "roles/pcp"
        shutil.copytree(
            ROOT / "roles/pcp", self.role, ignore=shutil.ignore_patterns("__pycache__")
        )
        self.control = self.root / "control"
        self.control_d = self.root / "control.d"
        self.control_d.mkdir()
        self.original = (
            "# custom local and remote logging\n$version=1.1\n"
            "LOCALHOSTNAME y n /custom/local -c config.custom\n"
            "localhost n n /custom/other -c config.other\n"
            "remote n n /custom/remote -c config.remote\n"
        )
        self.control.write_text(self.original)
        self.other = self.control_d / "custom"
        self.other.write_text("# unrelated control.d entry\n")

    def run_role(self, tasks, variables):
        (self.role / "tasks/main.yml").write_text(yaml.safe_dump(tasks))
        play = self.root / "play.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "roles": ["pcp"],
                    }
                ]
            )
        )
        variables = dict(
            variables,
            __pcp_pmlogger_control_path=str(self.control),
            __pcp_pmlogger_control_d_path=str(self.control_d),
            __pcp_is_booted=False,
        )
        self.run_command(
            "ansible-playbook",
            "-i",
            "localhost,",
            str(play),
            "--extra-vars",
            json.dumps(variables),
        )

    def render(self, client):
        result = self.root / "rendered.control"
        self.run_role(
            [
                {
                    "template": {
                        "src": "push_client.service.j2",
                        "dest": str(result),
                        "mode": "0644",
                    }
                }
            ],
            {"pcp_push_client": client},
        )
        return result.read_text()

    def test_non_primary_entry_and_password_file(self):
        for url, normalized in [
            ("http://collector", "http://collector:44322"),
            ("https://[2001:db8::1]/", "https://[2001:db8::1]:44322"),
        ]:
            with self.subTest(url=url):
                content = self.render({"enabled": True, "collector_url": url})
                self.assertIn("User=pcp", content)
                self.assertIn("Restart=always", content)
                self.assertIn(normalized, content)
                self.assertEqual(self.control.read_text(), self.original)
        content = self.render(
            {
                "enabled": True,
                "collector_url": "https://collector",
                "auth": "basic",
                "username": "push_test",
                "password": "do-not-render-this",
            }
        )
        self.assertIn("--push-password-file", content)
        self.assertNotIn("do-not-render-this", content)
