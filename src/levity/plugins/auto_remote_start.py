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
        hooks = {
            PluginHook.AFTER_STATUS_NOTIFICATION: "on_status_change",
        }
        self.logger.debug(
            f"AutoRemoteStartPlugin.hooks() returning {len(hooks)} hook(s): {list(hooks.keys())}"
        )
        return hooks

    async def on_status_change(self, context: PluginContext):
        """
        Handle status notification changes.

        If a connector enters Preparing state, trigger remote start after delay.
        """
        connector_id = context.message_data.get("connector_id")
        status = context.message_data.get("status")

        self.logger.debug(
            f"AutoRemoteStartPlugin.on_status_change called for CP {context.charge_point.id}, "
            f"connector_id={connector_id}, status={status} (type: {type(status).__name__})"
        )

        # Only act on connector-level status (not charge point itself)
        if connector_id == 0:
            self.logger.debug(
                f"Ignoring charge point-level status (connector_id=0) for CP {context.charge_point.id}"
            )
            return

        # Check if connector is entering Preparing state
        # Normalize status to string for comparison (handles both string and enum inputs)
        status_str = status if isinstance(status, str) else status.value
        preparing_value = ChargePointStatus.preparing.value

        self.logger.debug(
            f"Comparing status '{status_str}' (normalized from {status}) "
            f"to '{preparing_value}' for connector {connector_id}"
        )

        if status_str != preparing_value:
            self.logger.debug(
                f"Status '{status_str}' does not match Preparing state for connector {connector_id}, "
                f"skipping RemoteStartTransaction"
            )
            return

        self.logger.info(
            f"Connector {connector_id} on {context.charge_point.id} entered Preparing state. "
            f"Will send RemoteStartTransaction in {self.delay_seconds}s"
        )

        # Wait before sending remote start
        await asyncio.sleep(self.delay_seconds)

        # Send RemoteStartTransaction
        try:
            request = call.RemoteStartTransaction(
                connector_id=connector_id,
                id_tag=self.id_tag,
            )

            self.logger.info(
                f"Sending RemoteStartTransaction to {context.charge_point.id} "
                f"connector {connector_id} with tag {self.id_tag}"
            )

            response = await context.charge_point.call(request)

            if response.status == "Accepted":
                self.logger.info(
                    f"RemoteStartTransaction accepted for {context.charge_point.id} "
                    f"connector {connector_id}"
                )
            else:
                self.logger.warning(
                    f"RemoteStartTransaction rejected for {context.charge_point.id} "
                    f"connector {connector_id}: {response.status}"
                )

        except Exception as e:
            self.logger.error(
                f"Failed to send RemoteStartTransaction to {context.charge_point.id}: {e}",
                exc_info=True,
            )
