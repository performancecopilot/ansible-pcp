Role Name
=========

Installs and configures the [Performance Co-Pilot](https://pcp.io/) toolkit.

Requirements
------------

Uses features of PCP v5 and later.

Role Variables
--------------

    pcp_rest_api: true

Enable the PCP REST APIs and log discovery via the [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) service.
Default: false

    pcp_pmlogger_interval: 10

Default logging interval for [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) archives for logging groups that do not set an explicit sampling interval.

    pcp_archive_dir: /var/log/pcp/pmlogger

Default location for [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) archives, per-host directories containing daily performance metric archives will be created here when pmlogger is enabled.  When [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) is running with archive discovery enabled, it monitors this location.

    pcp_pmcd_localonly: 0

Enable remote host connections to the [pmcd(1)](http://man7.org/linux/man-pages/man1/pmcd.1.html) service.  This affects most PMAPI client tools accessing live data such as including *pmlogger*, *pmchart*, *pmrep*, *pmie*, *pcp-dstat*, and so on

    pcp_pmproxy_localonly: 0

Enable remote host connections to the [pmproxy(1)](http://man7.org/linux/man-pages/man1/pmproxy.1.html) service.  This affects client tools using the REST API such as [grafana-pcp](https://grafana-pcp.readthedocs.io/) and PMAPI client tools using the protocol proxying features of *pmproxy*.

    pcp_pmlogger_localonly: 1

Enable remote host connections to the [pmlogger(1)](http://man7.org/linux/man-pages/man1/pmlogger.1.html) service.  This affects the optional [pmlc(1)](http://man7.org/linux/man-pages/man1/pmlc.1.html) utility.

Dependencies
------------

None.

Example Playbooks
-----------------

Basic PCP setup with monitoring suited for a single host.

    - hosts: all
      roles:
        - role: performancecopilot.pcp
          vars:
            pcp_pmlogger_interval: 10

Central PCP setup for monitoring of several remote hosts.

    - hosts: monitoring
      roles:
        - role: performancecopilot.pcp
          vars:
            pcp_pmlogger_interval: 10
            pcp_target_hosts: [slip, slop, slap]
            pcp_rest_apis: true

License
-------

MIT

Author Information
------------------

Official role for PCP, maintained by the PCP developers <pcp@groups.io>
