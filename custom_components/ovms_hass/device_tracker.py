"""Device tracker entities for OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OVMSDataCoordinator
from .entities import VehicleTracker

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker entities."""
    coordinator: OVMSDataCoordinator = config_entry.runtime_data["coordinator"]

    entities = [
        VehicleTracker(coordinator, coordinator.vehicle_id),
    ]

    async_add_entities(entities)
