"""Prompt-turn conformance: ACP-PROMPT-001..003 (Reqs 7, 24; Discrepancy 2)."""

from __future__ import annotations

import pytest

from tck.v1.protocol import STOP_REASONS
from tck.v1.validation import validate_agent_message

from ._helpers import connected_agent, new_session, run_prompt, skip_if_version_mismatch


@pytest.mark.requirement("ACP-PROMPT-001")
async def test_text_only_prompt_resolves_with_a_valid_stop_reason(agent_launch, agent_initialize_result, tmp_path):
    """ACP-PROMPT-001. Checks version mismatch first: a v1-shaped stopReason can't be judged
    against an agent that never negotiated v1."""
    if agent_initialize_result.result is not None:
        skip_if_version_mismatch(agent_initialize_result.result)
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello"}],
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and "result" in msg, f"session/prompt did not succeed: {msg!r}"
        stop_reason = msg["result"].get("stopReason")
        assert stop_reason in STOP_REASONS, f"invalid stopReason: {stop_reason!r}"


@pytest.mark.requirement("ACP-PROMPT-002")
async def test_updates_validate_and_carry_the_right_session_id(agent_launch, tmp_path):
    """ACP-PROMPT-002. An agent that emits zero `session/update` notifications is still
    conforming -- Req 1 only requires it be *able* to send them, not that it does. This test
    passes vacuously when `turn.updates` is empty; it only fails on a malformed or
    misattributed update.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello"}],
            timeout=agent_launch.default_timeout,
        )

        for _, entry in turn.updates:
            update_msg = entry.parsed
            assert isinstance(update_msg, dict), f"session/update line did not parse: {entry.raw!r}"
            issues = validate_agent_message(update_msg)
            assert not issues, f"session/update failed schema validation: {issues!r}"
            carried_session_id = (update_msg.get("params") or {}).get("sessionId")
            assert carried_session_id == session_id, (
                f"session/update carried sessionId {carried_session_id!r}, expected {session_id!r}"
            )


@pytest.mark.requirement("ACP-PROMPT-003")
async def test_resource_link_content_block_is_accepted(agent_launch, tmp_path):
    """ACP-PROMPT-003 (ADVISORY -- see `tck.v1.requirements` for the content.mdx/initialization.mdx
    discrepancy this defers to upstream)."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [
                {"type": "text", "text": "have a look at this"},
                {"type": "resource_link", "uri": "file:///tmp/tck-example.txt", "name": "example.txt"},
            ],
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"a prompt with a resource_link block must still succeed: {msg!r}"
        )
