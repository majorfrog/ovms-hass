"""OVMS Home Assistant integration coordinator.

This module provides the data coordinator that fetches vehicle data from OVMS
at regular intervals and manages command execution.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
import ssl
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OVMSApiClient, OVMSAPIError, OVMSConnectionError

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
COMMAND_TIMEOUT = 10  # seconds


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

    async def async_send_command(self, command: str) -> bool:
        """Send a command to the vehicle via Protocol v2.

        Args:
            command: Command string (e.g., "26,1" for AC ON)

        Returns:
            True if command was sent successfully
        """
        _LOGGER.info("Coordinator: Attempting to send command: %s", command)
        
        if not self.ovms_client:
            _LOGGER.error("Coordinator: Protocol v2 client not connected")
            return False

        if not self.ovms_client.connected:
            _LOGGER.error(
                "Coordinator: Protocol v2 client is not connected to OVMS server (connected=%s, authenticated=%s)",
                self.ovms_client.connected,
                getattr(self.ovms_client, 'authenticated', 'N/A'),
            )
            return False

        _LOGGER.info(
            "Coordinator: Protocol client status - connected=%s, authenticated=%s",
            self.ovms_client.connected,
            getattr(self.ovms_client, 'authenticated', 'N/A'),
        )

        try:
            timeout = asyncio.timeout(COMMAND_TIMEOUT)
            async with timeout:
                _LOGGER.info("Coordinator: Calling ovms_client.send_command(%s)", command)
                await self.ovms_client.send_command(command)
                _LOGGER.info("Coordinator: Command sent successfully, waiting for response...")

                # Try to read response
                response = await self.ovms_client.read_response(timeout=5)
                if response:
                    _LOGGER.info("Coordinator: Command response received: %s", response)
                else:
                    _LOGGER.warning("Coordinator: No response received for command: %s", command)

                # Refresh data after command execution
                _LOGGER.debug("Coordinator: Triggering data refresh after command")
                await self.async_request_refresh()
                return True
        except TimeoutError:
            _LOGGER.error(
                "Coordinator: Command timeout after %d seconds: %s", COMMAND_TIMEOUT, command
            )
            return False
        except (OVMSConnectionError, OVMSAPIError) as err:
            _LOGGER.error("Coordinator: Failed to send command %s: %s", command, err)
            return False


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

    async def disconnect(self) -> None:
        """Close connection to OVMS server."""
        if self._writer:
            self._writer.close()
            with suppress(Exception):
                await self._writer.wait_closed()
        self.connected = False
        self.authenticated = False
        self._tx_cipher = None
        self._rx_cipher = None
        _LOGGER.debug("Disconnected from OVMS server")

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

    async def send_command(self, command: str) -> None:
        """Send command to vehicle.

        Args:
            command: Command string (e.g., "26,1" for climate ON)

        Raises:
            OVMSConnectionError: If not connected or send fails
        """
        if not self.connected or not self._writer:
            _LOGGER.error("Cannot send command - not connected to OVMS server")
            raise OVMSConnectionError("Not connected to OVMS server")

        if not self.authenticated or not self._tx_cipher:
            _LOGGER.error("Cannot send command - not authenticated")
            raise OVMSConnectionError("Not authenticated with OVMS server")

        # Build the command message
        # Format: "MP-0 C<command_code>,<parameters>"
        # The command string is like "26,1" - command code 26, parameter 1
        message = f"MP-0 C{command}"
        _LOGGER.debug("Sending command: %s", message)

        try:
            # Encrypt the message with RC4 and Base64 encode
            encrypted = self._encrypt_message(message)

            # Send just the encrypted Base64 string (with newline)
            full_message = f"{encrypted}\r\n"
            self._writer.write(full_message.encode("utf-8"))
            await self._writer.drain()
            _LOGGER.debug(
                "Command sent successfully (encrypted: %s...)", encrypted[:20]
            )

        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            raise OVMSConnectionError(f"Failed to send command: {err}") from err

    async def read_response(self, timeout: int = 5) -> str | None:
        """Read and decrypt response from server.

        After authentication, all messages from the server are encrypted:
        - Server sends Base64 encoded RC4 encrypted data
        - Decrypted message format: "MP-0 <code><data>"

        Args:
            timeout: Read timeout in seconds

        Returns:
            Decrypted response string or None if timeout

        Raises:
            OVMSConnectionError: If not connected
        """
        if not self.connected or not self._reader:
            raise OVMSConnectionError("Not connected to OVMS server")

        try:
            data = await asyncio.wait_for(
                self._reader.readline(),
                timeout=timeout,
            )

            if not data:
                return None

            # All post-auth messages are Base64 encoded RC4 encrypted
            response = data.decode("utf-8").strip()
            _LOGGER.debug(
                "Raw encrypted response: %s...",
                response[:40] if len(response) > 40 else response,
            )

            # Decrypt the message
            if self._rx_cipher:
                decrypted = self._decrypt_message(response)
                _LOGGER.debug("Decrypted response: %s", decrypted)

                # Validate message format
                if not decrypted.startswith("MP-0 "):
                    _LOGGER.warning("Invalid decrypted message format: %s", decrypted)
                    return decrypted

                # Extract message type and payload
                msg_type = decrypted[5:6]
                payload = decrypted[6:]

                # Handle different message types
                if msg_type == "c":
                    # Command response
                    _LOGGER.debug("Command response: %s", payload)
                    return payload
                elif msg_type == "Z":
                    # Cars connected count
                    _LOGGER.debug("Cars connected: %s", payload)
                    return f"Z:{payload}"
                elif msg_type == "T":
                    # Last update timestamp
                    _LOGGER.debug("Last update: %s", payload)
                    return f"T:{payload}"
                elif msg_type == "P":
                    # Push notification
                    _LOGGER.debug("Push notification: %s", payload)
                    return f"PUSH:{payload}"
                else:
                    # Other message types (S=status, L=location, D=environment, etc.)
                    _LOGGER.debug("Message type %s: %s", msg_type, payload)
                    return f"{msg_type}:{payload}"
            else:
                _LOGGER.warning("No RX cipher - cannot decrypt message")
                return response

        except TimeoutError:
            _LOGGER.debug("Read timeout after %d seconds", timeout)
            return None
        except Exception as err:
            _LOGGER.error("Error reading response: %s", err)
            return None
