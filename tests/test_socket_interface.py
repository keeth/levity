"""Tests for Unix socket command interface."""

import json
import stat
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from levity.handlers import LevityChargePoint
from levity.models import Connector, Transaction
from levity.repositories.connector import ConnectorRepository
from levity.repositories.transaction import TransactionRepository
from levity.socket_interface import (
    Command,
    CommandResponse,
    Selector,
    SelectorType,
    UnixSocketCommandInterface,
)
from levity.socket_interface.command_interface import deserialize_ocpp_call
from levity.socket_interface.models import CallResult, OCPPCall


class TestModels:
    """Test data models."""

    def test_selector_from_dict_all(self):
        """Test Selector.from_dict with type=all."""
        selector = Selector.from_dict({"type": "all"})
        assert selector.type == SelectorType.ALL
        assert selector.value is None

    def test_selector_from_dict_ids(self):
        """Test Selector.from_dict with type=ids."""
        selector = Selector.from_dict({"type": "ids", "value": ["CP001", "CP002"]})
        assert selector.type == SelectorType.IDS
        assert selector.value == ["CP001", "CP002"]

    def test_selector_from_dict_in_transaction(self):
        """Test Selector.from_dict with type=in_transaction."""
        selector = Selector.from_dict({"type": "in_transaction"})
        assert selector.type == SelectorType.IN_TRANSACTION
        assert selector.value is None

    def test_selector_from_dict_not_in_transaction(self):
        """Test Selector.from_dict with type=not_in_transaction."""
        selector = Selector.from_dict({"type": "not_in_transaction"})
        assert selector.type == SelectorType.NOT_IN_TRANSACTION
        assert selector.value is None

    def test_ocpp_call_from_dict(self):
        """Test OCPPCall.from_dict."""
        call = OCPPCall.from_dict(
            {"action": "RemoteStartTransaction", "payload": {"connector_id": 1, "id_tag": "test"}}
        )
        assert call.action == "RemoteStartTransaction"
        assert call.payload == {"connector_id": 1, "id_tag": "test"}

    def test_ocpp_call_from_dict_no_payload(self):
        """Test OCPPCall.from_dict with no payload."""
        call = OCPPCall.from_dict({"action": "GetConfiguration"})
        assert call.action == "GetConfiguration"
        assert call.payload == {}

    def test_command_from_json(self):
        """Test Command.from_json."""
        json_str = json.dumps(
            {
                "selector": {"type": "all"},
                "call": {"action": "Reset", "payload": {"type": "Soft"}},
                "timeout": 60,
            }
        )
        command = Command.from_json(json_str)
        assert command.selector.type == SelectorType.ALL
        assert command.call.action == "Reset"
        assert command.call.payload == {"type": "Soft"}
        assert command.timeout == 60
        assert command.command_id is not None  # Auto-generated

    def test_command_from_json_default_timeout(self):
        """Test Command.from_json with default timeout."""
        json_str = json.dumps({"selector": {"type": "all"}, "call": {"action": "ClearCache"}})
        command = Command.from_json(json_str)
        assert command.timeout == 30  # Default

    def test_command_response_to_json(self):
        """Test CommandResponse.to_json."""
        response = CommandResponse.from_results(
            command_id="test-123",
            results=[
                CallResult(cp_id="CP001", status="success", response={"status": "Accepted"}),
                CallResult(cp_id="CP002", status="error", error="Timeout after 30s"),
            ],
        )

        json_str = response.to_json()
        data = json.loads(json_str)

        assert data["command_id"] == "test-123"
        assert data["status"] == "completed"
        assert len(data["results"]) == 2
        assert data["summary"]["total"] == 2
        assert data["summary"]["success"] == 1
        assert data["summary"]["error"] == 1


