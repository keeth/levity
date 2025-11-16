"""
Example OCPP server with plugins enabled.

This demonstrates how to use the plugin framework with:
1. AutoRemoteStartPlugin - automatically starts charging when cable is plugged in
2. OrphanedTransactionPlugin - automatically closes unclosed transactions
"""

import asyncio
import logging

from levity.database import Database
from levity.plugins import AutoRemoteStartPlugin, OrphanedTransactionPlugin
from levity.server import OCPPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def create_plugins():
    """
    Factory function that creates plugin instances for each charge point.

    This function is called once per charge point connection, so each
    charge point gets its own set of plugin instances.
    """
    return [
        # Auto-start charging when cable is plugged in (Preparing state)
        AutoRemoteStartPlugin(
            id_tag="anonymous",  # Use "anonymous" ID tag
            delay_seconds=1.0,  # Wait 1 second before sending RemoteStartTransaction
        ),
        # Clean up orphaned transactions when a new transaction starts
        OrphanedTransactionPlugin(),
    ]


async def main():
    """Start the OCPP server with plugins enabled."""
    # Initialize database
    db = Database("levity.db")

    # Create server with plugin factory
    server = OCPPServer(
        db=db,
        host="0.0.0.0",
        port=9000,
        plugin_factory=create_plugins,  # Pass the factory function
    )

    # Start server
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
