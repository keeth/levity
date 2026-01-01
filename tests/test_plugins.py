"""Tests for the plugin framework."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocpp.v16.enums import ChargePointStatus

from levity.handlers import LevityChargePoint
from levity.models import ChargePoint as ChargePointModel
from levity.plugins import (
    AutoRemoteStartPlugin,
    OrphanedTransactionPlugin,
)
from levity.plugins.base import ChargePointPlugin, PluginContext, PluginHook


async def create_test_charge_point(cp_id, db_connection, plugins=None):
    """Helper to create a charge point with database record."""
    mock_connection = MagicMock()
    cp = LevityChargePoint(cp_id, mock_connection, db_connection, plugins=plugins)

    # Create charge point database record (required for foreign keys)
    await cp.cp_repo.upsert(
        ChargePointModel(id=cp_id, vendor="Test", model="Test", is_connected=True)
    )

    return cp


class TestPluginFramework:
    """Test the base plugin framework functionality."""

    @pytest.mark.asyncio
    async def test_plugin_registration(self, db_connection):
        """Test that plugins are properly registered on initialization."""

        class TestPlugin(ChargePointPlugin):
            def hooks(self):
                return {PluginHook.ON_BOOT_NOTIFICATION: "on_boot"}

            async def on_boot(self, context: PluginContext):
                pass

        plugin = TestPlugin()

        # Create mock connection
        mock_connection = MagicMock()

        # Create charge point with plugin
        cp = LevityChargePoint("TEST001", mock_connection, db_connection, plugins=[plugin])

        # Verify plugin was registered
        assert len(cp.plugins) == 1
        assert cp.plugins[0] == plugin
        assert PluginHook.ON_BOOT_NOTIFICATION in cp._plugin_hooks

    @pytest.mark.asyncio
    async def test_plugin_hook_execution(self, db_connection):
        """Test that plugin hooks are called at the right time."""
        called = []

        class TestPlugin(ChargePointPlugin):
            def hooks(self):
                return {
                    PluginHook.BEFORE_BOOT_NOTIFICATION: "before_boot",
                    PluginHook.ON_BOOT_NOTIFICATION: "on_boot",
                }

            async def before_boot(self, context: PluginContext):
                called.append("before")

            async def on_boot(self, context: PluginContext):
                called.append("on")
                assert context.result is not None

        plugin = TestPlugin()
        mock_connection = MagicMock()

        cp = LevityChargePoint("TEST001", mock_connection, db_connection, plugins=[plugin])

        # Call boot notification
        result = await cp.on_boot_notification("TestVendor", "TestModel")

        # Verify hooks were called in order
        assert called == ["before", "on"]
        assert result.status == "Accepted"

    @pytest.mark.asyncio
    async def test_plugin_error_handling(self, db_connection):
        """Test that plugin errors don't break the main flow."""

        class BrokenPlugin(ChargePointPlugin):
            def hooks(self):
                return {PluginHook.BEFORE_BOOT_NOTIFICATION: "before_boot"}

            async def before_boot(self, context: PluginContext):
                msg = "Intentional error"
                raise RuntimeError(msg)

        plugin = BrokenPlugin()
        mock_connection = MagicMock()

        cp = LevityChargePoint("TEST001", mock_connection, db_connection, plugins=[plugin])

        # Boot notification should still work despite plugin error
        result = await cp.on_boot_notification("TestVendor", "TestModel")
        assert result.status == "Accepted"


class TestAutoRemoteStartPlugin:
    """Test the AutoRemoteStartPlugin."""

    @pytest.mark.asyncio
    async def test_remote_start_on_preparing(self, db_connection):
        """Test that RemoteStartTransaction is sent when connector enters Preparing state."""
        plugin = AutoRemoteStartPlugin(id_tag="test-tag", delay_seconds=0.1)
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Mock the call method
        mock_call = AsyncMock(return_value=MagicMock(status="Accepted"))
        cp.call = mock_call

        # Send status notification for connector entering Preparing state
        # The ON hook runs during the @on handler
        await cp.on_status_notification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.preparing,
        )

        # The AFTER hook runs after the response is sent (via @after decorator)
        # In production this is called by the ocpp library routing, but in tests
        # we need to call it explicitly
        await cp.after_status_notification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.preparing.value,
        )

        # Wait for the delay + a bit extra
        await asyncio.sleep(0.2)

        # Verify RemoteStartTransaction was called
        mock_call.assert_called_once()
        call_args = mock_call.call_args[0][0]
        assert call_args.connector_id == 1
        assert call_args.id_tag == "test-tag"

    @pytest.mark.asyncio
    async def test_no_remote_start_on_other_status(self, db_connection):
        """Test that RemoteStartTransaction is NOT sent for other statuses."""
        plugin = AutoRemoteStartPlugin(delay_seconds=0.1)
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Mock the call method
        mock_call = AsyncMock()
        cp.call = mock_call

        # Send status notification for connector in Available state
        await cp.on_status_notification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.available,
        )

        # Trigger the AFTER hook (as the ocpp library routing would)
        await cp.after_status_notification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.available.value,
        )

        # Wait for potential delay
        await asyncio.sleep(0.2)

        # Verify RemoteStartTransaction was NOT called
        mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignore_charge_point_status(self, db_connection):
        """Test that connector 0 (charge point itself) is ignored."""
        plugin = AutoRemoteStartPlugin(delay_seconds=0.1)

        mock_connection = MagicMock()
        mock_call = AsyncMock()

        cp = LevityChargePoint("TEST001", mock_connection, db_connection, plugins=[plugin])
        cp.call = mock_call

        # Send status notification for connector 0 (charge point)
        await cp.on_status_notification(
            connector_id=0,
            error_code="NoError",
            status=ChargePointStatus.preparing,
        )

        # Trigger the AFTER hook (as the ocpp library routing would)
        await cp.after_status_notification(
            connector_id=0,
            error_code="NoError",
            status=ChargePointStatus.preparing.value,
        )

        # Wait for potential delay
        await asyncio.sleep(0.2)

        # Verify RemoteStartTransaction was NOT called
        mock_call.assert_not_called()


