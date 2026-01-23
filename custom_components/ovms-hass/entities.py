"""Home Assistant entity definitions for OVMS integration.

This module defines Home Assistant entity classes suitable for OVMS vehicle data.
Each entity type (Climate, Lock, Sensor, etc.) is tailored to represent the
corresponding vehicle feature appropriately within Home Assistant.
"""

from __future__ import annotations

from abc import ABC
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.button import ButtonEntity
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.lock import LockEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
class EntityConfig:
    """Configuration for an entity."""

    unique_id: str
    """Unique identifier for the entity"""

    name: str
    """Human-readable entity name"""

    icon: str | None = None
    """Home Assistant icon name"""

    unit_of_measurement: str | None = None
    """Unit of measurement for sensors"""


class OVMSEntity(CoordinatorEntity, ABC):
    """Base class for OVMS entities.

    Provides common functionality for all OVMS-backed Home Assistant entities.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        config: EntityConfig,
        vehicle_id: str,
    ) -> None:
        """Initialize OVMS entity.

        Args:
            coordinator: Data coordinator for updates
            config: Entity configuration
            vehicle_id: OVMS vehicle ID
        """
        super().__init__(coordinator)
        self.vehicle_id = vehicle_id
        # Sanitize vehicle_id for use in unique_id (remove spaces and special chars)
        safe_vehicle_id = "".join(c if c.isalnum() else "_" for c in vehicle_id)
        self._attr_unique_id = f"ovms_{safe_vehicle_id}_{config.unique_id}"
        self._attr_name = config.name
        if config.icon:
            self._attr_icon = config.icon
        if config.unit_of_measurement:
            self._attr_native_unit_of_measurement = config.unit_of_measurement

    @property
    def device_info(self) -> dict:
        """Return device info for device registry."""
        status = self.coordinator.data.get("status", {})

        # Get device information from API
        car_type = status.get("car_type") or "Unknown"
        firmware = status.get("m_firmware") or status.get("m_version")
        hardware = status.get("m_hardware")
        vin = status.get("car_vin")

        device_info = {
            "identifiers": {("ovms", self.vehicle_id)},
            "name": self.vehicle_id,
            "manufacturer": "OVMS",
            "model": f"{car_type} Vehicle Monitor"
            if car_type != "Unknown"
            else "Vehicle Monitor",
        }

        # Add optional fields if available
        if firmware:
            device_info["sw_version"] = firmware
        if hardware:
            device_info["hw_version"] = hardware
        if vin:
            device_info["serial_number"] = vin

        return device_info


class ClimateControlEntity(OVMSEntity, ClimateEntity):
    """HVAC/Climate control entity for AC control."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    _attr_supported_features = ClimateEntityFeature(0)
    _attr_target_temperature_step = 1
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: Any,
        vehicle_id: str,
    ) -> None:
        """Initialize climate entity.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="climate",
            name="Climate Control",
            icon="mdi:air-conditioner",
        )
        super().__init__(coordinator, config, vehicle_id)
        self._hvac_mode = HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return current cabin temperature."""
        temp = self.coordinator.data.get("status", {}).get("temperature_cabin")
        if temp is not None:
            try:
                return float(temp)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature (not directly available)."""
        return self.current_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        is_on = self.coordinator.data.get("status", {}).get("hvac_on", False)
        return HVACMode.COOL if is_on else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode.

        Args:
            hvac_mode: New HVAC mode
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot control HVAC")
            return

        try:
            if hvac_mode == HVACMode.COOL:
                await self.coordinator.ovms_client.send_command("26,1")
            elif hvac_mode == HVACMode.OFF:
                await self.coordinator.ovms_client.send_command("26,0")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to set HVAC mode to %s: %s", hvac_mode, err)


class AmbientTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for ambient (outside) temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize ambient temperature sensor."""
        config = EntityConfig(
            unique_id="temp_ambient",
            name="Ambient Temperature",
            icon="mdi:thermometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return ambient temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_ambient")


class CabinTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for cabin (interior) temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize cabin temperature sensor."""
        config = EntityConfig(
            unique_id="temp_cabin",
            name="Cabin Temperature",
            icon="mdi:thermometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return cabin temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_cabin")


class BatteryTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for battery temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize battery temperature sensor."""
        config = EntityConfig(
            unique_id="temp_battery",
            name="Battery Temperature",
            icon="mdi:thermometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return battery temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_battery")


