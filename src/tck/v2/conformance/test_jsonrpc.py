"""JSON-RPC envelope conformance: ACP-JSONRPC-001..005.

v2 counterpart of `tck.v1.conformance.test_jsonrpc` (honest duplication, not shared machinery).
Per `tck.v2.requirements`, all five ids reuse their v1 wire assertions unchanged, widened only to
also cover a batch-delivered response/notification/erroneous-request -- but this file's own
probes are single-message only. That batch half of the evidence lives entirely in
`test_batch.py` (`@pytest.mark.requirement(...)` markers in both files jointly satisfy each id);
see its `test_batch_of_requests_replies_with_matching_responses`,
`test_notification_only_batch_gets_no_reply`, and
`test_invalid_batch_entries_get_per_entry_invalid_request`.

No row here needs `skip_if_version_mismatch`: a v1-only agent never receives a batch-shaped probe
in this file, and its single-message replies are judged by the same rule v1 already holds it to.

The unknown-method probe is `_tck/does_not_exist` -- `_`-prefixed per the extensibility rule
(mirrors v1's `test_jsonrpc.py`).
"""

from __future__ import annotations

import contextlib

import pytest

from tck.common.harness import AgentTimeout
from tck.v2 import SPEC
from tck.v2.protocol import METHOD_NOT_FOUND
from tck.v2.validation import validate_response_envelope

from ._helpers import connected_agent, first_response_within, new_session, quiet_period


@pytest.mark.requirement("ACP-JSONRPC-001")
async def test_id_is_echoed_for_integer_and_string_ids(agent_launch, tmp_path):
    """ACP-JSONRPC-001. Only ever sends one `initialize` per connection (a second `initialize` on
    an already-initialized connection is unspecified). The integer-id half uses `initialize`
    itself (a request every agent MUST answer); the string-id half hand-rolls its own
    `session/new` request -- id echo holds even for an error reply, so there is nothing here for
    an auth-gated or otherwise erroring agent to break."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        int_id = await agent.send_request("initialize", SPEC.initialize_params(), id=424242)
        int_entry = await agent.wait_for_response(int_id, timeout=agent_launch.default_timeout)
        assert int_entry.parsed["id"] == 424242, f"integer id not echoed: {int_entry.parsed!r}"

        req_id = await agent.send_request("session/new", {"cwd": str(tmp_path)}, id="tck-string-id")
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        assert entry.parsed["id"] == "tck-string-id", f"string id not echoed: {entry.parsed!r}"


def _assert_valid_response_envelope(entry, *, what: str) -> None:
    msg = entry.parsed
    assert isinstance(msg, dict), f"{what} did not parse to a JSON object: {entry.raw!r}"
    issues = validate_response_envelope(msg)
    assert not issues, f"{what} response envelope is invalid: {issues!r} ({msg!r})"


@pytest.mark.requirement("ACP-JSONRPC-002")
async def test_response_envelope_is_result_xor_error_with_valid_shape(agent_launch):
    """ACP-JSONRPC-002. Evidence comes only from responses that MUST exist -- `initialize`'s own
    response, and the response to a deliberately invalid-params request (`session/new` missing
    the required `cwd`) -- never from a reply to an unrecognised method, since replying to that
    at all is only SHOULD (see `ACP-JSONRPC-004`). Does not assert which error code either
    response uses, only that the envelope is well-formed."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", SPEC.initialize_params())
        init_entry = await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)
        _assert_valid_response_envelope(init_entry, what="initialize")

        bad_id = await agent.send_request("session/new", {})  # missing required cwd
        bad_entry = await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)
        _assert_valid_response_envelope(bad_entry, what="session/new (missing cwd)")


@pytest.mark.requirement("ACP-JSONRPC-003")
async def test_notification_receives_no_response(agent_launch, tmp_path):
    """ACP-JSONRPC-003. `session/cancel` with no prompt in flight is a pure notification. Checks
    every message inside a batch-array line too, not just a bare object line: an agent that
    folds a spurious response into a batch alongside something else would otherwise pass this
    MANDATORY check by accident. Only a reply fails this (`_helpers.is_response_line`), not the
    agent's own notifications or requests."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        await agent.send_notification("session/cancel", {"sessionId": session_id})

        entry = await first_response_within(agent, quiet_period(agent_launch.default_timeout))
        assert entry is None, f"agent replied to a notification: {entry.text!r}"


@pytest.mark.requirement("ACP-JSONRPC-004")
async def test_unknown_method_yields_method_not_found(agent_launch):
    """ACP-JSONRPC-004 (ADVISORY -- spec wording is still "should"). Only concerns the specific
    `-32601` code once a reply exists, so an agent that never replies SKIPs this check instead of
    failing it."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("_tck/does_not_exist")
        try:
            entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        except AgentTimeout:
            pytest.skip("agent never replied to the unknown method (replying is only SHOULD)")
        error = entry.parsed.get("error") if isinstance(entry.parsed, dict) else None
        assert error is not None, f"expected an error response, got {entry.parsed!r}"
        assert error.get("code") == METHOD_NOT_FOUND, f"expected -32601, got {error.get('code')!r}"


@pytest.mark.requirement("ACP-JSONRPC-005")
async def test_connection_survives_an_erroneous_request(agent_launch, tmp_path):
    """ACP-JSONRPC-005 (ADVISORY). Replying to `_tck/does_not_exist` at all is only SHOULD (see
    `ACP-JSONRPC-004`), so silence isn't a failure here -- it already demonstrates the connection
    survived, which is why the reply wait is bounded by `quiet_period()` and a timeout is
    suppressed rather than propagated."""
    async with connected_agent(agent_launch) as agent:
        bad_id = await agent.send_request("_tck/does_not_exist")
        with contextlib.suppress(AgentTimeout):
            await agent.wait_for_response(bad_id, timeout=quiet_period(agent_launch.default_timeout))

        # `new_session` itself asserts the response's shape and a non-empty `sessionId` --
        # the real, failable check that the connection survived; nothing further to check here.
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
