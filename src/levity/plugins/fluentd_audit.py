"""Plugin for structured audit logging to Fluentd."""

import asyncio
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
        "type": "ocpp",
        "cp": "CP001",
        "dir": "recv",
        "msg": {
            "charge_point_vendor": "TestVendor",
            "charge_point_model": "TestModel",
            "firmware_version": "1.0.0"
        }
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

    def _base_event_data(
        self, context: PluginContext, direction: str = "recv", message: Any = None
    ) -> dict:
        """Create base event data with common fields in the new format."""
        data = {
            "type": "ocpp",
            "cp": context.charge_point.id,
            "dir": direction,
            "msg": message if message is not None else context.raw_message,
        }
        # Include client IP if available
        if context.charge_point.remote_address:
            data["remote_addr"] = context.charge_point.remote_address
        return data

    def _result_to_dict(self, result: Any) -> dict | None:
        """Convert OCPP result object to dictionary."""
        if result is None:
            return None
        if hasattr(result, "__dict__"):
            # Handle dataclass-like objects
            return {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
        return None

    async def log_boot_notification(self, context: PluginContext):
        """Log boot notification event (received and sent)."""
        # Log received message
        data = self._base_event_data(context)
        await self._send_event("boot", data)
        # Log sent response
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("boot.response", response_data)

    async def log_heartbeat(self, context: PluginContext):
        """Log heartbeat event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("heartbeat", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("heartbeat.response", response_data)

    async def log_status_notification(self, context: PluginContext):
        """Log status notification event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("status", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("status.response", response_data)

    async def log_start_transaction(self, context: PluginContext):
        """Log transaction start event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("transaction.start", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("transaction.start.response", response_data)

    async def log_stop_transaction(self, context: PluginContext):
        """Log transaction stop event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("transaction.stop", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("transaction.stop.response", response_data)

    async def log_meter_values(self, context: PluginContext):
        """Log meter values event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("meter", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("meter.response", response_data)

    async def log_authorize(self, context: PluginContext):
        """Log authorization event (received and sent)."""
        data = self._base_event_data(context)
        await self._send_event("authorize", data)
        if context.result:
            response_data = self._base_event_data(
                context, direction="send", message=self._result_to_dict(context.result)
            )
            await self._send_event("authorize.response", response_data)


class FluentdWebSocketAuditPlugin(ChargePointPlugin):
    """
    Logs WebSocket connection and disconnection events to Fluentd.

    This is a companion plugin to FluentdAuditPlugin that specifically
    handles connection lifecycle events.

    Example log entry:
    {
        "type": "ws",
        "cp": "CP001",
        "event": "connect"
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
                "type": "ws",
                "cp": charge_point.id,
                "event": "connect",
            }
            # Include client IP if available
            if charge_point.remote_address:
                data["remote_addr"] = charge_point.remote_address

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
                    "type": "ws",
                    "cp": charge_point.id,
                    "event": "disconnect",
                }
                # Include client IP if available
                if charge_point.remote_address:
                    data["remote_addr"] = charge_point.remote_address

                await asyncio.to_thread(self.sender.emit, "websocket", data)

                await asyncio.to_thread(self.sender.close)
            except Exception as e:
                self.logger.error(f"Error in WebSocket audit cleanup: {e}", exc_info=True)
