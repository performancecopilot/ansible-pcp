# performancecopilot.metrics.keyserver

Installs and configures either [Valkey](https://valkey.io) or [Redis](https://redis.io) for use with the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Requires a modern version of either Valkey or Redis (preferencing the open source Valkey on latest Linux distributions).  If the target platform provides it, the ValkeySearch (or RediSearch) module will also be installed.

## Role Variables

### keyserver_save_to_disk: true

Incrementally save the database to disk. Default: true.

## Dependencies

None.

## Example Playbook

Central PCP setup for monitoring of several remote hosts with fast, scalable querying enabled.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.keyserver
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_target_hosts: [slip, slop, slap]
        pcp_rest_api: true
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
