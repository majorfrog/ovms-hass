"""Services for OVMS integration.

This module provides service calls for advanced OVMS control operations
that don't fit into standard entity types.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_hass"

# Service names
SERVICE_SEND_COMMAND = "send_command"
SERVICE_SEND_SMS = "send_sms"
SERVICE_SET_CHARGE_TIMER = "set_charge_timer"
SERVICE_WAKEUP_SUBSYSTEM = "wakeup_subsystem"
SERVICE_TPMS_MAP_WHEEL = "tpms_map_wheel"
SERVICE_GET_FEATURE = "get_feature"
SERVICE_SET_FEATURE = "set_feature"
SERVICE_GET_PARAMETER = "get_parameter"
SERVICE_SET_PARAMETER = "set_parameter"

# Service schemas
SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("command"): cv.string,
    }
)

SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("phone_number"): cv.string,
        vol.Required("message"): cv.string,
    }
)

SET_CHARGE_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("start_time"): cv.string,  # Format: "HH:MM"
        vol.Optional("enabled", default=True): cv.boolean,
    }
)

WAKEUP_SUBSYSTEM_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("subsystem"): cv.positive_int,
    }
)

TPMS_MAP_WHEEL_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("wheel"): vol.In(["fl", "fr", "rl", "rr"]),
        vol.Required("sensor_id"): cv.string,
    }
)

FEATURE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("feature_number"): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
        vol.Optional("value"): cv.string,
    }
)

PARAMETER_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("parameter_number"): vol.All(vol.Coerce(int), vol.Range(min=0, max=31)),
        vol.Optional("value"): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant, vehicle_id: str):
    """Get coordinator for a specific vehicle."""
    if DOMAIN not in hass.data:
        return None

    # Find the coordinator for this vehicle
    for entry_id, entry_data in hass.data[DOMAIN].items():
        if isinstance(entry_data, dict):
            coordinator = entry_data.get("coordinator")
            if coordinator and coordinator.vehicle_id == vehicle_id:
                return coordinator

    return None


async def async_send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle send_command service call.

    Sends a generic command to the vehicle using Command 7.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id and command
    """
    vehicle_id = call.data["vehicle_id"]
    command = call.data["command"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 7 is for generic commands
        _LOGGER.info("Sending command to %s: %s", vehicle_id, command)
        await coordinator.ovms_client.send_command(f"7,{command}")
    except Exception as err:
        _LOGGER.error("Failed to send command to %s: %s", vehicle_id, err)


async def async_send_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle send_sms service call.

    Sends an SMS via the vehicle's modem using Command 40.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id, phone_number, and message
    """
    vehicle_id = call.data["vehicle_id"]
    phone_number = call.data["phone_number"]
    message = call.data["message"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 40 is for sending SMS
        _LOGGER.info("Sending SMS from %s to %s", vehicle_id, phone_number)
        await coordinator.ovms_client.send_command(f"40,{phone_number},{message}")
    except Exception as err:
        _LOGGER.error("Failed to send SMS from %s: %s", vehicle_id, err)


async def async_set_charge_timer(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle set_charge_timer service call.

    Sets or clears the charge timer using Command 17.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id, start_time, and enabled
    """
    vehicle_id = call.data["vehicle_id"]
    start_time = call.data["start_time"]
    enabled = call.data.get("enabled", True)

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 17 is for charge timer
        # Format varies by vehicle, common format is mode,start_hour,start_min
        if enabled:
            parts = start_time.split(":")
            if len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                _LOGGER.info("Setting charge timer for %s to %s", vehicle_id, start_time)
                await coordinator.ovms_client.send_command(f"17,1,{hour},{minute}")
            else:
                _LOGGER.error("Invalid time format: %s (expected HH:MM)", start_time)
        else:
            _LOGGER.info("Disabling charge timer for %s", vehicle_id)
            await coordinator.ovms_client.send_command("17,0")
    except Exception as err:
        _LOGGER.error("Failed to set charge timer for %s: %s", vehicle_id, err)


async def async_wakeup_subsystem(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle wakeup_subsystem service call.

    Wakes a specific vehicle subsystem using Command 19.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id and subsystem
    """
    vehicle_id = call.data["vehicle_id"]
    subsystem = call.data["subsystem"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 19 is for waking specific subsystems
        _LOGGER.info("Waking subsystem %d for %s", subsystem, vehicle_id)
        await coordinator.ovms_client.send_command(f"19,{subsystem}")
    except Exception as err:
        _LOGGER.error("Failed to wake subsystem for %s: %s", vehicle_id, err)


async def async_tpms_map_wheel(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle tpms_map_wheel service call.

    Maps a TPMS sensor to a wheel position using Command 7.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id, wheel, and sensor_id
    """
    vehicle_id = call.data["vehicle_id"]
    wheel = call.data["wheel"]
    sensor_id = call.data["sensor_id"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # TPMS mapping uses generic command
        _LOGGER.info("Mapping TPMS sensor %s to wheel %s for %s", sensor_id, wheel, vehicle_id)
        await coordinator.ovms_client.send_command(f"7,tpms map {wheel} {sensor_id}")
        await coordinator.async_request_refresh()
    except Exception as err:
        _LOGGER.error("Failed to map TPMS for %s: %s", vehicle_id, err)


async def async_get_feature(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle get_feature service call.

    Gets a module feature using Command 1.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id and feature_number
    """
    vehicle_id = call.data["vehicle_id"]
    feature_number = call.data["feature_number"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 1 is for getting features
        _LOGGER.info("Getting feature %d for %s", feature_number, vehicle_id)
        await coordinator.ovms_client.send_command("1")
    except Exception as err:
        _LOGGER.error("Failed to get feature for %s: %s", vehicle_id, err)


async def async_set_feature(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle set_feature service call.

    Sets a module feature using Command 2.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id, feature_number, and value
    """
    vehicle_id = call.data["vehicle_id"]
    feature_number = call.data["feature_number"]
    value = call.data.get("value", "")

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 2 is for setting features
        _LOGGER.info("Setting feature %d to %s for %s", feature_number, value, vehicle_id)
        await coordinator.ovms_client.send_command(f"2,{feature_number},{value}")
    except Exception as err:
        _LOGGER.error("Failed to set feature for %s: %s", vehicle_id, err)


async def async_get_parameter(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle get_parameter service call.

    Gets a module parameter using Command 3.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id and parameter_number
    """
    vehicle_id = call.data["vehicle_id"]
    parameter_number = call.data["parameter_number"]

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 3 is for getting parameters
        _LOGGER.info("Getting parameter %d for %s", parameter_number, vehicle_id)
        await coordinator.ovms_client.send_command("3")
    except Exception as err:
        _LOGGER.error("Failed to get parameter for %s: %s", vehicle_id, err)


async def async_set_parameter(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle set_parameter service call.

    Sets a module parameter using Command 4.

    Args:
        hass: Home Assistant instance
        call: Service call data containing vehicle_id, parameter_number, and value
    """
    vehicle_id = call.data["vehicle_id"]
    parameter_number = call.data["parameter_number"]
    value = call.data.get("value", "")

    coordinator = _get_coordinator(hass, vehicle_id)
    if not coordinator:
        _LOGGER.error("Vehicle %s not found", vehicle_id)
        return

    if not coordinator.ovms_client:
        _LOGGER.error("OVMS Protocol client not available for vehicle %s", vehicle_id)
        return

    try:
        # Command 4 is for setting parameters
        _LOGGER.info("Setting parameter %d to %s for %s", parameter_number, value, vehicle_id)
        await coordinator.ovms_client.send_command(f"4,{parameter_number},{value}")
    except Exception as err:
        _LOGGER.error("Failed to set parameter for %s: %s", vehicle_id, err)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up OVMS services."""

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        lambda call: async_send_command(hass, call),
        schema=SEND_COMMAND_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_SMS,
        lambda call: async_send_sms(hass, call),
        schema=SEND_SMS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CHARGE_TIMER,
        lambda call: async_set_charge_timer(hass, call),
        schema=SET_CHARGE_TIMER_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_WAKEUP_SUBSYSTEM,
        lambda call: async_wakeup_subsystem(hass, call),
        schema=WAKEUP_SUBSYSTEM_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TPMS_MAP_WHEEL,
        lambda call: async_tpms_map_wheel(hass, call),
        schema=TPMS_MAP_WHEEL_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FEATURE,
        lambda call: async_get_feature(hass, call),
        schema=FEATURE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FEATURE,
        lambda call: async_set_feature(hass, call),
        schema=FEATURE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PARAMETER,
        lambda call: async_get_parameter(hass, call),
        schema=PARAMETER_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PARAMETER,
        lambda call: async_set_parameter(hass, call),
        schema=PARAMETER_SCHEMA,
    )

    _LOGGER.info("OVMS services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload OVMS services."""
    services = [
        SERVICE_SEND_COMMAND,
        SERVICE_SEND_SMS,
        SERVICE_SET_CHARGE_TIMER,
        SERVICE_WAKEUP_SUBSYSTEM,
        SERVICE_TPMS_MAP_WHEEL,
        SERVICE_GET_FEATURE,
        SERVICE_SET_FEATURE,
        SERVICE_GET_PARAMETER,
        SERVICE_SET_PARAMETER,
    ]

    for service in services:
        hass.services.async_remove(DOMAIN, service)