class TestOCPPDeserialization:
    """Test OCPP call deserialization."""

    def test_deserialize_remote_start_transaction(self):
        """Test deserializing RemoteStartTransaction."""
        call = deserialize_ocpp_call(
            "RemoteStartTransaction", {"connector_id": 1, "id_tag": "anonymous"}
        )
        assert call.connector_id == 1
        assert call.id_tag == "anonymous"

    def test_deserialize_reset(self):
        """Test deserializing Reset."""
        call = deserialize_ocpp_call("Reset", {"type": "Soft"})
        assert call.type == "Soft"

    def test_deserialize_change_configuration(self):
        """Test deserializing ChangeConfiguration."""
        call = deserialize_ocpp_call(
            "ChangeConfiguration", {"key": "HeartbeatInterval", "value": "60"}
        )
        assert call.key == "HeartbeatInterval"
        assert call.value == "60"

    def test_deserialize_get_configuration(self):
        """Test deserializing GetConfiguration with no payload."""
        call = deserialize_ocpp_call("GetConfiguration", {})
        # GetConfiguration accepts optional 'key' parameter
        assert call is not None

    def test_deserialize_invalid_action(self):
        """Test deserializing invalid action."""
        with pytest.raises(ValueError, match="Unknown OCPP action"):
            deserialize_ocpp_call("InvalidAction", {})

    def test_deserialize_invalid_payload(self):
        """Test deserializing with invalid payload."""
        with pytest.raises(ValueError, match="Invalid payload"):
            # RemoteStartTransaction requires id_tag
            deserialize_ocpp_call("RemoteStartTransaction", {"connector_id": 1})


class TestSelectors:
    """Test charge point selectors."""

    @pytest.fixture
    async def mock_server(self, temp_db):
        """Create mock OCPPServer with charge points."""
        server = Mock()
        server.charge_points = {
            "CP001": Mock(spec=LevityChargePoint),
            "CP002": Mock(spec=LevityChargePoint),
            "CP003": Mock(spec=LevityChargePoint),
        }

        # Populate database with charge points
        conn = await temp_db.connect()

        # Create charge points in DB
        for cp_id in ["CP001", "CP002", "CP003", "CP004"]:
            await conn.execute(
                "INSERT INTO cp (id, vendor, model) VALUES (?, ?, ?)",
                (cp_id, "TestVendor", "TestModel"),
            )
        await conn.commit()

        yield server, temp_db

    @pytest.fixture
    async def socket_interface(self, mock_server):
        """Create UnixSocketCommandInterface for testing (without starting)."""
        _server, db = mock_server
        return UnixSocketCommandInterface(
            socket_path="/tmp/test-socket-placeholder",
            server=_server,
            db=db,
            default_timeout=5,
        )

    async def test_selector_all(self, socket_interface):
        """Test selector type=all."""
        selector = Selector(type=SelectorType.ALL)
        cp_ids = await socket_interface._select_charge_points(selector)
        assert set(cp_ids) == {"CP001", "CP002", "CP003"}

    async def test_selector_ids_all_connected(self, socket_interface):
        """Test selector type=ids with all requested IDs connected."""
        selector = Selector(type=SelectorType.IDS, value=["CP001", "CP002"])
        cp_ids = await socket_interface._select_charge_points(selector)
        assert set(cp_ids) == {"CP001", "CP002"}

    async def test_selector_ids_partial_connected(self, socket_interface):
        """Test selector type=ids with some requested IDs not connected."""
        selector = Selector(type=SelectorType.IDS, value=["CP001", "CP004"])
        cp_ids = await socket_interface._select_charge_points(selector)
        assert cp_ids == ["CP001"]  # CP004 is in DB but not connected

    async def test_selector_ids_none_connected(self, socket_interface):
        """Test selector type=ids with no requested IDs connected."""
        selector = Selector(type=SelectorType.IDS, value=["CP004", "CP005"])
        cp_ids = await socket_interface._select_charge_points(selector)
        assert cp_ids == []

    async def test_selector_in_transaction(self, mock_server, socket_interface):
        """Test selector type=in_transaction."""
        _server, db = mock_server
        conn = await db.connect()
        tx_repo = TransactionRepository(conn)
        conn_repo = ConnectorRepository(conn)

        # Create connectors
        connector1 = Connector(cp_id="CP001", conn_id=1, status="Charging")
        connector2 = Connector(cp_id="CP002", conn_id=1, status="Available")
        await conn_repo.upsert(connector1)
        await conn_repo.upsert(connector2)
        conn1 = await conn_repo.get_by_cp_and_connector(cp_id="CP001", conn_id=1)

        # Create active transaction for CP001
        from datetime import UTC, datetime

        transaction = Transaction(
            tx_id=1,
            cp_id="CP001",
            cp_conn_id=conn1.id,
            start_time=datetime.now(UTC),
            meter_start=0,
            id_tag="test",
        )
        await tx_repo.create(transaction)

        selector = Selector(type=SelectorType.IN_TRANSACTION)
        cp_ids = await socket_interface._select_charge_points(selector)
        assert cp_ids == ["CP001"]

    async def test_selector_not_in_transaction(self, mock_server, socket_interface):
        """Test selector type=not_in_transaction."""
        _server, db = mock_server
        conn = await db.connect()
        tx_repo = TransactionRepository(conn)
        conn_repo = ConnectorRepository(conn)

        # Create connectors
        connector1 = Connector(cp_id="CP001", conn_id=1, status="Charging")
        await conn_repo.upsert(connector1)
        conn1 = await conn_repo.get_by_cp_and_connector(cp_id="CP001", conn_id=1)

        # Create active transaction for CP001
        from datetime import UTC, datetime

        transaction = Transaction(
            tx_id=1,
            cp_id="CP001",
            cp_conn_id=conn1.id,
            start_time=datetime.now(UTC),
            meter_start=0,
            id_tag="test",
        )
        await tx_repo.create(transaction)

        selector = Selector(type=SelectorType.NOT_IN_TRANSACTION)
        cp_ids = await socket_interface._select_charge_points(selector)
        # CP002 and CP003 are connected but not in transaction
        # CP004 is in DB but not connected
        assert set(cp_ids) == {"CP002", "CP003"}


