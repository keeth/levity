#!/usr/bin/env python3
"""
Example OCPP client for testing the Levity central system.

This script simulates a simple charge point that connects to the server,
sends a BootNotification, Heartbeat, and StatusNotification.
"""

import asyncio
import logging
from datetime import UTC, datetime

import websockets
from ocpp.v16 import ChargePoint, call
from ocpp.v16.enums import ChargePointStatus

logging.basicConfig(level=logging.INFO)


class TestChargePoint(ChargePoint):
    """Simple test charge point implementation."""

    async def send_boot_notification(self):
        """Send BootNotification to the central system."""
        request = call.BootNotification(
            charge_point_vendor="TestVendor",
            charge_point_model="TestModel v1.0",
            charge_point_serial_number="TEST-001",
            firmware_version="1.0.0",
        )
        response = await self.call(request)

        if response.status == "Accepted":
            print("✓ Connected to central system")
            print(f"  Heartbeat interval: {response.interval}s")
            print(f"  Server time: {response.current_time}")

        return response

    async def send_heartbeat(self):
        """Send Heartbeat to the central system."""
        request = call.Heartbeat()
        response = await self.call(request)
        print(f"✓ Heartbeat acknowledged, server time: {response.current_time}")
        return response

    async def send_status_notification(self, connector_id: int, status: str):
        """Send StatusNotification to the central system."""
        request = call.StatusNotification(
            connector_id=connector_id,
            error_code="NoError",
            status=status,
        )
        response = await self.call(request)
        print(f"✓ Status updated: Connector {connector_id} -> {status}")
        return response

    async def send_start_transaction(self, connector_id: int, id_tag: str):
        """Start a charging transaction."""
        request = call.StartTransaction(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=0,
            timestamp=datetime.now(UTC).isoformat(),
        )
        response = await self.call(request)
        print(f"✓ Transaction started: ID={response.transaction_id}")
        return response

    async def send_meter_values(self, connector_id: int, transaction_id: int):
        """Send meter values during charging."""
        request = call.MeterValues(
            connector_id=connector_id,
            transaction_id=transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "sampled_value": [
                        {
                            "value": "1500",
                            "context": "Sample.Periodic",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                        }
                    ],
                }
            ],
        )
        response = await self.call(request)
        print("✓ Meter values sent")
        return response

    async def send_stop_transaction(self, transaction_id: int, meter_stop: int):
        """Stop a charging transaction."""
        request = call.StopTransaction(
            transaction_id=transaction_id,
            meter_stop=meter_stop,
            timestamp=datetime.now(UTC).isoformat(),
        )
        response = await self.call(request)
        print(f"✓ Transaction stopped: ID={transaction_id}")
        return response


async def main():
    """Main test routine."""
    charge_point_id = "TEST_CP_001"
    server_url = "ws://localhost:9000"

    print(f"\n{'=' * 60}")
    print("Levity OCPP Test Client")
    print(f"{'=' * 60}")
    print(f"Charge Point ID: {charge_point_id}")
    print(f"Server URL: {server_url}/ws/{charge_point_id}")
    print(f"{'=' * 60}\n")

    async with websockets.connect(
        f"{server_url}/ws/{charge_point_id}",
        subprotocols=["ocpp1.6"],
    ) as ws:
        charge_point = TestChargePoint(charge_point_id, ws)

        # Start the ChargePoint in the background
        await asyncio.gather(
            charge_point.start(),
            simulate_charging_session(charge_point),
        )


async def simulate_charging_session(cp: TestChargePoint):
    """Simulate a complete charging session."""
    try:
        # Wait a moment for connection to establish
        await asyncio.sleep(0.5)

        print("\n1. Sending BootNotification...")
        await cp.send_boot_notification()

        await asyncio.sleep(1)

        print("\n2. Sending initial status notifications...")
        await cp.send_status_notification(0, ChargePointStatus.available)
        await cp.send_status_notification(1, ChargePointStatus.available)
        await cp.send_status_notification(2, ChargePointStatus.available)

        await asyncio.sleep(1)

        print("\n3. Sending heartbeat...")
        await cp.send_heartbeat()

        await asyncio.sleep(1)

        print("\n4. Starting transaction on connector 1...")
        await cp.send_status_notification(1, ChargePointStatus.preparing)
        tx_response = await cp.send_start_transaction(1, "RFID-USER-001")
        transaction_id = tx_response.transaction_id

        await asyncio.sleep(1)

        print("\n5. Charging...")
        await cp.send_status_notification(1, ChargePointStatus.charging)

        # Send some meter values during charging
        for _ in range(3):
            await asyncio.sleep(2)
            await cp.send_meter_values(1, transaction_id)

        await asyncio.sleep(1)

        print("\n6. Finishing transaction...")
        await cp.send_status_notification(1, ChargePointStatus.finishing)
        await cp.send_stop_transaction(transaction_id, meter_stop=4500)

        await asyncio.sleep(1)

        print("\n7. Returning to available...")
        await cp.send_status_notification(1, ChargePointStatus.available)

        await asyncio.sleep(1)

        print("\n8. Sending final heartbeat...")
        await cp.send_heartbeat()

        print(f"\n{'=' * 60}")
        print("✓ Test completed successfully!")
        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed: {e}")
