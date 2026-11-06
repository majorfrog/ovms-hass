"""Tests for the REST poll in the coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ovms_hass.api import (
    ChargeStatus,
    LocationData,
    OVMSApiClient,
    OVMSConnectionError,
    TPMSData,
    VehicleStatus,
)
from custom_components.ovms_hass.coordinator import OVMSDataCoordinator

DOWN = OVMSConnectionError("down")


def _api(soc: int = 80, connected: int = 1) -> MagicMock:
    api = MagicMock(spec=OVMSApiClient)
    api.get_status = AsyncMock(return_value=VehicleStatus(soc=soc))
    api.get_charge = AsyncMock(return_value=ChargeStatus(chargelimit=90))
    api.get_location = AsyncMock(return_value=LocationData(latitude=59.0))
    api.get_tpms = AsyncMock(return_value=TPMSData(fl_pressure=250.0))
    api.get_vehicle = AsyncMock(return_value={"v_net_connected": connected})
    return api


async def test_failed_section_keeps_previous_values(hass: HomeAssistant) -> None:
    """One failed fetch must not blank that section's sensors."""
    api = _api(soc=80)
    coord = OVMSDataCoordinator(hass, api, "APA123")
    await coord._async_update_data()

    api.get_status.side_effect = DOWN
    api.get_charge.return_value = ChargeStatus(chargelimit=70)
    data = await coord._async_update_data()

    assert data["status"]["soc"] == 80
    assert data["charge"]["chargelimit"] == 70


async def test_failed_connection_fetch_keeps_previous_state(
    hass: HomeAssistant,
) -> None:
    """A failed fetch must not make the car look disconnected."""
    api = _api(connected=1)
    coord = OVMSDataCoordinator(hass, api, "APA123")
    await coord._async_update_data()

    api.get_vehicle.side_effect = DOWN
    data = await coord._async_update_data()

    assert data["vehicle"]["v_net_connected"] == 1


async def test_all_fetches_failing_raises_update_failed(hass: HomeAssistant) -> None:
    """With nothing fetched, entities should go unavailable, not keep old data."""
    api = _api()
    for method in ("get_status", "get_charge", "get_location", "get_tpms", "get_vehicle"):
        getattr(api, method).side_effect = DOWN
    coord = OVMSDataCoordinator(hass, api, "APA123")

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_pushed_values_survive_failed_status_fetch(hass: HomeAssistant) -> None:
    """Protocol v2 values stay in the status when its REST fetch fails."""
    api = _api()
    coord = OVMSDataCoordinator(hass, api, "APA123")
    coord.ovms_client = MagicMock(protocol_data={"hvac": True})
    await coord._async_update_data()

    api.get_status.side_effect = DOWN
    data = await coord._async_update_data()

    assert data["status"]["hvac"] is True
