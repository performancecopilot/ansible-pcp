# SPDX-License-Identifier: MIT
"""Check-mode version validation must still reject installed unsupported PCP."""

import subprocess

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class PushVersion(AnsibleTestCase):
    def test_version_assertion_in_check_and_normal_modes(self):
        tasks = yaml.safe_load(
            (ROOT / "roles/pcp/tasks/push_validate.yml").read_text()
        )
        block = next(task for task in tasks
                     if task["name"] == "Check installed PCP version")
        assertion = block["block"][1]
        cases = [
            ({"rc": 2}, True, True),
            ({}, True, True),
            ({"rc": 2}, False, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.1"}, True, False),
            ({"rc": 0, "stdout": "unrecognized"}, True, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.2"}, True, True),
            ({"rc": 0, "stdout": "pminfo version 7.2.2"}, False, True),
        ]
        for probe, check, succeeds in cases:
            with self.subTest(probe=probe, check=check):
                play = self.root / "version.yml"
                play.write_text(yaml.safe_dump([{
                    "hosts": "localhost", "connection": "local",
                    "gather_facts": False,
                    "vars": {"__pcp_push_version": probe},
                    "tasks": [assertion],
                }]))
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(play)]
                    + (["--check"] if check else []),
                    env=self.environment, cwd=self.root,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=45,
                )
                self.assertEqual(result.returncode == 0, succeeds, result.stdout)
                if not succeeds:
                    self.assertIn("push requires PCP >= 7.2.2", result.stdout)