class TestDispatch:
    """Test OCPP call dispatching."""

    @pytest.fixture
    async def mock_server_with_responses(self):
        """Create mock server with charge points that return responses."""
        server = Mock()

        # Mock charge point that succeeds
        cp_success = Mock(spec=LevityChargePoint)
        success_response = Mock()
        success_response.status = "Accepted"
        cp_success.call = AsyncMock(return_value=success_response)

        # Mock charge point that times out
        cp_timeout = Mock(spec=LevityChargePoint)
        cp_timeout.call = AsyncMock(side_effect=TimeoutError())

        # Mock charge point that raises an exception
        cp_error = Mock(spec=LevityChargePoint)
        cp_error.call = AsyncMock(side_effect=Exception("Test error"))

        server.charge_points = {
            "CP001": cp_success,
            "CP002": cp_timeout,
            "CP003": cp_error,
        }

        return server

    @pytest.fixture
    async def socket_interface_with_mock(self, mock_server_with_responses, temp_db):
        """Create UnixSocketCommandInterface with mock server."""
        return UnixSocketCommandInterface(
            socket_path="/tmp/test-socket-placeholder",
            server=mock_server_with_responses,
            db=temp_db,
            default_timeout=1,  # Short timeout for tests
        )

    async def test_dispatch_to_single_charger_success(self, socket_interface_with_mock):
        """Test dispatching to a single charger that succeeds."""
        results = await socket_interface_with_mock._dispatch_call(
            cp_ids=["CP001"], action="Reset", payload={"type": "Soft"}, timeout=1
        )

        assert len(results) == 1
        assert results[0].cp_id == "CP001"
        assert results[0].status == "success"
        assert results[0].response is not None

    async def test_dispatch_to_multiple_chargers(self, socket_interface_with_mock):
        """Test dispatching to multiple chargers concurrently."""
        results = await socket_interface_with_mock._dispatch_call(
            cp_ids=["CP001", "CP002", "CP003"],
            action="ClearCache",
            payload={},
            timeout=1,
        )

        assert len(results) == 3

        # CP001 should succeed
        cp001_result = next(r for r in results if r.cp_id == "CP001")
        assert cp001_result.status == "success"

        # CP002 should timeout
        cp002_result = next(r for r in results if r.cp_id == "CP002")
        assert cp002_result.status == "error"
        assert "Timeout" in cp002_result.error

        # CP003 should error
        cp003_result = next(r for r in results if r.cp_id == "CP003")
        assert cp003_result.status == "error"
        assert "Test error" in cp003_result.error

    async def test_dispatch_to_disconnected_charger(self, socket_interface_with_mock):
        """Test dispatching to disconnected charger."""
        results = await socket_interface_with_mock._dispatch_call(
            cp_ids=["CP999"],  # Not in charge_points dict
            action="Reset",
            payload={"type": "Soft"},
            timeout=1,
        )

        assert len(results) == 1
        assert results[0].cp_id == "CP999"
        assert results[0].status == "error"
        assert "not connected" in results[0].error

    async def test_dispatch_invalid_action(self, socket_interface_with_mock):
        """Test dispatching with invalid OCPP action."""
        results = await socket_interface_with_mock._dispatch_call(
            cp_ids=["CP001"], action="InvalidAction", payload={}, timeout=1
        )

        assert len(results) == 1
        assert results[0].status == "error"
        assert "Unknown OCPP action" in results[0].error

    async def test_dispatch_invalid_payload(self, socket_interface_with_mock):
        """Test dispatching with invalid payload."""
        results = await socket_interface_with_mock._dispatch_call(
            cp_ids=["CP001"],
            action="RemoteStartTransaction",
            payload={"connector_id": 1},  # Missing required id_tag
            timeout=1,
        )

        assert len(results) == 1
        assert results[0].status == "error"
        assert "Invalid payload" in results[0].error


