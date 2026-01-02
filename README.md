# Levity

OCPP 1.6 Central System with SQLite storage, built with Python's [`ocpp`](https://github.com/mobilityhouse/ocpp) library.

## Why this exists

I needed a program to manage a fleet of 20 EV chargers ([Grizzl-e Smart](https://grizzl-e.com/)) in a cohousing development, primarily to track energy use for billing purposes, but with solid observability so that I could respond quickly to any problems.

My [v1](https://github.com/keeth/levity/tree/v1) was overengineered ([Django](https://www.djangoproject.com/), [Docker](https://www.docker.com/), [RabbitMQ](https://www.rabbitmq.com/), [nginx](https://nginx.org/), etc) and over time I realized that I would be better served by something smaller and simpler, with a strong focus on reliability and low resource usage.

Levity is a barebones, no-GUI, [SQLite](https://www.sqlite.org/)-backed, single-threaded OCPP server. But complementary tools like [Prometheus](https://prometheus.io/)/[Grafana](https://grafana.com/), [Fluentd](https://www.fluentd.org/), and [Litestream](https://litestream.io/) make it something more like a complete package.

I run Levity onsite on a Raspberry Pi with attached SSD storage. It sends metrics and audit logs up to a cloud instance ([Hetzner](https://www.hetzner.com/) / [Coolify](https://coolify.io/)) running the above tools.

- [Grafana](https://grafana.com/): alerts and monitoring (not just the service itself but the status of each charger, total energy use, active charging sessions, network disconnections, etc)

- [Fluentd](https://www.fluentd.org/): complete bidirectional logging of OCPP traffic for audit/debug purposes

- [Litestream](https://litestream.io/): replicate the central database to S3 for durability

## Status of the project

I fix bugs as I find them in my own installation. Though I'm scratching my own itch here, I've tried to build things in an extensible way, and welcome contributions.

## Features

- Core [OCPP 1.6](https://www.openchargealliance.org/) JSON protocol (BootNotification, Heartbeat, Status, Transactions, MeterValues, Authorize)
- Multi-chargepoint WebSocket server
- SQLite persistence with async I/O
- Plugin system for extensibility
- [Prometheus](https://prometheus.io/) metrics
- [Fluentd](https://www.fluentd.org/) logging
- Auto remote start for single-owner charging (optional)

## Quick Start

```bash
# Install
uv sync

# Run server
levity --port 9000 --metrics-port 9090

# Connect charge points to: ws://localhost:9000/ws/{charge_point_id}
```

## CLI Options

```
--host              WebSocket host (default: 0.0.0.0)
--port              WebSocket port (default: 9000)
--db                SQLite database path (default: levity.db)
--metrics-port      Prometheus metrics port (enables metrics)
--enable-auto-start Enable auto remote start on cable plug-in
--fluentd-endpoint  Fluentd endpoint (host:port) for audit logging
--log-level         DEBUG, INFO, WARNING, ERROR (default: INFO)
```

## Development

```bash
make test      # Run all tests
make lint      # Check code quality
make format    # Format code
make run       # Start server
```

Pre-commit hooks run automatically on commit. Install with: `uv run pre-commit install`

## Plugins

Built-in plugins: PrometheusMetrics, OrphanedTransaction, AutoRemoteStart, FluentdAudit.

See [PLUGINS.md](PLUGINS.md) for creating custom plugins.

## Project Structure

```
src/levity/
├── handlers/      # OCPP message handlers
├── plugins/       # Plugin framework + built-in plugins
├── repositories/  # Database access layer
├── models/        # Domain models
├── database/      # Connection management
├── server.py      # WebSocket server
└── main.py        # Entry point
```

## License

MIT
