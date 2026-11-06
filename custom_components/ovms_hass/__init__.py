"""OVMS Home Assistant Integration.

This integration provides Home Assistant support for OVMS (Open Vehicles Monitoring System).
It communicates with the OVMS server using REST API (HTTP/HTTPS) for data retrieval
and the binary Protocol v2 (TCP/TLS) for real-time vehicle commands.

Configuration via configuration.yaml:
    ovms_hass:
      host: api.openvehicles.com
      port: 6869
      username: your_username
      password: your_rest_api_password
      vehicles:
        - vehicle_id: DEMO
          name: My Vehicle
          vehicle_password: your_vehicle_module_password
          scan_interval: 300
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import (
    OVMSApiClient,
    OVMSAPIError,
    OVMSAuthenticationError,
    OVMSConnectionError,
)
from .coordinator import OVMSDataCoordinator, OVMSProtocolClient
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "ovms_hass"
DEFAULT_HOST: Final = "api.openvehicles.com"
DEFAULT_PORT: Final = 6869
DEFAULT_SCAN_INTERVAL: Final = 300
CONF_VEHICLE_PASSWORD: Final = "vehicle_password"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional("vehicles", default=[]): [
                    {
                        vol.Required("vehicle_id"): cv.string,
                        vol.Optional("name"): cv.string,
                        vol.Optional(CONF_VEHICLE_PASSWORD): cv.string,
                        vol.Optional(
                            "scan_interval", default=DEFAULT_SCAN_INTERVAL
                        ): cv.positive_int,
                    }
                ],
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up OVMS integration from configuration.yaml.

    Note: YAML configuration is imported as config entries.
    This function validates configuration but actual setup happens via async_setup_entry.

    Args:
        hass: Home Assistant instance
        config: Configuration dictionary

    Returns:
        True if setup was successful
    """
    if DOMAIN not in config:
        return True

    # Initialize hass.data storage
    hass.data.setdefault(DOMAIN, {})

    # Store config for later use in import
    ovms_config = config[DOMAIN]

    # Import YAML configuration as config entries
    # This converts YAML setup to use the config entry system
    # Create a separate config entry for each vehicle
    vehicles = ovms_config.get("vehicles", [])
    for vehicle in vehicles:
        # Create entry data with shared server config and vehicle-specific data
        entry_data = {
            CONF_HOST: ovms_config.get(CONF_HOST, DEFAULT_HOST),
            CONF_PORT: ovms_config.get(CONF_PORT, DEFAULT_PORT),
            CONF_USERNAME: ovms_config[CONF_USERNAME],
            CONF_PASSWORD: ovms_config[CONF_PASSWORD],
            CONF_VEHICLE_PASSWORD: vehicle.get(CONF_VEHICLE_PASSWORD),
            "vehicle_id": vehicle.get("vehicle_id"),
            "name": vehicle.get("name", vehicle.get("vehicle_id")),
            "scan_interval": vehicle.get("scan_interval", DEFAULT_SCAN_INTERVAL),
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=entry_data,
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If the server can't be reached (HA retries)
        ConfigEntryError: If the server rejects the credentials
    """
    host = entry.data.get(CONF_HOST, DEFAULT_HOST)
    # Create API client (always create new instance per entry)
    api_client = OVMSApiClient(
        host=host,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        use_https=True,
    )

    # Connect to OVMS server. connect() closes its session when it fails.
    try:
        await api_client.connect()
    except OVMSAuthenticationError as err:
        raise ConfigEntryError(f"OVMS login failed: {err}") from err
    except OVMSConnectionError as err:
        raise ConfigEntryNotReady(f"Cannot reach OVMS server {host}: {err}") from err
    _LOGGER.debug("Connected to OVMS server %s", host)

    # Create coordinator
    # Use entry ID as vehicle_id if not explicitly set for consistent unique_ids
    vehicle_id = entry.data.get("vehicle_id", entry.entry_id)

    # Get scan interval from options (if set) or data
    scan_interval = entry.options.get(
        "scan_interval",
        entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
    )

    coordinator = OVMSDataCoordinator(
        hass,
        api_client,
        vehicle_id,
        scan_interval=scan_interval,
        config_entry=entry,
    )

    # Store coordinator in entry runtime data
    entry.runtime_data = {
        "coordinator": coordinator,
        "api_client": api_client,
    }

    # Set up Protocol v2 client for commands
    # Use vehicle_password for Protocol v2 if available, otherwise fall back to password
    # The vehicle_password is the password configured in the OVMS module itself
    # which is different from the server account password
    vehicle_password = entry.data.get(CONF_VEHICLE_PASSWORD) or entry.data[CONF_PASSWORD]

    _LOGGER.debug(
        "Setting up Protocol v2 client for vehicle %s - vehicle_password configured: %s",
        vehicle_id,
        "YES" if entry.data.get(CONF_VEHICLE_PASSWORD) else "NO (using REST API password as fallback)",
    )

    protocol_client = OVMSProtocolClient(
        host=host,
        username=entry.data[CONF_USERNAME],
        password=vehicle_password,  # Use vehicle module password for Protocol v2
        vehicle_id=vehicle_id,
        port=6870,  # TLS port
        use_tls=True,
    )

    try:
        await _async_connect_protocol(coordinator, protocol_client)
        # Raises ConfigEntryNotReady if the first refresh fails
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        # HA does not call async_unload_entry after a failed setup, so close
        # the connections here or every retry leaks one.
        await _async_close_clients(coordinator, api_client)
        raise

    # Forward entry to entity platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once, check if already registered)
    if not hass.services.has_service(DOMAIN, "send_command"):
        await async_setup_services(hass)

    # Add listener for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def _async_close_clients(
    coordinator: OVMSDataCoordinator | None, api_client: OVMSApiClient | None
) -> None:
    """Stop the HVAC follow-up and close both server connections."""
    if coordinator:
        coordinator.async_cancel_scheduled()
        if coordinator.ovms_client:
            try:
                await coordinator.ovms_client.disconnect()
            except (OVMSConnectionError, OVMSAPIError) as err:
                _LOGGER.debug("Error disconnecting protocol client: %s", err)
    if api_client:
        try:
            await api_client.disconnect()
        except (OVMSConnectionError, OVMSAPIError) as err:
            _LOGGER.debug("Error disconnecting API client: %s", err)


async def _async_connect_protocol(
    coordinator: OVMSDataCoordinator, protocol_client: OVMSProtocolClient
) -> None:
    """Attach the Protocol v2 client to the coordinator and connect it.

    The client is attached before connecting, so a failed first connect still
    leaves a client that reconnects in the background and on the next command.
    """
    coordinator.ovms_client = protocol_client
    protocol_client.on_protocol_data = coordinator.async_handle_protocol_data
    try:
        _LOGGER.debug(
            "Connecting Protocol v2 client for vehicle %s", coordinator.vehicle_id
        )
        await protocol_client.connect()
        # Start background reader loop and ping keepalive
        # This keeps the TCP connection alive and processes incoming messages
        protocol_client.start_background_reader()
        _LOGGER.debug(
            "Protocol v2 client connected with background reader for vehicle %s",
            coordinator.vehicle_id,
        )
    except (OVMSConnectionError, OVMSAPIError) as err:
        _LOGGER.warning(
            "Failed to connect Protocol v2 client for commands, retrying in background: %s",
            err,
        )
        protocol_client.start_reconnect()
    except Exception as err:
        _LOGGER.exception("Unexpected error connecting Protocol v2 client: %s", err)
        protocol_client.start_reconnect()


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options.

    Args:
        hass: Home Assistant instance
        entry: Config entry with updated options
    """
    try:
        # Update the coordinator's scan interval if it changed
        coordinator: OVMSDataCoordinator = entry.runtime_data["coordinator"]

        new_scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        if (
            coordinator.update_interval
            and coordinator.update_interval.total_seconds() != new_scan_interval
        ):
            coordinator.update_interval = timedelta(seconds=new_scan_interval)
            await coordinator.async_request_refresh()
    except (OVMSConnectionError, OVMSAPIError):
        _LOGGER.exception("Error updating OVMS options")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await _async_close_clients(
            entry.runtime_data.get("coordinator"),
            entry.runtime_data.get("api_client"),
        )

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to newer version.

    Args:
        hass: Home Assistant instance
        config_entry: Config entry to migrate

    Returns:
        True if migration successful
    """
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        # Version 1 to 2 migration (placeholder for future use)
        # Currently no changes needed
        pass

    _LOGGER.debug("Migration to version %s successful", config_entry.version)
    return True
