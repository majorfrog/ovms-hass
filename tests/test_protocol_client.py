"""Tests for the OVMS Protocol v2 command round-trip."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ovms_hass import coordinator as coordinator_module
from custom_components.ovms_hass.api import OVMSCommandNotSent, OVMSConnectionLost
from custom_components.ovms_hass.coordinator import RC4, OVMSProtocolClient


def _command_code(data: bytes) -> str:
    """Return the command code from a plain-text written message."""
    # "MP-0 C26,1\r\n" -> "26"
    return data.decode()[6:].split(",", 1)[0]


def make_client() -> tuple[OVMSProtocolClient, MagicMock]:
    """Return a connected client with a fake socket writer."""
    client = OVMSProtocolClient("h", "u", "p", "APA123")
    client.connected = True
    client.authenticated = True
    client._tx_cipher = RC4(b"k")
    # Skip encryption so tests can read what was written.
    client._encrypt_message = lambda message: message
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = MagicMock(return_value=False)
    client._writer = writer
    return client, writer


async def test_reply_before_wait_is_not_lost() -> None:
    """A reply handled while the command is still being written counts."""
    client, writer = make_client()
    writer.write.side_effect = lambda _data: client._handle_command_response("26,0,")

    result = await client.async_command("26,1", 1)

    assert result == {"code": 26, "result": 0, "message": ""}


async def test_reply_with_other_code_is_ignored() -> None:
    """A reply for another command code does not ack this command."""
    client, writer = make_client()
    loop = asyncio.get_running_loop()

    def reply(_data: bytes) -> None:
        client._handle_command_response("7,0,yes")
        loop.call_later(0.05, client._handle_command_response, "26,0,")

    writer.write.side_effect = reply

    result = await client.async_command("26,1", 1)

    assert result is not None
    assert result["code"] == 26


async def test_timeout_returns_none() -> None:
    """No reply within the timeout gives None."""
    client, _writer = make_client()

    assert await client.async_command("26,1", 0.1) is None


async def test_concurrent_commands_are_serialized() -> None:
    """Two concurrent commands each get their own reply, one after the other."""
    client, writer = make_client()
    loop = asyncio.get_running_loop()
    events: list[str] = []

    def reply(data: bytes) -> None:
        code = _command_code(data)
        events.append(f"write {code}")

        def answer() -> None:
            events.append(f"reply {code}")
            client._handle_command_response(f"{code},0,ok{code}")

        loop.call_later(0.05, answer)

    writer.write.side_effect = reply

    first, second = await asyncio.gather(
        client.async_command("26,1", 1),
        client.async_command("7,metrics get v.e.hvac", 1),
    )

    assert first == {"code": 26, "result": 0, "message": "ok26"}
    assert second == {"code": 7, "result": 0, "message": "ok7"}
    assert events == ["write 26", "reply 26", "write 7", "reply 7"]


async def test_not_connected_raises_not_sent() -> None:
    """Nothing is written when the client is not connected."""
    client, writer = make_client()
    client.connected = False

    with pytest.raises(OVMSCommandNotSent):
        await client.async_command("26,1", 1)
    writer.write.assert_not_called()


async def test_write_failure_raises_not_sent() -> None:
    """A failing write means nothing reached the server."""
    client, writer = make_client()
    writer.write.side_effect = OSError("broken pipe")

    with pytest.raises(OVMSCommandNotSent):
        await client.async_command("26,1", 1)


async def test_drain_failure_raises_connection_lost() -> None:
    """A failing drain may have delivered the bytes."""
    client, writer = make_client()
    writer.drain.side_effect = OSError("reset")

    with pytest.raises(OVMSConnectionLost):
        await client.async_command("26,1", 1)


async def test_drain_hang_raises_connection_lost() -> None:
    """A drain that never returns is bounded by SEND_TIMEOUT."""
    client, writer = make_client()

    async def hang() -> None:
        await asyncio.Event().wait()

    writer.drain.side_effect = hang

    with (
        patch.object(coordinator_module, "SEND_TIMEOUT", 0.1),
        pytest.raises(OVMSConnectionLost),
    ):
        await client.async_command("26,1", 5)


async def test_disconnect_during_wait_raises_connection_lost() -> None:
    """A disconnect while waiting fails at once instead of timing out."""
    client, _writer = make_client()
    loop = asyncio.get_running_loop()
    loop.call_later(
        0.05, lambda: loop.create_task(client.disconnect(intentional=False))
    )

    start = loop.time()
    with pytest.raises(OVMSConnectionLost):
        await client.async_command("26,1", 1)
    assert loop.time() - start < 0.5


async def test_timeout_marks_connection_down() -> None:
    """After a missing reply the next command must not reuse the socket."""
    client, _writer = make_client()

    assert await client.async_command("26,1", 0.05) is None
    assert client.connected is False


async def test_closing_writer_raises_not_sent() -> None:
    """A transport that is already closing drops writes: nothing was sent."""
    client, writer = make_client()
    writer.is_closing.return_value = True

    with pytest.raises(OVMSCommandNotSent):
        await client.async_command("26,1", 1)
    writer.write.assert_not_called()


async def test_ping_failure_starts_reconnect() -> None:
    """A failed ping starts the background reconnect."""
    client, writer = make_client()
    writer.drain.side_effect = OSError("reset")
    client.start_reconnect = MagicMock()

    with patch.object(coordinator_module, "PING_INTERVAL", 0):
        await asyncio.wait_for(client._ping_loop(), 1)

    assert client.connected is False
    client.start_reconnect.assert_called_once()


async def _hang(*_args, **_kwargs):
    await asyncio.Event().wait()


async def test_connect_times_out_when_server_unreachable() -> None:
    """A hanging TCP connect must fail fast, or commands queue for minutes."""
    client = OVMSProtocolClient("h", "u", "p", "APA123", use_tls=False)

    with (
        patch.object(coordinator_module, "CONNECT_TIMEOUT", 0.05),
        patch.object(coordinator_module.asyncio, "open_connection", _hang),
        pytest.raises(coordinator_module.OVMSConnectionError),
    ):
        async with asyncio.timeout(2):
            await client.connect()

    assert not client.connected


async def test_connect_times_out_when_login_reply_never_comes() -> None:
    """The whole connect, including the login reply, is under one timeout."""
    client = OVMSProtocolClient("h", "u", "p", "APA123", use_tls=False)
    reader = MagicMock()
    reader.readline = _hang
    writer = MagicMock()
    writer.drain = AsyncMock()

    with (
        patch.object(coordinator_module, "CONNECT_TIMEOUT", 0.05),
        patch.object(
            coordinator_module.asyncio,
            "open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
        pytest.raises(coordinator_module.OVMSConnectionError),
    ):
        async with asyncio.timeout(2):
            await client.connect()

    assert not client.connected
    writer.close.assert_called_once()


async def test_connect_refused_logs_no_traceback(caplog: pytest.LogCaptureFixture) -> None:
    """An unreachable server is expected, not a bug: no traceback."""
    client = OVMSProtocolClient("h", "u", "p", "APA123", use_tls=False)

    with (
        patch.object(
            coordinator_module.asyncio,
            "open_connection",
            AsyncMock(side_effect=ConnectionRefusedError("refused")),
        ),
        pytest.raises(coordinator_module.OVMSConnectionError, match="refused"),
    ):
        await client.connect()

    assert not [r for r in caplog.records if r.exc_info]


async def test_reconnect_outage_warns_once_and_logs_recovery(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated failures in one outage give one warning, then one recovery line."""
    client = OVMSProtocolClient("h", "u", "p", "APA123")
    down = coordinator_module.OVMSConnectionError("down")

    with (
        patch.object(coordinator_module, "RECONNECT_DELAY", 0),
        patch.object(client, "disconnect", AsyncMock()),
        patch.object(client, "connect", AsyncMock(side_effect=[down, down, down, None])),
        patch.object(client, "start_background_reader"),
    ):
        await client._reconnect_loop()

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "down" in warnings[0].getMessage()
    assert any(
        r.levelname == "INFO" and "restored" in r.getMessage() for r in caplog.records
    )
    assert not [r for r in caplog.records if r.exc_info]


