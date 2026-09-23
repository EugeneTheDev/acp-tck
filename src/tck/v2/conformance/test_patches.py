"""Patch/upsert semantics: ACP-PATCH-201, ACP-PATCH-203..209.

`ACP-PATCH-202` (the `session/prompt` result's `messageId` matches the `user_message`/
`user_message_chunk` updates' own `messageId`) is deliberately **not** registered here: it is
already fully covered by `ACP-PROMPT-201` + `ACP-PROMPT-203`.

ACP-PATCH-201/203/204/205/206/207 are `Tier.CAPABILITY` (`capabilities.session`);
ACP-PATCH-208/209 are `Tier.ADVISORY` with only the *test* capability-gated for the SKIP.

Most of these are pure shape checks over whatever the agent happens to emit during one driven
turn: SKIP "no <variant> observed" whenever the relevant update kind never appears, rather than a
vacuous PASS or an unjustified FAIL. Neither reference SDK exercises tool calls/plans/terminals
over v2 yet, so these rows SKIP against `testy`/`echo_agent` and only PASS for real against the
repo's own `conforming_full.py` (opted in via `emit_rich_turn_updates=True`) and its defect
fixtures.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import pytest

from ..protocol import STOP_REASON_CANCELLED, STOP_REASON_REFUSAL
from ._helpers import connected_agent, new_session, run_prompt

_PROMPT_TEXT = "hi"

_MESSAGE_KINDS = frozenset(
    {
        "user_message_chunk",
        "user_message",
        "agent_message_chunk",
        "agent_message",
        "agent_thought_chunk",
        "agent_thought",
    }
)


def _update_dicts(turn) -> list[dict[str, Any]]:
    """Every `session/update`'s inner `update` object observed during `turn`, in wire order."""
    result: list[dict[str, Any]] = []
    for _, entry in turn.updates:
        msg = entry.parsed
        if not isinstance(msg, dict):
            continue
        params = msg.get("params")
        if not isinstance(params, dict):
            continue
        update = params.get("update")
        if isinstance(update, dict):
            result.append(update)
    return result


async def _drive_one_turn(agent_launch, tmp_path):
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
    return turn


@pytest.mark.requirement("ACP-PATCH-201")
@pytest.mark.capability("capabilities.session")
async def test_every_message_update_carries_a_message_id(agent_launch, tmp_path):
    """ACP-PATCH-201 (CAPABILITY). Every `*_message*`/`*_thought*` update carries a non-empty
    string `messageId` -- the keyed-upsert identity the whole message-patch family hinges on
    (`prompt-lifecycle.mdx:246`; `schema/v2/schema.json:4738-4856`)."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    message_updates = [u for u in _update_dicts(turn) if u.get("sessionUpdate") in _MESSAGE_KINDS]
    if not message_updates:
        pytest.skip("no message update observed during this turn")
    for update in message_updates:
        message_id = update.get("messageId")
        assert isinstance(message_id, str) and message_id, (
            f"{update.get('sessionUpdate')!r} update missing/empty messageId: {update!r}"
        )


@pytest.mark.requirement("ACP-PATCH-203")
@pytest.mark.capability("capabilities.session")
async def test_two_prompts_receive_distinct_message_ids(agent_launch, tmp_path):
    """ACP-PATCH-203 (CAPABILITY). Two `session/prompt`s with identical content receive two
    distinct `messageId`s (`prompt-lifecycle.mdx:151`) -- the v2 analogue of v1's
    `duplicate_session_id.py` defect pattern, applied to message ids instead of session ids."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        first = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
        second = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )

    assert first.message_id, f"first session/prompt response missing messageId: {first!r}"
    assert second.message_id, f"second session/prompt response missing messageId: {second!r}"
    assert first.message_id != second.message_id, (
        f"two session/prompt calls with identical content received the same messageId "
        f"({first.message_id!r}); each submission must get a distinct id"
    )