class StateOfChargeSensor(OVMSEntity, SensorEntity):
    """Sensor for state of charge (battery %)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize SOC sensor."""
        config = EntityConfig(
            unique_id="soc",
            name="State of Charge",
            icon="mdi:battery",
        )
        super().__init__(coordinator, config, vehicle_id)
        self._soc_source = "status.soc"

    @property
    def native_value(self) -> int | None:
        """Return state of charge percentage."""
        # Try multiple SOC sources with fallback logic
        # Primary: status.soc
        soc = self.coordinator.data.get("status", {}).get("soc")
        soc_source = "status.soc"

        # Fallback 1: charge.soc (some OVMS configs report SOC here)
        if soc is None or soc == 0:
            charge_soc = self.coordinator.data.get("charge", {}).get("soc")
            if charge_soc not in (None, 0):
                soc = charge_soc
                soc_source = "charge.soc"

        # Store source for diagnostic purposes
        self._soc_source = soc_source

        # Return None instead of 0 if truly unavailable
        return soc if soc not in (None, 0) else None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        attrs = {}

        # Show which field provided the SOC value
        if hasattr(self, "_soc_source"):
            attrs["source"] = self._soc_source

        # Show raw values for debugging
        status_soc = self.coordinator.data.get("status", {}).get("soc")
        charge_soc = self.coordinator.data.get("charge", {}).get("soc")

        attrs["status_soc_raw"] = status_soc
        attrs["charge_soc_raw"] = charge_soc

        # Show SOH if available (helps diagnose battery issues)
        soh = self.coordinator.data.get("status", {}).get("soh")
        if soh is not None:
            attrs["battery_health"] = soh

        return attrs


