"""Plugin to automatically start charging when a connector enters Preparing state."""

import asyncio

from ocpp.v16 import call
from ocpp.v16.enums import ChargePointStatus

from .base import ChargePointPlugin, PluginContext, PluginHook
from .prometheus_metrics import PrometheusMetricsPlugin


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
        """Register hook to monitor status notifications (after response is sent)."""
        return {
            PluginHook.AFTER_STATUS_NOTIFICATION: "on_status_change",
        }

    async def on_status_change(self, context: PluginContext):
        """
        Handle status notification changes.

        This hook runs AFTER the StatusNotification response has been sent to the
        charge point, allowing us to safely send commands back without blocking
        the response.

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
        cp_id = context.charge_point.id
        try:
            request = call.RemoteStartTransaction(
                connector_id=connector_id,
                id_tag=self.id_tag,
            )

            response = await context.charge_point.call(request)

            if response.status != "Accepted":
                self.logger.warning(
                    f"RemoteStartTransaction rejected for {cp_id} "
                    f"connector {connector_id}: {response.status}"
                )
                PrometheusMetricsPlugin.record_call_rejected(
                    cp_id=cp_id,
                    action="RemoteStartTransaction",
                    status=response.status,
                )

        except TimeoutError as e:
            self.logger.error(
                f"Timeout sending RemoteStartTransaction to {cp_id}: {e}",
                exc_info=True,
            )
            PrometheusMetricsPlugin.record_call_error(
                cp_id=cp_id,
                action="RemoteStartTransaction",
                error_type="timeout",
            )

        except Exception as e:
            self.logger.error(
                f"Failed to send RemoteStartTransaction to {cp_id}: {e}",
                exc_info=True,
            )
            PrometheusMetricsPlugin.record_call_error(
                cp_id=cp_id,
                action="RemoteStartTransaction",
                error_type=type(e).__name__,
            )
