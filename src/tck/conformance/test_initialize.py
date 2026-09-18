"""`initialize` handshake conformance: ACP-INIT-001..004, ACP-SCHEMA-001."""

from __future__ import annotations

from typing import Any

import pytest

from tck.harness import Direction
from tck.protocol import PROTOCOL_VERSION
from tck.validation import validate_agent_message, validate_agent_response

from ._helpers import connected_agent, new_session, run_prompt


@pytest.mark.requirement("ACP-INIT-001")
async def test_initialize_succeeds_and_validates(agent_launch):
    """ACP-INIT-001."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, f"initialize did not succeed: {msg!r}"

        issues = validate_agent_response("initialize", msg)
        assert not issues, f"initialize result failed schema validation: {issues!r}"

        version = msg["result"].get("protocolVersion")
        assert isinstance(version, int) and not isinstance(version, bool), (
            f"protocolVersion must be an integer, got {version!r}"
        )


@pytest.mark.requirement("ACP-INIT-002")
async def test_requested_v1_is_echoed(agent_launch):
    """ACP-INIT-002."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        version = msg["result"].get("protocolVersion")
        # Req 5: the agent echoes the requested version *only if it supports it*, otherwise it
        # returns its own latest -- for a v1-only TCK requesting v1, "not 1" means the agent
        # does not support protocol v1, not that it violated an echo rule (review N13).
        assert version == 1, f"agent does not support protocol v1 (returned {version!r} instead)"


@pytest.mark.requirement("ACP-INIT-003")
async def test_unsupported_version_still_succeeds(agent_launch):
    """ACP-INIT-003."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": 65535, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert "result" in msg, f"an unsupported version must still yield a successful result, got {msg!r}"
        version = msg["result"].get("protocolVersion")
        assert isinstance(version, int) and not isinstance(version, bool), (
            f"protocolVersion must be an integer, got {version!r}"
        )


@pytest.mark.requirement("ACP-INIT-004")
async def test_agent_info_present(agent_launch):
    """ACP-INIT-004 (ADVISORY)."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        agent_info = msg["result"].get("agentInfo")
        assert isinstance(agent_info, dict), "agentInfo is not present in the initialize result"
        assert isinstance(agent_info.get("name"), str), f"agentInfo.name is not a string: {agent_info!r}"
        assert isinstance(agent_info.get("version"), str), f"agentInfo.version is not a string: {agent_info!r}"


@pytest.mark.requirement("ACP-SCHEMA-001")
async def test_full_exchange_validates_against_schema(agent_launch, tmp_path):
    """ACP-SCHEMA-001. Every message the agent emits during initialize -> session/new ->
    session/prompt validates against the vendored v1 schema.

    Driven through `run_prompt` (review S4): a real agent that asks for permission or calls
    `fs/*`/`terminal/*` mid-turn must not deadlock this MANDATORY requirement just because
    nothing here answers it. `method_by_id` -- needed to know which method's response schema
    each reply must validate against -- is derived automatically by scanning the SENT
    transcript for `{"method", "id"}` pairs rather than threading it through the helpers by
    hand, so this test stays agnostic to how `run_prompt`/`new_session` are implemented.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello"}],
            timeout=agent_launch.default_timeout,
        )

    method_by_id: dict[Any, str] = {}
    for entry in agent.transcript:
        msg = entry.parsed
        if entry.direction is Direction.SENT and isinstance(msg, dict) and "method" in msg and "id" in msg:
            method_by_id[msg["id"]] = msg["method"]

    received = [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]

    issues = []
    for entry in received:
        msg = entry.parsed
        assert isinstance(msg, dict), f"non-object line from the agent: {entry.raw!r}"
        if "method" in msg:
            issues.extend(validate_agent_message(msg))
            continue
        method = method_by_id.get(msg.get("id"))
        if method is not None:
            issues.extend(validate_agent_response(method, msg))
        else:
            issues.extend(validate_agent_message(msg))

    assert not issues, f"schema violations in agent output: {issues!r}"
