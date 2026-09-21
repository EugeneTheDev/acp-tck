"""`session/new` conformance: ACP-SESSION-001/002 (see `tck.v2.requirements`'s module docstring
for the id-namespacing decision -- reused from v1, but `Tier.CAPABILITY` here, gated on
`capabilities.session`, since v2's session surface is opt-in).
"""

from __future__ import annotations

from tck.v2.validation import validate_agent_response

import pytest

from ._helpers import connected_agent, new_session


@pytest.mark.requirement("ACP-SESSION-001")
@pytest.mark.capability("capabilities.session")
async def test_session_new_returns_unique_string_id(agent_launch, tmp_path):
    """ACP-SESSION-001. `session/new` with an absolute `cwd` and no `mcpServers` succeeds with a
    non-empty string `sessionId`, and the response validates against the v2 schema.
    """
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("session/new", {"cwd": str(tmp_path)})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/new did not return a result object: {entry.text!r}"
        )
        session_id = msg["result"].get("sessionId")
        assert isinstance(session_id, str) and session_id, (
            f"sessionId must be a non-empty string, got {session_id!r}"
        )
        issues = validate_agent_response("session/new", msg)
        assert not issues, f"session/new result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-SESSION-002")
@pytest.mark.capability("capabilities.session")
async def test_session_new_ids_are_unique(agent_launch, tmp_path):
    """ACP-SESSION-002. Two `session/new` calls on one connection return distinct `sessionId`s."""
    async with connected_agent(agent_launch) as agent:
        first_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        second_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert first_id != second_id, (
            f"two session/new calls returned the same sessionId: {first_id!r}"
        )
