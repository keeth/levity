# Quick Start Guide

Get up and running with Levity in under 2 minutes!

## 1. Installation

```bash
# Install the package
uv pip install -e .
```

## 2. Start the Server

In one terminal:

```bash
levity
```

You should see:

```
2025-01-15 10:30:00,123 - __main__ - INFO - Starting Levity OCPP Central System
2025-01-15 10:30:00,234 - __main__ - INFO - Database: levity.db
2025-01-15 10:30:00,345 - __main__ - INFO - WebSocket endpoint: ws://0.0.0.0:9000/ws/{cp_id}
2025-01-15 10:30:00,456 - levity.server - INFO - Starting OCPP server on 0.0.0.0:9000
2025-01-15 10:30:00,567 - levity.database.connection - INFO - Database schema initialized
2025-01-15 10:30:00,678 - levity.server - INFO - OCPP server listening on ws://0.0.0.0:9000/ws/{cp_id}
```

## 3. Run the Test Client

In another terminal:

```bash
python example_client.py
```

This will simulate a complete charging session with:
- BootNotification
- Status updates
- Starting a transaction
- Sending meter values
- Stopping the transaction

## 4. Inspect the Database

After running the test client, you can inspect the SQLite database:

```bash
sqlite3 levity.db
```

Then run queries:

```sql
-- View all charge points
SELECT id, vendor, model, status, is_connected, last_boot_at FROM cp;

-- View connectors
SELECT cp_id, conn_id, status FROM cp_conn;

-- View transactions
SELECT tx_id, cp_id, id_tag, start_time, stop_time,
       meter_start, meter_stop, energy_delivered, status
FROM tx;

-- View meter values
SELECT cp_id, timestamp, measurand, value, unit
FROM meter_val
ORDER BY timestamp DESC
LIMIT 10;
```

## Next Steps

### Connect Real Charge Points

Configure your charge points to connect to:
```
ws://<your-server-ip>:9000/ws/{charge_point_id}
```

### Customize the Server

```bash
# Custom port
levity --port 8080

# Enable debug logging
levity --log-level DEBUG

# Custom database path
levity --db /var/lib/levity/production.db
```

### Add More Handlers

Edit [src/levity/handlers/charge_point.py](src/levity/handlers/charge_point.py) to add support for additional OCPP messages.

### Build a Dashboard

Query the SQLite database to build monitoring dashboards:
- Real-time charge point status
- Transaction history
- Energy consumption graphs
- Connector availability

## Troubleshooting

### Server won't start

Check if port 9000 is available:
```bash
lsof -i :9000
```

Use a different port:
```bash
levity --port 8080
```

### Client can't connect

1. Check server is running
2. Verify firewall settings
3. Check the WebSocket URL format: `ws://host:port/ws/{cp_id}`

### Database errors

Delete and recreate:
```bash
rm levity.db
levity  # Will recreate schema automatically
```

## API Endpoint Format

The WebSocket endpoint follows this pattern:

```
ws://<host>:<port>/ws/{charge_point_id}
```

Examples:
- `ws://localhost:9000/ws/CP001`
- `ws://192.168.1.100:9000/ws/CHARGER_MAIN_LOBBY`
- `ws://charger.example.com:9000/ws/STATION_42`

The `charge_point_id` must be unique for each charge point and will be used as the primary key in the database.
