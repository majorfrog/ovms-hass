"""Tests for config entry setup failures and REST client cleanup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovms_hass.api import (
    OVMSApiClient,
    OVMSAuthenticationError,
    OVMSConnectionError,
)
from custom_components.ovms_hass.coordinator import OVMSProtocolClient

ENTRY_DATA = {
    "host": "ovms.example",
    "port": 6869,
    "username": "user",
    "password": "pw",
    "vehicle_id": "APA123",
}


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="ovms_hass", data=ENTRY_DATA)
    entry.add_to_hass(hass)
    return entry


def _api_client(connect: AsyncMock | None = None) -> MagicMock:
    api = MagicMock(spec=OVMSApiClient)
    api.connect = connect or AsyncMock()
    api.disconnect = AsyncMock()
    return api


def _protocol_client() -> MagicMock:
    client = MagicMock(spec=OVMSProtocolClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


async def _setup(hass: HomeAssistant, entry, api, protocol) -> None:
    with (
        patch("custom_components.ovms_hass.OVMSApiClient", return_value=api),
        patch("custom_components.ovms_hass.OVMSProtocolClient", return_value=protocol),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_unreachable_server_retries_setup(hass: HomeAssistant) -> None:
    """A server that can't be reached at startup must be retried by HA."""
    entry = _entry(hass)
    api = _api_client(AsyncMock(side_effect=OVMSConnectionError("down")))

    await _setup(hass, entry, api, _protocol_client())

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_bad_credentials_fail_setup(hass: HomeAssistant) -> None:
    """Bad credentials are a permanent error, not a retry."""
    entry = _entry(hass)
    api = _api_client(AsyncMock(side_effect=OVMSAuthenticationError("401")))

    await _setup(hass, entry, api, _protocol_client())

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_failed_first_refresh_closes_clients(hass: HomeAssistant) -> None:
    """A setup that fails after connecting must not leave connections behind."""
    entry = _entry(hass)
    api = _api_client()
    protocol = _protocol_client()

    with patch(
        "custom_components.ovms_hass.coordinator.OVMSDataCoordinator._async_update_data",
        AsyncMock(side_effect=UpdateFailed("REST down")),
    ):
        await _setup(hass, entry, api, protocol)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    protocol.disconnect.assert_awaited_once_with()
    api.disconnect.assert_awaited_once()


def _response(status: int) -> MagicMock:
    response = MagicMock(status=status, headers={})
    response.text = AsyncMock(return_value="")
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.parametrize(
    "error", [aiohttp.ClientConnectionError("down"), TimeoutError()]
)
async def test_login_network_error_is_connection_error(error: Exception) -> None:
    """Network trouble during login must not look like bad credentials."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    client.session = MagicMock()
    client.session.request.side_effect = error

    with pytest.raises(OVMSConnectionError):
        await client.login()


async def test_login_server_error_is_connection_error() -> None:
    """A 5xx from the server is an outage, not bad credentials."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    client.session = MagicMock()
    client.session.request.return_value = _response(503)

    with pytest.raises(OVMSConnectionError):
        await client.login()


async def test_login_401_is_authentication_error() -> None:
    """Wrong username or password is an authentication error."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    client.session = MagicMock()
    client.session.request.return_value = _response(401)

    with pytest.raises(OVMSAuthenticationError):
        await client.login()


async def test_connect_closes_session_when_login_fails() -> None:
    """A failed login must not leak the aiohttp session."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    session = MagicMock()
    session.close = AsyncMock()

    with (
        patch("custom_components.ovms_hass.api.aiohttp.TCPConnector"),
        patch(
            "custom_components.ovms_hass.api.aiohttp.ClientSession",
            return_value=session,
        ),
        patch.object(
            client, "login", AsyncMock(side_effect=OVMSConnectionError("down"))
        ),
        pytest.raises(OVMSConnectionError),
    ):
        await client.connect()

    session.close.assert_awaited_once()
    assert client.session is None


async def test_disconnect_closes_session_when_logout_fails() -> None:
    """Logout errors must not stop the session from being closed."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    client.session = MagicMock()
    client.session.close = AsyncMock()
    client.session_id = "abc"
    session = client.session

    with patch.object(
        client, "_request", AsyncMock(side_effect=OVMSConnectionError("down"))
    ):
        await client.disconnect()

    session.close.assert_awaited_once()
    assert client.session is None


def _working_clients() -> tuple[MagicMock, MagicMock]:
    """API and protocol client mocks for a setup that succeeds."""
    from .test_poll import _api

    api = _api()
    api.connect = AsyncMock()
    api.disconnect = AsyncMock()
    protocol = _protocol_client()
    protocol.protocol_data = {}
    return api, protocol


async def test_services_registered_by_async_setup(hass: HomeAssistant) -> None:
    """Services exist once the integration is set up, entry or not."""
    assert await async_setup_component(hass, "ovms_hass", {})

    services = hass.services.async_services_for_domain("ovms_hass")
    assert "send_command" in services
    assert "set_feature" in services
    assert "get_feature" not in services
    assert "get_parameter" not in services


async def test_setup_removes_stale_gps_interval_entity(hass: HomeAssistant) -> None:
    """The removed GPS interval number must not linger as 'not provided'."""
    entry = _entry(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "number",
        "ovms_hass",
        "ovms_APA123_gps_streaming_interval",
        config_entry=entry,
    )

    await _setup(hass, entry, *_working_clients())

    assert entry.state is ConfigEntryState.LOADED
    assert (
        registry.async_get_entity_id(
            "number", "ovms_hass", "ovms_APA123_gps_streaming_interval"
        )
        is None
    )
