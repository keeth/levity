"""WebSocket server for OCPP central system."""

import asyncio
import logging
from typing import Optional

import websockets
from websockets.asyncio.server import ServerConnection

from .database import Database
from .handlers import LevityChargePoint

logger = logging.getLogger(__name__)


class OCPPServer:
    """
    OCPP WebSocket server that manages charge point connections.

    The server accepts connections at /ws/{charge_point_id} and creates
    a LevityChargePoint instance for each connection to handle OCPP messages.
    """

    def __init__(self, db: Database, host: str = "0.0.0.0", port: int = 9000):
        self.db = db
        self.host = host
        self.port = port
        self.charge_points: dict[str, LevityChargePoint] = {}

    async def on_connect(self, connection: ServerConnection):
        """
        Handle new WebSocket connection.

        Extracts charge point ID from the URL path and creates a
        LevityChargePoint instance to handle OCPP messages.
        """
        # Extract charge point ID from path: /ws/{charge_point_id}
        path_parts = connection.request.path.strip("/").split("/")

        if len(path_parts) != 2 or path_parts[0] != "ws":
            logger.warning(
                f"Invalid connection path: {connection.request.path}. "
                "Expected format: /ws/{{charge_point_id}}"
            )
            await connection.close(1002, "Invalid path format")
            return

        charge_point_id = path_parts[1]

        if not charge_point_id:
            logger.warning("Empty charge point ID in connection path")
            await connection.close(1002, "Missing charge point ID")
            return

        logger.info(f"Charge point {charge_point_id} connecting...")

        # Get database connection
        db_conn = await self.db.connect()

        # Create ChargePoint instance
        charge_point = LevityChargePoint(charge_point_id, connection, db_conn)
        self.charge_points[charge_point_id] = charge_point

        try:
            # Update connection status in database
            await charge_point.cp_repo.update_connection_status(
                charge_point_id, True, charge_point.cp_repo.conn.execute(
                    "SELECT datetime('now')"
                ).fetchone()[0]
            )

            logger.info(f"Charge point {charge_point_id} connected")

            # Start listening for messages
            await charge_point.start()

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Charge point {charge_point_id} connection closed")
        except Exception as e:
            logger.error(f"Error handling charge point {charge_point_id}: {e}", exc_info=True)
        finally:
            # Clean up on disconnect
            await charge_point.on_disconnect()
            if charge_point_id in self.charge_points:
                del self.charge_points[charge_point_id]
            logger.info(f"Charge point {charge_point_id} disconnected")

    async def start(self):
        """
        Start the WebSocket server.

        Initializes the database schema and starts listening for connections.
        """
        logger.info(f"Starting OCPP server on {self.host}:{self.port}")

        # Initialize database
        await self.db.initialize_schema()

        # Start WebSocket server
        async with websockets.serve(
            self.on_connect,
            self.host,
            self.port,
            subprotocols=["ocpp1.6"],
        ) as server:
            logger.info(f"OCPP server listening on ws://{self.host}:{self.port}/ws/{{cp_id}}")
            await asyncio.Future()  # Run forever

    async def stop(self):
        """Stop the server and cleanup resources."""
        logger.info("Stopping OCPP server")

        # Disconnect all charge points
        for cp_id, cp in list(self.charge_points.items()):
            try:
                await cp.on_disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting charge point {cp_id}: {e}")

        self.charge_points.clear()

        # Close database connection
        await self.db.disconnect()

        logger.info("OCPP server stopped")
