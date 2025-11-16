"""Base plugin infrastructure for LevityChargePoint."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..handlers.charge_point import LevityChargePoint

logger = logging.getLogger(__name__)


class PluginHook(str, Enum):
    """
    Available plugin hooks in the charge point lifecycle.

    Hooks are called at specific points during message processing:
    - BEFORE_*: Called before the standard handler processes the message
    - AFTER_*: Called after the standard handler completes successfully
    """

    # Boot notification hooks
    BEFORE_BOOT_NOTIFICATION = "before_boot_notification"
    AFTER_BOOT_NOTIFICATION = "after_boot_notification"

    # Status notification hooks
    BEFORE_STATUS_NOTIFICATION = "before_status_notification"
    AFTER_STATUS_NOTIFICATION = "after_status_notification"

    # Transaction hooks
    BEFORE_START_TRANSACTION = "before_start_transaction"
    AFTER_START_TRANSACTION = "after_start_transaction"
    BEFORE_STOP_TRANSACTION = "before_stop_transaction"
    AFTER_STOP_TRANSACTION = "after_stop_transaction"

    # Heartbeat hooks
    BEFORE_HEARTBEAT = "before_heartbeat"
    AFTER_HEARTBEAT = "after_heartbeat"

    # Meter values hooks
    BEFORE_METER_VALUES = "before_meter_values"
    AFTER_METER_VALUES = "after_meter_values"

    # Authorization hooks
    BEFORE_AUTHORIZE = "before_authorize"
    AFTER_AUTHORIZE = "after_authorize"


@dataclass
class PluginContext:
    """
    Context provided to plugin hooks.

    Contains:
    - charge_point: Reference to the LevityChargePoint instance
    - message_data: The parsed OCPP message data (kwargs from handler)
    - result: The result from the handler (only available in AFTER hooks)
    """

    charge_point: "LevityChargePoint"
    message_data: dict[str, Any]
    result: Any = None


class ChargePointPlugin(ABC):
    """
    Base class for LevityChargePoint plugins.

    Plugins can register hooks to execute custom logic at various points
    in the OCPP message processing lifecycle.

    To create a plugin:
    1. Subclass ChargePointPlugin
    2. Implement the `hooks()` method to register your hook handlers
    3. Implement async methods for each hook you want to handle

    Example:
        class MyPlugin(ChargePointPlugin):
            def hooks(self) -> dict[PluginHook, str]:
                return {
                    PluginHook.AFTER_BOOT_NOTIFICATION: "on_boot_complete"
                }

            async def on_boot_complete(self, context: PluginContext):
                logger.info(f"Charge point {context.charge_point.id} booted!")
    """

    def __init__(self):
        """Initialize the plugin."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def hooks(self) -> dict[PluginHook, str]:
        """
        Return a mapping of hooks to handler method names.

        Returns:
            Dictionary mapping PluginHook enum values to method names on this class.
        """

    async def initialize(self, charge_point: "LevityChargePoint"):
        """
        Called once when the plugin is registered with a charge point.

        Override this to perform any initialization logic.

        Args:
            charge_point: The charge point instance this plugin is attached to
        """
        # Default implementation does nothing
        _ = charge_point  # Suppress unused argument warning

    async def cleanup(self, charge_point: "LevityChargePoint"):
        """
        Called when the charge point disconnects or the plugin is removed.

        Override this to perform any cleanup logic.

        Args:
            charge_point: The charge point instance this plugin is attached to
        """
        # Default implementation does nothing
        _ = charge_point  # Suppress unused argument warning
