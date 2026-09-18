"""JSON-RPC envelope conformance: ACP-JSONRPC-001..005.

Not listed by name in the slice-3 task's conformance-tests file list (which named only
`test_transport.py` / `test_initialize.py`), but the task's own bullet points describe a
distinct "jsonrpc:" group of assertions; splitting them into their own module keeps each file
focused on one requirement family. See `AGENTS.md` "How to add a requirement + test".

The TCK's own probe method for "does this agent even reply to something it doesn't recognise"
is `_tck/does_not_exist` -- `_`-prefixed, per Req 42 / J9 ("custom methods must be `_`-prefixed",
`docs/protocol/v1/extensibility.mdx`): the TCK holds agents to that rule, so its own probe
traffic must follow it too (review S3).
"""

from __future__ import annotations

import pytest

from tck.harness import AgentTimeout
from tck.protocol import METHOD_NOT_FOUND, PROTOCOL_VERSION
from tck.validation import validate_response_envelope

from ._helpers import connected_agent, new_session, quiet_period


@pytest.mark.requirement("ACP-JSONRPC-001")
async def test_id_is_echoed_for_integer_and_string_ids(agent_launch):
    """ACP-JSONRPC-001."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        params = {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}

        int_id = await agent.send_request("initialize", params, id=424242)
        int_entry = await agent.wait_for_response(int_id, timeout=agent_launch.default_timeout)
        assert int_entry.parsed["id"] == 424242, f"integer id not echoed: {int_entry.parsed!r}"

        str_id = await agent.send_request("initialize", params, id="tck-string-id")
        str_entry = await agent.wait_for_response(str_id, timeout=agent_launch.default_timeout)
        assert str_entry.parsed["id"] == "tck-string-id", f"string id not echoed: {str_entry.parsed!r}"


def _assert_valid_response_envelope(entry, *, what: str) -> None:
    msg = entry.parsed
    assert isinstance(msg, dict), f"{what} did not parse to a JSON object: {entry.raw!r}"
    issues = validate_response_envelope(msg)
    assert not issues, f"{what} response envelope is invalid: {issues!r} ({msg!r})"


@pytest.mark.requirement("ACP-JSONRPC-002")
async def test_response_envelope_is_result_xor_error_with_valid_shape(agent_launch):
    """ACP-JSONRPC-002. Evidence comes only from responses that MUST exist -- `initialize`'s
    own response, and the response to a deliberately invalid-params request (`session/new`
    missing the required `cwd`) -- never from a reply to an unrecognised method, since replying
    to that at all is only SHOULD (see ACP-JSONRPC-004) (review S3). This does not assert which
    error code either response uses, only that the envelope (`id`, `result` xor `error`, error
    shape) is well-formed.
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
    """ACP-JSONRPC-004 (ADVISORY -- spec wording is "should"). Replying to an unrecognised
    method at all is optional, so an agent that never replies SKIPs this check instead of
    failing it -- only an agent that *does* reply is held to the `-32601` code (review S3)."""
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

    This also stands in for a would-be `ACP-CANCEL-003` ("`session/cancel` itself is a
    notification and receives no response", J2 applied to cancel): the slice-4 task considered
    a dedicated requirement id for that, but it is exactly what this test already asserts, so no
    separate id was registered -- see `.agents/plan.md` slice 4 notes.

    Uses the `new_session()` helper (not a hand-rolled `session/new`) so it SKIPs, via
    `skip_if_auth_gated`, instead of crashing with a `KeyError` on an agent that gates
    `session/new` behind authentication and was run without `--auth-method`."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        await agent.send_notification("session/cancel", {"sessionId": session_id})

        def _is_a_response(entry) -> bool:
            # Any line that is not itself a request/notification (no `method`) is a reply of
            # some kind, even a malformed one missing `id`/`result`/`error` entirely -- treat it
            # as a response candidate rather than requiring `id` to be present (review N16).
            return isinstance(entry.parsed, dict) and "method" not in entry.parsed

        wait = quiet_period(agent_launch.default_timeout)
        with pytest.raises(AgentTimeout):
            await agent.wait_for_message(_is_a_response, timeout=wait)


@pytest.mark.requirement("ACP-JSONRPC-005")
async def test_connection_survives_an_erroneous_request(agent_launch, tmp_path):
    """ACP-JSONRPC-005 (ADVISORY -- see `tck.requirements` for why this isn't MANDATORY).

    Uses the `new_session()` helper (not a hand-rolled `session/new`) so it SKIPs, via
    `skip_if_auth_gated`, instead of failing on an agent that gates `session/new` behind
    authentication and was run without `--auth-method`."""
    async with connected_agent(agent_launch) as agent:
        bad_id = await agent.send_request("_tck/does_not_exist")
        await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert isinstance(session_id, str)
