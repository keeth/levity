# Levity - Project Context for Claude

This document contains important project context and decisions made during initial development.

## Project Overview

**Levity** is a multi-chargepoint OCPP 1.6 Central System with SQLite storage, built using Python's `ocpp` library and `aiosqlite`. It handles WebSocket connections from EV charging stations and persists all OCPP protocol data to a local SQLite database.

## Key Architecture Decisions

### Storage Strategy: Handmade Repositories vs ORM

**Decision**: Use handmade repository classes with raw SQL instead of SQLAlchemy/SQLModel.

**Rationale**:
- Schema is well-defined and relatively simple (defined in `sql/001_initial.up.sql`)
- Better performance for time-series data (meter values)
- Direct SQL control allows OCPP-specific optimizations
- Fewer dependencies to manage
- Easier to understand query execution

### WebSocket URL Pattern

The server accepts connections at: `/ws/{charge_point_id}`

Example: `ws://localhost:9000/ws/CP001`

The charge point ID from the URL is used as the primary database identifier.

### Database Schema Overview

Main tables:
- `cp` - Charge point metadata (vendor, model, firmware, connection status)
- `cp_conn` - Individual connectors per charge point
- `tx` - Charging transactions
- `meter_val` - Time-series meter readings
- `cp_err` - Error events

All use abbreviated names to keep SQL concise.

## Implementation Notes

### OCPP Message Handlers

Located in `src/levity/handlers/charge_point.py`, the `LevityChargePoint` class handles:

- **BootNotification**: Upserts charge point details to database
- **Heartbeat**: Updates `last_heartbeat_at` timestamp
- **StatusNotification**: Updates connector or charge point status
- **StartTransaction**: Creates new transaction record, returns DB ID as OCPP transaction ID
- **StopTransaction**: Marks transaction complete, calculates energy delivered
- **MeterValues**: Stores time-series meter data
- **Authorize**: Currently accepts all (placeholder for production authorization)

### Repository Pattern

Each repository (`repositories/`) handles one table:
- Uses `BaseRepository` for common operations
- All methods are async (using aiosqlite)
- Returns domain models (dataclasses from `models/domain.py`)

### SQLite Compatibility Issues Encountered

**Problem**: `RETURNING` clause in INSERT statements failed with "cannot commit transaction - SQL statements in progress"

**Solution**: Replaced `RETURNING id` with `last_insert_rowid()` for better SQLite compatibility:

```python
# Instead of:
cursor = await self._execute("INSERT ... RETURNING id", params)
row = await cursor.fetchone()

# Use:
await self._execute("INSERT ...", params)
cursor = await self.conn.execute("SELECT last_insert_rowid()")
row = await cursor.fetchone()
tx.id = row[0]
```

### Schema Initialization

The `Database.initialize_schema()` method:
- Checks if tables exist before running schema script
- Idempotent - safe to call multiple times
- Allows tests to provision fresh databases without conflicts

## Testing Strategy

### Unit Tests (`tests/test_repositories.py`)
- Test each repository class in isolation
- Use real SQLite databases (not mocks)
- Each test gets fresh database via `temp_db` fixture
- Fast and reliable

### Integration Tests (`tests/test_integration.py`)
- Test full WebSocket OCPP protocol flows
- Use `MockOCPPClient` to simulate charge points
- More complex due to async server startup
- Can be skipped during development (unit tests provide good coverage)

### Test Fixtures (`tests/conftest.py`)
```python
@pytest.fixture
async def temp_db():
    """Provisions fresh SQLite database with schema for each test"""
```

## Development Workflow

```bash
make test-unit       # Fast unit tests (recommended during development)
make lint            # Check code quality
make format          # Auto-format code
make fix             # Auto-fix linting issues + format
make run             # Start the server
make example         # Run example client simulation
```

## Common Patterns

### Creating a New OCPP Message Handler

1. Add method to `LevityChargePoint` class
2. Use `@on(Action.message_name)` decorator
3. Extract data from kwargs (OCPP uses snake_case conversion)
4. Use repositories to persist to database
5. Return appropriate `call_result` object

Example:
```python
@on(Action.data_transfer)
async def on_data_transfer(self, vendor_id: str, **kwargs):
    message_id = kwargs.get("message_id")
    data = kwargs.get("data")

    # Process and store as needed

    return call_result.DataTransfer(status="Accepted")
```

### Adding a New Repository

1. Create file in `src/levity/repositories/`
2. Extend `BaseRepository`
3. Implement CRUD methods
4. Use `_fetchone()`, `_fetchall()`, `_execute()` helpers
5. Add `_row_to_model()` to convert DB rows to domain models

## Known Limitations / TODOs

- Authorization currently accepts all ID tags (needs production auth logic)
- Integration tests have server startup timing issues
- No support for:
  - RemoteStartTransaction/RemoteStopTransaction
  - Configuration management (GetConfiguration, ChangeConfiguration)
  - Firmware updates
  - Reservation system
  - Smart charging profiles

## Dependencies

**Core**:
- `ocpp` - OCPP 1.6 protocol implementation
- `websockets` - WebSocket server
- `aiosqlite` - Async SQLite driver

**Dev**:
- `pytest` + `pytest-asyncio` - Testing framework
- `ruff` - Linting and formatting

**Package Manager**: `uv` (modern, fast Python package manager)

## Useful References

- OCPP 1.6 Spec: Section 3.1.1 defines WebSocket URL pattern with charge point identity
- Python OCPP library docs: `reference/Server side usage — ocpp 2.1.0 documentation.html`
- Database schema: `sql/001_initial.up.sql` (canonical source of truth)

## Ruff Configuration Notes

Disabled rules for OCPP-specific patterns:
- `A002` - `id` is commonly used as charge point identifier
- `ARG002` - OCPP handlers need all parameters for correct signature
- `TID252` - Relative imports are fine for internal modules

Test files ignore: `PLR0915` (long functions), `PLC0415` (imports anywhere), `SIM105` (try-except-pass)
