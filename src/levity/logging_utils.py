"""Structured JSON logging utilities for event-based logging."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add event-specific fields if present
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        if hasattr(record, "event_data"):
            log_data.update(record.event_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def log_ocpp_message(
    logger: logging.Logger,
    direction: str,
    cp_id: str,
    message_type: str,
    message_id: str | None = None,
    action: str | None = None,
    payload: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """
    Log an OCPP message event.

    Args:
        logger: Logger instance
        direction: "received" or "sent"
        cp_id: Charge point ID
        message_type: "CALL", "CALLRESULT", "CALLERROR"
        message_id: OCPP message ID
        action: OCPP action name (e.g., "BootNotification")
        payload: Message payload
        **kwargs: Additional fields to include
    """
    event_data = {
        "direction": direction,
        "cp_id": cp_id,
        "message_type": message_type,
    }

    # Only include optional fields if they're not None
    if message_id is not None:
        event_data["message_id"] = message_id
    if action is not None:
        event_data["action"] = action
    if payload is not None:
        event_data["payload"] = payload

    # Filter out None values from kwargs
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    extra = {
        "event_type": "ocpp_message",
        "event_data": event_data,
    }

    logger.info(f"OCPP {direction}: {action or message_type}", extra=extra)


def log_websocket_event(
    logger: logging.Logger,
    event: str,
    cp_id: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Log a WebSocket event.

    Args:
        logger: Logger instance
        event: Event name (e.g., "connect", "disconnect", "error")
        cp_id: Charge point ID (if applicable)
        **kwargs: Additional fields to include
    """
    event_data = {
        "event": event,
    }

    # Only include cp_id if it's not None
    if cp_id is not None:
        event_data["cp_id"] = cp_id

    # Filter out None values from kwargs
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    extra = {
        "event_type": "websocket_event",
        "event_data": event_data,
    }
    logger.info(f"WebSocket {event}", extra=extra)


def log_error(
    logger: logging.Logger,
    error_type: str,
    message: str,
    cp_id: str | None = None,
    exc_info: Exception | None = None,
    **kwargs: Any,
) -> None:
    """
    Log an error event.

    Args:
        logger: Logger instance
        error_type: Type of error (e.g., "handler_error", "plugin_error")
        message: Error message
        cp_id: Charge point ID (if applicable)
        exc_info: Exception object (will extract traceback)
        **kwargs: Additional fields to include
    """
    event_data = {
        "error_type": error_type,
    }

    # Only include cp_id if it's not None
    if cp_id is not None:
        event_data["cp_id"] = cp_id

    # Filter out None values from kwargs
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    extra = {
        "event_type": "error",
        "event_data": event_data,
    }
    logger.error(message, extra=extra, exc_info=exc_info)
