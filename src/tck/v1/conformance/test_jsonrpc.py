"""JSON-RPC envelope conformance: ACP-JSONRPC-001..005.

Separate from `test_transport.py`/`test_initialize.py` to keep the "jsonrpc:" group of
assertions in one focused file.

The TCK's own probe method, `_tck/does_not_exist`, is `_`-prefixed because the spec requires
custom methods to be (`docs/protocol/v1/extensibility.mdx`) -- the TCK holds its own probe
traffic to the same rule it enforces on agents.
"""

from __future__ import annotations

import contextlib

import pytest

from tck.common.harness import AgentTimeout
from tck.v1.protocol import METHOD_NOT_FOUND, PROTOCOL_VERSION
from tck.v1.validation import validate_response_envelope

from ._helpers import connected_agent, new_session, quiet_period


@pytest.mark.requirement("ACP-JSONRPC-001")
async def test_id_is_echoed_for_integer_and_string_ids(agent_launch, tmp_path):
    """ACP-JSONRPC-001.

    Only ever sends one `initialize` per connection: a second one is unspecified in v1 and a
    strict agent may reject it with `-32600`, falsely FAILing an agent that echoes ids fine.
    The string-id half hand-rolls `session/new` instead of using `new_session`/
    `skip_if_auth_gated` -- id echo holds even for a `-32000` (auth-required) reply, so an
    auth-gated agent has nothing to break here."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        int_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}},
            id=424242,
        )
        int_entry = await agent.wait_for_response(int_id, timeout=agent_launch.default_timeout)
        assert int_entry.parsed["id"] == 424242, f"integer id not echoed: {int_entry.parsed!r}"

        req_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}, id="tck-string-id"
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        assert entry.parsed["id"] == "tck-string-id", f"string id not echoed: {entry.parsed!r}"


def _assert_valid_response_envelope(entry, *, what: str) -> None:
    msg = entry.parsed
    assert isinstance(msg, dict), f"{what} did not parse to a JSON object: {entry.raw!r}"
    issues = validate_response_envelope(msg)
    assert not issues, f"{what} response envelope is invalid: {issues!r} ({msg!r})"


@pytest.mark.requirement("ACP-JSONRPC-002")
async def test_response_envelope_is_result_xor_error_with_valid_shape(agent_launch):
    """ACP-JSONRPC-002. Uses only responses that MUST exist -- `initialize`, and an
    invalid-params `session/new` (missing `cwd`) -- never a reply to an unrecognised method,
    since replying to that is only SHOULD (see ACP-JSONRPC-004). Checks envelope shape only
    (`id`, `result` xor `error`), not which error code is used.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request(
            "initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}
        )
        init_entry = await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)
        _assert_valid_response_envelope(init_entry, what="initialize")

        bad_id = await agent.send_request("session/new", {"mcpServers": []})  # missing required cwd
        bad_entry = await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)
        _assert_valid_response_envelope(bad_entry, what="session/new (missing cwd)")


@pytest.mark.requirement("ACP-JSONRPC-004")
async def test_unknown_method_yields_method_not_found(agent_launch):
    """ACP-JSONRPC-004 (ADVISORY -- spec wording is "should"). Only concerns the specific
    `-32601` code once a reply exists, so an agent that never replies SKIPs rather than fails --
    whether it must reply *at all* to `_`-prefixed custom methods is the separate, MANDATORY
    concern covered by ACP-EXT-001, which does not skip on silence."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("_tck/does_not_exist")
        try:
            entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        except AgentTimeout:
            pytest.skip("agent never replied to the unknown method (replying is only SHOULD)")
        error = entry.parsed.get("error") if isinstance(entry.parsed, dict) else None
        assert error is not None, f"expected an error response, got {entry.parsed!r}"
        assert error.get("code") == METHOD_NOT_FOUND, f"expected -32601, got {error.get('code')!r}"


@pytest.mark.requirement("ACP-JSONRPC-003")
async def test_notification_receives_no_response(agent_launch, tmp_path):
    """ACP-JSONRPC-003. `session/cancel` with no prompt in flight is a pure notification.

    Also covers a would-be `ACP-CANCEL-003` (cancel itself gets no response) -- no separate id
    was registered since this test already asserts it.

    Uses `new_session()` (not a hand-rolled `session/new`) so it SKIPs via `skip_if_auth_gated`
    instead of crashing with a `KeyError` on an agent that gates `session/new` behind auth."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        await agent.send_notification("session/cancel", {"sessionId": session_id})

        def _is_a_response(entry) -> bool:
            # A line without `method` is a reply of some kind, even a malformed one missing
            # `id`/`result`/`error` -- don't require `id` to be present.
            return isinstance(entry.parsed, dict) and "method" not in entry.parsed

        wait = quiet_period(agent_launch.default_timeout)
        with pytest.raises(AgentTimeout):
            await agent.wait_for_message(_is_a_response, timeout=wait)


@pytest.mark.requirement("ACP-JSONRPC-005")
async def test_connection_survives_an_erroneous_request(agent_launch, tmp_path):
    """ACP-JSONRPC-005 (ADVISORY -- see `tck.v1.requirements` for why this isn't MANDATORY).

    Replying to an unrecognised method is only SHOULD (see ACP-JSONRPC-004), so silence on
    `_tck/does_not_exist` already demonstrates the property this test checks (the connection
    survives). The wait for that reply is bounded by `quiet_period()` with the timeout
    suppressed, not propagated -- an unguarded `wait_for_response` would fold legal silence into
    a FAIL and cost a full `--timeout` of dead wall-clock doing it.

    Uses `new_session()` (not a hand-rolled `session/new`) so it SKIPs via `skip_if_auth_gated`
    instead of failing on an agent that gates `session/new` behind auth."""
    async with connected_agent(agent_launch) as agent:
        bad_id = await agent.send_request("_tck/does_not_exist")
        with contextlib.suppress(AgentTimeout):
            await agent.wait_for_response(bad_id, timeout=quiet_period(agent_launch.default_timeout))

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert isinstance(session_id, str)
