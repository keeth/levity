# Levity Plugin Framework

The Levity plugin framework allows you to extend the behavior of the OCPP Central System without modifying core code. Plugins can hook into various lifecycle events and add custom logic.

## Architecture

The plugin system uses a **hook-based architecture**:

1. **Plugins** - Classes that extend `ChargePointPlugin`
2. **Hooks** - Lifecycle points where plugins can inject behavior (`BEFORE_*` and `AFTER_*` hooks)
3. **Context** - Information passed to plugin hooks (charge point instance, message data, results)

### Plugin Lifecycle

```
Connection → Plugin Registration → Hook Execution → Disconnect → Plugin Cleanup
```

Each hook execution:
```
BEFORE Hook → Core Handler → AFTER Hook
```

## Built-in Plugins

### AutoRemoteStartPlugin

Automatically starts charging when a cable is plugged in, eliminating the need for RFID authentication.

**Use Case**: Public charging stations with anonymous usage

**Behavior**:
- Monitors `StatusNotification` messages
- When a connector enters `Preparing` state (cable plugged in)
- Waits a configurable delay (default 1 second)
- Sends `RemoteStartTransaction` with a configured ID tag (default "anonymous")

**Configuration**:
```python
from levity.plugins import AutoRemoteStartPlugin

plugin = AutoRemoteStartPlugin(
    id_tag="anonymous",      # ID tag for anonymous charging
    delay_seconds=1.0        # Delay before sending remote start
)
```

### OrphanedTransactionPlugin

Automatically closes unclosed (orphaned) transactions when a new transaction starts.

**Use Case**: Handle edge cases where transactions weren't properly closed due to communication failures, power loss, or other anomalies

**Behavior**:
- Monitors `StartTransaction` messages
- Before a new transaction starts, checks for active transactions on the same charge point
- Closes any orphaned transactions using:
  - Last recorded meter value as `meter_stop` (or `meter_start` if no meter values)
  - Stop reason: "Other"
  - Current timestamp

**Configuration**:
```python
from levity.plugins import OrphanedTransactionPlugin

plugin = OrphanedTransactionPlugin()  # No configuration needed
```

### FluentdAuditPlugin

Sends structured audit logs of all OCPP events to Fluentd for centralized logging, analysis, and archival.

**Use Case**: Compliance logging, analytics, debugging, billing integration

**Behavior**:
- Captures all OCPP messages (boot, heartbeat, status, transactions, meter values, authorization)
- Sends to Fluentd with structured JSON format
- Tags events by type (`ocpp.boot`, `ocpp.transaction.start`, `ocpp.meter`, etc.)
- Includes charge point ID, timestamps, and all relevant message data
- Calculates energy delivered for transaction stop events

**Configuration**:
```python
from levity.plugins import FluentdAuditPlugin

plugin = FluentdAuditPlugin(
    tag_prefix="ocpp",            # Tag prefix (default: "ocpp")
    host="localhost",             # Fluentd server (default: "localhost")
    port=24224,                   # Fluentd port (default: 24224)
    timeout=3.0,                  # Connection timeout (default: 3.0)
)
```

**Example Event**:
```json
{
  "type": "ocpp",
  "cp": "CP001",
  "dir": "recv",
  "msg": {
    "connector_id": 1,
    "id_tag": "USER-123",
    "meter_start": 1000
  }
}
```

### FluentdWebSocketAuditPlugin

Logs WebSocket connection and disconnection events to Fluentd.

**Use Case**: Monitor charge point connectivity, detect connection issues

**Behavior**:
- Logs connection events when charge points connect
- Logs disconnection events when charge points disconnect
- Includes charge point ID and timestamps
- Attempts to include remote IP address if available

**Configuration**:
```python
from levity.plugins import FluentdWebSocketAuditPlugin

plugin = FluentdWebSocketAuditPlugin(
    tag_prefix="ocpp",    # Tag prefix (default: "ocpp")
    host="localhost",     # Fluentd server
    port=24224,           # Fluentd port
)
```

