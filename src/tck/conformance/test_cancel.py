"""Cancellation conformance: ACP-CANCEL-001, ACP-CANCEL-002 (Reqs 25, 26, 28).

`ACP-JSONRPC-003` (slice 3) already covers `session/cancel` as a plain notification (no prompt
in flight) receiving no response -- see that test's docstring in `test_jsonrpc.py`, extended to
say so explicitly; there is no separate `ACP-CANCEL-003` here to avoid duplicating it.

The TCK cannot make a real agent's turn "hang": whether `session/cancel` actually lands while
the prompt is still in flight depends on how fast the agent under test resolves the turn, which
this suite has no way to observe from the outside before sending the notification. `run_prompt`
(`_helpers.py`) mitigates this by sending `session/cancel` as soon as either the first
`session/update` arrives or 0.5s elapses, but a genuinely instant agent can still finish before
that. `test_cancel_resolves_with_cancelled_stop_reason` below documents and records that race
rather than asserting a `stopReason` the spec never promised for an already-finished turn.
"""

from __future__ import annotations

import pytest

from tck.harness import AgentTimeout
from tck.protocol import STOP_REASONS

from ._helpers import connected_agent, new_session, run_prompt


@pytest.mark.requirement("ACP-CANCEL-001")
async def test_cancel_resolves_with_cancelled_stop_reason(agent_launch, tmp_path, record_property):
    """ACP-CANCEL-001 (Reqs 25, 26).

    Sends a prompt, sends `session/cancel` once the turn looks like it is still in flight (see
    module docstring), then waits for the prompt response. If the response had already arrived
    before `session/cancel` could be sent -- a race with a fast/no-op agent -- this test cannot
    exercise "cancel a turn that is actually in flight" at all; it degrades to only checking
    that `stopReason` is one of the defined values (already covered by ACP-PROMPT-001) and
    records the race via `record_property`, since asserting `stopReason == "cancelled"` for a
    turn that had already finished on its own would be asserting a requirement the spec does
    not place on that scenario.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "please do some work"}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"cancel must resolve the prompt with a success result, not an error: {msg!r}"
        )
        stop_reason = msg["result"].get("stopReason")
        if turn.cancelled_at_index is None:
            record_property(
                "acp_tck_cancel_raced",
                "session/prompt resolved before session/cancel was sent; cancellation was not "
                "actually exercised",
            )
            assert stop_reason in STOP_REASONS, f"invalid stopReason: {stop_reason!r}"
        else:
            assert stop_reason == "cancelled", (
                f"expected stopReason 'cancelled' after session/cancel, got {stop_reason!r}"
            )


@pytest.mark.requirement("ACP-CANCEL-002")
async def test_no_session_update_follows_the_cancelled_response(agent_launch, tmp_path):
    """ACP-CANCEL-002 (Req 28).

    Every `session/update` `run_prompt` observed necessarily arrived before the prompt response
    (it reads stdout strictly line-by-line and stops at the matching response), so the "before"
    half of Req 28 is structural. This test adds the other half: after the response, no further
    `session/update` for this session may arrive.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "please do some work"}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"cancel must resolve the prompt with a success result, not an error: {msg!r}"
        )
        for _, entry in turn.updates:
            carried_session_id = (entry.parsed.get("params") or {}).get("sessionId")
            assert carried_session_id == session_id, (
                f"session/update carried sessionId {carried_session_id!r}, expected {session_id!r}"
            )

        def _is_late_update_for_this_session(entry) -> bool:
            candidate = entry.parsed
            return (
                isinstance(candidate, dict)
                and candidate.get("method") == "session/update"
                and (candidate.get("params") or {}).get("sessionId") == session_id
            )

        with pytest.raises(AgentTimeout):
            await agent.wait_for_message(_is_late_update_for_this_session, timeout=0.3)
