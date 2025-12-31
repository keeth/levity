"""Tests for the Prometheus metrics plugin."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ocpp.v16.enums import ChargePointStatus
from prometheus_client import REGISTRY

from levity.models import ChargePoint as ChargePointModel
from levity.models import Connector, Transaction
from levity.plugins import PrometheusMetricsPlugin


async def create_test_charge_point(cp_id, db_connection, plugins=None):
    """Helper to create a charge point with database record."""
    from levity.handlers import LevityChargePoint

    mock_connection = MagicMock()
    cp = LevityChargePoint(cp_id, mock_connection, db_connection, plugins=plugins)

    # Create charge point database record
    await cp.cp_repo.upsert(
        ChargePointModel(id=cp_id, vendor="Test", model="Test", is_connected=True)
    )

    # Initialize plugins (normally done by server)
    if plugins:
        for plugin in plugins:
            await plugin.initialize(cp)

    return cp


def get_metric_value(metric, labels):
    """Helper to get current value of a metric with specific labels."""
    for sample in metric.collect()[0].samples:
        if sample.labels == labels:
            return sample.value
    return None


class TestPrometheusMetricsPlugin:
    """Test the Prometheus metrics plugin."""

    @pytest.mark.asyncio
    async def test_plugin_initialization(self, db_connection):
        """Test that metrics are initialized on plugin creation."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Verify connection metric
        value = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "TEST001"})
        assert value == 1.0

        # Verify central system is up
        samples = list(plugin.ocpp_central_up.collect()[0].samples)
        assert len(samples) > 0
        assert samples[0].value == 1.0

    @pytest.mark.asyncio
    async def test_cleanup_marks_disconnected(self, db_connection):
        """Test that cleanup marks charge point as disconnected."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Initially connected
        value = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "TEST001"})
        assert value == 1.0

        # Cleanup
        await plugin.cleanup(cp)

        # Now disconnected
        value = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "TEST001"})
        assert value == 0.0

        # Disconnect counter incremented
        value = get_metric_value(plugin.ocpp_cp_disconnects_total, {"cp_id": "TEST001"})
        assert value == 1.0

    @pytest.mark.asyncio
    async def test_boot_notification_tracking(self, db_connection):
        """Test that boot notifications increment counter."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Send boot notification
        await cp.on_boot_notification("TestVendor", "TestModel")

        # Verify boot counter
        value = get_metric_value(plugin.ocpp_cp_boots_total, {"cp_id": "TEST001"})
        assert value == 1.0

    @pytest.mark.asyncio
    async def test_heartbeat_tracking(self, db_connection):
        """Test that heartbeat updates timestamp."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Send heartbeat
        await cp.on_heartbeat()

        # Verify heartbeat timestamp is set
        value = get_metric_value(plugin.ocpp_cp_last_heartbeat_ts, {"cp_id": "TEST001"})
        assert value is not None
        assert value > 0

    @pytest.mark.asyncio
    async def test_status_notification_tracking(self, db_connection):
        """Test that status notifications update metrics."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Send status notification for charge point (connector 0)
        await cp.on_status_notification(
            connector_id=0,
            error_code="NoError",
            status=ChargePointStatus.available,
        )

        # Verify status metric
        value = get_metric_value(plugin.ocpp_cp_status, {"cp_id": "TEST001"})
        assert value == 0.0  # Available = 0

    @pytest.mark.asyncio
    async def test_error_tracking(self, db_connection):
        """Test that errors are counted."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Send status notification with error
        await cp.on_status_notification(
            connector_id=1,
            error_code="GroundFailure",
            status=ChargePointStatus.faulted,
        )

        # Verify error counter
        value = get_metric_value(
            plugin.ocpp_cp_errors_total,
            {"cp_id": "TEST001", "error_type": "GroundFailure"},
        )
        assert value == 1.0

    @pytest.mark.asyncio
    async def test_transaction_start_tracking(self, db_connection):
        """Test that transaction start updates metrics."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Start transaction
        await cp.on_start_transaction(
            connector_id=1,
            id_tag="USER-123",
            meter_start=1000,
            timestamp="2024-01-15T10:00:00Z",
        )

        # Verify transaction active
        value = get_metric_value(
            plugin.ocpp_tx_active,
            {"cp_id": "TEST001", "connector_id": "1"},
        )
        assert value == 1.0

        # Verify transaction counter
        value = get_metric_value(plugin.ocpp_tx_total, {"cp_id": "TEST001"})
        assert value == 1.0

        # Verify energy gauge initialized
        value = get_metric_value(
            plugin.ocpp_tx_energy_wh,
            {"cp_id": "TEST001", "connector_id": "1"},
        )
        assert value == 0.0

    @pytest.mark.asyncio
    async def test_transaction_stop_tracking(self, db_connection):
        """Test that transaction stop updates metrics."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Create a transaction first
        connector = Connector(cp_id="TEST001", conn_id=1, status=ChargePointStatus.charging)
        connector = await cp.conn_repo.upsert(connector)

        tx = Transaction(
            cp_id="TEST001",
            cp_conn_id=connector.id,
            id_tag="USER-123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        tx = await cp.tx_repo.create(tx)

        # Stop transaction
        await cp.on_stop_transaction(
            transaction_id=tx.id,
            meter_stop=5000,
            timestamp="2024-01-15T11:00:00Z",
            reason="Local",
        )

        # Verify transaction no longer active
        value = get_metric_value(
            plugin.ocpp_tx_active,
            {"cp_id": "TEST001", "connector_id": "1"},
        )
        assert value == 0.0

        # Verify energy counter incremented
        value = get_metric_value(plugin.ocpp_cp_energy_total_wh, {"cp_id": "TEST001"})
        assert value == 4000.0  # 5000 - 1000

        # Verify last transaction timestamp
        value = get_metric_value(plugin.ocpp_cp_last_tx_ts, {"cp_id": "TEST001"})
        assert value is not None
        assert value > 0

    @pytest.mark.asyncio
    async def test_meter_values_tracking(self, db_connection):
        """Test that meter values update metrics."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Create a transaction first
        connector = Connector(cp_id="TEST001", conn_id=1, status=ChargePointStatus.charging)
        connector = await cp.conn_repo.upsert(connector)

        tx = Transaction(
            cp_id="TEST001",
            cp_conn_id=connector.id,
            id_tag="USER-123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        tx = await cp.tx_repo.create(tx)

        # Send meter values
        meter_value = [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "sampled_value": [
                    {"value": "3000", "measurand": "Energy.Active.Import.Register"},
                    {"value": "16.5", "measurand": "Current.Import"},
                ],
            }
        ]

        await cp.on_meter_values(connector_id=1, meter_value=meter_value, transaction_id=tx.id)

        # Verify energy metric
        value = get_metric_value(
            plugin.ocpp_tx_energy_wh,
            {"cp_id": "TEST001", "connector_id": "1"},
        )
        assert value == 2000.0  # 3000 - 1000 (meter_start)

        # Verify current metric
        value = get_metric_value(
            plugin.ocpp_cp_current_a,
            {"cp_id": "TEST001", "connector_id": "1"},
        )
        assert value == 16.5

    @pytest.mark.asyncio
    async def test_energy_jump_detection(self, db_connection):
        """Test that large energy reading jumps are detected within a transaction."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Create connector and transaction for meter values
        connector = Connector(cp_id="TEST001", conn_id=1, status=ChargePointStatus.charging)
        connector = await cp.conn_repo.upsert(connector)

        tx = Transaction(
            cp_id="TEST001",
            cp_conn_id=connector.id,
            id_tag="USER-123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=5000,
            status="Active",
        )
        tx = await cp.tx_repo.create(tx)

        # Send first meter value (normal reading)
        meter_value1 = [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "sampled_value": [
                    {"value": "5000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value1, transaction_id=tx.id)

        # Verify no jumps detected yet (first reading establishes baseline)
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST001"})
        assert value is None or value == 0.0

        # Send second meter value with normal increment (should not trigger)
        meter_value2 = [
            {
                "timestamp": "2024-01-15T10:01:00Z",
                "sampled_value": [
                    {"value": "5100", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value2, transaction_id=tx.id)

        # Still no jumps (only 100 Wh difference)
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST001"})
        assert value is None or value == 0.0

        # Send third meter value with large jump (>10,000 Wh)
        meter_value3 = [
            {
                "timestamp": "2024-01-15T10:02:00Z",
                "sampled_value": [
                    {"value": "16000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value3, transaction_id=tx.id)

        # Verify jump counter incremented (16000 - 5100 = 10900 Wh > 10000)
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST001"})
        assert value == 1.0

        # Send another large jump
        meter_value4 = [
            {
                "timestamp": "2024-01-15T10:03:00Z",
                "sampled_value": [
                    {"value": "27000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value4, transaction_id=tx.id)

        # Verify counter incremented again (27000 - 16000 = 11000 Wh > 10000)
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST001"})
        assert value == 2.0

    @pytest.mark.asyncio
    async def test_energy_jump_detection_negative_jump(self, db_connection):
        """Test that negative jumps (decreases) are also detected within a transaction."""
        plugin = PrometheusMetricsPlugin()
        # Use unique ID to avoid metric conflicts with other tests
        cp = await create_test_charge_point("TEST_NEG_JUMP", db_connection, plugins=[plugin])

        # Create connector and transaction for meter values
        connector = Connector(cp_id="TEST_NEG_JUMP", conn_id=1, status=ChargePointStatus.charging)
        connector = await cp.conn_repo.upsert(connector)

        tx = Transaction(
            cp_id="TEST_NEG_JUMP",
            cp_conn_id=connector.id,
            id_tag="USER-123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=20000,
            status="Active",
        )
        tx = await cp.tx_repo.create(tx)

        # Send first meter value
        meter_value1 = [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "sampled_value": [
                    {"value": "20000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value1, transaction_id=tx.id)

        # Send meter value with large negative jump (abs value > 10,000)
        # This could indicate a meter reset bug or data corruption
        meter_value2 = [
            {
                "timestamp": "2024-01-15T10:01:00Z",
                "sampled_value": [
                    {"value": "5000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value2, transaction_id=tx.id)

        # Verify jump detected (abs(5000 - 20000) = 15000 > 10000)
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST_NEG_JUMP"})
        assert value == 1.0

    @pytest.mark.asyncio
    async def test_energy_jump_detection_multiple_charge_points(self, db_connection):
        """Test that energy jumps are tracked separately per charge point/transaction."""
        plugin = PrometheusMetricsPlugin()

        # Create two charge points
        cp1 = await create_test_charge_point("CP001", db_connection, plugins=[plugin])
        cp2 = await create_test_charge_point("CP002", db_connection, plugins=[plugin])

        # Create connectors and transactions for both charge points
        connector1 = Connector(cp_id="CP001", conn_id=1, status=ChargePointStatus.charging)
        connector1 = await cp1.conn_repo.upsert(connector1)
        connector2 = Connector(cp_id="CP002", conn_id=1, status=ChargePointStatus.charging)
        connector2 = await cp2.conn_repo.upsert(connector2)

        tx1 = Transaction(
            cp_id="CP001",
            cp_conn_id=connector1.id,
            id_tag="USER-001",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        tx1 = await cp1.tx_repo.create(tx1)

        tx2 = Transaction(
            cp_id="CP002",
            cp_conn_id=connector2.id,
            id_tag="USER-002",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        tx2 = await cp2.tx_repo.create(tx2)

        # Send initial readings for both
        meter_value1 = [
            {
                "timestamp": "2024-01-15T10:00:00Z",
                "sampled_value": [
                    {"value": "1000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp1.on_meter_values(connector_id=1, meter_value=meter_value1, transaction_id=tx1.id)
        await cp2.on_meter_values(connector_id=1, meter_value=meter_value1, transaction_id=tx2.id)

        # Trigger jump on CP001 only
        meter_value2 = [
            {
                "timestamp": "2024-01-15T10:01:00Z",
                "sampled_value": [
                    {"value": "12000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp1.on_meter_values(connector_id=1, meter_value=meter_value2, transaction_id=tx1.id)

        # Verify CP001 has jump, CP002 does not
        value1 = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "CP001"})
        value2 = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "CP002"})
        assert value1 == 1.0
        assert value2 is None or value2 == 0.0

    @pytest.mark.asyncio
    async def test_energy_jump_not_detected_between_transactions(self, db_connection):
        """Test that meter resets between transactions don't trigger false positive jumps."""
        plugin = PrometheusMetricsPlugin()
        # Use unique ID to avoid metric conflicts
        cp = await create_test_charge_point("TEST_NO_FALSE_POS", db_connection, plugins=[plugin])

        # Create connector
        connector = Connector(cp_id="TEST_NO_FALSE_POS", conn_id=1, status=ChargePointStatus.charging)
        connector = await cp.conn_repo.upsert(connector)

        # First transaction with high meter reading
        tx1 = Transaction(
            cp_id="TEST_NO_FALSE_POS",
            cp_conn_id=connector.id,
            id_tag="USER-123",
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            meter_start=50000,
            status="Active",
        )
        tx1 = await cp.tx_repo.create(tx1)

        # Send meter value for first transaction
        meter_value1 = [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "sampled_value": [
                    {"value": "55000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value1, transaction_id=tx1.id)

        # Stop first transaction
        await cp.on_stop_transaction(
            transaction_id=tx1.id,
            meter_stop=55000,
            timestamp="2024-01-15T11:00:00Z",
            reason="Local",
        )

        # Second transaction starts with meter reset (low value after high value)
        tx2 = Transaction(
            cp_id="TEST_NO_FALSE_POS",
            cp_conn_id=connector.id,
            id_tag="USER-456",
            start_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            meter_start=0,  # Meter reset!
            status="Active",
        )
        tx2 = await cp.tx_repo.create(tx2)

        # Send meter value for second transaction (would be huge jump if tracked globally)
        meter_value2 = [
            {
                "timestamp": "2024-01-15T12:30:00Z",
                "sampled_value": [
                    {"value": "5000", "measurand": "Energy.Active.Import.Register"},
                ],
            }
        ]
        await cp.on_meter_values(connector_id=1, meter_value=meter_value2, transaction_id=tx2.id)

        # Should NOT detect a jump because readings are from different transactions
        value = get_metric_value(plugin.ocpp_energy_jump_total, {"cp_id": "TEST_NO_FALSE_POS"})
        assert value is None or value == 0.0

    @pytest.mark.asyncio
    async def test_message_latency_tracking(self, db_connection):
        """Test that message handling latency is recorded."""
        plugin = PrometheusMetricsPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Send a message (boot notification)
        await cp.on_boot_notification("TestVendor", "TestModel")

        # Check that histogram has samples
        samples = list(plugin.ocpp_msg_handling_seconds.collect()[0].samples)
        # Filter for our charge point
        cp_samples = [s for s in samples if s.labels.get("cp_id") == "TEST001"]
        assert len(cp_samples) > 0

    @pytest.mark.asyncio
    async def test_multiple_charge_points(self, db_connection):
        """Test that metrics work with multiple charge points."""
        plugin = PrometheusMetricsPlugin()

        # Create two charge points
        cp1 = await create_test_charge_point("CP001", db_connection, plugins=[plugin])
        cp2 = await create_test_charge_point("CP002", db_connection, plugins=[plugin])

        # Both should be connected
        value1 = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "CP001"})
        value2 = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "CP002"})
        assert value1 == 1.0
        assert value2 == 1.0

        # Disconnect one
        await plugin.cleanup(cp1)

        # Only cp2 should be connected
        value1 = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "CP001"})
        value2 = get_metric_value(plugin.ocpp_cp_connected, {"cp_id": "CP002"})
        assert value1 == 0.0
        assert value2 == 1.0
