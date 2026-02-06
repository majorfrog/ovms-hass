"""Diagnostics support for OVMS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import OVMSDataCoordinator

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "car_vin",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        Dictionary with diagnostic data
    """
    coordinator: OVMSDataCoordinator = entry.runtime_data["coordinator"]

    diagnostics_data = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "vehicle_id": coordinator.vehicle_id,
            "update_interval": str(coordinator.update_interval),
            "last_update_success": coordinator.last_update_success,
            "protocol_client_connected": (
                coordinator.ovms_client.connected
                if coordinator.ovms_client
                else False
            ),
        },
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }

    return diagnostics_data
