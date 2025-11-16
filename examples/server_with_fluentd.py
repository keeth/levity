"""
Example OCPP server with Fluentd audit logging enabled.

This demonstrates how to configure structured audit logging to Fluentd
for all OCPP events and WebSocket connections.

Setup:
1. Install and run Fluentd:
   docker run -p 24224:24224 -p 24224:24224/udp fluent/fluentd

2. Or configure local Fluentd with this config:
   <source>
     @type forward
     port 24224
   </source>

   <match ocpp.**>
     @type stdout
   </match>

3. Run this server
"""

import asyncio
import logging
import os

from levity.database import Database
from levity.plugins import (
    AutoRemoteStartPlugin,
    FluentdAuditPlugin,
    FluentdWebSocketAuditPlugin,
    OrphanedTransactionPlugin,
)
from levity.server import OCPPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def create_plugins():
    """
    Factory function that creates plugin instances for each charge point.

    Configuration via environment variables:
    - FLUENTD_ENABLED: Set to "true" to enable Fluentd logging (default: false)
    - FLUENTD_HOST: Fluentd server hostname (default: localhost)
    - FLUENTD_PORT: Fluentd server port (default: 24224)
    - FLUENTD_TAG: Tag prefix for Fluentd events (default: ocpp)
    """
    plugins = [
        # Auto-start charging when cable is plugged in
        AutoRemoteStartPlugin(id_tag="anonymous", delay_seconds=1.0),
        # Clean up orphaned transactions
        OrphanedTransactionPlugin(),
    ]

    # Add Fluentd logging if enabled
    fluentd_enabled = os.getenv("FLUENTD_ENABLED", "false").lower() == "true"

    if fluentd_enabled:
        fluentd_host = os.getenv("FLUENTD_HOST", "localhost")
        fluentd_port = int(os.getenv("FLUENTD_PORT", "24224"))
        fluentd_tag = os.getenv("FLUENTD_TAG", "ocpp")

        logging.info(
            f"Fluentd audit logging enabled: {fluentd_host}:{fluentd_port} (tag: {fluentd_tag})"
        )

        plugins.extend(
            [
                # Log all OCPP messages
                FluentdAuditPlugin(
                    tag_prefix=fluentd_tag,
                    host=fluentd_host,
                    port=fluentd_port,
                    timeout=3.0,
                ),
                # Log WebSocket connections/disconnections
                FluentdWebSocketAuditPlugin(
                    tag_prefix=fluentd_tag,
                    host=fluentd_host,
                    port=fluentd_port,
                ),
            ]
        )
    else:
        logging.info("Fluentd audit logging disabled (set FLUENTD_ENABLED=true to enable)")

    return plugins


async def main():
    """Start the OCPP server with optional Fluentd logging."""
    # Initialize database
    db = Database("levity.db")

    # Create server with plugin factory
    server = OCPPServer(
        db=db,
        host="0.0.0.0",
        port=9000,
        plugin_factory=create_plugins,
    )

    # Start server
    await server.start()


if __name__ == "__main__":
    print("=" * 70)
    print("OCPP Server with Fluentd Audit Logging")
    print("=" * 70)
    print()
    print("Environment Variables:")
    print(f"  FLUENTD_ENABLED={os.getenv('FLUENTD_ENABLED', 'false')}")
    print(f"  FLUENTD_HOST={os.getenv('FLUENTD_HOST', 'localhost')}")
    print(f"  FLUENTD_PORT={os.getenv('FLUENTD_PORT', '24224')}")
    print(f"  FLUENTD_TAG={os.getenv('FLUENTD_TAG', 'ocpp')}")
    print()
    print("To enable Fluentd logging:")
    print("  export FLUENTD_ENABLED=true")
    print()
    print("Starting server...")
    print("=" * 70)
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
