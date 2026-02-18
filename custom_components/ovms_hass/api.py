"""OVMS Server REST API client.

This module provides a Pythonic REST API client for communicating with the OVMS Server.
It handles HTTP/HTTPS endpoints on ports 6868/6869, session management, and vehicle data retrieval.

The OVMS Server provides REST API access to:
- Authentication and session management
- Vehicle list and connection management
- Vehicle status, charging, location, and TPMS data
- Historical data retrieval
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import logging
import re
from typing import Any, Self, TypeVar, get_args

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _convert_value(value: Any, target_type: type) -> Any:
    """Convert a value to the target type with proper handling.

    Args:
        value: Value to convert
        target_type: Target type to convert to

    Returns:
        Converted value

    Raises:
        ValueError: If conversion fails
    """
    if isinstance(value, target_type):
        return value

    if target_type is bool:
        # Proper boolean conversion
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    if target_type is float:
        return float(value)
    if target_type is int:
        # Convert to float first to handle decimal strings like "0.0" or "382.00"
        return int(float(value))
    if target_type is str:
        return str(value)

    return value


def _from_dict_with_type_conversion(cls: type[T], data: dict) -> T:
    """Create dataclass instance from dict with proper type conversion.

    Args:
        cls: Dataclass type to create
        data: Dictionary with data from API

    Returns:
        Instance of the dataclass with properly typed fields
    """
    supported_fields = {field.name: field.type for field in fields(cls)}  # type: ignore[arg-type]
    filtered_data = {}

    for key, value in data.items():
        if key not in supported_fields or value is None:
            continue

        field_type = supported_fields[key]

        # Handle Optional types by extracting the actual type
        if hasattr(field_type, "__args__"):
            # Get the non-None type from Optional[T]
            type_args = get_args(field_type)
            actual_type = next((t for t in type_args if t is not type(None)), None)

            if actual_type:
                try:
                    filtered_data[key] = _convert_value(value, actual_type)
                except (ValueError, TypeError) as e:
                    _LOGGER.debug(
                        "Failed to convert %s=%s to %s: %s", key, value, actual_type, e
                    )
                    continue
        else:
            filtered_data[key] = value

    return cls(**filtered_data)


class OVMSConnectionError(Exception):
    """Raised when unable to connect to OVMS server."""


class OVMSAuthenticationError(Exception):
    """Raised when authentication with OVMS server fails."""


class OVMSAPIError(Exception):
    """Raised when API returns an error."""


@dataclass
class VehicleInfo:
    """Vehicle information from /api/vehicles endpoint."""

    id: str
    v_net_connected: int
    v_apps_connected: int
    v_btcs_connected: int


@dataclass
class VehicleStatus:
    """Comprehensive vehicle status data."""

    m_msgtime_s: str | None = None
    m_msgage_s: int | None = None
    soc: int | None = None
    units: str | None = None
    idealrange: int | None = None
    idealrange_max: int | None = None
    estimatedrange: int | None = None
    mode: str | None = None
    chargestate: str | None = None
    soh: int | None = None
    cac100: int | None = None
    # Device/System Information
    m_hardware: str | None = None
    m_firmware: str | None = None
    m_version: str | None = None
    car_type: str | None = None
    car_vin: str | None = None
    car_gsm_signal: int | None = None
    car_wifi_signal: int | None = None
    m_server_firmware: str | None = None
    temperature_battery: float | None = None
    temperature_cabin: float | None = None
    temperature_ambient: float | None = None
    temperature_pem: float | None = None
    temperature_motor: float | None = None
    temperature_charger: float | None = None
    tripmeter: float | None = None
    odometer: int | None = None
    speed: int | None = None
    charging: bool | None = None
    caron: bool | None = None
    carlocked: bool | None = None
    valetmode: bool | None = None
    charging_12v: bool | None = None
    vehicle12v: float | None = None
    vehicle12v_ref: float | None = None
    vehicle12v_current: float | None = None
    fl_dooropen: bool | None = None
    fr_dooropen: bool | None = None
    cp_dooropen: bool | None = None
    pilotpresent: bool | None = None
    handbrake: bool | None = None
    bt_open: bool | None = None
    tr_open: bool | None = None
    alarmsounding: bool | None = None
    staletemps: bool | None = None
    staleambient: bool | None = None
    # Additional door status
    rl_dooropen: bool | None = None
    rr_dooropen: bool | None = None
    # Headlights and system status
    headlights: bool | None = None
    canwrite: bool | None = None
    # Service information
    servicerange: int | None = None
    servicetime: int | None = None
    # Modem/network mode
    m_mdm_mode: str | None = None
    m_mdm_network: str | None = None
    # Climate control
    hvac: bool | None = None

    @classmethod
    def from_dict(cls, data: dict) -> VehicleStatus:
        """Create VehicleStatus from API response dictionary.

        Args:
            data: Dictionary from API response

        Returns:
            VehicleStatus instance with properly typed fields
        """
        return _from_dict_with_type_conversion(cls, data)


@dataclass
class ChargeStatus:
    """Detailed charging information."""

    m_msgtime_s: str | None = None
    m_msgage_s: int | None = None
    linevoltage: int | None = None
    battvoltage: int | None = None
    chargecurrent: int | None = None
    chargepower: int | None = None
    chargepowerinput: int | None = None
    chargerefficiency: int | None = None
    chargetype: str | None = None
    chargestate: str | None = None
    soc: int | None = None
    units: str | None = None
    idealrange: int | None = None
    estimatedrange: int | None = None
    mode: str | None = None
    chargelimit: int | None = None
    chargeduration: int | None = None
    chargeb4: int | None = None
    chargekwh: float | None = None
    chargesubstate: str | None = None
    soh: int | None = None
    cac100: int | None = None
    charge_etr_full: int | None = None
    charge_etr_limit: int | None = None
    charge_limit_range: int | None = None
    charge_limit_soc: int | None = None
    cooldown_active: bool | None = None
    cooldown_tbattery: float | None = None
    charge_kwh_grid: float | None = None
    charge_kwh_grid_total: float | None = None
    batt_capacity: int | None = None
    batt_current: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ChargeStatus:
        """Create ChargeStatus from API response dictionary.

        Args:
            data: Dictionary from API response

        Returns:
            ChargeStatus instance with properly typed fields
        """
        return _from_dict_with_type_conversion(cls, data)


@dataclass
class LocationData:
    """Vehicle location and driving information."""

    m_msgtime_l: str | None = None
    m_msgage_l: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    direction: int | None = None
    altitude: int | None = None
    gpslock: bool | None = None
    stalegps: bool | None = None
    speed: int | None = None
    tripmeter: float | None = None
    drivemode: str | None = None
    power: int | None = None
    energyused: float | None = None
    energyrecd: float | None = None
    invpower: int | None = None
    invefficiency: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> LocationData:
        """Create LocationData from API response dictionary.

        Args:
            data: Dictionary from API response

        Returns:
            LocationData instance with properly typed fields
        """
        return _from_dict_with_type_conversion(cls, data)


@dataclass
class TPMSData:
    """Tire Pressure Monitoring System data."""

    m_msgtime_y: str | None = None
    m_msgage_y: int | None = None
    fl_pressure_kpa: float | None = None
    fl_pressure: float | None = None
    fl_temperature: int | None = None
    fr_pressure_kpa: float | None = None
    fr_pressure: float | None = None
    fr_temperature: int | None = None
    rl_pressure_kpa: float | None = None
    rl_pressure: float | None = None
    rl_temperature: int | None = None
    rr_pressure_kpa: float | None = None
    rr_pressure: float | None = None
    rr_temperature: int | None = None
    stale_pressure: bool | None = None
    stale_temperature: bool | None = None

    @classmethod
    def from_dict(cls, data: dict) -> TPMSData:
        """Create TPMSData from API response dictionary.

        Args:
            data: Dictionary from API response

        Returns:
            TPMSData instance with properly typed fields
        """
        return _from_dict_with_type_conversion(cls, data)


class OVMSApiClient:
    """Async REST API client for OVMS Server.

    Handles HTTP/HTTPS communication with the OVMS Server on ports 6868/6869.
    Manages session cookies and provides methods for all documented REST API endpoints.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 6869,
        use_https: bool = True,
        timeout: int = 30,
    ) -> None:
        """Initialize OVMS API client.

        Args:
            host: OVMS server hostname or IP address
            username: OVMS account username
            password: OVMS account password
            port: Server port (6869 for HTTPS, 6868 for HTTP)
            use_https: Use HTTPS if True, HTTP if False
            timeout: Request timeout in seconds
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_https = use_https
        self.timeout = timeout
        self.protocol = "https" if use_https else "http"
        self.base_url = f"{self.protocol}://{self.host}:{self.port}"
        self.session: aiohttp.ClientSession | None = None
        self.session_id: str | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish connection and authenticate with OVMS server.

        Raises:
            OVMSConnectionError: If unable to establish connection
            OVMSAuthenticationError: If authentication fails
        """
        connector = aiohttp.TCPConnector(
            verify_ssl=False  # OVMS uses self-signed certificates
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

        await self.login()

    async def disconnect(self) -> None:
        """Close connection and logout from OVMS server."""
        if self.session_id:
            await self.logout()

        if self.session:
            await self.session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        params: dict | None = None,
        retry_on_auth_failure: bool = True,
    ) -> dict:
        """Make HTTP request to OVMS API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (e.g., "/api/vehicles")
            json_data: JSON body data for POST/PUT requests
            params: Query parameters
            retry_on_auth_failure: Retry request after re-authentication if session expired

        Returns:
            Parsed JSON response

        Raises:
            OVMSConnectionError: If connection fails
            OVMSAPIError: If API returns error
        """
        if not self.session:
            raise OVMSConnectionError("Not connected to OVMS server")

        url = f"{self.base_url}{endpoint}"
        cookies = {}
        if self.session_id:
            cookies["ovmsapisession"] = self.session_id

        _LOGGER.debug("Making %s request to %s", method, url)
        _LOGGER.debug(
            "Session ID: %s", self.session_id[:20] if self.session_id else "None"
        )

        try:
            async with self.session.request(
                method,
                url,
                json=json_data,
                params=params,
                cookies=cookies,
                ssl=False,
            ) as response:
                text = await response.text()

                _LOGGER.debug("Response status: %d", response.status)

                # OVMS server returns 404 when session cookie is expired/invalid
                # Try to re-authenticate and retry the request once
                if (
                    response.status == 404
                    and retry_on_auth_failure
                    and endpoint != "/api/cookie"
                ):
                    _LOGGER.debug(
                        "Got 404, session may have expired. Re-authenticating"
                    )
                    await self.login()
                    return await self._request(
                        method, endpoint, json_data, params, retry_on_auth_failure=False
                    )

                if response.status == 401:
                    raise OVMSAuthenticationError("Authentication failed")
                if response.status == 403:
                    raise OVMSAPIError("Forbidden access")
                if response.status == 404:
                    raise OVMSAPIError("Endpoint not found")
                if response.status == 502:
                    raise OVMSAPIError("Bad gateway (paranoid vehicle?)")
                if response.status >= 400:
                    raise OVMSAPIError(f"HTTP {response.status}: {text}")

                # Try to parse JSON, fallback to text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}

        except TimeoutError as e:
            raise OVMSConnectionError(f"Request timeout: {e}") from e
        except aiohttp.ClientError as e:
            raise OVMSConnectionError(f"Connection error: {e}") from e

    async def login(self) -> None:
        """Authenticate and create a session cookie.

        Raises:
            OVMSAuthenticationError: If login fails
        """
        params = {"username": self.username, "password": self.password}

        try:
            # Make the login request
            if not self.session:
                raise OVMSConnectionError("Session not initialized")

            url = f"{self.base_url}/api/cookie"
            async with self.session.request(
                "GET",
                url,
                params=params,
                ssl=False,
            ) as response:
                if response.status == 401:
                    raise OVMSAuthenticationError("Invalid username or password")
                if response.status >= 400:
                    text = await response.text()
                    raise OVMSAuthenticationError(
                        f"Login failed: HTTP {response.status}: {text}"
                    )

                # Extract session ID from cookies
                # aiohttp automatically stores cookies in the session
                cookies = self.session.cookie_jar.filter_cookies(URL(self.base_url))

                if "ovmsapisession" in cookies:
                    self.session_id = cookies["ovmsapisession"].value
                    if self.session_id:
                        _LOGGER.debug(
                            "Successfully obtained session ID: %s",
                            self.session_id[:20]
                            if len(self.session_id) > 20
                            else self.session_id,
                        )
                else:
                    # If no session cookie, try to get it from response headers
                    set_cookie = response.headers.get("Set-Cookie", "")
                    if "ovmsapisession" in set_cookie:
                        # Extract session ID from Set-Cookie header
                        match = re.search(r"ovmsapisession=([^;]+)", set_cookie)
                        if match:
                            self.session_id = match.group(1)
                            if self.session_id:
                                _LOGGER.debug(
                                    "Successfully obtained session ID from Set-Cookie: %s",
                                    self.session_id[:20]
                                    if len(self.session_id) > 20
                                    else self.session_id,
                                )

                    if not self.session_id:
                        raise OVMSAuthenticationError(
                            "No session ID received from server"
                        )

        except OVMSAPIError as e:
            raise OVMSAuthenticationError(f"Login failed: {e}") from e
        except OVMSAuthenticationError as e:
            raise e
        except aiohttp.ClientError as err:
            raise OVMSAuthenticationError(f"Login error: {err}") from err

    async def logout(self) -> None:
        """Logout and destroy session cookie."""
        try:
            await self._request("DELETE", "/api/cookie")
        except OVMSAPIError:
            pass  # Ignore errors during logout
        finally:
            self.session_id = None

    async def list_vehicles(self) -> list[VehicleInfo]:
        """Get list of vehicles accessible to current user.

        Returns:
            List of VehicleInfo objects
        """
        response = await self._request("GET", "/api/vehicles")
        return [VehicleInfo(**vehicle) for vehicle in response]

    async def connect_vehicle(self, vehicle_id: str) -> dict:
        """Connect to a vehicle and get its connection status.

        Args:
            vehicle_id: Vehicle ID to connect to

        Returns:
            Connection status dictionary
        """
        return await self._request("GET", f"/api/vehicle/{vehicle_id}")

    async def disconnect_vehicle(self, vehicle_id: str) -> None:
        """Disconnect from a vehicle.

        Args:
            vehicle_id: Vehicle ID to disconnect from
        """
        await self._request("DELETE", f"/api/vehicle/{vehicle_id}")

    async def get_status(self, vehicle_id: str) -> VehicleStatus:
        """Get comprehensive vehicle status.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            VehicleStatus object with vehicle telemetry
        """
        response = await self._request("GET", f"/api/status/{vehicle_id}")
        return VehicleStatus.from_dict(response)

    async def get_charge(self, vehicle_id: str) -> ChargeStatus:
        """Get detailed charging information.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            ChargeStatus object with battery and charging data
        """
        response = await self._request("GET", f"/api/charge/{vehicle_id}")
        return ChargeStatus.from_dict(response)

    async def get_location(self, vehicle_id: str) -> LocationData:
        """Get vehicle location and driving information.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            LocationData object with GPS and driving data
        """
        response = await self._request("GET", f"/api/location/{vehicle_id}")
        return LocationData.from_dict(response)

    async def get_tpms(self, vehicle_id: str) -> TPMSData:
        """Get tire pressure monitoring system data.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            TPMSData object with tire pressure and temperature
        """
        response = await self._request("GET", f"/api/tpms/{vehicle_id}")
        return TPMSData.from_dict(response)

    async def get_vehicle(self, vehicle_id: str) -> dict:
        """Get vehicle connection information.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            Dictionary with connection status (v_net_connected, v_apps_connected, v_btcs_connected)
        """
        return await self._request("GET", f"/api/vehicle/{vehicle_id}")

    async def get_protocol(self, vehicle_id: str) -> list[dict]:
        """Get raw protocol messages.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            List of raw protocol message dictionaries
        """
        response = await self._request("GET", f"/api/protocol/{vehicle_id}")
        return response if isinstance(response, list) else [response]

    async def get_historical_summary(
        self, vehicle_id: str, since: str | None = None
    ) -> list[dict]:
        """Get summary of available historical data types.

        Args:
            vehicle_id: Vehicle ID
            since: Optional timestamp filter (ISO format)

        Returns:
            List of historical data type summaries
        """
        params = {}
        if since:
            params["since"] = since

        response = await self._request(
            "GET", f"/api/historical/{vehicle_id}", params=params
        )
        return response if isinstance(response, list) else [response]

    async def get_historical_records(
        self,
        vehicle_id: str,
        datatype: str,
        since: str | None = None,
    ) -> list[dict]:
        """Get specific historical data records.

        Args:
            vehicle_id: Vehicle ID
            datatype: Data type code (e.g., "S" for status)
            since: Optional timestamp filter (ISO format)

        Returns:
            List of historical records
        """
        params = {}
        if since:
            params["since"] = since

        response = await self._request(
            "GET",
            f"/api/historical/{vehicle_id}/{datatype}",
            params=params,
        )
        return response if isinstance(response, list) else [response]

    async def get_tokens(self) -> list[dict]:
        """Get list of API tokens for current user.

        Returns:
            List of token objects
        """
        response = await self._request("GET", "/api/token")
        return response if isinstance(response, list) else [response]

    async def create_token(
        self,
        application: str | None = None,
        purpose: str | None = None,
        permit: str = "auth",
    ) -> dict:
        """Create a new API token.

        Args:
            application: Application name (optional)
            purpose: Purpose description (optional)
            permit: Permission type (default "auth")

        Returns:
            Token object with newly created token
        """
        params = {"permit": permit}
        if application:
            params["application"] = application
        if purpose:
            params["purpose"] = purpose

        return await self._request("POST", "/api/token", params=params)

    async def delete_token(self, token: str) -> dict:
        """Delete a specific API token.

        Args:
            token: Token string to delete

        Returns:
            Confirmation dictionary
        """
        return await self._request("DELETE", f"/api/token/{token}")
