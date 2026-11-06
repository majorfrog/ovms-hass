"""Tests for distance and charge-limit entities (values as OVMS reports them)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant

from custom_components.ovms_hass.coordinator import OVMSDataCoordinator
from custom_components.ovms_hass.entities import OdometerSensor, TripMeterSensor


def _coordinator(hass: HomeAssistant, status: dict, location: dict | None = None):
    coord = OVMSDataCoordinator(hass, MagicMock(), "APA123")
    coord.data["status"] = status
    coord.data["location"] = location or {}
    return coord


async def test_odometer_is_scaled_from_tenths(hass: HomeAssistant) -> None:
    """OVMS reports the odometer in 1/10 km: 1324320 is 132432 km."""
    sensor = OdometerSensor(_coordinator(hass, {"odometer": 1324320, "units": "K"}), "APA123")

    assert sensor.native_value == 132432.0
    assert sensor.native_unit_of_measurement == UnitOfLength.KILOMETERS


async def test_trip_meter_is_scaled_from_tenths(hass: HomeAssistant) -> None:
    """The trip meter is in 1/10 km too, from location first, then status."""
    coord = _coordinator(hass, {"tripmeter": 5}, {"tripmeter": 106})
    assert TripMeterSensor(coord, "APA123").native_value == 10.6

    coord = _coordinator(hass, {"tripmeter": 5})
    assert TripMeterSensor(coord, "APA123").native_value == 0.5


@pytest.mark.parametrize("sensor_cls", [OdometerSensor, TripMeterSensor])
async def test_distance_unit_follows_vehicle_units(
    hass: HomeAssistant, sensor_cls
) -> None:
    """A car set to miles reports tenths of a mile."""
    coord = _coordinator(hass, {"odometer": 100, "tripmeter": 100, "units": "M"})

    assert sensor_cls(coord, "APA123").native_unit_of_measurement == UnitOfLength.MILES


@pytest.mark.parametrize("raw", [None, "", "x"])
async def test_distance_missing_or_invalid_is_unknown(hass: HomeAssistant, raw) -> None:
    """No value, or one that isn't a number, shows unknown instead of raising."""
    coord = _coordinator(hass, {"odometer": raw, "tripmeter": raw})

    assert OdometerSensor(coord, "APA123").native_value is None
    assert TripMeterSensor(coord, "APA123").native_value is None


async def test_charge_current_number_shows_the_limit_not_the_measured_current(
    hass: HomeAssistant,
) -> None:
    """The number sets the charge current limit (command 15), so it must show
    the configured limit (S field 8, REST "chargelimit"), not the current
    flowing right now (REST "chargecurrent")."""
    from custom_components.ovms_hass.entities import ChargingCurrentNumber

    coord = _coordinator(hass, {})
    coord.data["charge"] = {"chargelimit": 16, "chargecurrent": -9.5}

    assert ChargingCurrentNumber(coord, "APA123").native_value == 16


async def test_charge_limit_soc_sensor_shows_configured_soc_limit(
    hass: HomeAssistant,
) -> None:
    """The SOC limit is read-only: S field 22, REST "charge_limit_soc"."""
    from homeassistant.const import PERCENTAGE

    from custom_components.ovms_hass.entities import ChargeLimitSOCSensor

    coord = _coordinator(hass, {})
    coord.data["charge"] = {"charge_limit_soc": 80, "chargelimit": 16}
    sensor = ChargeLimitSOCSensor(coord, "APA123")

    assert sensor.native_value == 80
    assert sensor.native_unit_of_measurement == PERCENTAGE