class RangeSensor(OVMSEntity, SensorEntity):
    """Sensor for estimated driving range."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize range sensor."""
        config = EntityConfig(
            unique_id="range",
            name="Estimated Range",
            icon="mdi:map-marker-distance",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return estimated range."""
        return self.coordinator.data.get("status", {}).get("estimatedrange")


class OdometerSensor(OVMSEntity, SensorEntity):
    """Sensor for vehicle odometer reading."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize odometer sensor."""
        config = EntityConfig(
            unique_id="odometer",
            name="Odometer",
            icon="mdi:speedometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return odometer reading."""
        return self.coordinator.data.get("status", {}).get("odometer")


class SpeedSensor(OVMSEntity, SensorEntity):
    """Sensor for current vehicle speed."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize speed sensor."""
        config = EntityConfig(
            unique_id="speed",
            name="Speed",
            icon="mdi:speedometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return current speed."""
        return self.coordinator.data.get("status", {}).get("speed")


class ChargingPowerSensor(OVMSEntity, SensorEntity):
    """Sensor for current charging power."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charging power sensor."""
        config = EntityConfig(
            unique_id="charge_power",
            name="Charging Power",
            icon="mdi:flash",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return charging power."""
        return self.coordinator.data.get("charge", {}).get("chargepower")


class ChargingCurrentSensor(OVMSEntity, SensorEntity):
    """Sensor for charging current."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "A"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charging current sensor."""
        config = EntityConfig(
            unique_id="charge_current",
            name="Charging Current",
            icon="mdi:current-ac",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return charging current."""
        return self.coordinator.data.get("charge", {}).get("chargecurrent")


class ChargingStateSensor(OVMSEntity, SensorEntity):
    """Sensor for charging state."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charging state sensor."""
        config = EntityConfig(
            unique_id="charge_state",
            name="Charging State",
            icon="mdi:battery-charging",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return charging state."""
        return self.coordinator.data.get("charge", {}).get("chargestate")


class TimeToFullSensor(OVMSEntity, SensorEntity):
    """Sensor for estimated time to full charge."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize time to full sensor."""
        config = EntityConfig(
            unique_id="charge_etr_full",
            name="Time to Full",
            icon="mdi:timer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return estimated time to full charge."""
        return self.coordinator.data.get("charge", {}).get("charge_etr_full")


class StateOfHealthSensor(OVMSEntity, SensorEntity):
    """Sensor for battery state of health."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize state of health sensor."""
        config = EntityConfig(
            unique_id="soh",
            name="State of Health",
            icon="mdi:battery-heart",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return battery state of health percentage."""
        return self.coordinator.data.get("status", {}).get("soh")


class Battery12VSensor(OVMSEntity, SensorEntity):
    """Sensor for 12V auxiliary battery voltage."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "V"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize 12V battery sensor."""
        config = EntityConfig(
            unique_id="vehicle12v",
            name="12V Battery",
            icon="mdi:car-battery",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return 12V battery voltage."""
        return self.coordinator.data.get("status", {}).get("vehicle12v")


class Battery12VCurrentSensor(OVMSEntity, SensorEntity):
    """Sensor for 12V auxiliary battery current."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "A"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize 12V battery current sensor."""
        config = EntityConfig(
            unique_id="vehicle12v_current",
            name="12V Battery Current",
            icon="mdi:current-dc",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return 12V battery current."""
        return self.coordinator.data.get("status", {}).get("vehicle12v_current")


class LatitudeSensor(OVMSEntity, SensorEntity):
    """Sensor for GPS latitude."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize latitude sensor."""
        config = EntityConfig(
            unique_id="latitude",
            name="Latitude",
            icon="mdi:crosshairs-gps",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return latitude."""
        return self.coordinator.data.get("location", {}).get("latitude")


class LongitudeSensor(OVMSEntity, SensorEntity):
    """Sensor for GPS longitude."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize longitude sensor."""
        config = EntityConfig(
            unique_id="longitude",
            name="Longitude",
            icon="mdi:crosshairs-gps",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return longitude."""
        return self.coordinator.data.get("location", {}).get("longitude")


class AltitudeSensor(OVMSEntity, SensorEntity):
    """Sensor for GPS altitude."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "m"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize altitude sensor."""
        config = EntityConfig(
            unique_id="altitude",
            name="Altitude",
            icon="mdi:image-filter-hdr",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return altitude in meters."""
        return self.coordinator.data.get("location", {}).get("altitude")


class DirectionSensor(OVMSEntity, SensorEntity):
    """Sensor for vehicle direction/heading."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "°"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize direction sensor."""
        config = EntityConfig(
            unique_id="direction",
            name="Direction",
            icon="mdi:compass",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return direction in degrees."""
        return self.coordinator.data.get("location", {}).get("direction")


class BatteryVoltageSensor(OVMSEntity, SensorEntity):
    """Sensor for main battery pack voltage."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "V"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize battery voltage sensor."""
        config = EntityConfig(
            unique_id="battvoltage",
            name="Battery Voltage",
            icon="mdi:lightning-bolt",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return battery pack voltage."""
        return self.coordinator.data.get("charge", {}).get("battvoltage")


class EnergyUsedSensor(OVMSEntity, SensorEntity):
    """Sensor for energy used."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize energy used sensor."""
        config = EntityConfig(
            unique_id="energyused",
            name="Energy Used",
            icon="mdi:lightning-bolt",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return energy used."""
        return self.coordinator.data.get("location", {}).get("energyused")


class EnergyRecoveredSensor(OVMSEntity, SensorEntity):
    """Sensor for energy recovered through regeneration."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize energy recovered sensor."""
        config = EntityConfig(
            unique_id="energyrecd",
            name="Energy Recovered",
            icon="mdi:recycle",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return energy recovered."""
        return self.coordinator.data.get("location", {}).get("energyrecd")


class LastSeenSensor(OVMSEntity, SensorEntity):
    """Sensor for when OVMS unit last communicated with server."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize last seen sensor."""
        config = EntityConfig(
            unique_id="last_seen",
            name="Last Seen",
            icon="mdi:clock-outline",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> datetime | None:
        """Return last seen timestamp."""
        # Try status message time first, fall back to other message times
        timestamp_str = (
            self.coordinator.data.get("status", {}).get("m_msgtime_s")
            or self.coordinator.data.get("charge", {}).get("m_msgtime_s")
            or self.coordinator.data.get("location", {}).get("m_msgtime_l")
        )

        if timestamp_str:
            try:
                # Parse ISO format timestamp and make it UTC aware
                dt = datetime.fromisoformat(timestamp_str.replace(" ", "T"))
                # If timezone-naive, assume UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                return None
            else:
                return dt

        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        attrs = {}

        # Add age in seconds if available
        age = self.coordinator.data.get("status", {}).get("m_msgage_s")
        if age is not None:
            attrs["age_seconds"] = age

        return attrs


class GSMSignalSensor(OVMSEntity, SensorEntity):
    """Sensor for GSM signal strength."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "dBm"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize GSM signal sensor."""
        config = EntityConfig(
            unique_id="gsm_signal",
            name="GSM Signal",
            icon="mdi:signal-cellular-3",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return GSM signal strength."""
        return self.coordinator.data.get("status", {}).get("car_gsm_signal")


class WiFiSignalSensor(OVMSEntity, SensorEntity):
    """Sensor for WiFi signal strength."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "dBm"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize WiFi signal sensor."""
        config = EntityConfig(
            unique_id="wifi_signal",
            name="WiFi Signal",
            icon="mdi:wifi",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return WiFi signal strength."""
        return self.coordinator.data.get("status", {}).get("car_wifi_signal")


class ConnectionStatusSensor(OVMSEntity, SensorEntity):
    """Binary sensor for vehicle server connection status."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize connection status sensor."""
        config = EntityConfig(
            unique_id="connection_status",
            name="Connection Status",
            icon="mdi:lan-connect",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str:
        """Return connection status."""
        v_net_connected = self.coordinator.data.get("vehicle", {}).get(
            "v_net_connected", 0
        )
        return "connected" if v_net_connected > 0 else "disconnected"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        vehicle_data = self.coordinator.data.get("vehicle", {})
        return {
            "car_connections": vehicle_data.get("v_net_connected", 0),
            "app_connections": vehicle_data.get("v_apps_connected", 0),
            "batch_connections": vehicle_data.get("v_btcs_connected", 0),
        }


class DoorLockEntity(OVMSEntity, LockEntity):
    """Lock entity for vehicle door locks."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize lock entity.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="lock",
            name="Door Lock",
            icon="mdi:lock",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_locked(self) -> bool | None:
        """Return lock state."""
        return self.coordinator.data.get("status", {}).get("carlocked")

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle.

        Args:
            **kwargs: Additional arguments
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot lock vehicle")
            return

        try:
            await self.coordinator.ovms_client.send_command("20")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to lock vehicle: %s", err)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle.

        Args:
            **kwargs: Additional arguments
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot unlock vehicle")
            return

        try:
            await self.coordinator.ovms_client.send_command("22")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to unlock vehicle: %s", err)


class CooldownSwitch(OVMSEntity, SwitchEntity):
    """Switch for battery/cabin cooldown."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize cooldown switch.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="cooldown",
            name="Cooldown",
            icon="mdi:water-percent",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return cooldown state."""
        return self.coordinator.data.get("charge", {}).get("cooldown_active", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate cooldown.

        Args:
            **kwargs: Additional arguments
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error(
                "OVMS Protocol client not available, cannot activate cooldown"
            )
            return

        try:
            await self.coordinator.ovms_client.send_command("25")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to activate cooldown: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate cooldown (no direct command available).

        Args:
            **kwargs: Additional arguments
        """
        # OVMS doesn't provide a direct cooldown OFF command
        _LOGGER.debug("Cooldown OFF not supported by OVMS")


class ValetModeSwitch(OVMSEntity, SwitchEntity):
    """Switch for valet mode."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize valet mode switch.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="valet_mode",
            name="Valet Mode",
            icon="mdi:car-key",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return valet mode state."""
        return self.coordinator.data.get("status", {}).get("valetmode", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable valet mode.

        Args:
            **kwargs: Additional arguments
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error(
                "OVMS Protocol client not available, cannot enable valet mode"
            )
            return

        try:
            await self.coordinator.ovms_client.send_command("21")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to enable valet mode: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable valet mode.

        Args:
            **kwargs: Additional arguments
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error(
                "OVMS Protocol client not available, cannot disable valet mode"
            )
            return

        try:
            await self.coordinator.ovms_client.send_command("23")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to disable valet mode: %s", err)


class ChargeLimitNumber(OVMSEntity, NumberEntity):
    """Number entity for setting charge limit SOC."""

    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charge limit number entity.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="charge_limit",
            name="Charge Limit",
            icon="mdi:battery-charging-100",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return current charge limit."""
        return self.coordinator.data.get("charge", {}).get("chargelimit")

    async def async_set_native_value(self, value: float) -> None:
        """Set charge limit SOC.

        Args:
            value: Target SOC percentage
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot set charge limit")
            return

        try:
            soc_int = int(value)
            await self.coordinator.ovms_client.send_command(f"16,{soc_int}")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to set charge limit: %s", err)


class ChargingCurrentNumber(OVMSEntity, NumberEntity):
    """Number entity for setting charging current."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "A"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charging current number entity.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="charge_current",
            name="Charge Current",
            icon="mdi:current-ac",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return current charging current setting."""
        return self.coordinator.data.get("charge", {}).get("chargecurrent")

    async def async_set_native_value(self, value: float) -> None:
        """Set charging current.

        Args:
            value: Charging current in amperes
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error(
                "OVMS Protocol client not available, cannot set charging current"
            )
            return

        try:
            amps_int = int(value)
            await self.coordinator.ovms_client.send_command(f"15,{amps_int}")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to set charging current: %s", err)


class GPSStreamingIntervalNumber(OVMSEntity, NumberEntity):
    """Number entity for setting GPS streaming interval (feature #8)."""

    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "s"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize GPS streaming interval number entity.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="gps_streaming_interval",
            name="GPS Streaming Interval",
            icon="mdi:map-marker-radius",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return current GPS streaming interval from feature #8."""
        features = self.coordinator.data.get("features", {})
        value = features.get(8)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set GPS streaming interval using command 2.

        Args:
            value: Streaming interval in seconds
        """
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot set GPS interval")
            return

        try:
            interval_int = int(value)
            # Command 2 format: "2,<feature_slot>,<value>"
            await self.coordinator.ovms_client.send_command(f"2,8,{interval_int}")
            # Update local cache
            features = self.coordinator.data.get("features", {})
            features[8] = str(interval_int)
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to set GPS streaming interval: %s", err)


class RefreshButton(OVMSEntity, ButtonEntity):
    """Button entity to manually refresh vehicle data."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize refresh button.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="refresh",
            name="Refresh Data",
            icon="mdi:refresh",
        )
        super().__init__(coordinator, config, vehicle_id)

    async def async_press(self) -> None:
        """Handle button press - refresh vehicle data immediately."""
        _LOGGER.info("Manual refresh requested for vehicle %s", self.vehicle_id)
        await self.coordinator.async_request_refresh()


class WakeUpButton(OVMSEntity, ButtonEntity):
    """Button entity to wake up the vehicle."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize wake-up button.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="wakeup",
            name="Wake Up",
            icon="mdi:sleep",
        )
        super().__init__(coordinator, config, vehicle_id)

    async def async_press(self) -> None:
        """Handle button press - send wake-up command to vehicle."""
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot wake up vehicle")
            return

        try:
            _LOGGER.info("Sending wake-up command to vehicle %s", self.vehicle_id)
            await self.coordinator.ovms_client.send_command("18")
            # Wait a moment for the vehicle to wake up before refreshing
            await asyncio.sleep(2)
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to wake up vehicle: %s", err)


class HomeLinkButton(OVMSEntity, ButtonEntity):
    """Button entity to activate HomeLink."""

    def __init__(self, coordinator: Any, vehicle_id: str, button_number: int) -> None:
        """Initialize HomeLink button.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
            button_number: HomeLink button number (0, 1, or 2)
        """
        self.button_number = button_number
        config = EntityConfig(
            unique_id=f"homelink_{button_number + 1}",
            name=f"HomeLink {button_number + 1}",
            icon="mdi:garage",
        )
        super().__init__(coordinator, config, vehicle_id)

    async def async_press(self) -> None:
        """Handle button press - activate HomeLink."""
        if not self.coordinator.ovms_client:
            _LOGGER.error(
                "OVMS Protocol client not available, cannot activate HomeLink"
            )
            return

        try:
            _LOGGER.info(
                "Activating HomeLink %d for vehicle %s",
                self.button_number + 1,
                self.vehicle_id,
            )
            await self.coordinator.ovms_client.send_command(f"24,{self.button_number}")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to activate HomeLink: %s", err)


class ModuleResetButton(OVMSEntity, ButtonEntity):
    """Button entity to reset OVMS module."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize module reset button.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="module_reset",
            name="Module Reset",
            icon="mdi:restart",
        )
        super().__init__(coordinator, config, vehicle_id)

    async def async_press(self) -> None:
        """Handle button press - reset OVMS module."""
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot reset module")
            return

        try:
            _LOGGER.info("Resetting OVMS module for vehicle %s", self.vehicle_id)
            await self.coordinator.ovms_client.send_command("5")
            # Module will restart, don't refresh immediately
            _LOGGER.info("Module reset command sent, module will restart")
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to reset module: %s", err)


class VehicleTracker(OVMSEntity, TrackerEntity):
    """Device tracker entity for vehicle GPS location."""

    _attr_icon = "mdi:car"

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize vehicle tracker.

        Args:
            coordinator: Data coordinator
            vehicle_id: OVMS vehicle ID
        """
        config = EntityConfig(
            unique_id="tracker",
            name="Location",
            icon="mdi:car",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        lat = self.coordinator.data.get("location", {}).get("latitude")
        if lat is not None:
            try:
                return float(lat)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        lon = self.coordinator.data.get("location", {}).get("longitude")
        if lon is not None:
            try:
                return float(lon)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.GPS

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the device."""
        return self.coordinator.data.get("status", {}).get("soc")

    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy in meters."""
        # If GPS lock is available and not stale, assume good accuracy
        gpslock = self.coordinator.data.get("location", {}).get("gpslock", False)
        stalegps = self.coordinator.data.get("location", {}).get("stalegps", True)

        if gpslock and not stalegps:
            return 10  # Good GPS lock
        if gpslock:
            return 50  # GPS lock but stale
        return 100  # No GPS lock


# =============================================================================
# NEW BINARY SENSORS
# =============================================================================


class FrontLeftDoorSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for front left door status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize front left door sensor."""
        config = EntityConfig(
            unique_id="fl_dooropen",
            name="Front Left Door",
            icon="mdi:car-door",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open."""
        return self.coordinator.data.get("status", {}).get("fl_dooropen")


class FrontRightDoorSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for front right door status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize front right door sensor."""
        config = EntityConfig(
            unique_id="fr_dooropen",
            name="Front Right Door",
            icon="mdi:car-door",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open."""
        return self.coordinator.data.get("status", {}).get("fr_dooropen")


class RearLeftDoorSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for rear left door status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize rear left door sensor."""
        config = EntityConfig(
            unique_id="rl_dooropen",
            name="Rear Left Door",
            icon="mdi:car-door",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open."""
        return self.coordinator.data.get("status", {}).get("rl_dooropen")


class RearRightDoorSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for rear right door status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize rear right door sensor."""
        config = EntityConfig(
            unique_id="rr_dooropen",
            name="Rear Right Door",
            icon="mdi:car-door",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open."""
        return self.coordinator.data.get("status", {}).get("rr_dooropen")


class BonnetSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for bonnet/hood status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize bonnet sensor."""
        config = EntityConfig(
            unique_id="bt_open",
            name="Bonnet",
            icon="mdi:car",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if bonnet is open."""
        return self.coordinator.data.get("status", {}).get("bt_open")


class TrunkSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for trunk status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize trunk sensor."""
        config = EntityConfig(
            unique_id="tr_open",
            name="Trunk",
            icon="mdi:car-back",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if trunk is open."""
        return self.coordinator.data.get("status", {}).get("tr_open")


class ChargePortSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for charge port status."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charge port sensor."""
        config = EntityConfig(
            unique_id="cp_dooropen",
            name="Charge Port",
            icon="mdi:ev-plug-type2",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if charge port is open."""
        return self.coordinator.data.get("status", {}).get("cp_dooropen")


class ParkingBrakeSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for parking brake status."""

    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize parking brake sensor."""
        config = EntityConfig(
            unique_id="handbrake",
            name="Parking Brake",
            icon="mdi:car-brake-parking",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if parking brake is engaged."""
        return self.coordinator.data.get("status", {}).get("handbrake")


class PilotPresentSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for charge pilot present (plugged in)."""

    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize pilot present sensor."""
        config = EntityConfig(
            unique_id="pilotpresent",
            name="Charger Plugged In",
            icon="mdi:ev-plug-type2",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if charger is plugged in."""
        return self.coordinator.data.get("status", {}).get("pilotpresent")


class CarOnSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for car on/started status."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize car on sensor."""
        config = EntityConfig(
            unique_id="caron",
            name="Car Started",
            icon="mdi:car-key",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if car is on/started."""
        return self.coordinator.data.get("status", {}).get("caron")


class HeadlightsSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for headlights status."""

    _attr_device_class = BinarySensorDeviceClass.LIGHT
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize headlights sensor."""
        config = EntityConfig(
            unique_id="headlights",
            name="Headlights",
            icon="mdi:car-light-high",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if headlights are on."""
        return self.coordinator.data.get("status", {}).get("headlights")


class AlarmSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for alarm sounding status."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize alarm sensor."""
        config = EntityConfig(
            unique_id="alarmsounding",
            name="Alarm",
            icon="mdi:car-emergency",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if alarm is sounding."""
        return self.coordinator.data.get("status", {}).get("alarmsounding")


class GPSLockSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for GPS lock status."""

    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize GPS lock sensor."""
        config = EntityConfig(
            unique_id="gpslock",
            name="GPS Lock",
            icon="mdi:crosshairs-gps",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if GPS has a lock."""
        return self.coordinator.data.get("location", {}).get("gpslock")


# =============================================================================
# NEW TEMPERATURE SENSORS
# =============================================================================


class PEMTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for Power Electronics Module temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize PEM temperature sensor."""
        config = EntityConfig(
            unique_id="temp_pem",
            name="PEM Temperature",
            icon="mdi:thermometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return PEM temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_pem")


class MotorTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for motor temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize motor temperature sensor."""
        config = EntityConfig(
            unique_id="temp_motor",
            name="Motor Temperature",
            icon="mdi:engine",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return motor temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_motor")


class ChargerTemperatureSensor(OVMSEntity, SensorEntity):
    """Sensor for charger temperature."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charger temperature sensor."""
        config = EntityConfig(
            unique_id="temp_charger",
            name="Charger Temperature",
            icon="mdi:thermometer",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return charger temperature."""
        return self.coordinator.data.get("status", {}).get("temperature_charger")


# =============================================================================
# NEW BATTERY/POWER SENSORS
# =============================================================================


class BatteryCapacitySensor(OVMSEntity, SensorEntity):
    """Sensor for battery capacity."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize battery capacity sensor."""
        config = EntityConfig(
            unique_id="batt_capacity",
            name="Battery Capacity",
            icon="mdi:battery-high",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return battery capacity in kWh."""
        return self.coordinator.data.get("charge", {}).get("batt_capacity")


class CACSensor(OVMSEntity, SensorEntity):
    """Sensor for Calculated Amp Capacity (CAC)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Ah"
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize CAC sensor."""
        config = EntityConfig(
            unique_id="cac",
            name="CAC (Amp Capacity)",
            icon="mdi:battery-heart-variant",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return calculated amp capacity."""
        return self.coordinator.data.get("charge", {}).get("cac100")


class DriveModeSensor(OVMSEntity, SensorEntity):
    """Sensor for drive mode."""

    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize drive mode sensor."""
        config = EntityConfig(
            unique_id="drivemode",
            name="Drive Mode",
            icon="mdi:car-cruise-control",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return drive mode."""
        return self.coordinator.data.get("location", {}).get("drivemode")


class PowerSensor(OVMSEntity, SensorEntity):
    """Sensor for instantaneous power draw/output."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize power sensor."""
        config = EntityConfig(
            unique_id="power",
            name="Power",
            icon="mdi:flash",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return instantaneous power."""
        return self.coordinator.data.get("location", {}).get("power")


class InverterPowerSensor(OVMSEntity, SensorEntity):
    """Sensor for inverter power."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize inverter power sensor."""
        config = EntityConfig(
            unique_id="invpower",
            name="Inverter Power",
            icon="mdi:current-ac",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return inverter power in kW."""
        return self.coordinator.data.get("location", {}).get("invpower")


class InverterEfficiencySensor(OVMSEntity, SensorEntity):
    """Sensor for inverter efficiency."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize inverter efficiency sensor."""
        config = EntityConfig(
            unique_id="invefficiency",
            name="Inverter Efficiency",
            icon="mdi:gauge",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return inverter efficiency percentage."""
        return self.coordinator.data.get("location", {}).get("invefficiency")


class TripMeterSensor(OVMSEntity, SensorEntity):
    """Sensor for trip meter (resettable distance)."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize trip meter sensor."""
        config = EntityConfig(
            unique_id="tripmeter",
            name="Trip Meter",
            icon="mdi:counter",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return trip meter distance."""
        # Try location first, then status
        tripmeter = self.coordinator.data.get("location", {}).get("tripmeter")
        if tripmeter is None:
            tripmeter = self.coordinator.data.get("status", {}).get("tripmeter")
        return tripmeter


# =============================================================================
# NEW CHARGING SENSORS
# =============================================================================


class ChargeTypeSensor(OVMSEntity, SensorEntity):
    """Sensor for charge type (AC/DC, Type 2, CCS, etc.)."""

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charge type sensor."""
        config = EntityConfig(
            unique_id="chargetype",
            name="Charge Type",
            icon="mdi:ev-plug-type2",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return charge type."""
        return self.coordinator.data.get("charge", {}).get("chargetype")


class ChargeLimitRangeSensor(OVMSEntity, SensorEntity):
    """Sensor for charge limit range."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charge limit range sensor."""
        config = EntityConfig(
            unique_id="charge_limit_range",
            name="Charge Limit Range",
            icon="mdi:map-marker-distance",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return charge limit range in km."""
        return self.coordinator.data.get("charge", {}).get("charge_limit_range")


class GridKwhSensor(OVMSEntity, SensorEntity):
    """Sensor for energy from grid during current charge session."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize grid kWh sensor."""
        config = EntityConfig(
            unique_id="charge_kwh_grid",
            name="Charge Grid Energy",
            icon="mdi:transmission-tower",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return grid energy in kWh."""
        return self.coordinator.data.get("charge", {}).get("charge_kwh_grid")


class TotalGridKwhSensor(OVMSEntity, SensorEntity):
    """Sensor for total lifetime energy from grid."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize total grid kWh sensor."""
        config = EntityConfig(
            unique_id="charge_kwh_grid_total",
            name="Total Grid Energy",
            icon="mdi:transmission-tower",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return total grid energy in kWh."""
        return self.coordinator.data.get("charge", {}).get("charge_kwh_grid_total")


class ChargerEfficiencySensor(OVMSEntity, SensorEntity):
    """Sensor for charger efficiency."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_registry_enabled_default = False  # Disabled by default (technical)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charger efficiency sensor."""
        config = EntityConfig(
            unique_id="chargerefficiency",
            name="Charger Efficiency",
            icon="mdi:gauge",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return charger efficiency percentage."""
        return self.coordinator.data.get("charge", {}).get("chargerefficiency")


class ChargerPowerInputSensor(OVMSEntity, SensorEntity):
    """Sensor for charger power input (power drawn from wallbox)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charger power input sensor."""
        config = EntityConfig(
            unique_id="chargepowerinput",
            name="Charger Power Input",
            icon="mdi:flash",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return charger power input in watts."""
        return self.coordinator.data.get("charge", {}).get("chargepowerinput")


class ChargeKwhSensor(OVMSEntity, SensorEntity):
    """Sensor for energy charged in current session."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize charge kWh sensor."""
        config = EntityConfig(
            unique_id="chargekwh",
            name="Charge Session Energy",
            icon="mdi:battery-charging",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> float | None:
        """Return energy charged in kWh."""
        return self.coordinator.data.get("charge", {}).get("chargekwh")


# =============================================================================
# NEW DIAGNOSTIC SENSORS
# =============================================================================


class FirmwareVersionSensor(OVMSEntity, SensorEntity):
    """Sensor for OVMS firmware version."""

    _attr_entity_registry_enabled_default = False  # Disabled by default (diagnostic)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize firmware version sensor."""
        config = EntityConfig(
            unique_id="firmware",
            name="Firmware Version",
            icon="mdi:memory",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return firmware version."""
        status = self.coordinator.data.get("status", {})
        return status.get("m_firmware") or status.get("m_version")


class HardwareVersionSensor(OVMSEntity, SensorEntity):
    """Sensor for OVMS hardware version."""

    _attr_entity_registry_enabled_default = False  # Disabled by default (diagnostic)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize hardware version sensor."""
        config = EntityConfig(
            unique_id="hardware",
            name="Hardware Version",
            icon="mdi:chip",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return hardware version."""
        return self.coordinator.data.get("status", {}).get("m_hardware")


class CanWriteSensor(OVMSEntity, BinarySensorEntity):
    """Binary sensor for CAN write capability."""

    _attr_entity_registry_enabled_default = False  # Disabled by default (diagnostic)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize CAN write sensor."""
        config = EntityConfig(
            unique_id="canwrite",
            name="CAN Write Enabled",
            icon="mdi:database-edit",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if CAN write is enabled."""
        return self.coordinator.data.get("status", {}).get("canwrite")


class ServiceRangeSensor(OVMSEntity, SensorEntity):
    """Sensor for distance until service is due."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_entity_registry_enabled_default = False  # Disabled by default
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize service range sensor."""
        config = EntityConfig(
            unique_id="servicerange",
            name="Service Range",
            icon="mdi:wrench-clock",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return distance until service in km."""
        value = self.coordinator.data.get("status", {}).get("servicerange")
        return value if value is not None and value >= 0 else None


class ServiceTimeSensor(OVMSEntity, SensorEntity):
    """Sensor for days until service is due."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_entity_registry_enabled_default = False  # Disabled by default
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize service time sensor."""
        config = EntityConfig(
            unique_id="servicetime",
            name="Service Time",
            icon="mdi:wrench-clock",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> int | None:
        """Return days until service."""
        value = self.coordinator.data.get("status", {}).get("servicetime")
        return value if value is not None and value >= 0 else None


class ModemModeSensor(OVMSEntity, SensorEntity):
    """Sensor for modem mode (2G/3G/4G)."""

    _attr_entity_registry_enabled_default = False  # Disabled by default (diagnostic)
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize modem mode sensor."""
        config = EntityConfig(
            unique_id="mdm_mode",
            name="Modem Mode",
            icon="mdi:signal-cellular-3",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self) -> str | None:
        """Return modem mode."""
        return self.coordinator.data.get("status", {}).get("m_mdm_mode")


# =============================================================================
# NEW BUTTONS
# =============================================================================


class TPMSResetButton(OVMSEntity, ButtonEntity):
    """Button to reset/auto-learn TPMS sensors."""

    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(self, coordinator: Any, vehicle_id: str) -> None:
        """Initialize TPMS reset button."""
        config = EntityConfig(
            unique_id="tpms_reset",
            name="TPMS Auto-Learn",
            icon="mdi:car-tire-alert",
        )
        super().__init__(coordinator, config, vehicle_id)

    async def async_press(self) -> None:
        """Handle button press - reset TPMS mapping."""
        if not self.coordinator.ovms_client:
            _LOGGER.error("OVMS Protocol client not available, cannot reset TPMS")
            return

        try:
            _LOGGER.info("Resetting TPMS mapping for vehicle %s", self.vehicle_id)
            await self.coordinator.ovms_client.send_command("7,tpms map reset")
            await self.coordinator.async_request_refresh()
        except (ValueError, KeyError, RuntimeError) as err:
            _LOGGER.error("Failed to reset TPMS: %s", err)
