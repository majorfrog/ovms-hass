"""Tests that the integration uses no deprecated HA APIs."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ovms_hass import entities

from .test_poll import _api
from .test_setup import _entry, _protocol_client, _setup


def test_tracker_does_not_override_battery_level() -> None:
    """HA 2026.10 warns when a tracker class defines battery_level itself.

    Same check as HA's BaseTrackerEntity.__init_subclass__ (the test venv's
    older HA doesn't have the warning yet).
    """
    assert "battery_level" not in entities.VehicleTracker.__dict__


def test_tracker_entity_not_imported_from_deprecated_alias() -> None:
    """device_tracker.config_entry.TrackerEntity is removed in HA 2027.6."""
    assert "device_tracker.config_entry import" not in inspect.getsource(entities)


async def test_coordinator_gets_config_entry_explicitly(hass: HomeAssistant) -> None:
    """HA reports coordinators that rely on the setup context for their entry."""
    entry = _entry(hass)
    api = _api()
    api.connect = AsyncMock()
    api.disconnect = AsyncMock()
    protocol = _protocol_client()
    protocol.protocol_data = {}

    with patch(
        "homeassistant.helpers.frame.report_usage"
    ) as report_usage:
        await _setup(hass, entry, api, protocol)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data["coordinator"].config_entry is entry
    report_usage.assert_not_called()
