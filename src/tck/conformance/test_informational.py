"""INFORMATIONAL-tier probes: ACP-INFO-PARSE-001, ACP-INFO-INVALIDREQ-001,
ACP-INFO-UNKNOWNSESSION-001.

The spec is silent on all three behaviours and real SDKs disagree in practice (`.agents/plan.md`
"Open questions"), so none of these ever fail -- they exist purely to record what the agent
under test actually does, via `record_property`, for a human reading the report. Each uses its
own throwaway `connected_agent` so a bad reaction (if any) cannot contaminate a later test's
connection.
"""

from __future__ import annotations

import pytest

from tck.harness import AgentExited, AgentTimeout
from tck.protocol import PROTOCOL_VERSION

from ._helpers import connected_agent, new_session, skip_if_auth_gated


async def _probe_connection_usable_after(agent, tmp_path, timeout: float) -> str:
    """Send an ordinary `session/new` and report whether it still gets a normal response."""
    try:
        session_id = await new_session(agent, tmp_path, timeout=timeout)
    except AssertionError:
        return "unusable (session/new did not return a well-formed result)"
    except (AgentTimeout, AgentExited):
        return "unusable (no response / agent exited)"
    else:
        return f"usable (sessionId={session_id!r})"


@pytest.mark.requirement("ACP-INFO-PARSE-001")
async def test_malformed_json_line_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-PARSE-001 (INFORMATIONAL). Sends one line of malformed JSON (not valid JSON at
    all) and records whether the agent: replies with a `-32700`/`id: null` error (J1's
    documented-but-not-universal behaviour), replies with something else, or stays silent.
    Then, using a fresh, ordinary `session/new` on the *same* connection, records whether the
    connection is still usable afterwards. Never asserts."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        await agent.send_raw(b"{not valid json at all")

        try:
            entry = await agent.read_line(timeout=agent_launch.default_timeout)
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            if (
                isinstance(msg, dict)
                and isinstance(msg.get("error"), dict)
                and msg["error"].get("code") == -32700
                and msg.get("id") is None
            ):
                behaviour = "replied -32700 with id:null"
            else:
                behaviour = f"replied: {entry.text!r}"

        connection_usable_after = await _probe_connection_usable_after(
            agent, tmp_path, agent_launch.default_timeout
        )

    record_property("behaviour", behaviour)
    record_property("connection_usable_after", connection_usable_after)


@pytest.mark.requirement("ACP-INFO-INVALIDREQ-001")
async def test_structurally_invalid_request_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-INVALIDREQ-001 (INFORMATIONAL). Same as ACP-INFO-PARSE-001, but for a line that
    *is* valid JSON yet not a JSON-RPC request/notification/response at all (`{"foo": "bar"}`,
    no `jsonrpc`/`method`/`id`). Never asserts."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        await agent.send_raw(b'{"foo": "bar"}')

        try:
            entry = await agent.read_line(timeout=agent_launch.default_timeout)
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            if (
                isinstance(msg, dict)
                and isinstance(msg.get("error"), dict)
                and msg["error"].get("code") == -32600
            ):
                behaviour = "replied -32600 (invalid request)"
            else:
                behaviour = f"replied: {entry.text!r}"

        connection_usable_after = await _probe_connection_usable_after(
            agent, tmp_path, agent_launch.default_timeout
        )

    record_property("behaviour", behaviour)
    record_property("connection_usable_after", connection_usable_after)


@pytest.mark.requirement("ACP-INFO-UNKNOWNSESSION-001")
async def test_unknown_session_id_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-UNKNOWNSESSION-001 (INFORMATIONAL). `session/prompt` for a `sessionId` the agent
    never created. Records the error code, if any (spec is silent on what, if anything, an
    agent should reply with here). Never asserts."""
    async with connected_agent(agent_launch) as agent:
        new_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        new_entry = await agent.wait_for_response(new_id, timeout=agent_launch.default_timeout)
        skip_if_auth_gated(new_entry)

        prompt_id = await agent.send_request(
            "session/prompt",
            {"sessionId": "tck-does-not-exist", "prompt": [{"type": "text", "text": "hi"}]},
        )
        try:
            entry = await agent.wait_for_response(prompt_id, timeout=agent_launch.default_timeout)
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            error = msg.get("error") if isinstance(msg, dict) else None
            if isinstance(error, dict):
                behaviour = f"replied with error code {error.get('code')!r}"
            elif isinstance(msg, dict) and "result" in msg:
                behaviour = "replied with a result (no error)"
            else:
                behaviour = f"replied: {entry.text!r}"

    record_property("behaviour", behaviour)
