# performancecopilot.metrics.elasticsearch

Installs and configures [Elasticsearch](https://www.elastic.co/elasticsearch) metrics from the [Performance Co-Pilot](https://pcp.io/) toolkit, and optional exporting of PCP metrics to Elasticsearch.

## Requirements

Uses features of PCP v5.2.1 and later.

## Role Variables

### elasticsearch_agent: true

Collect metrics from the local Elasticsearch server.

### elasticsearch_agent_port: 9200

Connect on given socket port for Elasticsearch metric collection.

### elasticsearch_agent_authname: ''

Sets the HTTP request username for Elasticsearch metric collection.

### elasticsearch_agent_password: ''

Sets the HTTP request password for Elasticsearch metric collection.

### elasticsearch_export_metrics: false

Enable exporting of PCP metrics metadata and values to Elasticsearch.

### elasticsearch_export_interval: 60

Sets the sampling interval for exporting metric values to Elasticsearch, in seconds.

### elasticsearch_export_server: `http://localhost:9200`

Elasticsearch server URL for PCP metric metadata and value exporting.

### elasticsearch_export_index: pcp

Elasticsearch index to use for PCP metric names.

### elasticsearch_export_hostid: []

Specify the Elasticsearch host-id for measurements, default is the PCP metrics source hostname.

### elasticsearch_export_type: pcp-metric

Specify the Elasticsearch search type for measurements.

## Dependencies

None.

## Example Playbooks

Make local Elasticsearch metrics available to PCP analysis tools.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.elasticsearch
      vars:
        elasticsearch_agent_port: 9200
```

Setup export of PCP metrics to a remote Elasticsearch server.

```yaml
- hosts: monitoring
  roles:
    - role: performancecopilot.metrics.elasticsearch
      vars:
        elasticsearch_export_server: 'http://elastic.example.com:9200'
        elasticsearch_export_authname: metrics
        elasticsearch_export_password: 'xxxxxxx'
```

## License

MIT

## Author Information

An official role for PCP, maintained by the PCP developers <pcp@groups.io>