class TestSocketLifecycle:
    """Test FIFO lifecycle management."""

    @pytest.fixture
    def socket_path(self):
        """Create temporary FIFO path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.fifo"

    async def test_socket_creation(self, socket_path, temp_db):
        """Test socket is created on start."""
        server = Mock()
        server.charge_points = {}

        interface = UnixSocketCommandInterface(
            socket_path=str(socket_path), server=server, db=temp_db, default_timeout=5
        )

        assert not socket_path.exists()
        await interface.start()
        assert socket_path.exists()
        assert stat.S_ISSOCK(socket_path.stat().st_mode)  # Check if it's a socket

        await interface.stop()
        assert not socket_path.exists()

    async def test_socket_already_exists(self, socket_path, temp_db):
        """Test starting when socket already exists."""
        # Create a socket manually
        import socket as sock_module

        s = sock_module.socket(sock_module.AF_UNIX, sock_module.SOCK_STREAM)
        s.bind(str(socket_path))
        s.close()
        server = Mock()
        server.charge_points = {}

        interface = UnixSocketCommandInterface(
            socket_path=str(socket_path), server=server, db=temp_db, default_timeout=5
        )

        # Should not raise error
        await interface.start()
        assert socket_path.exists()

        await interface.stop()

    async def test_socket_exists_as_regular_file(self, socket_path, temp_db):
        """Test starting when path exists but is not a socket."""
        socket_path.touch()  # Create regular file
        server = Mock()
        server.charge_points = {}

        interface = UnixSocketCommandInterface(
            socket_path=str(socket_path), server=server, db=temp_db, default_timeout=5
        )

        with pytest.raises(ValueError, match="exists but is not a socket"):
            await interface.start()

        socket_path.unlink()


class TestCommandProcessing:
    """Test end-to-end command processing."""

    @pytest.fixture
    async def setup_server_and_interface(self, temp_db):
        """Create server with mock charge points and FIFO interface."""
        server = Mock()

        # Create mock charge point
        cp = Mock(spec=LevityChargePoint)
        response = Mock()
        response.status = "Accepted"
        cp.call = AsyncMock(return_value=response)

        server.charge_points = {"CP001": cp}

        # Create temporary FIFO path
        tmpdir = tempfile.mkdtemp()
        socket_path = Path(tmpdir) / "test.fifo"

        interface = UnixSocketCommandInterface(
            socket_path=str(socket_path), server=server, db=temp_db, default_timeout=5
        )

        yield server, interface, socket_path

        # Cleanup
        if interface._server:
            await interface.stop()
        if socket_path.exists():
            socket_path.unlink()
        Path(tmpdir).rmdir()

    async def test_process_command_success(self, setup_server_and_interface):
        """Test processing a valid command."""
        _server, interface, _socket_path = setup_server_and_interface

        command = Command(
            selector=Selector(type=SelectorType.ALL),
            call=OCPPCall(action="Reset", payload={"type": "Soft"}),
            timeout=5,
        )

        response = await interface._process_command(command)

        assert response.command_id == command.command_id
        assert response.status == "completed"
        assert response.summary["total"] == 1
        assert response.summary["success"] == 1
        assert response.summary["error"] == 0

    async def test_process_command_empty_selector(self, setup_server_and_interface):
        """Test processing command with empty selector."""
        server, interface, _socket_path = setup_server_and_interface
        server.charge_points = {}  # No connected charge points

        command = Command(
            selector=Selector(type=SelectorType.ALL),
            call=OCPPCall(action="Reset", payload={"type": "Soft"}),
            timeout=5,
        )

        response = await interface._process_command(command)

        assert response.status == "completed"
        assert response.summary["total"] == 0
        assert response.results == []
