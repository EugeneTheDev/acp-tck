"""`initialize` handshake conformance: ACP-INIT-001, ACP-INIT-003, ACP-INIT-201..204,
ACP-SCHEMA-001 (see `tck.v2.requirements`'s module docstring for the id-namespacing decisions).
"""

from __future__ import annotations

from typing import Any

from tck.common.harness import Direction
from tck.common.report import current_tck_version
from tck.v2.protocol import PROTOCOL_VERSION
from tck.v2.validation import validate_agent_message, validate_agent_response

import pytest

from ._helpers import connected_agent, login_if_needed, new_session, run_prompt, skip_if_version_mismatch


@pytest.mark.requirement("ACP-INIT-001")
async def test_initialize_succeeds(agent_launch):
    """ACP-INIT-001. Deliberately scoped to the basic handshake sanity check only -- a non-error
    JSON-RPC result. This is judged the same regardless of which `protocolVersion` the agent
    actually negotiates: an agent that honestly negotiates down to a version other than 2 (e.g.
    a v1-only agent answering `1` to a v2 client, per `ACP-INIT-201`'s two-branch rule) still
    MUST answer `initialize` successfully, so this row does not SKIP on a version mismatch the
    way the v2-only shape checks below do. Schema/shape validation of the result -- including
    v2-only requirements like `info` being REQUIRED, capability markers being objects, and the
    negotiated version's own type -- lives in `ACP-SCHEMA-001`/`ACP-INIT-201`/`ACP-INIT-203`/
    `ACP-INIT-204`, all of which are version-mismatch-aware.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, f"initialize did not succeed: {msg!r}"


@pytest.mark.requirement("ACP-INIT-201")
async def test_version_negotiation_follows_the_two_branch_rule(agent_launch):
    """ACP-INIT-201 (initialization.mdx:92-96): "If the Agent supports the requested version, it
    MUST respond with the same version. Otherwise, the Agent MUST respond with the latest
    version it supports."

    Two fresh processes (matching v1 `ACP-INIT-003`'s "one process per initialize call"
    pattern), because a single connection's `initialize` must never be sent twice:

    1. Request the TCK's own latest known version (`PROTOCOL_VERSION`, currently 2) ->
       `version_a`.
    2. Request an absurd version (65535) no real agent implements -> `version_b`. Since no
       agent supports 65535, this call is *always* answered by the rule's "otherwise" branch,
       so `version_b` is always the agent's true own-latest-supported value, regardless of what
       the first call requested.

    The rule then reduces to a single falsifiable check: `version_a` is either exactly the
    requested `PROTOCOL_VERSION` (the agent supports it, "same version" branch), or exactly
    `version_b` (the agent does not support it, and its fallback answer -- self-consistently --
    is the same "own latest" value both unsupported-ish requests must produce). Anything else
    (e.g. blindly echoing whatever was requested, or answering some third, unrelated value)
    violates the rule.
    """
    async with connected_agent(agent_launch, handshake=False) as agent_a:
        req_id = await agent_a.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry_a = await agent_a.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg_a = entry_a.parsed
        assert isinstance(msg_a, dict) and isinstance(msg_a.get("result"), dict), (
            f"initialize(protocolVersion={PROTOCOL_VERSION}) did not return a result object: "
            f"{entry_a.text!r}"
        )
        version_a = msg_a["result"].get("protocolVersion")
        assert isinstance(version_a, int) and not isinstance(version_a, bool), (
            f"protocolVersion must be an integer, got {version_a!r}"
        )

    async with connected_agent(agent_launch, handshake=False) as agent_b:
        req_id = await agent_b.send_request(
            "initialize",
            {"protocolVersion": 65535, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry_b = await agent_b.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg_b = entry_b.parsed
        assert isinstance(msg_b, dict) and "result" in msg_b, (
            f"an unsupported version must still yield a successful result, got {msg_b!r}"
        )
        version_b = msg_b["result"].get("protocolVersion")
        assert isinstance(version_b, int) and not isinstance(version_b, bool), (
            f"protocolVersion must be an integer, got {version_b!r}"
        )
        assert version_b != 65535, (
            "protocolVersion must not echo the client's unsupported requested version "
            "verbatim -- it must be the agent's own latest supported version"
        )

    assert version_a == PROTOCOL_VERSION or version_a == version_b, (
        f"protocolVersion negotiation violated the two-branch rule: requested "
        f"{PROTOCOL_VERSION}, got {version_a!r}, but the agent's own latest supported version "
        f"(from the unsupported-version probe) is {version_b!r} -- {version_a!r} matches "
        "neither"
    )


@pytest.mark.requirement("ACP-INIT-003")
async def test_unsupported_version_still_succeeds(agent_launch):
    """ACP-INIT-003 (reused from v1, re-cited to v2 -- see `tck.v2.requirements`'s module
    docstring). Distinct from `ACP-INIT-201`'s own internal 65535 probe: that test only checks
    the two-branch *shape* of the negotiation rule; this one is the dedicated "must not echo an
    absurd version, and must be at least as high as a known-supported reference answer" probe,
    mirroring v1's `ACP-INIT-003` structure exactly (`tck.v1.conformance.test_initialize`).

    Two fresh processes, one per `initialize` call, matching every other test's "one fresh agent
    process per handshake" pattern.
    """
    async with connected_agent(agent_launch, handshake=False) as reference_agent:
        ref_req_id = await reference_agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        ref_entry = await reference_agent.wait_for_response(
            ref_req_id, timeout=agent_launch.default_timeout
        )
        ref_msg = ref_entry.parsed
        assert isinstance(ref_msg, dict) and isinstance(ref_msg.get("result"), dict), (
            f"initialize(protocolVersion={PROTOCOL_VERSION}) did not return a result object: "
            f"{ref_entry.text!r}"
        )
        latest_supported = ref_msg["result"].get("protocolVersion")
        assert isinstance(latest_supported, int) and not isinstance(latest_supported, bool), (
            f"reference agent's protocolVersion is not an integer: {latest_supported!r}"
        )

    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {
                "protocolVersion": 65535,
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
        assert version >= latest_supported, (
            f"protocolVersion for an unsupported request ({version!r}) must be at least the "
            f"version the same agent returns for a supported request ({latest_supported!r})"
        )


@pytest.mark.requirement("ACP-INIT-202")
async def test_downgrade_request_still_succeeds(agent_launch):
    """ACP-INIT-202. `protocolVersion: 1` requested against a v2 agent must still succeed --
    never a JSON-RPC error -- per the negotiation rule's `N < min(S)` case
    (`.agents/research/acp-v2-version-negotiation.md` requirement 10). The result's
    `protocolVersion` is either the requested `1` (a dual-version agent that still speaks v1) or
    the agent's own latest supported version (`2` for a strict v2-only agent) -- never an error,
    and never any other value.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize", {"protocolVersion": 1, "info": {"name": "acp-tck", "version": "0"}}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            "a downgrade request (protocolVersion: 1) must still succeed, never error, per the "
            f"negotiation rule's N < min(S) case, got {msg!r}"
        )
        version = msg["result"].get("protocolVersion")
        assert version in (1, 2), (
            f"protocolVersion for a downgrade request must be 1 or 2, got {version!r}"
        )


