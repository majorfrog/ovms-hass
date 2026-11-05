"""OVMS Home Assistant integration coordinator.

This module provides the data coordinator that fetches vehicle data from OVMS
at regular intervals and manages command execution.

The Protocol v2 TCP connection includes:
- Background reader loop to process all incoming server messages
- Periodic ping (MP-0 A) every 5 minutes to keep the connection alive
- Automatic reconnection on connection failure
- Proper command response handling (waits for 'c' type messages)
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import suppress
from datetime import timedelta
from collections.abc import Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OVMSApiClient,
    OVMSAPIError,
    OVMSCommandNotSent,
    OVMSConnectionError,
    OVMSConnectionLost,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
COMMAND_TIMEOUT = 10  # seconds
SEND_TIMEOUT = 5  # seconds allowed for flushing a command to the socket
PING_INTERVAL = 120  # 2 minutes
RECONNECT_DELAY = 3  # seconds before reconnect attempt

# Seconds after AC ON/OFF at which v.e.hvac is queried
HVAC_FOLLOWUP_DELAYS = (15, 60)
# Command 7 runs a module shell command; its output comes back in the reply
HVAC_QUERY_COMMAND = "7,metrics get v.e.hvac"
_HVAC_TRUE = {"yes", "1", "true", "on"}
_HVAC_FALSE = {"no", "0", "false", "off"}

# Protocol v2 command result codes (0 = success)
COMMAND_RESULT_REASONS = {1: "failed", 2: "not supported", 3: "not implemented"}


class OVMSCommandError(HomeAssistantError):
    """Raised when a command did not reach the car or was not accepted."""


class OVMSDataCoordinator(DataUpdateCoordinator):
    """Coordinator to manage OVMS data fetching and updates.

    Fetches vehicle status, charging, and location data from the OVMS REST API
    at regular intervals. Also manages command execution via the Protocol v2 client.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OVMSApiClient,
        vehicle_id: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance
            api_client: OVMS REST API client
            vehicle_id: OVMS vehicle ID
            scan_interval: Update interval in seconds
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"OVMS {vehicle_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api_client = api_client
        self.vehicle_id = vehicle_id
        self.ovms_client: OVMSProtocolClient | None = None
        self._hvac_followup_unsubs: list[CALLBACK_TYPE] = []
        self._hvac_query_task: asyncio.Task | None = None
        self.data: dict[str, Any] = {
            "vehicle_id": vehicle_id,
            "vehicle_name": vehicle_id,
            "status": {},
            "charge": {},
            "location": {},
            "tpms": {},
            "features": {},
            "vehicle": {},
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from OVMS API.

        Returns:
            Dictionary containing all vehicle data

        Raises:
            UpdateFailed: If connection to OVMS fails
        """
        try:
            # Fetch vehicle status data in parallel for efficiency
            status_task = self.api_client.get_status(self.vehicle_id)
            charge_task = self.api_client.get_charge(self.vehicle_id)
            location_task = self.api_client.get_location(self.vehicle_id)
            tpms_task = self.api_client.get_tpms(self.vehicle_id)
            features_task = self._fetch_features()
            vehicle_task = self._fetch_vehicle_connection()

            status, charge, location, tpms, features, vehicle = await asyncio.gather(
                status_task,
                charge_task,
                location_task,
                tpms_task,
                features_task,
                vehicle_task,
                return_exceptions=True,
            )

            # Update data dictionary with results, filtering out exceptions
            self.data["status"] = (
                status.__dict__ if not isinstance(status, Exception) else {}
            )
            self.data["charge"] = (
                charge.__dict__ if not isinstance(charge, Exception) else {}
            )
            self.data["location"] = (
                location.__dict__ if not isinstance(location, Exception) else {}
            )
            self.data["tpms"] = tpms.__dict__ if not isinstance(tpms, Exception) else {}
            self.data["features"] = (
                features if not isinstance(features, Exception) else {}
            )
            self.data["vehicle"] = vehicle if not isinstance(vehicle, Exception) else {}

            # Merge data from Protocol v2 messages (F, D, etc.)
            # These fill in fields not available via the REST API
            # (e.g., HVAC from D message, GSM signal from F message)
            if self.ovms_client and self.ovms_client.protocol_data:
                for key, value in self.ovms_client.protocol_data.items():
                    if value is not None:
                        self.data["status"][key] = value

            # Log any exceptions that occurred (not as errors, just debug)
            for task_name, result in [
                ("status", status),
                ("charge", charge),
                ("location", location),
                ("tpms", tpms),
                ("features", features),
                ("vehicle", vehicle),
            ]:
                if isinstance(result, Exception):
                    _LOGGER.debug(
                        "Failed to fetch %s for %s: %s",
                        task_name,
                        self.vehicle_id,
                        result,
                    )

            return self.data

        except OVMSConnectionError as err:
            raise UpdateFailed(f"Connection to OVMS failed: {err}") from err
        except OVMSAPIError as err:
            raise UpdateFailed(f"OVMS API error: {err}") from err

    @callback
    def async_handle_protocol_data(self, changed: dict[str, Any]) -> None:
        """Merge pushed Protocol v2 values into the data and update entities now.

        Uses async_update_listeners, not async_set_updated_data: the latter
        reschedules the next poll, so frequent D/F messages would keep
        postponing the REST refresh.
        """
        status = self.data.setdefault("status", {})
        for key, value in changed.items():
            if value is not None:
                status[key] = value
        self.async_update_listeners()

    async def async_query_hvac(self) -> bool | None:
        """Read v.e.hvac from the module and push it to the HVAC state.

        Returns:
            The HVAC state, or None if the reply could not be parsed

        Raises:
            OVMSCommandError: If the query was not sent or not acknowledged
        """
        response = await self.async_send_command(
            HVAC_QUERY_COMMAND, "HVAC status query"
        )
        value = _parse_hvac_reply(response.get("message", ""))
        if value is None:
            _LOGGER.debug("Unrecognised v.e.hvac reply: %r", response.get("message"))
            return None
        # Through protocol_data, so the next REST poll keeps this value.
        self.ovms_client.update_protocol_data({"hvac": value})
        return value

    @callback
    def async_schedule_hvac_followup(self) -> None:
        """Query v.e.hvac at each HVAC_FOLLOWUP_DELAYS after an AC command."""
        self.async_cancel_hvac_followup()
        for delay in HVAC_FOLLOWUP_DELAYS:
            self._hvac_followup_unsubs.append(
                async_call_later(self.hass, delay, self._async_hvac_followup_fire)
            )

    @callback
    def _async_hvac_followup_fire(self, _now: Any) -> None:
        """Start one follow-up query unless one is still running."""
        if self._hvac_query_task and not self._hvac_query_task.done():
            return
        self._hvac_query_task = self.hass.async_create_background_task(
            self._async_hvac_followup_query(), f"OVMS {self.vehicle_id} HVAC query"
        )

    async def _async_hvac_followup_query(self) -> None:
        try:
            value = await self.async_query_hvac()
        except OVMSCommandError as err:
            _LOGGER.warning("HVAC follow-up query failed: %s", err)
            return
        _LOGGER.debug("HVAC follow-up query: hvac=%s", value)

    @callback
    def async_cancel_hvac_followup(self) -> None:
        """Cancel pending follow-up queries and one that is running."""
        for unsub in self._hvac_followup_unsubs:
            unsub()
        self._hvac_followup_unsubs.clear()
        if self._hvac_query_task and not self._hvac_query_task.done():
            self._hvac_query_task.cancel()

    async def _fetch_features(self) -> dict[int, str]:
        """Fetch vehicle features via command 1.

        Returns:
            Dictionary mapping feature slot to value
        """
        if not self.ovms_client:
            return {}

        try:
            # Send command 1 to request features
            # Response format: "MP-0 c1,0,fn,fm,fv" where fn=feature number, fm=max features, fv=value
            # We'll parse the response to build features dict
            # For now, return empty dict as feature parsing requires response handling
            # This will be populated when we receive feature responses
            return self.data.get("features", {})
        except (OVMSConnectionError, OVMSAPIError) as err:
            _LOGGER.debug("Failed to fetch features: %s", err)
            return {}

    async def _fetch_vehicle_connection(self) -> dict[str, int]:
        """Fetch vehicle connection status from API.

        Returns:
            Dictionary with v_net_connected, v_apps_connected, v_btcs_connected
        """
        try:
            # The /api/vehicle/<VEHICLEID> endpoint returns connection info
            response = await self.api_client.get_vehicle(self.vehicle_id)
            return {
                "v_net_connected": response.get("v_net_connected", 0),
                "v_apps_connected": response.get("v_apps_connected", 0),
                "v_btcs_connected": response.get("v_btcs_connected", 0),
            }
        except (OVMSConnectionError, OVMSAPIError) as err:
            _LOGGER.debug("Failed to fetch vehicle connection: %s", err)
            return {
                "v_net_connected": 0,
                "v_apps_connected": 0,
                "v_btcs_connected": 0,
            }

    async def async_send_command(
        self, command: str, label: str | None = None
    ) -> dict[str, Any]:
        """Send a command to the vehicle and return the car's acknowledgement.

        A command is only retried when nothing was written to the server.
        Once it may have reached the car (missing ack, connection lost after
        the write) it is never resent, so toggle-type commands such as
        HomeLink cannot fire twice.

        Args:
            command: Command string (e.g., "26,1" for AC ON)
            label: Short name used in log lines and error messages

        Returns:
            Reply dict with 'code', 'result' (0) and 'message'

        Raises:
            OVMSCommandError: If the command was not sent, not acknowledged
                or rejected
        """
        label = label or command
        vid = self.vehicle_id
        _LOGGER.info("Coordinator: Sending %s (%s)", label, command)

        for attempt in (1, 2):
            if not await self._ensure_protocol_connection():
                _LOGGER.error("Coordinator: No Protocol v2 connection, %s not sent", label)
                raise OVMSCommandError(
                    f"{vid}: no connection to the OVMS server, {label} not sent"
                )

            try:
                response = await self.ovms_client.async_command(
                    command, COMMAND_TIMEOUT
                )
            except OVMSCommandNotSent as err:
                _LOGGER.error(
                    "Coordinator: %s not sent on attempt %d/2: %s", label, attempt, err
                )
                await self.ovms_client.disconnect(intentional=False)
                continue
            except OVMSConnectionLost as err:
                _LOGGER.error("Coordinator: Connection lost after sending %s: %s", label, err)
                raise OVMSCommandError(
                    f"{vid}: connection lost after sending {label}, "
                    "it may not have reached the car"
                ) from err

            if response is None:
                _LOGGER.error("Coordinator: %s was not acknowledged", label)
                # Usually a half-open TCP connection: drop it and reconnect in
                # the background so pushed data comes back without a command.
                await self.ovms_client.disconnect(intentional=False)
                self.ovms_client.start_reconnect()
                raise OVMSCommandError(f"{vid} did not acknowledge {label}")

            _LOGGER.info(
                "Coordinator: Command response: code=%s, result=%s, message=%s",
                response.get("code"),
                response.get("result"),
                response.get("message", ""),
            )
            result = response.get("result")
            if result != 0:
                reason = COMMAND_RESULT_REASONS.get(result, f"result {result}")
                if response.get("message"):
                    reason = f"{reason}: {response['message']}"
                _LOGGER.error("Coordinator: %s rejected (%s)", label, reason)
                raise OVMSCommandError(f"{vid} rejected {label} ({reason})")

            _LOGGER.info("Coordinator: %s acknowledged", label)
            await self.async_request_refresh()
            return response

        _LOGGER.error("Coordinator: %s could not be sent after retry", label)
        raise OVMSCommandError(f"{vid}: {label} could not be sent")

    async def _ensure_protocol_connection(self) -> bool:
        """Ensure the Protocol v2 TCP connection is alive, reconnecting if needed.

        Returns:
            True if connected and authenticated
        """
        client = self.ovms_client
        if not client:
            return False

        if client.connected and client.authenticated:
            return True

        if not client._auto_reconnect_enabled:
            # Integration is unloading/unloaded: never open a new connection.
            return False

        async with client._reconnect_lock:
            if client.connected and client.authenticated:
                return True
            _LOGGER.info("Coordinator: Protocol v2 connection is down, attempting reconnect...")
            try:
                await client.disconnect(intentional=False)
                await client.connect()
                client.start_background_reader()
                _LOGGER.info("Coordinator: Protocol v2 reconnected successfully")
                return True
            except (OVMSConnectionError, OVMSAPIError) as err:
                _LOGGER.error("Coordinator: Failed to reconnect Protocol v2: %s", err)
            except Exception as err:
                _LOGGER.exception("Coordinator: Unexpected error during reconnect: %s", err)
        # The failed attempt cancelled any background loop; start it again.
        client.start_reconnect()
        return False


def _parse_hvac_reply(message: str) -> bool | None:
    """Parse the output of `metrics get v.e.hvac` (or `metrics list v.e.hvac`).

    Accepts a bare value ("yes") or a "name value" line ("v.e.hvac   yes").
    """
    for line in message.splitlines():
        tokens = line.split()
        if len(tokens) == 1 or (len(tokens) >= 2 and tokens[0] == "v.e.hvac"):
            token = tokens[-1].lower()
            if token in _HVAC_TRUE:
                return True
            if token in _HVAC_FALSE:
                return False
    return None


class RC4:
    """RC4 stream cipher implementation for OVMS Protocol v2."""

    def __init__(self, key: bytes) -> None:
        """Initialize RC4 cipher with key.

        Args:
            key: Encryption key bytes
        """
        self.state = list(range(256))
        self.x = 0
        self.y = 0

        # Key scheduling algorithm (KSA)
        j = 0
        for i in range(256):
            j = (j + self.state[i] + key[i % len(key)]) % 256
            self.state[i], self.state[j] = self.state[j], self.state[i]

    def crypt(self, data: bytes) -> bytes:
        """Encrypt or decrypt data using RC4.

        Args:
            data: Data to encrypt/decrypt

        Returns:
            Encrypted/decrypted data
        """
        result = bytearray()
        for byte in data:
            self.x = (self.x + 1) % 256
            self.y = (self.y + self.state[self.x]) % 256
            self.state[self.x], self.state[self.y] = (
                self.state[self.y],
                self.state[self.x],
            )
            k = self.state[(self.state[self.x] + self.state[self.y]) % 256]
            result.append(byte ^ k)
        return bytes(result)


class OVMSProtocolClient:
    """OVMS Protocol v2 client with RC4 encryption and HMAC-MD5 authentication.

    Implements the OVMS MP (Message Protocol) v2 for communicating with OVMS servers.
    The protocol uses:
    - TCP connection on port 6867 (plaintext) or 6870 (TLS)
    - HMAC-MD5 for authentication handshake
    - RC4 encryption for message payload
    - Base64 encoding for transport

    This client maintains a background reader loop to:
    - Keep the TCP connection alive with periodic pings
    - Process incoming server messages continuously
    - Properly handle command responses via an asyncio Event
    - Detect connection failures and enable reconnection
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        vehicle_id: str,
        port: int = 6870,
        use_tls: bool = True,
    ) -> None:
        """Initialize Protocol v2 client.

        Args:
            host: OVMS server hostname or IP
            username: OVMS username
            password: OVMS password
            vehicle_id: Vehicle ID to connect to
            port: Server port (6870 for TLS, 6867 for plaintext)
            use_tls: Use TLS encryption
        """
        self.host = host
        self.username = username
        self.password = password
        self.vehicle_id = vehicle_id
        self.port = port
        self.use_tls = use_tls
        self.connected = False
        self.authenticated = False
        self._reader: Any | None = None
        self._writer: Any | None = None
        self._tx_cipher: RC4 | None = None
        self._rx_cipher: RC4 | None = None
        self._token: str = ""
        # Background tasks
        self._reader_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        # Command response handling
        self._command_response: dict[str, Any] | None = None
        self._command_event: asyncio.Event = asyncio.Event()
        # Lock held for a whole command round-trip (send + wait for reply)
        self._command_lock: asyncio.Lock = asyncio.Lock()
        # Code of the command waiting for a reply, None when idle
        self._pending_code: int | None = None
        # Set when the connection drops while a command waits for its reply
        self._connection_lost = False
        # Lock and task for automatic reconnect on unexpected disconnects
        self._reconnect_lock: asyncio.Lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
        self._auto_reconnect_enabled = True
        # Data parsed from Protocol v2 messages (F, D, etc.)
        self.protocol_data: dict[str, Any] = {}
        # Called with the changed keys whenever protocol_data changes
        self.on_protocol_data: Callable[[dict[str, Any]], None] | None = None

    async def connect(self) -> None:
        """Establish connection to OVMS server and authenticate.

        1. Client connects to server
        2. CLIENT sends first: "MP-A 0 <client_token> <client_digest> <vehicle_id>"
        3. Server responds: "MP-A 0 <result> <server_token> <server_digest>"
        4. Both sides derive RC4 keys from server_token + client_token

        Raises:
            OVMSConnectionError: If connection or authentication fails
        """
        import hashlib
        import hmac

        try:
            _LOGGER.debug(
                "Connecting to OVMS server %s:%d (TLS: %s)",
                self.host,
                self.port,
                self.use_tls,
            )

            if self.use_tls:
                # Pre-create SSL context outside the event loop to avoid blocking call
                loop = asyncio.get_event_loop()
                ssl_context = await loop.run_in_executor(
                    None, ssl.create_default_context
                )
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=ssl_context,
                )
            else:
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                )

            self._reader = reader
            self._writer = writer
            self.connected = True
            _LOGGER.info("Connected to OVMS server %s:%d", self.host, self.port)

            # Generate client token - 22 random Base64 characters
            import random
            import base64

            b64_chars = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            )
            client_token = "".join(random.choice(b64_chars) for _ in range(22))
            self._token = client_token
            _LOGGER.debug("Generated client token: %s", client_token)

            # Calculate client digest using HMAC-MD5
            # Key = password (UTF-8), Message = client_token as bytes
            # Digest is Base64 encoded (not hex!)
            auth_key = self.password.encode("utf-8")
            client_token_bytes = client_token.encode("utf-8")
            client_hmac = hmac.new(auth_key, client_token_bytes, hashlib.md5)
            client_digest = base64.b64encode(client_hmac.digest()).decode("ascii")
            _LOGGER.debug("Generated client digest: %s", client_digest)

            # CLIENT sends first (this is the key difference from old implementation!)
            # Format: "MP-A 0 <client_token> <client_digest> <vehicle_id>"
            auth_request = (
                f"MP-A 0 {client_token} {client_digest} {self.vehicle_id}\r\n"
            )
            _LOGGER.debug(
                "Sending auth request: MP-A 0 %s %s %s",
                client_token,
                client_digest,
                self.vehicle_id,
            )
            writer.write(auth_request.encode("utf-8"))
            await writer.drain()

            # Read server response
            # Format: "MP-A 0 <result> <server_token> <server_digest>"
            # Or space-separated: ["MP-A", "0", result, server_token, server_digest]
            _LOGGER.debug("Waiting for server auth response...")
            response = await asyncio.wait_for(reader.readline(), timeout=30)

            if not response:
                raise OVMSConnectionError("No response from server")

            # Parse only the first line of response
            response_str = response.decode("utf-8", errors="replace").strip()
            first_line = response_str.split("\n")[0].strip()
            _LOGGER.debug("Server response (first line): %s", first_line)

            # Parse space-separated response
            parts = first_line.split()
            _LOGGER.debug("Response parts: %s", parts)

            # Server responds with MP-S (Server) or MP-A (Authentication)
            if len(parts) < 4 or parts[0] not in ("MP-A", "MP-S") or parts[1] != "0":
                raise OVMSConnectionError(
                    f"Invalid server response format: {first_line}"
                )

            # Format: MP-S 0 <server_token> <server_digest>
            server_token = parts[2]
            server_digest = parts[3]

            _LOGGER.debug("Server token: %s", server_token)
            _LOGGER.debug("Server digest: %s", server_digest)

            # Verify server's digest (Base64 encoded HMAC-MD5)
            # Server digest = Base64(HMAC-MD5(password, server_token))
            expected_server_digest = base64.b64encode(
                hmac.new(auth_key, server_token.encode("utf-8"), hashlib.md5).digest()
            ).decode("ascii")

            if server_digest != expected_server_digest:
                _LOGGER.warning(
                    "Server digest mismatch! Expected %s, got %s",
                    expected_server_digest,
                    server_digest,
                )
                # Some servers may not send correct digest, continue anyway

            # Derive RC4 encryption key
            # Key = HMAC-MD5(password, server_token + client_token)
            # Both TX and RX use the same key
            server_client_token = server_token + client_token
            crypto_key = hmac.new(
                auth_key, server_client_token.encode("utf-8"), hashlib.md5
            ).digest()
            _LOGGER.debug("Derived crypto key from: %s", server_client_token)

            # Initialize RC4 ciphers (same key for both directions)
            self._tx_cipher = RC4(crypto_key)
            self._rx_cipher = RC4(crypto_key)

            # Prime the ciphers with 1024 zero bytes
            # This discards the first 1024 bytes of keystream for security
            prime_data = bytes(1024)
            self._tx_cipher.crypt(prime_data)
            self._rx_cipher.crypt(prime_data)
            _LOGGER.debug("Primed RC4 ciphers with 1024 zero bytes")

            self.authenticated = True

            _LOGGER.info(
                "Successfully authenticated with OVMS server for vehicle %s",
                self.vehicle_id,
            )

        except TimeoutError as err:
            self.connected = False
            raise OVMSConnectionError(
                "Connection timeout during authentication"
            ) from err
        except Exception as err:
            self.connected = False
            _LOGGER.exception("Failed to connect/authenticate with OVMS server")
            raise OVMSConnectionError(f"Failed to connect to OVMS: {err}") from err

    async def disconnect(self, intentional: bool = True) -> None:
        """Close connection to OVMS server and stop background tasks.

        Args:
            intentional: True when caller is intentionally shutting down.
                False for transient reconnect workflows.
        """
        if intentional:
            self._auto_reconnect_enabled = False

        if (
            self._reconnect_task
            and not self._reconnect_task.done()
            and asyncio.current_task() is not self._reconnect_task
        ):
            self._reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None

        # Stop background tasks first
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._ping_task
            self._ping_task = None

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self._writer:
            self._writer.close()
            with suppress(Exception):
                await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self.connected = False
        self.authenticated = False
        self._tx_cipher = None
        self._rx_cipher = None
        self._wake_pending_command()
        _LOGGER.debug("Disconnected from OVMS server")

    def start_background_reader(self) -> None:
        """Start the background reader loop and ping timer.

        Should be called after a successful connect() and authentication.
        The background reader continuously reads server messages, keeping the RC4 cipher in sync and
        enabling proper command response handling.
        """
        if not self.connected or not self.authenticated:
            _LOGGER.warning("Cannot start background reader - not connected/authenticated")
            return

        # Start the reader loop
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.ensure_future(self._background_reader_loop())
            _LOGGER.info("Background reader loop started")

        # Start the ping timer
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.ensure_future(self._ping_loop())
            _LOGGER.info("Ping keepalive started (interval: %ds)", PING_INTERVAL)

    async def _background_reader_loop(self) -> None:
        """Continuously read and process messages from the OVMS server.

        This background reader loop is essential for maintaining the Protocol v2 connection. It:
        - Keeps the RC4 RX cipher state in sync by processing all messages
        - Routes command responses to the command_event for send_command callers
        - Detects connection drops (EOF or read errors)
        - Logs all received message types for debugging
        """
        _LOGGER.debug("Background reader loop: starting")
        try:
            while self.connected and self._reader:
                try:
                    data = await self._reader.readline()

                    if not data:
                        # EOF - connection closed by server
                        _LOGGER.warning("Background reader: Connection closed by server (EOF)")
                        break

                    response = data.decode("utf-8").strip()
                    if not response:
                        continue

                    # Decrypt the message
                    if not self._rx_cipher:
                        _LOGGER.warning("Background reader: No RX cipher available")
                        break

                    decrypted = self._decrypt_message(response)

                    # Validate message format
                    if not decrypted.startswith("MP-0 "):
                        _LOGGER.debug(
                            "Background reader: Non-MP message: %s",
                            decrypted[:60] if len(decrypted) > 60 else decrypted,
                        )
                        continue

                    # Extract message type and payload
                    msg_type = decrypted[5:6]
                    payload = decrypted[6:]

                    if msg_type == "c":
                        # Command response - signal the waiting command sender
                        _LOGGER.debug("Background reader: Command response: %s", payload)
                        self._handle_command_response(payload)
                    elif msg_type == "F":
                        # Firmware info - parse for GSM signal, car type, etc.
                        _LOGGER.debug("Background reader: Firmware info: %s", payload)
                        self._parse_firmware_message(payload)
                    elif msg_type == "D":
                        # Environment/doors - parse for HVAC, etc.
                        self._parse_environment_message(payload)
                    elif msg_type in ("S", "T", "L", "a"):
                        # High-frequency messages (status, timestamp,
                        # location, ping ack) — processed silently to keep RC4
                        # cipher in sync without spamming the log.
                        pass
                    elif msg_type == "P":
                        _LOGGER.debug("Background reader: Push notification: %s", payload)
                    elif msg_type == "Z":
                        _LOGGER.debug("Background reader: Cars connected: %s", payload)
                    elif msg_type == "V":
                        _LOGGER.debug("Background reader: Capabilities: %s", payload)
                    else:
                        _LOGGER.debug(
                            "Background reader: Message type '%s': %s",
                            msg_type,
                            payload[:80] if len(payload) > 80 else payload,
                        )

                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.error("Background reader: Error reading message: %s", err)
                    break

        except asyncio.CancelledError:
            _LOGGER.debug("Background reader loop cancelled")
            return

        # If we get here, the connection dropped
        _LOGGER.warning("Background reader: Connection lost, marking as disconnected")
        self.connected = False
        self.authenticated = False
        self._wake_pending_command()
        await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        """Schedule automatic reconnect after an unexpected disconnect."""
        self.start_reconnect()

    def start_reconnect(self) -> None:
        """Start the background reconnect loop unless it is running or disabled."""
        if not self._auto_reconnect_enabled:
            _LOGGER.debug("Auto-reconnect disabled, not scheduling reconnect")
            return

        if self._reconnect_task and not self._reconnect_task.done():
            _LOGGER.debug("Reconnect task already active")
            return

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Try to restore Protocol v2 connection in the background."""
        delay = RECONNECT_DELAY
        max_delay = 60

        while self._auto_reconnect_enabled and not self.connected:
            async with self._reconnect_lock:
                if self.connected:
                    return

                try:
                    _LOGGER.info(
                        "Protocol v2 auto-reconnect: reconnecting to %s:%d",
                        self.host,
                        self.port,
                    )
                    await self.disconnect(intentional=False)
                    await self.connect()
                    self.start_background_reader()
                    _LOGGER.info("Protocol v2 auto-reconnect successful")
                    return
                except OVMSConnectionError as err:
                    _LOGGER.warning(
                        "Protocol v2 auto-reconnect failed, retrying in %ds: %s",
                        delay,
                        err,
                    )

            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)

    def _handle_command_response(self, payload: str) -> None:
        """Parse a command response and signal the waiting caller.

        Response format: "<code>,<result_code>[,<message>]"

        Args:
            payload: Command response payload (without the 'c' prefix)
        """
        parts = payload.split(",", 2)
        response = {
            "code": int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None,
            "result": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            "message": parts[2] if len(parts) > 2 else "",
        }
        if self._pending_code is None or response["code"] != self._pending_code:
            _LOGGER.debug(
                "Unmatched command response %s (waiting for %s)",
                payload,
                self._pending_code,
            )
            return
        self._command_response = response
        self._command_event.set()

    def _wake_pending_command(self) -> None:
        """Wake a command waiting for its reply because the connection dropped."""
        self._command_response = None
        if self._pending_code is not None:
            self._connection_lost = True
            self._command_event.set()
        else:
            self._command_event.clear()

    def _parse_firmware_message(self, payload: str) -> None:
        """Parse firmware message (Protocol v2 type F).

        OVMS v3 F message CSV format:
          0: firmware version
          1: VIN
          2: network signal quality (dBm)
          3: canwrite (0/1)
          4: car type
          5: network provider
          6: service range
          7: service time
          8: hardware version
          9: modem mode

        Args:
            payload: CSV payload after the 'F' type character
        """
        parts = payload.split(",")
        data: dict[str, Any] = {}

        if len(parts) > 0 and parts[0]:
            data["m_firmware"] = parts[0]
        if len(parts) > 1 and parts[1]:
            data["car_vin"] = parts[1]
        if len(parts) > 2 and parts[2]:
            try:
                data["car_gsm_signal"] = int(float(parts[2]))
            except (ValueError, TypeError):
                pass
        if len(parts) > 4 and parts[4]:
            data["car_type"] = parts[4]
        if len(parts) > 8 and parts[8]:
            data["m_hardware"] = parts[8]
        if len(parts) > 9 and parts[9]:
            data["m_mdm_mode"] = parts[9]

        if data:
            _LOGGER.debug("Parsed firmware data: %s", data)
            self.update_protocol_data(data)

    def update_protocol_data(self, data: dict[str, Any]) -> None:
        """Merge parsed values and notify the callback about the ones that changed.

        Runs inside the reader loop, so a failing callback is logged here and
        never propagates (the loop would otherwise drop the connection).
        """
        changed = {
            key: value
            for key, value in data.items()
            if key not in self.protocol_data or self.protocol_data[key] != value
        }
        self.protocol_data.update(data)
        if not changed or self.on_protocol_data is None:
            return
        try:
            self.on_protocol_data(changed)
        except Exception:
            _LOGGER.exception("Error handling pushed OVMS data %s", changed)

    def _parse_environment_message(self, payload: str) -> None:
        """Parse environment/doors message (Protocol v2 type D).

        OVMS v3 D message CSV format (relevant fields):
          0: doors1 byte
          ...
          17: doors5 byte - bit 7 (0x80) = HVAC active

        Args:
            payload: CSV payload after the 'D' type character
        """
        parts = payload.split(",")

        # doors5 is at index 17
        if len(parts) > 17 and parts[17]:
            try:
                doors5 = int(parts[17])
            except (ValueError, TypeError):
                return
            hvac = bool(doors5 & 0x80)
            _LOGGER.debug("D message: doors5=%s hvac=%s", doors5, hvac)
            self.update_protocol_data({"hvac": hvac})

    async def _ping_loop(self) -> None:
        """Send periodic ping messages to keep the connection alive.

        Sends 'MP-0 A' every 5 minutes. This prevents
        NAT/firewall timeouts from silently killing the TCP connection.
        """
        try:
            while self.connected:
                await asyncio.sleep(PING_INTERVAL)
                if not self.connected or not self._writer:
                    break
                try:
                    _LOGGER.debug("Sending ping (MP-0 A)")
                    await self._send_encrypted_message("MP-0 A")
                    _LOGGER.debug("Ping sent successfully")
                except (OVMSConnectionError, OSError) as err:
                    _LOGGER.warning("Ping failed, connection may be dead: %s", err)
                    self.connected = False
                    self.authenticated = False
                    self.start_reconnect()
                    break
        except asyncio.CancelledError:
            _LOGGER.debug("Ping loop cancelled")

    async def _send_encrypted_message(self, message: str) -> None:
        """Encrypt and send a message over the TCP connection.

        Args:
            message: Plaintext message to send (e.g., "MP-0 A" or "MP-0 C26,1")

        Raises:
            OVMSConnectionError: If not connected or send fails
        """
        self._write_encrypted(message)
        await self._writer.drain()

    def _write_encrypted(self, message: str) -> None:
        """Encrypt a message and hand it to the socket writer.

        Raises:
            OVMSCommandNotSent: If nothing could be written
        """
        if not self.connected or not self._writer:
            raise OVMSCommandNotSent("Not connected to OVMS server")
        if not self._tx_cipher:
            raise OVMSCommandNotSent("Not authenticated - no TX cipher")
        if self._writer.is_closing():
            # asyncio drops writes on a closing transport without raising.
            raise OVMSCommandNotSent("Connection is closing")

        encrypted = self._encrypt_message(message)
        try:
            self._writer.write(f"{encrypted}\r\n".encode("utf-8"))
        except Exception as err:
            raise OVMSCommandNotSent(f"Write failed: {err}") from err

    def _encrypt_message(self, message: str) -> str:
        """Encrypt a message using RC4 and base64 encode.

        Args:
            message: Plaintext message

        Returns:
            Base64 encoded encrypted message
        """
        import base64

        if not self._tx_cipher:
            raise OVMSConnectionError("Not authenticated - no TX cipher")

        encrypted = self._tx_cipher.crypt(message.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def _decrypt_message(self, encoded: str) -> str:
        """Decrypt a base64 encoded RC4 encrypted message.

        Args:
            encoded: Base64 encoded encrypted message

        Returns:
            Decrypted plaintext message
        """
        import base64

        if not self._rx_cipher:
            raise OVMSConnectionError("Not authenticated - no RX cipher")

        encrypted = base64.b64decode(encoded)
        decrypted = self._rx_cipher.crypt(encrypted)
        return decrypted.decode("utf-8", errors="replace")

    async def async_command(
        self, command: str, timeout: float
    ) -> dict[str, Any] | None:
        """Send a command and wait for the reply with the same command code.

        The lock covers the whole round-trip, so concurrent commands cannot
        take each other's replies. The pending code is set before writing, so
        a reply that arrives while the write is still draining is kept.

        Args:
            command: Command string (e.g., "26,1" for climate ON)
            timeout: Seconds to wait for the reply

        Returns:
            Reply dict with 'code', 'result', 'message', or None if no
            matching reply arrived within the timeout

        Raises:
            OVMSCommandNotSent: Nothing was written (safe to retry)
            OVMSConnectionLost: The command may have been written
        """
        message = f"MP-0 C{command}"
        async with self._command_lock:
            self._pending_code = int(command.split(",", 1)[0])
            self._connection_lost = False
            self._command_response = None
            self._command_event.clear()
            try:
                _LOGGER.debug("Sending command: %s", message)
                self._write_encrypted(message)
                try:
                    async with asyncio.timeout(SEND_TIMEOUT):
                        await self._writer.drain()
                except (TimeoutError, OSError, AttributeError) as err:
                    raise OVMSConnectionLost(
                        f"Connection failed while sending: {err!r}"
                    ) from err

                try:
                    await asyncio.wait_for(self._command_event.wait(), timeout)
                except TimeoutError:
                    _LOGGER.debug(
                        "Timed out waiting for reply to %s after %ss", command, timeout
                    )
                    # Probably a half-open socket: mark it down before releasing
                    # the lock, so a queued command reconnects instead of writing
                    # into it.
                    self.connected = False
                    self.authenticated = False
                    return None
                if self._connection_lost:
                    raise OVMSConnectionLost(
                        "Connection lost while waiting for the reply"
                    )
                return self._command_response
            finally:
                self._pending_code = None
