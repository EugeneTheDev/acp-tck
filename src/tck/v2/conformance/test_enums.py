"""Open-enum emitter rules: ACP-ENUM-201, ACP-ENUM-202, ACP-ENUM-203
(`.agents/research/acp-v2-patches-enums-extensibility.md` "Open enums -- new family", B.1/B.2/B.5).

v2's schema is open at every scalar enum and tagged-union discriminator except
`ElicitationSchemaType` and the JSON-RPC `jsonrpc` literal (B.4) -- but nine separate prose
passages bind the *emitter* anyway: a value must be a defined constant OR begin with `_`
(B.5). `tck.v2.protocol.is_valid_open_enum_value` is the hand-written check that enforces this
(the schema itself would happily accept `"kind": "sorcery"` via its own `other`-branch
fallback). The defined-constant sets themselves (`TOOL_KIND`, `TOOL_CALL_STATUS`,
`PLAN_ENTRY_PRIORITY`, `PLAN_ENTRY_STATUS`, `SESSION_UPDATE_KIND`, `STATE_UPDATE_STATE`,
`TOOL_CALL_CONTENT_TYPE`) live in `tck.v2.protocol` next to `STOP_REASONS`, not here -- promoted
out of this module's former local copies (review-v2-slices-1b-6 finding 20); see
`tests/v2/test_validation.py::test_enum_sets_match_the_schema` for the meta-test that keeps them
honest against `schema.json`.

The re-worded v1 `ACP-PROMPT-001` ("the idle's `stopReason` is a defined constant or `_`-prefixed")
is deliberately **not** re-registered here: it is already fully covered by `ACP-STATE-203`, which
already combines "carries a `stopReason`" with exactly this value-legality check.

`ACP-ENUM-201` covers the sites the report's B.2 table says carry *dedicated* per-site MUST prose
(a curated, not exhaustive, subset of the full 30-site B.1/B.2 inventory -- classifying every
single site's prose strength individually is out of scope; this subset is directly traceable to
the report's own citations and is the highest-value one to automate):
`ToolKind` (`tool_call_update.kind`), `ToolCallStatus` (`tool_call_update.status`),
`PlanEntryPriority`/`PlanEntryStatus` (plan entries). Turn-observable, so `Tier.CAPABILITY`,
`capability="capabilities.session"` per the session-baseline tiering rule (promoted from the
report's own MANDATORY).

`ACP-ENUM-202` covers three of the report's own "no dedicated prose" examples --
`SessionUpdate.sessionUpdate`, `StateUpdate.state`, `ToolCallContent.type` -- at `Tier.ADVISORY`,
`capability=None` (not promoted; only the *test* still `@pytest.mark.capability`-gated for the
SKIP, mirroring `ACP-CANCEL-204`/`ACP-DELETE-203`).

`ACP-ENUM-203` is the receiver-tolerance direction (client sends a `_`-prefixed value, agent must
not crash/`-32602`): also `Tier.ADVISORY`, `capability=None`, test `@pytest.mark.capability`-gated.
`run_prompt()` has no hook to inject a non-standard permission-outcome value, so this test drives
its own minimal turn by hand instead of reusing it.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v2.protocol import (
    METHOD_NOT_FOUND,
    PLAN_ENTRY_PRIORITY,
    PLAN_ENTRY_STATUS,
    SESSION_UPDATE_KIND,
    STATE_UPDATE_STATE,
    TOOL_CALL_CONTENT_TYPE,
    TOOL_CALL_STATUS,
    TOOL_KIND,
    is_valid_open_enum_value,
)

from ._helpers import connected_agent, new_session, run_prompt

_PROMPT_TEXT = "hi"


def _update_dicts(turn) -> list[dict[str, Any]]:
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


@pytest.mark.requirement("ACP-ENUM-201")
@pytest.mark.capability("capabilities.session")
async def test_dedicated_prose_open_enum_sites_are_defined_or_underscore_prefixed(
    agent_launch, tmp_path
):
    """ACP-ENUM-201 (CAPABILITY). `tool_call_update.kind`/`.status` and plan entries'
    `priority`/`status` are each a defined constant or begin with `_`."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    updates = _update_dicts(turn)

    checked = 0
    violations: list[str] = []

    for update in updates:
        if update.get("sessionUpdate") != "tool_call_update":
            continue
        if "kind" in update and update["kind"] is not None:
            checked += 1
            if not is_valid_open_enum_value(update["kind"], TOOL_KIND):
                violations.append(f"tool_call_update.kind={update['kind']!r}")
        if "status" in update and update["status"] is not None:
            checked += 1
            if not is_valid_open_enum_value(update["status"], TOOL_CALL_STATUS):
                violations.append(f"tool_call_update.status={update['status']!r}")

    for update in updates:
        if update.get("sessionUpdate") != "plan_update":
            continue
        plan = update.get("plan")
        if not isinstance(plan, dict):
            continue
        for entry in plan.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            if "priority" in entry:
                checked += 1
                if not is_valid_open_enum_value(entry["priority"], PLAN_ENTRY_PRIORITY):
                    violations.append(f"plan entry priority={entry['priority']!r}")
            if "status" in entry:
                checked += 1
                if not is_valid_open_enum_value(entry["status"], PLAN_ENTRY_STATUS):
                    violations.append(f"plan entry status={entry['status']!r}")

    if checked == 0:
        pytest.skip("no tool_call_update.kind/.status or plan entry priority/status observed")
    assert not violations, (
        f"open-enum value(s) that are neither a defined constant nor `_`-prefixed: {violations!r}"
    )


