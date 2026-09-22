"""Cancellation conformance: ACP-CANCEL-001, ACP-CANCEL-002 (Reqs 25, 26, 28).

`ACP-JSONRPC-003` already covers `session/cancel` as a plain notification (no prompt in flight)
receiving no response -- see that test's docstring in `test_jsonrpc.py`; there is no separate
`ACP-CANCEL-003` here to avoid duplicating it.

The TCK cannot make a real agent's turn "hang": whether `session/cancel` actually lands while
the prompt is still in flight depends on how fast the agent under test resolves the turn, which
this suite has no way to observe from the outside before sending the notification. `run_prompt`
(`_helpers.py`) mitigates this by sending `session/cancel` as soon as either the first
`session/update` arrives or `cancel_wait` seconds elapse, and the cancel tests use the
`--tck-cancel-prompt` text (long by default) to keep a real agent busy long enough for the
notification to land while the turn is still in flight -- but a genuinely instant (or very fast)
agent can still finish before or shortly after that.

A raced/unexercised cancellation is reported as SKIPPED, never PASS -- claiming a PASS for a
requirement that was never actually exercised would be dishonest. Two situations count as
"not exercised":

1. The response was read before `session/cancel` could be sent at all (`cancelled_at_index is
   None`) -- `run_prompt` never got a chance to interrupt an in-flight turn.
2. `session/cancel` was sent, but the response arrives with a valid, non-`cancelled` stop reason
   within a quiet period (`tck.v1.conformance._helpers.quiet_period`, derived from `--tck-timeout`
   rather than a fixed sub-second constant) of when the cancel notification was written -- the
   agent may simply have finished on its own before it ever read the notification.

Anything else is exercised and judged normally: `stopReason: "cancelled"` is a PASS: a
JSON-RPC error, or a non-`cancelled` stop reason arriving later than the race window, is a FAIL.
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v1.protocol import STOP_REASONS

from ._helpers import PromptTurn, connected_agent, new_session, quiet_period, run_prompt


def _skip_if_cancel_not_exercised(
    agent, turn: PromptTurn, record_property, *, race_window: float
) -> None:
    """Shared by both cancel tests: `pytest.skip(...)` -- never PASS or FAIL -- if this turn's
    cancellation could not actually be observed (module docstring, situations 1 and 2). An
    unexercised cancel says nothing about `stopReason` correctness (ACP-CANCEL-001) or
    post-cancel update ordering (ACP-CANCEL-002) either way.
    """
    if turn.cancelled_at_index is None:
        pytest.skip(
            "cancellation not exercised: prompt turn completed before session/cancel could be sent"
        )
    msg = turn.response_entry.parsed
    if not (isinstance(msg, dict) and "result" in msg):
        return  # not a success result -- the caller's own assertion will judge this normally
    stop_reason = msg["result"].get("stopReason")
    if stop_reason == "cancelled" or stop_reason not in STOP_REASONS:
        return  # either a clean pass, or a genuinely invalid value -- judge it normally either way
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
    (it reads stdout strictly line-by-line and stops at the matching response), so the "before"
    half of Req 28 is structural. This test adds the other half: after the response, no further
    `session/update` for this session may arrive. Skips, rather than passing or failing, under
    the same conditions as ACP-CANCEL-001 -- see module docstring: an unexercised cancel says
    nothing about post-cancel ordering.
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
            # An error-shaped cancel response is ACP-CANCEL-001's finding to make, not this
            # test's -- asserting it here too would double-report the same defect as an
            # *ordering* violation of Req 28, which is this test's actual and only concern.
            pytest.skip(
                "prerequisite not met: cancel did not resolve the prompt with a success "
                f"result (see ACP-CANCEL-001): {msg!r}"
            )
        # Only ordering is this test's concern (Req 28); whether each update carries the right
        # sessionId is ACP-PROMPT-002/Req 1 territory, asserted there -- attributing that here
        # would mis-blame Req 28 for a mis-attributed-update defect.

        def _is_late_update_for_this_session(entry) -> bool:
            candidate = entry.parsed
            return (
                isinstance(candidate, dict)
                and candidate.get("method") == "session/update"
                and (candidate.get("params") or {}).get("sessionId") == session_id
            )

        # An agent that exits promptly after resolving the prompt (rather than staying connected
        # through the quiet period) raises AgentExited on EOF, not AgentTimeout -- that is still
        # "no late update arrived," not a defect this requirement is about.
        with pytest.raises((AgentTimeout, AgentExited)):
            await agent.wait_for_message(
                _is_late_update_for_this_session, timeout=quiet_period(agent_launch.default_timeout)
            )
