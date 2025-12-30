# Grafana Dashboards and Alerts for OCPP Central System

This directory contains Grafana dashboards and alert rules for monitoring the OCPP Central System.

## Files

- `dashboards/ocpp-central-system.json` - Main dashboard with all monitoring panels
- `alerts/ocpp-alerts.json` - Alert rule definitions

## Dashboard Panels

The dashboard includes the following panels:

1. **Central Service Running** - Gauge showing if the service is up (1) or down (0)
2. **Central Service Resident Memory** - Time series of process memory usage
3. **Connected Charge Points** - Total count of connected charge points
4. **Active Transactions** - Total count of active transactions
5. **Connected Charge Points Over Time (by CP)** - Line chart showing connection status per charge point
6. **Active Transactions Over Time (by CP)** - Line chart showing active transactions per charge point
7. **Number of Boots Over Time (by CP)** - Bar chart showing boot count per charge point
8. **Number of Disconnects Over Time (by CP)** - Bar chart showing disconnect count per charge point
9. **Number of Errors Over Time (by CP)** - Bar chart showing error count per charge point
10. **Sum of Measured Current Delivered (by CP)** - Total current per charge point
11. **Time Since Last Heartbeat (by CP)** - Time elapsed since last heartbeat per charge point
12. **Time Since Last Transaction (by CP)** - Time elapsed since last transaction per charge point
13. **Total Reconnects During Transaction (by CP)** - Count of reconnects during active transactions
14. **Sum of Measured Current Delivered (Total System)** - Total current draw across all charge points

## Alert Rules

The following alerts are configured:

1. **Charge Point Multiple Reboots** - Alert when any CP has more than 1 reboot in a day
2. **Charge Point Multiple Disconnects** - Alert when any CP has more than 1 disconnection in a day
3. **Charge Point Error Detected** - Alert when any CP reports an error
4. **Charge Point Stale Heartbeat** - Alert when any CP's last heartbeat is over 1 day ago
5. **Charge Point Stale Transaction** - Alert when any CP's last transaction was over 2 weeks ago
6. **Charge Point Reboot During Transaction** - Alert when any CP reboots during an active transaction

## Installation

### Prerequisites

1. Grafana installed and running
2. Prometheus datasource configured in Grafana
3. OCPP Central System running with `--metrics-port` enabled

### Import Dashboard

1. Open Grafana in your browser
2. Go to **Dashboards** → **Import**
3. Click **Upload JSON file** and select `dashboards/ocpp-central-system.json`
4. Select your Prometheus datasource
5. Click **Import**

Alternatively, you can copy the JSON content and paste it into the import dialog.

### Import Alert Rules

For Grafana 8.0+ with unified alerting:

1. Go to **Alerting** → **Alert rules**
2. Click **New alert rule**
3. For each alert in `alerts/ocpp-alerts.json`:
   - Click **Import** or manually create the rule
   - Copy the query from the JSON file
   - Configure the condition and thresholds
   - Set up notification channels

Alternatively, you can use the Grafana API to import alert rules:

```bash
curl -X POST \
  http://admin:admin@localhost:3000/api/ruler/grafana/api/v1/rules/ocpp \
  -H 'Content-Type: application/json' \
  -d @alerts/ocpp-alerts.json
```

## Configuration

### Prometheus Data Source

Make sure your Prometheus datasource is configured in Grafana:

1. Go to **Configuration** → **Data sources**
2. Add Prometheus datasource if not already present
3. Set the URL to your Prometheus server (e.g., `http://localhost:9090`)
4. Save and test the connection

### Metrics Endpoint

Ensure the OCPP Central System is exposing metrics:

```bash
python -m levity.main --metrics-port 9091
```

The metrics will be available at `http://localhost:9091/metrics`

### Process Memory Metric

The process memory metric uses Prometheus's standard `process_resident_memory_bytes` metric, which is automatically provided by Prometheus's process exporter or the prometheus_client library's PROCESS_COLLECTOR. No additional configuration is needed.

## Customization

### Dashboard Variables

The dashboard uses a datasource variable `${DS_PROMETHEUS}`. Make sure your Prometheus datasource is named correctly or update the variable in the dashboard settings.

### Time Ranges

Default time range is set to "Last 6 hours". You can change this in the dashboard time picker or modify the default in the JSON file.

### Refresh Interval

The dashboard refreshes every 30 seconds by default. You can change this in the dashboard settings.

## Troubleshooting

### No Data Showing

1. Verify Prometheus is scraping the metrics endpoint
2. Check that the metrics endpoint is accessible: `curl http://localhost:9091/metrics`
3. Verify the datasource is correctly configured in Grafana
4. Check that charge points are connected and sending data

### Alerts Not Firing

1. Verify alert rules are properly imported
2. Check notification channels are configured
3. Verify the alert conditions match your data
4. Check Grafana alerting logs for errors

### Memory Metric Missing

1. Install psutil: `pip install psutil`
2. Or ensure you're running on Linux
3. The metric updates every 100 messages, so it may take time to appear

## Metrics Reference

All metrics are prefixed with `ocpp_` (except for standard Prometheus process metrics):

- `ocpp_central_up` - Service availability (1 = up, 0 = down)
- `process_resident_memory_bytes` - Process memory in bytes (standard Prometheus metric)
- `ocpp_cp_connected{cp_id}` - Connection status per CP
- `ocpp_tx_active{cp_id, connector_id}` - Active transaction status
- `ocpp_cp_boots_total{cp_id}` - Total boot count
- `ocpp_cp_disconnects_total{cp_id}` - Total disconnect count
- `ocpp_cp_errors_total{cp_id, error_type}` - Total error count
- `ocpp_cp_current_a{cp_id, connector_id}` - Measured current in Amperes
- `ocpp_cp_last_heartbeat_ts{cp_id}` - Last heartbeat timestamp
- `ocpp_cp_last_tx_ts{cp_id}` - Last transaction timestamp
- `ocpp_cp_reconnect_during_tx_total{cp_id}` - Reconnects during transactions

For a complete list, see the Prometheus metrics plugin documentation.

