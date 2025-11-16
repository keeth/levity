# Levity

A multi-chargepoint OCPP 1.6 Central System implementation with SQLite storage, built using Python's `ocpp` library and `aiosqlite`.

## Features

- **OCPP 1.6 Compliant**: Full support for OCPP 1.6 JSON protocol
- **Multi-Chargepoint**: Handle multiple charge points concurrently
- **SQLite Storage**: Persistent storage of charge point data, transactions, and meter values
- **Async/Await**: Built on asyncio for high performance
- **Repository Pattern**: Clean separation of concerns with dedicated repository classes
- **WebSocket Support**: Standards-compliant WebSocket server

## Project Structure

```
levity/
├── src/levity/
│   ├── database/          # Database connection management
│   ├── handlers/          # OCPP message handlers
│   ├── models/            # Domain models (dataclasses)
│   ├── repositories/      # Database repositories
│   ├── main.py            # Application entry point
│   └── server.py          # WebSocket server
└── sql/
    └── 001_initial.up.sql # Database schema
```

## Installation

Using `uv` (recommended):

```bash
# Install dependencies
uv sync

# Install in development mode
uv pip install -e .
```

## Usage

### Starting the Server

```bash
# Run with default settings (host: 0.0.0.0, port: 9000)
levity

# Custom host and port
levity --host 127.0.0.1 --port 8080

# Custom database location
levity --db /path/to/database.db

# Enable debug logging
levity --log-level DEBUG
```

### Command Line Options

- `--host`: Host to bind the WebSocket server (default: 0.0.0.0)
- `--port`: Port to bind the WebSocket server (default: 9000)
- `--db`: Path to SQLite database file (default: levity.db)
- `--log-level`: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)

### Connecting Charge Points

Charge points should connect to the WebSocket endpoint:

```
ws://<host>:<port>/ws/{charge_point_id}
```

For example:
```
ws://localhost:9000/ws/CP001
```

The `charge_point_id` in the URL path is used to identify the charge point in the database.

## Supported OCPP Messages

### Implemented Handlers

- **BootNotification**: Registers/updates charge point details in the database
- **Heartbeat**: Updates last heartbeat timestamp
- **StatusNotification**: Updates connector or charge point status
- **StartTransaction**: Creates new transaction record
- **StopTransaction**: Completes transaction and records final meter values
- **MeterValues**: Stores time-series meter readings
- **Authorize**: Basic authorization (currently accepts all)

## Database Schema

The system uses the following main tables:

- `cp`: Charge point information (vendor, model, status, connection state)
- `cp_conn`: Connector status for each charge point
- `tx`: Charging transactions
- `meter_val`: Time-series meter value readings
- `cp_err`: Error events from charge points

See [sql/001_initial.up.sql](sql/001_initial.up.sql) for complete schema details.

## Testing

### Manual Testing with wscat

Install wscat:
```bash
npm install -g wscat
```

Connect and send a BootNotification:
```bash
wscat -c ws://localhost:9000/ws/TEST_CP_001 -s ocpp1.6

# Send a BootNotification message
> [2, "12345", "BootNotification", {"chargePointVendor": "TestVendor", "chargePointModel": "TestModel"}]

# You should receive a response like:
< [3, "12345", {"currentTime": "2025-01-15T10:30:00+00:00", "interval": 60, "status": "Accepted"}]
```

### Testing with Python OCPP Client

```python
import asyncio
from ocpp.v16 import call
from ocpp.v16 import ChargePoint as cp
import websockets

async def test_client():
    async with websockets.connect(
        'ws://localhost:9000/ws/TEST_CP_001',
        subprotocols=['ocpp1.6']
    ) as ws:
        charge_point = cp('TEST_CP_001', ws)

        request = call.BootNotification(
            charge_point_vendor="TestVendor",
            charge_point_model="TestModel"
        )

        response = await charge_point.call(request)
        print(response)

asyncio.run(test_client())
```

## Development

### Testing

The project includes comprehensive unit and integration tests using pytest.

```bash
# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run only integration tests
make test-integration

# Run only WebSocket tests
make test-ws

# Or directly with pytest
uv run pytest tests/ -v
uv run pytest tests/ -v -m unit
uv run pytest tests/ -v -k test_upsert
```

Test fixtures automatically provision fresh SQLite databases for each test, ensuring isolation.

### Code Quality

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Using make (recommended)
make lint         # Run linting checks
make format       # Format code
make fix          # Auto-fix issues and format
make check        # Run all checks (lint + format + tests)

# Or directly with uv
uv run ruff check src/ tests/ example_client.py
uv run ruff check --fix src/ tests/ example_client.py
uv run ruff format src/ tests/ example_client.py
```

See `make help` for all available commands.

### Repository Classes

The project uses a repository pattern for database access:

- `ChargePointRepository`: CRUD operations for charge points
- `ConnectorRepository`: Connector status management
- `TransactionRepository`: Transaction lifecycle management
- `MeterValueRepository`: Meter value storage and retrieval

### Adding New Message Handlers

To add support for additional OCPP messages:

1. Add handler method to `LevityChargePoint` class in [src/levity/handlers/charge_point.py](src/levity/handlers/charge_point.py)
2. Use the `@on(Action.message_name)` decorator
3. Implement database persistence logic using repositories

Example:
```python
@on(Action.data_transfer)
async def on_data_transfer(self, vendor_id: str, **kwargs):
    # Your implementation here
    return call_result.DataTransfer(status="Accepted")
```

## Architecture Decisions

### Why Handmade Repositories vs SQLAlchemy/SQLModel?

This project uses handmade repository classes instead of an ORM for several reasons:

1. **Simplicity**: The schema is well-defined and relatively simple
2. **Performance**: Direct SQL control is better for time-series data (meter values)
3. **Transparency**: Easier to understand and debug SQL queries
4. **Flexibility**: Easy to optimize queries for OCPP-specific access patterns
5. **Minimal Dependencies**: Fewer dependencies to manage and update

### Storage Approach

- **SQLite**: Perfect for single-instance deployments, low maintenance
- **aiosqlite**: Async support for high concurrency without blocking
- **Repository Pattern**: Clean separation between business logic and data access

## Logging

Logs are written to both stdout and `levity.log` file. The log format includes:

- Timestamp
- Logger name
- Log level
- Message

Example log output:
```
2025-01-15 10:30:00,123 - levity.server - INFO - Starting OCPP server on 0.0.0.0:9000
2025-01-15 10:30:00,234 - levity.database.connection - INFO - Connected to database: levity.db
2025-01-15 10:30:00,345 - levity.server - INFO - OCPP server listening on ws://0.0.0.0:9000/ws/{cp_id}
2025-01-15 10:30:15,456 - levity.handlers.charge_point - INFO - Charge point TEST_CP_001 connected
2025-01-15 10:30:15,567 - levity.handlers.charge_point - INFO - BootNotification from TEST_CP_001: TestVendor TestModel
```

## Future Enhancements

- [ ] User authentication and authorization management
- [ ] Remote operations (RemoteStartTransaction, RemoteStopTransaction, etc.)
- [ ] Configuration management (GetConfiguration, ChangeConfiguration)
- [ ] Firmware updates
- [ ] Reservation system
- [ ] Smart charging profiles
- [ ] REST API for monitoring and management
- [ ] WebUI dashboard
- [ ] PostgreSQL/MySQL support for production deployments
- [ ] Metrics and monitoring (Prometheus, Grafana)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
