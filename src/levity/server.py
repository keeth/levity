"""WebSocket server for OCPP central system."""

import asyncio
import contextlib
import logging
from collections.abc import Callable

import websockets
from aiohttp import web
from prometheus_client import generate_latest
from websockets.asyncio.server import ServerConnection

from .database import Database
from .handlers import LevityChargePoint
from .logging_utils import log_error, log_websocket_event
from .plugins.base import ChargePointPlugin
from .plugins.prometheus_metrics import PrometheusMetricsPlugin

logger = logging.getLogger("levity")


class OCPPServer:
    """
    OCPP WebSocket server that manages charge point connections.

    The server accepts connections at /ws/{charge_point_id} and creates
    a LevityChargePoint instance for each connection to handle OCPP messages.

    Supports a plugin system for extending charge point behavior.
    """

    def __init__(
        self,
        db: Database,
        host: str = "0.0.0.0",
        port: int = 9000,
        plugin_factory: Callable[[], list[ChargePointPlugin]] | None = None,
        metrics_port: int | None = None,
        ping_interval: float | None = 20,
        heartbeat_interval: int = 60,
        response_timeout: int = 30,
    ):
        self.db = db
        self.host = host
        self.port = port
        self.charge_points: dict[str, LevityChargePoint] = {}
        self.plugin_factory = plugin_factory or (list)
        self.metrics_port = metrics_port
        self.ping_interval = ping_interval
        self.heartbeat_interval = heartbeat_interval
        self.response_timeout = response_timeout
        self.metrics_app = None
        self.metrics_runner = None

    async def on_connect(self, connection: ServerConnection):
        """
        Handle new WebSocket connection.

        Extracts charge point ID from the URL path and creates a
        LevityChargePoint instance to handle OCPP messages.
        """
        charge_point_id = None
        charge_point = None

        try:
            # Extract charge point ID from path: /ws/{charge_point_id}
            path_parts = connection.request.path.strip("/").split("/")

            if len(path_parts) != 2 or path_parts[0] != "ws":
                log_error(
                    logger,
                    "websocket_error",
                    f"Invalid connection path: {connection.request.path}",
                    error_code="INVALID_PATH",
                )
                await connection.close(1002, "Invalid path format")
                return

            charge_point_id = path_parts[1]

            if not charge_point_id:
                log_error(
                    logger,
                    "websocket_error",
                    "Empty charge point ID in connection path",
                    error_code="MISSING_CP_ID",
                )
                await connection.close(1002, "Missing charge point ID")
                return

            # Get remote address from connection
            remote_address = None
            try:
                addr = connection.remote_address
                if addr:
                    remote_address = f"{addr[0]}:{addr[1]}" if len(addr) >= 2 else str(addr)
            except Exception:
                pass

            log_websocket_event(
                logger, "connect", cp_id=charge_point_id, remote_address=remote_address
            )

            # Check for existing connection and close it (handles reconnects)
            existing_cp = self.charge_points.get(charge_point_id)
            if existing_cp:
                old_addr = existing_cp.remote_address
                log_websocket_event(
                    logger,
                    "duplicate_connection",
                    cp_id=charge_point_id,
                    remote_address=remote_address,
                    old_remote_address=old_addr,
                )
                with contextlib.suppress(Exception):
                    await existing_cp._connection.close(1000, "Replaced by new connection")
                # Don't delete from dict here - let the old handler's finally block handle it
                # (but it won't clobber us because of the identity check below)

            # Get database connection
            db_conn = await self.db.connect()

            # Create plugins for this charge point
            plugins = self.plugin_factory()

            # Create ChargePoint instance with plugins
            charge_point = LevityChargePoint(
                charge_point_id,
                connection,
                db_conn,
                plugins,
                heartbeat_interval=self.heartbeat_interval,
                response_timeout=self.response_timeout,
                remote_address=remote_address,
            )
            self.charge_points[charge_point_id] = charge_point

            # Initialize plugins
            for plugin in plugins:
                try:
                    await plugin.initialize(charge_point)
                except Exception as e:
                    log_error(
                        logger,
                        "plugin_initialization_error",
                        f"Failed to initialize plugin {plugin.__class__.__name__} for CP {charge_point_id}: {e}",
                        cp_id=charge_point_id,
                        plugin=plugin.__class__.__name__,
                        exc_info=e,
                    )

            # Get current timestamp from database
            cursor = await charge_point.cp_repo.conn.execute("SELECT datetime('now')")
            row = await cursor.fetchone()
            current_time = row[0] if row else None

            # Update connection status in database
            await charge_point.cp_repo.update_connection_status(
                charge_point_id,
                True,
                current_time,
            )

            # Start listening for messages
            await charge_point.start()

        except websockets.exceptions.ConnectionClosed:
            # Reason will be logged in finally block
            disconnect_reason = "connection_closed"
        except Exception as e:
            log_error(
                logger,
                "websocket_error",
                f"Error handling charge point {charge_point_id}: {e}",
                cp_id=charge_point_id,
                exc_info=e,
            )
            disconnect_reason = "error"
            # Try to close the connection gracefully
            try:
                if connection.open:
                    await connection.close(1011, "Internal server error")
            except Exception:
                pass
        else:
            # Normal exit (shouldn't happen as start() runs forever)
            disconnect_reason = "normal"
        finally:
            # Clean up on disconnect
            if charge_point:
                try:
                    await charge_point.on_disconnect()
                except Exception as e:
                    log_error(
                        logger,
                        "disconnect_cleanup_error",
                        f"Error during disconnect cleanup for {charge_point_id}: {e}",
                        cp_id=charge_point_id,
                        exc_info=e,
                    )
            # Only remove from dict if THIS connection is still the registered one
            # (prevents old connection cleanup from clobbering a newer connection)
            if charge_point_id and self.charge_points.get(charge_point_id) is charge_point:
                del self.charge_points[charge_point_id]
            if charge_point_id:
                log_websocket_event(
                    logger,
                    "disconnect",
                    cp_id=charge_point_id,
                    remote_address=remote_address if "remote_address" in dir() else None,
                    reason=disconnect_reason if "disconnect_reason" in dir() else None,
                )

    async def metrics_handler(self, request):
        """Handle /metrics endpoint for Prometheus."""
        metrics = generate_latest()
        return web.Response(body=metrics, content_type="text/plain")

    async def start_metrics_server(self):
        """Start the HTTP server for Prometheus metrics."""
        if self.metrics_port is None:
            return

        self.metrics_app = web.Application()
        self.metrics_app.router.add_get("/metrics", self.metrics_handler)

        self.metrics_runner = web.AppRunner(self.metrics_app)
        await self.metrics_runner.setup()

        site = web.TCPSite(self.metrics_runner, self.host, self.metrics_port)
        await site.start()

    async def stop_metrics_server(self):
        """Stop the metrics HTTP server."""
        if self.metrics_runner:
            await self.metrics_runner.cleanup()

    def select_subprotocol(self, connection, subprotocols):
        """
        Select subprotocol during WebSocket handshake.

        Defaults to 'ocpp1.6' if client doesn't send any subprotocols.
        This allows chargers that don't send subprotocol headers to connect.

        Args:
            connection: ServerConnection object (websockets 15.x signature)
            subprotocols: List of subprotocols offered by the client (may be empty)
        """
        try:
            # Handle case where client doesn't send any subprotocols
            if not subprotocols:
                return "ocpp1.6"

            # If client sent subprotocols, check if ocpp1.6 is supported
            if "ocpp1.6" in subprotocols:
                return "ocpp1.6"

            # Client sent subprotocols but not ocpp1.6 - default anyway
            log_error(
                logger,
                "websocket_error",
                f"Client sent subprotocols {subprotocols} but ocpp1.6 not found. Defaulting to ocpp1.6 anyway.",
                error_code="UNSUPPORTED_SUBPROTOCOL",
            )
            return "ocpp1.6"
        except Exception as e:
            log_error(logger, "websocket_error", f"Error in select_subprotocol: {e}", exc_info=e)
            # Default to ocpp1.6 on error
            return "ocpp1.6"

    async def start(self):
        """
        Start the WebSocket server.

        Initializes the database schema and starts listening for connections.
        """
        # Initialize database
        await self.db.initialize_schema()

        # Initialize Prometheus metrics if metrics port is configured
        # This sets ocpp_central_up = 1 even before any charge points connect
        if self.metrics_port:
            PrometheusMetricsPlugin().ocpp_central_up.set(1)

        # Start metrics server if configured
        await self.start_metrics_server()

        # Start WebSocket server
        async with websockets.serve(
            self.on_connect,
            self.host,
            self.port,
            subprotocols=["ocpp1.6"],
            select_subprotocol=self.select_subprotocol,
            ping_interval=self.ping_interval,
        ):
            log_websocket_event(
                logger,
                "server_started",
                host=self.host,
                port=self.port,
            )
            await asyncio.Future()  # Run forever

    async def stop(self):
        """Stop the server and cleanup resources."""
        # Stop metrics server
        await self.stop_metrics_server()

        # Disconnect all charge points
        for cp_id, cp in list(self.charge_points.items()):
            try:
                await cp.on_disconnect()
            except Exception as e:
                log_error(
                    logger,
                    "disconnect_error",
                    f"Error disconnecting charge point {cp_id}: {e}",
                    cp_id=cp_id,
                    exc_info=e,
                )

        self.charge_points.clear()

        # Close database connection
        await self.db.disconnect()

        log_websocket_event(logger, "server_stopped")
