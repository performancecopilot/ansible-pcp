# performancecopilot.metrics.bintray

Installs and configures the [bintray](https://bintray.com/pcp) package repositories to get the very latest [Performance Co-Pilot](https://pcp.io/) toolkit releases.

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
    - role: performancecopilot.metrics.bintray
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