**Example Events**:
```json
{
  "type": "ws",
  "cp": "CP001",
  "event": "connect",
  "remote_addr": "192.168.1.100:54321"
}
```

### PrometheusMetricsPlugin

Exposes Prometheus metrics for monitoring OCPP Central System performance, charge point status, and transaction activity.

**Use Case**: Production monitoring, alerting, performance analysis, capacity planning

**Behavior**:
- Tracks service-level metrics (message handling latency, uptime)
- Monitors per-charge-point connection status and health
- Records transaction lifecycle and energy delivery
- Measures current draw and power consumption
- Counts errors and boots
- All metrics exposed via `/metrics` HTTP endpoint

**Configuration**:
```python
from levity.plugins import PrometheusMetricsPlugin
from levity.server import OCPPServer

def create_plugins():
    return [PrometheusMetricsPlugin()]

server = OCPPServer(
    db=db,
    host="0.0.0.0",
    port=9000,
    plugin_factory=create_plugins,
    metrics_port=9090,  # Enable /metrics endpoint
)
```

**Key Metrics**:
- `ocpp_central_up` - Central system uptime
- `ocpp_cp_connected{cp_id}` - Connection status per charge point
- `ocpp_tx_active{cp_id, connector_id}` - Active transactions
- `ocpp_cp_energy_total_wh{cp_id}` - Cumulative energy delivered
- `ocpp_cp_current_a{cp_id, connector_id}` - Real-time current draw
- `ocpp_msg_handling_seconds` - Message processing latency

See [examples/prometheus/README.md](examples/prometheus/README.md) for complete metrics list and example queries.

## Creating Custom Plugins

### Step 1: Extend ChargePointPlugin

```python
from levity.plugins.base import ChargePointPlugin, PluginContext, PluginHook

class MyCustomPlugin(ChargePointPlugin):
    def hooks(self) -> dict[PluginHook, str]:
        """Register which hooks this plugin wants to handle."""
        return {
            PluginHook.AFTER_BOOT_NOTIFICATION: "on_boot_complete",
            PluginHook.BEFORE_START_TRANSACTION: "before_transaction",
        }

    async def on_boot_complete(self, context: PluginContext):
        """Called AFTER BootNotification is processed."""
        cp_id = context.charge_point.id
        vendor = context.message_data.get("charge_point_vendor")
        self.logger.info(f"Charge point {cp_id} ({vendor}) has booted!")

    async def before_transaction(self, context: PluginContext):
        """Called BEFORE StartTransaction is processed."""
        id_tag = context.message_data.get("id_tag")
        # Perform validation, logging, or other pre-processing
```

### Step 2: Available Hooks

#### Boot Notification
- `BEFORE_BOOT_NOTIFICATION` - Before charge point registration
- `AFTER_BOOT_NOTIFICATION` - After charge point registration

#### Status Notification
- `BEFORE_STATUS_NOTIFICATION` - Before status update
- `AFTER_STATUS_NOTIFICATION` - After status update (used by AutoRemoteStart)

#### Transactions
- `BEFORE_START_TRANSACTION` - Before transaction creation (used by OrphanedTransaction)
- `AFTER_START_TRANSACTION` - After transaction creation
- `BEFORE_STOP_TRANSACTION` - Before transaction completion
- `AFTER_STOP_TRANSACTION` - After transaction completion

#### Heartbeat
- `BEFORE_HEARTBEAT` - Before heartbeat processing
- `AFTER_HEARTBEAT` - After heartbeat processing

#### Meter Values
- `BEFORE_METER_VALUES` - Before meter value storage
- `AFTER_METER_VALUES` - After meter value storage

#### Authorization
- `BEFORE_AUTHORIZE` - Before authorization check
- `AFTER_AUTHORIZE` - After authorization check

### Step 3: Plugin Context

