# Ansible Collection - community.performancecopilot

A collection containing roles for Performance Co-Pilot (PCP)
and related software, such as Redis and Grafana.

The collection is arranged as follows:

- community.performancecopilot.pcp
  A role for core PCP capabilities, configuring live performance
  analysis with a large base set of metrics from the kernel and
  system services, as well as data recording and rule inference.

- community.performancecopilot.redis
  A role for configuring a local Redis server, suitable for use
  with a Performance Co-Pilot archive repository (for single or
  many hosts) and fast, scalable querying of metrics.

- community.performancecopilot.grafana
  A role for configuring a local Grafana server, providing web
  frontend visuals for Performance Co-Pilot metrics, both live
  and historically.
  Data sources for Vector (live), Redis (historical) as well as
  interactive bpftrace (eBPF) scripts can be configured by this
  role.  The PCP REST API service (from the core PCP role) must
  be configured in order to use this role.

- community.performancecopilot.bintray
  A role configuring an additional PCP packaging repository -
  bintray.com/pcp - for installation of the latest releases of
  PCP from the community.

- community.performancecopilot.bpftrace
  A role that extends the core PCP role, providing metrics from
  bftrace scripts (using the Linux kernel eBPF facilities).
  Configuring authentication of a local user capable of running
  bpftrace scripts via the PCP agent is a key task of this role.

- community.performancecopilot.elasticsearch
  A role that extends the core PCP role, providing metrics from
  a live ElasticSearch instance for PCP analysis - or exporting
  of PCP metric values (and meta-data) to ElasticSearch for the
  indexing and querying of performance data.

- community.performancecopilot.mssql
  A role that extends the core PCP role, providing metrics from
  a SQL Server database.  Configuring authentication of the PCP
  mssql metric agent is a key task of this role.

- community.performancecopilot.spark
  A role that extends the core PCP role, exporting metrics from
  PCP into Apache Spark for further analysis.