@pytest.mark.requirement("ACP-PATCH-204")
@pytest.mark.capability("capabilities.session")
async def test_tool_call_updates_carry_tool_call_id(agent_launch, tmp_path):
    """ACP-PATCH-204 (CAPABILITY). Every `tool_call_update` carries `toolCallId`; every
    `tool_call_content_chunk` carries `toolCallId` + `content`
    (`schema/v2/schema.json:674-758,5040-5110`) -- there is no separate "create" message in v2's
    keyed-upsert model, so the identity key must be present on every single one, including the
    very first (which *is* the create)."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    updates = _update_dicts(turn)
    tool_call_updates = [u for u in updates if u.get("sessionUpdate") == "tool_call_update"]
    content_chunks = [u for u in updates if u.get("sessionUpdate") == "tool_call_content_chunk"]
    if not tool_call_updates and not content_chunks:
        pytest.skip("no tool_call_update/tool_call_content_chunk observed during this turn")
    for update in tool_call_updates:
        tool_call_id = update.get("toolCallId")
        assert isinstance(tool_call_id, str) and tool_call_id, (
            f"tool_call_update missing/empty toolCallId: {update!r}"
        )
    for update in content_chunks:
        tool_call_id = update.get("toolCallId")
        assert isinstance(tool_call_id, str) and tool_call_id, (
            f"tool_call_content_chunk missing/empty toolCallId: {update!r}"
        )
        assert update.get("content") is not None, (
            f"tool_call_content_chunk missing content: {update!r}"
        )


@pytest.mark.requirement("ACP-PATCH-205")
@pytest.mark.capability("capabilities.session")
async def test_plan_updates_carry_plan_id(agent_launch, tmp_path):
    """ACP-PATCH-205 (CAPABILITY). Every `plan_update.plan`, including an unknown/`_`-prefixed
    variant, carries `planId` (`agent-plan.mdx:71`; `schema/v2/schema.json:5199-5278`)."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    plan_updates = [u for u in _update_dicts(turn) if u.get("sessionUpdate") == "plan_update"]
    if not plan_updates:
        pytest.skip("no plan_update observed during this turn")
    for update in plan_updates:
        plan = update.get("plan")
        assert isinstance(plan, dict), f"plan_update missing plan object: {update!r}"
        plan_id = plan.get("planId")
        assert isinstance(plan_id, str) and plan_id, (
            f"plan_update.plan missing/empty planId: {update!r}"
        )


@pytest.mark.requirement("ACP-PATCH-206")
@pytest.mark.capability("capabilities.session")
async def test_terminal_updates_have_absolute_cwd_and_unique_ids(agent_launch, tmp_path):
    """ACP-PATCH-206 (CAPABILITY). A supplied `terminal_update.cwd` is absolute; a `terminalId`
    is never reused for a different terminal within a session (`tool-calls.mdx:405-411,439-440`).
    "Reused for a different terminal" is judged as: the same `terminalId` observed with a
    different `cwd` than the first time it was seen (the only client-observable signal that two
    distinct terminals were assigned the same id -- v2 has no separate terminal "create" call to
    compare against)."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    terminal_updates = [u for u in _update_dicts(turn) if u.get("sessionUpdate") == "terminal_update"]
    if not terminal_updates:
        pytest.skip("no terminal_update observed during this turn")
    first_cwd_by_id: dict[str, str] = {}
    for update in terminal_updates:
        terminal_id = update.get("terminalId")
        assert isinstance(terminal_id, str) and terminal_id, (
            f"terminal_update missing/empty terminalId: {update!r}"
        )
        cwd = update.get("cwd")
        if cwd is None:
            continue  # cwd is a patch field: omitted means unchanged, nothing new to check
        assert isinstance(cwd, str) and os.path.isabs(cwd), (
            f"terminal_update.cwd must be an absolute path, got {cwd!r}"
        )
        seen_cwd = first_cwd_by_id.get(terminal_id)
        if seen_cwd is None:
            first_cwd_by_id[terminal_id] = cwd
        else:
            assert cwd == seen_cwd, (
                f"terminalId {terminal_id!r} was seen with two different cwds "
                f"({seen_cwd!r}, {cwd!r}) -- terminalIds must not be reused for a different "
                "terminal within a session"
            )


@pytest.mark.requirement("ACP-PATCH-207")
@pytest.mark.capability("capabilities.session")
async def test_terminal_output_chunks_decode_standalone(agent_launch, tmp_path):
    """ACP-PATCH-207 (CAPABILITY). `terminal_output_chunk.data` and `terminal_update.output.data`
    each decode as standalone RFC 4648 base64 (`tool-calls.mdx:441-446,466-474`) -- a chunk that
    only decodes once concatenated with a previous one is non-conforming."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    updates = _update_dicts(turn)
    chunks = [u for u in updates if u.get("sessionUpdate") == "terminal_output_chunk"]
    terminal_updates_with_output = [
        u
        for u in updates
        if u.get("sessionUpdate") == "terminal_update" and isinstance(u.get("output"), dict)
    ]
    if not chunks and not terminal_updates_with_output:
        pytest.skip("no terminal_output_chunk/terminal_update.output observed during this turn")
    for update in chunks:
        data = update.get("data")
        assert isinstance(data, str), f"terminal_output_chunk missing data: {update!r}"
        try:
            base64.b64decode(data, validate=True)
        except Exception as exc:  # noqa: BLE001 - report any decode failure as the assertion
            pytest.fail(f"terminal_output_chunk.data did not decode as standalone base64: {exc}")
    for update in terminal_updates_with_output:
        data = update["output"].get("data")
        assert isinstance(data, str), f"terminal_update.output missing data: {update!r}"
        try:
            base64.b64decode(data, validate=True)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"terminal_update.output.data did not decode as standalone base64: {exc}")


