# SPDX-License-Identifier: MIT
"""Verify version failures and opt-in host skipping before push configuration."""

import shutil
import subprocess

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class PushVersion(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        self.role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", self.role)
        self.version_tasks = self.role / "tasks/push_version.yml"
        tasks = yaml.safe_load(self.version_tasks.read_text())
        tasks[0]["block"][0] = {
            "name": "Use the test version probe result",
            "set_fact": {"__pcp_push_version": "{{ test_probe }}"},
        }
        self.version_tasks.write_text(yaml.safe_dump(tasks))

    def test_version_assertion_in_check_and_normal_modes(self):
        cases = [
            ({"rc": 2}, True, True, None, False),
            ({}, True, True, None, False),
            ({"rc": 2}, False, False, None, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.1"}, True, False, None, False),
            ({"rc": 0, "stdout": "unrecognized"}, True, False, None, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.2"}, True, True, None, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.2"}, False, True, None, False),
            ({"rc": 0, "stdout": "pminfo version 7.2.1"}, False, True, False, True),
            ({"rc": 0, "stdout": "pminfo version 7.2.1"}, True, True, False, True),
            ({"rc": 0, "stdout": "pminfo version 7.2.2"}, False, True, False, False),
            ({"rc": 0, "stdout": "unrecognized"}, False, False, False, False),
            ({"rc": 2}, False, False, False, False),
        ]
        for probe, check, succeeds, fail_if_old, ended in cases:
            with self.subTest(probe=probe, check=check, fail_if_old=fail_if_old):
                variables = {
                    "test_probe": probe,
                    "pcp_push_collector": {"enabled": True},
                }
                if fail_if_old is not None:
                    variables["pcp_fail_if_too_old"] = fail_if_old
                play = self.root / "version.yml"
                play.write_text(
                    yaml.safe_dump(
                        [
                            {
                                "hosts": "localhost",
                                "connection": "local",
                                "gather_facts": False,
                                "vars": variables,
                                "tasks": [
                                    {
                                        "include_role": {
                                            "name": "pcp",
                                            "tasks_from": "push_version.yml",
                                        }
                                    },
                                    {"debug": {"msg": "PCP_VERSION_CONTINUED"}},
                                ],
                            }
                        ]
                    )
                )
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(play)]
                    + (["--check"] if check else []),
                    env=self.environment,
                    cwd=self.root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=45,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, succeeds, result.stdout)
                if not succeeds:
                    self.assertIn("push requires PCP >= 7.2.2", result.stdout)
                elif ended:
                    self.assertNotIn("PCP_VERSION_CONTINUED", result.stdout)
                    self.assertIn("Skipping archive push", result.stdout)
                    self.assertIn("7.2.1", result.stdout)
                else:
                    self.assertIn("PCP_VERSION_CONTINUED", result.stdout)

    def test_mixed_versions_skip_all_later_integration_plays(self):
        tests = self.root / "tests"
        tests.mkdir()
        shutil.copy2(ROOT / "tests/check_push_versions.yml", tests)
        plays = yaml.safe_load((ROOT / "tests/tests_verify_push.yml").read_text())
        # Execute the real preflight and every later skip guard. Package install
        # and actual deployment are outside this isolated version regression.
        for play in plays:
            play["become"] = False
            play["gather_facts"] = False
        plays[0]["tasks"].pop(0)
        plays[0]["tasks"][0]["include_role"]["name"] = "pcp"
        for play in plays[1:]:
            play.pop("roles", None)
            play["pre_tasks"] = play["pre_tasks"][:1]
            play["tasks"] = [{"fail": {"msg": "Unsupported scenario was not skipped"}}]
        playbook = tests / "versions.yml"
        inventory = self.root / "inventory.yml"
        for old_host in ["collector", "client1", None]:
            with self.subTest(old_host=old_host):
                for play in plays[1:]:
                    play["tasks"] = (
                        [{"debug": {"msg": "SUPPORTED_SCENARIO_CONTINUED"}}]
                        if old_host is None
                        else [{"fail": {"msg": "Unsupported scenario was not skipped"}}]
                    )
                playbook.write_text(yaml.safe_dump(plays))
                hosts = {
                    name: {
                        "ansible_connection": "local",
                        "test_probe": {
                            "rc": 0,
                            "stdout": "pminfo version "
                            + ("7.2.1" if name == old_host else "7.2.2"),
                        },
                    }
                    for name in ["collector", "client1", "client2"]
                }
                inventory.write_text(
                    yaml.safe_dump(
                        {
                            "all": {
                                "children": {
                                    "push_collectors": {
                                        "hosts": {"collector": hosts["collector"]}
                                    },
                                    "push_clients": {
                                        "hosts": {
                                            name: hosts[name]
                                            for name in ["client1", "client2"]
                                        }
                                    },
                                }
                            }
                        }
                    )
                )
                output = self.run_command(
                    "ansible-playbook", "-i", str(inventory), str(playbook)
                )
                self.assertNotIn("Unsupported scenario was not skipped", output)
                if old_host is None:
                    self.assertIn("SUPPORTED_SCENARIO_CONTINUED", output)