class TestOrphanedTransactionPlugin:
    """Test the OrphanedTransactionPlugin."""

    @pytest.mark.asyncio
    async def test_closes_orphaned_transactions(self, db_connection):
        """Test that orphaned transactions are closed when a new one starts."""
        plugin = OrphanedTransactionPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Create connector first
        from levity.models import Connector

        connector = Connector(
            cp_id="TEST001",
            conn_id=1,
            status=ChargePointStatus.available,
        )
        connector = await cp.conn_repo.upsert(connector)

        # Create an orphaned transaction (Active status, no stop time)
        from levity.models import Transaction

        orphaned_tx = Transaction(
            cp_id="TEST001",
            cp_conn_id=connector.id,
            id_tag="orphaned-tag",
            start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        orphaned_tx = await cp.tx_repo.create(orphaned_tx)

        # Add a meter value to the orphaned transaction
        from levity.models import MeterValue

        meter_val = MeterValue(
            tx_id=orphaned_tx.id,
            cp_id="TEST001",
            cp_conn_id=connector.id,
            timestamp=datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC),
            measurand="Energy.Active.Import.Register",
            value=5000.0,  # 5000 Wh delivered
            unit="Wh",
        )
        await cp.meter_repo.create(meter_val)

        # Start a new transaction - this should trigger orphaned cleanup
        await cp.on_start_transaction(
            connector_id=1,
            id_tag="new-tag",
            meter_start=5000,
            timestamp="2024-01-01T13:00:00Z",
        )

        # Verify the orphaned transaction was closed
        closed_tx = await cp.tx_repo.get_by_id(orphaned_tx.id)
        assert closed_tx.status == "Completed"
        assert closed_tx.meter_stop == 5000  # Used the meter value
        assert closed_tx.stop_reason == "Other"
        assert closed_tx.stop_time is not None

    @pytest.mark.asyncio
    async def test_handles_no_meter_values(self, db_connection):
        """Test that orphaned transactions without meter values use meter_start."""
        plugin = OrphanedTransactionPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Create connector
        from levity.models import Connector

        connector = Connector(
            cp_id="TEST001",
            conn_id=1,
            status=ChargePointStatus.available,
        )
        connector = await cp.conn_repo.upsert(connector)

        # Create orphaned transaction WITHOUT meter values
        from levity.models import Transaction

        orphaned_tx = Transaction(
            cp_id="TEST001",
            cp_conn_id=connector.id,
            id_tag="orphaned-tag",
            start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            meter_start=1000,
            status="Active",
        )
        orphaned_tx = await cp.tx_repo.create(orphaned_tx)

        # Start a new transaction
        await cp.on_start_transaction(
            connector_id=1,
            id_tag="new-tag",
            meter_start=1000,
            timestamp="2024-01-01T13:00:00Z",
        )

        # Verify the orphaned transaction was closed with meter_start
        closed_tx = await cp.tx_repo.get_by_id(orphaned_tx.id)
        assert closed_tx.status == "Completed"
        assert closed_tx.meter_stop == 1000  # Used meter_start
        assert closed_tx.stop_reason == "Other"

    @pytest.mark.asyncio
    async def test_no_action_when_no_orphans(self, db_connection):
        """Test that plugin does nothing when there are no orphaned transactions."""
        plugin = OrphanedTransactionPlugin()
        cp = await create_test_charge_point("TEST001", db_connection, plugins=[plugin])

        # Start a transaction with no existing orphans
        result = await cp.on_start_transaction(
            connector_id=1,
            id_tag="new-tag",
            meter_start=1000,
            timestamp="2024-01-01T13:00:00Z",
        )

        # Should succeed without errors
        assert result.id_tag_info["status"] == "Accepted"
