"""Main entry point for Levity OCPP Central System."""

import sys
from pathlib import Path

# Add src directory to Python path when running directly (not as installed package)
if __package__ is None:
    src_dir = Path(__file__).parent.parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

import argparse
import asyncio
import logging

from levity.database import Database
from levity.logging_utils import JSONFormatter, log_error
from levity.plugins import (
    AutoRemoteStartPlugin,
    FluentdAuditPlugin,
    FluentdWebSocketAuditPlugin,
    OrphanedTransactionPlugin,
    PrometheusMetricsPlugin,
)
from levity.server import OCPPServer


def setup_logging(level: str = "INFO"):
    """Configure JSON logging for the application."""
    json_formatter = JSONFormatter()

    # Create handlers
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)

    file_handler = logging.FileHandler("levity.log")
    file_handler.setFormatter(json_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.handlers = [console_handler, file_handler]

    # Suppress verbose logging from dependencies
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("ocpp").setLevel(logging.WARNING)


async def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="Levity - OCPP Central System with SQLite storage")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the WebSocket server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port to bind the WebSocket server (default: 9000)",
    )
    parser.add_argument(
        "--db",
        default="levity.db",
        help="Path to SQLite database file (default: levity.db)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=None,
        help="Port for Prometheus metrics HTTP server (default: disabled)",
    )
    parser.add_argument(
        "--enable-auto-start",
        action="store_true",
        help="Enable AutoRemoteStartPlugin to automatically start charging when cable is plugged in",
    )
    parser.add_argument(
        "--auto-start-id-tag",
        default="anonymous",
        help="ID tag to use for auto-start transactions (default: anonymous)",
    )
    parser.add_argument(
        "--auto-start-delay",
        type=float,
        default=1.0,
        help="Seconds to wait before sending RemoteStartTransaction (default: 1.0)",
    )
    parser.add_argument(
        "--disable-websocket-ping",
        action="store_true",
        help="Disable WebSocket ping/pong messages (useful for chargers that don't handle pings well)",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=60,
        help="OCPP heartbeat interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--fluentd-endpoint",
        default=None,
        help="Fluentd endpoint in host:port format (e.g., localhost:24224). If provided, enables Fluentd audit logging.",
    )
    parser.add_argument(
        "--fluentd-tag",
        default="ocpp",
        help="Tag prefix for Fluentd events (default: ocpp)",
    )

    args = parser.parse_args()

    # Parse Fluentd endpoint if provided
    fluentd_host = None
    fluentd_port = None
    if args.fluentd_endpoint:
        try:
            if ":" not in args.fluentd_endpoint:
                parser.error("--fluentd-endpoint must be in host:port format (e.g., localhost:24224)")
            fluentd_host, port_str = args.fluentd_endpoint.rsplit(":", 1)
            fluentd_port = int(port_str)
            if not fluentd_host:
                parser.error("--fluentd-endpoint host cannot be empty")
        except ValueError:
            parser.error(f"Invalid port in --fluentd-endpoint: {args.fluentd_endpoint}")

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # Log startup as structured event
    logger.info(
        "System starting",
        extra={
            "event_type": "system_startup",
            "event_data": {
                "database": args.db,
                "websocket_endpoint": f"ws://{args.host}:{args.port}/ws/{{cp_id}}",
                "metrics_endpoint": f"http://{args.host}:{args.metrics_port}/metrics"
                if args.metrics_port
                else None,
                "fluentd_enabled": args.fluentd_endpoint is not None,
                "fluentd_endpoint": args.fluentd_endpoint,
            },
        },
    )

    # Initialize database
    db = Database(args.db)

    # Create plugin factory - always include PrometheusMetricsPlugin if metrics_port is set
    # Also include OrphanedTransactionPlugin for cleanup
    def create_plugins():
        plugins = []

        # Always include PrometheusMetricsPlugin if metrics port is configured
        if args.metrics_port:
            plugins.append(PrometheusMetricsPlugin())

        # Include OrphanedTransactionPlugin for cleanup
        plugins.append(OrphanedTransactionPlugin())

        # Include AutoRemoteStartPlugin if enabled
        if args.enable_auto_start:
            plugins.append(
                AutoRemoteStartPlugin(
                    id_tag=args.auto_start_id_tag,
                    delay_seconds=args.auto_start_delay,
                )
            )

        # Include Fluentd plugins if enabled
        if args.fluentd_endpoint:
            plugins.extend(
                [
                    FluentdAuditPlugin(
                        tag_prefix=args.fluentd_tag,
                        host=fluentd_host,
                        port=fluentd_port,
                        timeout=3.0,
                    ),
                    FluentdWebSocketAuditPlugin(
                        tag_prefix=args.fluentd_tag,
                        host=fluentd_host,
                        port=fluentd_port,
                    ),
                ]
            )

        return plugins

    plugin_factory = create_plugins

    # Configure WebSocket ping interval (None disables pings)
    ping_interval = None if args.disable_websocket_ping else 20

    # Create and start server
    server = OCPPServer(
        db,
        host=args.host,
        port=args.port,
        metrics_port=args.metrics_port,
        plugin_factory=plugin_factory,
        ping_interval=ping_interval,
        heartbeat_interval=args.heartbeat_interval,
    )

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info(
            "System shutting down",
            extra={"event_type": "system_shutdown", "event_data": {"reason": "SIGINT"}},
        )
    except Exception as e:
        log_error(logger, "server_error", f"Server error: {e}", exc_info=e)
        raise
    finally:
        await server.stop()


def run():
    """Entry point for console script."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
