"""Main entry point for Levity OCPP Central System."""

import argparse
import asyncio
import logging
import sys

from .database import Database
from .server import OCPPServer


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
    parser = argparse.ArgumentParser(
        description="Levity - OCPP Central System with SQLite storage"
    )
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

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Starting Levity OCPP Central System")
    logger.info(f"Database: {args.db}")
    logger.info(f"WebSocket endpoint: ws://{args.host}:{args.port}/ws/{{cp_id}}")

    # Initialize database
    db = Database(args.db)

    # Create and start server
    server = OCPPServer(db, host=args.host, port=args.port)

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
