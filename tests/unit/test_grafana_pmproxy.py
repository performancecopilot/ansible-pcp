# SPDX-License-Identifier: MIT
"""Validate datasource configuration without installing or starting Grafana."""

import shutil
import subprocess

import yaml

from test_pcp_role_loading import AnsibleTestCase, ROOT


class GrafanaEndpoint(AnsibleTestCase):
    def setUp(self):
        super().setUp()
        self.role = self.root / "roles/grafana"
        shutil.copytree(ROOT / "roles/grafana", self.role)
        self.rendered = self.root / "datasources.yml"
        # Exercise the real validation and template, leaving package/service
        # installation to the booted full-stack integration tests.
        (self.role / "tasks/main.yml").write_text(
            yaml.safe_dump(
                [
                    {"include_tasks": "pmproxy.yml"},
                    {
                        "template": {
                            "src": "grafana-pcp-datasources.yaml.j2",
                            "dest": str(self.rendered),
                            "mode": "0644",
                        }
                    },
                ]
            )
        )

    def configure(self, variables, expected_url=None, error=None, check_mode=False):
        self.rendered.unlink(missing_ok=True)
        play = self.root / "grafana.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": dict(
                            {
                                "__grafana_keyserver_datasource_name": "Valkey",
                                "__grafana_keyserver_datasource_type": "pcp-valkey-datasource",
                            },
                            **variables
                        ),
                        "roles": ["grafana"],
                    }
                ]
            )
        )
        arguments = ["ansible-playbook", "-i", "localhost,", str(play)]
        if check_mode:
            arguments.append("--check")
        result = subprocess.run(
            arguments,
            env=self.environment,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
        )
        if error:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stdout)
            self.assertFalse(self.rendered.exists())
        else:
            self.assertEqual(result.returncode, 0, result.stdout)
            data = yaml.safe_load(self.rendered.read_text())
            self.assertEqual(len(data["datasources"]), 3)
            self.assertEqual(
                {item["url"] for item in data["datasources"]}, {expected_url}
            )
        return result.stdout

    def test_default_and_known_custom_port(self):
        self.configure({}, "http://localhost:44322")
        self.configure(
            {
                "__pcp_push_collector_policy": {
                    "enabled": True,
                    "port": 44323,
                    "auth": "none",
                }
            },
            "http://localhost:44323",
        )

    def test_explicit_remote_https_and_ipv6_urls(self):
        for url in [
            "https://query.example:8443",
            "https://query.example",
            "http://[::1]:44323/",
        ]:
            with self.subTest(url=url):
                self.configure({"grafana_pmproxy_url": url}, url.rstrip("/"))

    def test_known_local_mutual_tls_is_rejected(self):
        for url in [
            "http://localhost:44322",
            "https://127.0.0.1:44322",
            "https://[::1]:44322",
        ]:
            with self.subTest(url=url):
                self.configure(
                    {
                        "grafana_pmproxy_url": url,
                        "__pcp_push_collector_policy": {
                            "enabled": True,
                            "port": 44322,
                            "auth": "mtls",
                        },
                    },
                    error="does not configure client certificates",
                )

    def test_main_role_rejects_mutual_tls_before_installation(self):
        shutil.copy2(
            ROOT / "roles/grafana/tasks/main.yml", self.role / "tasks/main.yml"
        )
        output = self.configure(
            {
                "__pcp_push_collector_policy": {
                    "enabled": True,
                    "port": 44322,
                    "auth": "mtls",
                }
            },
            error="does not configure client certificates",
            check_mode=True,
        )
        self.assertNotIn("Install Grafana packages", output)

    def test_explicit_other_endpoint_has_no_assumed_policy(self):
        for url in ["http://localhost:44323", "https://query.example:44322"]:
            with self.subTest(url=url):
                self.configure(
                    {
                        "grafana_pmproxy_url": url,
                        "__pcp_push_collector_policy": {
                            "enabled": True,
                            "port": 44322,
                            "auth": "mtls",
                        },
                    },
                    url,
                )

    def test_disabled_policy_restores_default_endpoint(self):
        self.configure(
            {
                "__pcp_push_collector_policy": {"enabled": False},
                "pcp_push_collector": {"enabled": True, "port": 44323, "auth": "mtls"},
            },
            "http://localhost:44322",
        )

    def test_invalid_urls_are_rejected_without_logging_credentials(self):
        for url in [
            "collector:44322",
            "http://collector/path",
            "http://user:do-not-log-this@collector",
            "http://collector?x",
            "http://collector:0",
            "http://collector\n",
        ]:
            with self.subTest(url=url):
                output = self.configure(
                    {"grafana_pmproxy_url": url},
                    error="grafana_pmproxy_url must be one",
                )
                self.assertNotIn("do-not-log-this", output)


if __name__ == "__main__":
    import unittest

    unittest.main()
