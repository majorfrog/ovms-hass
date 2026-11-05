"""Tests for querying v.e.hvac after AC ON/OFF."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ovms_hass import _async_connect_protocol
from custom_components.ovms_hass.coordinator import (
    OVMSCommandError,
    OVMSDataCoordinator,
    OVMSProtocolClient,
)
from custom_components.ovms_hass.entities import ACOnButton

# Confirmed on 2026-11-05: `metrics get v.e.hvac` replies "7,0,no", i.e. a
# bare "yes"/"no". The "v.e.hvac  yes" form (`metrics list`) is accepted as a fallback.

def reply(message: str) -> dict:
    return {"code": 7, "result": 0, "message": message}


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> OVMSDataCoordinator:
    """Coordinator wired to a connected protocol client with a mocked round-trip."""
    api = MagicMock()
    for name in ("get_status", "get_charge", "get_location", "get_tpms"):
        setattr(api, name, AsyncMock(return_value=SimpleNamespace(hvac=None)))
    api.get_vehicle = AsyncMock(return_value={})
    coord = OVMSDataCoordinator(hass, api, "APA123")
    client = OVMSProtocolClient("h", "u", "p", "APA123")
    client.connect = AsyncMock()
    client.start_background_reader = MagicMock()
    await _async_connect_protocol(coord, client)
    client.connected = True
    client.authenticated = True
    client.async_command = AsyncMock(return_value=reply("yes"))
    coord.async_request_refresh = AsyncMock()
    yield coord
    coord.async_cancel_hvac_followup()


@pytest.mark.parametrize(
    ("message", "expected"),
    [("yes", True), ("no", False), ("v.e.hvac       yes", True), ("1", True)],
)
async def test_query_parses_yes_and_no(
    coordinator: OVMSDataCoordinator, message: str, expected: bool
) -> None:
    """The metric value is parsed and pushed to the status data."""
    coordinator.ovms_client.async_command.return_value = reply(message)

    assert await coordinator.async_query_hvac() is expected
    assert coordinator.data["status"]["hvac"] is expected
    assert coordinator.ovms_client.async_command.await_args.args[0] == (
        "7,metrics get v.e.hvac"
    )


async def test_query_unparseable_returns_none(coordinator: OVMSDataCoordinator) -> None:
    """An unexpected reply leaves the HVAC state alone."""
    coordinator.data["status"]["hvac"] = False
    coordinator.ovms_client.async_command.return_value = reply("garbage")

    assert await coordinator.async_query_hvac() is None
    assert coordinator.data["status"]["hvac"] is False


async def test_followup_runs_at_15_and_60_s(
    hass: HomeAssistant, coordinator: OVMSDataCoordinator
) -> None:
    """The follow-up queries the metric at +15 s and +60 s."""
    coordinator.async_query_hvac = AsyncMock(return_value=True)
    now = dt_util.utcnow()

    coordinator.async_schedule_hvac_followup()
    async_fire_time_changed(hass, now + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert coordinator.async_query_hvac.await_count == 0

    async_fire_time_changed(hass, now + timedelta(seconds=16))
    await hass.async_block_till_done()
    assert coordinator.async_query_hvac.await_count == 1

    async_fire_time_changed(hass, now + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert coordinator.async_query_hvac.await_count == 2


async def test_followup_query_error_is_not_raised(
    hass: HomeAssistant, coordinator: OVMSDataCoordinator
) -> None:
    """A failed follow-up query is logged, not raised."""
    coordinator.async_query_hvac = AsyncMock(side_effect=OVMSCommandError("nope"))
    now = dt_util.utcnow()

    coordinator.async_schedule_hvac_followup()
    async_fire_time_changed(hass, now + timedelta(seconds=16))
    await hass.async_block_till_done()

    assert coordinator.async_query_hvac.await_count == 1


async def test_ac_on_press_schedules_followup(coordinator: OVMSDataCoordinator) -> None:
    """A successful AC ON press schedules the follow-up."""
    coordinator.ovms_client.async_command.return_value = {
        "code": 26,
        "result": 0,
        "message": "",
    }
    coordinator.async_schedule_hvac_followup = MagicMock()

    await ACOnButton(coordinator, "APA123").async_press()

    coordinator.async_schedule_hvac_followup.assert_called_once()


async def test_failed_ac_on_press_does_not_schedule_followup(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A failed AC ON press does not schedule the follow-up."""
    coordinator.ovms_client.async_command.return_value = None
    coordinator.async_schedule_hvac_followup = MagicMock()

    with pytest.raises(OVMSCommandError):
        await ACOnButton(coordinator, "APA123").async_press()

    coordinator.async_schedule_hvac_followup.assert_not_called()


async def test_poll_after_query_keeps_queried_hvac(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A REST poll after a query keeps the queried value."""
    coordinator.ovms_client.update_protocol_data({"hvac": False})
    coordinator.ovms_client.async_command.return_value = reply("yes")

    await coordinator.async_query_hvac()
    data = await coordinator._async_update_data()

    assert data["status"]["hvac"] is True


async def test_cancel_stops_running_query(
    hass: HomeAssistant, coordinator: OVMSDataCoordinator
) -> None:
    """Cancelling also cancels a query that is already running."""
    started = asyncio.Event()

    async def blocking_query() -> None:
        started.set()
        await asyncio.Event().wait()

    coordinator.async_query_hvac = blocking_query
    now = dt_util.utcnow()
    coordinator.async_schedule_hvac_followup()
    async_fire_time_changed(hass, now + timedelta(seconds=16))
    await started.wait()
    task = coordinator._hvac_query_task

    coordinator.async_cancel_hvac_followup()
    await asyncio.sleep(0)

    assert task.cancelled()
