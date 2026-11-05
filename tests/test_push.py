"""Tests for pushing parsed Protocol v2 data to entities."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.ovms_hass import _async_connect_protocol
from custom_components.ovms_hass.coordinator import (
    OVMSDataCoordinator,
    OVMSProtocolClient,
)


def d_payload(doors5: str) -> str:
    """A D message payload with doors5 at index 17."""
    return ",".join([""] * 17 + [doors5])


async def _wired(hass: HomeAssistant) -> tuple[OVMSDataCoordinator, OVMSProtocolClient]:
    coordinator = OVMSDataCoordinator(hass, MagicMock(), "APA123")
    client = OVMSProtocolClient("h", "u", "p", "APA123")
    client.connect = MagicMock(side_effect=Exception("offline in tests"))
    client.start_reconnect = MagicMock()
    await _async_connect_protocol(coordinator, client)
    return coordinator, client


async def test_d_message_updates_hvac_entity_immediately(hass: HomeAssistant) -> None:
    """A D message with the HVAC bit set reaches listeners at once."""
    coordinator, client = await _wired(hass)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    client._parse_environment_message(d_payload("128"))

    assert coordinator.data["status"]["hvac"] is True
    listener.assert_called_once()


async def test_unchanged_protocol_data_does_not_notify(hass: HomeAssistant) -> None:
    """Repeating the same D message does not notify again."""
    coordinator, client = await _wired(hass)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    client._parse_environment_message(d_payload("128"))
    client._parse_environment_message(d_payload("128"))

    listener.assert_called_once()


async def test_push_does_not_reschedule_poll(hass: HomeAssistant) -> None:
    """Pushed data must not move the next REST poll."""
    coordinator, client = await _wired(hass)
    coordinator.async_add_listener(MagicMock())
    scheduled = coordinator._unsub_refresh
    assert scheduled is not None

    client._parse_environment_message(d_payload("128"))

    assert coordinator._unsub_refresh is scheduled


async def test_hvac_off_is_pushed(hass: HomeAssistant) -> None:
    """HVAC turning off is pushed too."""
    coordinator, client = await _wired(hass)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    client._parse_environment_message(d_payload("128"))
    client._parse_environment_message(d_payload("0"))

    assert coordinator.data["status"]["hvac"] is False
    assert listener.call_count == 2


async def test_callback_error_does_not_propagate(hass: HomeAssistant) -> None:
    """A failing callback must not break the reader loop."""
    client = OVMSProtocolClient("h", "u", "p", "APA123")
    client.on_protocol_data = MagicMock(side_effect=RuntimeError("boom"))

    client.update_protocol_data({"hvac": True})

    assert client.protocol_data["hvac"] is True
