# Fluentd Integration for Levity OCPP

This directory contains configuration and examples for integrating Levity with Fluentd for structured audit logging.

## Quick Start

### Option 1: Docker Compose (Recommended for Testing)

```bash
cd examples/fluentd
docker-compose up -d
```

This starts:
- Fluentd on port 24224 (configured to output to stdout)
- Elasticsearch on port 9200 (optional, for log storage)
- Kibana on port 5601 (optional, for log visualization)

### Option 2: Local Fluentd

```bash
# Install Fluentd
gem install fluentd

# Run with provided config
fluentd -c fluent.conf
```

## Running Levity with Fluentd

```bash
# Enable Fluentd logging
export FLUENTD_ENABLED=true
export FLUENTD_HOST=localhost
export FLUENTD_PORT=24224

# Run the server
python examples/server_with_fluentd.py
```

## Event Types

Levity sends the following event types to Fluentd:

### Boot Events (`ocpp.boot`)

```json
{
  "event_type": "boot_notification",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:00:00Z",
  "vendor": "TestVendor",
  "model": "TestModel",
  "serial_number": "SN-123",
  "firmware_version": "1.0.0",
  "status": "Accepted"
}
```

### Status Events (`ocpp.status`)

```json
{
  "event_type": "status_notification",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:05:00Z",
  "connector_id": 1,
  "status": "Preparing",
  "error_code": "NoError"
}
```

### Transaction Events (`ocpp.transaction.start`, `ocpp.transaction.stop`)

**Start**:
```json
{
  "event_type": "transaction_start",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:10:00Z",
  "connector_id": 1,
  "id_tag": "USER-123",
  "meter_start": 1000,
  "transaction_id": 42,
  "transaction_timestamp": "2024-01-15T10:10:00Z"
}
```

**Stop**:
```json
{
  "event_type": "transaction_stop",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T11:00:00Z",
  "transaction_id": 42,
  "meter_stop": 15000,
  "energy_delivered": 14000,
  "reason": "Local",
  "transaction_timestamp": "2024-01-15T11:00:00Z"
}
```

### Meter Value Events (`ocpp.meter`)

```json
{
  "event_type": "meter_values",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:30:00Z",
  "connector_id": 1,
  "transaction_id": 42,
  "samples_count": 3,
  "measurands": ["Energy.Active.Import.Register", "Voltage", "Current.Import"]
}
```

### Heartbeat Events (`ocpp.heartbeat`)

```json
{
  "event_type": "heartbeat",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:15:00Z"
}
```

### Authorization Events (`ocpp.authorize`)

```json
{
  "event_type": "authorize",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:09:00Z",
  "id_tag": "USER-123",
  "status": "Accepted"
}
```

### WebSocket Events (`ocpp.websocket`)

```json
{
  "event_type": "websocket_connect",
  "charge_point_id": "CP001",
  "timestamp": "2024-01-15T10:00:00Z",
  "remote_address": "192.168.1.100:54321"
}
```

## Fluentd Configuration Examples

### Output to Stdout (Development)

```
<match ocpp.**>
  @type stdout
</match>
```

### Output to File

```
<match ocpp.**>
  @type file
  path /var/log/ocpp/${tag}/%Y%m%d
  compress gzip
  <buffer tag,time>
    timekey 1d
    timekey_wait 10m
  </buffer>
  <format>
    @type json
  </format>
</match>
```

### Forward to Elasticsearch

```
<match ocpp.**>
  @type elasticsearch
  host elasticsearch.example.com
  port 9200
  index_name ocpp_events
  type_name _doc
  include_tag_key true
  tag_key @log_name
  <buffer>
    @type memory
    flush_interval 5s
  </buffer>
</match>
```

### Send to AWS CloudWatch

```
<match ocpp.**>
  @type cloudwatch_logs
  log_group_name /ocpp/audit
  log_stream_name ${tag}
  auto_create_stream true
  <buffer tag>
    @type memory
    flush_interval 5s
  </buffer>
</match>
```

### Send to AWS S3

```
<match ocpp.**>
  @type s3
  s3_bucket ocpp-audit-logs
  s3_region us-east-1
  path logs/${tag}/%Y/%m/%d/
  <buffer tag,time>
    @type file
    path /var/log/fluentd/s3
    timekey 3600
    timekey_wait 10m
    chunk_limit_size 256m
  </buffer>
  <format>
    @type json
  </format>
</match>
```

## Filtering and Routing

### Route Transactions to Billing System

```
<match ocpp.transaction.**>
  @type forward
  <server>
    host billing-system.example.com
    port 24225
  </server>
</match>
```

### Add Metadata to All Events

```
<filter ocpp.**>
  @type record_transformer
  <record>
    environment production
    region us-east-1
    facility_id 42
  </record>
</filter>
```

### Filter High-Value Transactions

```
<filter ocpp.transaction.stop>
  @type grep
  <regexp>
    key energy_delivered
    pattern /^[1-9][0-9]{4,}$/  # >= 10000 Wh
  </regexp>
</filter>
```

## Querying with Elasticsearch

If you're using Elasticsearch, you can query events:

```bash
# Get all transactions for a charge point
curl -X GET "localhost:9200/ocpp_events/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "bool": {
      "must": [
        { "term": { "charge_point_id": "CP001" } },
        { "term": { "event_type": "transaction_start" } }
      ]
    }
  },
  "sort": [{ "timestamp": "desc" }]
}
'

# Calculate total energy delivered
curl -X GET "localhost:9200/ocpp_events/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": { "event_type": "transaction_stop" }
  },
  "aggs": {
    "total_energy": {
      "sum": { "field": "energy_delivered" }
    }
  }
}
'
```

## Viewing Logs with Kibana

1. Open Kibana at http://localhost:5601
2. Go to Management → Stack Management → Index Patterns
3. Create index pattern: `ocpp_events*`
4. Set time field: `timestamp`
5. Go to Discover to view and search logs

## Production Considerations

1. **Security**: Use TLS for Fluentd connections in production
2. **Buffer Management**: Configure appropriate buffer sizes for high-volume deployments
3. **Retention**: Set up log rotation and retention policies
4. **Monitoring**: Monitor Fluentd health and buffer status
5. **High Availability**: Run multiple Fluentd instances behind a load balancer
6. **Privacy**: Consider filtering out sensitive data (ID tags, etc.) based on your requirements

## Troubleshooting

### Events Not Appearing

```bash
# Check Fluentd is running
docker-compose ps

# Check Fluentd logs
docker-compose logs -f fluentd

# Test connectivity
telnet localhost 24224
```

### Connection Refused

```bash
# Check firewall
sudo ufw status

# Verify Fluentd is listening
netstat -an | grep 24224
```

### Missing Events

- Check plugin initialization in Levity logs
- Verify `FLUENTD_ENABLED=true` environment variable
- Check Fluentd configuration file syntax
```

