"""OCPP Charge Point handler with database integration."""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from ocpp.routing import on, after
from ocpp.v16 import ChargePoint as BaseChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (
    Action,
    RegistrationStatus,
    ChargePointStatus,
)

from ..models import ChargePoint, Connector, Transaction, MeterValue
from ..repositories import (
    ChargePointRepository,
    ConnectorRepository,
    TransactionRepository,
    MeterValueRepository,
)

logger = logging.getLogger(__name__)


class LevityChargePoint(BaseChargePoint):
    """
    OCPP 1.6 ChargePoint implementation with SQLite persistence.

    Handles incoming OCPP messages from charge points and persists
    relevant data to the database.
    """

    def __init__(self, id: str, connection, db_connection: aiosqlite.Connection):
        super().__init__(id, connection)
        self.db = db_connection

        # Initialize repositories
        self.cp_repo = ChargePointRepository(db_connection)
        self.conn_repo = ConnectorRepository(db_connection)
        self.tx_repo = TransactionRepository(db_connection)
        self.meter_repo = MeterValueRepository(db_connection)

    @on(Action.boot_notification)
    async def on_boot_notification(
        self, charge_point_vendor: str, charge_point_model: str, **kwargs
    ):
        """
        Handle BootNotification message.

        Creates or updates the charge point record in the database.
        """
        logger.info(
            f"BootNotification from {self.id}: {charge_point_vendor} {charge_point_model}"
        )

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
            last_boot_at=datetime.now(timezone.utc),
        )

        await self.cp_repo.upsert(cp)

        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=60,  # Heartbeat interval in seconds
            status=RegistrationStatus.accepted,
        )

    @on(Action.heartbeat)
    async def on_heartbeat(self):
        """
        Handle Heartbeat message.

        Updates the last heartbeat timestamp for the charge point.
        """
        logger.debug(f"Heartbeat from {self.id}")

        await self.cp_repo.update_heartbeat(self.id, datetime.now(timezone.utc))

        return call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    @on(Action.status_notification)
    async def on_status_notification(
        self, connector_id: int, error_code: str, status: str, **kwargs
    ):
        """
        Handle StatusNotification message.

        Updates connector status in the database. If connector_id is 0,
        updates the charge point status instead.
        """
        logger.info(
            f"StatusNotification from {self.id}, connector {connector_id}: {status}"
        )

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

        return call_result.StatusNotification()

    @on(Action.start_transaction)
    async def on_start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int, timestamp: str, **kwargs
    ):
        """
        Handle StartTransaction message.

        Creates a new transaction record in the database.
        """
        logger.info(
            f"StartTransaction from {self.id}, connector {connector_id}, tag {id_tag}"
        )

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
        return call_result.StartTransaction(
            transaction_id=tx.id, id_tag_info={"status": "Accepted"}
        )

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
        logger.info(f"StopTransaction from {self.id}, tx_id {transaction_id}")

        stop_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        reason = kwargs.get("reason", "")
        id_tag = kwargs.get("id_tag")

        # Stop the transaction
        await self.tx_repo.stop_transaction(
            transaction_id, stop_time, meter_stop, reason
        )

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
            await self._process_meter_values(
                transaction_id, self.id, transaction_data
            )

        return call_result.StopTransaction(id_tag_info={"status": "Accepted"})

    @on(Action.meter_values)
    async def on_meter_values(
        self, connector_id: int, meter_value: list, **kwargs
    ):
        """
        Handle MeterValues message.

        Stores meter value readings in the database.
        """
        transaction_id = kwargs.get("transaction_id")
        logger.debug(
            f"MeterValues from {self.id}, connector {connector_id}, "
            f"tx {transaction_id}, {len(meter_value)} samples"
        )

        await self._process_meter_values(transaction_id, self.id, meter_value, connector_id)

        return call_result.MeterValues()

    async def _process_meter_values(
        self,
        transaction_id: Optional[int],
        cp_id: str,
        meter_data: list,
        connector_id: Optional[int] = None,
    ):
        """Process and store meter values from transaction data or MeterValues message."""
        meter_values = []

        for sample in meter_data:
            timestamp = datetime.fromisoformat(
                sample.get("timestamp", "").replace("Z", "+00:00")
            )
            sampled_values = sample.get("sampled_value", [])

            for value in sampled_values:
                # Get connector ID - either from function param or from looking up transaction
                conn_id = connector_id
                if conn_id is None and transaction_id:
                    tx = await self.tx_repo.get_by_ocpp_tx_id(transaction_id)
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
        logger.info(f"Authorize request from {self.id} for tag {id_tag}")

        # For now, accept all authorizations
        # In production, check id_tag against authorized users
        return call_result.Authorize(id_tag_info={"status": "Accepted"})

    @after(Action.boot_notification)
    async def after_boot_notification(
        self, charge_point_vendor: str, charge_point_model: str, **kwargs
    ):
        """Post-processing after BootNotification."""
        logger.debug(f"Charge point {self.id} registered successfully")

    async def on_disconnect(self):
        """Handle charge point disconnection."""
        logger.info(f"Charge point {self.id} disconnected")
        await self.cp_repo.update_connection_status(self.id, False)
