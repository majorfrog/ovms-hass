"""Tests for the reauth flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ovms_hass.api import (
    OVMSApiClient,
    VehicleInfo,
    OVMSAuthenticationError,
    OVMSConnectionError,
)
from custom_components.ovms_hass.coordinator import OVMSDataCoordinator

from .test_poll import _api
from .test_setup import (
    _api_client,
    _entry,
    _protocol_client,
    _setup,
    _working_clients,
)


def _flow_api(
    connect_error: Exception | None = None, vehicles: tuple[str, ...] = ("APA123",)
) -> MagicMock:
    api = MagicMock(spec=OVMSApiClient)
    api.connect = AsyncMock(side_effect=connect_error)
    api.disconnect = AsyncMock()
    api.list_vehicles = AsyncMock(
        return_value=[VehicleInfo(vid, 0, 0, 0) for vid in vehicles]
    )
    return api


async def test_bad_credentials_start_reauth(hass: HomeAssistant) -> None:
    """Bad credentials at startup ask the user for a new password."""
    entry = _entry(hass)
    api = _api_client(AsyncMock(side_effect=OVMSAuthenticationError("401")))

    await _setup(hass, entry, api, _protocol_client())

    flows = hass.config_entries.flow.async_progress_by_handler("ovms_hass")
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_poll_with_rejected_credentials_raises_auth_failed(
    hass: HomeAssistant,
) -> None:
    """A password changed on the server while HA runs triggers reauth."""
    api = _api()
    for method in ("get_status", "get_charge", "get_location", "get_tpms", "get_vehicle"):
        getattr(api, method).side_effect = OVMSAuthenticationError("401")
    coord = OVMSDataCoordinator(hass, api, "APA123")

    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_poll_with_mixed_failures_is_update_failed(hass: HomeAssistant) -> None:
    """An outage that isn't about credentials stays a plain update failure."""
    api = _api()
    for method in ("get_status", "get_charge", "get_location", "get_tpms"):
        getattr(api, method).side_effect = OVMSConnectionError("down")
    api.get_vehicle.side_effect = OVMSAuthenticationError("401")
    coord = OVMSDataCoordinator(hass, api, "APA123")

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def _start_reauth(hass: HomeAssistant):
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    return entry, result


