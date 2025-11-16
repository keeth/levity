"""Unit tests for repository classes."""

from datetime import UTC, datetime

import pytest

from levity.models import ChargePoint, Connector, MeterValue, Transaction
from levity.repositories import (
    ChargePointRepository,
    ConnectorRepository,
    MeterValueRepository,
    TransactionRepository,
)


@pytest.mark.unit
class TestChargePointRepository:
    """Test ChargePoint repository operations."""

    async def test_upsert_new_charge_point(self, db_connection):
        """Test creating a new charge point."""
        repo = ChargePointRepository(db_connection)

        cp = ChargePoint(
            id="TEST_CP_001",
            vendor="TestVendor",
            model="TestModel",
            is_connected=True,
        )

        result = await repo.upsert(cp)

        assert result.id == "TEST_CP_001"
        assert result.vendor == "TestVendor"
        assert result.model == "TestModel"
        assert result.is_connected is True

    async def test_upsert_existing_charge_point(self, db_connection):
        """Test updating an existing charge point."""
        repo = ChargePointRepository(db_connection)

        # Create initial charge point
        cp1 = ChargePoint(id="TEST_CP_001", vendor="Vendor1", model="Model1")
        await repo.upsert(cp1)

        # Update with new data
        cp2 = ChargePoint(id="TEST_CP_001", vendor="Vendor2", model="Model2")
        result = await repo.upsert(cp2)

        assert result.vendor == "Vendor2"
        assert result.model == "Model2"

    async def test_get_by_id(self, db_connection):
        """Test retrieving a charge point by ID."""
        repo = ChargePointRepository(db_connection)

        cp = ChargePoint(id="TEST_CP_001", vendor="TestVendor", model="TestModel")
        await repo.upsert(cp)

        result = await repo.get_by_id("TEST_CP_001")

        assert result is not None
        assert result.id == "TEST_CP_001"
        assert result.vendor == "TestVendor"

    async def test_get_by_id_not_found(self, db_connection):
        """Test retrieving a non-existent charge point."""
        repo = ChargePointRepository(db_connection)

        result = await repo.get_by_id("NONEXISTENT")

        assert result is None

    async def test_update_connection_status(self, db_connection):
        """Test updating charge point connection status."""
        repo = ChargePointRepository(db_connection)

        cp = ChargePoint(id="TEST_CP_001", is_connected=False)
        await repo.upsert(cp)

        now = datetime.now(UTC)
        await repo.update_connection_status("TEST_CP_001", True, now)

        result = await repo.get_by_id("TEST_CP_001")
        assert result.is_connected is True

    async def test_update_heartbeat(self, db_connection):
        """Test updating last heartbeat timestamp."""
        repo = ChargePointRepository(db_connection)

        cp = ChargePoint(id="TEST_CP_001")
        await repo.upsert(cp)

        now = datetime.now(UTC)
        await repo.update_heartbeat("TEST_CP_001", now)

        result = await repo.get_by_id("TEST_CP_001")
        assert result.last_heartbeat_at is not None


@pytest.mark.unit
class TestConnectorRepository:
    """Test Connector repository operations."""

    async def test_upsert_new_connector(self, db_connection):
        """Test creating a new connector."""
        # First create a charge point
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        connector = Connector(cp_id="TEST_CP_001", conn_id=1, status="Available")

        result = await conn_repo.upsert(connector)

        assert result.cp_id == "TEST_CP_001"
        assert result.conn_id == 1
        assert result.status == "Available"

    async def test_upsert_existing_connector(self, db_connection):
        """Test updating an existing connector."""
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)

        # Create initial connector
        conn1 = Connector(cp_id="TEST_CP_001", conn_id=1, status="Available")
        await conn_repo.upsert(conn1)

        # Update status
        conn2 = Connector(cp_id="TEST_CP_001", conn_id=1, status="Charging")
        result = await conn_repo.upsert(conn2)

        assert result.status == "Charging"

    async def test_get_by_cp_and_connector(self, db_connection):
        """Test retrieving a connector by charge point and connector ID."""
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        connector = Connector(cp_id="TEST_CP_001", conn_id=1, status="Available")
        await conn_repo.upsert(connector)

        result = await conn_repo.get_by_cp_and_connector("TEST_CP_001", 1)

        assert result is not None
        assert result.conn_id == 1

    async def test_get_all_for_cp(self, db_connection):
        """Test retrieving all connectors for a charge point."""
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))
        await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=2))

        results = await conn_repo.get_all_for_cp("TEST_CP_001")

        assert len(results) == 2
        assert results[0].conn_id == 1
        assert results[1].conn_id == 2


