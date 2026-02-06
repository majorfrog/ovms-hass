"""Sensor entities for OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OVMSDataCoordinator
from .entities import (
    AltitudeSensor,
    AmbientTemperatureSensor,
    Battery12VCurrentSensor,
    Battery12VSensor,
    BatteryCapacitySensor,
    BatteryTemperatureSensor,
    BatteryVoltageSensor,
    CabinTemperatureSensor,
    CACSensor,
    ChargeKwhSensor,
    ChargeLimitRangeSensor,
    ChargerEfficiencySensor,
    ChargerPowerInputSensor,
    ChargerTemperatureSensor,
    ChargeTypeSensor,
    ChargingCurrentSensor,
    ChargingPowerSensor,
    ChargingStateSensor,
    ConnectionStatusSensor,
    DirectionSensor,
    DriveModeSensor,
    EnergyRecoveredSensor,
    EnergyUsedSensor,
    FirmwareVersionSensor,
    GridKwhSensor,
    GSMSignalSensor,
    HardwareVersionSensor,
    InverterEfficiencySensor,
    InverterPowerSensor,
    LastSeenSensor,
    LatitudeSensor,
    LongitudeSensor,
    ModemModeSensor,
    MotorTemperatureSensor,
    OdometerSensor,
    PEMTemperatureSensor,
    PowerSensor,
    RangeSensor,
    ServiceRangeSensor,
    ServiceTimeSensor,
    SpeedSensor,
    StateOfChargeSensor,
    StateOfHealthSensor,
    TimeToFullSensor,
    TotalGridKwhSensor,
    TripMeterSensor,
    WiFiSignalSensor,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: OVMSDataCoordinator = config_entry.runtime_data["coordinator"]

    entities = [
        # =================================================================
        # CORE SENSORS (Enabled by default)
        # =================================================================
        # Battery & Range
        StateOfChargeSensor(coordinator, coordinator.vehicle_id),
        StateOfHealthSensor(coordinator, coordinator.vehicle_id),
        RangeSensor(coordinator, coordinator.vehicle_id),
        BatteryCapacitySensor(coordinator, coordinator.vehicle_id),

        # Distance & Speed
        OdometerSensor(coordinator, coordinator.vehicle_id),
        SpeedSensor(coordinator, coordinator.vehicle_id),
        TripMeterSensor(coordinator, coordinator.vehicle_id),

        # Temperature (commonly used)
        AmbientTemperatureSensor(coordinator, coordinator.vehicle_id),
        CabinTemperatureSensor(coordinator, coordinator.vehicle_id),
        BatteryTemperatureSensor(coordinator, coordinator.vehicle_id),
        MotorTemperatureSensor(coordinator, coordinator.vehicle_id),

        # Charging
        ChargingStateSensor(coordinator, coordinator.vehicle_id),
        ChargingPowerSensor(coordinator, coordinator.vehicle_id),
        ChargingCurrentSensor(coordinator, coordinator.vehicle_id),
        ChargerPowerInputSensor(coordinator, coordinator.vehicle_id),
        ChargeTypeSensor(coordinator, coordinator.vehicle_id),
        ChargeKwhSensor(coordinator, coordinator.vehicle_id),
        TimeToFullSensor(coordinator, coordinator.vehicle_id),

        # Power & Driving
        PowerSensor(coordinator, coordinator.vehicle_id),
        EnergyUsedSensor(coordinator, coordinator.vehicle_id),
        EnergyRecoveredSensor(coordinator, coordinator.vehicle_id),

        # 12V Battery
        Battery12VSensor(coordinator, coordinator.vehicle_id),
        BatteryVoltageSensor(coordinator, coordinator.vehicle_id),

        # Location
        LatitudeSensor(coordinator, coordinator.vehicle_id),
        LongitudeSensor(coordinator, coordinator.vehicle_id),
        AltitudeSensor(coordinator, coordinator.vehicle_id),
        DirectionSensor(coordinator, coordinator.vehicle_id),

        # Connectivity
        LastSeenSensor(coordinator, coordinator.vehicle_id),
        GSMSignalSensor(coordinator, coordinator.vehicle_id),
        WiFiSignalSensor(coordinator, coordinator.vehicle_id),
        ConnectionStatusSensor(coordinator, coordinator.vehicle_id),

        # =================================================================
        # OPTIONAL SENSORS (Disabled by default - technical/diagnostic)
        # =================================================================
        # Temperature (technical)
        PEMTemperatureSensor(coordinator, coordinator.vehicle_id),
        ChargerTemperatureSensor(coordinator, coordinator.vehicle_id),

        # Battery/Power (technical)
        Battery12VCurrentSensor(coordinator, coordinator.vehicle_id),
        CACSensor(coordinator, coordinator.vehicle_id),
        DriveModeSensor(coordinator, coordinator.vehicle_id),
        InverterPowerSensor(coordinator, coordinator.vehicle_id),
        InverterEfficiencySensor(coordinator, coordinator.vehicle_id),

        # Charging (technical)
        ChargeLimitRangeSensor(coordinator, coordinator.vehicle_id),
        GridKwhSensor(coordinator, coordinator.vehicle_id),
        TotalGridKwhSensor(coordinator, coordinator.vehicle_id),
        ChargerEfficiencySensor(coordinator, coordinator.vehicle_id),

        # Diagnostic
        FirmwareVersionSensor(coordinator, coordinator.vehicle_id),
        HardwareVersionSensor(coordinator, coordinator.vehicle_id),
        ServiceRangeSensor(coordinator, coordinator.vehicle_id),
        ServiceTimeSensor(coordinator, coordinator.vehicle_id),
        ModemModeSensor(coordinator, coordinator.vehicle_id),
    ]

    async_add_entities(entities)
