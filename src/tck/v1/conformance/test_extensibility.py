"""Extensibility conformance: ACP-EXT-001, ACP-META-001, ACP-SCHEMA-002 (Reqs 41, 42, 43)."""

from __future__ import annotations

from typing import Any

import pytest

from tck.v1 import validation
from tck.common.harness import AgentExited, AgentTimeout, Direction
from tck.v1.protocol import STOP_REASONS

from ._helpers import connected_agent, new_session, run_prompt


@pytest.mark.requirement("ACP-EXT-001")
async def test_unknown_custom_method_receives_a_response(agent_launch):
    """ACP-EXT-001 (MANDATORY, judgment call -- see `tck.v1.requirements` for the rationale): Req
    42's "recipients must respond to custom requests" (extensibility.mdx:43,52,65,109) is
    phrased as a MUST, distinct from the separate SHOULD about which specific error *code* an
    unrecognised method gets in general (extensibility.mdx:80-92, ACP-JSONRPC-004). This test
    only asserts that *some* response -- a result, or an error with any code -- arrives at all
    for a `_`-prefixed custom method; the `-32601` code specifically remains ACP-JSONRPC-004's
    ADVISORY concern and is not re-checked here.

    An agent that never replies at all is caught explicitly (rather than letting
    `wait_for_response` raise a bare `AgentTimeout`/`AgentExited`) so this -- the one MANDATORY
    assertion in the module -- fails with the Req-42 wording, not a harness exception
    (review-slices-7.md N7)."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("_tck/unknown")
        try:
            entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        except (AgentTimeout, AgentExited) as exc:
            pytest.fail(
                f"a `_`-prefixed custom method request must receive a response (Req 42): {exc}",
                pytrace=False,
            )
        msg = entry.parsed
        assert isinstance(msg, dict) and ("result" in msg or "error" in msg), (
            f"a `_`-prefixed custom method request must receive a response (Req 42), got {msg!r}"
        )


@pytest.mark.requirement("ACP-META-001")
async def test_prompt_meta_field_is_accepted(agent_launch, tmp_path):
    """ACP-META-001 (ADVISORY; Reqs 41, 43). A `session/prompt` carrying `_meta` with a
    `traceparent` key (SHOULD-reserved by Req 43) is accepted and resolves normally -- proves
    the agent does not choke on `_meta` placed exactly where the spec says custom data
    belongs."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello"}],
            extra_params={
                "_meta": {
                    "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
                    "tck": True,
                }
            },
            timeout=agent_launch.default_timeout,
        )

    msg = turn.response_entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"a session/prompt carrying _meta must still resolve normally: {turn.response_entry.text!r}"
    )
    stop_reason = msg["result"].get("stopReason")
    assert stop_reason in STOP_REASONS, f"unexpected stopReason with _meta present: {stop_reason!r}"


@pytest.mark.requirement("ACP-SCHEMA-002")
async def test_full_exchange_has_no_unknown_root_keys(agent_launch, tmp_path):
    """ACP-SCHEMA-002 (ADVISORY; Req 41 -- implementations MUST NOT add custom root fields to a
    spec type, `_meta` is for custom data instead). The vendored schema has no
    `additionalProperties: false` anywhere (`.agents/plan.md` "Open questions"), so mandatory
    schema validation (ACP-SCHEMA-001) cannot catch this on its own --
    `validation.find_unknown_root_keys` implements the comparison by hand: for every
    agent-emitted request/notification `params` and every successful response `result`,
    resolve the full property-name union of its `$def` (following `allOf`/`anyOf`/`oneOf`/
    `$ref`) and flag any key not in that union. Swept over the same
    initialize -> session/new -> session/prompt exchange ACP-SCHEMA-001 validates, using the
    same "derive `method_by_id` from the SENT transcript" trick as
    `test_initialize.py::test_full_exchange_validates_against_schema`."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello"}],
            timeout=agent_launch.default_timeout,
        )

    method_by_id: dict[Any, str] = {}
    for entry in agent.transcript:
        msg = entry.parsed
        if entry.direction is Direction.SENT and isinstance(msg, dict) and "method" in msg and "id" in msg:
            method_by_id[msg["id"]] = msg["method"]

    response_defs = validation._response_method_defs()
    request_and_notification_defs = validation._request_and_notification_method_defs()

    unknown: list[str] = []
    for entry in agent.transcript:
        if entry.direction is not Direction.RECEIVED:
            continue
        msg = entry.parsed
        if not isinstance(msg, dict):
            continue

        method = msg.get("method")
        if isinstance(method, str):
            if method.startswith("_"):
                continue  # extension methods carry no fixed shape by design
            def_name = request_and_notification_defs.get(method)
            if def_name is not None:
                extras = validation.find_unknown_root_keys(def_name, msg.get("params"))
                if extras:
                    unknown.append(f"{method} params: {extras}")
            continue

        if "result" in msg:
            response_method = method_by_id.get(msg.get("id"))
            def_name = response_defs.get(response_method) if response_method is not None else None
            if def_name is not None:
                extras = validation.find_unknown_root_keys(def_name, msg.get("result"))
                if extras:
                    unknown.append(f"{response_method} result: {extras}")

    assert not unknown, f"unknown root-level key(s) found (Req 41): {unknown!r}"
