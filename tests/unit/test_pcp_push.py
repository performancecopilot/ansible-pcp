# SPDX-License-Identifier: MIT
"""Run with: /usr/bin/python3 -m unittest discover -s tests/unit."""

import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[2] / "roles/pcp/library/pcp_push.py"
SPEC = importlib.util.spec_from_file_location("pcp_push", SOURCE)
push = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(push)


class Settings(unittest.TestCase):
    def test_url_normalization(self):
        for before, after in [
            ("http://collector", "http://collector:44322"),
            ("https://[::1]/", "https://[::1]:44322"),
            ("https://collector:1234", "https://collector:1234"),
        ]:
            self.assertEqual(push.collector_url(before), after)

    def test_url_rejections(self):
        for value in [
            None,
            [],
            "collector",
            "http://a,b",
            "https://u:p@a",
            "http://a/path",
            "http://a?x",
            "http://a#f",
            "http://a?",
            "http://a:0",
            "http://a:65536",
            "http://a:",
            "http://a;id",
            "https://a/$(id)",
            "https://a\\evil",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                push.collector_url(value)


class Collector(unittest.TestCase):
    def test_conflicting_port_option_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as root, patch.object(push, "ROOT", root):
            directory = pathlib.Path(root) / "pmproxy"
            directory.mkdir()
            options = directory / "pmproxy.options"
            options.write_text("# caller options\n-p 1234\n")
            with self.assertRaisesRegex(ValueError, "pmproxy.options:2 conflicts"):
                push.collector_plan(dict(enabled=True), str(directory / "timers"), "14")

    def test_disabling_never_managed_collector_preserves_custom_settings(self):
        with tempfile.TemporaryDirectory() as root, patch.object(push, "ROOT", root):
            directory = pathlib.Path(root) / "pmproxy"
            directory.mkdir()
            config = directory / "pmproxy.conf"
            original = "[pmlogger]\nenabled = true\nauthenticate = true\n"
            config.write_text(original)
            timers = directory / "timers"
            timers.write_text('PMLOGGER_DAILY_PARAMS="-E"\n')
            plan = push.collector_plan(dict(enabled=False), str(timers), "14")
            self.assertEqual(plan[str(config)], original)
            self.assertEqual(plan[str(timers)], timers.read_text())

    def test_lifecycle_and_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as root, patch.object(push, "ROOT", root):
            directory = pathlib.Path(root) / "pmproxy"
            directory.mkdir()
            conf = directory / "pmproxy.conf"
            conf.write_text(
                "[keys]\nservers = unrelated:6379\n[pmlogger]\nenabled = true\n[pmproxy]\nhttp.enabled = false\n"
            )
            timers = str(directory / "timers")
            pathlib.Path(timers).write_text(
                '# caller comment\nPMLOGGER_DAILY_PARAMS="-E"\n'
            )

            def apply(plan):
                for path, content in plan.items():
                    if path.startswith("/etc/systemd/"):
                        continue
                    if content is None:
                        pathlib.Path(path).unlink(missing_ok=True)
                    else:
                        pathlib.Path(path).write_text(content)

            for auth in ("none", "basic", "mtls", "none"):
                config = dict(enabled=True, auth=auth)
                plan = push.collector_plan(config, timers, "5")
                apply(plan)
                self.assertEqual(push.collector_plan(config, timers, "5"), plan)
                self.assertIn("servers = unrelated:6379", conf.read_text())
                self.assertIn("cached = false", conf.read_text())
                self.assertIn("-E --discard 5", pathlib.Path(timers).read_text())
                self.assertEqual(
                    "--certreqd" in (directory / "pmproxy.options").read_text(),
                    auth == "mtls",
                )
            apply(push.collector_plan(dict(enabled=False), timers, "5"))
            self.assertIn("http.enabled = false", conf.read_text())
            self.assertIn("enabled = false", conf.read_text())
            self.assertNotIn("authenticate", conf.read_text())
            self.assertEqual(
                pathlib.Path(timers).read_text(),
                '# caller comment\nPMLOGGER_DAILY_PARAMS="-E"\n',
            )

    def test_ini_preserves_comments_and_other_sections(self):
        text = "# keep\n[a]\nvalue = 1\n[b]\nvalue = 2\n"
        changed, old = push.ini_value(text, "a", "value", "value = 3\n")
        self.assertEqual(old, "value = 1\n")
        self.assertEqual(changed, text.replace("value = 1", "value = 3"))


if __name__ == "__main__":
    unittest.main()
