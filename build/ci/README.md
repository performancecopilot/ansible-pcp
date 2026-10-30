# Integration tests (containers)

The collection is verified by running every `tests/tests_*.yml` playbook
against a systemd-enabled container of each supported Linux distribution.
This is the same approach that the downstream `ansible-pcp` package test uses,
with one difference: the containers are started with `podman` and Ansible
connects to them over SSH, so no TMT, Beaker or other downstream test
technology is involved.

The machinery lives in `build/ci`:

| Path | Purpose |
|------|---------|
| `ci-run.py` | builds/starts containers, runs the playbooks, writes artifacts |
| `Containerfile` | generic systemd + sshd + python image, parameterised by base image |
| `platforms/*.yml` | one file per distribution: base image, group membership, skipped tests |

## Platforms

| Id | Image | `pr` group |
|----|-------|------------|
| `centos-stream9` | `quay.io/centos/centos:stream9` | no |
| `centos-stream10` | `quay.io/centos/centos:stream10` | yes |
| `fedora43` | `registry.fedoraproject.org/fedora:43` | no |
| `fedora44` | `registry.fedoraproject.org/fedora:44` | no |
| `fedora45` | `registry.fedoraproject.org/fedora:45` | yes |
| `debian12` | `docker.io/library/debian:12` | no |
| `debian13` | `docker.io/library/debian:13` | yes |
| `ubuntu2204` | `docker.io/library/ubuntu:22.04` | no |
| `ubuntu2404` | `docker.io/library/ubuntu:24.04` | yes |
| `ubuntu2604` | `docker.io/library/ubuntu:26.04` | no |
| `opensuse-leap15.6` | `registry.opensuse.org/opensuse/leap:15.6` | no |
| `opensuse-leap16.0` | `registry.opensuse.org/opensuse/leap:16.0` | yes |

The `pr` group is the subset that runs automatically for every pull request;
the complete matrix runs on demand (see below).

RHEL itself is not started on GitHub-hosted runners: a real RHEL container
needs a subscription, and the freely available UBI images only expose a subset
of the RHEL package set (`pcp` is not part of it).  Enterprise Linux is
therefore covered through CentOS Stream, whose `distribution` fact is `CentOS`
so the same role code paths and the same platform-gated playbooks are
executed.

## Known platform limitations

Some playbooks cannot run on some distributions for reasons that are outside
of the test harness.  They are listed under `skip` in the platform file, are
reported as `SKIP` in the summary and never fail the job:

| Platform(s) | Skipped test | Reason |
|-------------|--------------|--------|
| Debian, Ubuntu | `tests_verify_postfix.yml` | the distribution `pcp` package does not ship the postfix PMDA |
| Debian, Ubuntu | `tests_verify_spark.yml` | the `spark` role enables PCP agents using the RPM `.NeedInstall` mechanism, which the Debian packaging does not have |
| openSUSE Leap | everything that uses the `pcp`, `keyserver`, `repository` or `spark` roles | the collection has no `vars/Suse.yml` yet, so those tasks fail on undefined variables |

openSUSE Leap 15.6 still ships Python 3.6 as `python3`, which current
`ansible-core` releases refuse to use as a target interpreter; the platform
file therefore installs `python311` and points `ansible_python_interpreter` at
it.

Fedora 45 ships Python 3.15, which `ansible-core` 2.21 does not support as a
target interpreter yet (module execution fails with a `dataclasses` error).
Its platform file pins `ansible_core: ">=2.22.0rc1"`, which works with Python
3.15; the pin can be dropped once 2.22 is the default version.

## GitHub Actions

* `.github/workflows/ci.yml` runs the `pr` group automatically for every pull
  request, for the merge queue and for pushes to `main`.  It can also be run
  manually with the complete matrix.
* `.github/workflows/citest.yml` implements the `/citest` pull request command
  and a manual `workflow_dispatch` trigger for the complete matrix.  Results
  are published as commit statuses named `ci/containers/<platform>`.

