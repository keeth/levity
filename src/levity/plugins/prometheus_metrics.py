"""Plugin for Prometheus metrics instrumentation."""

import time

from prometheus_client import Counter, Gauge, Histogram

from .base import ChargePointPlugin, PluginContext, PluginHook


class PrometheusMetricsPlugin(ChargePointPlugin):
    """
    Exposes Prometheus metrics for OCPP Central System monitoring.

    This plugin tracks:
    - Service-level metrics (message handling latency)
    - Per-CP connection & status (connected, heartbeat, last message)
    - Errors & boots
    - Transaction lifecycle & energy delivery
    - Current measurements

    Metrics are exposed via the standard prometheus_client registry.
    Use prometheus_client.start_http_server() or generate_latest() to expose /metrics.
    """

    # Class-level metrics (shared across all plugin instances)
    # This ensures metrics persist even when charge points disconnect

    # Service-level metrics
    ocpp_central_up = Gauge(
        "ocpp_central_up",
        "1 if OCPP Central System is running, 0 otherwise",
    )

    ocpp_msg_handling_seconds = Histogram(
        "ocpp_msg_handling_seconds",
        "OCPP message handling duration in seconds",
        labelnames=["cp_id", "message_type"],
    )

    # Per-CP connection & status
    ocpp_cp_connected = Gauge(
        "ocpp_cp_connected",
        "1 if WebSocket is open, 0 otherwise",
        labelnames=["cp_id"],
    )

    ocpp_cp_last_heartbeat_ts = Gauge(
        "ocpp_cp_last_heartbeat_ts",
        "Unix timestamp of last heartbeat",
        labelnames=["cp_id"],
    )

    ocpp_cp_last_msg_ts = Gauge(
        "ocpp_cp_last_msg_ts",
        "Unix timestamp of last message received",
        labelnames=["cp_id"],
    )

    ocpp_cp_last_tx_ts = Gauge(
        "ocpp_cp_last_tx_ts",
        "Unix timestamp of last transaction stop",
        labelnames=["cp_id"],
    )

    ocpp_cp_status = Gauge(
        "ocpp_cp_status",
        "Numeric status code of charge point",
        labelnames=["cp_id"],
    )

    ocpp_cp_disconnects_total = Counter(
        "ocpp_cp_disconnects_total",
        "Total number of disconnections",
        labelnames=["cp_id"],
    )

    # Errors & boots
    ocpp_cp_errors_total = Counter(
        "ocpp_cp_errors_total",
        "Total number of errors",
        labelnames=["cp_id", "error_type"],
    )

    ocpp_cp_boots_total = Counter(
        "ocpp_cp_boots_total",
        "Total number of boot notifications",
        labelnames=["cp_id"],
    )

    # Transaction lifecycle
    ocpp_tx_active = Gauge(
        "ocpp_tx_active",
        "1 if transaction is active on connector, 0 otherwise",
        labelnames=["cp_id", "connector_id"],
    )

    ocpp_tx_energy_wh = Gauge(
        "ocpp_tx_energy_wh",
        "Energy delivered in current transaction (Wh)",
        labelnames=["cp_id", "connector_id"],
    )

    ocpp_cp_current_a = Gauge(
        "ocpp_cp_current_a",
        "Instantaneous measured current (A)",
        labelnames=["cp_id", "connector_id"],
    )

    ocpp_cp_current_limit_a = Gauge(
        "ocpp_cp_current_limit_a",
        "Configured current limit (A)",
        labelnames=["cp_id", "connector_id"],
    )

    # Cumulative counters
    ocpp_tx_total = Counter(
        "ocpp_tx_total",
        "Total transaction count",
        labelnames=["cp_id"],
    )

    ocpp_cp_energy_total_wh = Counter(
        "ocpp_cp_energy_total_wh",
        "Cumulative energy delivered (Wh)",
        labelnames=["cp_id"],
    )

    def __init__(self):
        """Initialize the Prometheus metrics plugin."""
        super().__init__()
        # Set central system as up
        self.ocpp_central_up.set(1)
        # Track message start times for histogram
        self._message_start_times = {}

    def hooks(self) -> dict[PluginHook, str]:
        """Register hooks for all relevant OCPP message types."""
        return {
            # Connection lifecycle
            PluginHook.BEFORE_BOOT_NOTIFICATION: "before_message",
            PluginHook.AFTER_BOOT_NOTIFICATION: "after_boot_notification",
            # Heartbeat
            PluginHook.BEFORE_HEARTBEAT: "before_message",
            PluginHook.AFTER_HEARTBEAT: "after_heartbeat",
            # Status
            PluginHook.BEFORE_STATUS_NOTIFICATION: "before_message",
            PluginHook.AFTER_STATUS_NOTIFICATION: "after_status_notification",
            # Transactions
            PluginHook.BEFORE_START_TRANSACTION: "before_message",
            PluginHook.AFTER_START_TRANSACTION: "after_start_transaction",
            PluginHook.BEFORE_STOP_TRANSACTION: "before_message",
            PluginHook.AFTER_STOP_TRANSACTION: "after_stop_transaction",
            # Meter values
            PluginHook.BEFORE_METER_VALUES: "before_message",
            PluginHook.AFTER_METER_VALUES: "after_meter_values",
            # Authorization
            PluginHook.BEFORE_AUTHORIZE: "before_message",
            PluginHook.AFTER_AUTHORIZE: "after_message",
        }

    async def initialize(self, charge_point):
        """Mark charge point as connected when initialized."""
        cp_id = charge_point.id
        self.ocpp_cp_connected.labels(cp_id=cp_id).set(1)
        self.ocpp_cp_last_msg_ts.labels(cp_id=cp_id).set(time.time())

    async def cleanup(self, charge_point):
        """Mark charge point as disconnected and increment disconnect counter."""
        cp_id = charge_point.id
        self.ocpp_cp_connected.labels(cp_id=cp_id).set(0)
        self.ocpp_cp_disconnects_total.labels(cp_id=cp_id).inc()

    # Helper methods

    def _get_message_type(self, context: PluginContext) -> str:  # noqa: PLR0911
        """Extract message type from context."""
        # Try to infer from message data keys - check specific patterns first
        data = context.message_data

        if "charge_point_vendor" in data:
            return "BootNotification"
        if "meter_value" in data:
            return "MeterValues"
        if "meter_stop" in data and "transaction_id" in data:
            return "StopTransaction"
        if "meter_start" in data and "id_tag" in data:
            return "StartTransaction"
        if "status" in data and "connector_id" in data:
            return "StatusNotification"
        if "id_tag" in data:
            return "Authorize"

        return "Heartbeat"

    def _status_to_numeric(self, status: str) -> int:
        """Convert OCPP status string to numeric code."""
        # OCPP 1.6 ChargePointStatus enum
        status_map = {
            "Available": 0,
            "Preparing": 1,
            "Charging": 2,
            "SuspendedEVSE": 3,
            "SuspendedEV": 4,
            "Finishing": 5,
            "Reserved": 6,
            "Unavailable": 7,
            "Faulted": 8,
        }
        return status_map.get(status, -1)

    # Hook handlers

    async def before_message(self, context: PluginContext):
        """Record message start time for latency tracking."""
        cp_id = context.charge_point.id
        message_type = self._get_message_type(context)
        key = (cp_id, message_type)
        self._message_start_times[key] = time.time()

        # Update last message timestamp on any message
        self.ocpp_cp_last_msg_ts.labels(cp_id=cp_id).set(time.time())

    async def after_message(self, context: PluginContext):
        """Record message handling duration."""
        cp_id = context.charge_point.id
        message_type = self._get_message_type(context)
        key = (cp_id, message_type)

        if key in self._message_start_times:
            duration = time.time() - self._message_start_times.pop(key)
            self.ocpp_msg_handling_seconds.labels(
                cp_id=cp_id,
                message_type=message_type,
            ).observe(duration)

    async def after_boot_notification(self, context: PluginContext):
        """Track boot notifications."""
        cp_id = context.charge_point.id
        await self.after_message(context)
        self.ocpp_cp_boots_total.labels(cp_id=cp_id).inc()

    async def after_heartbeat(self, context: PluginContext):
        """Track heartbeat timestamp."""
        cp_id = context.charge_point.id
        await self.after_message(context)
        self.ocpp_cp_last_heartbeat_ts.labels(cp_id=cp_id).set(time.time())

    async def after_status_notification(self, context: PluginContext):
        """Track charge point status changes."""
        cp_id = context.charge_point.id
        await self.after_message(context)

        connector_id = context.message_data.get("connector_id")
        status = context.message_data.get("status")
        error_code = context.message_data.get("error_code")

        # Update status gauge (only for charge point, not individual connectors)
        if connector_id == 0 and status:
            numeric_status = self._status_to_numeric(status)
            self.ocpp_cp_status.labels(cp_id=cp_id).set(numeric_status)

        # Track errors
        if error_code and error_code != "NoError":
            self.ocpp_cp_errors_total.labels(
                cp_id=cp_id,
                error_type=error_code,
            ).inc()

    async def after_start_transaction(self, context: PluginContext):
        """Track transaction start."""
        cp_id = context.charge_point.id
        await self.after_message(context)

        connector_id = context.message_data.get("connector_id")
        context.message_data.get("meter_start", 0)

        # Mark transaction as active
        self.ocpp_tx_active.labels(cp_id=cp_id, connector_id=str(connector_id)).set(1)

        # Initialize energy to 0 (will be updated by meter values)
        self.ocpp_tx_energy_wh.labels(cp_id=cp_id, connector_id=str(connector_id)).set(0)

        # Increment total transaction counter
        self.ocpp_tx_total.labels(cp_id=cp_id).inc()

    async def after_stop_transaction(self, context: PluginContext):
        """Track transaction stop and cumulative energy."""
        cp_id = context.charge_point.id
        await self.after_message(context)

        transaction_id = context.message_data.get("transaction_id")
        meter_stop = context.message_data.get("meter_stop")

        # Look up transaction to get connector_id and meter_start
        try:
            tx = await context.charge_point.tx_repo.get_by_id(transaction_id)
            if tx:
                connector_id = tx.cp_conn_id  # This is the DB connector ID, not OCPP connector_id
                # Get the OCPP connector_id from the connector record
                connector = await context.charge_point.conn_repo.get_by_id(connector_id)
                if connector:
                    ocpp_conn_id = connector.conn_id

                    # Mark transaction as inactive
                    self.ocpp_tx_active.labels(
                        cp_id=cp_id,
                        connector_id=str(ocpp_conn_id),
                    ).set(0)

                    # Reset energy gauge
                    self.ocpp_tx_energy_wh.labels(
                        cp_id=cp_id,
                        connector_id=str(ocpp_conn_id),
                    ).set(0)

                    # Add to cumulative energy if we have meter values
                    if tx.meter_start is not None and meter_stop is not None:
                        energy_wh = meter_stop - tx.meter_start
                        self.ocpp_cp_energy_total_wh.labels(cp_id=cp_id).inc(energy_wh)

        except Exception as e:
            self.logger.error(f"Error tracking transaction stop metrics: {e}")

        # Update last transaction timestamp
        self.ocpp_cp_last_tx_ts.labels(cp_id=cp_id).set(time.time())

    async def after_meter_values(self, context: PluginContext):
        """Track meter values (energy and current)."""
        cp_id = context.charge_point.id
        await self.after_message(context)

        connector_id = context.message_data.get("connector_id")
        transaction_id = context.message_data.get("transaction_id")
        meter_value = context.message_data.get("meter_value", [])

        if not meter_value:
            return

        # Extract latest values from meter_value array
        for sample in meter_value:
            sampled_values = sample.get("sampled_value", [])
            for value in sampled_values:
                measurand = value.get("measurand", "Energy.Active.Import.Register")
                raw_value = value.get("value")

                if raw_value is None:
                    continue

                try:
                    numeric_value = float(raw_value)
                except (ValueError, TypeError):
                    continue

                # Track energy (Wh)
                if measurand == "Energy.Active.Import.Register":
                    # This is the current meter reading
                    # To get energy for THIS transaction, need meter_start
                    if transaction_id:
                        try:
                            tx = await context.charge_point.tx_repo.get_by_id(transaction_id)
                            if tx and tx.meter_start is not None:
                                tx_energy = numeric_value - tx.meter_start
                                self.ocpp_tx_energy_wh.labels(
                                    cp_id=cp_id,
                                    connector_id=str(connector_id),
                                ).set(tx_energy)
                        except Exception:
                            pass

                # Track current (A)
                elif measurand == "Current.Import":
                    self.ocpp_cp_current_a.labels(
                        cp_id=cp_id,
                        connector_id=str(connector_id),
                    ).set(numeric_value)

                # Track current limit if available
                elif measurand == "Current.Offered":
                    self.ocpp_cp_current_limit_a.labels(
                        cp_id=cp_id,
                        connector_id=str(connector_id),
                    ).set(numeric_value)
