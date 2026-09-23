"""Advisory/informational diagnostics: ACP-ERROR-001, ACP-SHUTDOWN-001, ACP-STDERR-001."""

from __future__ import annotations

import json

import pytest

from tck.v1.protocol import PROTOCOL_VERSION

from ._helpers import connected_agent, skip_if_auth_gated


@pytest.mark.requirement("ACP-ERROR-001")
async def test_error_messages_are_non_empty_single_line(agent_launch):
    """ACP-ERROR-001 (ADVISORY -- `Error.message` is documented as a "short description" but
    "non-empty"/"no embedded newline" is never pinned down as a MUST, so this flags rather than
    fails). Reuses the error replies already required by ACP-JSONRPC-002 (unrecognised method,
    `session/new` missing `cwd`) instead of inventing a third exchange."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        unknown_id = await agent.send_request("_tck/does_not_exist")
        unknown_entry = await agent.wait_for_response(unknown_id, timeout=agent_launch.default_timeout)

        bad_id = await agent.send_request("session/new", {"mcpServers": []})  # missing required cwd
        bad_entry = await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)

    for what, entry in (("_tck/does_not_exist", unknown_entry), ("session/new (missing cwd)", bad_entry)):
        msg = entry.parsed
        error = msg.get("error") if isinstance(msg, dict) else None
        if not isinstance(error, dict):
            continue  # no error to inspect; ACP-JSONRPC-002/004 own whether that's acceptable
        message = error.get("message")
        if not isinstance(message, str):
            continue  # envelope shape is ACP-JSONRPC-002's concern, not this test's
        assert message != "", f"{what}: error.message must not be empty"
        assert "\n" not in message, f"{what}: error.message must not contain a newline: {message!r}"
        data = error.get("data")
        if data is not None:
            # only confirms it's JSON-shaped; structure isn't asserted
            json.dumps(data)


@pytest.mark.requirement("ACP-SHUTDOWN-001")
async def test_agent_exits_promptly_after_stdin_close(agent_launch, tmp_path):
    """ACP-SHUTDOWN-001 (ADVISORY -- the spec is silent on shutdown timing, but a well-behaved
    agent should exit on stdin EOF without needing SIGTERM/SIGKILL). Relies on
    `connected_agent`'s close() ladder and `AgentProcess.exited_on_stdin_close` to report whether
    it exited on the first rung."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        skip_if_auth_gated(entry)

    assert agent.exited_on_stdin_close, (
        "agent did not exit within the grace period after stdin closed; it needed SIGTERM/"
        "SIGKILL to terminate (advisory -- the spec does not mandate shutdown timing, but a "
        "prompt exit on stdin EOF is expected of a well-behaved agent)"
    )


@pytest.mark.requirement("ACP-STDERR-001")
async def test_stderr_byte_count_is_recorded(agent_launch, tmp_path, record_property):
    """ACP-STDERR-001 (INFORMATIONAL -- the spec has nothing to say about stderr at all; this
    exists purely to surface how chatty an agent is on stderr during an ordinary exchange, for a
    human reading the report, never to fail a run). Always PASSes."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        skip_if_auth_gated(entry)

    stderr_bytes = len(agent.stderr_text().encode("utf-8"))
    record_property("acp_tck_stderr_bytes", stderr_bytes)