async def _run_ping_loop_briefly(client: OVMSProtocolClient) -> None:
    task = asyncio.create_task(client._ping_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_silent_server_triggers_reconnect() -> None:
    """With nothing received for STALE_TIMEOUT, the connection is treated as dead."""
    client, writer = make_client()
    client._last_received = asyncio.get_running_loop().time() - 1000

    with (
        patch.object(coordinator_module, "PING_INTERVAL", 0.01),
        patch.object(client, "start_reconnect") as start_reconnect,
    ):
        await _run_ping_loop_briefly(client)

    start_reconnect.assert_called_once()
    assert not client.connected
    writer.write.assert_not_called()


async def test_recent_data_keeps_pinging() -> None:
    """A server that sent something recently gets a ping, not a reconnect."""
    client, writer = make_client()
    client._last_received = asyncio.get_running_loop().time()

    with (
        patch.object(coordinator_module, "PING_INTERVAL", 0.01),
        patch.object(client, "start_reconnect") as start_reconnect,
    ):
        await _run_ping_loop_briefly(client)

    start_reconnect.assert_not_called()
    assert client.connected
    assert writer.write.call_args.args[0].startswith(b"MP-0 A")


async def test_reader_records_time_of_last_message() -> None:
    """Every received line counts as a sign of life."""
    client, _writer = make_client()
    client._rx_cipher = RC4(b"k")
    client._decrypt_message = lambda message: "MP-0 a"
    client._reader = MagicMock()
    client._reader.readline = AsyncMock(side_effect=[b"x\r\n", b""])
    client._last_received = 0.0

    with patch.object(client, "start_reconnect"):
        await client._background_reader_loop()

    assert client._last_received > 0.0
