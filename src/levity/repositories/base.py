"""Base repository class."""

import aiosqlite


class BaseRepository:
    """Base class for all repositories."""

    def __init__(self, connection: aiosqlite.Connection):
        self.conn = connection

    async def _execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a query and return cursor (caller must fetch before committing)."""
        return await self.conn.execute(query, params)

    async def _execute_and_commit(self, query: str, params: tuple = ()) -> None:
        """Execute a query and commit (for queries that don't return data)."""
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def _fetchone(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        """Execute query and fetch one row."""
        cursor = await self.conn.execute(query, params)
        return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        """Execute query and fetch all rows."""
        cursor = await self.conn.execute(query, params)
        return await cursor.fetchall()
