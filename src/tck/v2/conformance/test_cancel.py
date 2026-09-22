"""Cancellation conformance: ACP-CANCEL-201..208, ACP-INFO-CANCEL-201/202.

`ACP-CLOSE-202` is additionally bound to `test_close_cancels_foreground_work` below, via a
second `@pytest.mark.requirement(...)` id on the same test -- see `tck.v2.requirements`'s
module docstring, "Session management", for why this is a deliberate reuse rather than a
duplicate probe (precedent: `ACP-CANCEL-201`/`ACP-CANCEL-207`).

v2 moves cancellation's confirmation off the `session/prompt` response (which is only ever an
acceptance receipt, `{messageId}`) onto a *separate*, terminating `session/update`
`state_update {state: "idle", stopReason: "cancelled"}` notification
(`.agents/research/acp-v2-cancellation-and-batching.md` "Answer" / prompt-lifecycle.mdx:519,526).
`ACP-CANCEL-201/202/203/205/206/207/208` are `Tier.CAPABILITY`, `capability="capabilities.session"`
-- `session/cancel` is named directly in the seven-method session baseline (the session-baseline
rows rule), exactly like `ACP-SESSION-001/002`/`ACP-PROMPT-201` etc. `ACP-CANCEL-204`
("as soon as possible") is `Tier.ADVISORY` on the `Requirement` itself (`capability=None`, per
`Requirement.__post_init__`'s invariant) since a client-only TCK has no wire-observable way to
judge promptness at all; its test still carries the `capabilities.session` marker for the SKIP
gate and always ends in an explicit `pytest.skip(...)`, never an assertion, mirroring
`ACP-PROMPT-003`'s "ADVISORY row, capability marker on the test anyway" pattern.

**The race, and the honest-SKIP pattern** (ported from v1's `test_cancel.py`, re-keyed to v2's
idle-based turn end instead of the response): `run_prompt(..., on_cancel=True)` fires
`session/cancel` on the transition to `state_update {state: "running"}` (or after `cancel_wait`
elapses if `running` is never observed) -- see `_helpers.run_prompt`'s own docstring. Even so, a
fast agent may finish the whole turn -- including its terminating idle -- before it ever reads
the cancel notification. `_skip_if_cancel_not_exercised` (below) treats this as **not exercised**,
not as a defect, in exactly two situations:

1. `turn.cancelled_at_index is None` -- the turn ended (idle, or an outright rejection) before
   `run_prompt` ever got to send `session/cancel` at all.
2. `session/cancel` *was* sent, but the terminating idle arrives with a valid, non-`"cancelled"`
   `stopReason` within `quiet_period(agent_launch.default_timeout)` of the cancel notification --
   the agent may simply have finished on its own before reading it.

Outside those two situations, cancellation is judged for real. `ACP-CANCEL-201`/`207` (folded
into one test -- see below) only skip (deferring the diagnostic to `ACP-CANCEL-203`) when the
turn ended via a JSON-RPC error instead of an idle -- there is nothing for their own
`stopReason == "cancelled"` assertion to check against in that case. `ACP-CANCEL-203`'s own
registered text (`tck.v2.requirements`) explicitly covers *both* "ends with a JSON-RPC error" and
"ends with an idle whose stopReason is a non-cancelled known value" -- the second half genuinely
overlaps `ACP-CANCEL-201`/`207`'s own positive claim. This is intentional, source-mandated
duplication, not a test bug: an agent that resolves a cancelled turn with e.g. `stopReason:
"end_turn"` really does violate both rows at once (it failed to signal cancellation, *and* it
surfaced non-cancellation as if the turn simply ended normally), so both legitimately FAIL
together on that one defect.

`ACP-CANCEL-201` and `ACP-CANCEL-207` share one test function
(`@pytest.mark.requirement("ACP-CANCEL-201", "ACP-CANCEL-207")`): both rows are evidenced by the
exact same wire fact (the terminating idle's `stopReason` value after a cancel) -- 201 from the
"MUST send a cancelled idle" angle, 207 from the "no illegal non-`_`-prefixed substitute value"
angle -- so a single `stop_reason == "cancelled"` assertion honestly resolves both simultaneously;
this is not the same as `ACP-BATCH-204`/`205`'s ADVISORY-only sharing (see `test_batch.py`), but
sharing is still safe here because both rows are the *same* tier (`CAPABILITY`) and a real defect
here (e.g. `stopReason: "aborted"`) genuinely violates both at once, not just one of them.

`ACP-CANCEL-208` ("`session/close` MUST cancel any foreground work for that session first") reuses
`ACP-CANCEL-201`'s evidence shape (a terminating idle with `stopReason: "cancelled"`), but the
*trigger* is `session/close`, not `session/cancel` -- driven via `run_prompt`'s `on_action`
parameter instead of `on_cancel`. This does **not** duplicate `session/close`'s own-contract rows
(`ACP-CLOSE-201`/`202`): those cover `session/close`'s own result shape and idempotency; this row
covers only the cancellation *side effect* `session/close` must have on in-flight work.

`ACP-INFO-CANCEL-201`/`202` are `Tier.INFORMATIONAL`: cancelling a session with no foreground work
in flight, and cancelling while a `session/request_permission` is pending, are both left
unspecified by the v2 docs the report could find (`acp-v2-cancellation-and-batching.md`
Testability notes) -- each records what the agent actually does via `record_property`, never
asserts on it, and is gated on `capabilities.session` purely for the SKIP mechanism (same
independence between the `Requirement`'s own `capability=None` and the test marker used
throughout this registry; see `tck.v2.requirements`'s module docstring).
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout, Direction

from ..protocol import STOP_REASONS
from ._helpers import connected_agent, new_session, quiet_period, run_prompt


def _skip_if_cancel_not_exercised(agent, turn, record_property, *, race_window: float) -> None:
    """Shared v2 race gate for `ACP-CANCEL-201/203/206/207` -- see the module docstring's
    "The race, and the honest-SKIP pattern" section. Only ever raises `pytest.skip.Exception`
    (situations 1/2) or returns; never asserts anything itself."""
    if turn.cancelled_at_index is None:
        pytest.skip(
            "cancellation not exercised: the turn ended before session/cancel could be sent"
        )
    if turn.idle_update is None:
        # Ended via a JSON-RPC error instead of an idle -- not a race, but not this helper's
        # callers' concern either; ACP-CANCEL-203 is the row that judges this directly.
        return
    stop_reason = turn.stop_reason
    if stop_reason == "cancelled" or stop_reason not in STOP_REASONS:
        # A clean pass, or a value so wrong it isn't a plausible "finished on its own" outcome
        # either (ACP-STATE-203 already owns flagging an invalid stopReason) -- nothing to skip.
        return
    cancel_timestamp = agent.transcript[turn.cancelled_at_index].timestamp
    elapsed_ms = (turn.idle_update.timestamp - cancel_timestamp) * 1000
    record_property("acp_tck_cancel_race_window_ms", f"{race_window * 1000:.0f}")
    if elapsed_ms < race_window * 1000:
        record_property("acp_tck_cancel_race_ms", f"{elapsed_ms:.0f}")
        pytest.skip(
            f"cancellation not exercised: idle arrived {elapsed_ms:.0f} ms after session/cancel "
            "(within the race window) with a valid but non-cancelled stopReason -- the agent may "
            "simply have finished before reading the cancel notification"
        )


@pytest.mark.requirement("ACP-CANCEL-201", "ACP-CANCEL-207")
@pytest.mark.capability("capabilities.session")
async def test_cancel_resolves_with_a_cancelled_idle(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-201/207. Once `session/cancel` is observed to have actually raced against an
    in-flight turn, the turn's terminating idle carries `stopReason: "cancelled"` -- exactly that
    value, not some other valid-but-wrong stop reason (ACP-CANCEL-203's job) and not an illegal
    non-`_`-prefixed substitute (ACP-CANCEL-207's own angle on the very same fact)."""
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
        if turn.idle_update is None:
            pytest.skip(
                "prerequisite not met: the turn ended via a JSON-RPC error, not an idle "
                "state_update -- see ACP-CANCEL-203"
            )
        assert turn.stop_reason == "cancelled", (
            f"expected stopReason 'cancelled' on the terminating idle after session/cancel, "
            f"got {turn.stop_reason!r}"
        )


