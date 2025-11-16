"""Domain models for the OCPP central system."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChargePoint:
    """Represents a charge point in the system."""

    id: str
    name: str = ""
    vendor: str = ""
    model: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    iccid: str = ""
    imsi: str = ""
    status: str = "Unknown"
    is_connected: bool = False
    last_heartbeat_at: datetime | None = None
    last_boot_at: datetime | None = None
    last_connect_at: datetime | None = None
    last_tx_start_at: datetime | None = None
    last_tx_stop_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Connector:
    """Represents a connector on a charge point."""

    id: int | None = None
    cp_id: str = ""
    conn_id: int = 0
    status: str = "Available"
    error_code: str = ""
    vendor_error_code: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Transaction:
    """Represents a charging transaction."""

    id: int | None = None
    tx_id: int | None = None
    cp_id: str = ""
    cp_conn_id: int = 0
    id_tag: str = ""
    start_time: datetime | None = None
    stop_time: datetime | None = None
    meter_start: int = 0
    meter_stop: int | None = None
    energy_delivered: int = 0
    stop_reason: str = ""
    status: str = "Active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class MeterValue:
    """Represents a meter value reading."""

    id: int | None = None
    tx_id: int | None = None
    cp_id: str = ""
    cp_conn_id: int = 0
    timestamp: datetime | None = None
    measurand: str = ""
    value: float = 0.0
    unit: str = "Wh"
    context: str = "Sample.Periodic"
    location: str = "Outlet"
    phase: str = ""
    format: str = "Raw"
    created_at: datetime | None = None
