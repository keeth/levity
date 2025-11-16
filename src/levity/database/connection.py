"""Database connection management."""

import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """Manages SQLite database connections and initialization."""

    def __init__(self, db_path: str = "levity.db"):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish database connection."""
        if self.connection is None:
            self.connection = await aiosqlite.connect(self.db_path)
            self.connection.row_factory = aiosqlite.Row
            logger.info(f"Connected to database: {self.db_path}")
        return self.connection

    async def disconnect(self):
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            logger.info("Disconnected from database")

    async def initialize_schema(self, schema_path: str = "sql/001_initial.up.sql"):
        """Initialize database schema from SQL file."""
        conn = await self.connect()

        schema_file = Path(schema_path)
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_file.read_text()

        # Execute schema initialization
        await conn.executescript(schema_sql)
        await conn.commit()
        logger.info("Database schema initialized")

    async def __aenter__(self):
        """Async context manager entry."""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
