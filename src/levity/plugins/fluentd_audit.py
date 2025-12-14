"""Plugin for structured audit logging to Fluentd."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from fluent import sender

from .base import ChargePointPlugin, PluginContext, PluginHook


class FluentdAuditPlugin(ChargePointPlugin):
    """
    Sends structured audit logs of all OCPP events to Fluentd.

    This plugin captures all OCPP message types (boot notifications, transactions,
    status updates, heartbeats, etc.) and sends them to a Fluentd endpoint for
    centralized logging and analysis.

    Example log entry:
    {
        "event_type": "boot_notification",
        "charge_point_id": "CP001",
        "timestamp": "2024-01-15T10:30:00Z",
        "vendor": "TestVendor",
        "model": "TestModel",
        "firmware_version": "1.0.0"
    }
    """

    def __init__(
        self,
        tag_prefix: str = "ocpp",
        host: str = "localhost",
        port: int = 24224,
        timeout: float = 3.0,
        buffer_overflow_handler: Any = None,
        nanosecond_precision: bool = False,
    ):
        """
        Initialize the Fluentd audit plugin.

        Args:
            tag_prefix: Prefix for Fluentd tags (default: "ocpp")
                       Tags will be: ocpp.boot, ocpp.transaction, etc.
            host: Fluentd server hostname (default: "localhost")
            port: Fluentd server port (default: 24224)
            timeout: Connection timeout in seconds (default: 3.0)
            buffer_overflow_handler: Handler for buffer overflow (default: None)
            nanosecond_precision: Use nanosecond precision timestamps (default: False)
        """
        super().__init__()
        self.tag_prefix = tag_prefix
        self.host = host
        self.port = port
        self.timeout = timeout
        self.buffer_overflow_handler = buffer_overflow_handler
        self.nanosecond_precision = nanosecond_precision
        self.sender = None

    def hooks(self) -> dict[PluginHook, str]:
        """Register hooks for all OCPP message types."""
        return {
            # Boot and connection
            PluginHook.AFTER_BOOT_NOTIFICATION: "log_boot_notification",
            PluginHook.AFTER_HEARTBEAT: "log_heartbeat",
            # Status updates
            PluginHook.AFTER_STATUS_NOTIFICATION: "log_status_notification",
            # Transactions
            PluginHook.AFTER_START_TRANSACTION: "log_start_transaction",
            PluginHook.AFTER_STOP_TRANSACTION: "log_stop_transaction",
            # Meter values
            PluginHook.AFTER_METER_VALUES: "log_meter_values",
            # Authorization
            PluginHook.AFTER_AUTHORIZE: "log_authorize",
        }

    async def initialize(self, charge_point):
        """Initialize Fluentd sender when plugin is registered."""
        try:
            self.sender = sender.FluentSender(
                self.tag_prefix,
                host=self.host,
                port=self.port,
                timeout=self.timeout,
                buffer_overflow_handler=self.buffer_overflow_handler,
                nanosecond_precision=self.nanosecond_precision,
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Fluentd sender: {e}", exc_info=True)
            self.sender = None

    async def cleanup(self, charge_point):
        """Close Fluentd sender when charge point disconnects."""
        if self.sender:
            try:
                await asyncio.to_thread(self.sender.close)
            except Exception as e:
                self.logger.error(f"Error closing Fluentd sender: {e}", exc_info=True)

    async def _send_event(self, tag: str, data: dict):
        """
        Send an event to Fluentd without blocking the event loop.

        Args:
            tag: Event tag (e.g., "boot", "transaction.start")
            data: Event data dictionary
        """
        if not self.sender:
            return

        try:
            await asyncio.to_thread(self.sender.emit, tag, data)
        except Exception as e:
            self.logger.error(f"Failed to send event to Fluentd (tag={tag}): {e}")

    def _base_event_data(self, context: PluginContext) -> dict:
        """Create base event data with common fields."""
        return {
            "charge_point_id": context.charge_point.id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def log_boot_notification(self, context: PluginContext):
        """Log boot notification event."""
        data = self._base_event_data(context)
        data.update(
            {
                "event_type": "boot_notification",
                "vendor": context.message_data.get("charge_point_vendor"),
                "model": context.message_data.get("charge_point_model"),
                "serial_number": context.message_data.get("charge_point_serial_number", ""),
                "firmware_version": context.message_data.get("firmware_version", ""),
                "iccid": context.message_data.get("iccid", ""),
                "imsi": context.message_data.get("imsi", ""),
                "status": context.result.status if context.result else None,
            }
        )
        await self._send_event("boot", data)

    async def log_heartbeat(self, context: PluginContext):
        """Log heartbeat event."""
        data = self._base_event_data(context)
        data.update(
            {
                "event_type": "heartbeat",
            }
        )
        await self._send_event("heartbeat", data)

    async def log_status_notification(self, context: PluginContext):
        """Log status notification event."""
        data = self._base_event_data(context)
        data.update(
            {
                "event_type": "status_notification",
                "connector_id": context.message_data.get("connector_id"),
                "status": context.message_data.get("status"),
                "error_code": context.message_data.get("error_code"),
                "vendor_error_code": context.message_data.get("vendor_error_code", ""),
                "info": context.message_data.get("info", ""),
            }
        )
        await self._send_event("status", data)

    async def log_start_transaction(self, context: PluginContext):
        """Log transaction start event."""
        data = self._base_event_data(context)
        data.update(
            {
                "event_type": "transaction_start",
                "connector_id": context.message_data.get("connector_id"),
                "id_tag": context.message_data.get("id_tag"),
                "meter_start": context.message_data.get("meter_start"),
                "reservation_id": context.message_data.get("reservation_id"),
                "transaction_id": context.result.transaction_id if context.result else None,
                "transaction_timestamp": context.message_data.get("timestamp"),
            }
        )
        await self._send_event("transaction.start", data)

    async def log_stop_transaction(self, context: PluginContext):
        """Log transaction stop event."""
        data = self._base_event_data(context)

        meter_stop = context.message_data.get("meter_stop")
        transaction_id = context.message_data.get("transaction_id")

        # Calculate energy delivered - need to look up meter_start from database
        energy_delivered = None
        try:
            tx = await context.charge_point.tx_repo.get_by_id(transaction_id)
            if tx and tx.meter_start is not None and meter_stop is not None:
                energy_delivered = meter_stop - tx.meter_start
        except Exception:
            pass  # Transaction might not exist

        data.update(
            {
                "event_type": "transaction_stop",
                "transaction_id": transaction_id,
                "id_tag": context.message_data.get("id_tag"),
                "meter_stop": meter_stop,
                "energy_delivered": energy_delivered,
                "reason": context.message_data.get("reason", ""),
                "transaction_timestamp": context.message_data.get("timestamp"),
            }
        )

        # Include transaction data if present
        transaction_data = context.message_data.get("transaction_data", [])
        if transaction_data:
            data["meter_samples_count"] = len(transaction_data)

        await self._send_event("transaction.stop", data)

    async def log_meter_values(self, context: PluginContext):
        """Log meter values event."""
        data = self._base_event_data(context)

        meter_value = context.message_data.get("meter_value", [])
        connector_id = context.message_data.get("connector_id")
        transaction_id = context.message_data.get("transaction_id")

        # Extract summary statistics from meter values
        total_samples = 0
        measurands = set()
        for sample in meter_value:
            sampled_values = sample.get("sampled_value", [])
            total_samples += len(sampled_values)
            for value in sampled_values:
                measurands.add(value.get("measurand", "Energy.Active.Import.Register"))

        data.update(
            {
                "event_type": "meter_values",
                "connector_id": connector_id,
                "transaction_id": transaction_id,
                "samples_count": total_samples,
                "measurands": list(measurands),
            }
        )
        await self._send_event("meter", data)

    async def log_authorize(self, context: PluginContext):
        """Log authorization event."""
        data = self._base_event_data(context)
        data.update(
            {
                "event_type": "authorize",
                "id_tag": context.message_data.get("id_tag"),
                "status": (
                    context.result.id_tag_info.get("status")
                    if context.result and hasattr(context.result, "id_tag_info")
                    else None
                ),
            }
        )
        await self._send_event("authorize", data)


class FluentdWebSocketAuditPlugin(ChargePointPlugin):
    """
    Logs WebSocket connection and disconnection events to Fluentd.

    This is a companion plugin to FluentdAuditPlugin that specifically
    handles connection lifecycle events.

    Example log entry:
    {
        "event_type": "websocket_connect",
        "charge_point_id": "CP001",
        "timestamp": "2024-01-15T10:30:00Z",
        "remote_address": "192.168.1.100:54321"
    }
    """

    def __init__(
        self,
        tag_prefix: str = "ocpp",
        host: str = "localhost",
        port: int = 24224,
        timeout: float = 3.0,
    ):
        """
        Initialize the WebSocket audit plugin.

        Args:
            tag_prefix: Prefix for Fluentd tags (default: "ocpp")
            host: Fluentd server hostname (default: "localhost")
            port: Fluentd server port (default: 24224)
            timeout: Connection timeout in seconds (default: 3.0)
        """
        super().__init__()
        self.tag_prefix = tag_prefix
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sender = None

    def hooks(self) -> dict[PluginHook, str]:
        """No OCPP message hooks - we handle connection events separately."""
        return {}

    async def initialize(self, charge_point):
        """Initialize sender and log connection event."""
        try:
            self.sender = sender.FluentSender(
                self.tag_prefix,
                host=self.host,
                port=self.port,
                timeout=self.timeout,
            )

            # Log connection event
            data = {
                "event_type": "websocket_connect",
                "charge_point_id": charge_point.id,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Try to get remote address from WebSocket connection
            try:
                if hasattr(charge_point, "_connection") and hasattr(
                    charge_point._connection, "remote_address"
                ):
                    remote_addr = charge_point._connection.remote_address
                    data["remote_address"] = f"{remote_addr[0]}:{remote_addr[1]}"
            except Exception:
                pass  # Remote address not available

            await asyncio.to_thread(self.sender.emit, "websocket", data)

        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket audit logger: {e}", exc_info=True)
            self.sender = None

    async def cleanup(self, charge_point):
        """Log disconnection event and close sender."""
        if self.sender:
            try:
                # Log disconnection event
                data = {
                    "event_type": "websocket_disconnect",
                    "charge_point_id": charge_point.id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await asyncio.to_thread(self.sender.emit, "websocket", data)

                await asyncio.to_thread(self.sender.close)
            except Exception as e:
                self.logger.error(f"Error in WebSocket audit cleanup: {e}", exc_info=True)
