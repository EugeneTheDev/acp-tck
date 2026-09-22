"""Extensibility conformance: `ACP-EXT-001` (re-cited, unchanged), `ACP-META-001` (re-cited,
unchanged), `ACP-SCHEMA-002` (re-cited, v2 carve-out already implemented in
`tck.v2.validation.find_unknown_root_keys`), and the new hygiene rows `ACP-META-201`,
`ACP-EXT-201`, `ACP-EXT-202`, `ACP-EXT-203`
(`.agents/research/acp-v2-patches-enums-extensibility.md` "Extensibility / hygiene" +
"New hygiene rows").

`ACP-EXT-001`/`ACP-META-001` are connection-level rows whose registry entries keep
`capability=None` exactly as their v1 originals (`.agents/research/...` table: "re-cite only",
"unchanged") -- `ACP-META-001`'s own test still carries `@pytest.mark.capability(
"capabilities.session")` for its SKIP gate, since it drives an actual `session/prompt` turn.
`ACP-EXT-201`/`ACP-EXT-203` need only one ordinary notification exchange to probe, and
`ACP-EXT-202` only needs `initialize`'s own result -- none of the three drive a turn, so none
carries a capability marker.

`ACP-META-201` and `ACP-SCHEMA-002` both sweep an entire `session/new` + `session/prompt`
exchange (the former for every `_meta` value in the transcript, the latter for unknown root
keys), so both need the same `@pytest.mark.capability("capabilities.session")` marker as any
other turn-driving test -- registry `capability` stays `None` for both (re-cited
unchanged for `ACP-SCHEMA-002`; not promoted for `ACP-META-201`, per the "v2 tiering rule for
session-baseline rows"), but the *test* still needs the marker so the autouse version-mismatch/
capability gate skips it cleanly instead of driving `run_prompt` against an agent that never
advertised (or never negotiated) session support at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from tck.common.harness import AgentExited, AgentTimeout, Direction
from tck.v2 import SPEC, validation
from tck.v2.protocol import STOP_REASONS

from ._helpers import connected_agent, login_if_needed, new_session, quiet_period, run_prompt

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
    """ACP-META-001 (ADVISORY, re-cited from v1 unchanged -- `_meta` on `session/prompt` params
    still exists, `PromptRequest._meta`). A `session/prompt` carrying `_meta` with a
    `traceparent` key is accepted and the turn still reaches a terminating idle with a legal
    `stopReason` (v2's response is only an acceptance receipt, so this checks the *turn*, not the
    response, unlike v1's version of this test)."""
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
    assert turn.stop_reason in STOP_REASONS or (
        isinstance(turn.stop_reason, str) and turn.stop_reason.startswith("_")
    ), f"unexpected stopReason with _meta present: {turn.stop_reason!r}"


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
    produces no response line and no crash (SHOULD-ignore,
    `docs/protocol/v2/extensibility.mdx:109`) -- the v2 analogue of v1's
    `answers_notifications.py` defect pattern, generalised to any custom notification rather
    than specifically `session/cancel`."""
    async with connected_agent(agent_launch) as agent:
        await agent.send_notification("_tck/ping", {"hello": "world"})
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
        except AgentTimeout:
            return  # silence -- exactly what SHOULD-ignore predicts
        except AgentExited:
            pytest.fail("agent exited after receiving an unrecognized custom notification")
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
    whole-response root-level check `ACP-SCHEMA-002` already performs."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request("initialize", SPEC.initialize_params())
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.startup_timeout)
        await login_if_needed(agent, timeout=agent_launch.startup_timeout)

    msg = entry.parsed
    if not (isinstance(msg, dict) and isinstance(msg.get("result"), dict)):
        pytest.skip("initialize did not succeed; nothing to check here (ACP-INIT-001 owns this)")
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
    only records what happens, never asserts)."""
    async with connected_agent(agent_launch) as agent:
        await agent.send_notification("$/does_not_exist", {})
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
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
    test: derive `method_by_id` from the SENT transcript to resolve each response's own method."""
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
