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
from levity.plugins import AutoRemoteStartPlugin, OrphanedTransactionPlugin
from levity.server import OCPPServer


def setup_logging(level: str = "INFO"):
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("levity.log"),
        ],
    )


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

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Starting Levity OCPP Central System")
    logger.info(f"Database: {args.db}")
    logger.info(f"WebSocket endpoint: ws://{args.host}:{args.port}/ws/{{cp_id}}")
    if args.metrics_port:
        logger.info(f"Metrics endpoint: http://{args.host}:{args.metrics_port}/metrics")

    # Initialize database
    db = Database(args.db)

    # Create plugin factory if auto-start is enabled
    plugin_factory = None
    if args.enable_auto_start:
        def create_plugins():
            return [
                AutoRemoteStartPlugin(
                    id_tag=args.auto_start_id_tag,
                    delay_seconds=args.auto_start_delay,
                ),
                OrphanedTransactionPlugin(),
            ]
        plugin_factory = create_plugins
        logger.info(
            f"AutoRemoteStartPlugin enabled: id_tag={args.auto_start_id_tag}, "
            f"delay={args.auto_start_delay}s"
        )

    # Create and start server
    server = OCPPServer(
        db,
        host=args.host,
        port=args.port,
        metrics_port=args.metrics_port,
        plugin_factory=plugin_factory,
    )

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
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
