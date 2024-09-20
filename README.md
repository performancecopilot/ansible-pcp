# Ansible Collection - performancecopilot.metrics

![CI Testing](https://github.com/performancecopilot/ansible-pcp/workflows/tox/badge.svg)
[![Mailing List](https://img.shields.io/badge/Mailing%20List-pcp-blue.svg)](https://groups.io/g/pcp)
[![Slack Team](https://img.shields.io/badge/Slack-pcp-blue.svg)](https://h7zo83mvt1.execute-api.us-west-2.amazonaws.com/Express/)
[![IRC #pcp](https://img.shields.io/badge/IRC-pcp-blue.svg)](https://web.libera.chat/#pcp)
[![Github Release](https://img.shields.io/github/release/performancecopilot/ansible-pcp.svg)](https://github.com/performancecopilot/ansible-pcp/releases/latest)

A collection containing roles for Performance Co-Pilot (PCP)
and related software, such as Valkey/Redis and Grafana.

The collection is arranged as follows:

- performancecopilot.metrics.pcp

  A role for core PCP capabilities, configuring live performance
  analysis with a large base set of metrics from the kernel and
  system services, as well as data recording and rule inference.

- performancecopilot.metrics.grafana

  A role for configuring a local Grafana server, providing web
  frontend visuals for Performance Co-Pilot metrics, both live
  and historically.
  Data sources for Vector (live), Valkey/Redis (historical) and
  interactive bpftrace (eBPF) scripts can be configured by this
  role.  The PCP REST API service (from the core PCP role) must
  be configured in order to use this role.

- performancecopilot.metrics.keyserver

  A role for configuring a local key server (Valkey/Redis) that
  is suitable for use with a Performance Co-Pilot installation
  (for single or many hosts) with fast, scalable metric queries.

- performancecopilot.metrics.repository

  A role configuring an additional PCP packaging repository -
  for installation of the latest (upstream) releases of the PCP
  packages from the Performance Co-Pilot development community.

- performancecopilot.metrics.bpftrace

  A role that extends the core PCP role, providing metrics from
  bpftrace scripts (using the Linux kernel eBPF facilities).
  Configuring authentication of a local user capable of running
  bpftrace scripts via the PCP agent is a key task of this role.

- performancecopilot.metrics.elasticsearch

  A role that extends the core PCP role, providing metrics from
  a live ElasticSearch instance for PCP analysis - or exporting
  of PCP metric values (and meta-data) to ElasticSearch for the
  indexing and querying of performance data.

- performancecopilot.metrics.mssql

  A role that extends the core PCP role, providing metrics from
  a SQL Server database.  Configuring authentication of the PCP
  mssql metric agent is a key task of this role.

- performancecopilot.metrics.postfix

  A role that extends the core PCP role, providing metrics from
  a Postfix mail server.

- performancecopilot.metrics.spark

  A role that extends the core PCP role, exporting metrics from
  PCP into Apache Spark for further analysis.
