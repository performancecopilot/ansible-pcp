#!/usr/bin/python
# SPDX-License-Identifier: MIT
"""Preserve pmproxy configuration while enabling or disabling archive push."""

import glob
import json
import os
import re
import tempfile
from urllib.parse import urlsplit

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: pcp_push
short_description: Edit existing PCP archive push configuration
description:
- Internal helper for preserving unrelated pmproxy settings and validating push URLs.
- The PCP role handles input validation, certificates, probes and service management.
options:
  action:
    type: str
    required: true
    choices: [validate, collector]
    description: Check configuration conflicts or apply configuration edits.
  client:
    type: dict
    default: {}
    description: Client URL settings, excluding passwords.
  collector:
    type: dict
    default: {}
    description: Collector configuration settings.
  discard:
    type: str
    default: '14'
    description: Pushed archive retention period.
  timers:
    type: path
    required: true
    description: Platform pmproxy maintenance environment file.
attributes:
  check_mode:
    support: full
author:
- PCP developers (@performancecopilot)
version_added: 2.5.0
"""
EXAMPLES = r"""
- name: Validate a push URL
  pcp_push:
    action: validate
    client:
      enabled: true
      collector_url: http://collector:44322
    timers: /etc/default/pmproxy_timers
"""
RETURN = r"""
changed:
  description: Whether configuration files changed.
  type: bool
  returned: always
