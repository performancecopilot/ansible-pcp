# performancecopilot.spark

Installs and configures the [bintray](https://bintray.com/pcp) package repositories to get the very latest [Performance Co-Pilot](https://pcp.io/) toolkit releases.

## Requirements

On Debian/Ubuntu systems, the following packages are needed on the host that executes this module:

- python-apt (python 2)
- python3-apt (python 3)



## Role Variables

None.

## Dependencies

None.

## Example Playbooks

Ensure latest upstream PCP packages are available for installation.

```yaml
- hosts: monitoring
  roles:
    - role: community.performancecopilot.bintray
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
