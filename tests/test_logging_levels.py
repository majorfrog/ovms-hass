"""Tests that routine operation logs nothing at INFO or above."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ovms_hass.coordinator import OVMSDataCoordinator
from custom_components.ovms_hass.entities import ACOnButton

from . import test_commands
from .test_commands import _setup_entry
from .test_log_secrets import SERVER_TOKEN, _connect, _digest
from .test_poll import _api
from .test_setup import _entry, _protocol_client, _setup

# Fixture reused from the command tests (a coordinator with a mocked client)
coordinator = test_commands.coordinator


def _ovms_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname} {r.getMessage()}"
        for r in caplog.records
        if r.name.startswith("custom_components.ovms_hass")
        and r.levelno >= logging.INFO
    ]


async def test_command_button_and_service_log_nothing_at_info(
    hass: HomeAssistant,
    coordinator: OVMSDataCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful command, AC press and service call stay out of the log."""
    await _setup_entry(hass, coordinator)
    caplog.set_level(logging.INFO)
    caplog.clear()

    await coordinator.async_send_command("26,1", "AC ON")
    await ACOnButton(coordinator, "APA123").async_press()
    await hass.services.async_call(
        "ovms_hass",
        "send_command",
        {"vehicle_id": "APA123", "command": "metrics get v.e.hvac"},
        blocking=True,
    )

    assert _ovms_records(caplog) == []


async def test_setup_logs_nothing_at_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A successful setup stays out of the log."""
    caplog.set_level(logging.INFO)
    api = _api()
    api.connect = AsyncMock()
    api.disconnect = AsyncMock()
    protocol = _protocol_client()
    protocol.protocol_data = {}

    await _setup(hass, _entry(hass), api, protocol)

    assert _ovms_records(caplog) == []


async def test_protocol_login_logs_nothing_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Connecting and logging in to the Protocol v2 server stays out of the log."""
    caplog.set_level(logging.INFO)

    await _connect(_digest(SERVER_TOKEN))

    assert _ovms_records(caplog) == []
