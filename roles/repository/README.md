# performancecopilot.metrics.repository

Installs and configures the upstream package repositories - currently hosted at [Packagecloud](https://packagecloud.io/performancecopilot/pcp) - to get the very latest [Performance Co-Pilot](https://pcp.io/) toolkit releases.

## Requirements

None.

## Role Variables

None.

## Dependencies

None.

## Example Playbooks

Ensure latest upstream PCP packages are available for installation.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.repository
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
