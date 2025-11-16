## 1. Metrics endpoint

Expose Prometheus metrics on `/metrics`

## 2. Service-level metrics

**Gauges**

- `ocpp_central_up`

**Histogram**

- `ocpp_msg_handling_seconds`  
  Wrap each OCPP message handler.

---

## 3. Per-CP connection & status

**Gauges**

- `ocpp_cp_connected{cp_id}`  
  `1` if WebSocket open, else `0`
- `ocpp_cp_last_heartbeat_ts{cp_id}`  
  Unix timestamp
- `ocpp_cp_last_msg_ts{cp_id}`  
  Unix timestamp
- `ocpp_cp_last_tx_ts{cp_id}`  
  Unix timestamp
- `ocpp_cp_status{cp_id}`  
  Numeric status code

**Counters**

- `ocpp_cp_disconnects_total{cp_id}`

**Update points**

- On connect:
  - `ocpp_cp_connected{cp_id} = 1`
  - `ocpp_cp_last_msg_ts{cp_id} = now`
- On disconnect:
  - `ocpp_cp_connected{cp_id} = 0`
  - `ocpp_cp_disconnects_total{cp_id}++`
- On any message:
  - `ocpp_cp_last_msg_ts{cp_id} = now`
- On Heartbeat:
  - `ocpp_cp_last_heartbeat_ts{cp_id} = now`
- On StatusNotification:
  - `ocpp_cp_status{cp_id} = numeric_status`
- On TransactionStop:
  - `ocpp_cp_last_tx_ts{cp_id} = now`

---

## 4. Errors & boots

**Counters**

- `ocpp_cp_errors_total{cp_id, error_type}`
- `ocpp_cp_boots_total{cp_id}` (BootNotification count)

Update on error and on BootNotification.

---

## 5. Tx, energy (Wh), and current (A)

### 5.1 Instantaneous / per-tx values (Gauges)

**Gauges**

- `ocpp_tx_active{cp_id, connector_id}`  
  `1` if a tx is active on this connector, else `0`
- `ocpp_tx_energy_wh{cp_id, connector_id}`  
  Energy delivered so far in the *current* tx (Wh)
- `ocpp_cp_current_a{cp_id, connector_id}`  
  Instantaneous measured current (A)
- `ocpp_cp_current_limit_a{cp_id, connector_id}` (optional)  
  Configured current limit / setpoint (A)

**Update points**

- On StartTransaction:
  - `ocpp_tx_active{cp, conn} = 1`
  - `ocpp_tx_energy_wh{cp, conn} = 0` (or starting value)
- On MeterValues:
  - `ocpp_tx_energy_wh{cp, conn} = current_tx_energy_wh`
  - `ocpp_cp_current_a{cp, conn} = measured_current_a`
- On StopTransaction:
  - `ocpp_tx_active{cp, conn} = 0`
  - `ocpp_tx_energy_wh{cp, conn} = 0` (reset after use)

### 5.2 Cumulative counts (Counters)

**Counters**

- `ocpp_tx_total{cp_id}`  
  Total tx count per cp
- `ocpp_cp_energy_total_wh{cp_id}`  
  Cumulative energy delivered by this cp (Wh)

**Update points**

- On StartTransaction:
  - `ocpp_tx_total{cp}++`
- On StopTransaction (with final `tx_energy_wh`):
  - `ocpp_cp_energy_total_wh{cp} += tx_energy_wh`

---

## 6. Handler latency wrapping

Wrap your OCPP message handling with the histogram:

```python
with ocpp_msg_handling_seconds.time():
    # decode & handle OCPP message
    ...
```

---

That’s the full, compact spec your code agent can implement:  
**/metrics endpoint + gauges/counters for cp connection, status, errors, BootNotification, tx lifecycle, Wh as counters for totals, A as gauges for instantaneous current.**