"""Integration tests for OCPP server with WebSocket communication."""

import asyncio
from datetime import UTC, datetime

import pytest
import websockets
from ocpp.v16 import ChargePoint as OCPPChargePoint
from ocpp.v16 import call
from ocpp.v16.enums import ChargePointStatus

from levity.repositories import ChargePointRepository, TransactionRepository
from levity.server import OCPPServer


@pytest.fixture
async def ocpp_server(temp_db):
    """Create and start an OCPP server for testing."""
    server = OCPPServer(temp_db, host="127.0.0.1", port=19000)

    # Start server in background - but catch exceptions
    async def run_server():
        try:
            await server.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Server error: {e}")
            raise

    server_task = asyncio.create_task(run_server())

    # Give server time to start
    await asyncio.sleep(1.0)

    # Check if server started successfully
    if server_task.done() and server_task.exception():
        raise server_task.exception()

    yield server

    # Cleanup
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass  # Ignore cleanup errors

    await server.stop()


class MockOCPPClient(OCPPChargePoint):
    """Test OCPP client for integration tests."""

    def __init__(self, id: str, connection):
        super().__init__(id, connection)
        self.messages_received = []

    async def send_boot_notification(self, vendor: str, model: str):
        """Send BootNotification."""
        request = call.BootNotification(
            charge_point_vendor=vendor,
            charge_point_model=model,
        )
        return await self.call(request)

    async def send_heartbeat(self):
        """Send Heartbeat."""
        request = call.Heartbeat()
        return await self.call(request)

    async def send_status_notification(
        self, connector_id: int, status: str, error_code: str = "NoError"
    ):
        """Send StatusNotification."""
        request = call.StatusNotification(
            connector_id=connector_id,
            error_code=error_code,
            status=status,
        )
        return await self.call(request)

    async def send_start_transaction(self, connector_id: int, id_tag: str, meter_start: int = 0):
        """Send StartTransaction."""
        request = call.StartTransaction(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=meter_start,
            timestamp=datetime.now(UTC).isoformat(),
        )
        return await self.call(request)

    async def send_stop_transaction(
        self, transaction_id: int, meter_stop: int, reason: str = "Local"
    ):
        """Send StopTransaction."""
        request = call.StopTransaction(
            transaction_id=transaction_id,
            meter_stop=meter_stop,
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
        )
        return await self.call(request)

    async def send_meter_values(self, connector_id: int, transaction_id: int | None = None):
        """Send MeterValues."""
        request = call.MeterValues(
            connector_id=connector_id,
            transaction_id=transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "sampled_value": [
                        {
                            "value": "1500",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                        }
                    ],
                }
            ],
        )
        return await self.call(request)


