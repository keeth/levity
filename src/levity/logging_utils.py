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
        **kwargs: Additional fields to include (remote_address, etc.)
    """
    # Convert direction to short form matching Fluentd format
    dir_short = "recv" if direction == "received" else "send"

    # Build msg dict with message details
    msg: dict[str, Any] = {"message_type": message_type}
    if message_id is not None:
        msg["message_id"] = message_id
    if action is not None:
        msg["action"] = action
    if payload is not None:
        msg["payload"] = payload

    # Add error details if present in kwargs
    for key in ["error_code", "error_description", "error_details"]:
        if key in kwargs and kwargs[key] is not None:
            msg[key] = kwargs.pop(key)

    # Use Fluentd-style keys
    event_data: dict[str, Any] = {
        "type": "ocpp",
        "cp": cp_id,
        "dir": dir_short,
        "msg": msg,
    }

    # Filter out None values from remaining kwargs (remote_address, etc.)
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    logger.info(f"OCPP[{cp_id}] {dir_short.upper()} {action or message_type} {message_id or '-'}", extra={"event_data": event_data})


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
        **kwargs: Additional fields to include (remote_address, reason, etc.)
    """
    # Use Fluentd-style keys
    event_data: dict[str, Any] = {
        "type": "ws",
        "event": event,
    }

    # Only include cp if it's not None
    if cp_id is not None:
        event_data["cp"] = cp_id

    # Filter out None values from kwargs
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    logger.info(f"WS[{cp_id}] {event.upper()}", extra={"event_data": event_data})


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
    # Use Fluentd-style keys
    event_data: dict[str, Any] = {
        "type": "error",
        "error_type": error_type,
    }

    # Only include cp if it's not None
    if cp_id is not None:
        event_data["cp"] = cp_id

    # Filter out None values from kwargs
    for key, value in kwargs.items():
        if value is not None:
            event_data[key] = value

    logger.error(message, extra={"event_data": event_data}, exc_info=exc_info)
