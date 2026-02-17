"""Unix socket-based command interface for sending OCPP commands to charge points."""

import asyncio
import json
import logging
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ocpp.v16 import call

from ..repositories.charge_point import ChargePointRepository
from .models import CallResult, Command, CommandResponse, Selector, SelectorType

if TYPE_CHECKING:
    from ..database import Database
    from ..server import OCPPServer

logger = logging.getLogger("levity")


# Mapping of OCPP action names to call dataclasses
# Only includes server-initiated (central system → charge point) actions
OCPP_CALL_CLASSES = {
    "CancelReservation": call.CancelReservation,
    "CertificateSigned": call.CertificateSigned,
    "ChangeAvailability": call.ChangeAvailability,
    "ChangeConfiguration": call.ChangeConfiguration,
    "ClearCache": call.ClearCache,
    "ClearChargingProfile": call.ClearChargingProfile,
    "DataTransfer": call.DataTransfer,
    "DeleteCertificate": call.DeleteCertificate,
    "ExtendedTriggerMessage": call.ExtendedTriggerMessage,
    "GetCompositeSchedule": call.GetCompositeSchedule,
    "GetConfiguration": call.GetConfiguration,
    "GetDiagnostics": call.GetDiagnostics,
    "GetInstalledCertificateIds": call.GetInstalledCertificateIds,
    "GetLocalListVersion": call.GetLocalListVersion,
    "GetLog": call.GetLog,
    "InstallCertificate": call.InstallCertificate,
    "RemoteStartTransaction": call.RemoteStartTransaction,
    "RemoteStopTransaction": call.RemoteStopTransaction,
    "ReserveNow": call.ReserveNow,
    "Reset": call.Reset,
    "SendLocalList": call.SendLocalList,
    "SetChargingProfile": call.SetChargingProfile,
    "SignedUpdateFirmware": call.SignedUpdateFirmware,
    "TriggerMessage": call.TriggerMessage,
    "UnlockConnector": call.UnlockConnector,
    "UpdateFirmware": call.UpdateFirmware,
}


def deserialize_ocpp_call(action: str, payload: dict[str, Any]):
    """Deserialize OCPP call from action name and payload dict.

    Args:
        action: OCPP action name (e.g., "RemoteStartTransaction")
        payload: Payload dict with parameters for the call

    Returns:
        Instance of the appropriate OCPP call dataclass

    Raises:
        ValueError: If action is unknown or payload is invalid
    """
    if action not in OCPP_CALL_CLASSES:
        raise ValueError(f"Unknown OCPP action: {action}")

    call_class = OCPP_CALL_CLASSES[action]

    try:
        return call_class(**payload)
    except TypeError as e:
        raise ValueError(f"Invalid payload for {action}: {e}") from e


