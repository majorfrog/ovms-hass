"""Tests for command error handling in the coordinator, entities and services."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovms_hass import _async_connect_protocol
from custom_components.ovms_hass.api import (
    OVMSCommandNotSent,
    OVMSConnectionError,
    OVMSConnectionLost,
)
from custom_components.ovms_hass.coordinator import (
    OVMSCommandError,
    OVMSDataCoordinator,
    OVMSProtocolClient,
)
from custom_components.ovms_hass.entities import ACOnButton
from custom_components.ovms_hass.services import async_setup_services

ACK = {"code": 26, "result": 0, "message": ""}


@pytest.fixture
def coordinator(hass: HomeAssistant) -> OVMSDataCoordinator:
    """Coordinator with a mocked, connected protocol client."""
    coord = OVMSDataCoordinator(hass, MagicMock(), "APA123")
    client = MagicMock(spec=OVMSProtocolClient)
    client.connected = True
    client.authenticated = True
    client._auto_reconnect_enabled = True
    client.async_command = AsyncMock(return_value=ACK)
    client.disconnect = AsyncMock()
    coord.ovms_client = client
    coord.async_request_refresh = AsyncMock()
    return coord


async def test_ack_returns_response(coordinator: OVMSDataCoordinator) -> None:
    """An acknowledged command returns the reply."""
    assert await coordinator.async_send_command("26,1", "AC ON") == ACK


async def test_no_ack_raises_without_resend(coordinator: OVMSDataCoordinator) -> None:
    """A missing ack raises and does not send the command again."""
    coordinator.ovms_client.async_command.return_value = None

    with pytest.raises(OVMSCommandError, match="^APA123 did not acknowledge AC ON$"):
        await coordinator.async_send_command("26,1", "AC ON")
    assert coordinator.ovms_client.async_command.await_count == 1


async def test_no_ack_marks_connection_for_reconnect(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A missing ack drops the (probably half-open) connection."""
    coordinator.ovms_client.async_command.return_value = None

    with pytest.raises(OVMSCommandError):
        await coordinator.async_send_command("26,1", "AC ON")
    coordinator.ovms_client.disconnect.assert_awaited_once_with(intentional=False)


async def test_rejected_raises(coordinator: OVMSDataCoordinator) -> None:
    """A non-zero result raises with the reason."""
    coordinator.ovms_client.async_command.return_value = {
        "code": 26,
        "result": 2,
        "message": "",
    }

    with pytest.raises(OVMSCommandError, match=r"rejected AC ON \(not supported\)"):
        await coordinator.async_send_command("26,1", "AC ON")


async def test_send_failure_retries_once_then_raises(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A send that wrote nothing is retried once."""
    coordinator.ovms_client.async_command.side_effect = OVMSCommandNotSent("down")

    with pytest.raises(OVMSCommandError, match="^APA123: AC ON could not be sent$"):
        await coordinator.async_send_command("26,1", "AC ON")
    assert coordinator.ovms_client.async_command.await_count == 2


async def test_connection_lost_after_send_raises_without_resend(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A connection lost after writing is not retried."""
    coordinator.ovms_client.async_command.side_effect = OVMSConnectionLost("reset")

    with pytest.raises(
        OVMSCommandError, match="connection lost after sending AC ON"
    ):
        await coordinator.async_send_command("26,1", "AC ON")
    assert coordinator.ovms_client.async_command.await_count == 1


async def test_no_client_raises(coordinator: OVMSDataCoordinator) -> None:
    """No protocol client means the command is not sent."""
    coordinator.ovms_client = None

    with pytest.raises(OVMSCommandError, match="no connection to the OVMS server"):
        await coordinator.async_send_command("26,1", "AC ON")


async def test_no_reconnect_after_unload(coordinator: OVMSDataCoordinator) -> None:
    """After unload the coordinator must not open a new connection."""
    client = coordinator.ovms_client
    client.connected = False
    client._auto_reconnect_enabled = False
    client.connect = AsyncMock()

    assert await coordinator._ensure_protocol_connection() is False
    client.connect.assert_not_called()


async def test_ac_on_button_raises(coordinator: OVMSDataCoordinator) -> None:
    """The AC ON button surfaces a missing ack as an error."""
    coordinator.ovms_client.async_command.return_value = None

    with pytest.raises(HomeAssistantError, match="did not acknowledge AC ON"):
        await ACOnButton(coordinator, "APA123").async_press()


async def _setup_entry(hass: HomeAssistant, coordinator: OVMSDataCoordinator) -> None:
    entry = MockConfigEntry(domain="ovms_hass", state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    entry.runtime_data = {"coordinator": coordinator}
    await async_setup_services(hass)


async def test_service_finds_coordinator_and_raises(
    hass: HomeAssistant, coordinator: OVMSDataCoordinator
) -> None:
    """The service handler runs, finds the vehicle and raises on no ack."""
    await _setup_entry(hass, coordinator)
    coordinator.ovms_client.async_command.return_value = None

    with pytest.raises(HomeAssistantError, match="did not acknowledge"):
        await hass.services.async_call(
            "ovms_hass",
            "send_command",
            {"vehicle_id": "APA123", "command": "metrics get v.e.hvac"},
            blocking=True,
        )
    coordinator.ovms_client.async_command.assert_awaited_once()
    assert coordinator.ovms_client.async_command.await_args.args[0] == (
        "7,metrics get v.e.hvac"
    )


async def test_service_unknown_vehicle_raises_validation_error(
    hass: HomeAssistant, coordinator: OVMSDataCoordinator
) -> None:
    """An unknown vehicle id is a validation error."""
    await _setup_entry(hass, coordinator)

    with pytest.raises(ServiceValidationError, match="Unknown OVMS vehicle NOPE"):
        await hass.services.async_call(
            "ovms_hass",
            "send_command",
            {"vehicle_id": "NOPE", "command": "metrics get v.e.hvac"},
            blocking=True,
        )


async def test_failed_first_connect_keeps_client_and_reconnects(
    hass: HomeAssistant,
) -> None:
    """A failed first connect still attaches the client and starts reconnecting."""
    coord = OVMSDataCoordinator(hass, MagicMock(), "APA123")
    client = OVMSProtocolClient("h", "u", "p", "APA123")

    with (
        patch.object(
            client, "connect", AsyncMock(side_effect=OVMSConnectionError("down"))
        ),
        patch.object(client, "start_reconnect") as start_reconnect,
    ):
        await _async_connect_protocol(coord, client)

    assert coord.ovms_client is client
    start_reconnect.assert_called_once()


async def test_no_ack_starts_background_reconnect(
    coordinator: OVMSDataCoordinator,
) -> None:
    """After dropping a dead connection, pushed data must come back by itself."""
    coordinator.ovms_client.async_command.return_value = None

    with pytest.raises(OVMSCommandError):
        await coordinator.async_send_command("26,1", "AC ON")
    coordinator.ovms_client.start_reconnect.assert_called_once()


async def test_failed_reconnect_starts_background_reconnect(
    coordinator: OVMSDataCoordinator,
) -> None:
    """A failed on-demand reconnect hands over to the background loop."""
    client = coordinator.ovms_client
    client.connected = False
    client._reconnect_lock = asyncio.Lock()
    client.connect = AsyncMock(side_effect=OVMSConnectionError("down"))

    assert await coordinator._ensure_protocol_connection() is False
    client.start_reconnect.assert_called_once()
