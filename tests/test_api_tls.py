"""Tests that the REST client verifies the server's TLS certificate."""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ovms_hass.api import OVMSApiClient


def _ok_response() -> MagicMock:
    response = MagicMock(status=200, headers={})
    response.text = AsyncMock(return_value="{}")
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


async def test_connect_uses_verifying_ssl_context() -> None:
    """The session's connector checks the certificate and the host name."""
    client = OVMSApiClient("ovms.example", "user", "pw")

    with (
        patch("custom_components.ovms_hass.api.aiohttp.TCPConnector") as connector,
        patch("custom_components.ovms_hass.api.aiohttp.ClientSession"),
        patch.object(client, "login", AsyncMock()),
    ):
        await client.connect()

    context = connector.call_args.kwargs["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert "verify_ssl" not in connector.call_args.kwargs


async def test_requests_do_not_disable_verification() -> None:
    """No request may switch verification off with ssl=False."""
    client = OVMSApiClient("ovms.example", "user", "pw")
    client.session = MagicMock()
    client.session.request.return_value = _ok_response()
    client.session.cookie_jar.filter_cookies.return_value = {
        "ovmsapisession": MagicMock(value="abc")
    }

    await client.login()
    await client._request("GET", "/api/vehicles")

    for call in client.session.request.call_args_list:
        assert call.kwargs.get("ssl", True) is not False