Each hook receives a `PluginContext` object with:

```python
@dataclass
class PluginContext:
    charge_point: LevityChargePoint  # Access to repositories, charge point ID, etc.
    message_data: dict[str, Any]      # The OCPP message parameters
    result: Any = None                # The handler result (AFTER hooks only)
```

**Examples**:

```python
# Access the charge point ID
cp_id = context.charge_point.id

# Access message data
connector_id = context.message_data.get("connector_id")
status = context.message_data.get("status")

# Access repositories (for database operations)
await context.charge_point.tx_repo.get_by_id(tx_id)
await context.charge_point.meter_repo.get_for_transaction(tx_id)

# Send OCPP messages to the charge point
from ocpp.v16 import call
request = call.RemoteStartTransaction(connector_id=1, id_tag="user-123")
response = await context.charge_point.call(request)
```

### Step 4: Lifecycle Methods (Optional)

Override these for setup and cleanup:

```python
async def initialize(self, charge_point: LevityChargePoint):
    """Called once when plugin is registered."""
    self.logger.info(f"Plugin initialized for {charge_point.id}")
    # Setup resources, connections, etc.

async def cleanup(self, charge_point: LevityChargePoint):
    """Called when charge point disconnects."""
    self.logger.info(f"Plugin cleanup for {charge_point.id}")
    # Close connections, save state, etc.
```

## Using Plugins

### Method 1: Server-Wide Plugins

Apply the same plugins to all charge points:

```python
from levity.database import Database
from levity.server import OCPPServer
from levity.plugins import AutoRemoteStartPlugin, OrphanedTransactionPlugin

def create_plugins():
    """Factory function called for each charge point connection."""
    return [
        AutoRemoteStartPlugin(id_tag="anonymous", delay_seconds=1.0),
        OrphanedTransactionPlugin(),
    ]

# Create server with plugin factory
db = Database("levity.db")
server = OCPPServer(
    db=db,
    host="0.0.0.0",
    port=9000,
    plugin_factory=create_plugins,
)

await server.start()
```

### Method 2: Per-Charge-Point Plugins

Different plugins for different charge points:

```python
def create_plugins():
    """Conditional plugin loading based on charge point ID."""
    # Note: At this point, we don't have the CP ID yet
    # For per-CP logic, implement it in the plugin's initialize() method
    return [
        AutoRemoteStartPlugin(),
        OrphanedTransactionPlugin(),
    ]
```

For more advanced per-CP customization, create a custom plugin that checks the charge point ID in its `initialize()` method.

### Method 3: Manual Plugin Registration

For testing or special cases:

```python
from levity.handlers import LevityChargePoint

# Create charge point
cp = LevityChargePoint(
    "CP001",
    websocket_connection,
    db_connection,
    plugins=[AutoRemoteStartPlugin(), OrphanedTransactionPlugin()]
)
```

## Best Practices

### 1. Error Handling

Plugins should handle their own errors gracefully. The framework catches exceptions, but your plugin should:

```python
async def on_status_change(self, context: PluginContext):
    try:
        # Your logic here
        await some_operation()
    except Exception as e:
        self.logger.error(f"Failed to process status change: {e}")
        # Don't re-raise - let the main handler continue
```

### 2. Performance

- **Avoid blocking operations** - All hooks are async; use `await` for I/O
- **BEFORE hooks should be fast** - They delay the main handler
- **Use AFTER hooks for heavy processing** - Main handler has already responded

### 3. Database Access

Access repositories through the charge point instance:

```python
# Transaction operations
await context.charge_point.tx_repo.get_by_id(tx_id)
await context.charge_point.tx_repo.stop_transaction(...)

# Meter values
await context.charge_point.meter_repo.get_last_for_transaction(tx_id)

# Connectors
await context.charge_point.conn_repo.get_by_cp_and_connector(cp_id, conn_id)

# Charge point
await context.charge_point.cp_repo.update_status(cp_id, status)
```

