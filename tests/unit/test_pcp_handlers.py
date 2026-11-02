# SPDX-License-Identifier: MIT
"""Exercise the real pmproxy service decisions with a recording service module."""

import json
import shutil

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class HandlerScheduling(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        role = self.root / "roles/pcp"
        shutil.copytree(ROOT / "roles/pcp", role)
        self.record = self.root / "services.jsonl"
        (role / "library/pcp_test_service.py").write_text("""
import json
from ansible.module_utils.basic import AnsibleModule
module = AnsibleModule(argument_spec=dict(
    name=dict(type='str'), state=dict(type='str'), enabled=dict(type='bool'),
    record=dict(type='path')), supports_check_mode=True)
with open(module.params['record'], 'a') as stream:
    stream.write(json.dumps(module.params) + '\\n')
module.exit_json(changed=False)
""")
        for path in [role / "tasks/pmproxy_service.yml", role / "handlers/main.yml"]:
            tasks = yaml.safe_load(path.read_text())
            for task in tasks:
                if "service" in task:
                    task["pcp_test_service"] = task.pop("service")
                    task["pcp_test_service"]["record"] = str(self.record)
            path.write_text(yaml.safe_dump(tasks))

    def run_scenarios(self, scenarios, external=False, check=False):
        tasks = [
            {
                "debug": {"msg": "Caller change"},
                "changed_when": True,
                "notify": "Unrelated",
            }
        ]
        for variables in scenarios:
            tasks.append(
                {
                    "include_role": {
                        "name": "pcp",
                        "tasks_from": "pmproxy_service.yml",
                    },
                    "vars": variables,
                }
            )
        tasks.append({"assert": {"that": "not unrelated | default(false)"}})
        if external:
            tasks.append(
                {
                    "debug": {"msg": "External pmproxy change"},
                    "changed_when": True,
                    "notify": "Restart pmproxy",
                }
            )
        tasks.append({"meta": "flush_handlers"})
        play = self.root / "services.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {"__pcp_is_booted": True},
                        "handlers": [
                            {"name": "Unrelated", "set_fact": {"unrelated": True}}
                        ],
                        "tasks": tasks,
                    }
                ]
            )
        )
        args = ["ansible-playbook", "-i", "localhost,", str(play)]
        if check:
            args.append("--check")
        self.run_command(*args)
        return (
            [json.loads(line) for line in self.record.read_text().splitlines()]
            if self.record.exists()
            else []
        )

    def test_changed_collector_then_unchanged_combined_host_and_external_request(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": True},
                    "__pcp_push_collector_result": {"changed": True},
                },
                {
                    "pcp_push_collector": {"enabled": True},
                    "pcp_push_client": {"enabled": True},
                    "__pcp_push_collector_result": {"changed": False},
                },
            ],
            external=True,
        )
        self.assertEqual(
            [call["state"] for call in calls], ["restarted", "started", "restarted"]
        )

    def test_each_configuration_source_triggers_restart(self):
        sources = [
            "__pcp_register_changed_log_location",
            "__pcp_pmproxy_defaults",
            "__pcp_pmproxy_local",
            "__pcp_push_collector_result",
            "__pcp_push_collector_tls",
            "__pcp_push_collector_dropin",
            "__pcp_push_collector_cleanup",
        ]
        scenarios = []
        for source in sources:
            variables = {name: {"changed": name == source} for name in sources}
            variables["pcp_push_collector"] = {"enabled": True}
            scenarios.append(variables)
        calls = self.run_scenarios(scenarios)
        self.assertEqual(
            [call["state"] for call in calls], ["restarted"] * len(sources)
        )

    def test_rest_and_archive_only_changes_without_push(self):
        calls = self.run_scenarios(
            [
                {"pcp_rest_api": True, "__pcp_pmproxy_defaults": {"changed": True}},
                {
                    "pcp_rest_api": False,
                    "__pcp_register_changed_log_location": {"changed": True},
                },
            ]
        )
        self.assertEqual([call["state"] for call in calls], ["restarted", "restarted"])
        self.assertTrue(calls[0]["enabled"])
        self.assertIsNone(calls[1]["enabled"])

    def test_disabling_collector_stops_and_disables_service(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": False},
                    "__pcp_push_collector_cleanup": {"changed": True},
                },
            ]
        )
        self.assertEqual(calls[0]["state"], "stopped")
        self.assertFalse(calls[0]["enabled"])

    def test_disabled_collector_remains_stopped_when_cleanup_is_unchanged(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": False},
                    "__pcp_push_collector_cleanup": {"changed": False},
                },
            ]
        )
        self.assertEqual(calls[0]["state"], "stopped")
        self.assertFalse(calls[0]["enabled"])

    def test_disabling_collector_preserves_requested_rest_service(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_rest_api": True,
                    "pcp_push_collector": {"enabled": False},
                    "__pcp_push_collector_cleanup": {"changed": True},
                },
                {
                    "pcp_rest_api": True,
                    "pcp_push_collector": {"enabled": False},
                    "__pcp_push_collector_cleanup": {"changed": False},
                },
            ]
        )
        self.assertEqual([call["state"] for call in calls], ["restarted", "started"])
        self.assertTrue(all(call["enabled"] for call in calls))

    def test_offline_disable_only_disables_on_boot(self):
        calls = self.run_scenarios(
            [
                {
                    "__pcp_is_booted": False,
                    "pcp_push_collector": {"enabled": False},
                },
            ]
        )
        self.assertIsNone(calls[0]["state"])
        self.assertFalse(calls[0]["enabled"])

    def test_explicit_disable_in_check_mode(self):
        calls = self.run_scenarios(
            [
                {"pcp_push_collector": {"enabled": False}},
            ],
            check=True,
        )
        self.assertEqual(calls[0]["state"], "stopped")
        self.assertFalse(calls[0]["enabled"])

    def test_unmanaged_invocation_ignores_stale_collector_results(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": True},
                    "__pcp_push_collector_result": {"changed": True},
                },
                {
                    "pcp_push_collector": {},
                    "pcp_rest_api": False,
                    "__pcp_push_collector_result": {"changed": True},
                    "__pcp_pmproxy_defaults": {"changed": True},
                },
            ]
        )
        self.assertEqual(len(calls), 1)

    def test_offline_only_enables_requested_service(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": True},
                    "__pcp_is_booted": False,
                    "__pcp_push_collector_result": {"changed": True},
                },
                {
                    "pcp_push_collector": {},
                    "__pcp_is_booted": False,
                    "__pcp_register_changed_log_location": {"changed": True},
                },
            ]
        )
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]["state"])
        self.assertTrue(calls[0]["enabled"])

    def test_service_decision_runs_in_check_mode(self):
        calls = self.run_scenarios(
            [
                {
                    "pcp_push_collector": {"enabled": True},
                    "__pcp_push_collector_result": {"changed": True},
                },
            ],
            check=True,
        )
        self.assertEqual(calls[0]["state"], "restarted")
