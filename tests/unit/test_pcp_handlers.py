# SPDX-License-Identifier: MIT
"""Exercise handler scheduling with a counted substitute for service restart."""

import shutil
import yaml
from test_pcp_role_loading import AnsibleTestCase, ROOT


class HandlerScheduling(AnsibleTestCase):
    def exercise_scheduling(self, booted):
        role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", role)
        shared = role / "tasks/restart_pmproxy.yml"
        tasks = yaml.safe_load(shared.read_text())
        tasks[0].pop("service")
        tasks[0]["set_fact"] = {"restarts": "{{ restarts | int + 1 }}"}
        shared.write_text(yaml.safe_dump(tasks))
        (role / "tasks/main.yml").write_text(
            yaml.safe_dump(
                [
                    {
                        "set_fact": {
                            "__pcp_pmproxy_restart_pending": "{{ changed_configuration | default(true) }}"
                        },
                        "changed_when": "changed_configuration | default(true)",
                        "notify": ["Restart pmproxy", "Unrelated"],
                    },
                    {"include_tasks": "restart_pmproxy.yml"},
                    {
                        "assert": {
                            "that": [
                                "restarts | int == expected | int",
                                "not unrelated | default(false)",
                            ]
                        }
                    },
                ]
            )
        )
        play = self.root / "handlers.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {"__pcp_is_booted": booted, "restarts": 0},
                        "handlers": [
                            {"name": "Unrelated", "set_fact": {"unrelated": True}}
                        ],
                        "tasks": [
                            {
                                "include_role": {"name": "pcp"},
                                "vars": {"expected": 1 if booted else 0},
                            },
                            {
                                "include_role": {"name": "pcp"},
                                "vars": {
                                    "expected": 1 if booted else 0,
                                    "changed_configuration": False,
                                },
                            },
                            {
                                "include_role": {"name": "pcp"},
                                "vars": {"expected": 2 if booted else 0},
                            },
                            {"meta": "flush_handlers"},
                            {
                                "assert": {
                                    "that": [
                                        "restarts | int == " + str(2 if booted else 0),
                                        "unrelated | bool",
                                    ]
                                }
                            },
                        ],
                    }
                ]
            )
        )
        self.run_command("ansible-playbook", "-i", "localhost,", str(play))

    def test_early_restart_leaves_other_handlers_pending(self):
        self.exercise_scheduling(True)

    def test_offline_skips_service_restart(self):
        self.exercise_scheduling(False)
