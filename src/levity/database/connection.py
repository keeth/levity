"""Database connection management."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import aiosqlite

# Register datetime adapters to avoid Python 3.12+ deprecation warning
# See: https://docs.python.org/3/library/sqlite3.html#adapter-and-converter-recipes


def _adapt_datetime(val: datetime) -> str:
    """Convert datetime to ISO format string for SQLite storage."""
    return val.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    """Convert ISO format string from SQLite to datetime."""
    return datetime.fromisoformat(val.decode())


# Register adapters and converters
sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("datetime", _convert_datetime)
sqlite3.register_converter("DATETIME", _convert_datetime)

logger = logging.getLogger(__name__)


class Database:
    """Manages SQLite database connections and initialization."""

    def __init__(self, db_path: str = "levity.db"):
        self.db_path = db_path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish database connection with optimized pragmas."""
        if self.connection is None:
            # Use PARSE_DECLTYPES to enable custom datetime converters
            self.connection = await aiosqlite.connect(
                self.db_path, detect_types=sqlite3.PARSE_DECLTYPES
            )
            self.connection.row_factory = aiosqlite.Row

            await self.connection.execute("PRAGMA journal_mode=WAL")
            await self.connection.execute("PRAGMA synchronous=NORMAL")
            await self.connection.execute("PRAGMA temp_store=MEMORY")
            await self.connection.execute("PRAGMA foreign_keys=ON")
        return self.connection

    async def disconnect(self):
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None

    async def initialize_schema(self, schema_path: str = "sql/001_initial.up.sql"):
        """Initialize database schema from SQL file."""
        conn = await self.connect()

        # Check if schema already exists
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cp'"
        )
        table_exists = await cursor.fetchone()

        if table_exists:
            logger.debug("Database schema already exists, skipping initialization")
            return

        schema_file = Path(schema_path)
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_file.read_text()

        # Execute schema initialization
        await conn.executescript(schema_sql)
        await conn.commit()

    async def __aenter__(self):
        """Async context manager entry."""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
