# performancecopilot.bpftrace

Installs and configures [bpftrace](https://github.com/iovisor/bpftrace) metrics from the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of PCP v5.1 and later, and makes use of Cyrus SASL (Simple Authentication Security Layer) SCRAM (Salted Challenge Response Authentication) for authentication.

## Role Variables

```yaml
bpftrace_users:
- username: metrics
  password: admin
```

Local system accounts that are able to load new bpftrace scripts.  These accounts will be able to load eBPF code into the running kernel, which is a privileged operation.  The mandatory value for the variable is an array of username-to-password mappings.

## Dependencies

None.

## Example Playbooks

Make bpftrace metrics available to PCP analysis tools, and allow the local *grafana* and *metrics* users to create new metrics from bpftrace scripts.

```yaml
- hosts: monitoring
  roles:
    - role: community.performancecopilot.bpftrace
      vars:
        bpftrace_users:
        - username: metrics
          password: p4ssw0rd
        - username: grafana
          password: adm1n!
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
