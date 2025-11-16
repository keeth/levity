"""Repository for transaction operations."""

from datetime import datetime

from ..models import Transaction
from .base import BaseRepository


class TransactionRepository(BaseRepository):
    """Handles database operations for transactions."""

    async def create(self, tx: Transaction) -> Transaction:
        """Create a new transaction."""
        query = """
            INSERT INTO tx (
                tx_id, cp_id, cp_conn_id, id_tag, start_time,
                meter_start, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """

        cursor = await self._execute(
            query,
            (
                tx.tx_id,
                tx.cp_id,
                tx.cp_conn_id,
                tx.id_tag,
                tx.start_time,
                tx.meter_start,
                tx.status,
            ),
        )

        row = await cursor.fetchone()
        tx.id = row["id"] if row else None
        return tx

    async def get_by_id(self, tx_id: int) -> Transaction | None:
        """Get transaction by database ID."""
        row = await self._fetchone("SELECT * FROM tx WHERE id = ?", (tx_id,))
        if row:
            return self._row_to_model(row)
        return None

    async def get_by_ocpp_tx_id(self, ocpp_tx_id: int) -> Transaction | None:
        """Get transaction by OCPP transaction ID."""
        row = await self._fetchone("SELECT * FROM tx WHERE tx_id = ?", (ocpp_tx_id,))
        if row:
            return self._row_to_model(row)
        return None

    async def get_active_for_connector(self, cp_id: str, cp_conn_id: int) -> Transaction | None:
        """Get active transaction for a connector."""
        row = await self._fetchone(
            """
            SELECT * FROM tx
            WHERE cp_id = ? AND cp_conn_id = ? AND status = 'Active'
            ORDER BY start_time DESC
            LIMIT 1
            """,
            (cp_id, cp_conn_id),
        )
        if row:
            return self._row_to_model(row)
        return None

    async def stop_transaction(
        self,
        ocpp_tx_id: int,
        stop_time: datetime,
        meter_stop: int,
        stop_reason: str = "",
    ):
        """Stop a transaction."""
        query = """
            UPDATE tx
            SET stop_time = ?,
                meter_stop = ?,
                energy_delivered = ? - meter_start,
                stop_reason = ?,
                status = 'Completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE tx_id = ?
        """
        await self._execute(query, (stop_time, meter_stop, meter_stop, stop_reason, ocpp_tx_id))

    async def get_all_for_cp(self, cp_id: str, limit: int = 100) -> list[Transaction]:
        """Get transactions for a charge point."""
        rows = await self._fetchall(
            """
            SELECT * FROM tx
            WHERE cp_id = ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (cp_id, limit),
        )
        return [self._row_to_model(row) for row in rows]

    def _row_to_model(self, row) -> Transaction:
        """Convert database row to Transaction model."""
        return Transaction(
            id=row["id"],
            tx_id=row["tx_id"],
            cp_id=row["cp_id"],
            cp_conn_id=row["cp_conn_id"],
            id_tag=row["id_tag"],
            start_time=row["start_time"],
            stop_time=row["stop_time"],
            meter_start=row["meter_start"],
            meter_stop=row["meter_stop"],
            energy_delivered=row["energy_delivered"],
            stop_reason=row["stop_reason"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
