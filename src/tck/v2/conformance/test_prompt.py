"""Prompt-turn conformance: ACP-PROMPT-201, ACP-PROMPT-203, ACP-STATE-201..203, ACP-PROMPT-205
(NOT a reuse of v1's ACP-PROMPT-002 -- the tier changed, see `tck.v2.requirements`'s module
docstring for the id-namespacing decisions), and ACP-PROMPT-003 (reused from v1, unchanged
ADVISORY tier -- the text+resource_link doc conflict survives verbatim into v2).

The first six are `Tier.CAPABILITY`, `capability="capabilities.session"` -- `session/prompt` is
part of the seven-method baseline an agent commits to by advertising `capabilities.session` at
all, exactly like `ACP-SESSION-001/002`. `ACP-PROMPT-003` is `Tier.ADVISORY` on the
`Requirement` itself (`capability=None`, per `Requirement.__post_init__`'s invariant), but its
test still carries the same `@pytest.mark.capability("capabilities.session")` marker for the
SKIP gate -- `_tck_capability_gate` reads only the marker, independent of the registered tier.
"""

from __future__ import annotations

import pytest

from tck.v2.protocol import STOP_REASONS, is_valid_open_enum_value
from tck.v2.validation import validate_agent_message

from ._helpers import connected_agent, new_session, run_prompt

_PROMPT_TEXT = "hi"


@pytest.mark.requirement("ACP-PROMPT-201")
@pytest.mark.capability("capabilities.session")
async def test_prompt_response_is_an_acceptance_receipt_with_a_message_id(agent_launch, tmp_path):
    """ACP-PROMPT-201. The `session/prompt` response is a non-error result whose `messageId` is
    a non-empty string -- the acceptance-receipt shape (no `stopReason` here at all; the turn's
    outcome is learned only from a later `session/update`, see `ACP-STATE-201..203` below).
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/prompt did not return a result object: {turn.response_entry.text!r}"
        )
        assert isinstance(turn.message_id, str) and turn.message_id, (
            f"session/prompt result.messageId must be a non-empty string, got "
            f"{msg['result'].get('messageId')!r}"
        )


@pytest.mark.requirement("ACP-PROMPT-203")
@pytest.mark.capability("capabilities.session")
async def test_agent_echoes_the_inserted_user_message(agent_launch, tmp_path):
    """ACP-PROMPT-203. The agent reports the inserted user message via a `user_message` update
    (or at least one `user_message_chunk` update) carrying the *same* `messageId` as the
    `session/prompt` response, for the prompted session.

    SKIPs (rather than asserting against `None`) whenever `turn.message_id` is not itself a
    valid non-empty string -- `ACP-PROMPT-201` is the row that already FAILs that case with a
    more precise diagnostic; this row has nothing meaningful to check the echo against then.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        if not (isinstance(turn.message_id, str) and turn.message_id):
            pytest.skip(
                "session/prompt response carried no usable messageId -- see ACP-PROMPT-201"
            )

        echoed = False
        for _, entry in turn.updates:
            update_msg = entry.parsed
            if not isinstance(update_msg, dict):
                continue
            params = update_msg.get("params") or {}
            if params.get("sessionId") != session_id:
                continue
            update = params.get("update") or {}
            kind = update.get("sessionUpdate")
            if kind in ("user_message", "user_message_chunk") and update.get(
                "messageId"
            ) == turn.message_id:
                echoed = True
                break
        assert echoed, (
            f"no user_message/user_message_chunk update echoed messageId "
            f"{turn.message_id!r} for session {session_id!r}"
        )


