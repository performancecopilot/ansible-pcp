# performancecopilot.metrics.bpftrace

Installs and configures [bpftrace](https://github.com/iovisor/bpftrace) metrics from the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of PCP v5.1 and later, and makes use of Cyrus SASL (Simple Authentication Security Layer) SCRAM (Salted Challenge Response Authentication) for authentication.

## Role Variables

```yaml
bpftrace_metrics_provider: pcp
```

The metrics collector to use to provide metrics.

This can be either set to 'none' for local bpftrace package installation only.
The default value 'pcp' configures bpftrace for use with Performance Co-Pilot.

```yaml
bpftrace_users:
  - {user: metrics}
```

Local user accounts that are allowed to load new bpftrace scripts.  These accounts will be able to load eBPF code into the running kernel, which is a privileged operation.  The mandatory value for the variable is an array of dictionaries containing account names under the 'user' key.  Other authentication mechanisms can share these dictionaries, e.g. for remote [pmcd(1)](http://man7.org/linux/man-pages/man1/pmcd.1.html) authentication with PCP using SASL.

## Dependencies

None.

## Example Playbooks

Make bpftrace metrics available to PCP analysis tools, and allow the local *grafana* and *metrics* users to create new metrics from bpftrace scripts.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.bpftrace
      vars:
        bpftrace_users:
          - {user: 'grafana'}
          - {user: 'metrics', sasluser: 'metrics', saslpassword: 'p4ssw0rd'}
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