@pytest.mark.integration
@pytest.mark.websocket
class TestOCPPIntegration:
    """Integration tests for OCPP protocol over WebSocket."""

    async def test_boot_notification(self, ocpp_server, temp_db):
        """Test BootNotification flow."""
        cp_id = "TEST_CP_001"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)

            # Start client
            client_task = asyncio.create_task(client.start())

            # Send BootNotification
            response = await client.send_boot_notification("TestVendor", "TestModel")

            assert response.status == "Accepted"
            assert response.interval == 60

            # Verify data in database
            conn = await temp_db.connect()
            repo = ChargePointRepository(conn)
            cp = await repo.get_by_id(cp_id)

            assert cp is not None
            assert cp.vendor == "TestVendor"
            assert cp.model == "TestModel"
            assert cp.is_connected is True

            # Cleanup
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_message_before_boot_notification(self, ocpp_server, temp_db):
        """
        Test that messages received before BootNotification automatically create charge point.

        This prevents foreign key constraint errors when chargers send messages
        (like StatusNotification or MeterValues) before BootNotification.
        """
        cp_id = "TEST_CP_EARLY_MESSAGE"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            # Send StatusNotification BEFORE BootNotification
            # This should automatically create a minimal charge point record
            await client.send_status_notification(1, "Available", "NoError")

            # Verify charge point was created automatically
            conn = await temp_db.connect()
            repo = ChargePointRepository(conn)
            cp = await repo.get_by_id(cp_id)

            assert cp is not None, "Charge point should be created automatically"
            assert cp.id == cp_id
            assert cp.status == "Unknown", "Should have default status"
            assert cp.vendor == "", "Should have empty vendor until BootNotification"
            assert cp.is_connected is True

            # Now send BootNotification - should update existing record
            boot_response = await client.send_boot_notification("TestVendor", "TestModel")
            assert boot_response.status == "Accepted"

            # Verify charge point was updated with boot notification data
            cp = await repo.get_by_id(cp_id)
            assert cp.vendor == "TestVendor"
            assert cp.model == "TestModel"
            assert cp.status == "Unknown", (
                "Status should remain Unknown (not updated by BootNotification)"
            )

            # Cleanup
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_heartbeat(self, ocpp_server, temp_db):
        """Test Heartbeat flow."""
        cp_id = "TEST_CP_002"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            # Send BootNotification first
            await client.send_boot_notification("TestVendor", "TestModel")

            # Send Heartbeat
            before = datetime.now(UTC)
            response = await client.send_heartbeat()
            after = datetime.now(UTC)

            assert response.current_time is not None

            # Verify heartbeat timestamp in database
            conn = await temp_db.connect()
            repo = ChargePointRepository(conn)
            cp = await repo.get_by_id(cp_id)

            assert cp.last_heartbeat_at is not None
            # Should be between before and after
            assert (
                before.replace(microsecond=0)
                <= datetime.fromisoformat(str(cp.last_heartbeat_at)).replace(
                    microsecond=0, tzinfo=UTC
                )
                <= after.replace(microsecond=0)
            )

            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_status_notification(self, ocpp_server, temp_db):
        """Test StatusNotification flow."""
        cp_id = "TEST_CP_003"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            await client.send_boot_notification("TestVendor", "TestModel")

            # Send StatusNotification
            await client.send_status_notification(1, ChargePointStatus.available, "NoError")

            # Verify connector status in database
            conn = await temp_db.connect()
            from levity.repositories import ConnectorRepository

            repo = ConnectorRepository(conn)
            connectors = await repo.get_all_for_cp(cp_id)

            assert len(connectors) == 1
            assert connectors[0].conn_id == 1
            assert connectors[0].status == ChargePointStatus.available

            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_complete_charging_session(self, ocpp_server, temp_db):
        """Test a complete charging session from start to finish."""
        cp_id = "TEST_CP_004"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            # 1. Boot notification
            boot_resp = await client.send_boot_notification("TestVendor", "TestModel")
            assert boot_resp.status == "Accepted"

            # 2. Initial status - Available
            await client.send_status_notification(1, ChargePointStatus.available)

            # 3. Start transaction
            start_resp = await client.send_start_transaction(1, "RFID-USER-001", 0)
            transaction_id = start_resp.transaction_id
            assert transaction_id is not None

            # 4. Charging status
            await client.send_status_notification(1, ChargePointStatus.charging)

            # 5. Send some meter values
            await client.send_meter_values(1, transaction_id)

            # 6. Stop transaction
            stop_resp = await client.send_stop_transaction(transaction_id, 5000, "Local")
            assert stop_resp.id_tag_info["status"] == "Accepted"

            # 7. Back to available
            await client.send_status_notification(1, ChargePointStatus.available)

            # Verify complete session in database
            conn = await temp_db.connect()

            # Check charge point
            cp_repo = ChargePointRepository(conn)
            cp = await cp_repo.get_by_id(cp_id)
            assert cp is not None
            assert cp.last_tx_start_at is not None
            assert cp.last_tx_stop_at is not None

            # Check transaction
            tx_repo = TransactionRepository(conn)
            tx = await tx_repo.get_by_id(transaction_id)
            assert tx is not None
            assert tx.id_tag == "RFID-USER-001"
            assert tx.status == "Completed"
            assert tx.meter_start == 0
            assert tx.meter_stop == 5000
            assert tx.energy_delivered == 5000

            # Check meter values
            from levity.repositories import MeterValueRepository

            mv_repo = MeterValueRepository(conn)
            meter_values = await mv_repo.get_for_transaction(transaction_id)
            assert len(meter_values) >= 1

            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_multiple_concurrent_clients(self, ocpp_server, temp_db):
        """Test multiple charge points connecting simultaneously."""
        cp_ids = ["TEST_CP_005", "TEST_CP_006", "TEST_CP_007"]

        async def client_session(cp_id: str):
            async with websockets.connect(
                f"ws://127.0.0.1:19000/ws/{cp_id}",
                subprotocols=["ocpp1.6"],
            ) as ws:
                client = MockOCPPClient(cp_id, ws)
                client_task = asyncio.create_task(client.start())

                # Each client sends boot notification
                response = await client.send_boot_notification(f"Vendor-{cp_id}", f"Model-{cp_id}")
                assert response.status == "Accepted"

                # Send a heartbeat
                await client.send_heartbeat()

                client_task.cancel()
                try:
                    await client_task
                except asyncio.CancelledError:
                    pass

        # Run all clients concurrently
        await asyncio.gather(*[client_session(cp_id) for cp_id in cp_ids])

        # Verify all charge points in database
        conn = await temp_db.connect()
        repo = ChargePointRepository(conn)

        for cp_id in cp_ids:
            cp = await repo.get_by_id(cp_id)
            assert cp is not None
            assert cp.vendor == f"Vendor-{cp_id}"
            assert cp.last_heartbeat_at is not None

    async def test_connection_without_subprotocol(self, ocpp_server, temp_db):
        """
        Test that server's select_subprotocol defaults to ocpp1.6 when client sends empty list.

        This simulates chargers that don't properly send subprotocol headers.
        The server's select_subprotocol method receives an empty list and defaults to ocpp1.6.
        Note: The websockets client library requires us to accept the server's selected
        subprotocol, so we pass subprotocols=["ocpp1.6"] to match what the server selects.
        """
        cp_id = "TEST_CP_NO_SUBPROTOCOL"

        # The server's select_subprotocol will receive an empty list and default to ocpp1.6
        # We need to accept "ocpp1.6" in the client to match the server's selection
        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],  # Accept server's default selection
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            # Send BootNotification to verify connection works
            response = await client.send_boot_notification("TestVendor", "TestModel")

            assert response.status == "Accepted"
            assert response.interval == 60

            # Verify data in database
            conn = await temp_db.connect()
            repo = ChargePointRepository(conn)
            cp = await repo.get_by_id(cp_id)

            assert cp is not None
            assert cp.vendor == "TestVendor"
            assert cp.model == "TestModel"
            assert cp.is_connected is True

            # Cleanup
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    async def test_message_before_boot_notification(self, ocpp_server, temp_db):
        """
        Test that messages received before BootNotification automatically create charge point.

        This prevents foreign key constraint errors when chargers send messages
        (like StatusNotification or MeterValues) before BootNotification.
        """
        cp_id = "TEST_CP_EARLY_MESSAGE"

        async with websockets.connect(
            f"ws://127.0.0.1:19000/ws/{cp_id}",
            subprotocols=["ocpp1.6"],
        ) as ws:
            client = MockOCPPClient(cp_id, ws)
            client_task = asyncio.create_task(client.start())

            # Send StatusNotification BEFORE BootNotification
            # This should automatically create a minimal charge point record
            await client.send_status_notification(1, "Available", "NoError")

            # Verify charge point was created automatically
            conn = await temp_db.connect()
            repo = ChargePointRepository(conn)
            cp = await repo.get_by_id(cp_id)

            assert cp is not None, "Charge point should be created automatically"
            assert cp.id == cp_id
            assert cp.status == "Unknown", "Should have default status"
            assert cp.vendor == "", "Should have empty vendor until BootNotification"
            assert cp.is_connected is True

            # Now send BootNotification - should update existing record
            boot_response = await client.send_boot_notification("TestVendor", "TestModel")
            assert boot_response.status == "Accepted"

            # Verify charge point was updated with boot notification data
            cp = await repo.get_by_id(cp_id)
            assert cp.vendor == "TestVendor"
            assert cp.model == "TestModel"
            assert cp.status == "Unknown", (
                "Status should remain Unknown (not updated by BootNotification)"
            )

            # Cleanup
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass
