"""Cancellation conformance: ACP-CANCEL-001, ACP-CANCEL-002 (Reqs 25, 26, 28).

`ACP-JSONRPC-003` already covers a bare `session/cancel` (no prompt in flight) getting no
response, so there is no separate `ACP-CANCEL-003` here.

Whether `session/cancel` actually lands while the prompt is still in flight depends on how fast
the agent resolves the turn, which the TCK can't control. `run_prompt` sends `session/cancel` as
soon as the first `session/update` arrives (or `cancel_wait` elapses); `--tck-cancel-prompt`
gives a real agent enough work to still be in flight when it does, but a fast agent can still
finish first.

A raced/unexercised cancellation SKIPs rather than PASSes, since nothing was actually exercised.
"Not exercised" means either: the response was read before `session/cancel` could be sent
(`cancelled_at_index is None`), or the response arrives with a valid, non-`cancelled` stop reason
within the race window (`quiet_period`, from `--tck-timeout`) of when cancel was sent -- the
agent may have finished on its own before reading the notification.

Anything else is judged normally: `stopReason: "cancelled"` PASSes; an error or a late
non-`cancelled` stop reason FAILs.
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v1.protocol import STOP_REASONS

from ._helpers import PromptTurn, connected_agent, new_session, quiet_period, run_prompt


def _skip_if_cancel_not_exercised(
    agent, turn: PromptTurn, record_property, *, race_window: float
) -> None:
    """Shared by both cancel tests: skips (never PASS/FAIL) if cancellation wasn't actually
    observed (module docstring). An unexercised cancel says nothing about `stopReason`
    correctness (ACP-CANCEL-001) or post-cancel update ordering (ACP-CANCEL-002).
    """
    if turn.cancelled_at_index is None:
        pytest.skip(
            "cancellation not exercised: prompt turn completed before session/cancel could be sent"
        )
    msg = turn.response_entry.parsed
    if not (isinstance(msg, dict) and "result" in msg):
        return  # not a success result -- let the caller's own assertion judge it
    stop_reason = msg["result"].get("stopReason")
    if stop_reason == "cancelled" or stop_reason not in STOP_REASONS:
        return  # clean pass, or an invalid value -- judge it normally either way
    cancel_timestamp = agent.transcript[turn.cancelled_at_index].timestamp
    elapsed_ms = (turn.response_entry.timestamp - cancel_timestamp) * 1000
    record_property("acp_tck_cancel_race_window_ms", f"{race_window * 1000:.0f}")
    if elapsed_ms < race_window * 1000:
        record_property("acp_tck_cancel_race_ms", f"{elapsed_ms:.0f}")
        pytest.skip(
            f"cancellation not exercised: response arrived {elapsed_ms:.0f} ms after cancel; "
            "agent may have finished before reading it"
        )


@pytest.mark.requirement("ACP-CANCEL-001")
async def test_cancel_resolves_with_cancelled_stop_reason(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-001 (Reqs 25, 26). See module docstring for the SKIP-vs-FAIL split."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        _skip_if_cancel_not_exercised(
            agent, turn, record_property, race_window=quiet_period(agent_launch.default_timeout)
        )

        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"cancel must resolve the prompt with a success result, not an error: {msg!r}"
        )
        stop_reason = msg["result"].get("stopReason")
        assert stop_reason == "cancelled", (
            f"expected stopReason 'cancelled' after session/cancel, got {stop_reason!r}"
        )


@pytest.mark.requirement("ACP-CANCEL-002")
async def test_no_session_update_follows_the_cancelled_response(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-002 (Req 28).

    Every `session/update` `run_prompt` observed necessarily arrived before the prompt response
    (stdout is read strictly line-by-line, stopping at the matching response), so the "before"
    half of Req 28 is structural. This test covers the other half: no further `session/update`
    for this session may arrive after the response. Skips under the same conditions as
    ACP-CANCEL-001 (module docstring).
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        _skip_if_cancel_not_exercised(
            agent, turn, record_property, race_window=quiet_period(agent_launch.default_timeout)
        )

        msg = turn.response_entry.parsed
        if not (isinstance(msg, dict) and "result" in msg):
            # An error-shaped cancel response is ACP-CANCEL-001's finding, not this test's.
            pytest.skip(
                "prerequisite not met: cancel did not resolve the prompt with a success "
                f"result (see ACP-CANCEL-001): {msg!r}"
            )
        # Only ordering is this test's concern; sessionId correctness is ACP-PROMPT-002 territory.

        def _is_late_update_for_this_session(entry) -> bool:
            candidate = entry.parsed
            return (
                isinstance(candidate, dict)
                and candidate.get("method") == "session/update"
                and (candidate.get("params") or {}).get("sessionId") == session_id
            )

        # An agent that exits promptly (rather than staying connected through the quiet period)
        # raises AgentExited on EOF, not AgentTimeout -- still "no late update arrived."
        with pytest.raises((AgentTimeout, AgentExited)):
            await agent.wait_for_message(
                _is_late_update_for_this_session, timeout=quiet_period(agent_launch.default_timeout)
            )
