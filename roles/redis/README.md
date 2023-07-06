# performancecopilot.metrics.redis

Installs and configures [Redis](https://redis.io) for use with the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of Redis v5+.  If the target platform provides it, the RediSearch module will also be installed.

## Role Variables

    redis_save_to_disk: true

Incrementally save the redis database to disk. Default: true.

## Dependencies

None.

## Example Playbook

Central PCP setup for monitoring of several remote hosts with fast, scalable querying enabled.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.redis
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_target_hosts: [slip, slop, slap]
        pcp_rest_api: true
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