@pytest.mark.requirement("ACP-INIT-203")
async def test_info_is_required_and_well_formed(agent_launch):
    """ACP-INIT-203. `info` is REQUIRED in the v2 `initialize` result (unlike v1's optional
    `agentInfo`), and its `name`/`version` are non-empty strings.

    This is a v2-only shape requirement: an agent that honestly negotiates down to a version
    other than 2 (see `ACP-INIT-201`) never claimed to speak v2 in the first place, so its
    result cannot be judged against v2's own `info` requirement -- `skip_if_version_mismatch`
    SKIPs with the `VERSION-MISMATCH:` marker in that case instead of FAILing.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        info = msg["result"].get("info")
        assert isinstance(info, dict), f"info is required in v2 but missing/not an object: {info!r}"
        name = info.get("name")
        version = info.get("version")
        assert isinstance(name, str) and name, f"info.name must be a non-empty string, got {name!r}"
        assert isinstance(version, str) and version, (
            f"info.version must be a non-empty string, got {version!r}"
        )


@pytest.mark.requirement("ACP-INIT-204")
async def test_capabilities_markers_are_objects_not_booleans(agent_launch):
    """ACP-INIT-204. `capabilities`, when present, is an object whose known nested markers
    (`session`, `auth`) are themselves objects (or absent/`null`) -- never booleans. There are no
    boolean-encoded capabilities anywhere in v2 (`docs/protocol/v2/migration.mdx:181`).

    Also a v2-only shape requirement, so `skip_if_version_mismatch` SKIPs it with the
    `VERSION-MISMATCH:` marker whenever the agent negotiated down to a version other than 2 --
    see `test_info_is_required_and_well_formed` (`ACP-INIT-203`) above for the rationale.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        capabilities = msg["result"].get("capabilities")
        if capabilities is None:
            return
        assert isinstance(capabilities, dict), (
            f"capabilities must be an object when present, got {capabilities!r}"
        )
        for key in ("session", "auth"):
            if key in capabilities and capabilities[key] is not None:
                assert isinstance(capabilities[key], dict) and not isinstance(
                    capabilities[key], bool
                ), (
                    f"capabilities.{key} must be an object marker, never a boolean, got "
                    f"{capabilities[key]!r}"
                )


