# performancecopilot.metrics.grafana

Installs and configures [Grafana](https://grafana.com) for use with the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of Grafana v6+.  All available PCP datasources will be installed from the [grafana-pcp](https://github.com/performancecopilot/grafana-pcp) package.

## Role Variables

### grafana_pmproxy_url: http://localhost:44322

The outgoing pmproxy URL used by the provisioned PCP datasources. The default
uses the port of a known local role-managed push collector, or 44322 otherwise.
Set an explicit `http://` or `https://` hostname/IP and port when using a remote
query endpoint or a collector with a custom port. A trailing `/` is accepted;
other paths, credentials, queries and fragments are rejected. For example:

```yaml
grafana_pmproxy_url: http://localhost:44323
```

HTTPS uses the Grafana host's system trust. Install the appropriate CA trust
before using a private CA. This setting controls Grafana's outgoing datasource
connection; `grafana_cert` and `grafana_private_key` configure its web server.

The role checks the authentication policy when its datasource URL identifies
the host and port of a known local role-managed push collector. A mutual TLS
collector is rejected with an actionable error before Grafana configuration
is changed: the role does not configure datasource client certificates, and
the Grafana-PCP Valkey/Redis backend does not consume Grafana's standard client
TLS settings. Use a separate query endpoint or manage compatible datasources
separately. Remote endpoints with unknown policies are not assumed to require
client certificates.

## Dependencies

None.

## Example Playbook

Setup PCP and Grafana for graphing live metrics locally using Vector.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.grafana
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_rest_api: true
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