### 4. Logging

Use the built-in logger:

```python
self.logger.info("Informational message")
self.logger.warning("Warning message")
self.logger.error("Error message", exc_info=True)  # Include traceback
```

The logger is automatically named after your plugin class.

### 5. Sending OCPP Messages

Send messages to the charge point using the `call()` method:

```python
from ocpp.v16 import call

# Remote start
request = call.RemoteStartTransaction(connector_id=1, id_tag="user")
response = await context.charge_point.call(request)

# Remote stop
request = call.RemoteStopTransaction(transaction_id=123)
response = await context.charge_point.call(request)

# Get configuration
request = call.GetConfiguration(key=["MeterValueSampleInterval"])
response = await context.charge_point.call(request)
```

## Example: Custom Notification Plugin

Here's a complete example of a plugin that sends notifications when transactions start:

```python
import asyncio
import aiohttp
from levity.plugins.base import ChargePointPlugin, PluginContext, PluginHook

class TransactionNotificationPlugin(ChargePointPlugin):
    """Send webhook notifications when transactions start/stop."""

    def __init__(self, webhook_url: str):
        super().__init__()
        self.webhook_url = webhook_url

    def hooks(self) -> dict[PluginHook, str]:
        return {
            PluginHook.AFTER_START_TRANSACTION: "on_transaction_start",
            PluginHook.AFTER_STOP_TRANSACTION: "on_transaction_stop",
        }

    async def on_transaction_start(self, context: PluginContext):
        """Notify when a transaction starts."""
        data = {
            "event": "transaction_start",
            "charge_point_id": context.charge_point.id,
            "connector_id": context.message_data.get("connector_id"),
            "id_tag": context.message_data.get("id_tag"),
            "meter_start": context.message_data.get("meter_start"),
            "transaction_id": context.result.transaction_id,
        }

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=data)
            self.logger.info(f"Sent start notification for tx {data['transaction_id']}")
        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")

    async def on_transaction_stop(self, context: PluginContext):
        """Notify when a transaction stops."""
        data = {
            "event": "transaction_stop",
            "charge_point_id": context.charge_point.id,
            "transaction_id": context.message_data.get("transaction_id"),
            "meter_stop": context.message_data.get("meter_stop"),
            "reason": context.message_data.get("reason", ""),
        }

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=data)
            self.logger.info(f"Sent stop notification for tx {data['transaction_id']}")
        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
```

Usage:

```python
def create_plugins():
    return [
        AutoRemoteStartPlugin(),
        OrphanedTransactionPlugin(),
        TransactionNotificationPlugin(webhook_url="https://example.com/webhook"),
    ]
```

## Testing Plugins

See [tests/test_plugins.py](tests/test_plugins.py) for examples of how to test plugins:

```python
@pytest.mark.asyncio
async def test_my_plugin(db_connection):
    """Test custom plugin behavior."""
    plugin = MyCustomPlugin()

    # Create test charge point with plugin
    cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

    # Trigger OCPP message that should activate the plugin
    result = await cp.on_boot_notification("TestVendor", "TestModel")

    # Verify plugin behavior
    # (check database, mock calls, logs, etc.)
```

## Plugin Ideas

Here are some ideas for useful plugins:

- **RateLimitPlugin** - Limit transaction frequency per ID tag
- **EnergyPricingPlugin** - Calculate charging costs based on time-of-use pricing
- **MaintenancePlugin** - Track usage metrics and schedule maintenance
- **LoadBalancingPlugin** - Limit total power across multiple connectors
- **ReservationPlugin** - Implement connector reservations
- **BillingPlugin** - Send transaction data to billing system
- **StatisticsPlugin** - Collect and report usage statistics
- **SmartChargingPlugin** - Implement charging profiles based on grid demand
- **FailoverPlugin** - Replicate data to backup system
- **CompliancePlugin** - Log all transactions for regulatory compliance
