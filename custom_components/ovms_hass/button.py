"""Button entities for OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OVMSDataCoordinator
from .entities import (
    ACOnButton,
    HomeLinkButton,
    ModuleResetButton,
    RefreshButton,
    TPMSResetButton,
    WakeUpButton,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""
    coordinator: OVMSDataCoordinator = config_entry.runtime_data["coordinator"]

    entities = [
        RefreshButton(coordinator, coordinator.vehicle_id),
        WakeUpButton(coordinator, coordinator.vehicle_id),
        ACOnButton(coordinator, coordinator.vehicle_id),
        HomeLinkButton(coordinator, coordinator.vehicle_id, 0),  # HomeLink 1
        HomeLinkButton(coordinator, coordinator.vehicle_id, 1),  # HomeLink 2
        HomeLinkButton(coordinator, coordinator.vehicle_id, 2),  # HomeLink 3
        ModuleResetButton(coordinator, coordinator.vehicle_id),
        TPMSResetButton(coordinator, coordinator.vehicle_id),  # Disabled by default
    ]

    async_add_entities(entities)
