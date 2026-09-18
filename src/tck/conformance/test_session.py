"""Session lifecycle conformance: ACP-SESSION-001, ACP-SESSION-002 (Req 9)."""

from __future__ import annotations

import pytest

from tck.validation import validate_agent_response

from ._helpers import connected_agent


@pytest.mark.requirement("ACP-SESSION-001")
async def test_session_new_succeeds_with_a_unique_session_id(agent_launch, tmp_path):
    """ACP-SESSION-001."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, f"session/new did not succeed: {msg!r}"

        issues = validate_agent_response("session/new", msg)
        assert not issues, f"session/new result failed schema validation: {issues!r}"

        session_id = msg["result"].get("sessionId")
        assert isinstance(session_id, str) and session_id, (
            f"sessionId must be a non-empty string, got {session_id!r}"
        )


@pytest.mark.requirement("ACP-SESSION-002")
async def test_two_sessions_get_distinct_ids(agent_launch, tmp_path):
    """ACP-SESSION-002."""
    async with connected_agent(agent_launch) as agent:
        first_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        first_entry = await agent.wait_for_response(first_req, timeout=agent_launch.default_timeout)
        first_msg = first_entry.parsed
        assert isinstance(first_msg, dict) and isinstance(first_msg.get("result"), dict), (
            f"first session/new did not return a result object: {first_entry.text!r}"
        )
        first_id = first_msg["result"].get("sessionId")

        second_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        second_entry = await agent.wait_for_response(second_req, timeout=agent_launch.default_timeout)
        second_msg = second_entry.parsed
        assert isinstance(second_msg, dict) and isinstance(second_msg.get("result"), dict), (
            f"second session/new did not return a result object: {second_entry.text!r}"
        )
        second_id = second_msg["result"].get("sessionId")

        assert first_id != second_id, f"two session/new calls returned the same sessionId: {first_id!r}"