Examples of the pull request command (only repository owners, members and
collaborators may use it):

```text
/citest                       # all platforms
/citest pr                    # the platforms from the pr group
/citest fedora45 ubuntu2404   # just these two
```

Every platform job uploads the per-playbook logs and a
`summary.md`/`summary.json` as the `test-artifacts-<platform>` artifact, writes
a table to the job summary and always tears its container down.

`.github/workflows/integration-tests.yml` is the reusable workflow shared by
`ci.yml` and `citest.yml`.

## Running locally

The runner only needs `podman`, `python3` with PyYAML and network access (it
creates its own virtualenv with `ansible-core` and installs the required
collections).  The controller virtualenv is built from the newest of
`python3.14`, `python3.13`, `python3.12`, `python3.11` and `python3.10` found in
`PATH`, or from `$CI_PYTHON`; a platform that asks for `ansible-core` 2.22
(Fedora 45) needs at least Python 3.13 for the controller, so the GitHub
workflow installs one with `actions/setup-python`:

```bash
# list platforms / playbooks
python3 build/ci/ci-run.py list
python3 build/ci/ci-run.py tests

# full run for one platform
python3 build/ci/ci-run.py reproduce fedora45

# just the pr group
python3 build/ci/ci-run.py reproduce --group pr

# a single playbook, then a shell inside the still-running container
python3 build/ci/ci-run.py test fedora45 --test tests_verify_basic.yml
python3 build/ci/ci-run.py shell fedora45

# clean up
python3 build/ci/ci-run.py destroy fedora45
```

Because the containers are privileged and must be reachable over SSH, the
runner uses rootful podman (`podman` when run as root, `sudo podman`
otherwise), which also means that `podman` must be usable without a password
prompt.  Artifacts are written to `artifacts/test/<platform>/`.

## How a test run works

1. The generic `Containerfile` is built with the platform's base image; it
   installs `systemd`, `openssh-server` and Python, plus the `packages` listed
   in the platform file.
2. The container is started with `--privileged --systemd=always` on a
   dedicated podman network.  Platforms whose systemd only handles the legacy
   cgroup hierarchy set `cgroup_v1: true`, which mounts `/sys/fs/cgroup` from
   the host.
3. An SSH key is installed, the package metadata is refreshed (like on a
   freshly provisioned system) and the collection is laid out under
   `ansible_collections/performancecopilot/metrics` so that the
   `performancecopilot.metrics.*` role names resolve.
4. Each `tests/tests_*.yml` playbook is executed with
   `ansible-playbook -i <container>`, exactly like the downstream test does.
   Playbooks that detect an unsupported platform and call `meta: end_host`
   pass without doing anything.
5. A non-zero exit code of a playbook fails the run, but the remaining
   playbooks are still executed so a single job reports every failure.

## Adding a platform

Create `build/ci/platforms/<id>.yml`:

```yaml
---
name: openSUSE Tumbleweed
base_image: registry.opensuse.org/opensuse/tumbleweed:latest
packages: []                           # optional extra packages for the image
cgroup_v1: false                       # true for EL8 style systemd
python_interpreter: /usr/bin/python3   # optional, defaults to /usr/bin/python3
ansible_core: ">=2.19,<2.23"           # optional, defaults to the CI version
collections:                           # optional, defaults to the CI versions
  ansible.posix: "*"
  community.general: "*"
groups:
  - all
  - pr                                 # only for platforms tested on every PR
skip:
  tests_verify_mssql.yml: SQL Server is not available for this distribution
```

Then check it locally with `python3 build/ci/ci-run.py reproduce <id>`.

## Skipping a test

If a playbook cannot run on a platform for an environmental reason (for
example a package that the distribution does not ship, or a role feature that
has not been implemented for that distribution yet), list it under `skip` in
the platform file together with a short reason and, if useful, a comment.
Skipped tests are reported as `SKIP` in the summary and do not fail the job.
Prefer fixing the playbook, the role or its platform detection over adding a
skip, and remove the skip once the underlying problem is solved.
