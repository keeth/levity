# Prometheus Metrics for Levity OCPP

This directory contains configuration and examples for integrating Levity with Prometheus for monitoring and alerting.

## Quick Start

### 1. Run Levity with Prometheus Plugin

```bash
# Set environment variables
export METRICS_PORT=9090

# Run the example server
python examples/server_with_prometheus.py
```

This starts:
- OCPP WebSocket server on port 9000
- Prometheus metrics HTTP server on port 9090

### 2. Access Metrics Endpoint

```bash
# View raw metrics
curl http://localhost:9090/metrics
```

## Available Metrics

### Service-Level Metrics

**`ocpp_central_up`** (Gauge)
- Value: `1` if OCPP Central System is running, `0` otherwise
- Used for: Uptime monitoring

**`ocpp_msg_handling_seconds`** (Histogram)
- Labels: `cp_id`, `message_type`
- Measures: Time to process OCPP messages
- Used for: Performance monitoring, SLA tracking

### Per-Charge-Point Connection & Status

**`ocpp_cp_connected{cp_id}`** (Gauge)
- Value: `1` if WebSocket connected, `0` otherwise
- Used for: Connection monitoring, alerting on disconnections

**`ocpp_cp_last_heartbeat_ts{cp_id}`** (Gauge)
- Value: Unix timestamp of last heartbeat
- Used for: Detecting stale connections (current_time - value > threshold)

**`ocpp_cp_last_msg_ts{cp_id}`** (Gauge)
- Value: Unix timestamp of last message received
- Used for: Activity monitoring

**`ocpp_cp_last_tx_ts{cp_id}`** (Gauge)
- Value: Unix timestamp of last transaction stop
- Used for: Transaction activity tracking

**`ocpp_cp_status{cp_id}`** (Gauge)
- Value: Numeric status code (0=Available, 1=Preparing, 2=Charging, etc.)
- Used for: Charge point state monitoring

**`ocpp_cp_disconnects_total{cp_id}`** (Counter)
- Value: Total number of disconnections
- Used for: Connection stability analysis

### Errors & Boots

**`ocpp_cp_errors_total{cp_id, error_type}`** (Counter)
- Labels: `cp_id`, `error_type` (e.g., "GroundFailure", "OverVoltage")
- Used for: Error monitoring, fault detection

**`ocpp_cp_boots_total{cp_id}`** (Counter)
- Value: Total number of boot notifications
- Used for: Tracking restarts, firmware updates

### Transaction Metrics

**`ocpp_tx_active{cp_id, connector_id}`** (Gauge)
- Value: `1` if transaction active on connector, `0` otherwise
- Used for: Active session monitoring

**`ocpp_tx_energy_wh{cp_id, connector_id}`** (Gauge)
- Value: Energy delivered in current transaction (Wh)
- Used for: Real-time energy monitoring

**`ocpp_tx_total{cp_id}`** (Counter)
- Value: Total transaction count
- Used for: Usage statistics, billing

**`ocpp_cp_energy_total_wh{cp_id}`** (Counter)
- Value: Cumulative energy delivered (Wh)
- Used for: Total energy tracking, revenue calculation

### Current Measurements

**`ocpp_cp_current_a{cp_id, connector_id}`** (Gauge)
- Value: Instantaneous measured current (Amperes)
- Used for: Load monitoring, safety alerts

**`ocpp_cp_current_limit_a{cp_id, connector_id}`** (Gauge)
- Value: Configured current limit (Amperes)
- Used for: Capacity planning, load balancing

## Prometheus Configuration

Create a `prometheus.yml` file:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'levity-ocpp'
    static_configs:
      - targets: ['localhost:9090']
        labels:
          instance: 'central-system-1'
```

Run Prometheus:

```bash
docker run -d \
  --name prometheus \
  -p 9091:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

Access Prometheus UI at http://localhost:9091

## Example Queries

### Connection Monitoring

```promql
# Number of connected charge points
sum(ocpp_cp_connected)

# Charge points that haven't sent heartbeat in 5 minutes
time() - ocpp_cp_last_heartbeat_ts{} > 300

# Connection success rate (last hour)
rate(ocpp_cp_disconnects_total[1h])
```

### Transaction Analytics

```promql
# Active charging sessions
sum(ocpp_tx_active)

# Total energy delivered today (Wh)
increase(ocpp_cp_energy_total_wh[24h])

# Transaction rate (transactions per minute)
rate(ocpp_tx_total[5m]) * 60

# Current energy being delivered
sum(ocpp_tx_energy_wh)
```

### Performance Monitoring

