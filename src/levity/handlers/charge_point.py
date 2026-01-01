"""OCPP Charge Point handler with database integration."""

import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime

import aiosqlite
from ocpp.routing import after, on
from ocpp.v16 import ChargePoint as BaseChargePoint
from ocpp.v16 import call_result
from ocpp.v16.enums import (
    Action,
    ChargePointStatus,
    RegistrationStatus,
)

from ..logging_utils import log_error, log_ocpp_message
from ..models import ChargePoint, Connector, MeterValue, Transaction
from ..plugins.base import ChargePointPlugin, PluginContext, PluginHook
from ..repositories import (
    ChargePointRepository,
    ConnectorRepository,
    MeterValueRepository,
    TransactionRepository,
)

logger = logging.getLogger("levity")


class LevityChargePoint(BaseChargePoint):
    """
    OCPP 1.6 ChargePoint implementation with SQLite persistence.

    Handles incoming OCPP messages from charge points and persists
    relevant data to the database.

    Supports a plugin system for extending behavior at various lifecycle hooks.
    """

    def __init__(
        self,
        id: str,
        connection,
        db_connection: aiosqlite.Connection,
        plugins: list[ChargePointPlugin] | None = None,
        heartbeat_interval: int = 60,
        response_timeout: int = 30,
        remote_address: str | None = None,
    ):
        super().__init__(id, connection, response_timeout=response_timeout)
        self.db = db_connection
        self.heartbeat_interval = heartbeat_interval
        self.remote_address = remote_address

        # Heartbeat watchdog: disconnect after 3x heartbeat interval with no heartbeats
        self.heartbeat_timeout = heartbeat_interval * 3
        self._last_heartbeat_time: float = time.time()  # Initialize to now
        self._watchdog_task: asyncio.Task | None = None

        # Initialize repositories
        self.cp_repo = ChargePointRepository(db_connection)
        self.conn_repo = ConnectorRepository(db_connection)
        self.tx_repo = TransactionRepository(db_connection)
        self.meter_repo = MeterValueRepository(db_connection)

        # Initialize plugin system
        self.plugins: list[ChargePointPlugin] = plugins or []
        self._plugin_hooks: dict[PluginHook, list[tuple[ChargePointPlugin, str]]] = {}
        self._register_plugins()

        # Store the current raw message for plugins
        self._current_raw_message: list | None = None

    async def route_message(self, raw_message: str):
        """Override to log incoming OCPP messages."""
        try:
            message = json.loads(raw_message)
            # Store raw message for plugins
            self._current_raw_message = message
            message_type = message[0]
            message_id = message[1] if len(message) > 1 else None

            if message_type == 2:  # CALL
                action = message[2] if len(message) > 2 else None
                payload = message[3] if len(message) > 3 else None
                log_ocpp_message(
                    logger,
                    direction="received",
                    cp_id=self.id,
                    message_type="CALL",
                    message_id=message_id,
                    action=action,
                    payload=payload,
                    remote_address=self.remote_address,
                )
            elif message_type == 3:  # CALLRESULT
                payload = message[2] if len(message) > 2 else None
                log_ocpp_message(
                    logger,
                    direction="received",
                    cp_id=self.id,
                    message_type="CALLRESULT",
                    message_id=message_id,
                    payload=payload,
                    remote_address=self.remote_address,
                )
            elif message_type == 4:  # CALLERROR
                error_code = message[2] if len(message) > 2 else None
                error_description = message[3] if len(message) > 3 else None
                error_details = message[4] if len(message) > 4 else None
                log_ocpp_message(
                    logger,
                    direction="received",
                    cp_id=self.id,
                    message_type="CALLERROR",
                    message_id=message_id,
                    error_code=error_code,
                    error_description=error_description,
                    error_details=error_details,
                    remote_address=self.remote_address,
                )
        except Exception as e:
            log_error(
                logger,
                "message_logging_error",
                f"Failed to log incoming message: {e}",
                cp_id=self.id,
            )

        return await super().route_message(raw_message)

    async def call(self, payload, suppress=False):
        """Override to log outgoing OCPP CALL messages."""
        try:
            # Extract action from payload
            action = payload.__class__.__name__
            payload_dict = payload.to_dict() if hasattr(payload, "to_dict") else {}
            log_ocpp_message(
                logger,
                direction="sent",
                cp_id=self.id,
                message_type="CALL",
                action=action,
                payload=payload_dict,
                remote_address=self.remote_address,
            )
        except Exception as e:
            log_error(
                logger,
                "message_logging_error",
                f"Failed to log outgoing message: {e}",
                cp_id=self.id,
            )

        return await super().call(payload, suppress=suppress)

    async def _send(self, message: str) -> None:
        """Override to log all outgoing WebSocket messages (including CALLRESULT responses)."""
        try:
            parsed = json.loads(message)
            message_type_id = parsed[0] if parsed else None
            message_id = parsed[1] if len(parsed) > 1 else None

            if message_type_id == 3:  # CALLRESULT
                payload = parsed[2] if len(parsed) > 2 else None
                log_ocpp_message(
                    logger,
                    direction="sent",
                    cp_id=self.id,
                    message_type="CALLRESULT",
                    message_id=message_id,
                    payload=payload,
                    remote_address=self.remote_address,
                )
            elif message_type_id == 4:  # CALLERROR
                error_code = parsed[2] if len(parsed) > 2 else None
                error_description = parsed[3] if len(parsed) > 3 else None
                error_details = parsed[4] if len(parsed) > 4 else None
                log_ocpp_message(
                    logger,
                    direction="sent",
                    cp_id=self.id,
                    message_type="CALLERROR",
                    message_id=message_id,
                    error_code=error_code,
                    error_description=error_description,
                    error_details=error_details,
                    remote_address=self.remote_address,
                )
            # Note: CALL messages (type 2) are already logged in the call() override
        except Exception as e:
            log_error(
                logger,
                "message_logging_error",
                f"Failed to log outgoing message: {e}",
                cp_id=self.id,
            )

        await super()._send(message)

    async def _ensure_charge_point_exists(self):
        """
        Ensure charge point exists in database.

        Upserts a minimal charge point record if it doesn't exist.
        This prevents foreign key constraint errors when messages arrive
        before BootNotification.
        """
        existing = await self.cp_repo.get_by_id(self.id)
        if not existing:
            # Create minimal charge point record
            minimal_cp = ChargePoint(
                id=self.id,
                is_connected=True,
                status="Unknown",
            )
            await self.cp_repo.upsert(minimal_cp)

    @on(Action.boot_notification)
    async def on_boot_notification(
        self, charge_point_vendor: str, charge_point_model: str, **kwargs
    ):
        """
        Handle BootNotification message.

        Creates or updates the charge point record in the database.
        """
        # Execute BEFORE hooks
        message_data = {
            "charge_point_vendor": charge_point_vendor,
            "charge_point_model": charge_point_model,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.BEFORE_BOOT_NOTIFICATION, message_data)

        # Extract optional fields
        serial_number = kwargs.get("charge_point_serial_number", "")
        firmware_version = kwargs.get("firmware_version", "")
        iccid = kwargs.get("iccid", "")
        imsi = kwargs.get("imsi", "")

        # Create or update charge point
        cp = ChargePoint(
            id=self.id,
            vendor=charge_point_vendor,
            model=charge_point_model,
            serial_number=serial_number,
            firmware_version=firmware_version,
            iccid=iccid,
            imsi=imsi,
            is_connected=True,
            last_boot_at=datetime.now(UTC),
        )

        await self.cp_repo.upsert(cp)

        result = call_result.BootNotification(
            current_time=datetime.now(UTC).isoformat(),
            interval=self.heartbeat_interval,
            status=RegistrationStatus.accepted,
        )

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_BOOT_NOTIFICATION, message_data, result)

        return result

    @on(Action.heartbeat)
    async def on_heartbeat(self):
        """
        Handle Heartbeat message.

        Updates the last heartbeat timestamp for the charge point.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        # Update in-memory heartbeat time for watchdog
        self._last_heartbeat_time = time.time()

        # Execute BEFORE hooks
        message_data = {}
        await self._execute_plugin_hooks(PluginHook.BEFORE_HEARTBEAT, message_data)

        await self.cp_repo.update_heartbeat(self.id, datetime.now(UTC))

        result = call_result.Heartbeat(current_time=datetime.now(UTC).isoformat())

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_HEARTBEAT, message_data, result)

        return result

    @on(Action.status_notification)
    async def on_status_notification(
        self, connector_id: int, error_code: str, status: str, **kwargs
    ):
        """
        Handle StatusNotification message.

        Updates connector status in the database. If connector_id is 0,
        updates the charge point status instead.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        # Execute BEFORE hooks
        message_data = {
            "connector_id": connector_id,
            "error_code": error_code,
            "status": status,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.BEFORE_STATUS_NOTIFICATION, message_data)

        vendor_error_code = kwargs.get("vendor_error_code", "")

        if connector_id == 0:
            # Connector 0 represents the charge point itself
            await self.cp_repo.update_status(self.id, status)
        else:
            # Update or create connector status
            connector = Connector(
                cp_id=self.id,
                conn_id=connector_id,
                status=status,
                error_code=error_code,
                vendor_error_code=vendor_error_code,
            )
            await self.conn_repo.upsert(connector)

        result = call_result.StatusNotification()

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_STATUS_NOTIFICATION, message_data, result)

        return result

    @on(Action.start_transaction)
    async def on_start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int, timestamp: str, **kwargs
    ):
        """
        Handle StartTransaction message.

        Creates a new transaction record in the database.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        # Execute BEFORE hooks (orphaned transaction cleanup happens here)
        message_data = {
            "connector_id": connector_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "timestamp": timestamp,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.BEFORE_START_TRANSACTION, message_data)

        # Get connector database ID
        connector = await self.conn_repo.get_by_cp_and_connector(self.id, connector_id)
        if not connector:
            # Create connector if it doesn't exist
            connector = Connector(
                cp_id=self.id,
                conn_id=connector_id,
                status=ChargePointStatus.charging,
            )
            connector = await self.conn_repo.upsert(connector)

        # Parse timestamp
        start_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Generate transaction ID (using auto-increment from database)
        # We'll use a simple counter approach for OCPP transaction IDs
        tx = Transaction(
            cp_id=self.id,
            cp_conn_id=connector.id,
            id_tag=id_tag,
            start_time=start_time,
            meter_start=meter_start,
            status="Active",
        )

        tx = await self.tx_repo.create(tx)

        # Update charge point last transaction time
        await self.cp_repo.upsert(
            ChargePoint(
                id=self.id,
                is_connected=True,
                last_tx_start_at=start_time,
            )
        )

        # Use database ID as OCPP transaction ID
        result = call_result.StartTransaction(
            transaction_id=tx.id, id_tag_info={"status": "Accepted"}
        )

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_START_TRANSACTION, message_data, result)

        return result

    @on(Action.stop_transaction)
    async def on_stop_transaction(
        self,
        meter_stop: int,
        timestamp: str,
        transaction_id: int,
        **kwargs,
    ):
        """
        Handle StopTransaction message.

        Completes the transaction record in the database.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        # Execute BEFORE hooks
        message_data = {
            "meter_stop": meter_stop,
            "timestamp": timestamp,
            "transaction_id": transaction_id,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.BEFORE_STOP_TRANSACTION, message_data)

        stop_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        reason = kwargs.get("reason", "")

        # Stop the transaction
        await self.tx_repo.stop_transaction(transaction_id, stop_time, meter_stop, reason)

        # Update charge point last transaction time
        await self.cp_repo.upsert(
            ChargePoint(
                id=self.id,
                is_connected=True,
                last_tx_stop_at=stop_time,
            )
        )

        # Process transaction data if present
        transaction_data = kwargs.get("transaction_data", [])
        if transaction_data:
            await self._process_meter_values(transaction_id, self.id, transaction_data)

        result = call_result.StopTransaction(id_tag_info={"status": "Accepted"})

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_STOP_TRANSACTION, message_data, result)

        return result

    @on(Action.meter_values)
    async def on_meter_values(self, connector_id: int, meter_value: list, **kwargs):
        """
        Handle MeterValues message.

        Stores meter value readings in the database.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        transaction_id = kwargs.get("transaction_id")

        # Execute BEFORE hooks
        message_data = {
            "connector_id": connector_id,
            "meter_value": meter_value,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.BEFORE_METER_VALUES, message_data)

        await self._process_meter_values(transaction_id, self.id, meter_value, connector_id)

        result = call_result.MeterValues()

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_METER_VALUES, message_data, result)

        return result

    async def _process_meter_values(
        self,
        transaction_id: int | None,
        cp_id: str,
        meter_data: list,
        connector_id: int | None = None,
    ):
        """Process and store meter values from transaction data or MeterValues message."""
        meter_values = []

        for sample in meter_data:
            timestamp = datetime.fromisoformat(sample.get("timestamp", "").replace("Z", "+00:00"))
            sampled_values = sample.get("sampled_value", [])

            for value in sampled_values:
                # Get connector ID - either from function param or from looking up transaction
                conn_id = connector_id
                if conn_id is None and transaction_id:
                    # transaction_id is the database ID (returned from StartTransaction)
                    tx = await self.tx_repo.get_by_id(transaction_id)
                    conn_id = tx.cp_conn_id if tx else 0

                mv = MeterValue(
                    tx_id=transaction_id,
                    cp_id=cp_id,
                    cp_conn_id=conn_id or 0,
                    timestamp=timestamp,
                    measurand=value.get("measurand", "Energy.Active.Import.Register"),
                    value=float(value.get("value", 0)),
                    unit=value.get("unit", "Wh"),
                    context=value.get("context", "Sample.Periodic"),
                    location=value.get("location", "Outlet"),
                    phase=value.get("phase", ""),
                    format=value.get("format", "Raw"),
                )
                meter_values.append(mv)

        if meter_values:
            await self.meter_repo.create_batch(meter_values)

    @on(Action.authorize)
    async def on_authorize(self, id_tag: str):
        """
        Handle Authorize message.

        Basic implementation that accepts all tags. In production,
        you would validate against a database of authorized tags.
        """
        # Ensure charge point exists before processing
        await self._ensure_charge_point_exists()

        # Execute BEFORE hooks
        message_data = {"id_tag": id_tag}
        await self._execute_plugin_hooks(PluginHook.BEFORE_AUTHORIZE, message_data)

        # For now, accept all authorizations
        result = call_result.Authorize(id_tag_info={"status": "Accepted"})

        # Execute ON hooks (before response is sent)
        await self._execute_plugin_hooks(PluginHook.ON_AUTHORIZE, message_data, result)

        return result

    @after(Action.boot_notification)
    async def after_boot_notification(
        self, charge_point_vendor: str, charge_point_model: str, **kwargs
    ):
        """Execute AFTER hooks after BootNotification response is sent."""
        message_data = {
            "charge_point_vendor": charge_point_vendor,
            "charge_point_model": charge_point_model,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.AFTER_BOOT_NOTIFICATION, message_data)

    @after(Action.heartbeat)
    async def after_heartbeat(self):
        """Execute AFTER hooks after Heartbeat response is sent."""
        message_data = {}
        await self._execute_plugin_hooks(PluginHook.AFTER_HEARTBEAT, message_data)

    @after(Action.status_notification)
    async def after_status_notification(
        self, connector_id: int, error_code: str, status: str, **kwargs
    ):
        """Execute AFTER hooks after StatusNotification response is sent."""
        message_data = {
            "connector_id": connector_id,
            "error_code": error_code,
            "status": status,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.AFTER_STATUS_NOTIFICATION, message_data)

    @after(Action.start_transaction)
    async def after_start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int, timestamp: str, **kwargs
    ):
        """Execute AFTER hooks after StartTransaction response is sent."""
        message_data = {
            "connector_id": connector_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "timestamp": timestamp,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.AFTER_START_TRANSACTION, message_data)

    @after(Action.stop_transaction)
    async def after_stop_transaction(
        self,
        meter_stop: int,
        timestamp: str,
        transaction_id: int,
        **kwargs,
    ):
        """Execute AFTER hooks after StopTransaction response is sent."""
        message_data = {
            "meter_stop": meter_stop,
            "timestamp": timestamp,
            "transaction_id": transaction_id,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.AFTER_STOP_TRANSACTION, message_data)

    @after(Action.meter_values)
    async def after_meter_values(self, connector_id: int, meter_value: list, **kwargs):
        """Execute AFTER hooks after MeterValues response is sent."""
        message_data = {
            "connector_id": connector_id,
            "meter_value": meter_value,
            **kwargs,
        }
        await self._execute_plugin_hooks(PluginHook.AFTER_METER_VALUES, message_data)

    @after(Action.authorize)
    async def after_authorize(self, id_tag: str):
        """Execute AFTER hooks after Authorize response is sent."""
        message_data = {"id_tag": id_tag}
        await self._execute_plugin_hooks(PluginHook.AFTER_AUTHORIZE, message_data)

    async def start(self):
        """Start the charge point message handler and heartbeat watchdog."""
        # Start watchdog task
        self._watchdog_task = asyncio.create_task(self._heartbeat_watchdog())
        try:
            await super().start()
        finally:
            # Cancel watchdog on disconnect
            if self._watchdog_task:
                self._watchdog_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._watchdog_task

    async def _heartbeat_watchdog(self):
        """Background task to detect stale heartbeats and disconnect."""
        # Wait for first heartbeat timeout before starting monitoring
        # This gives the charge point time to boot and send its first heartbeat
        await asyncio.sleep(self.heartbeat_timeout)

        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                elapsed = time.time() - self._last_heartbeat_time

                if elapsed > self.heartbeat_timeout:
                    logger.warning(
                        f"Charge point {self.id} heartbeat timeout "
                        f"(last heartbeat {elapsed:.0f}s ago, timeout {self.heartbeat_timeout}s)",
                        extra={
                            "event_data": {
                                "type": "heartbeat_timeout",
                                "cp_id": self.id,
                                "elapsed_seconds": elapsed,
                                "timeout_seconds": self.heartbeat_timeout,
                                "remote_address": self.remote_address,
                            },
                        },
                    )
                    # Close the WebSocket connection
                    await self._connection.close(1000, "Heartbeat timeout")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Watchdog error for {self.id}: {e}")

    async def on_disconnect(self):
        """Handle charge point disconnection."""
        await self.cp_repo.update_connection_status(self.id, False)

        # Cleanup plugins
        for plugin in self.plugins:
            try:
                await plugin.cleanup(self)
            except Exception as e:
                log_error(
                    logger,
                    "plugin_cleanup_error",
                    f"Error cleaning up plugin {plugin.__class__.__name__}: {e}",
                    cp_id=self.id,
                    plugin=plugin.__class__.__name__,
                    exc_info=e,
                )

    def _register_plugins(self):
        """Register all plugins and build hook mapping."""
        for plugin in self.plugins:
            try:
                hooks = plugin.hooks()
                for hook, method_name in hooks.items():
                    if hook not in self._plugin_hooks:
                        self._plugin_hooks[hook] = []
                    self._plugin_hooks[hook].append((plugin, method_name))
            except Exception as e:
                log_error(
                    logger,
                    "plugin_registration_error",
                    f"Failed to register plugin {plugin.__class__.__name__}: {e}",
                    cp_id=self.id,
                    plugin=plugin.__class__.__name__,
                    exc_info=e,
                )

    async def _execute_plugin_hooks(
        self,
        hook: PluginHook,
        message_data: dict,
        result=None,
    ):
        """
        Execute all registered plugin hooks for a given lifecycle point.

        Args:
            hook: The hook point to execute
            message_data: The message data (kwargs from OCPP handler)
            result: The result from the handler (for AFTER hooks)
        """
        if hook not in self._plugin_hooks:
            return

        context = PluginContext(
            charge_point=self,
            message_data=message_data,
            raw_message=self._current_raw_message,
            result=result,
        )

        for plugin, method_name in self._plugin_hooks[hook]:
            try:
                method = getattr(plugin, method_name)
                await method(context)
            except Exception as e:
                log_error(
                    logger,
                    "plugin_execution_error",
                    f"Error executing {plugin.__class__.__name__}.{method_name} for hook {hook.value}: {e}",
                    cp_id=self.id,
                    plugin=plugin.__class__.__name__,
                    hook=hook.value,
                    method=method_name,
                    exc_info=e,
                )
