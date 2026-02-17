"""Data models for FIFO command interface."""

import json
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class SelectorType(str, Enum):
    """Selector types for targeting charge points."""

    ALL = "all"
    IDS = "ids"
    IN_TRANSACTION = "in_transaction"
    NOT_IN_TRANSACTION = "not_in_transaction"


@dataclass
class Selector:
    """Selector for targeting charge points."""

    type: SelectorType
    value: list[str] | None = None  # Only used for type=ids

    @classmethod
    def from_dict(cls, data: dict) -> "Selector":
        """Create Selector from dict."""
        return cls(type=SelectorType(data.get("type", "all")), value=data.get("value"))


@dataclass
class OCPPCall:
    """OCPP call specification."""

    action: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict) -> "OCPPCall":
        """Create OCPPCall from dict."""
        return cls(action=data["action"], payload=data.get("payload", {}))


@dataclass
class Command:
    """Command to send OCPP call to charge points."""

    selector: Selector
    call: OCPPCall
    timeout: int = 30
    command_id: str | None = None

    def __post_init__(self):
        """Generate command_id if not provided."""
        if self.command_id is None:
            self.command_id = str(uuid.uuid4())

    @classmethod
    def from_json(cls, json_str: str) -> "Command":
        """Parse command from JSON string."""
        data = json.loads(json_str)
        return cls(
            selector=Selector.from_dict(data["selector"]),
            call=OCPPCall.from_dict(data["call"]),
            timeout=data.get("timeout", 30),
            command_id=data.get("command_id"),
        )


@dataclass
class CallResult:
    """Result of sending call to a single charge point."""

    cp_id: str
    status: str  # "success" or "error"
    response: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class CommandResponse:
    """Response to a command."""

    command_id: str
    status: str  # "completed"
    results: list[CallResult]
    summary: dict[str, int]  # {"total": N, "success": N, "error": N}

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "command_id": self.command_id,
            "status": self.status,
            "results": [asdict(r) for r in self.results],
            "summary": self.summary,
        }
        return json.dumps(data)

    @classmethod
    def from_results(cls, command_id: str, results: list[CallResult]) -> "CommandResponse":
        """Create response from results."""
        success_count = sum(1 for r in results if r.status == "success")
        error_count = sum(1 for r in results if r.status == "error")

        return cls(
            command_id=command_id,
            status="completed",
            results=results,
            summary={"total": len(results), "success": success_count, "error": error_count},
        )
