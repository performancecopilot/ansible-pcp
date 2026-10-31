# SPDX-License-Identifier: MIT
#
# Run with "python3 build/ci/ci-run.py ...".  The file intentionally has no
# shebang: ansible-test only accepts "#!/usr/bin/env python" in a collection,
# which does not exist on every supported host.
"""Run the ansible-pcp integration testsuite in systemd-enabled containers.

The runner mirrors what the downstream ``ansible-pcp`` package test does: it
starts one systemd-enabled container per selected distribution, makes it
reachable over SSH and executes every ``tests/tests_*.yml`` playbook against
it (the playbooks are *not* wrapped in TMT, Beaker or any other harness).

It is used by the GitHub Actions workflows in ``.github/workflows`` and can be
used locally to reproduce a CI job.

Examples
--------
    ./build/ci/ci-run.py list
    ./build/ci/ci-run.py list --group pr --json
    ./build/ci/ci-run.py reproduce fedora45
    ./build/ci/ci-run.py reproduce --group pr
    ./build/ci/ci-run.py test fedora45 --test tests_verify_basic.yml
    ./build/ci/ci-run.py shell fedora45
    ./build/ci/ci-run.py destroy fedora45
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the environment
    sys.exit("PyYAML is required, install it with: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "build" / "ci"
PLATFORM_DIR = CI_DIR / "platforms"
CONTAINERFILE = CI_DIR / "Containerfile"
DEFAULT_ARTIFACTS = REPO_ROOT / "artifacts"
STATE_ROOT = Path(os.environ.get("CI_STATE_DIR", Path(tempfile.gettempdir()) / "ansible-pcp-ci"))

DEFAULT_TIMEOUT = int(os.environ.get("CI_TEST_TIMEOUT", "1800"))
# ansible-core version used unless a platform pins a different one.  EL8 still
# ships Python 3.6 as the system interpreter, which requires ansible-core 2.16.
DEFAULT_ANSIBLE_CORE = os.environ.get("CI_ANSIBLE_CORE", ">=2.19,<2.23")
# ansible-core does not support every brand new Python release and drops
# support for old ones: 2.19 and newer, which is the default below, need Python
# 3.11.  Prefer the newest interpreter ansible-core supports for the
# controller virtualenv when one exists.
CONTROLLER_PYTHONS = ("python3.14", "python3.13", "python3.12", "python3.11")
MIN_CONTROLLER_PYTHON = (3, 11)
DEFAULT_COLLECTIONS = {
    "ansible.posix": "*",
    # provides the zypper backend used by the package module on SUSE
    "community.general": "*",
}
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=5",
    "-o", "LogLevel=ERROR",
]


def log(message: str) -> None:
    print(f"[ci] {message}", flush=True)


def controller_python() -> str:
    """Interpreter used for the ansible-core virtualenv.

    Some ansible-core versions do not run on the newest
    Python of the host, so pick the newest interpreter ansible-core supports
    instead of blindly using the default python3.  ``CI_PYTHON`` overrides the
    search and is not checked, so a platform that pins an ansible-core release
    with different requirements can point at any interpreter it likes.
    """
    requested = os.environ.get("CI_PYTHON")
    if requested:
        return requested
    for name in CONTROLLER_PYTHONS:
        path = shutil.which(name)
        if path:
            return path
    # The default ansible-core range (2.19 and newer) needs Python 3.11 or
    # newer.  Falling back to an older interpreter would only make pip fail
    # later with a "no matching distribution" error for ansible-core, so say
    # what is actually missing.
    if sys.version_info[:2] >= MIN_CONTROLLER_PYTHON:
        return sys.executable
    raise SystemExit(
        "No Python 3.11 or newer found for the ansible-core controller; "
        "install python3.11+ or set CI_PYTHON to a suitable interpreter"
    )


# ---------------------------------------------------------------------------
# Platform definitions
# ---------------------------------------------------------------------------
def available_platforms() -> list[str]:
    return sorted(p.stem for p in PLATFORM_DIR.glob("*.yml"))


def load_platform(name: str) -> dict:
    path = PLATFORM_DIR / f"{name}.yml"
    if not path.is_file():
        raise SystemExit(
            f"Unknown platform '{name}'. Available platforms: {', '.join(available_platforms())}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["id"] = name
    if not data.get("base_image"):
        raise SystemExit(f"{path}: 'base_image' is required")
    data.setdefault("packages", [])
    data.setdefault("cgroup_v1", False)
    data.setdefault("skip", {})
    data.setdefault("groups", [])
    return data


def platforms_in_group(group: str) -> list[str]:
    if group == "all":
        return available_platforms()
    selected = [name for name in available_platforms() if group in load_platform(name)["groups"]]
    if not selected:
        raise SystemExit(f"No platform is part of group '{group}'")
    return selected


def all_tests() -> list[str]:
    return sorted(p.name for p in (REPO_ROOT / "tests").glob("tests_*.yml"))


# ---------------------------------------------------------------------------
# Podman helpers
# ---------------------------------------------------------------------------
def is_ubuntu() -> bool:
    try:
        return 'NAME="Ubuntu"' in Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return False


def podman_prefix() -> list[str]:
    """Return the podman command, using rootful podman when not root.

    Rootful podman is required: the containers are privileged, run systemd and
    need routable addresses so that Ansible can connect to them over SSH.
    """
    if os.geteuid() == 0:
        return ["podman"]
    if is_ubuntu():
        # Do not leak a rootless XDG_RUNTIME_DIR/socket into the sudo session.
        return ["sudo", "-E", "XDG_RUNTIME_DIR=", "podman"]
    return ["sudo", "-E", "podman"]


class Runner:
    def __init__(self, platform: dict, artifacts: Path | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.platform = platform
        self.id = platform["id"]
        self.safe_id = self.id.replace(".", "-")
        self.container = f"ansible-pcp-ci-{self.safe_id}"
        self.network = f"{self.container}-net"
        self.image = f"{self.container}:latest"
        self.state = STATE_ROOT / self.safe_id
        self.workspace = self.state / "workspace"
        self.key = self.state / "id_ed25519"
        self.inventory = self.state / "inventory.ini"
        self.artifacts = Path(artifacts) if artifacts else DEFAULT_ARTIFACTS
        self.timeout = timeout
        self.podman = podman_prefix()
        self.ansible_core = platform.get("ansible_core", DEFAULT_ANSIBLE_CORE)
        self.collections = platform.get("collections", DEFAULT_COLLECTIONS)
        self.venv = self.state / "venv"

    # -- low level ---------------------------------------------------------
    def run(self, cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
        log("+ " + " ".join(cmd))
        return subprocess.run(cmd, check=check, **kwargs)

    def podman_run(self, *args: str, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
        return self.run([*self.podman, *args], check=check, **kwargs)

    def in_container(self, command: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.podman_run(
            "exec", self.container, "bash", "-c", command,
            check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def container_running(self) -> bool:
        result = self.podman_run(
            "inspect", "-f", "{{.State.Running}}", self.container,
            check=False, capture_output=True, text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def container_ip(self) -> str:
        result = self.podman_run(
            "inspect", "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            self.container, capture_output=True, text=True,
        )
        ip = result.stdout.strip()
        if not ip:
            raise SystemExit(f"No IP address found for container {self.container}")
        return ip

    # -- lifecycle ---------------------------------------------------------
    def build(self) -> None:
        args = [
            "build", "-t", self.image, "-f", str(CONTAINERFILE),
            "--build-arg", f"BASE_IMAGE={self.platform['base_image']}",
            "--build-arg", f"EXTRA_PACKAGES={' '.join(self.platform['packages'])}",
            str(CI_DIR),
        ]
        self.podman_run(*args)

    def start(self) -> None:
        self.podman_run("rm", "-f", self.container, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.podman_run("network", "rm", "-f", self.network, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.podman_run("network", "create", self.network,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        args = [
            "run", "-d", "--name", self.container,
            "--network", self.network,
            "--hostname", self.safe_id,
            # Privileged + a real init are needed for the roles to manage
            # services through systemd.
            "--privileged",
            "--systemd=always",
            "--security-opt", "label=disable",
        ]
        # EL8's systemd requires the legacy cgroup hierarchy.
        if self.platform["cgroup_v1"]:
            args += ["-v", "/sys/fs/cgroup:/sys/fs/cgroup:ro"]
        args.append(self.image)
        self.podman_run(*args, stdout=subprocess.DEVNULL)

    def wait_for_sshd(self) -> None:
        log(f"Waiting for sshd in {self.container}")
        # Debian/Ubuntu ship ssh.service and only provide sshd.service as a
        # linked alias, which "systemctl enable" refuses to operate on.  Start
        # whichever unit exists and consider the server up once one is active.
        start = (
            "for unit in ssh.service sshd.service; do "
            "systemctl cat \"$unit\" >/dev/null 2>&1 || continue; "
            "systemctl start \"$unit\" >/dev/null 2>&1; "
            "systemctl is-active --quiet \"$unit\" && exit 0; "
            "done; exit 1"
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if not self.container_running():
                raise SystemExit(f"Container {self.container} exited unexpectedly")
            if self.in_container(start, check=False).returncode == 0:
                return
            time.sleep(2)
        raise SystemExit(f"sshd did not start in {self.container}")

    def install_ssh_key(self) -> None:
        if not self.key.is_file():
            self.state.mkdir(parents=True, exist_ok=True)
            self.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "ansible-pcp CI",
                      "-f", str(self.key)], stdout=subprocess.DEVNULL)
        self.in_container("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        self.podman_run("cp", f"{self.key}.pub", f"{self.container}:/root/.ssh/authorized_keys")
        self.in_container("chmod 600 /root/.ssh/authorized_keys && restorecon -R /root/.ssh 2>/dev/null || true")

    def wait_for_ssh(self) -> str:
        ip = self.container_ip()
        log(f"Waiting for SSH on {ip}")
        deadline = time.time() + 180
        while time.time() < deadline:
            result = subprocess.run(
                ["ssh", *SSH_OPTS, "-i", str(self.key), f"root@{ip}", "true"],
                check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return ip
            time.sleep(2)
        raise SystemExit(f"Unable to connect to {self.container} ({ip}) over SSH")

    def write_inventory(self, ip: str) -> None:
        interpreter = self.platform.get("python_interpreter", "/usr/bin/python3")
        common_args = " ".join(SSH_OPTS)
        self.inventory.write_text(
            "[all]\n"
            f"{ip} ansible_connection=ssh ansible_user=root "
            f"ansible_ssh_private_key_file={self.key} "
            f"ansible_python_interpreter={interpreter} "
            f"ansible_ssh_common_args='{common_args}'\n",
            encoding="utf-8",
        )

    def refresh_package_cache(self) -> None:
        """Refresh package metadata like a freshly provisioned system would.

        The images are built with a cleaned package cache (in particular apt
        drops /var/lib/apt/lists), while the playbooks install packages without
        requesting a cache refresh themselves.
        """
        refresh = (
            "if command -v apt-get >/dev/null 2>&1; then "
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq; "
            "elif command -v zypper >/dev/null 2>&1; then "
            "zypper --non-interactive --quiet refresh; "
            "fi"
        )
        log(f"Refreshing package metadata in {self.container}")
        self.in_container(refresh)

    def setup(self) -> str:
        self.state.mkdir(parents=True, exist_ok=True)
        self.build()
        self.start()
        self.wait_for_sshd()
        self.install_ssh_key()
        ip = self.wait_for_ssh()
        self.write_inventory(ip)
        self.refresh_package_cache()
        log(f"Platform {self.id} is ready at {ip}")
        return ip

    def destroy(self) -> None:
        self.podman_run("rm", "-f", self.container, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.podman_run("network", "rm", "-f", self.network, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.podman_run("rmi", "-f", self.image, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.state.is_dir():
            shutil.rmtree(self.state, ignore_errors=True)
        log(f"Removed {self.container}")

    def shell(self) -> None:
        os.execvp(self.podman[0], [*self.podman, "exec", "-it", self.container, "bash"])

    # -- ansible -----------------------------------------------------------
    def ansible_bin(self, name: str) -> Path:
        return self.venv / "bin" / name

    def ensure_ansible(self) -> None:
        """Create a per-platform virtualenv with the requested ansible-core."""
        marker = self.venv / "ansible-core-spec"
        python = controller_python()
        spec = f"{self.ansible_core}|{python}"
        have = self.ansible_bin("ansible-playbook").is_file() and marker.is_file()
        if have and marker.read_text(encoding="utf-8").strip() == spec:
            return
        log(f"Installing ansible-core{self.ansible_core} with {python} for {self.id}")
        shutil.rmtree(self.venv, ignore_errors=True)
        self.run([python, "-m", "venv", str(self.venv)])
        pip = [str(self.venv / "bin" / "python"), "-m", "pip"]
        self.run([*pip, "install", "-q", "--upgrade", "pip"])
        self.run([*pip, "install", "-q", f"ansible-core{self.ansible_core}"])
        marker.write_text(spec + "\n", encoding="utf-8")

    # -- tests -------------------------------------------------------------
    def prepare_workspace(self) -> Path:
        """Lay the collection out so that FQCN role names resolve."""
        collection = self.workspace / "ansible_collections" / "performancecopilot" / "metrics"
        if collection.is_dir():
            shutil.rmtree(collection)
        collection.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            REPO_ROOT, collection,
            ignore=shutil.ignore_patterns(".git", "artifacts", "__pycache__", "*.pyc"),
            symlinks=True,
        )
        missing = []
        for name, version in self.collections.items():
            namespace, collection_name = name.split(".", 1)
            if not (self.workspace / "ansible_collections" / namespace / collection_name).is_dir():
                missing.append(name if version == "*" else f"{name}:{version}")
        if missing:
            # ansible.posix is a collection dependency (galaxy.yml), while
            # community.general provides the zypper backend used on SUSE.
            # Galaxy occasionally answers with a server error, so retry.
            for attempt in range(1, 4):
                try:
                    self.run(
                        [str(self.ansible_bin("ansible-galaxy")), "collection", "install",
                         *missing, "--collections-path", str(self.workspace)],
                        env=self.ansible_env(),
                    )
                    break
                except subprocess.CalledProcessError:
                    if attempt == 3:
                        raise
                    log(f"ansible-galaxy failed (attempt {attempt}), retrying")
                    time.sleep(5 * attempt)
        return collection

    def ansible_env(self) -> dict:
        env = os.environ.copy()
        env.update({
            "PATH": f"{self.venv / 'bin'}:{env.get('PATH', '')}",
            "ANSIBLE_COLLECTIONS_PATH": str(self.workspace),
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_FORCE_COLOR": "0",
            "PYTHONUNBUFFERED": "1",
        })
        return env

    def selected_tests(self, only: list[str] | None) -> list[str]:
        tests = all_tests()
        if not only:
            return tests
        selected = []
        for requested in only:
            name = requested if requested.endswith(".yml") else f"{requested}.yml"
            if name not in tests:
                raise SystemExit(
                    f"Unknown test '{requested}'. Available tests: {', '.join(tests)}"
                )
            selected.append(name)
        return selected

    def run_playbook(self, collection: Path, test: str, logfile: Path) -> tuple[int, bool]:
        cmd = [
            str(self.ansible_bin("ansible-playbook")),
            "-i", str(self.inventory),
            "-v",
            str(collection / "tests" / test),
        ]
        timed_out = False
        with open(logfile, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(
                cmd, cwd=collection, env=self.ansible_env(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )

            def tee() -> None:
                assert proc.stdout is not None
                for line in iter(proc.stdout.readline, ""):
                    fh.write(line)
                    fh.flush()
                    sys.stdout.write(line)
                    sys.stdout.flush()

            reader = threading.Thread(target=tee, daemon=True)
            reader.start()
            try:
                rc = proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                rc = 124
                fh.write(f"\n[ci] Test timed out after {self.timeout} seconds\n")
            reader.join(timeout=10)
        return rc, timed_out

    def test(self, only: list[str] | None = None) -> int:
        if not self.container_running():
            raise SystemExit(
                f"Container {self.container} is not running, run 'ci-run.py setup {self.id}' first"
            )
        if not self.inventory.is_file():
            self.write_inventory(self.container_ip())

        self.ensure_ansible()
        collection = self.prepare_workspace()
        result_dir = self.artifacts / "test" / self.id
        result_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for test in self.selected_tests(only):
            reason = self.platform["skip"].get(test)
            if reason:
                log(f"SKIP {test}: {reason}")
                results.append({"test": test, "status": "skipped", "reason": reason, "rc": None})
                continue
            log(f"RUN  {test}")
            started = time.time()
            rc, timed_out = self.run_playbook(collection, test, result_dir / f"{test}.log")
            duration = round(time.time() - started, 1)
            if rc == 0:
                status = "passed"
            elif timed_out:
                status = "timeout"
            else:
                status = "failed"
            log(f"{status.upper():7} {test} ({duration}s)")
            results.append({"test": test, "status": status, "rc": rc, "duration": duration})

        summary = {
            "platform": self.id,
            "image": self.platform["base_image"],
            "results": results,
        }
        (result_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        self.write_summary(summary, result_dir)
        return 0 if all(r["status"] in ("passed", "skipped") for r in results) else 1

    def write_summary(self, summary: dict, result_dir: Path) -> None:
        ok = all(r["status"] in ("passed", "skipped") for r in summary["results"])
        lines = [
            f"## Integration tests: `{summary['platform']}`",
            "",
            f"Image: `{summary['image']}`",
            "",
            "| Test | Result | Duration |",
            "|------|--------|----------|",
        ]
        for result in summary["results"]:
            icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "timeout": "TIMEOUT"}[result["status"]]
            duration = f"{result.get('duration', '')}s" if result.get("duration") else ""
            note = f" ({result['reason']})" if result.get("reason") else ""
            lines.append(f"| `{result['test']}` | {icon}{note} | {duration} |")
        lines.append("")
        lines.append(f"Overall: {'**success**' if ok else '**failure**'}")
        text = "\n".join(lines) + "\n"
        (result_dir / "summary.md").write_text(text, encoding="utf-8")
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as fh:
                fh.write(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def add_platform_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("platforms", nargs="*", help="platform ids (see 'list')")
    parser.add_argument("--group", help="run all platforms of a group (e.g. pr, all)")


def platforms_from_args(args: argparse.Namespace) -> list[str]:
    selected = list(args.platforms)
    if args.group:
        selected += platforms_in_group(args.group)
    if not selected:
        raise SystemExit("Specify at least one platform or use --group")
    # keep the order, drop duplicates
    return list(dict.fromkeys(selected))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS,
                        help=f"artifacts directory (default: {DEFAULT_ARTIFACTS})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"per playbook timeout in seconds (default: {DEFAULT_TIMEOUT})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list platforms")
    p_list.add_argument("--group", help="only platforms of this group")
    p_list.add_argument("--json", action="store_true", help="print a JSON array")

    p_tests = sub.add_parser("tests", help="list the tests/tests_*.yml playbooks")

    for name, help_text in (
        ("setup", "build the image and start the container"),
        ("test", "run the test playbooks"),
        ("reproduce", "setup + test"),
        ("shell", "open a shell in the container"),
        ("destroy", "remove the container, network and image"),
    ):
        p = sub.add_parser(name, help=help_text)
        add_platform_argument(p)
        if name in ("test", "reproduce"):
            p.add_argument("--test", action="append", dest="tests",
                           help="only run this playbook (can be repeated)")

    args = parser.parse_args(argv)

    if args.command == "list":
        platforms = platforms_in_group(args.group) if args.group else available_platforms()
        if args.json:
            print(json.dumps(platforms))
        else:
            for name in platforms:
                data = load_platform(name)
                groups = ",".join(data["groups"]) or "-"
                label = data.get("name", name)
                print(f"{name:22} {label:26} {data['base_image']:52} groups={groups}")
        return 0

    if args.command == "tests":
        for test in all_tests():
            print(test)
        return 0

    platforms = platforms_from_args(args)
    exit_code = 0
    for name in platforms:
        try:
            runner = Runner(load_platform(name), artifacts=args.artifacts, timeout=args.timeout)
            if args.command == "setup":
                runner.setup()
            elif args.command == "test":
                exit_code = max(exit_code, runner.test(args.tests))
            elif args.command == "reproduce":
                runner.setup()
                exit_code = max(exit_code, runner.test(args.tests))
            elif args.command == "shell":
                runner.shell()
            elif args.command == "destroy":
                runner.destroy()
        except (SystemExit, subprocess.CalledProcessError) as error:
            # A single platform is used by the CI jobs, propagate the failure.
            if len(platforms) == 1:
                raise
            print(f"[ci] ERROR {name}: {error}", file=sys.stderr, flush=True)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
