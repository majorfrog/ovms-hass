"""Binary sensor entities for OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OVMSDataCoordinator
from .entities import (
    AlarmSensor,
    BonnetSensor,
    CanWriteSensor,
    CarOnSensor,
    ChargePortSensor,
    FrontLeftDoorSensor,
    FrontRightDoorSensor,
    GPSLockSensor,
    HeadlightsSensor,
    ParkingBrakeSensor,
    PilotPresentSensor,
    RearLeftDoorSensor,
    RearRightDoorSensor,
    TrunkSensor,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: OVMSDataCoordinator = config_entry.runtime_data["coordinator"]

    entities = [
        # Door sensors (enabled by default - security relevant)
        FrontLeftDoorSensor(coordinator, coordinator.vehicle_id),
        FrontRightDoorSensor(coordinator, coordinator.vehicle_id),
        RearLeftDoorSensor(coordinator, coordinator.vehicle_id),  # Disabled by default
        RearRightDoorSensor(coordinator, coordinator.vehicle_id),  # Disabled by default

        # Hood/Trunk (enabled by default - security relevant)
        BonnetSensor(coordinator, coordinator.vehicle_id),
        TrunkSensor(coordinator, coordinator.vehicle_id),

        # Charge port (enabled by default - useful for charging workflows)
        ChargePortSensor(coordinator, coordinator.vehicle_id),

        # Vehicle state sensors
        PilotPresentSensor(coordinator, coordinator.vehicle_id),  # Enabled - useful for charging
        CarOnSensor(coordinator, coordinator.vehicle_id),  # Enabled - useful for automations
        AlarmSensor(coordinator, coordinator.vehicle_id),  # Enabled - security relevant

        # Less common sensors (disabled by default)
        ParkingBrakeSensor(coordinator, coordinator.vehicle_id),  # Disabled
        HeadlightsSensor(coordinator, coordinator.vehicle_id),  # Disabled
        GPSLockSensor(coordinator, coordinator.vehicle_id),  # Disabled

        # Diagnostic sensors (disabled by default)
        CanWriteSensor(coordinator, coordinator.vehicle_id),  # Disabled
    ]

    async_add_entities(entities)