@pytest.mark.requirement("ACP-STATE-201")
@pytest.mark.capability("capabilities.session")
async def test_running_precedes_a_turn_ending_idle(agent_launch, tmp_path, record_property):
    """ACP-STATE-201. If a turn-ending idle (one carrying a `stopReason`) is observed for the
    prompted session, a `state_update {state: "running"}` for that session was observed earlier
    in the same turn.

    Gated on the idle, not on `running` itself (see `tck.v2.requirements`'s `ACP-STATE-201`
    docstring for why this differs from `ACP-STATE-202`/`ACP-STATE-203`'s own gate): SKIPs as
    "no turn-ending idle observed" only when the turn's idle never carried a `stopReason` at
    all. A turn-ending idle with no preceding `running` FAILs this row rather than SKIPping it.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        record_property("acp_tck_running_seen", turn.running_seen)
        record_property("acp_tck_stop_reason", turn.stop_reason)
        if turn.idle_update is None or turn.stop_reason is None:
            pytest.skip("no turn-ending idle observed: this turn never reached a stop-reason-bearing idle")
        assert turn.running_seen, (
            "a turn-ending idle (stopReason present) was observed, but no state_update "
            "{state: \"running\"} preceded it for this session"
        )


@pytest.mark.requirement("ACP-STATE-202")
@pytest.mark.capability("capabilities.session")
async def test_idle_follows_running_within_the_turn_deadline(agent_launch, tmp_path, record_property):
    """ACP-STATE-202. After an accepted prompt for a session that showed `state_update
    {state: "running"}`, an idle `state_update` for that session arrives within the turn's
    `--timeout` budget.

    SKIPs as "no foreground work observed" when `running` was never observed at all -- the spec
    does not say whether a zero-work prompt must still emit `running`, so a turn that never
    shows it is not scored a defect by this row.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        record_property("acp_tck_running_seen", turn.running_seen)
        if not turn.running_seen:
            pytest.skip("no foreground work observed: this turn never showed state_update {state: \"running\"}")
        assert turn.idle_update is not None, (
            "state_update {state: \"running\"} was observed, but no terminating idle "
            "state_update arrived within the turn's timeout budget"
        )


@pytest.mark.requirement("ACP-STATE-203")
@pytest.mark.capability("capabilities.session")
async def test_terminating_idle_carries_a_valid_stop_reason(agent_launch, tmp_path, record_property):
    """ACP-STATE-203. The idle `state_update` that terminates an observed `running` turn carries
    a `stopReason`, and its value is one of the five defined constants or begins with `_`
    (`tck.v2.protocol.is_valid_open_enum_value`) -- the open-enum extensibility rule.

    Same "no foreground work observed" SKIP gate as `ACP-STATE-202` (`running` never observed).
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        record_property("acp_tck_running_seen", turn.running_seen)
        record_property("acp_tck_stop_reason", turn.stop_reason)
        if not turn.running_seen:
            pytest.skip("no foreground work observed: this turn never showed state_update {state: \"running\"}")
        assert turn.idle_update is not None, (
            "state_update {state: \"running\"} was observed, but no terminating idle "
            "state_update ever arrived -- see ACP-STATE-202"
        )
        assert is_valid_open_enum_value(turn.stop_reason, STOP_REASONS), (
            f"terminating idle's stopReason is not a defined constant or a valid `_`-prefixed "
            f"extension: {turn.stop_reason!r}"
        )


@pytest.mark.requirement("ACP-PROMPT-205")
@pytest.mark.capability("capabilities.session")
async def test_updates_validate_and_carry_the_right_session_id(agent_launch, tmp_path):
    """ACP-PROMPT-205 (NOT a reuse of v1's ACP-PROMPT-002: same check, but v1's was
    `Tier.MANDATORY` and this one is `Tier.CAPABILITY` -- a changed tier is a changed
    requirement under D3, so it gets its own id; see `tck.v2.requirements`'s module docstring).

    Vacuous pass when `turn.updates` is empty (a conforming agent is not required to send any
    updates at all -- see v1's identically-scoped test for the same rationale); only fails when
    an update *is* sent and is malformed or misattributed.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
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
@pytest.mark.capability("capabilities.session")
async def test_resource_link_content_block_is_accepted(agent_launch, tmp_path):
    """ACP-PROMPT-003 (ADVISORY -- reused from v1, re-cited to v2 sources:
    `initialization.mdx:203` lists `resource_link` as baseline MUST-accept alongside `text`, but
    `content.mdx:33` says only `text` is MUST -- the same doc conflict v1 already carries,
    unresolved verbatim in v2, so this stays ADVISORY rather than becoming a hard FAIL target."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [
                {"type": "text", "text": "have a look at this"},
                {
                    "type": "resource_link",
                    "uri": "file:///tmp/tck-example.txt",
                    "name": "example.txt",
                },
            ],
            timeout=agent_launch.default_timeout,
        )
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"a prompt with a resource_link block must still succeed: {turn.response_entry.text!r}"
        )
