"""Example OCPP server with Prometheus metrics enabled."""

import asyncio
import logging
import os

from levity.database import Database
from levity.plugins import PrometheusMetricsPlugin
from levity.server import OCPPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def create_plugins():
    """Factory function to create plugins for each charge point connection."""
    return [
        PrometheusMetricsPlugin(),
    ]


async def main():
    """Run the OCPP server with Prometheus metrics."""
    # Configuration
    db_path = os.getenv("DATABASE_PATH", "levity.db")
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "9000"))
    metrics_port = int(os.getenv("METRICS_PORT", "9090"))

    logger.info("Starting OCPP Central System with Prometheus metrics")
    logger.info(f"Database: {db_path}")
    logger.info(f"WebSocket server: ws://{host}:{port}/ws/{{cp_id}}")
    logger.info(f"Metrics endpoint: http://{host}:{metrics_port}/metrics")

    # Create database
    db = Database(db_path)

    # Create server with Prometheus metrics
    server = OCPPServer(
        db=db,
        host=host,
        port=port,
        plugin_factory=create_plugins,
        metrics_port=metrics_port,
    )

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
