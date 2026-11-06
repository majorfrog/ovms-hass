"""Tests for the diagnostics download."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovms_hass.coordinator import OVMSDataCoordinator
from custom_components.ovms_hass.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redact_credentials(hass: HomeAssistant) -> None:
    """No password from the entry may appear in the diagnostics."""
    entry = MockConfigEntry(
        domain="ovms_hass",
        data={
            "host": "api.openvehicles.com",
            "port": 6869,
            "username": "user-secret",
            "password": "server-secret",
            "vehicle_password": "module-secret",
            "vehicle_id": "APA123",
        },
    )
    entry.runtime_data = {
        "coordinator": OVMSDataCoordinator(hass, MagicMock(), "APA123")
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    text = repr(diagnostics)
    for secret in ("user-secret", "server-secret", "module-secret"):
        assert secret not in text
    assert diagnostics["config_entry"]["data"]["vehicle_password"] == "**REDACTED**"
