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
from .commands import OVMSCommandBuilder

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
        if not self.ovms_client:
            _LOGGER.error("Protocol v2 client not connected")
            return False

        try:
            timeout = asyncio.timeout(COMMAND_TIMEOUT)
            async with timeout:
                await self.ovms_client.send_command(command)
                # Refresh data after command execution
                await self.async_request_refresh()
                return True
        except TimeoutError:
            _LOGGER.error("Command timeout: %s", command)
            return False
        except (OVMSConnectionError, OVMSAPIError) as err:
            _LOGGER.error("Failed to send command %s: %s", command, err)
            return False


class OVMSProtocolClient:
    """OVMS Protocol v2 binary protocol client.

    Handles TCP connections to OVMS server on ports 6867 (plaintext) and 6870 (TLS),
    with RC4 encryption and HMAC-MD5 authentication.

    Note: This is a placeholder for the actual binary protocol implementation.
    In production, this would handle socket communication, encryption, and
    message parsing for the binary Protocol v2.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 6870,
        use_tls: bool = True,
    ) -> None:
        """Initialize Protocol v2 client.

        Args:
            host: OVMS server hostname or IP
            username: OVMS username
            password: OVMS password
            port: Server port (6870 for TLS, 6867 for plaintext)
            use_tls: Use TLS encryption
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_tls = use_tls
        self.connected = False
        self._reader: Any | None = None
        self._writer: Any | None = None

    async def connect(self) -> None:
        """Establish connection to OVMS server.

        Raises:
            OVMSConnectionError: If connection fails
        """
        try:
            if self.use_tls:
                # Pre-create SSL context outside the event loop to avoid blocking call
                loop = asyncio.get_event_loop()
                ssl_context = await loop.run_in_executor(
                    None, ssl.create_default_context
                )
                # TLS connection with pre-created context
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=ssl_context,
                )
            else:
                # Plaintext connection
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                )

            self._reader = reader
            self._writer = writer
            self.connected = True
            _LOGGER.info("Connected to OVMS server %s:%d", self.host, self.port)

            # Authenticate (simplified - actual implementation would handle encryption)
            await self._authenticate()

        except Exception as err:
            raise OVMSConnectionError(f"Failed to connect to OVMS: {err}") from err

    async def disconnect(self) -> None:
        """Close connection to OVMS server."""
        if self._writer:
            self._writer.close()
            with suppress(Exception):
                await self._writer.wait_closed()
        self.connected = False

    async def _authenticate(self) -> None:
        """Authenticate with OVMS server.

        In actual implementation, this would:
        1. Exchange challenge/response with server
        2. Generate RC4 cipher keys using HMAC-MD5
        3. Set up encryption for subsequent messages
        """
        # Placeholder: Actual implementation would handle binary protocol v2 auth

    async def send_command(self, command: str) -> None:
        """Send command to vehicle.

        Args:
            command: Command string (e.g., "26,1")

        Raises:
            OVMSConnectionError: If not connected or send fails
        """
        if not self.connected or not self._writer:
            raise OVMSConnectionError("Not connected to OVMS server")

        # Wrap command with Protocol v2 header
        message = OVMSCommandBuilder.build_command(
            int(command.split(",")[0]), command.split(",")[1] if "," in command else ""
        )

        # In actual implementation, this would:
        # 1. Apply RC4 encryption
        # 2. Calculate HMAC-MD5
        # 3. Base64 encode
        # 4. Send over socket

        _LOGGER.debug("Sending command: %s", message)

    async def read_response(self, timeout: int = 5) -> str | None:
        """Read response from vehicle.

        Args:
            timeout: Read timeout in seconds

        Returns:
            Response string or None if timeout

        Raises:
            OVMSConnectionError: If not connected
        """
        if not self.connected or not self._reader:
            raise OVMSConnectionError("Not connected to OVMS server")

        try:
            # In actual implementation, this would:
            # 1. Read encrypted data from socket
            # 2. Base64 decode
            # 3. Apply RC4 decryption
            # 4. Verify HMAC-MD5
            # 5. Parse Protocol v2 message

            data = await asyncio.wait_for(
                self._reader.readline(),
                timeout=timeout,
            )
            return data.decode("utf-8").strip() if data else None

        except TimeoutError:
            return None
