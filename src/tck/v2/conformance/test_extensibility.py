"""Extensibility conformance: `ACP-EXT-001`, `ACP-META-001`, `ACP-SCHEMA-002` (re-cited from v1,
unchanged) plus new hygiene rows `ACP-META-201`, `ACP-EXT-201`, `ACP-EXT-202`, `ACP-EXT-203`.

`ACP-EXT-001`/`ACP-META-001` are connection-level rows with `capability=None`, matching their v1
registry entries; `ACP-META-001`'s test still carries the `capabilities.session` marker since it
drives an actual `session/prompt` turn. `ACP-EXT-201`/`ACP-EXT-203` need only one notification
exchange to probe, and `ACP-EXT-202` only `initialize`'s own result -- none of the three drive a
turn, so none carries a capability marker.

`ACP-META-201` and `ACP-SCHEMA-002` each sweep a full `session/new` + `session/prompt` exchange,
so both tests carry `@pytest.mark.capability("capabilities.session")` even though registry
`capability` stays `None` for both -- the marker only exists so the autouse skip gate doesn't run
them against an agent that never negotiated session support.
"""

from __future__ import annotations

from typing import Any

import pytest

from tck.common.harness import AgentExited, AgentTimeout, Direction
from tck.v2 import SPEC, validation

from ._helpers import (
    connected_agent,
    first_response_within,
    is_response_line,
    iter_messages,
    new_session,
    quiet_period,
    run_prompt,
    skip_if_version_mismatch,
)

_PROMPT_TEXT = "hi"


@pytest.mark.requirement("ACP-EXT-001")
async def test_unknown_custom_method_receives_a_response(agent_launch):
    """ACP-EXT-001 (MANDATORY, re-cited from v1 unchanged --
    `docs/protocol/v2/extensibility.mdx:43,52,65,109`). *Some* response -- a result, or an error
    with any code -- must arrive for a `_`-prefixed custom method; the `-32601` code specifically
    remains `ACP-JSONRPC-004`'s ADVISORY concern, not re-checked here."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("_tck/unknown")
        try:
            entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        except (AgentTimeout, AgentExited) as exc:
            pytest.fail(
                f"a `_`-prefixed custom method request must receive a response: {exc}",
                pytrace=False,
            )
        msg = entry.parsed
        assert isinstance(msg, dict) and ("result" in msg or "error" in msg), (
            f"a `_`-prefixed custom method request must receive a response, got {msg!r}"
        )


@pytest.mark.requirement("ACP-META-001")
@pytest.mark.capability("capabilities.session")
async def test_meta_field_on_prompt_is_accepted(agent_launch, tmp_path):
    """ACP-META-001 (ADVISORY, re-cited from v1 unchanged). A `session/prompt` carrying `_meta`
    is still accepted (a normal acceptance receipt arrives) and the turn still reaches a
    terminating idle `state_update` -- v2's response is only an acceptance receipt, so this
    checks the *turn*, not the response, unlike v1's version. Does not check the stopReason's
    validity; that's `ACP-STATE-203`'s unconditional concern."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            extra_params={
                "_meta": {
                    "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
                    "tck": True,
                }
            },
            timeout=agent_launch.default_timeout,
        )

    assert turn.message_id, (
        f"a session/prompt carrying _meta must still receive a normal acceptance receipt: "
        f"{turn.response_entry.text!r}"
    )
    assert turn.idle_update is not None, (
        "a session/prompt carrying _meta must still reach a terminating idle state_update"
    )


@pytest.mark.requirement("ACP-META-201")
@pytest.mark.capability("capabilities.session")
async def test_emitted_meta_is_object_or_null(agent_launch, tmp_path):
    """ACP-META-201 (ADVISORY, new). Every `_meta` the agent emits, anywhere in the transcript,
    is a JSON object or `null` -- never a string/array/number (all 106 `_meta` sites in the
    schema are typed `["object", "null"]`, e.g. `schema/v2/schema.json:4289-4295`)."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )

    violations: list[Any] = []

    def _scan(node: Any) -> None:
        if isinstance(node, dict):
            if "_meta" in node and node["_meta"] is not None and not isinstance(node["_meta"], dict):
                violations.append(node["_meta"])
            for value in node.values():
                _scan(value)
        elif isinstance(node, list):
            for item in node:
                _scan(item)

    for entry in agent.transcript:
        if entry.direction is Direction.RECEIVED and isinstance(entry.parsed, (dict, list)):
            _scan(entry.parsed)

    assert not violations, f"_meta value(s) that are not an object or null: {violations!r}"


@pytest.mark.requirement("ACP-EXT-201")
async def test_unrecognized_custom_notification_produces_no_response(agent_launch):
    """ACP-EXT-201 (ADVISORY). An unrecognized `_`-prefixed *notification* sent to the agent
    produces no response and no crash (SHOULD-ignore, `docs/protocol/v2/extensibility.mdx:109`)
    -- the v2 analogue of v1's `answers_notifications.py` defect pattern, generalised to any
    custom notification rather than specifically `session/cancel`. Only a reply fails this
    (`_helpers.is_response_line`), not the agent's own notifications or requests."""
    async with connected_agent(agent_launch) as agent:
        await agent.send_notification("_tck/ping", {"hello": "world"})
        try:
            entry = await first_response_within(agent, quiet_period(agent_launch.default_timeout))
        except AgentExited:
            pytest.fail("agent exited after receiving an unrecognized custom notification")
        if entry is None:
            return  # no reply -- exactly what SHOULD-ignore predicts
        pytest.fail(
            f"agent responded to an unrecognized `_`-prefixed notification (should be ignored "
            f"silently): {entry.text!r}"
        )