async def test_reauth_updates_passwords_and_reloads(hass: HomeAssistant) -> None:
    """A working new password is stored, and the vehicle password if given."""
    entry, result = await _start_reauth(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    api = _flow_api()
    with (
        patch("custom_components.ovms_hass.config_flow.OVMSApiClient", return_value=api) as cls,
        patch("custom_components.ovms_hass.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "new-pw", "vehicle_password": "new-module-pw"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-pw"
    assert entry.data["vehicle_password"] == "new-module-pw"
    assert entry.data["username"] == "user"
    assert cls.call_args.kwargs["password"] == "new-pw"
    assert cls.call_args.kwargs["host"] == "ovms.example"
    api.disconnect.assert_awaited_once()


async def test_reauth_keeps_vehicle_password_when_left_empty(
    hass: HomeAssistant,
) -> None:
    """Leaving the vehicle password empty keeps the stored one."""
    entry = _entry(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "vehicle_password": "old-module-pw"}
    )
    result = await entry.start_reauth_flow(hass)

    with (
        patch("custom_components.ovms_hass.config_flow.OVMSApiClient", return_value=_flow_api()),
        patch("custom_components.ovms_hass.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "new-pw"}
        )

    assert result["reason"] == "reauth_successful"
    assert entry.data["vehicle_password"] == "old-module-pw"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OVMSAuthenticationError("401"), "invalid_auth"),
        (OVMSConnectionError("down"), "cannot_connect"),
    ],
)
async def test_reauth_shows_error_and_keeps_entry(
    hass: HomeAssistant, error: Exception, expected: str
) -> None:
    """A failing login shows the error and changes nothing."""
    entry, result = await _start_reauth(hass)

    with patch(
        "custom_components.ovms_hass.config_flow.OVMSApiClient",
        return_value=_flow_api(error),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert entry.data["password"] == "pw"


def _suggested(result) -> dict:
    """Suggested (prefilled) values of a form's fields."""
    return {
        str(key): (key.description or {}).get("suggested_value")
        for key in result["data_schema"].schema
    }


async def _start_reconfigure(hass: HomeAssistant):
    entry = _entry(hass)
    hass.config_entries.async_update_entry(
        entry, unique_id="APA123", data={**entry.data, "vehicle_password": "module"}
    )
    result = await entry.start_reconfigure_flow(hass)
    return entry, result


async def test_reconfigure_form_prefills_connection(hass: HomeAssistant) -> None:
    """Host, port and username are prefilled; passwords never are."""
    _entry_, result = await _start_reconfigure(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    suggested = _suggested(result)
    assert suggested["host"] == "ovms.example"
    assert suggested["port"] == 6869
    assert suggested["username"] == "user"
    assert suggested["password"] is None
    assert suggested["vehicle_password"] is None
    assert result["description_placeholders"]["vehicle_id"] == "APA123"


async def test_reconfigure_updates_connection_and_reloads(hass: HomeAssistant) -> None:
    """Working new settings are stored; the vehicle stays the same."""
    entry, result = await _start_reconfigure(hass)

    api = _flow_api()
    with (
        patch("custom_components.ovms_hass.config_flow.OVMSApiClient", return_value=api) as cls,
        patch("custom_components.ovms_hass.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "ovms2.example",
                "port": 6870,
                "username": "user2",
                "password": "pw2",
                "vehicle_password": "module2",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "ovms2.example"
    assert entry.data["port"] == 6870
    assert entry.data["username"] == "user2"
    assert entry.data["password"] == "pw2"
    assert entry.data["vehicle_password"] == "module2"
    assert entry.data["vehicle_id"] == "APA123"
    assert entry.unique_id == "APA123"
    assert cls.call_args.kwargs == {
        "host": "ovms2.example",
        "port": 6870,
        "username": "user2",
        "password": "pw2",
        "use_https": True,
    }


async def test_reconfigure_keeps_vehicle_password_when_left_empty(
    hass: HomeAssistant,
) -> None:
    """Leaving the vehicle password empty keeps the stored one."""
    entry, result = await _start_reconfigure(hass)

    with (
        patch("custom_components.ovms_hass.config_flow.OVMSApiClient", return_value=_flow_api()),
        patch("custom_components.ovms_hass.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "ovms.example", "port": 6869, "username": "user", "password": "pw2"},
        )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data["vehicle_password"] == "module"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OVMSAuthenticationError("401"), "invalid_auth"),
        (OVMSConnectionError("down"), "cannot_connect"),
    ],
)
async def test_reconfigure_shows_error_and_keeps_entry(
    hass: HomeAssistant, error: Exception, expected: str
) -> None:
    """Settings that don't log in are never stored."""
    entry, result = await _start_reconfigure(hass)
    before = dict(entry.data)

    with patch(
        "custom_components.ovms_hass.config_flow.OVMSApiClient",
        return_value=_flow_api(error),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "bad.example", "port": 6869, "username": "user", "password": "x"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert dict(entry.data) == before


async def test_reconfigure_rejects_account_without_the_vehicle(
    hass: HomeAssistant,
) -> None:
    """Another account that logs in but lacks this vehicle is not saved."""
    entry, result = await _start_reconfigure(hass)
    before = dict(entry.data)
    api = _flow_api(vehicles=("OTHER1",))

    with patch("custom_components.ovms_hass.config_flow.OVMSApiClient", return_value=api):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "ovms.example", "port": 6869, "username": "other", "password": "x"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "vehicle_not_found"}
    assert dict(entry.data) == before
    api.disconnect.assert_awaited_once()


async def test_entry_has_no_update_listener(hass: HomeAssistant) -> None:
    """HA 2026.12 breaks reauth/reconfigure for entries with update listeners."""
    entry = _entry(hass)

    await _setup(hass, entry, *_working_clients())

    assert entry.state is ConfigEntryState.LOADED
    assert entry.update_listeners == []


async def test_options_change_reloads_with_new_interval(hass: HomeAssistant) -> None:
    """Changing the update interval in Options reloads the entry with it."""
    entry = _entry(hass)
    api, protocol = _working_clients()
    with (
        patch("custom_components.ovms_hass.OVMSApiClient", return_value=api),
        patch("custom_components.ovms_hass.OVMSProtocolClient", return_value=protocol),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 120}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data["coordinator"]
    assert coordinator.update_interval.total_seconds() == 120


async def test_reconfigure_unexpected_error_shows_unknown(hass: HomeAssistant) -> None:
    """An unexpected error during the login check shows "unknown"."""
    entry, result = await _start_reconfigure(hass)
    before = dict(entry.data)

    with patch(
        "custom_components.ovms_hass.config_flow.OVMSApiClient",
        return_value=_flow_api(RuntimeError("boom")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "ovms.example", "port": 6869, "username": "user", "password": "x"},
        )

    assert result["errors"] == {"base": "unknown"}
    assert dict(entry.data) == before


async def test_reconfigure_entry_without_vehicle_id_names_entry(
    hass: HomeAssistant,
) -> None:
    """Old entries made without a vehicle ID show the entry title instead."""
    entry = MockConfigEntry(
        domain="ovms_hass",
        title="OVMS (ovms.example)",
        unique_id="ovms.example:user",
        data={"host": "ovms.example", "port": 6869, "username": "user", "password": "pw"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert result["description_placeholders"]["vehicle_id"] == "OVMS (ovms.example)"