@pytest.mark.requirement("ACP-ENUM-202")
@pytest.mark.capability("capabilities.session")
async def test_no_dedicated_prose_open_enum_sites_are_defined_or_underscore_prefixed(
    agent_launch, tmp_path
):
    """ACP-ENUM-202 (ADVISORY -- registry `capability=None`; test still capability-gated for the
    SKIP). `session/update`'s own `sessionUpdate` discriminator, `state_update.state`, and
    `tool_call_update`/`tool_call_content_chunk`'s `content[*].type` are each a defined constant
    or begin with `_`, even though no per-site prose individually restates the generic rule for
    these three."""
    turn = await _drive_one_turn(agent_launch, tmp_path)
    updates = _update_dicts(turn)

    checked = 0
    violations: list[str] = []

    for update in updates:
        kind = update.get("sessionUpdate")
        if kind is None:
            continue
        checked += 1
        if not is_valid_open_enum_value(kind, SESSION_UPDATE_KIND):
            violations.append(f"sessionUpdate={kind!r}")
        if kind == "state_update" and "state" in update:
            checked += 1
            if not is_valid_open_enum_value(update["state"], STATE_UPDATE_STATE):
                violations.append(f"state_update.state={update['state']!r}")
        if kind in ("tool_call_update", "tool_call_content_chunk"):
            content = update.get("content")
            for block in content or []:
                if isinstance(block, dict) and "type" in block:
                    checked += 1
                    if not is_valid_open_enum_value(block["type"], TOOL_CALL_CONTENT_TYPE):
                        violations.append(f"tool call content type={block['type']!r}")

    if checked == 0:
        pytest.skip("no session/update observed during this turn")
    assert not violations, (
        f"open-enum value(s) that are neither a defined constant nor `_`-prefixed: {violations!r}"
    )


@pytest.mark.requirement("ACP-ENUM-203")
@pytest.mark.capability("capabilities.session")
async def test_agent_tolerates_underscore_prefixed_permission_outcome(agent_launch, tmp_path):
    """ACP-ENUM-203 (ADVISORY -- registry `capability=None`; test still capability-gated for the
    SKIP). Answers a `session/request_permission` with a `_`-prefixed, non-standard `outcome`
    value instead of `selected`/`cancelled`; the agent must not crash or answer the *prompt*
    itself with `-32602` (Invalid params) -- it may treat the unrecognised outcome however it
    likes internally (untestable, B4/B6), but the connection and the turn must survive it.

    `run_prompt()` always answers with `selected`/`cancelled`, with no hook to override the
    outcome value, so this drives a minimal turn by hand instead."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        prompt_id = await agent.send_request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": _PROMPT_TEXT}]},
        )

        permission_seen = False
        prompt_response = None
        crashed_or_invalid = None
        reached_idle = False
        running_seen = False

        crashed_break = False

        async def _process_message(msg: dict[str, Any]) -> None:
            nonlocal permission_seen, prompt_response, crashed_or_invalid, reached_idle
            nonlocal running_seen, crashed_break

            if entry.matches_id(prompt_id):
                prompt_response = msg
                error = msg.get("error")
                if isinstance(error, dict) and error.get("code") == -32602:
                    crashed_or_invalid = error
                    crashed_break = True
                return

            method = msg.get("method")
            if method == "session/request_permission" and "id" in msg:
                permission_seen = True
                await agent.send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "result": {"outcome": {"outcome": "_tck/unknown"}},
                    }
                )
                return

            if method == "session/update":
                params = msg.get("params") or {}
                update = params.get("update") if isinstance(params, dict) else None
                if isinstance(update, dict) and update.get("sessionUpdate") == "state_update":
                    if update.get("state") == "running":
                        running_seen = True
                    elif update.get("state") == "idle" and (
                        update.get("stopReason") is not None or running_seen
                    ):
                        reached_idle = True
                return

            if method is not None and "id" in msg:
                await agent.send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
                    }
                )

        # `deadline` bounds the *whole* loop below, not each individual read (review-v2-slices-
        # 1b-6 finding 21): an agent that keeps streaming updates, each safely within
        # `agent_launch.default_timeout` of the last, but never actually reaches a terminating
        # idle, would otherwise let this loop run arbitrarily long since a fresh per-read
        # deadline never itself expires.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + agent_launch.default_timeout
        try:
            while not reached_idle and not crashed_break:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise AgentTimeout(
                        "never reached a terminating idle state_update after a `_`-prefixed "
                        f"permission outcome within {agent_launch.default_timeout}s",
                        agent.transcript,
                        stderr=agent.stderr_text(),
                    )
                entry = await agent.read_line(timeout=remaining)
                raw = entry.parsed
                # A line may itself be a JSON-RPC batch array (`ACP-BATCH-207` permits an agent
                # to spontaneously emit a batch of `session/update` notifications) -- unwrap it
                # the same way `_helpers.run_prompt`'s `_handle_one` does, so a batching but
                # otherwise conformant agent (`emits_batch_updates.py`) doesn't spuriously FAIL
                # this test just because its terminating idle arrived inside a batch.
                if isinstance(raw, list):
                    items = [item for item in raw if isinstance(item, dict)]
                elif isinstance(raw, dict):
                    items = [raw]
                else:
                    continue
                for msg in items:
                    entry = replace(entry, parsed=msg)
                    await _process_message(msg)
                    if reached_idle or crashed_break:
                        break
        except (AgentTimeout, AgentExited):
            pass  # judged below: absence of a crash signal is not itself proof of tolerance

    if not permission_seen:
        pytest.skip("no permission request observed during this turn")
    assert crashed_or_invalid is None, (
        f"agent answered the prompt with -32602 after receiving a `_`-prefixed, non-standard "
        f"permission outcome: {crashed_or_invalid!r}"
    )
    assert reached_idle, (
        f"agent never reached a terminating idle state_update after a `_`-prefixed permission "
        f"outcome was returned; last prompt response seen: {prompt_response!r}"
    )