@pytest.mark.requirement("ACP-SCHEMA-001")
async def test_initialize_exchange_validates_against_schema(agent_launch, tmp_path):
    """ACP-SCHEMA-001. Extends beyond the `initialize` exchange alone to also drive a
    `session/new` + `session/prompt` turn on the same connection (mirrors
    `tck.v1.conformance.test_initialize.test_full_exchange_validates_against_schema`'s "full
    exchange" scope). `method_by_id` is derived by scanning the SENT transcript rather than
    threaded by hand, so it picks up `session/new`/`session/prompt` alongside `initialize` for
    free.

    The session/prompt-turn portion only runs when the negotiated result actually advertises
    `capabilities.session` (an object marker, checked manually here rather than via
    `@pytest.mark.capability(...)` -- this test manages its own connection instead of sharing
    the marker-gated `agent_initialize_result` fixture) -- an agent that never advertises
    `session` support has no `session/new`/`session/prompt` traffic to validate at all, and this
    row still validates whatever the bare `initialize` exchange produced.

    Validating against the *v2* schema is itself a v2-only shape requirement -- a v1-shaped
    result (`agentInfo` instead of `info`, etc.) from an agent that honestly negotiated down to
    a version other than 2 would otherwise misleadingly FAIL here even though the agent simply
    does not speak v2 yet, so `skip_if_version_mismatch` SKIPs with the `VERSION-MISMATCH:`
    marker in that case instead.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])

        capabilities = msg["result"].get("capabilities")
        if isinstance(capabilities, dict) and capabilities.get("session") is not None:
            await login_if_needed(agent, timeout=agent_launch.default_timeout)
            session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
            await run_prompt(
                agent,
                session_id,
                [{"type": "text", "text": "hi"}],
                timeout=agent_launch.default_timeout,
            )

    method_by_id: dict[Any, str] = {}
    for entry in agent.transcript:
        msg = entry.parsed
        if entry.direction is Direction.SENT and isinstance(msg, dict) and "method" in msg and "id" in msg:
            method_by_id[msg["id"]] = msg["method"]

    received = [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]

    # A received line may itself be a JSON-RPC batch array (`ACP-BATCH-207`/`ACP-TRANSPORT-201`
    # both permit an agent to spontaneously batch its own notifications, e.g.
    # `emits_batch_updates.py`) -- flatten to individual message dicts before validating, rather
    # than hard-failing on the first list-shaped line.
    messages: list[dict[str, Any]] = []
    for entry in received:
        msg = entry.parsed
        if isinstance(msg, list):
            for item in msg:
                assert isinstance(item, dict), (
                    f"non-object batch element from the agent: {item!r} in {entry.raw!r}"
                )
                messages.append(item)
        else:
            assert isinstance(msg, dict), f"non-object line from the agent: {entry.raw!r}"
            messages.append(msg)

    issues = []
    for msg in messages:
        if "method" in msg:
            issues.extend(validate_agent_message(msg))
            continue
        method = method_by_id.get(msg.get("id"))
        if method is not None:
            issues.extend(validate_agent_response(method, msg))
        else:
            issues.extend(validate_agent_message(msg))

    assert not issues, f"schema violations in agent output: {issues!r}"
