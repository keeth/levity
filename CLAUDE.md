# Levity - Project Context

OCPP 1.6 Central System with SQLite storage.

## Architecture

- **WebSocket endpoint**: `/ws/{charge_point_id}` (e.g., `ws://localhost:9000/ws/CP001`)
- **Storage**: SQLite with async aiosqlite, handmade repository classes (no ORM)
- **Plugins**: Hook-based system for extensibility (see PLUGINS.md)

## Database Tables

| Table | Purpose |
|-------|---------|
| `cp` | Charge point metadata |
| `cp_conn` | Connector status |
| `tx` | Transactions |
| `meter_val` | Time-series meter readings |
| `cp_err` | Error events |

Schema: `sql/001_initial.up.sql`

## Key Files

- `src/levity/handlers/charge_point.py` - OCPP message handlers (LevityChargePoint class)
- `src/levity/server.py` - WebSocket server
- `src/levity/plugins/` - Plugin framework + built-in plugins
- `src/levity/repositories/` - Database access layer

## Patterns

### SQLite RETURNING Clause

Fetch BEFORE commit when using RETURNING:

```python
cursor = await self._execute("INSERT ... RETURNING id", params)
row = await cursor.fetchone()  # Fetch BEFORE commit
await self.conn.commit()
```

### Adding OCPP Handler

```python
@on(Action.data_transfer)
async def on_data_transfer(self, vendor_id: str, **kwargs):
    # Use repositories for persistence
    return call_result.DataTransfer(status="Accepted")
```

### Plugin Hooks

Plugins hook into `BEFORE_*` and `ON_*` events. See PLUGINS.md.

## Development

```bash
make test       # Run tests
make lint       # Ruff check
make format     # Ruff format
make run        # Start server
```

Pre-commit hooks: `uv run pre-commit install`

## Ruff Config Notes

Disabled rules for OCPP patterns:
- `A002` - `id` commonly used for identifiers
- `ARG002` - OCPP handlers need all params for signature
- Complexity rules ignored for: `main.py`, `server.py`, `prometheus_metrics.py`
