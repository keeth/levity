.PHONY: help install dev run test test-unit test-integration test-ws example lint format check clean

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv sync

dev:  ## Install in development mode
	uv pip install -e .

run:  ## Run the server
	uv run levity

test:  ## Run all tests
	uv run pytest tests/ -v

test-unit:  ## Run unit tests only
	uv run pytest tests/ -v -m unit

test-integration:  ## Run integration tests only
	uv run pytest tests/ -v -m integration

test-ws:  ## Run WebSocket tests only
	uv run pytest tests/ -v -m websocket

example:  ## Run the example test client
	uv run python example_client.py

lint:  ## Run linting checks
	uv run ruff check src/ tests/ example_client.py

format:  ## Format code
	uv run ruff format src/ tests/ example_client.py

check:  ## Run all checks (lint + format check + tests)
	uv run ruff check src/ tests/ example_client.py
	uv run ruff format --check src/ tests/ example_client.py
	uv run pytest tests/ -v

fix:  ## Auto-fix linting issues
	uv run ruff check --fix src/ tests/ example_client.py
	uv run ruff format src/ tests/ example_client.py

clean:  ## Clean up generated files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .venv/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	rm -f levity.db
	rm -f levity.log