@pytest.mark.requirement("ACP-CANCEL-203")
@pytest.mark.capability("capabilities.session")
async def test_cancel_does_not_surface_as_a_generic_failure(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-203. After a `session/cancel` that actually raced against the turn, the turn
    must not resolve with a JSON-RPC error on `session/prompt`, nor with a terminating idle whose
    `stopReason` is some other *valid* value (e.g. `end_turn`) instead of `cancelled` -- i.e.
    cancellation must not be surfaced as a generic failure or silently ignored. The positive
    "and it really is 'cancelled'" claim itself belongs to `ACP-CANCEL-201`/`207`, not this row."""
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
        assert not (isinstance(msg, dict) and "error" in msg), (
            f"cancellation surfaced as a JSON-RPC error on session/prompt: {msg!r}"
        )
        if turn.idle_update is not None:
            assert turn.stop_reason == "cancelled" or turn.stop_reason not in STOP_REASONS, (
                f"after session/cancel, the turn ended with a valid but non-cancelled "
                f"stopReason {turn.stop_reason!r} instead of being surfaced as cancelled"
            )


@pytest.mark.requirement("ACP-CANCEL-202")
@pytest.mark.capability("capabilities.session")
async def test_no_further_state_update_after_the_cancelled_idle(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-202. Once the turn has resolved with `stopReason: "cancelled"`, no further
    `state_update` for the same session arrives within `quiet_period` -- i.e. the cancelled idle
    really is the end of this turn's foreground-state machinery. (Other `session/update` kinds
    -- e.g. background content -- are explicitly allowed after it; see the report's own note that
    only *state_update*s for the cancelled foreground work are constrained here.)

    SKIPs (deferring to `ACP-CANCEL-201`/`207`) whenever the turn didn't actually resolve as
    `stopReason: "cancelled"` in the first place -- this row has nothing to check the "no further
    state_update" claim against otherwise.
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
        if turn.idle_update is None or turn.stop_reason != "cancelled":
            pytest.skip(
                "prerequisite not met: the turn did not resolve with stopReason 'cancelled' -- "
                "see ACP-CANCEL-201/207"
            )

        def _is_state_update_for_this_session(entry) -> bool:
            msg = entry.parsed
            if not (isinstance(msg, dict) and msg.get("method") == "session/update"):
                return False
            params = msg.get("params") or {}
            if params.get("sessionId") != session_id:
                return False
            update = params.get("update") or {}
            return update.get("sessionUpdate") == "state_update"

        with pytest.raises((AgentTimeout, AgentExited)):
            await agent.wait_for_message(
                _is_state_update_for_this_session,
                timeout=quiet_period(agent_launch.default_timeout),
            )


@pytest.mark.requirement("ACP-CANCEL-204")
@pytest.mark.capability("capabilities.session")
async def test_cancel_stops_work_promptly(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-204 (ADVISORY -- "as soon as possible" has no wire-observable signal a
    client-only TCK can check; see `tck.v2.requirements`'s module docstring). Runs the same
    cancellation scenario as `ACP-CANCEL-201` so the prerequisite handshake/turn genuinely
    happens, records whether cancellation was actually exercised, and always ends in an explicit
    `pytest.skip(...)` -- never an assertion."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        record_property("acp_tck_cancel_sent", turn.cancelled_at_index is not None)
        record_property("acp_tck_stop_reason", turn.stop_reason)
    pytest.skip(
        "ACP-CANCEL-204 is unobservable from a client-only TCK: the promptness of 'as soon as "
        "possible' cancellation has no wire-level signal to check"
    )


@pytest.mark.requirement("ACP-CANCEL-205")
@pytest.mark.capability("capabilities.session")
async def test_cancel_notification_receives_no_direct_response(
    agent_launch, tmp_path, cancel_prompt_text
):
    """ACP-CANCEL-205. `session/cancel` is a notification (no `id`); the agent must not send any
    response-shaped message (a line with no `method`) attributable to it. The turn's own
    `session/prompt` response is excluded, since a legitimate, merely-delayed acceptance receipt
    can arrive after `session/cancel` was sent without violating anything."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        if turn.cancelled_at_index is None:
            pytest.skip(
                "cancellation not exercised: the turn ended before session/cancel could be sent"
            )

        prompt_response_id = None
        if isinstance(turn.response_entry.parsed, dict):
            prompt_response_id = turn.response_entry.parsed.get("id")

        if turn.idle_update is None:
            end_index = len(agent.transcript)
        else:
            # `turn.idle_update` may be a *synthetic* per-item entry (`dataclasses.replace(...)`)
            # when the terminating idle arrived inside a spontaneous batch line
            # (`emits_batch_updates.py`) -- it is then not `in` `agent.transcript` by identity, so
            # `agent.transcript.index(...)` would raise. `turn.updates` already recorded the
            # *line's own* transcript index alongside that exact entry object; look it up there
            # instead.
            idle_line_index = next(
                line_index for line_index, entry in turn.updates if entry is turn.idle_update
            )
            end_index = idle_line_index + 1
        window = agent.transcript[turn.cancelled_at_index + 1 : end_index]
        for entry in window:
            if entry.direction is not Direction.RECEIVED:
                continue
            raw_msg = entry.parsed
            # A batch line's elements must be checked individually too -- a response-shaped
            # message hidden inside a spontaneous batch is just as much a violation as one on its
            # own line.
            messages = raw_msg if isinstance(raw_msg, list) else [raw_msg]
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if "method" in msg:
                    continue  # an agent -> client request/notification, not a response
                if (
                    prompt_response_id is not None
                    and "id" in msg
                    and msg["id"] == prompt_response_id
                ):
                    continue  # the prompt's own (possibly delayed) acceptance receipt
                pytest.fail(
                    f"agent sent a response-shaped message attributable to the session/cancel "
                    f"notification: {msg!r}"
                )


@pytest.mark.requirement("ACP-CANCEL-206")
@pytest.mark.capability("capabilities.session")
async def test_cancel_with_meta_is_accepted(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-206. A `session/cancel` notification that additionally carries `_meta` is
    still accepted and honoured exactly as a bare one would be -- extensibility (Req 42) applies
    to notifications too."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            cancel_meta={"tck": True},
            timeout=agent_launch.default_timeout,
        )
        _skip_if_cancel_not_exercised(
            agent, turn, record_property, race_window=quiet_period(agent_launch.default_timeout)
        )
        if turn.idle_update is None:
            pytest.skip(
                "prerequisite not met: the turn ended via a JSON-RPC error, not an idle "
                "state_update -- see ACP-CANCEL-203"
            )
        assert turn.stop_reason == "cancelled", (
            f"expected stopReason 'cancelled' after a _meta-carrying session/cancel, got "
            f"{turn.stop_reason!r}"
        )


def _skip_if_close_cancel_not_exercised(agent, turn, record_property, *, race_window: float) -> None:
    """`ACP-CANCEL-208`'s own analogue of `_skip_if_cancel_not_exercised`, keyed on
    `action_sent_at_index`/`action_response` (the `session/close` trigger) instead of
    `cancelled_at_index` (there is no `session/cancel` in this scenario at all)."""
    if turn.action_sent_at_index is None:
        pytest.skip(
            "cancellation-via-close not exercised: the turn ended before session/close could be "
            "sent"
        )
    if turn.idle_update is None:
        return
    stop_reason = turn.stop_reason
    if stop_reason == "cancelled" or stop_reason not in STOP_REASONS:
        return
    close_timestamp = agent.transcript[turn.action_sent_at_index].timestamp
    elapsed_ms = (turn.idle_update.timestamp - close_timestamp) * 1000
    record_property("acp_tck_close_cancel_race_window_ms", f"{race_window * 1000:.0f}")
    if elapsed_ms < race_window * 1000:
        record_property("acp_tck_close_cancel_race_ms", f"{elapsed_ms:.0f}")
        pytest.skip(
            f"cancellation-via-close not exercised: idle arrived {elapsed_ms:.0f} ms after "
            "session/close (within the race window) with a valid but non-cancelled stopReason"
        )


@pytest.mark.requirement("ACP-CANCEL-208", "ACP-CLOSE-202")
@pytest.mark.capability("capabilities.session")
async def test_close_cancels_foreground_work(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CANCEL-208 / ACP-CLOSE-202. `session/close` for a session with an in-flight turn must
    cancel that foreground work first -- the same terminating-idle-with-`stopReason: "cancelled"`
    evidence as `ACP-CANCEL-201`, but triggered by `session/close` instead of `session/cancel`.
    `ACP-CLOSE-202` is a deliberate re-mint of the exact same wire evidence, not a second probe
    -- see the module docstring and `tck.v2.requirements`'s "Session management" section.
    Does not duplicate `ACP-CLOSE-201`, which covers `session/close`'s own result-shape contract
    on a session with no foreground work in flight."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        async def _close():
            return await agent.send_request("session/close", {"sessionId": session_id})

        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_action=_close,
            timeout=agent_launch.default_timeout,
        )
        _skip_if_close_cancel_not_exercised(
            agent, turn, record_property, race_window=quiet_period(agent_launch.default_timeout)
        )
        if turn.idle_update is None:
            pytest.skip(
                "prerequisite not met: the turn ended via a JSON-RPC error, not an idle "
                "state_update"
            )
        assert turn.stop_reason == "cancelled", (
            f"expected stopReason 'cancelled' after session/close on a session with in-flight "
            f"work, got {turn.stop_reason!r}"
        )


@pytest.mark.requirement("ACP-INFO-CANCEL-201")
@pytest.mark.capability("capabilities.session")
async def test_cancel_with_no_foreground_work_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-CANCEL-201 (INFORMATIONAL). `session/cancel` for a session that has no prompt in
    flight at all. The v2 docs are silent on what, if anything, should happen -- records whether
    the agent replies, stays silent, or exits; never asserts."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await agent.send_notification("session/cancel", {"sessionId": session_id})

        def _is_a_response(entry) -> bool:
            return isinstance(entry.parsed, dict) and "method" not in entry.parsed

        try:
            entry = await agent.wait_for_message(
                _is_a_response, timeout=quiet_period(agent_launch.default_timeout)
            )
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            behaviour = f"sent a response-shaped message: {entry.text!r}"

    record_property("behaviour", behaviour)


@pytest.mark.requirement("ACP-INFO-CANCEL-202")
@pytest.mark.capability("capabilities.session")
async def test_cancel_during_pending_permission_request_behaviour(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-INFO-CANCEL-202 (INFORMATIONAL). Records the terminating stopReason -- and whether a
    pending `session/request_permission` was answered `cancelled` -- when `session/cancel`
    arrives while a permission request is outstanding. `_helpers.run_prompt` already answers a
    pending permission request with `{"outcome": "cancelled"}` once cancel has been sent
    (`tool-calls.mdx:304`); this row simply records the resulting shape rather than asserting on
    it, since the report found no explicit MUST/SHOULD tying the two together."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_cancel=True,
            timeout=agent_launch.default_timeout,
        )
        record_property("acp_tck_cancel_sent", turn.cancelled_at_index is not None)
        record_property(
            "acp_tck_permission_requests_seen", len(turn.client_requests_seen)
        )
        record_property("acp_tck_stop_reason", turn.stop_reason)
