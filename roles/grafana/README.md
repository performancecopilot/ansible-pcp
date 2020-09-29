# performancecopilot.grafana

Installs and configures [Grafana](https://grafana.com) for use with the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of Grafana v6+.  All available PCP datasources will be installed from the [grafana-pcp](https://github.com/performancecopilot/grafana-pcp) package.

## Role Variables

None.

## Dependencies

None.

## Example Playbook

Setup PCP and Grafana for graphing live metrics locally using Vector.

```yaml
- hosts: monitoring
  roles:
    - role: community.performancecopilot.grafana
    - role: community.performancecopilot.pcp
      vars:
        pcp_rest_api: yes
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>