@pytest.mark.requirement("ACP-EXT-202")
async def test_extensions_are_advertised_under_capabilities_meta(agent_launch):
    """ACP-EXT-202 (ADVISORY). Any vendor extension the agent advertises lives under
    `initialize` -> `result.capabilities._meta`, not as a new root key of `capabilities` itself
    (`docs/protocol/v2/extensibility.mdx:93,126-149`) -- checked via a *nested* application of
    `find_unknown_root_keys` against the `AgentCapabilities` `$def`, rather than the
    whole-response root-level check `ACP-SCHEMA-002` already performs.

    Manual `initialize` (no session follows, so no `login_if_needed` call either -- nothing
    session-dependent comes after it) plus `skip_if_version_mismatch`: `AgentCapabilities`' own
    shape is v2-specific, so a v1-only agent forced under `--protocol-version 2` cannot be
    honestly judged against it."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request("initialize", SPEC.initialize_params())
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.startup_timeout)

    msg = entry.parsed
    if not (isinstance(msg, dict) and isinstance(msg.get("result"), dict)):
        pytest.skip("initialize did not succeed; nothing to check here (ACP-INIT-001 owns this)")
    skip_if_version_mismatch(msg["result"])
    capabilities = msg["result"].get("capabilities")
    if not isinstance(capabilities, dict):
        pytest.skip("initialize result has no capabilities object to check")

    extras = validation.find_unknown_root_keys("AgentCapabilities", capabilities)
    assert not extras, (
        f"initialize result.capabilities has unrecognized root key(s) {extras!r} -- vendor "
        "extensions must be advertised under capabilities._meta instead"
    )


@pytest.mark.requirement("ACP-EXT-203")
async def test_dollar_prefixed_protocol_notification_behaviour(agent_launch, record_property):
    """ACP-EXT-203 (INFORMATIONAL -- the spec explicitly says the agent "is free to ignore" a
    `$/`-prefixed protocol-level notification it does not implement,
    `schema/v2/schema.json:6967-6990`; there is no conforming/non-conforming distinction, so this
    only records what happens, never asserts). Like `ACP-EXT-201`, only a reply counts, not the
    agent's own notifications or requests."""
    async with connected_agent(agent_launch) as agent:
        await agent.send_notification("$/does_not_exist", {})
        try:
            entry = await agent.wait_for_message(
                is_response_line, timeout=quiet_period(agent_launch.default_timeout)
            )
        except AgentTimeout:
            behaviour = "silent (ignored)"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            behaviour = f"replied: {entry.text!r}"

    record_property("behaviour", behaviour)


@pytest.mark.requirement("ACP-SCHEMA-002")
@pytest.mark.capability("capabilities.session")
async def test_full_exchange_has_no_unknown_root_keys(agent_launch, tmp_path):
    """ACP-SCHEMA-002 (ADVISORY, re-cited from v1; needs a v2 carve-out --
    `tck.v2.validation.find_unknown_root_keys` already skips detection for any object matched by
    an open `"other"`-titled fallback branch, since an unknown/`_`-prefixed variant is by
    construction not "a type that's part of the specification",
    `docs/protocol/v2/extensibility.mdx:39`). Swept over an ordinary
    initialize -> session/new -> session/prompt exchange, same trick as v1's version of this
    test: derive `method_by_id` from the SENT transcript to resolve each response's own method.
    Unwraps every transcript line via `iter_messages` rather than requiring
    `isinstance(entry.parsed, dict)`: a message delivered inside a batch-array line must not
    silently escape this scan."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )

    method_by_id: dict[Any, str] = {}
    for entry in agent.transcript:
        if entry.direction is not Direction.SENT:
            continue
        for msg in iter_messages(entry):
            if "method" in msg and "id" in msg:
                method_by_id[msg["id"]] = msg["method"]

    response_defs = validation._response_method_defs()
    request_and_notification_defs = validation._request_and_notification_method_defs()

    unknown: list[str] = []
    for entry in agent.transcript:
        if entry.direction is not Direction.RECEIVED:
            continue
        for msg in iter_messages(entry):
            method = msg.get("method")
            if isinstance(method, str):
                if method.startswith("_") or method.startswith("$/"):
                    continue  # extension/protocol methods carry no fixed shape by design
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

    assert not unknown, f"unknown root-level key(s) found: {unknown!r}"
