"""Plugin to automatically start charging when a connector enters Preparing state."""

import asyncio

from ocpp.v16 import call
from ocpp.v16.enums import ChargePointStatus

from .base import ChargePointPlugin, PluginContext, PluginHook


class AutoRemoteStartPlugin(ChargePointPlugin):
    """
    Automatically sends RemoteStartTransaction when a connector enters Preparing state.

    This plugin monitors StatusNotification messages. When a connector transitions
    to the "Preparing" state (typically when a cable is plugged in but no RFID
    authorization has occurred), it waits 1 second then sends a RemoteStartTransaction
    request to the charge point with an anonymous ID tag.

    Use case: Enables automatic charging without requiring RFID authentication.
    """

    def __init__(self, id_tag: str = "anonymous", delay_seconds: float = 1.0):
        """
        Initialize the auto remote start plugin.

        Args:
            id_tag: The ID tag to use for anonymous charging (default: "anonymous")
            delay_seconds: Seconds to wait before sending RemoteStartTransaction (default: 1.0)
        """
        super().__init__()
        self.id_tag = id_tag
        self.delay_seconds = delay_seconds

    def hooks(self) -> dict[PluginHook, str]:
        """Register hook to monitor status notifications."""
        return {
            PluginHook.AFTER_STATUS_NOTIFICATION: "on_status_change",
        }

    async def on_status_change(self, context: PluginContext):
        """
        Handle status notification changes.

        If a connector enters Preparing state, trigger remote start after delay.
        """
        connector_id = context.message_data.get("connector_id")
        status = context.message_data.get("status")

        # Only act on connector-level status (not charge point itself)
        if connector_id == 0:
            return

        # Check if connector is entering Preparing state
        # Normalize status to string for comparison (handles both string and enum inputs)
        status_str = status if isinstance(status, str) else status.value
        preparing_value = ChargePointStatus.preparing.value

        if status_str != preparing_value:
            return

        # Wait before sending remote start
        await asyncio.sleep(self.delay_seconds)

        # Send RemoteStartTransaction
        try:
            request = call.RemoteStartTransaction(
                connector_id=connector_id,
                id_tag=self.id_tag,
            )

            response = await context.charge_point.call(request)

            if response.status != "Accepted":
                self.logger.warning(
                    f"RemoteStartTransaction rejected for {context.charge_point.id} "
                    f"connector {connector_id}: {response.status}"
                )

        except Exception as e:
            self.logger.error(
                f"Failed to send RemoteStartTransaction to {context.charge_point.id}: {e}",
                exc_info=True,
            )
