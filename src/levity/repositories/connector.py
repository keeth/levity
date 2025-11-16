"""Repository for connector operations."""

from ..models import Connector
from .base import BaseRepository


class ConnectorRepository(BaseRepository):
    """Handles database operations for connectors."""

    async def upsert(self, connector: Connector) -> Connector:
        """Insert or update a connector."""
        query = """
            INSERT INTO cp_conn (
                cp_id, conn_id, status, error_code, vendor_error_code, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cp_id, conn_id) DO UPDATE SET
                status = excluded.status,
                error_code = excluded.error_code,
                vendor_error_code = excluded.vendor_error_code,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """

        cursor = await self._execute(
            query,
            (
                connector.cp_id,
                connector.conn_id,
                connector.status,
                connector.error_code,
                connector.vendor_error_code,
            ),
        )

        # Fetch BEFORE committing
        row = await cursor.fetchone()
        await self.conn.commit()

        connector.id = row["id"] if row else None
        return connector

    async def get_by_cp_and_connector(self, cp_id: str, conn_id: int) -> Connector | None:
        """Get connector by charge point ID and connector ID."""
        row = await self._fetchone(
            "SELECT * FROM cp_conn WHERE cp_id = ? AND conn_id = ?", (cp_id, conn_id)
        )
        if row:
            return self._row_to_model(row)
        return None

    async def get_by_id(self, connector_id: int) -> Connector | None:
        """Get connector by database ID."""
        row = await self._fetchone("SELECT * FROM cp_conn WHERE id = ?", (connector_id,))
        if row:
            return self._row_to_model(row)
        return None

    async def get_all_for_cp(self, cp_id: str) -> list[Connector]:
        """Get all connectors for a charge point."""
        rows = await self._fetchall(
            "SELECT * FROM cp_conn WHERE cp_id = ? ORDER BY conn_id", (cp_id,)
        )
        return [self._row_to_model(row) for row in rows]

    async def update_status(
        self,
        cp_id: str,
        conn_id: int,
        status: str,
        error_code: str = "",
        vendor_error_code: str = "",
    ):
        """Update connector status."""
        query = """
            UPDATE cp_conn
            SET status = ?,
                error_code = ?,
                vendor_error_code = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE cp_id = ? AND conn_id = ?
        """
        await self._execute(query, (status, error_code, vendor_error_code, cp_id, conn_id))

    def _row_to_model(self, row) -> Connector:
        """Convert database row to Connector model."""
        return Connector(
            id=row["id"],
            cp_id=row["cp_id"],
            conn_id=row["conn_id"],
            status=row["status"],
            error_code=row["error_code"],
            vendor_error_code=row["vendor_error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