@pytest.mark.requirement("ACP-PATCH-208")
@pytest.mark.capability("capabilities.session")
async def test_first_tool_call_update_reports_title(agent_launch, tmp_path):
    """ACP-PATCH-208 (ADVISORY). The first `tool_call_update` for a new `toolCallId` includes
    `title`, and `name` does not change afterward once set (`tool-calls.mdx:44-52`)."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    tool_call_updates = [
        u for u in _update_dicts(turn) if u.get("sessionUpdate") == "tool_call_update"
    ]
    if not tool_call_updates:
        pytest.skip("no tool_call_update observed during this turn")
    first_seen: dict[str, dict[str, Any]] = {}
    names: dict[str, Any] = {}
    for update in tool_call_updates:
        tool_call_id = update.get("toolCallId")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue  # ACP-PATCH-204 already FAILs this case
        if tool_call_id not in first_seen:
            first_seen[tool_call_id] = update
            title = update.get("title")
            assert isinstance(title, str) and title, (
                f"first tool_call_update for toolCallId {tool_call_id!r} is missing a "
                f"non-empty title: {update!r}"
            )
            if "name" in update and update["name"] is not None:
                names[tool_call_id] = update["name"]
        elif "name" in update and update["name"] is not None:
            previous = names.get(tool_call_id)
            if previous is not None:
                assert update["name"] == previous, (
                    f"toolCallId {tool_call_id!r}'s name changed from {previous!r} to "
                    f"{update['name']!r} across updates"
                )
            else:
                names[tool_call_id] = update["name"]


@pytest.mark.requirement("ACP-PATCH-209")
@pytest.mark.capability("capabilities.session")
async def test_requires_action_reported_around_permission_request(agent_launch, tmp_path):
    """ACP-PATCH-209 (ADVISORY). While blocked on a permission response the agent reports
    `requires_action`, and `running` when it resumes (`prompt-lifecycle.mdx:371`). SKIPs when
    the turn ends in `refusal`/`cancelled`: a refused or cancelled turn legitimately never
    resumes foreground work, so there is nothing for the "running again" half of this check to
    observe."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    if not any(
        isinstance(entry.parsed, dict) and entry.parsed.get("method") == "session/request_permission"
        for entry in turn.client_requests_seen
    ):
        pytest.skip("no permission request observed during this turn")

    states = [
        u.get("state") for u in _update_dicts(turn) if u.get("sessionUpdate") == "state_update"
    ]
    assert "requires_action" in states, (
        f"agent sent session/request_permission but never reported state_update "
        f"{{state: 'requires_action'}}; observed states: {states!r}"
    )
    if turn.stop_reason in (STOP_REASON_REFUSAL, STOP_REASON_CANCELLED):
        pytest.skip(
            f"turn ended with stopReason={turn.stop_reason!r}; the turn never resumed "
            "foreground work, so there is nothing to check for a 'running' state after "
            "requires_action"
        )
    last_requires_action = max(i for i, s in enumerate(states) if s == "requires_action")
    assert "running" in states[last_requires_action + 1 :], (
        f"agent never reported state_update {{state: 'running'}} again after "
        f"requires_action; observed states: {states!r}"
    )
