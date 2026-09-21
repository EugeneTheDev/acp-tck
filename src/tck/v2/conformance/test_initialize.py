"""`initialize` handshake conformance: ACP-INIT-001, ACP-INIT-201 (see `tck.v2.requirements`'s
module docstring for the id-namespacing decision between these two and v1's `ACP-INIT-002/003`).
"""

from __future__ import annotations

from tck.v2.protocol import PROTOCOL_VERSION
from tck.v2.validation import validate_agent_response

import pytest

from ._helpers import connected_agent


@pytest.mark.requirement("ACP-INIT-001")
async def test_initialize_succeeds_and_validates(agent_launch):
    """ACP-INIT-001."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
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
