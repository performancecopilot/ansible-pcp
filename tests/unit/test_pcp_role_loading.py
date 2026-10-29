# SPDX-License-Identifier: MIT
"""Exercise real Ansible loading without a separately installed PCP collection."""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


class AnsibleTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name)
        self.collections = self.root / "collections"
        self.collections.mkdir()
        configuration = self.root / "ansible.cfg"
        configuration.write_text("[defaults]\n")
        library = self.root / "empty-library"
        library.mkdir()
        self.environment = dict(
            os.environ,
            ANSIBLE_CONFIG=str(configuration),
            ANSIBLE_HOME=str(self.root / "ansible"),
            ANSIBLE_LOCAL_TEMP=str(self.root / "local"),
            ANSIBLE_REMOTE_TEMP=str(self.root / "remote"),
            ANSIBLE_COLLECTIONS_PATH=str(self.collections),
            ANSIBLE_COLLECTIONS_SCAN_SYS_PATH="false",
            ANSIBLE_ROLES_PATH=str(self.root / "roles"),
            ANSIBLE_LIBRARY=str(library),
        )

    def run_command(self, *arguments):
        result = subprocess.run(
            arguments,
            env=self.environment,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout


class RoleLoading(AnsibleTestCase):
    def copy_role(self, destination):
        shutil.copytree(
            ROOT / "roles/pcp",
            destination,
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    def check_role(self, name):
        play = self.root / "play.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "__pcp_pmlogger_control_path": str(self.root / "control"),
                            "__pcp_pmlogger_timers_path": str(self.root / "timers"),
                        },
                        "tasks": [{"include_role": {"name": name}}],
                    }
                ]
            )
        )
        return self.run_command(
            "ansible-playbook",
            "--check",
            "-i",
            "localhost,",
            str(play),
            "--extra-vars",
            json.dumps(
                {
                    "__pcp_pmlogger_control_path": str(self.root / "control"),
                    "__pcp_pmlogger_timers_path": str(self.root / "timers"),
                }
            ),
        )

    def make_wrapper(self, wrapper):
        """Match metrics' roles symlink and filesystem include_role pattern."""
        self.copy_role(wrapper / "vendor/ansible-pcp/roles/pcp")
        (wrapper / "roles").symlink_to("vendor/ansible-pcp/roles")
        tasks = wrapper / "tasks"
        tasks.mkdir()
        (tasks / "main.yml").write_text(
            yaml.safe_dump(
                [
                    {
                        "include_role": {
                            "name": "{{ role_path }}/roles/pcp",
                            "tasks_from": "push_validate.yml",
                        }
                    }
                ]
            )
        )

    def make_collection(self, destination):
        self.copy_role(destination / "roles/pcp")
        plugins = destination / "plugins/modules"
        plugins.mkdir(parents=True)
        (plugins / "pcp_push.py").symlink_to("../../roles/pcp/library/pcp_push.py")
        (destination / "galaxy.yml").write_text(
            yaml.safe_dump(
                {
                    "namespace": "performancecopilot",
                    "name": "metrics",
                    "version": "1.0.0",
                    "readme": "README.md",
                    "authors": ["PCP developers"],
                    "license": ["MIT"],
                }
            )
        )
        (destination / "README.md").write_text("PCP role loading test\n")
        # Run only the non-mutating validation entry point.
        (destination / "roles/pcp/tasks/main.yml").write_text(
            "- include_tasks: push_validate.yml\n"
        )

    def test_standalone_role(self):
        role = self.root / "roles/pcp"
        self.copy_role(role)
        (role / "tasks/main.yml").write_text("- include_tasks: push_validate.yml\n")
        self.check_role("pcp")

    def test_vendored_filesystem_role(self):
        wrapper = self.root / "roles/metrics"
        self.make_wrapper(wrapper)
        self.check_role("metrics")

    def test_vendored_role_in_collection_with_exported_module(self):
        collection = self.collections / "ansible_collections/fedora/linux_system_roles"
        wrapper = collection / "roles/metrics"
        self.make_wrapper(wrapper)
        # A collection converter must export nested roles' libraries too.
        # Ansible does not search a collection role's local library directory.
        plugins = collection / "plugins/modules"
        plugins.mkdir(parents=True)
        shutil.copy2(ROOT / "roles/pcp/library/pcp_push.py", plugins / "pcp_push.py")
        self.check_role("fedora.linux_system_roles.metrics")

    def test_source_collection(self):
        collection = self.collections / "ansible_collections/performancecopilot/metrics"
        self.make_collection(collection)
        self.check_role("performancecopilot.metrics.pcp")

    def test_built_collection(self):
        source = self.root / "source"
        self.make_collection(source)
        self.run_command(
            "ansible-galaxy",
            "collection",
            "build",
            str(source),
            "--output-path",
            str(self.root),
        )
        self.run_command(
            "ansible-galaxy",
            "collection",
            "install",
            str(self.root / "performancecopilot-metrics-1.0.0.tar.gz"),
            "--collections-path",
            str(self.collections),
            "--offline",
        )
        self.check_role("performancecopilot.metrics.pcp")


if __name__ == "__main__":
    unittest.main()