@pytest.mark.unit
class TestTransactionRepository:
    """Test Transaction repository operations."""

    async def test_create_transaction(self, db_connection):
        """Test creating a new transaction."""
        # Setup charge point and connector
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        # Create transaction
        tx_repo = TransactionRepository(db_connection)
        tx = Transaction(
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            id_tag="RFID-001",
            start_time=datetime.now(UTC),
            meter_start=0,
            status="Active",
        )

        result = await tx_repo.create(tx)

        assert result.id is not None
        assert result.id_tag == "RFID-001"
        assert result.status == "Active"

    async def test_get_by_ocpp_tx_id(self, db_connection):
        """Test retrieving transaction by OCPP transaction ID."""
        # Setup
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        tx_repo = TransactionRepository(db_connection)
        tx = Transaction(
            tx_id=12345,
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            id_tag="RFID-001",
            start_time=datetime.now(UTC),
        )
        await tx_repo.create(tx)

        result = await tx_repo.get_by_ocpp_tx_id(12345)

        assert result is not None
        assert result.tx_id == 12345

    async def test_stop_transaction(self, db_connection):
        """Test stopping a transaction."""
        # Setup
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        tx_repo = TransactionRepository(db_connection)
        tx = Transaction(
            tx_id=12345,
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            id_tag="RFID-001",
            start_time=datetime.now(UTC),
            meter_start=0,
        )
        await tx_repo.create(tx)

        # Stop transaction
        stop_time = datetime.now(UTC)
        await tx_repo.stop_transaction(12345, stop_time, 5000, "Local")

        result = await tx_repo.get_by_ocpp_tx_id(12345)
        assert result.status == "Completed"
        assert result.meter_stop == 5000
        assert result.energy_delivered == 5000

    async def test_get_active_for_connector(self, db_connection):
        """Test retrieving active transaction for a connector."""
        # Setup
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        tx_repo = TransactionRepository(db_connection)
        tx = Transaction(
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            id_tag="RFID-001",
            start_time=datetime.now(UTC),
            status="Active",
        )
        await tx_repo.create(tx)

        result = await tx_repo.get_active_for_connector("TEST_CP_001", conn.id)

        assert result is not None
        assert result.status == "Active"


@pytest.mark.unit
class TestMeterValueRepository:
    """Test MeterValue repository operations."""

    async def test_create_meter_value(self, db_connection):
        """Test creating a meter value."""
        # Setup charge point and connector
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        # Create meter value
        mv_repo = MeterValueRepository(db_connection)
        mv = MeterValue(
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            timestamp=datetime.now(UTC),
            measurand="Energy.Active.Import.Register",
            value=1500.0,
            unit="Wh",
        )

        result = await mv_repo.create(mv)

        assert result.id is not None
        assert result.value == 1500.0

    async def test_create_batch(self, db_connection):
        """Test creating multiple meter values at once."""
        # Setup
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        # Create batch
        mv_repo = MeterValueRepository(db_connection)
        now = datetime.now(UTC)
        meter_values = [
            MeterValue(
                cp_id="TEST_CP_001",
                cp_conn_id=conn.id,
                timestamp=now,
                measurand="Energy.Active.Import.Register",
                value=float(i * 100),
            )
            for i in range(5)
        ]

        await mv_repo.create_batch(meter_values)

        # Verify
        results = await mv_repo.get_for_cp("TEST_CP_001", limit=10)
        assert len(results) == 5

    async def test_get_for_cp(self, db_connection):
        """Test retrieving meter values for a charge point."""
        # Setup
        cp_repo = ChargePointRepository(db_connection)
        await cp_repo.upsert(ChargePoint(id="TEST_CP_001"))

        conn_repo = ConnectorRepository(db_connection)
        conn = await conn_repo.upsert(Connector(cp_id="TEST_CP_001", conn_id=1))

        mv_repo = MeterValueRepository(db_connection)
        mv = MeterValue(
            cp_id="TEST_CP_001",
            cp_conn_id=conn.id,
            timestamp=datetime.now(UTC),
            measurand="Energy.Active.Import.Register",
            value=1500.0,
        )
        await mv_repo.create(mv)

        results = await mv_repo.get_for_cp("TEST_CP_001")

        assert len(results) == 1
        assert results[0].value == 1500.0