class UnixSocketCommandInterface:
    """Manages Unix socket-based command interface for sending OCPP commands to charge points."""

    def __init__(
        self,
        socket_path: str,
        server: "OCPPServer",
        db: "Database",
        default_timeout: int = 30,
    ):
        """Initialize Unix socket command interface.

        Args:
            socket_path: Path to Unix domain socket
            server: Reference to OCPPServer for accessing charge_points
            db: Database instance for selector queries
            default_timeout: Default timeout in seconds for OCPP calls
        """
        self.socket_path = Path(socket_path)
        self.server = server
        self.db = db
        self.default_timeout = default_timeout
        self._server: asyncio.Server | None = None

    async def start(self):
        """Start the Unix socket server."""
        # Remove existing socket file if it exists
        if self.socket_path.exists():
            if not stat.S_ISSOCK(self.socket_path.stat().st_mode):
                raise ValueError(f"{self.socket_path} exists but is not a socket")
            self.socket_path.unlink()
            logger.info(f"Removed existing socket at {self.socket_path}")

        # Start Unix socket server
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_path)
        )
        logger.info(f"Unix socket command interface started at {self.socket_path}")

    async def stop(self):
        """Stop the socket server and cleanup."""
        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Unix socket server closed")

        # Remove socket file
        try:
            if self.socket_path.exists():
                self.socket_path.unlink()
                logger.info(f"Removed socket at {self.socket_path}")
        except Exception as e:
            logger.error(f"Failed to remove socket: {e}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle single client connection - read command, write response.

        Args:
            reader: Stream reader for reading command
            writer: Stream writer for writing response
        """
        try:
            # Read one line (command) with timeout
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                return

            # Parse and process command
            command = Command.from_json(line.decode("utf-8").strip())
            logger.info(
                f"Processing socket command {command.command_id}: "
                f"{command.call.action} to {command.selector.type.value}"
            )

            response = await self._process_command(command)

            # Write response back on same connection
            writer.write(response.to_json().encode("utf-8") + b"\n")
            await writer.drain()

            logger.info(
                f"Socket response for {response.command_id}: "
                f"{response.summary['success']}/{response.summary['total']} succeeded"
            )

        except TimeoutError:
            logger.error("Client read timeout after 10s")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in socket command: {e}")
        except Exception as e:
            logger.error(f"Error handling socket client: {e}")
        finally:
            # Always close the connection
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass  # Ignore errors during cleanup

    async def _process_command(self, command: Command) -> CommandResponse:
        """Process a single command and return response.

        Args:
            command: Command to process

        Returns:
            CommandResponse with results for all selected charge points
        """
        # Select charge points
        try:
            cp_ids = await self._select_charge_points(command.selector)
        except Exception as e:
            logger.error(f"Selector error: {e}")
            return CommandResponse.from_results(
                command_id=command.command_id,
                results=[
                    CallResult(
                        cp_id="<selector_error>",
                        status="error",
                        error=f"Selector error: {e}",
                    )
                ],
            )

        # Dispatch call to selected charge points
        results = await self._dispatch_call(
            cp_ids=cp_ids,
            action=command.call.action,
            payload=command.call.payload,
            timeout=command.timeout,
        )

        return CommandResponse.from_results(command_id=command.command_id, results=results)

    async def _select_charge_points(self, selector: Selector) -> list[str]:
        """Select charge point IDs based on selector criteria.

        Args:
            selector: Selector specifying which charge points to target

        Returns:
            List of charge point IDs (only connected charge points)
        """
        if selector.type == SelectorType.ALL:
            # Return all currently connected charge points
            return list(self.server.charge_points.keys())

        if selector.type == SelectorType.IDS:
            # Filter to only connected charge points with given IDs
            requested_ids = set(selector.value or [])
            connected_ids = set(self.server.charge_points.keys())
            return list(requested_ids & connected_ids)

        if selector.type in (SelectorType.IN_TRANSACTION, SelectorType.NOT_IN_TRANSACTION):
            # Query database for charge points with/without active transactions
            conn = await self.db.connect()
            try:
                cp_repo = ChargePointRepository(conn)

                if selector.type == SelectorType.IN_TRANSACTION:
                    cp_ids = await cp_repo.get_with_active_transactions()
                else:
                    cp_ids = await cp_repo.get_without_active_transactions()

                # Filter to only connected charge points
                connected_ids = set(self.server.charge_points.keys())
                return [cp_id for cp_id in cp_ids if cp_id in connected_ids]
            finally:
                # Connection is shared across server with WAL mode
                # Just ensure we don't leave uncommitted transactions
                await conn.rollback()  # Safe no-op if no transaction

        else:
            raise ValueError(f"Unknown selector type: {selector.type}")

    async def _dispatch_call(
        self, cp_ids: list[str], action: str, payload: dict[str, Any], timeout: int
    ) -> list[CallResult]:
        """Dispatch OCPP call to multiple charge points concurrently.

        Args:
            cp_ids: List of charge point IDs to send call to
            action: OCPP action name
            payload: Payload dict for the call
            timeout: Timeout in seconds for each call

        Returns:
            List of CallResult objects, one per charge point
        """
        # Deserialize OCPP call
        try:
            ocpp_call = deserialize_ocpp_call(action, payload)
        except ValueError as e:
            # Return error for all charge points
            return [CallResult(cp_id=cp_id, status="error", error=str(e)) for cp_id in cp_ids]

        # Create task for each charge point
        async def send_to_cp(cp_id: str) -> CallResult:
            """Send call to a single charge point with timeout."""
            try:
                cp = self.server.charge_points.get(cp_id)
                if not cp:
                    return CallResult(
                        cp_id=cp_id, status="error", error="Charge point not connected"
                    )

                # Send call with timeout
                response = await asyncio.wait_for(cp.call(ocpp_call), timeout=timeout)

                # Convert response to dict (OCPP responses have __dict__)
                response_dict = {}
                if hasattr(response, "__dict__"):
                    response_dict = {
                        k: v for k, v in response.__dict__.items() if not k.startswith("_")
                    }

                return CallResult(cp_id=cp_id, status="success", response=response_dict)

            except TimeoutError:
                return CallResult(cp_id=cp_id, status="error", error=f"Timeout after {timeout}s")
            except Exception as e:
                return CallResult(cp_id=cp_id, status="error", error=str(e))

        # Dispatch to all charge points concurrently
        tasks = [send_to_cp(cp_id) for cp_id in cp_ids]
        return await asyncio.gather(*tasks, return_exceptions=False)
