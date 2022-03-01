# performancecopilot.metrics.postfix

Installs [Postfix](https://www.postfix.org/) metrics from the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

All versions of Postfix and PCP should function correctly with this role.  This role does *not* install or configure Postfix itself, rather it configures PCP to extract metrics from a running Postfix service.

## Role Variables

None.

## Dependencies

None.

## Example Playbooks

Setup PCP Postfix performance metrics.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.postfix
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
