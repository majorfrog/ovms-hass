"""Tests that login secrets never reach the log."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ovms_hass import coordinator as coordinator_module
from custom_components.ovms_hass.api import OVMSApiClient
from custom_components.ovms_hass.coordinator import OVMSProtocolClient

PASSWORD = "module-pw"
SERVER_TOKEN = "ServerTokenABCDEFGHIJK"


def _digest(token: str) -> str:
    return base64.b64encode(
        hmac.new(PASSWORD.encode(), token.encode(), hashlib.md5).digest()
    ).decode()


async def _connect(server_digest: str) -> tuple[str, str]:
    """Run a Protocol v2 login against a fake server; return the client's token and digest."""
    client = OVMSProtocolClient("h", "u", PASSWORD, "APA123", use_tls=False)
    reader = MagicMock()
    reader.readline = AsyncMock(
        return_value=f"MP-S 0 {SERVER_TOKEN} {server_digest}\r\n".encode()
    )
    writer = MagicMock()
    writer.drain = AsyncMock()

    with patch.object(
        coordinator_module.asyncio,
        "open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        await client.connect()

    _mp, _zero, token, digest, _vid = writer.write.call_args.args[0].decode().split()
    return token, digest


@pytest.mark.parametrize(
    "server_digest", [_digest(SERVER_TOKEN), "WrongDigest"], ids=["ok", "mismatch"]
)
async def test_protocol_login_logs_no_tokens_or_digests(
    caplog: pytest.LogCaptureFixture, server_digest: str
) -> None:
    """Token plus digest allow an offline guess of the vehicle password."""
    caplog.set_level(logging.DEBUG)

    token, digest = await _connect(server_digest)

    for secret in (token, digest, SERVER_TOKEN, server_digest, _digest(SERVER_TOKEN)):
        assert secret not in caplog.text


async def test_client_token_comes_from_secrets() -> None:
    """The client token must come from a cryptographic random source."""
    with patch.object(coordinator_module.secrets, "choice", return_value="Q"):
        token, _digest_ = await _connect(_digest(SERVER_TOKEN))

    assert token == "Q" * 22


async def test_rest_login_logs_no_session_id(caplog: pytest.LogCaptureFixture) -> None:
    """The session cookie is a live credential."""
    caplog.set_level(logging.DEBUG)
    session_id = "SessionSecret0123456789abcdef"
    client = OVMSApiClient("ovms.example", "user", "pw")
    response = MagicMock(status=200, headers={})
    response.text = AsyncMock(return_value="{}")
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock()
    client.session.request.return_value = context
    client.session.cookie_jar.filter_cookies.return_value = {
        "ovmsapisession": MagicMock(value=session_id)
    }

    await client.login()
    await client._request("GET", "/api/vehicles")

    assert session_id[:8] not in caplog.text
