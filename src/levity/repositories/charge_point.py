"""Repository for charge point operations."""

from datetime import datetime

from ..models import ChargePoint
from .base import BaseRepository


class ChargePointRepository(BaseRepository):
    """Handles database operations for charge points."""

    async def upsert(self, cp: ChargePoint) -> ChargePoint:
        """Insert or update a charge point."""
        query = """
            INSERT INTO cp (
                id, name, vendor, model, serial_number, firmware_version,
                iccid, imsi, status, is_connected, last_heartbeat_at,
                last_boot_at, last_connect_at, last_tx_start_at, last_tx_stop_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = COALESCE(excluded.name, name),
                vendor = COALESCE(excluded.vendor, vendor),
                model = COALESCE(excluded.model, model),
                serial_number = COALESCE(excluded.serial_number, serial_number),
                firmware_version = COALESCE(excluded.firmware_version, firmware_version),
                iccid = COALESCE(excluded.iccid, iccid),
                imsi = COALESCE(excluded.imsi, imsi),
                status = COALESCE(excluded.status, status),
                is_connected = excluded.is_connected,
                last_heartbeat_at = COALESCE(excluded.last_heartbeat_at, last_heartbeat_at),
                last_boot_at = COALESCE(excluded.last_boot_at, last_boot_at),
                last_connect_at = COALESCE(excluded.last_connect_at, last_connect_at),
                last_tx_start_at = COALESCE(excluded.last_tx_start_at, last_tx_start_at),
                last_tx_stop_at = COALESCE(excluded.last_tx_stop_at, last_tx_stop_at),
                updated_at = CURRENT_TIMESTAMP
        """

        await self._execute(
            query,
            (
                cp.id,
                cp.name,
                cp.vendor,
                cp.model,
                cp.serial_number,
                cp.firmware_version,
                cp.iccid,
                cp.imsi,
                cp.status,
                1 if cp.is_connected else 0,
                cp.last_heartbeat_at,
                cp.last_boot_at,
                cp.last_connect_at,
                cp.last_tx_start_at,
                cp.last_tx_stop_at,
            ),
        )

        return await self.get_by_id(cp.id)

    async def get_by_id(self, cp_id: str) -> ChargePoint | None:
        """Get charge point by ID."""
        row = await self._fetchone("SELECT * FROM cp WHERE id = ?", (cp_id,))
        if row:
            return self._row_to_model(row)
        return None

    async def get_all(self) -> list[ChargePoint]:
        """Get all charge points."""
        rows = await self._fetchall("SELECT * FROM cp ORDER BY created_at DESC")
        return [self._row_to_model(row) for row in rows]

    async def update_connection_status(
        self, cp_id: str, is_connected: bool, connect_time: datetime | None = None
    ):
        """Update charge point connection status."""
        query = """
            UPDATE cp
            SET is_connected = ?,
                last_connect_at = COALESCE(?, last_connect_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        await self._execute(query, (1 if is_connected else 0, connect_time, cp_id))

    async def update_heartbeat(self, cp_id: str, heartbeat_time: datetime):
        """Update last heartbeat timestamp."""
        query = """
            UPDATE cp
            SET last_heartbeat_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        await self._execute(query, (heartbeat_time, cp_id))

    async def update_status(self, cp_id: str, status: str):
        """Update charge point status."""
        query = """
            UPDATE cp
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        await self._execute(query, (status, cp_id))

    def _row_to_model(self, row) -> ChargePoint:
        """Convert database row to ChargePoint model."""
        return ChargePoint(
            id=row["id"],
            name=row["name"],
            vendor=row["vendor"],
            model=row["model"],
            serial_number=row["serial_number"],
            firmware_version=row["firmware_version"],
            iccid=row["iccid"],
            imsi=row["imsi"],
            status=row["status"],
            is_connected=bool(row["is_connected"]),
            last_heartbeat_at=row["last_heartbeat_at"],
            last_boot_at=row["last_boot_at"],
            last_connect_at=row["last_connect_at"],
            last_tx_start_at=row["last_tx_start_at"],
            last_tx_stop_at=row["last_tx_stop_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
