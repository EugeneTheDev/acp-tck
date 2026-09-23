"""`initialize` handshake conformance: ACP-INIT-001..004, ACP-SCHEMA-001."""

from __future__ import annotations

from typing import Any

import pytest

from tck.common.harness import Direction
from tck.common.report import current_tck_version
from tck.v1.protocol import PROTOCOL_VERSION
from tck.v1.validation import validate_agent_message, validate_agent_response

from ._helpers import connected_agent, new_session, run_prompt, skip_if_version_mismatch


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
    """ACP-INIT-002. A single `initialize` requesting v1 cannot distinguish "the agent does not
    support v1" from "the agent supports v1 but echoed a different version" -- the returned
    `protocolVersion` is the only evidence either way, so a non-`1` answer is treated as a
    version mismatch (`skip_if_version_mismatch` SKIPs, which forces
    `Verdict.blocked_by_version_mismatch` and NOT CONFORMANT), not as an echo violation."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])


@pytest.mark.requirement("ACP-INIT-003")
async def test_unsupported_version_still_succeeds(agent_launch):
    """ACP-INIT-003: a successful result with an integer protocolVersion isn't sufficient --
    both `testy` and `examples/echo_agent.py` echo the unsupported requested version (65535)
    verbatim, which the requirement text ("its latest supported version") forbids. Checking
    against a reference point (the same agent's plain v1 answer, ACP-INIT-002) needs two fresh
    processes, one per `initialize` call.

    The rule is `!= 65535 and >= latest_supported`, not equality: an agent may legitimately
    answer higher than its own v1 answer for an unsupported/future version without ever having
    echoed 65535 -- equality would falsely FAIL that agent for a defect it didn't commit.

    The 65535 probe's params also carry a v2-shaped `info` object: a dual-version router agent
    selects v2 for any requested version >= 2, including 65535, and its v2 InitializeRequest
    requires `info`. Without it such an agent would answer -32602 for an unrelated params-shape
    reason -- a false MANDATORY FAIL. Extra keys are harmless for a plain v1 agent (no schema
    here sets `additionalProperties: false`)."""
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
                # v2's InitializeRequest requires `info`; a dual-version router agent needs
                # it to select v2 without rejecting these params (see docstring above).
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
    """ACP-INIT-004 (ADVISORY). `skip_if_version_mismatch` SKIPs if the agent did not actually
    negotiate v1 -- `agentInfo` is a v1 shape expectation, not a negotiation-outcome one."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        agent_info = msg["result"].get("agentInfo")
        assert isinstance(agent_info, dict), "agentInfo is not present in the initialize result"
        assert isinstance(agent_info.get("name"), str), f"agentInfo.name is not a string: {agent_info!r}"
        assert isinstance(agent_info.get("version"), str), f"agentInfo.version is not a string: {agent_info!r}"


@pytest.mark.requirement("ACP-SCHEMA-001")
async def test_full_exchange_validates_against_schema(agent_launch, agent_initialize_result, tmp_path):
    """ACP-SCHEMA-001. Every message the agent emits during initialize -> session/new ->
    session/prompt validates against the vendored v1 schema.

    Driven through `run_prompt` (not a hand-rolled exchange) so a real agent that asks for
    permission or calls `fs/*`/`terminal/*` mid-turn doesn't deadlock this MANDATORY
    requirement. `method_by_id` is derived by scanning the sent transcript for
    `{"method", "id"}` pairs rather than threaded through by hand, keeping this test agnostic
    to how `run_prompt`/`new_session` are implemented.

    Uses `connected_agent`'s default `handshake=True` so its auto-`authenticate` step (when
    `--tck-auth-method` is given) runs before `session/new` -- an agent gating `session/new`
    behind authentication mustn't fail this requirement just because the harness never
    authenticated. That traffic is still captured in `agent.transcript` and validated below.

    `connected_agent` doesn't hand back its own `initialize` result, so this reads the
    session-scoped `agent_initialize_result` fixture (same params/command) purely to decide
    whether to `skip_if_version_mismatch` before driving the exchange.
    """
    if agent_initialize_result.result is not None:
        skip_if_version_mismatch(agent_initialize_result.result)
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
