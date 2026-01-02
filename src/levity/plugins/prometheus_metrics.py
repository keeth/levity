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

    ocpp_cp_reconnect_during_tx_total = Counter(
        "ocpp_cp_reconnect_during_tx_total",
        "Total number of reconnects/reboots that occurred during active transactions",
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

    ocpp_energy_jump_total = Counter(
        "ocpp_energy_jump_total",
        "Total number of large energy reading jumps detected (>10kWh between readings)",
        labelnames=["cp_id"],
    )

    # Central system call errors (timeouts, rejections when sending commands to CPs)
    ocpp_central_call_errors_total = Counter(
        "ocpp_central_call_errors_total",
        "Total number of errors when central system sends commands to charge points",
        labelnames=["cp_id", "action", "error_type"],
    )

    ocpp_central_call_rejected_total = Counter(
        "ocpp_central_call_rejected_total",
        "Total number of rejected responses when central system sends commands to charge points",
        labelnames=["cp_id", "action", "status"],
    )

    @classmethod
    def record_call_error(cls, cp_id: str, action: str, error_type: str):
        """
        Record an error when the central system sends a command to a charge point.

        Args:
            cp_id: Charge point ID
            action: OCPP action name (e.g., "RemoteStartTransaction")
            error_type: Type of error (e.g., "timeout", "connection_error")
        """
        cls.ocpp_central_call_errors_total.labels(
            cp_id=cp_id,
            action=action,
            error_type=error_type,
        ).inc()

    @classmethod
    def record_call_rejected(cls, cp_id: str, action: str, status: str):
        """
        Record a rejected response when the central system sends a command.

        Args:
            cp_id: Charge point ID
            action: OCPP action name (e.g., "RemoteStartTransaction")
            status: Rejection status (e.g., "Rejected", "NotSupported")
        """
        cls.ocpp_central_call_rejected_total.labels(
            cp_id=cp_id,
            action=action,
            status=status,
        ).inc()

    def __init__(self):
        """Initialize the Prometheus metrics plugin."""
        super().__init__()
        # Set central system as up
        self.ocpp_central_up.set(1)
        # Track message start times for histogram
        self._message_start_times = {}
        # Track previous energy readings per transaction to detect jumps
        # Key: (cp_id, transaction_id), Value: last_reading
        # Only compare readings within the same transaction to avoid false positives
        # when meter resets between transactions
        self._previous_energy_readings = {}

    def hooks(self) -> dict[PluginHook, str]:
        """Register hooks for all relevant OCPP message types."""
        return {
            # Connection lifecycle
            PluginHook.BEFORE_BOOT_NOTIFICATION: "before_message",
            PluginHook.ON_BOOT_NOTIFICATION: "on_boot_notification",
            # Heartbeat
            PluginHook.BEFORE_HEARTBEAT: "before_message",
            PluginHook.ON_HEARTBEAT: "on_heartbeat",
            # Status
            PluginHook.BEFORE_STATUS_NOTIFICATION: "before_message",
            PluginHook.ON_STATUS_NOTIFICATION: "on_status_notification",
            # Transactions
            PluginHook.BEFORE_START_TRANSACTION: "before_message",
            PluginHook.ON_START_TRANSACTION: "on_start_transaction",
            PluginHook.BEFORE_STOP_TRANSACTION: "before_message",
            PluginHook.ON_STOP_TRANSACTION: "on_stop_transaction",
            # Meter values
            PluginHook.BEFORE_METER_VALUES: "before_message",
            PluginHook.ON_METER_VALUES: "on_meter_values",
            # Authorization
            PluginHook.BEFORE_AUTHORIZE: "before_message",
            PluginHook.ON_AUTHORIZE: "on_message",
        }

    async def initialize(self, charge_point):
        """Mark charge point as connected and restore active transaction metrics."""
        cp_id = charge_point.id
        self.ocpp_cp_connected.labels(cp_id=cp_id).set(1)
        self.ocpp_cp_last_msg_ts.labels(cp_id=cp_id).set(time.time())

        # Restore active transaction metrics from database
        # This handles server restarts where transactions are still running
        try:
            active_txs = await charge_point.tx_repo.get_all_active_for_cp(cp_id)
            for tx in active_txs:
                connector = await charge_point.conn_repo.get_by_id(tx.cp_conn_id)
                if connector:
                    conn_id = str(connector.conn_id)
                    self.ocpp_tx_active.labels(cp_id=cp_id, connector_id=conn_id).set(1)

                    # Restore energy if we have meter values
                    last_meter = await charge_point.meter_repo.get_last_for_transaction(
                        tx.id
                    )
                    if last_meter and tx.meter_start is not None:
                        try:
                            current_reading = float(last_meter.value)
                            tx_energy = current_reading - tx.meter_start
                            self.ocpp_tx_energy_wh.labels(
                                cp_id=cp_id, connector_id=conn_id
                            ).set(tx_energy)
                        except (ValueError, TypeError):
                            pass

                    self.logger.info(
                        f"Restored active transaction metric for {cp_id} "
                        f"connector {conn_id} (tx_id={tx.id})"
                    )
        except Exception as e:
            self.logger.error(f"Error restoring transaction metrics for {cp_id}: {e}")

    async def cleanup(self, charge_point):
        """Mark charge point as disconnected and increment disconnect counter."""
        cp_id = charge_point.id

        # Check if there are active transactions when disconnecting
        # This indicates a reconnect/reboot during an active transaction
        active_txs = await charge_point.tx_repo.get_all_active_for_cp(cp_id)
        if active_txs:
            # Increment counter for each active transaction
            for _ in active_txs:
                self.ocpp_cp_reconnect_during_tx_total.labels(cp_id=cp_id).inc()

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

    async def on_message(self, context: PluginContext):
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

    async def on_boot_notification(self, context: PluginContext):
        """Track boot notifications and reset transaction metrics."""
        cp_id = context.charge_point.id
        await self.on_message(context)
        self.ocpp_cp_boots_total.labels(cp_id=cp_id).inc()

        # Check if there were orphaned transactions when booting
        # This indicates a reboot during an active transaction
        active_txs = await context.charge_point.tx_repo.get_all_active_for_cp(cp_id)
        if active_txs:
            # Increment counter for each orphaned transaction found at boot
            for tx in active_txs:
                self.ocpp_cp_reconnect_during_tx_total.labels(cp_id=cp_id).inc()

                # Clean up energy reading tracking for orphaned transaction
                reading_key = (cp_id, tx.id)
                self._previous_energy_readings.pop(reading_key, None)

        # Reset transaction-related metrics for all connectors on this charge point
        # Boot means any active transaction is now terminated (charger rebooted)
        try:
            connectors = await context.charge_point.conn_repo.get_all_for_cp(cp_id)
            for connector in connectors:
                conn_id = str(connector.conn_id)
                # Mark transaction as inactive
                self.ocpp_tx_active.labels(cp_id=cp_id, connector_id=conn_id).set(0)
                # Reset energy gauge
                self.ocpp_tx_energy_wh.labels(cp_id=cp_id, connector_id=conn_id).set(0)
                # Reset current to 0 (charger rebooted, not charging)
                self.ocpp_cp_current_a.labels(cp_id=cp_id, connector_id=conn_id).set(0)
        except Exception as e:
            self.logger.error(f"Error resetting metrics on boot for {cp_id}: {e}")

    async def on_heartbeat(self, context: PluginContext):
        """Track heartbeat timestamp."""
        cp_id = context.charge_point.id
        await self.on_message(context)
        self.ocpp_cp_last_heartbeat_ts.labels(cp_id=cp_id).set(time.time())

    async def on_status_notification(self, context: PluginContext):
        """Track charge point status changes."""
        cp_id = context.charge_point.id
        await self.on_message(context)

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

    async def on_start_transaction(self, context: PluginContext):
        """Track transaction start."""
        cp_id = context.charge_point.id
        await self.on_message(context)

        connector_id = context.message_data.get("connector_id")
        context.message_data.get("meter_start", 0)

        # Mark transaction as active
        self.ocpp_tx_active.labels(cp_id=cp_id, connector_id=str(connector_id)).set(1)

        # Initialize energy to 0 (will be updated by meter values)
        self.ocpp_tx_energy_wh.labels(cp_id=cp_id, connector_id=str(connector_id)).set(0)

        # Increment total transaction counter
        self.ocpp_tx_total.labels(cp_id=cp_id).inc()

    async def on_stop_transaction(self, context: PluginContext):
        """Track transaction stop and cumulative energy."""
        cp_id = context.charge_point.id
        await self.on_message(context)

        transaction_id = context.message_data.get("transaction_id")
        meter_stop = context.message_data.get("meter_stop")

        # Clean up energy reading tracking for this transaction
        reading_key = (cp_id, transaction_id)
        self._previous_energy_readings.pop(reading_key, None)

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

                    # Reset current to 0 (transaction ended, no longer charging)
                    self.ocpp_cp_current_a.labels(
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

    async def on_meter_values(self, context: PluginContext):
        """Track meter values (energy and current)."""
        cp_id = context.charge_point.id
        await self.on_message(context)

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
                    # Detect large jumps in energy readings (charger bugs)
                    # Only compare readings within the SAME transaction to avoid
                    # false positives when meter resets between transactions
                    if transaction_id is not None:
                        reading_key = (cp_id, transaction_id)
                        if reading_key in self._previous_energy_readings:
                            previous_reading = self._previous_energy_readings[reading_key]
                            jump_size = abs(numeric_value - previous_reading)
                            # Detect jumps > 10,000 Wh (10 kWh)
                            if jump_size > 10000:
                                self.ocpp_energy_jump_total.labels(cp_id=cp_id).inc()
                                self.logger.warning(
                                    f"Large energy jump detected: {cp_id} tx={transaction_id} "
                                    f"jumped from {previous_reading} to {numeric_value} Wh "
                                    f"(delta: {jump_size} Wh)"
                                )
                        # Update previous reading for this transaction
                        self._previous_energy_readings[reading_key] = numeric_value

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
