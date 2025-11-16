"""Pytest configuration and fixtures."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from levity.database import Database


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for async tests."""
    return asyncio.get_event_loop_policy()


@pytest.fixture
async def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Initialize database with schema
    db = Database(db_path)
    await db.initialize_schema()

    yield db

    # Cleanup
    await db.disconnect()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
async def db_connection(temp_db):
    """Provide a database connection for testing."""
    conn = await temp_db.connect()
    yield conn
    # Connection is cleaned up by temp_db fixture


@pytest.fixture
def sample_boot_notification():
    """Sample BootNotification message payload."""
    return {
        "charge_point_vendor": "TestVendor",
        "charge_point_model": "TestModel",
        "charge_point_serial_number": "TEST-001",
        "firmware_version": "1.0.0",
    }


@pytest.fixture
def sample_status_notification():
    """Sample StatusNotification message payload."""
    return {
        "connector_id": 1,
        "error_code": "NoError",
        "status": "Available",
    }