"""

ROOT = "/etc/pcp"
BEGIN = "# BEGIN ansible-pcp push\n"
END = "# END ansible-pcp push\n"


def read(path):
    try:
        with open(path) as stream:
            return stream.read()
    except FileNotFoundError:
        return ""


def collector_url(value):
    if not isinstance(value, str) or re.search(r'[\s,\\;$`\'"<>|]', value):
        raise ValueError(
            "collector_url must contain one explicit http:// or https:// hostname/IP and optional port"
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
    ):
        raise ValueError(
            "collector_url requires http:// or https://; credentials, paths, queries and fragments are forbidden"
        )
    host = parsed.hostname
    if ":" in host:
        import ipaddress

        ipaddress.IPv6Address(host)
        host = "[" + host + "]"
    elif not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
        raise ValueError("collector_url contains an invalid hostname/IP")
    port = parsed.port if parsed.port is not None else 44322
    if not 1 <= port <= 65535 or parsed.netloc.endswith(":"):
        raise ValueError("collector_url port must be between 1 and 65535")
    return "{}://{}:{}".format(parsed.scheme, host, port)


def ini_value(text, section, key, value):
    """Replace one INI key, preserving all unrelated lines and comments."""
    lines = text.splitlines(True)
    current, positions, end = None, [], len(lines)
    start = None
    for i, line in enumerate(lines):
        header = re.match(r"^\s*\[([^]]+)\]", line)
        if header:
            if current == section:
                end = i
            current = header[1]
            if current == section:
                start = i
        elif current == section and re.match(r"^\s*" + re.escape(key) + r"\s*=", line):
            positions.append(i)
    if len(positions) > 1:
        raise ValueError(
            "Duplicate [{}] {} settings; consolidate them before configuring push".format(
                section, key
            )
        )
    old = lines[positions[0]] if positions else None
    if positions:
        lines[positions[0]] = value if value is not None else ""
    elif value is not None:
        if start is None:
            lines.append("\n[{}]\n".format(section))
            lines.append(value)
        else:
            lines.insert(end, value)
    return "".join(lines), old


def collector_plan(config, timers, discard):
    statepath = ROOT + "/pmproxy/ansible-push-state.json"
    state = json.loads(read(statepath) or "{}")
    enabled = config.get("enabled", False)
    changes = {}
    path = ROOT + "/pmproxy/pmproxy.conf"
    text = read(path)
    options_path = ROOT + "/pmproxy/pmproxy.options"
    previously_managed = bool(state) or BEGIN in read(options_path)
    keys = {}
    if enabled:
        keys["pmlogger.enabled"] = "true"
        keys.update(
            {
                "pmlogger.authenticate": str(config.get("auth") == "basic").lower(),
                "pmlogger.auth_host": "127.0.0.1",
                "pmlogger.cached": "false",
                "pmproxy.http.enabled": "true",
                "pmproxy.secure.enabled": "true",
            }
        )
    elif previously_managed:
        keys["pmlogger.enabled"] = "false"
    for compound in set(keys) | set(state.get("ini", {})):
        section, key = compound.split(".", 1)
        desired = (
            "{} = {}\n".format(key, keys[compound])
            if compound in keys
            else state["ini"][compound]
        )
        text, old = ini_value(text, section, key, desired)
        if enabled:
            state.setdefault("ini", {}).setdefault(compound, old)
    if os.path.exists(path) or text:
        changes[path] = text
    options = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END), "", read(options_path), flags=re.S
    )
    if enabled:
        overrides = ["/etc/default/pmproxy", "/etc/sysconfig/pmproxy", "/etc/pcp.conf"]
        overrides += glob.glob("/etc/systemd/system/pmproxy.service.d/*.conf")
        overrides += ["/etc/systemd/system/pmproxy.service"]
        overrides += glob.glob("/run/systemd/system/pmproxy.service.d/*.conf")
        for override in overrides:
            if override.endswith("/ansible-push.conf"):
                continue
            for number, line in enumerate(read(override).splitlines(), 1):
                if (
                    override == "/etc/pcp.conf"
                    and ROOT == "/etc/pcp"
                    and line.startswith("PCP_PMPROXYOPTIONS_PATH=")
                    and line.split("=", 1)[1].strip() != options_path
                ):
                    raise ValueError(
                        "{}:{} redirects pmproxy.options; restore {} before configuring push".format(
                            override, number, options_path
                        )
                    )
                if override == "/etc/pcp.conf" and re.fullmatch(
                    r'PCP_TLSCONF_PATH=["\']?/etc/pcp/tls.conf["\']?', line.strip()
                ):
                    continue
                if not line.lstrip().startswith("#") and "PCP_TLSCONF_PATH" in line:
                    raise ValueError(
                        "{}:{} overrides PCP_TLSCONF_PATH; remove this override before configuring push".format(
                            override, number
                        )
                    )
                if "/systemd/system/" in override and re.match(
                    r"^\s*(ExecStart|User|Group)\s*=", line
                ):
                    raise ValueError(
                        "{}:{} overrides pmproxy startup or service identity; remove this override before configuring push".format(
                            override, number
                        )
                    )
        for number, line in enumerate(options.splitlines(), 1):
            if (
                line.strip()
                and not line.lstrip().startswith("#")
                and re.search(
                    r"(^|\s)(-[pQctU]|--(port|certreqd|config|timeseries|username))|PCP_TLSCONF_PATH",
                    line,
                )
            ):
                raise ValueError(
                    "{}:{} conflicts with push; remove the port, certificate requirement, mode/config, user or TLS override".format(
                        options_path, number
                    )
                )
        for candidate in (ROOT + "/pmproxy/pmproxy.conf",):
            if re.search(
                r"^\s*(certificates|private_key|authority)\s*=", read(candidate), re.M
            ):
                raise ValueError(
                    "{} contains legacy TLS overrides; move TLS settings to caller-managed files before enabling push".format(
                        candidate
                    )
                )
        if options and not options.endswith("\n"):
            options += "\n"
        options += BEGIN + "-p {}\n".format(config.get("port", 44322))
        if config.get("auth") == "mtls":
            options += "--certreqd\n"
        options += END
    if os.path.exists(options_path) or options:
        changes[options_path] = options
    timertext = read(timers)
    timertext = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END), "", timertext, flags=re.S
    )
    if enabled:
        if not re.fullmatch(r"(\d+(:\d+){0,2}|never|forever)", discard):
            raise ValueError(
                "pcp_pmlogger_discard must be DD[:HH[:MM]], never or forever"
            )
        if "timer_original" not in state:
            match = re.search(r"^PMLOGGER_DAILY_PARAMS=.*\n?", timertext, re.M)
            state["timer_original"] = match[0] if match else ""
        timertext = re.sub(r"^PMLOGGER_DAILY_PARAMS=.*\n?", "", timertext, flags=re.M)
        timertext += (
            BEGIN + 'PMLOGGER_DAILY_PARAMS="-E --discard {}"\n'.format(discard) + END
        )
    elif state.get("timer_original"):
        timertext += state["timer_original"]
    if os.path.exists(timers) or timertext:
        changes[timers] = timertext
    changes[statepath] = json.dumps(state, sort_keys=True) + "\n" if enabled else None
    return changes


def main():
    module = AnsibleModule(
        argument_spec=dict(
            action=dict(type="str", required=True, choices=["validate", "collector"]),
            client=dict(type="dict", default={}),
            collector=dict(type="dict", default={}),
            discard=dict(type="str", default="14"),
            timers=dict(type="path", required=True),
        ),
        supports_check_mode=True,
    )
    p = module.params
    try:
        changes = {}
        if p["client"].get("enabled"):
            collector_url(p["client"].get("collector_url"))
        if p["action"] == "collector" or (
            p["action"] == "validate" and p["collector"].get("enabled")
        ):
            changes.update(collector_plan(p["collector"], p["timers"], p["discard"]))
        if p["action"] == "validate":
            module.exit_json(changed=False)
        changed = False
        for path, content in changes.items():
            if (content is None and not os.path.exists(path)) or (
                content is not None and os.path.exists(path) and read(path) == content
            ):
                continue
            changed = True
            if module.check_mode:
                continue
            if content is None:
                os.unlink(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path))
            try:
                with os.fdopen(fd, "w") as stream:
                    stream.write(content)
                os.chmod(temporary, 0o644)
                module.atomic_move(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        module.exit_json(changed=changed)
    except (ValueError, OSError, KeyError, StopIteration) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
