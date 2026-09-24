"""Cancellation conformance: ACP-CANCEL-201..208, ACP-INFO-CANCEL-201/202.

`ACP-CLOSE-202` is also bound to `test_close_cancels_foreground_work` below, alongside its own
`ACP-CANCEL-208` id -- see `tck.v2.requirements` for why this is a deliberate reuse rather than
a duplicate probe.

v2 confirms cancellation via a terminating `session/update` `state_update {state: "idle",
stopReason: "cancelled"}` notification, not the `session/prompt` response (which is only an
acceptance receipt, `{messageId}`; prompt-lifecycle.mdx:519,526).
`ACP-CANCEL-201/202/203/205/206/207/208` are `Tier.CAPABILITY`, `capability="capabilities.session"`.
`ACP-CANCEL-204` ("as soon as possible") is `Tier.INFORMATIONAL` since promptness has no
wire-observable signal; its test still carries the `capabilities.session` marker for the SKIP
gate and always ends in `pytest.skip(...)`, recording `acp_tck_cancel_sent`/`acp_tck_stop_reason`
first so the always-SKIP isn't vacuous.

**The race, and the honest-SKIP pattern**: `run_prompt(..., on_cancel=True)` fires
`session/cancel` on the transition to `state_update {state: "running"}` (or after `cancel_wait`
elapses if `running` is never observed). `_skip_if_cancel_not_exercised` (below) treats two
situations as **not exercised**, not a defect:

1. `turn.cancelled_at_index is None` -- the turn ended before `session/cancel` could be sent.
2. The cancel *was* sent, but the terminating idle arrives with a valid, non-`"cancelled"`
   `stopReason` within `quiet_period(agent_launch.default_timeout)` -- the agent may simply have
   finished on its own first.

Outside those, cancellation is judged for real. `ACP-CANCEL-201`/`207` (folded into one test)
skip when the turn ended via a JSON-RPC error instead of an idle -- `ACP-CANCEL-203` owns that
diagnostic. `ACP-CANCEL-203`'s registered text deliberately covers both "ends with an error" and
"ends with an idle whose stopReason is a non-cancelled known value" -- an agent resolving with
e.g. `stopReason: "end_turn"` genuinely violates both rows at once, so this overlap is intentional.

`ACP-CANCEL-201`/`207` share one test: a single `stopReason == "cancelled"` check evidences both
201's "MUST send a cancelled idle" and 207's "no illegal substitute value". Safe to share since
both are the same tier and a real defect violates both at once -- unlike `ACP-BATCH-204`/`205`'s
ADVISORY-only sharing (see `test_batch.py`).

`ACP-CANCEL-208` ("`session/close` MUST cancel foreground work first") reuses `ACP-CANCEL-201`'s
evidence shape but triggers via `session/close` (through `run_prompt`'s `on_action`, not
`on_cancel`). It does not duplicate `session/close`'s own result/idempotency rows
(`ACP-CLOSE-201`/`202`) -- only the cancellation side effect.

`ACP-INFO-CANCEL-201`/`202` are `Tier.INFORMATIONAL`: cancelling a session with no foreground
work, and cancelling while `session/request_permission` is pending, are both left unspecified by
the v2 docs. Each records the agent's actual behavior via `record_property` without asserting,
gated on `capabilities.session` purely for the SKIP mechanism.
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentTimeout, Direction

from ..protocol import STOP_REASONS
from ._helpers import (
    connected_agent,
    is_response_line,
    iter_messages,
    new_session,
    probe_behaviour,
    quiet_period,
    run_prompt,
)


def _skip_if_turn_end_race_not_exercised(
    agent,
    turn,
    record_property,
    *,
    race_window: float,
    trigger_at_index: int | None,
    trigger_method: str,
    verb: str,
    property_prefix: str,
    race_explanation_suffix: str = "",
) -> None:
    """Shared v2 race gate behind `_skip_if_cancel_not_exercised` (`session/cancel` trigger,
    `ACP-CANCEL-201/203/206/207`) and `_skip_if_close_cancel_not_exercised` (`session/close`
    trigger, `ACP-CANCEL-208`), differing only in trigger index/wire method/property-name
    prefix. See the module docstring's "The race, and the honest-SKIP pattern" section. Only
    ever raises `pytest.skip.Exception` (situations 1/2) or returns; never asserts anything
    itself."""
    if trigger_at_index is None:
        pytest.skip(f"{verb} not exercised: the turn ended before {trigger_method} could be sent")
    if turn.idle_update is None:
        # Ended via a JSON-RPC error instead of an idle -- not a race, but not this helper's
        # callers' concern either; ACP-CANCEL-203 is the row that judges this directly.
        return
    stop_reason = turn.stop_reason
    if stop_reason == "cancelled" or stop_reason not in STOP_REASONS:
        # A clean pass, or a value so wrong it isn't a plausible "finished on its own" outcome
        # either (ACP-STATE-203 already owns flagging an invalid stopReason) -- nothing to skip.
        return
    trigger_timestamp = agent.transcript[trigger_at_index].timestamp
    elapsed_ms = (turn.idle_update.timestamp - trigger_timestamp) * 1000
    record_property(f"acp_tck_{property_prefix}_race_window_ms", f"{race_window * 1000:.0f}")
    if elapsed_ms < race_window * 1000:
        record_property(f"acp_tck_{property_prefix}_race_ms", f"{elapsed_ms:.0f}")
        pytest.skip(
            f"{verb} not exercised: idle arrived {elapsed_ms:.0f} ms after {trigger_method} "
            f"(within the race window) with a valid but non-cancelled stopReason{race_explanation_suffix}"
        )


def _skip_if_cancel_not_exercised(agent, turn, record_property, *, race_window: float) -> None:
    """Shared v2 race gate for `ACP-CANCEL-201/203/206/207` -- see the module docstring's
    "The race, and the honest-SKIP pattern" section. Only ever raises `pytest.skip.Exception`
    (situations 1/2) or returns; never asserts anything itself."""
    _skip_if_turn_end_race_not_exercised(
        agent,
        turn,
        record_property,
        race_window=race_window,
        trigger_at_index=turn.cancelled_at_index,
        trigger_method="session/cancel",
        verb="cancellation",
        property_prefix="cancel",
        race_explanation_suffix=(
            " -- the agent may simply have finished before reading the cancel notification"
        ),
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
    -- e.g. background content -- are explicitly allowed after it; only *state_update*s for the
    cancelled foreground work are constrained here.)

    SKIPs (deferring to `ACP-CANCEL-201`/`207`) whenever the turn didn't actually resolve as
    `stopReason: "cancelled"` in the first place -- this row has nothing to check the "no further
    state_update" claim against otherwise.

    Checks every message inside a batch-array line too: an agent that delivers a spurious
    post-cancel `state_update` folded into a batch would otherwise be invisible to a dict-only
    scan. Only catches `AgentTimeout` on the quiet-period wait, not `AgentExited`: an agent that
    crashes right after the cancelled idle must not score a false PASS by having its exit
    swallowed alongside "no further update arrived".
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
            for msg in iter_messages(entry):
                if msg.get("method") != "session/update":
                    continue
                params = msg.get("params") or {}
                if params.get("sessionId") != session_id:
                    continue
                update = params.get("update") or {}
                if update.get("sessionUpdate") == "state_update":
                    return True
            return False

        with pytest.raises(AgentTimeout):
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
    _skip_if_turn_end_race_not_exercised(
        agent,
        turn,
        record_property,
        race_window=race_window,
        trigger_at_index=turn.action_sent_at_index,
        trigger_method="session/close",
        verb="cancellation-via-close",
        property_prefix="close_cancel",
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

        behaviour = await probe_behaviour(
            agent.wait_for_message(
                is_response_line, timeout=quiet_period(agent_launch.default_timeout)
            ),
            lambda entry: f"sent a response-shaped message: {entry.text!r}",
        )

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
    it, since there is no explicit MUST/SHOULD tying the two together."""
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
        permission_requests_seen = sum(
            1
            for entry in turn.client_requests_seen
            if isinstance(entry.parsed, dict)
            and entry.parsed.get("method") == "session/request_permission"
        )
        record_property(
            "acp_tck_permission_requests_seen",
            permission_requests_seen,
        )  # filtered to session/request_permission specifically: client_requests_seen also
        # carries agent -> client notifications, so an unfiltered len() here would no longer
        # mean what its property name says.
        record_property("acp_tck_stop_reason", turn.stop_reason)
