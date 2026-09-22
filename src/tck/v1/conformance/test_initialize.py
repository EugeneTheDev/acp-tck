"""`initialize` handshake conformance: ACP-INIT-001..004, ACP-SCHEMA-001."""

from __future__ import annotations

from typing import Any

import pytest

from tck.common.harness import Direction
from tck.common.report import current_tck_version
from tck.v1.protocol import PROTOCOL_VERSION
from tck.v1.validation import validate_agent_message, validate_agent_response

from ._helpers import connected_agent, new_session, run_prompt


@pytest.mark.requirement("ACP-INIT-001")
async def test_initialize_succeeds_and_validates(agent_launch):
    """ACP-INIT-001."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, f"initialize did not succeed: {msg!r}"

        issues = validate_agent_response("initialize", msg)
        assert not issues, f"initialize result failed schema validation: {issues!r}"

        version = msg["result"].get("protocolVersion")
        assert isinstance(version, int) and not isinstance(version, bool), (
            f"protocolVersion must be an integer, got {version!r}"
        )


@pytest.mark.requirement("ACP-INIT-002")
async def test_requested_v1_is_echoed(agent_launch):
    """ACP-INIT-002."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        version = msg["result"].get("protocolVersion")
        # Req 5: the agent echoes the requested version *only if it supports it*, otherwise it
        # returns its own latest -- for a v1-only TCK requesting v1, "not 1" means the agent
        # does not support protocol v1, not that it violated an echo rule.
        assert version == 1, f"agent does not support protocol v1 (returned {version!r} instead)"


@pytest.mark.requirement("ACP-INIT-003")
async def test_unsupported_version_still_succeeds(agent_launch):
    """ACP-INIT-003, strengthened per `.agents/research/testy-cross-check.md` finding 1: the
    previous version of this test only asserted "a successful result with an integer
    protocolVersion", which both `testy` and `examples/echo_agent.py` PASS despite echoing the
    client's unsupported requested version (65535) verbatim -- a false negative. The
    requirement text says the agent returns "its latest supported version", so this needs a
    reference point: whatever the same agent returns for a plain v1 request (ACP-INIT-002).

    The rule is `!= 65535 and >= latest_supported`, NOT equality: an agent legitimately
    supporting more than one version may answer `1` for a v1 request but
    something higher for an unsupported/future one (e.g. `2` for anything `>= 2`) -- equality
    would falsely FAIL that agent even though it never echoed 65535 and never answered *lower*
    than its own v1 answer, which is the actual defect this requirement exists to catch.

    Two fresh processes are used (one per `initialize` call) rather than two handshakes over one
    connection, matching every other test's "one fresh agent process" pattern.

    The 65535 probe's params also carry a v2-shaped `info` object alongside the ordinary v1
    fields (`.agents/research/acp-v2-version-negotiation.md`, "Router trap for the TCK"): a
    dual-version *router* agent (both reference SDKs ship one) selects v2 for any
    requested version `>= 2`, including 65535, and validates the params as a v2
    `InitializeRequest`, whose `info` is REQUIRED. Without it, such an agent legitimately
    answers `-32602` for a params-shape reason that has nothing to do with version negotiation
    -- a false MANDATORY FAIL. The probe represents a future-version client, so it legitimately
    carries every version's required client fields; extra keys are harmless for a plain v1
    agent (no schema anywhere sets `additionalProperties: false`, per
    `tck.v1.validation`'s documented quirks)."""
    async with connected_agent(agent_launch, handshake=False) as reference_agent:
        v1_req_id = await reference_agent.send_request(
            "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
        )
        v1_entry = await reference_agent.wait_for_response(
            v1_req_id, timeout=agent_launch.default_timeout
        )
        v1_msg = v1_entry.parsed
        assert isinstance(v1_msg, dict) and isinstance(v1_msg.get("result"), dict), (
            f"initialize(protocolVersion=1) did not return a result object: {v1_entry.text!r}"
        )
        latest_supported = v1_msg["result"].get("protocolVersion")

    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {
                "protocolVersion": 65535,
                "clientCapabilities": {},
                # This probe represents a future-version client, so its params legitimately
                # carry every version's required client fields -- including v2's REQUIRED
                # `info` object (see the module-level docstring above and
                # `.agents/research/acp-v2-version-negotiation.md`). A plain v1 agent ignores
                # the extra key; a dual-version router agent needs it to select v2 without
                # rejecting the params as invalid.
                "info": {"name": "acp-tck", "version": current_tck_version()},
            },
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"an unsupported version must still yield a successful result, got {msg!r}"
        )
        version = msg["result"].get("protocolVersion")
        assert isinstance(version, int) and not isinstance(version, bool), (
            f"protocolVersion must be an integer, got {version!r}"
        )
        assert version != 65535, (
            "protocolVersion must not echo the client's unsupported requested version "
            "verbatim -- it must be the agent's own latest supported version"
        )
        assert isinstance(latest_supported, int) and not isinstance(latest_supported, bool), (
            f"reference agent's v1 protocolVersion is not an integer: {latest_supported!r}"
        )
        assert version >= latest_supported, (
            f"protocolVersion for an unsupported request ({version!r}) must be at least the "
            f"version the same agent returns for a v1 request ({latest_supported!r}) -- "
            "an agent answering lower than its own v1 answer is not returning its latest "
            "supported version"
        )


@pytest.mark.requirement("ACP-INIT-004")
async def test_agent_info_present(agent_launch):
    """ACP-INIT-004 (ADVISORY)."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        agent_info = msg["result"].get("agentInfo")
        assert isinstance(agent_info, dict), "agentInfo is not present in the initialize result"
        assert isinstance(agent_info.get("name"), str), f"agentInfo.name is not a string: {agent_info!r}"
        assert isinstance(agent_info.get("version"), str), f"agentInfo.version is not a string: {agent_info!r}"


@pytest.mark.requirement("ACP-SCHEMA-001")
async def test_full_exchange_validates_against_schema(agent_launch, tmp_path):
    """ACP-SCHEMA-001. Every message the agent emits during initialize -> session/new ->
    session/prompt validates against the vendored v1 schema.

    Driven through `run_prompt`: a real agent that asks for permission or calls
    `fs/*`/`terminal/*` mid-turn must not deadlock this MANDATORY requirement just because
    nothing here answers it. `method_by_id` -- needed to know which method's response schema
    each reply must validate against -- is derived automatically by scanning the SENT
    transcript for `{"method", "id"}` pairs rather than threading it through the helpers by
    hand, so this test stays agnostic to how `run_prompt`/`new_session` are implemented.

    Uses `connected_agent`'s default `handshake=True` (not a hand-rolled `initialize` call like
    the other tests in this module) specifically so its built-in auto-`authenticate` step (when
    `--tck-auth-method` is given) runs before `session/new` -- an agent that gates `session/new`
    behind authentication must not fail this MANDATORY requirement just because the harness
    never authenticated. The `initialize` (and, if it ran, `authenticate`) traffic is still
    present in `agent.transcript` and still schema-validated below, exactly as if this test had
    sent it by hand.
    """
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

    received = [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]

    issues = []
    for entry in received:
        msg = entry.parsed
        assert isinstance(msg, dict), f"non-object line from the agent: {entry.raw!r}"
        if "method" in msg:
            issues.extend(validate_agent_message(msg))
            continue
        method = method_by_id.get(msg.get("id"))
        if method is not None:
            issues.extend(validate_agent_response(method, msg))
        else:
            issues.extend(validate_agent_message(msg))

    assert not issues, f"schema violations in agent output: {issues!r}"
