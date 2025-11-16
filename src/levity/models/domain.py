"""Domain models for the OCPP central system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    last_heartbeat_at: Optional[datetime] = None
    last_boot_at: Optional[datetime] = None
    last_connect_at: Optional[datetime] = None
    last_tx_start_at: Optional[datetime] = None
    last_tx_stop_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Connector:
    """Represents a connector on a charge point."""

    id: Optional[int] = None
    cp_id: str = ""
    conn_id: int = 0
    status: str = "Available"
    error_code: str = ""
    vendor_error_code: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Transaction:
    """Represents a charging transaction."""

    id: Optional[int] = None
    tx_id: Optional[int] = None
    cp_id: str = ""
    cp_conn_id: int = 0
    id_tag: str = ""
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    meter_start: int = 0
    meter_stop: Optional[int] = None
    energy_delivered: int = 0
    stop_reason: str = ""
    status: str = "Active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MeterValue:
    """Represents a meter value reading."""

    id: Optional[int] = None
    tx_id: Optional[int] = None
    cp_id: str = ""
    cp_conn_id: int = 0
    timestamp: Optional[datetime] = None
    measurand: str = ""
    value: float = 0.0
    unit: str = "Wh"
    context: str = "Sample.Periodic"
    location: str = "Outlet"
    phase: str = ""
    format: str = "Raw"
    created_at: Optional[datetime] = None
