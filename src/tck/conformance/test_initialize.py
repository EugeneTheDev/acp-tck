"""`initialize` handshake conformance: ACP-INIT-001..004, ACP-SCHEMA-001."""

from __future__ import annotations

from typing import Any

import pytest

from tck.harness import Direction
from tck.protocol import PROTOCOL_VERSION
from tck.validation import validate_agent_message, validate_agent_response

from ._helpers import connected_agent


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
        version = entry.parsed["result"]["protocolVersion"]
        assert version == 1, f"agent supports v1 but did not echo 1, returned {version!r}"


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
        agent_info = entry.parsed["result"].get("agentInfo")
        assert isinstance(agent_info, dict), "agentInfo is not present in the initialize result"
        assert isinstance(agent_info.get("name"), str), f"agentInfo.name is not a string: {agent_info!r}"
        assert isinstance(agent_info.get("version"), str), f"agentInfo.version is not a string: {agent_info!r}"


@pytest.mark.requirement("ACP-SCHEMA-001")
async def test_full_exchange_validates_against_schema(agent_launch, tmp_path):
    """ACP-SCHEMA-001. Every message the agent emits during initialize -> session/new ->
    session/prompt validates against the vendored v1 schema."""
    method_by_id: dict[Any, str] = {}
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        method_by_id[init_id] = "initialize"
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        session_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        method_by_id[session_req] = "session/new"
        session_entry = await agent.wait_for_response(session_req, timeout=agent_launch.default_timeout)
        session_id = session_entry.parsed["result"]["sessionId"]

        prompt_req = await agent.send_request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "hello"}]},
        )
        method_by_id[prompt_req] = "session/prompt"
        await agent.wait_for_response(prompt_req, timeout=agent_launch.default_timeout)

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
