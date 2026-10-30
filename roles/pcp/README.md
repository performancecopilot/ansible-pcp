# performancecopilot.metrics.pcp

Installs and configures the [Performance Co-Pilot](https://pcp.io/) toolkit.

## Requirements

Uses features of PCP v5 and later.

## Role Variables

### pcp_rest_api: true

Enable the PCP REST APIs and log discovery via the [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) service.  Default: false.

### pcp_pmlogger_interval: 60

Default logging interval for [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) archives for logging groups that do not set an explicit sampling interval.

### pcp_pmlogger_discard: 14

After some period, old PCP archives are discarded.  This period is 14 days by default, but may be changed using this variable.  Some special values are recognized for the period, namely '0' to keep no archives beyond the current one, and 'forever' or never to prevent any archives being discarded.  Note that the semantics of discard are that it is measured from the time of last modification of each archive, and not from the current day.

### pcp_archive_dir: /var/log/pcp/pmlogger

Default location for [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) archives, per-host directories containing daily performance metric archives will be created here when pmlogger is enabled.  When [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) is running with archive discovery enabled, it monitors this location.

### pcp_target_hosts: []

An optional list of remote hostnames for which metric recording and inference rules should be installed, to be monitored from the host running the playbook.  By default, all performance rules evaluating to true will be logged to the local system log (for both the local host and remote hosts in the target hosts list), and daily archives will be created below *pcp_archive_dir*/*hostname* locally, again for each host listed in the target hosts list.

### pcp_pmie_endpoint: ''

Send inference events to the given webhook endpoint (URL) from [pmie(1)](http://man7.org/linux/man-pages/man1/pmie.1.html) performance rules.  The default is to log these events into the local system log only.

### pcp_single_control: 0

Specifies whether the pcp_target_hosts configuration file(s) for pmie and pmlogger are in control.d form (the default) or in the single file form where /*etc*/*pcp*/*pmlogger*/*control* and /*etc*/*pcp*/*pmie*/*control* are used to setup the target hosts list for monitoring.

### pcp_pmcd_localonly: 0

Enable remote host connections to the [pmcd(1)](http://man7.org/linux/man-pages/man1/pmcd.1.html) service.  This affects most PMAPI client tools accessing live data such as including *pmlogger*, *pmchart*, *pmrep*, *pmie*, *pcp-dstat*, and so on

### pcp_pmproxy_localonly: 0

Enable remote host connections to the [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) service.  This affects client tools using the REST API such as [grafana-pcp](https://grafana-pcp.readthedocs.io/) and PMAPI client tools using the protocol proxying features of *pmproxy*.

### pcp_pmlogger_localonly: 1

Enable remote host connections to the [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) service.  This affects the optional [pmlc(1)](http://man7.org/linux/man-pages/man1/pmlc.1.html) utility.

### pcp_optional_agents: []

Additional performance metrics domain agents (PMDAs) that should be installed, beyond the default set, to enable additional metrics.  The array provided should contain shortened names for each PMDA to be enabled, such as "kvm".

### pcp_optional_packages: []

Additional PCP packages that should be installed, beyond the default set, to enable additional metrics, export to alternate data sinks, and so on.

```yaml
pcp_explicit_labels:
 environment: production

pcp_implicit_labels:
  deployment: 2020-08-17
  commitid: efbd2a331
```

Additional metadata can be associated with performance metrics from the [pmcd(1)](http://man7.org/linux/man-pages/man1/pmcd.1.html) service.  These are typically name=value pairs.  Explicit labels will be used in calculating time series identifiers seen by the [pmseries(1)](http://man7.org/linux/man-pages/man1/pmseries.1.html) command and [grafana-pcp](https://grafana-pcp.readthedocs.io/en/latest/index.html), and implicit labels will not.

```yaml
pcp_accounts:
  - {user: metrics, sasluser: metrics, saslpassword: p4ssw0rd}
  - {sasluser: nathans, saslpassword: "adm1n!"}
```

Configures access to system resources for accounts used by PCP.  The *user* setting configures a local user (system) account.  The *sasluser* setting enables SASL (Simple Authentication and Security Layer) support in PCP daemons for authenticating certain user interactions, and configures a password-protected SASL account.  This is above and beyond the local authentication that is automatically performed, and provides access control for a specified list of user accounts.  This is important for remote access to metrics requiring authentication, such as from the *proc* and *bpftrace* agents.

## Dependencies

None.

## Example Playbooks

Basic PCP setup with monitoring suited for a single host.

```yaml
- hosts: all
  roles:
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_pmlogger_interval: 10
        # NOTE: No openmetrics on EL7
        pcp_optional_agents: [dm, nfsclient, openmetrics]
        pcp_explicit_labels:
          environment: production
```

Central PCP setup for monitoring of several remote hosts.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_pmlogger_interval: 10
        pcp_pmlogger_discard: 5
        pcp_target_hosts: [slip, slop, slap]
        pcp_rest_api: true
```

## Push archives to a collector (PCP 7.2.2 or newer)

A host can be both a client and a collector. Configure both dictionaries in the
same role invocation and point `pcp_push_client.collector_url` at that host's
collector listener. For HTTPS, the URL hostname must match the certificate.
The role applies collector changes before probing and starting the local push
client; existing local logging continues alongside push.

Deploy the collector first, then clients. Each client pushes its local metrics to
exactly one collector. Use distinct client hostnames: the collector stores
archives by source hostname under PCP's `PCP_REMOTE_ARCHIVE_DIR` (normally
`/var/log/pcp/pmproxy`). Local archives already on clients remain untouched.
Push adds a non-primary logger alongside the client's existing local logging.
Local archives continue to be recorded and retained normally. The role manages
a dedicated `pcp-push.service`, leaving existing primary,
custom local and remote-target entries in place. This runs an additional logger
process and collects a separate stream of samples for the collector. The push
service starts on boot and restarts after failures; its diagnostics are available
with `journalctl -u pcp-push.service`.

`pcp_push_client` and `pcp_push_collector` default to `{}`. Empty dictionaries
leave push configuration untouched. Set `enabled: false` explicitly to remove
role-managed push settings. Removing variables from inventory does not disable a
previously configured deployment. Keep the enabled configuration in inventory
for ongoing management.

| Dictionary | Field | Default / requirement |
| --- | --- | --- |
| Both | `enabled` | `false` |
| Both | `auth` | `none`; one of `none`, `basic`, `mtls` |
| Client | `collector_url` | Required when enabled; `http://host[:port]` or `https://host[:port]` |
| Client | `ca_cert` | Required for HTTPS; existing PEM CA bundle on the client |
| Client | `cert`, `private_key` | Required together for `mtls` |
| Client | `username`, `password` | Required for `basic`; use Ansible Vault for the password |
| Collector | `port` | `44322` |
| Collector | `cert`, `private_key` | Together enable TLS; required for `basic` and `mtls` |
| Collector | `ca_cert` | Required for `mtls`; trusted client CA bundle |

A URL without a port uses 44322. Bracket IPv6 addresses, for example
`https://[2001:db8::1]:44322`. Embedded credentials, multiple destinations,
non-root paths, query strings and fragments are rejected. Authentication
requires HTTPS. HTTPS clients verify CA trust, certificate dates and the
collector's hostname; there is no HTTP fallback.

Prepare certificates before applying this role, using your certificate role or
other existing provisioning. As with the Grafana certificate integration, this
role neither issues nor copies certificates and adds no certificate-role
dependency. Files must exist on each managed host and be readable by the `pcp`
service account, including access through parent directories. Grant a group or
ACL read permission on private keys; the role does not change caller-managed
key ownership. Certificates must be current and match their unencrypted private
keys. The collector certificate needs a subject alternative name matching the
hostname or IP in client URLs; mutual TLS client certificates need client
certificate usage. Use separate client certificates when identities need to be
revoked independently.

### Plaintext

Use plaintext only on a trusted network. Run these plays in order:

```yaml
- hosts: collectors
  roles:
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_push_collector:
          enabled: true
        pcp_pmlogger_discard: 14

- hosts: clients
  roles:
    - role: performancecopilot.metrics.pcp
      vars:
        pcp_push_client:
          enabled: true
          collector_url: http://collector.example.com:44322
```

### Verified HTTPS

Set these dictionaries on the corresponding hosts:

```yaml
# Collector
pcp_push_collector:
  enabled: true
  cert: /etc/pki/pcp/collector.crt
  private_key: /etc/pki/pcp/collector.key

# Each client
pcp_push_client:
  enabled: true
  collector_url: https://collector.example.com:44322
  ca_cert: /etc/pki/pcp/ca.crt
```

Configuring HTTPS alone leaves pmproxy capable of receiving plaintext on its
listener. Set `auth: basic` to require credentials for push endpoints or
`auth: mtls` to require client certificates across HTTP endpoints. Basic
credentials are only transmitted by clients over verified HTTPS.

### Basic authentication over HTTPS

Add `auth: basic` to both HTTPS dictionaries. Add a client `username` and
Vault-backed `password`, and provision the same SASL account on the collector:

```yaml
# Collector
pcp_accounts:
  - user: archive_push
    sasluser: archive_push
    saslpassword: "{{ vault_archive_push_password }}"

# Add to each client's pcp_push_client dictionary
# auth: basic
# username: archive_push
# password: "{{ vault_archive_push_password }}"
```

The collector validates Basic credentials using its local pmcd SASL service.
Keep pmcd running and its authentication mechanism packages installed. Distinct
client accounts can be listed in `pcp_accounts`. Passwords are passed through
standard input for SASL provisioning and stored in a root-owned, `pcp`-readable
0640 client password file; they are never placed in push URLs or arguments.
`pcp_secure_logging: true` suppresses authentication task output. Validation and
probe errors are reported separately without credentials.

SASL provisioning creates missing accounts; it does not rotate passwords for
existing accounts. Changing `saslpassword` alone does not update an existing
collector account. Coordinate password changes in the collector's SASL database
with the client password configuration.

The shared account provisioning also uses safe password input and suppresses
sensitive output when push is not configured. Newly created accounts or installed
authentication packages can trigger a pmcd restart. These authentication fixes
are shared with existing `pcp_accounts` users.

### Mutual TLS

Add `auth: mtls` and `ca_cert` to the HTTPS collector dictionary. On each client,
add `auth: mtls`, `cert` and `private_key` to its HTTPS dictionary. Do not supply
Basic credentials. The collector uses certificate verification and `--certreqd`;
this rejects plaintext HTTP and requires a trusted certificate across pmproxy's
HTTP endpoints, including REST/Grafana consumers. If those consumers are in use,
prepare their client certificates before enabling this policy. Push Basic
authentication and HTTP certificate enforcement are separate PCP mechanisms;
this role configures one authentication policy per collector.

The Grafana role uses a known local collector's port by default and accepts
`grafana_pmproxy_url` for a different query endpoint. Its managed datasources
do not support client-certificate configuration; the Grafana role rejects
connections to a known local mutual TLS collector. Choose a compatible query
endpoint before enabling that collector policy. See the
[Grafana role](../grafana/README.md) for the datasource configuration boundary.

Push enables pmproxy independently of `pcp_rest_api`, retaining query/key-server
configuration. Dedicated `PCP_TLSCONF_PATH` settings leave shared pmcd TLS
configuration unchanged. Existing conflicting pmproxy command-line or TLS
overrides must be removed from the files named in validation errors. The role
keeps persistent archive storage enabled, sets pushed retention from
`pcp_pmlogger_discard`, and enables packaged `pmproxy_check.timer` and
`pmproxy_daily.timer`, retaining the maintenance `-E` default.

### Disable and troubleshoot

Set `pcp_push_client: {enabled: false}` to stop the managed push logger and remove
its systemd unit and password/TLS files. Local logging continues. Set
`pcp_push_collector: {enabled: false}` to disable push reception and remove
role-managed push authentication/TLS configuration. Independently requested
pmproxy REST functionality, unrelated configuration and stored archives remain.

Clients probe `/logger/ping` using curl before starting the push logger,
with three attempts and five-second timeouts. The role installs curl for
runtime probes and passes authentication headers through standard input.
Typical errors and remedies:

- **Detected PCP … requires PCP >= 7.2.2:** upgrade the managed host's PCP
  packages from its distribution or the upstream PCP repository.
- **Certificate verification / hostname failure:** install the correct CA
  bundle, renew expired certificates, and use a URL matching the collector SAN.
- **Rejected authentication (401/403):** check the SASL username/password or
  client certificate trust and usage.
- **Authentication service unavailable (503):** check collector pmcd and SASL
  configuration; this differs from rejected credentials when PCP reports it.
- **Connection refused / timeout:** deploy and start the collector first and
  allow its port through network firewalls.
- **Unreadable file / mismatched key:** grant `pcp` read access or supply the
  matching certificate/key pair; existing logging is retained on validation
  failure.

Check mode and offline image builds skip runtime probes and explicitly report
that runtime collector compatibility remains unverified. They cannot establish
that a collector is reachable or accepting the selected authentication policy.
Certificate validity uses the managed host's current clock and does not require
the caller to gather a `date_time` fact.

See PCP's [scaling guide](https://pcp.readthedocs.io/en/latest/HowTos/scaling/index.html)
and [TLS guide](https://pcp.readthedocs.io/en/latest/QG/EncryptedConnections.html)
for the underlying service behavior.

## License

MIT

## Author Information

Official role for PCP, maintained by the PCP developers <pcp@groups.io>
