# Levity Plugin Framework

Extend the OCPP Central System by hooking into message lifecycle events.

## Built-in Plugins

| Plugin | Purpose |
|--------|---------|
| `PrometheusMetricsPlugin` | Exposes `/metrics` endpoint for monitoring |
| `OrphanedTransactionPlugin` | Auto-closes unclosed transactions on boot/new transaction |
| `AutoRemoteStartPlugin` | Sends RemoteStartTransaction when cable is plugged in |
| `FluentdAuditPlugin` | Sends structured OCPP event logs to Fluentd |
| `FluentdWebSocketAuditPlugin` | Logs WebSocket connect/disconnect to Fluentd |

## Creating a Plugin

```python
from levity.plugins.base import ChargePointPlugin, PluginContext, PluginHook

class MyPlugin(ChargePointPlugin):
    def hooks(self) -> dict[PluginHook, str]:
        return {
            PluginHook.ON_BOOT_NOTIFICATION: "on_boot",
            PluginHook.ON_START_TRANSACTION: "on_tx_start",
        }

    async def on_boot(self, context: PluginContext):
        cp_id = context.charge_point.id
        vendor = context.message_data.get("charge_point_vendor")
        self.logger.info(f"{cp_id} booted: {vendor}")

    async def on_tx_start(self, context: PluginContext):
        id_tag = context.message_data.get("id_tag")
        # Access DB: context.charge_point.tx_repo, meter_repo, etc.
```

## Available Hooks

**Format**: `BEFORE_*` runs before handler, `ON_*` runs after.

- `BOOT_NOTIFICATION` - Charge point registration
- `HEARTBEAT` - Heartbeat messages
- `STATUS_NOTIFICATION` - Status changes
- `START_TRANSACTION` / `STOP_TRANSACTION` - Transaction lifecycle
- `METER_VALUES` - Meter readings
- `AUTHORIZE` - Authorization requests

## Plugin Context

```python
context.charge_point.id          # Charge point ID
context.message_data             # OCPP message parameters (dict)
context.result                   # Handler result (ON_* hooks only)

# Database access
context.charge_point.tx_repo     # TransactionRepository
context.charge_point.meter_repo  # MeterValueRepository
context.charge_point.conn_repo   # ConnectorRepository
context.charge_point.cp_repo     # ChargePointRepository

# Send OCPP message to charge point
from ocpp.v16 import call
response = await context.charge_point.call(
    call.RemoteStartTransaction(connector_id=1, id_tag="user")
)
```

## Lifecycle Methods

```python
async def initialize(self, charge_point):
    """Called when charge point connects."""

async def cleanup(self, charge_point):
    """Called when charge point disconnects."""
```

## Using Plugins

Plugins are configured via CLI flags or by creating a custom server:

```python
from levity.server import OCPPServer
from levity.plugins import AutoRemoteStartPlugin, OrphanedTransactionPlugin

def create_plugins():
    return [
        AutoRemoteStartPlugin(id_tag="anonymous", delay_seconds=1.0),
        OrphanedTransactionPlugin(),
    ]

server = OCPPServer(db=db, plugin_factory=create_plugins, metrics_port=9090)
```
