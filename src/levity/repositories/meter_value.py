"""Repository for meter value operations."""

from ..models import MeterValue
from .base import BaseRepository


class MeterValueRepository(BaseRepository):
    """Handles database operations for meter values."""

    async def create(self, meter_value: MeterValue) -> MeterValue:
        """Create a new meter value record."""
        query = """
            INSERT INTO meter_val (
                tx_id, cp_id, cp_conn_id, timestamp, measurand, value,
                unit, context, location, phase, format
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """

        cursor = await self._execute(
            query,
            (
                meter_value.tx_id,
                meter_value.cp_id,
                meter_value.cp_conn_id,
                meter_value.timestamp,
                meter_value.measurand,
                meter_value.value,
                meter_value.unit,
                meter_value.context,
                meter_value.location,
                meter_value.phase,
                meter_value.format,
            ),
        )

        # Fetch BEFORE committing
        row = await cursor.fetchone()
        await self.conn.commit()

        meter_value.id = row["id"] if row else None
        return meter_value

    async def create_batch(self, meter_values: list[MeterValue]):
        """Create multiple meter value records efficiently."""
        query = """
            INSERT INTO meter_val (
                tx_id, cp_id, cp_conn_id, timestamp, measurand, value,
                unit, context, location, phase, format
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = [
            (
                mv.tx_id,
                mv.cp_id,
                mv.cp_conn_id,
                mv.timestamp,
                mv.measurand,
                mv.value,
                mv.unit,
                mv.context,
                mv.location,
                mv.phase,
                mv.format,
            )
            for mv in meter_values
        ]

        await self.conn.executemany(query, params)
        await self.conn.commit()

    async def get_for_transaction(self, tx_id: int, limit: int = 1000) -> list[MeterValue]:
        """Get meter values for a transaction."""
        rows = await self._fetchall(
            """
            SELECT * FROM meter_val
            WHERE tx_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (tx_id, limit),
        )
        return [self._row_to_model(row) for row in rows]

    async def get_for_cp(self, cp_id: str, limit: int = 1000) -> list[MeterValue]:
        """Get recent meter values for a charge point."""
        rows = await self._fetchall(
            """
            SELECT * FROM meter_val
            WHERE cp_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (cp_id, limit),
        )
        return [self._row_to_model(row) for row in rows]

    async def get_last_for_transaction(self, tx_id: int) -> MeterValue | None:
        """Get the last (most recent) meter value for a transaction."""
        row = await self._fetchone(
            """
            SELECT * FROM meter_val
            WHERE tx_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (tx_id,),
        )
        if row:
            return self._row_to_model(row)
        return None

    def _row_to_model(self, row) -> MeterValue:
        """Convert database row to MeterValue model."""
        return MeterValue(
            id=row["id"],
            tx_id=row["tx_id"],
            cp_id=row["cp_id"],
            cp_conn_id=row["cp_conn_id"],
            timestamp=row["timestamp"],
            measurand=row["measurand"],
            value=row["value"],
            unit=row["unit"],
            context=row["context"],
            location=row["location"],
            phase=row["phase"],
            format=row["format"],
            created_at=row["created_at"],
        )
