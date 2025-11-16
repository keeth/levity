"""Tests for the Fluentd audit logging plugin."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from ocpp.v16.enums import ChargePointStatus

from levity.models import ChargePoint as ChargePointModel
from levity.models import Connector, Transaction
from levity.plugins import FluentdAuditPlugin, FluentdWebSocketAuditPlugin


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


class TestFluentdAuditPlugin:
    """Test the Fluentd audit logging plugin."""

    @pytest.mark.asyncio
    async def test_plugin_initialization(self, db_connection):
        """Test that Fluentd sender is initialized."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin(
                tag_prefix="test_ocpp",
                host="test-host",
                port=12345,
            )

            await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Verify sender was created with correct parameters
            mock_sender_class.assert_called_once_with(
                "test_ocpp",
                host="test-host",
                port=12345,
                timeout=3.0,
                buffer_overflow_handler=None,
                nanosecond_precision=False,
            )

            assert plugin.sender is not None

    @pytest.mark.asyncio
    async def test_boot_notification_logging(self, db_connection):
        """Test that boot notifications are logged to Fluentd."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Trigger boot notification
            await cp.on_boot_notification(
                charge_point_vendor="TestVendor",
                charge_point_model="TestModel",
                firmware_version="1.0.0",
                charge_point_serial_number="SN-123",
            )

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "boot"  # Tag
            event_data = call_args[0][1]  # Data

            assert event_data["event_type"] == "boot_notification"
            assert event_data["charge_point_id"] == "TEST001"
            assert event_data["vendor"] == "TestVendor"
            assert event_data["model"] == "TestModel"
            assert event_data["firmware_version"] == "1.0.0"
            assert event_data["serial_number"] == "SN-123"
            assert event_data["status"] == "Accepted"
            assert "timestamp" in event_data

    @pytest.mark.asyncio
    async def test_status_notification_logging(self, db_connection):
        """Test that status notifications are logged."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Trigger status notification
            await cp.on_status_notification(
                connector_id=1,
                error_code="NoError",
                status=ChargePointStatus.charging,
            )

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "status"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "status_notification"
            assert event_data["charge_point_id"] == "TEST001"
            assert event_data["connector_id"] == 1
            assert event_data["status"] == "Charging"
            assert event_data["error_code"] == "NoError"

    @pytest.mark.asyncio
    async def test_transaction_start_logging(self, db_connection):
        """Test that transaction start is logged."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Start transaction
            result = await cp.on_start_transaction(
                connector_id=1,
                id_tag="USER-123",
                meter_start=1000,
                timestamp="2024-01-15T10:00:00Z",
            )

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "transaction.start"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "transaction_start"
            assert event_data["charge_point_id"] == "TEST001"
            assert event_data["connector_id"] == 1
            assert event_data["id_tag"] == "USER-123"
            assert event_data["meter_start"] == 1000
            assert event_data["transaction_id"] == result.transaction_id

    @pytest.mark.asyncio
    async def test_transaction_stop_logging(self, db_connection):
        """Test that transaction stop is logged with energy calculation."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
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

            # Reset mock to clear boot notification call
            mock_sender.emit.reset_mock()

            # Stop transaction
            await cp.on_stop_transaction(
                transaction_id=tx.id,
                meter_stop=5000,
                timestamp="2024-01-15T11:00:00Z",
                reason="Local",
            )

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "transaction.stop"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "transaction_stop"
            assert event_data["charge_point_id"] == "TEST001"
            assert event_data["transaction_id"] == tx.id
            assert event_data["meter_stop"] == 5000
            assert event_data["energy_delivered"] == 4000  # 5000 - 1000
            assert event_data["reason"] == "Local"

    @pytest.mark.asyncio
    async def test_heartbeat_logging(self, db_connection):
        """Test that heartbeats are logged."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Reset mock to clear boot notification
            mock_sender.emit.reset_mock()

            # Send heartbeat
            await cp.on_heartbeat()

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "heartbeat"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "heartbeat"
            assert event_data["charge_point_id"] == "TEST001"

    @pytest.mark.asyncio
    async def test_meter_values_logging(self, db_connection):
        """Test that meter values are logged with summary statistics."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Create a transaction first for the meter values
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

            # Reset mock
            mock_sender.emit.reset_mock()

            # Send meter values
            meter_value = [
                {
                    "timestamp": "2024-01-15T10:30:00Z",
                    "sampled_value": [
                        {"value": "3000", "measurand": "Energy.Active.Import.Register"},
                        {"value": "220", "measurand": "Voltage"},
                    ],
                }
            ]

            await cp.on_meter_values(connector_id=1, meter_value=meter_value, transaction_id=tx.id)

            # Verify event was emitted
            mock_sender.emit.assert_called()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "meter"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "meter_values"
            assert event_data["connector_id"] == 1
            assert event_data["transaction_id"] == tx.id
            assert event_data["samples_count"] == 2
            assert set(event_data["measurands"]) == {"Energy.Active.Import.Register", "Voltage"}

    @pytest.mark.asyncio
    async def test_cleanup_closes_sender(self, db_connection):
        """Test that cleanup closes the Fluentd sender."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Cleanup
            await plugin.cleanup(cp)

            # Verify sender was closed
            mock_sender.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_sender_initialization_failure(self, db_connection):
        """Test graceful handling when Fluentd sender fails to initialize."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            # Simulate connection failure
            mock_sender_class.side_effect = ConnectionError("Cannot connect to Fluentd")

            plugin = FluentdAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Plugin should still work, just not send events
            assert plugin.sender is None

            # Boot notification should still succeed
            result = await cp.on_boot_notification("TestVendor", "TestModel")
            assert result.status == "Accepted"


class TestFluentdWebSocketAuditPlugin:
    """Test the WebSocket connection/disconnection logging plugin."""

    @pytest.mark.asyncio
    async def test_logs_connection_event(self, db_connection):
        """Test that connection events are logged."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdWebSocketAuditPlugin(tag_prefix="test")
            await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Verify connection event was emitted
            mock_sender.emit.assert_called_once()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "websocket"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "websocket_connect"
            assert event_data["charge_point_id"] == "TEST001"
            assert "timestamp" in event_data

    @pytest.mark.asyncio
    async def test_logs_disconnection_event(self, db_connection):
        """Test that disconnection events are logged."""
        with patch("fluent.sender.FluentSender") as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender

            plugin = FluentdWebSocketAuditPlugin()
            cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

            # Reset mock after connection event
            mock_sender.emit.reset_mock()

            # Trigger disconnection
            await plugin.cleanup(cp)

            # Verify disconnection event was emitted
            mock_sender.emit.assert_called_once()
            call_args = mock_sender.emit.call_args

            assert call_args[0][0] == "websocket"
            event_data = call_args[0][1]

            assert event_data["event_type"] == "websocket_disconnect"
            assert event_data["charge_point_id"] == "TEST001"

            # Verify sender was closed
            mock_sender.close.assert_called_once()
