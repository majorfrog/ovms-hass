"""Services for OVMS integration.

This module provides service calls for advanced OVMS control operations
that don't fit into standard entity types.
"""

from __future__ import annotations

from functools import partial
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
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
    """Return the coordinator for a vehicle.

    Raises:
        ServiceValidationError: If no loaded entry has this vehicle
    """
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        runtime_data = getattr(entry, "runtime_data", None)
        coordinator = (
            runtime_data.get("coordinator") if isinstance(runtime_data, dict) else None
        )
        if coordinator and coordinator.vehicle_id == vehicle_id:
            return coordinator

    raise ServiceValidationError(f"Unknown OVMS vehicle {vehicle_id}")


async def async_send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send a generic shell command to the vehicle (Command 7)."""
    vehicle_id = call.data["vehicle_id"]
    command = call.data["command"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Sending command to %s: %s", vehicle_id, command)
    await coordinator.async_send_command(f"7,{command}", command)


async def async_send_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send an SMS via the vehicle's modem (Command 40)."""
    vehicle_id = call.data["vehicle_id"]
    phone_number = call.data["phone_number"]
    message = call.data["message"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Sending SMS from %s to %s", vehicle_id, phone_number)
    await coordinator.async_send_command(f"40,{phone_number},{message}", "SMS")


async def async_set_charge_timer(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set or clear the charge timer (Command 17)."""
    vehicle_id = call.data["vehicle_id"]
    start_time = call.data["start_time"]
    enabled = call.data.get("enabled", True)
    coordinator = _get_coordinator(hass, vehicle_id)

    if not enabled:
        _LOGGER.info("Disabling charge timer for %s", vehicle_id)
        await coordinator.async_send_command("17,0", "charge timer")
        return

    # Format varies by vehicle, common format is mode,start_hour,start_min
    parts = start_time.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ServiceValidationError(
            f"Invalid time format: {start_time} (expected HH:MM)"
        )
    hour, minute = int(parts[0]), int(parts[1])
    _LOGGER.info("Setting charge timer for %s to %s", vehicle_id, start_time)
    await coordinator.async_send_command(f"17,1,{hour},{minute}", "charge timer")


async def async_wakeup_subsystem(hass: HomeAssistant, call: ServiceCall) -> None:
    """Wake a specific vehicle subsystem (Command 19)."""
    vehicle_id = call.data["vehicle_id"]
    subsystem = call.data["subsystem"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Waking subsystem %d for %s", subsystem, vehicle_id)
    await coordinator.async_send_command(f"19,{subsystem}", f"wake-up {subsystem}")


async def async_tpms_map_wheel(hass: HomeAssistant, call: ServiceCall) -> None:
    """Map a TPMS sensor to a wheel position (Command 7)."""
    vehicle_id = call.data["vehicle_id"]
    wheel = call.data["wheel"]
    sensor_id = call.data["sensor_id"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info(
        "Mapping TPMS sensor %s to wheel %s for %s", sensor_id, wheel, vehicle_id
    )
    await coordinator.async_send_command(f"7,tpms map {wheel} {sensor_id}", "TPMS map")


async def async_get_feature(hass: HomeAssistant, call: ServiceCall) -> None:
    """Request the module features (Command 1)."""
    vehicle_id = call.data["vehicle_id"]
    feature_number = call.data["feature_number"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Getting feature %d for %s", feature_number, vehicle_id)
    await coordinator.async_send_command("1", "get feature")


async def async_set_feature(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set a module feature (Command 2)."""
    vehicle_id = call.data["vehicle_id"]
    feature_number = call.data["feature_number"]
    value = call.data.get("value", "")
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Setting feature %d to %s for %s", feature_number, value, vehicle_id)
    await coordinator.async_send_command(
        f"2,{feature_number},{value}", f"set feature {feature_number}"
    )


async def async_get_parameter(hass: HomeAssistant, call: ServiceCall) -> None:
    """Request the module parameters (Command 3)."""
    vehicle_id = call.data["vehicle_id"]
    parameter_number = call.data["parameter_number"]
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info("Getting parameter %d for %s", parameter_number, vehicle_id)
    await coordinator.async_send_command("3", "get parameter")


async def async_set_parameter(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set a module parameter (Command 4)."""
    vehicle_id = call.data["vehicle_id"]
    parameter_number = call.data["parameter_number"]
    value = call.data.get("value", "")
    coordinator = _get_coordinator(hass, vehicle_id)
    _LOGGER.info(
        "Setting parameter %d to %s for %s", parameter_number, value, vehicle_id
    )
    await coordinator.async_send_command(
        f"4,{parameter_number},{value}", f"set parameter {parameter_number}"
    )


SERVICES = (
    (SERVICE_SEND_COMMAND, async_send_command, SEND_COMMAND_SCHEMA),
    (SERVICE_SEND_SMS, async_send_sms, SEND_SMS_SCHEMA),
    (SERVICE_SET_CHARGE_TIMER, async_set_charge_timer, SET_CHARGE_TIMER_SCHEMA),
    (SERVICE_WAKEUP_SUBSYSTEM, async_wakeup_subsystem, WAKEUP_SUBSYSTEM_SCHEMA),
    (SERVICE_TPMS_MAP_WHEEL, async_tpms_map_wheel, TPMS_MAP_WHEEL_SCHEMA),
    (SERVICE_GET_FEATURE, async_get_feature, FEATURE_SCHEMA),
    (SERVICE_SET_FEATURE, async_set_feature, FEATURE_SCHEMA),
    (SERVICE_GET_PARAMETER, async_get_parameter, PARAMETER_SCHEMA),
    (SERVICE_SET_PARAMETER, async_set_parameter, PARAMETER_SCHEMA),
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up OVMS services."""
    # functools.partial keeps the handler a coroutine function for HA. A lambda
    # would be run as an executor job and its coroutine never awaited.
    for name, handler, schema in SERVICES:
        hass.services.async_register(
            DOMAIN, name, partial(handler, hass), schema=schema
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