```promql
# Average message handling time
rate(ocpp_msg_handling_seconds_sum[5m]) / rate(ocpp_msg_handling_seconds_count[5m])

# 95th percentile message latency
histogram_quantile(0.95, rate(ocpp_msg_handling_seconds_bucket[5m]))

# Message processing rate by type
rate(ocpp_msg_handling_seconds_count[5m]) by (message_type)
```

### Error Tracking

```promql
# Error rate (errors per minute)
rate(ocpp_cp_errors_total[5m]) * 60

# Error breakdown by type
sum(rate(ocpp_cp_errors_total[1h])) by (error_type)

# Charge points with recent errors
ocpp_cp_errors_total > 0
```

### Load Monitoring

```promql
# Total current draw across all connectors
sum(ocpp_cp_current_a)

# Charge points near current limit (>90%)
ocpp_cp_current_a / ocpp_cp_current_limit_a > 0.9

# Average power consumption (approximation: 240V * current)
sum(ocpp_cp_current_a) * 240
```

## Example Alerts

Create an `alerts.yml` file:

```yaml
groups:
  - name: ocpp_alerts
    interval: 30s
    rules:
      # Connection alerts
      - alert: ChargePointDisconnected
        expr: ocpp_cp_connected == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Charge point {{ $labels.cp_id }} disconnected"
          description: "Charge point has been disconnected for 5 minutes"

      - alert: ChargePointStaleHeartbeat
        expr: time() - ocpp_cp_last_heartbeat_ts > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Charge point {{ $labels.cp_id }} heartbeat stale"
          description: "No heartbeat received for 5+ minutes"

      # Error alerts
      - alert: HighErrorRate
        expr: rate(ocpp_cp_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on {{ $labels.cp_id }}"
          description: "Error rate exceeds 0.1 errors/second"

      # Performance alerts
      - alert: SlowMessageHandling
        expr: histogram_quantile(0.95, rate(ocpp_msg_handling_seconds_bucket[5m])) > 1.0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow message processing"
          description: "95th percentile latency exceeds 1 second"

      # Safety alerts
      - alert: NearCurrentLimit
        expr: ocpp_cp_current_a / ocpp_cp_current_limit_a > 0.95
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Connector {{ $labels.connector_id }} on {{ $labels.cp_id }} near current limit"
          description: "Current draw is >95% of limit"
```

## Grafana Dashboard

### Import Dashboard

1. Open Grafana at http://localhost:3000
2. Go to Dashboards → Import
3. Use the JSON file in this directory or create panels using the queries above

### Key Panels

**Overview Row**:
- Total charge points (connected vs total)
- Active charging sessions
- Energy delivered today
- Total transactions

**Connection Health**:
- Connection status timeline
- Heartbeat freshness
- Disconnect rate
- Boot frequency

**Transaction Activity**:
- Active sessions by charge point
- Energy delivery rate
- Transaction rate
- Average session duration

**Performance**:
- Message handling latency (histogram)
- Processing rate by message type
- Error rate

**Power & Current**:
- Total power consumption
- Current draw by connector
- Load distribution

## Using Prometheus Plugin Programmatically

```python
from levity.database import Database
from levity.plugins import PrometheusMetricsPlugin
from levity.server import OCPPServer

def create_plugins():
    return [
        PrometheusMetricsPlugin(),
        # ... other plugins
    ]

# Create server with metrics
db = Database("levity.db")
server = OCPPServer(
    db=db,
    host="0.0.0.0",
    port=9000,
    plugin_factory=create_plugins,
    metrics_port=9090,  # Enable /metrics endpoint
)

await server.start()
```

## Production Considerations

1. **Security**: Use authentication for the metrics endpoint in production
2. **High Cardinality**: Be cautious with labels - avoid high-cardinality values like transaction IDs
3. **Retention**: Configure appropriate data retention in Prometheus
4. **Resource Usage**: Monitor Prometheus memory usage with many charge points
5. **Federation**: Use Prometheus federation for multi-region deployments
6. **Backup**: Regularly backup Prometheus data for historical analysis

## Troubleshooting

### Metrics Not Appearing

```bash
# Check if metrics endpoint is responding
curl http://localhost:9090/metrics

# Verify plugin is enabled
# Should see PrometheusMetricsPlugin in server logs

# Check Prometheus is scraping successfully
# Look for "UP" status in Prometheus targets page
```

### Missing Data Points

- Ensure charge points are connected and sending messages
- Check that transactions are actually starting/stopping
- Verify meter values include the expected measurands

### High Memory Usage

- Reduce metric cardinality (fewer unique label combinations)
- Decrease Prometheus scrape interval
- Enable metric relabeling to drop unnecessary labels
- Configure shorter retention period
