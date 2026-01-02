# Alert Setup Guide

This guide provides step-by-step instructions for setting up alerts manually in Grafana, as well as the PromQL queries for each alert.

## Manual Alert Setup

For each alert, follow these steps in Grafana:

1. Go to **Alerting** → **Alert rules**
2. Click **New alert rule**
3. Fill in the details below for each alert
4. Configure notification channels
5. Save the rule

## Alert Definitions

### 1. Charge Point Multiple Reboots

**Query:**
```promql
increase(ocpp_cp_boots_total[1d]) > 1
```

**Condition:** When query result is above threshold of 1

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: warning`
- `component: charge_point`

**Annotations:**
- Summary: `Multiple reboots detected for {{$labels.cp_id}}`
- Description: `Charge point {{$labels.cp_id}} has rebooted more than once in the last 24 hours ({{$value}} reboots).`

---

### 2. Charge Point Multiple Disconnects

**Query:**
```promql
increase(ocpp_cp_disconnects_total[1d]) > 1
```

**Condition:** When query result is above threshold of 1

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: warning`
- `component: charge_point`

**Annotations:**
- Summary: `Multiple disconnects detected for {{$labels.cp_id}}`
- Description: `Charge point {{$labels.cp_id}} has disconnected more than once in the last 24 hours ({{$value}} disconnects).`

---

### 3. Charge Point Error Detected

**Query:**
```promql
increase(ocpp_cp_errors_total[5m]) > 0
```

**Condition:** When query result is above threshold of 0

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: critical`
- `component: charge_point`

**Annotations:**
- Summary: `Error detected for {{$labels.cp_id}}: {{$labels.error_type}}`
- Description: `Charge point {{$labels.cp_id}} has reported an error: {{$labels.error_type}} ({{$value}} errors in last 5 minutes).`

---

### 4. Charge Point Stale Heartbeat

**Query:**
```promql
(time() - ocpp_cp_last_heartbeat_ts) > 86400
```

**Condition:** When query result is above threshold of 86400 (1 day in seconds)

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: warning`
- `component: charge_point`

**Annotations:**
- Summary: `Stale heartbeat for {{$labels.cp_id}}`
- Description: `Charge point {{$labels.cp_id}} last heartbeat was {{$value | humanizeDuration}} ago (more than 1 day).`

---

### 5. Charge Point Stale Transaction

**Query:**
```promql
(time() - ocpp_cp_last_tx_ts) > 1209600
```

**Condition:** When query result is above threshold of 1209600 (2 weeks in seconds)

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: info`
- `component: charge_point`

**Annotations:**
- Summary: `Stale transaction for {{$labels.cp_id}}`
- Description: `Charge point {{$labels.cp_id}} last transaction was {{$value | humanizeDuration}} ago (more than 2 weeks).`

---

### 6. Charge Point Reboot During Transaction

**Query:**
```promql
increase(ocpp_cp_reconnect_during_tx_total[5m]) > 0
```

**Condition:** When query result is above threshold of 0

**Evaluation:** Every 1 minute, for 0 seconds

**Labels:**
- `severity: critical`
- `component: charge_point`

**Annotations:**
- Summary: `Reboot during transaction for {{$labels.cp_id}}`
- Description: `Charge point {{$labels.cp_id}} has rebooted/reconnected during an active transaction ({{$value}} occurrences in last 5 minutes).`

---

## Notification Channels

Before alerts can fire, you need to configure notification channels:

1. Go to **Alerting** → **Notification channels** (or **Contact points** in Grafana 9+)
2. Add channels for:
   - Email
   - Slack
   - PagerDuty
   - Webhook
   - etc.

3. Assign notification channels to alert rules or create notification policies

## Testing Alerts

To test if alerts are working:

1. Temporarily lower thresholds (e.g., set reboot threshold to 0)
2. Or manually trigger conditions if possible
3. Check that alerts fire and notifications are sent
4. Restore original thresholds

## Troubleshooting

### Alerts Not Firing

1. Check that the Prometheus datasource is correctly configured
2. Verify the queries return data: Test queries in Grafana Explore
3. Check alert rule evaluation status in Grafana UI
4. Verify notification channels are configured and tested

### False Positives

1. Adjust thresholds if needed
2. Add `for` duration to require condition to be true for a period before alerting
3. Use alert grouping to reduce noise

### Missing Labels

If labels like `cp_id` are missing:
1. Verify charge points are connected and sending data
2. Check that metrics are being scraped by Prometheus
3. Verify metric labels in Prometheus: `curl http://localhost:9090/api/v1/query?query=ocpp_cp_connected`
