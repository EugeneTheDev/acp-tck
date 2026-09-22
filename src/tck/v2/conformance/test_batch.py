"""JSON-RPC 2.0 batching (v2 §6, `docs/protocol/v2/transports.mdx`): ACP-BATCH-201..208,
ACP-INFO-BATCH-201/202.

New to v2 -- v1 has no batching at all, so none of these ids reuse a v1 number; there is nothing
to reuse. Tiers are documented in full in `tck.v2.requirements`'s "Batching" module docstring
section; see that docstring for the per-id tiering rationale this file does not repeat.

**Every test here calls `skip_if_version_mismatch` on its own manual `initialize`**, unlike
`test_transport.py`/`test_jsonrpc.py`. Those two files' assertions hold for any agent's ordinary
traffic regardless of negotiated version; batching does not; a v1-only agent forced under
`--protocol-version 2` (per `tck.v1.conformance._base`'s `run()`: a top-level JSON array is
silently dropped, `isinstance(message, dict)` gate, no reply at all) would otherwise time out and
FAIL every MANDATORY row in this file, breaking `tests/v2/test_cli.py`'s
`test_v1_conforming_agent_under_protocol_version_2_is_blocked_by_version_mismatch` invariant
(zero FAILs, full `VERSION-MISMATCH:` coverage for every non-negotiation id). `_v2_only_agent`
below is this file's own copy of `test_initialize.py`'s "manual initialize + skip on mismatch"
pattern -- kept local rather than promoted to `_helpers.py` since only this file's tests need it.

Batch probes each use their own fresh connection (one `_v2_only_agent` per test): a batch line is
exactly the kind of traffic that could crash a less battle-tested agent implementation
(`.agents/research/acp-v2-cancellation-and-batching.md`'s own testability note), and isolating
each probe into its own process means one crash cannot cascade into or pollute a sibling
assertion.
"""

from __future__ import annotations

import contextlib
import json

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v2.protocol import INVALID_REQUEST, PROTOCOL_VERSION

from ._helpers import (
    connected_agent,
    login_if_needed,
    quiet_period,
    skip_if_auth_gated_msg,
    skip_if_version_mismatch,
)


@contextlib.asynccontextmanager
async def _v2_only_agent(agent_launch):
    """Like `test_initialize.py`'s tests: a fresh connection, one manual `initialize`, and a
    `VERSION-MISMATCH:` skip unless the agent actually negotiated v2 -- every batch probe below
    needs the agent to understand v2's own batching rules, which a version-mismatched agent
    never claimed to. Also logs in (`login_if_needed`) when `--auth-method` was given, since this
    manual `initialize` bypasses `connected_agent`'s own auto-login step and at least one batch
    probe (`test_batch_of_requests_replies_with_matching_responses`) sends `session/new` inside
    the batch -- without this, an agent gated behind authentication would answer `-32000` for
    real instead of succeeding."""
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
        await login_if_needed(agent, timeout=agent_launch.default_timeout)
        yield agent


@pytest.mark.requirement("ACP-BATCH-201")
async def test_empty_batch_yields_a_single_invalid_request_object(agent_launch):
    """ACP-BATCH-201 (MANDATORY). An empty array on stdin gets back a single Invalid Request
    (`-32600`) response *object* with `id: null` -- never a response array."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw("[]")
        entry = await agent.read_line(timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict), f"expected a single response object, got {entry.raw!r}"
        assert msg.get("id") is None, f"expected id: null, got {msg.get('id')!r}"
        error = msg.get("error")
        assert isinstance(error, dict), f"expected an error object, got {msg!r}"
        assert error.get("code") == INVALID_REQUEST, f"expected -32600, got {error.get('code')!r}"


@pytest.mark.requirement("ACP-BATCH-202")
async def test_notification_only_batch_produces_no_output(agent_launch):
    """ACP-BATCH-202 (MANDATORY). A batch containing only notifications (no `id` on any entry)
    must not be replied to at all -- not even an empty array."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw(json.dumps([{"jsonrpc": "2.0", "method": "_tck/notify_only"}]))
        wait = quiet_period(agent_launch.default_timeout)
        with pytest.raises(AgentTimeout):
            await agent.read_line(timeout=wait)


async def _collect_flattened_responses(agent, count: int, *, timeout: float) -> list[dict]:
    """Read lines until `count` response objects have been observed, flattening both a
    conforming single response array and a non-conforming agent's separate top-level object
    lines -- this helper's own job is only to gather evidence, not to judge `ACP-BATCH-204`."""
    collected: list[dict] = []
    while len(collected) < count:
        entry = await agent.read_line(timeout=timeout)
        parsed = entry.parsed
        if isinstance(parsed, list):
            collected.extend(parsed)
        elif isinstance(parsed, dict):
            collected.append(parsed)
        else:
            pytest.fail(f"unexpected line while collecting batch responses: {entry.raw!r}")
    return collected


@pytest.mark.requirement("ACP-BATCH-203")
async def test_invalid_batch_entries_get_per_entry_invalid_request(agent_launch):
    """ACP-BATCH-203 (ADVISORY -- report's own text carries no RFC-2119 keyword). A non-empty
    batch mixing one structurally invalid entry (missing `method`) with one well-formed sibling
    produces a per-entry `-32600`/`id: null` for the invalid one, without preventing the valid
    sibling from being processed and replied to normally."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": "tck-invalid-sibling"},  # missing "method"
                    {"jsonrpc": "2.0", "id": "tck-valid-sibling", "method": "_tck/does_not_exist"},
                ]
            )
        )
        responses = await _collect_flattened_responses(
            agent, 2, timeout=agent_launch.default_timeout
        )
        by_id = {response.get("id"): response for response in responses}
        assert None in by_id, f"expected one id: null entry for the invalid sibling: {responses!r}"
        invalid_error = by_id[None].get("error")
        assert isinstance(invalid_error, dict) and invalid_error.get("code") == INVALID_REQUEST, (
            f"invalid sibling did not get -32600: {by_id[None]!r}"
        )
        assert "tck-valid-sibling" in by_id, (
            f"the valid sibling was not processed/replied to: {responses!r}"
        )


@pytest.mark.requirement("ACP-BATCH-204", "ACP-BATCH-205")
async def test_batch_of_requests_replies_with_matching_responses(agent_launch, tmp_path):
    """ACP-BATCH-204/205 (both ADVISORY, shared test -- see `tck.v2.requirements`'s "Batching"
    docstring section for why sharing is safe here: identical wire evidence, neither is the sole
    cause of a failing verdict). `204`: the agent SHOULD reply to a batch containing at least one
    request
    with one array of the corresponding response objects. `205`: responses MAY appear in any
    order; matching is done here by `id`, never by position -- this test's own lookup-by-id
    (rather than assuming array-index correspondence) is exactly the practice `205` calls for,
    regardless of which order the agent's array actually uses."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw(
            json.dumps(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": "tck-batch-session",
                        "method": "session/new",
                        "params": {"cwd": str(tmp_path)},
                    },
                    {"jsonrpc": "2.0", "id": "tck-batch-unknown", "method": "_tck/does_not_exist"},
                ]
            )
        )
        entry = await agent.read_line(timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, list) and len(msg) == 2, (
            f"expected one array with both responses: {entry.raw!r}"
        )
        by_id = {item.get("id"): item for item in msg if isinstance(item, dict)}
        assert "tck-batch-session" in by_id and "tck-batch-unknown" in by_id, (
            f"response array is missing an id: {msg!r}"
        )
        session_response = by_id["tck-batch-session"]
        skip_if_auth_gated_msg(session_response)
        assert isinstance(session_response.get("result"), dict) and isinstance(
            session_response["result"].get("sessionId"), str
        ), f"session/new entry did not resolve to a sessionId, matched by id: {session_response!r}"
        unknown_response = by_id["tck-batch-unknown"]
        assert "error" in unknown_response, (
            f"_tck/does_not_exist entry did not resolve to an error, matched by id: "
            f"{unknown_response!r}"
        )


@pytest.mark.requirement("ACP-BATCH-206")
def test_concurrent_batch_processing_is_unobservable() -> None:
    """ACP-BATCH-206 (ADVISORY, record-only). The receiver MAY process batch entries
    concurrently, in any order, with any parallelism -- no ordering assertion a client-side TCK
    makes could legitimately distinguish conforming concurrent processing from conforming
    sequential processing. Always SKIPped."""
    pytest.skip("record-only: batch-entry processing order/concurrency is not asserted (MAY)")


@pytest.mark.requirement("ACP-BATCH-207")
def test_agent_initiated_batches_cannot_be_forced() -> None:
    """ACP-BATCH-207 (ADVISORY, record-only). An agent MAY spontaneously emit a batch of
    `session/update` notifications; a client-only TCK cannot make an agent choose to do this.
    Always SKIPped."""
    pytest.skip("record-only: cannot force an agent to spontaneously emit a batch (MAY)")


@pytest.mark.requirement("ACP-BATCH-208")
def test_lifecycle_batching_is_a_sender_property() -> None:
    """ACP-BATCH-208 (ADVISORY, record-only). "Clients and agents SHOULD NOT batch
    lifecycle-sensitive messages" is a property of whichever side sends a batch, not of the
    agent under test as a receiver -- the TCK itself never batches these, and cannot observe
    what a would-be batching agent-as-sender would do without an inbound-message scenario it
    does not otherwise exercise. Always SKIPped."""
    pytest.skip("record-only: lifecycle-batching restraint is a sender property, not a receiver one")


@pytest.mark.requirement("ACP-INFO-BATCH-201")
async def test_invalid_json_batch_line_behaviour(agent_launch, record_property):
    """ACP-INFO-BATCH-201 (INFORMATIONAL). Records -- never asserts -- how the agent responds to
    a line that looks like it wants to be a batch but is not valid JSON at all. The spec says a
    single Parse error (`-32700`) with `id: null`, but SDKs disagree (same unasserted rationale
    as v1's ACP-INFO-PARSE-001)."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw('[{"jsonrpc": "2.0", "id": 1, "method": ')  # truncated/malformed
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
        except AgentTimeout:
            record_property("behaviour", "silent")
        except AgentExited as exc:
            record_property("behaviour", f"exited (code={exc.exit_code!r})")
        else:
            msg = entry.parsed
            if isinstance(msg, dict) and isinstance(msg.get("error"), dict):
                record_property("behaviour", f"error response (code={msg['error'].get('code')!r})")
            else:
                record_property("behaviour", f"other: {entry.raw!r}")


@pytest.mark.requirement("ACP-INFO-BATCH-202")
async def test_mixed_call_and_response_shaped_batch_behaviour(agent_launch, record_property):
    """ACP-INFO-BATCH-202 (INFORMATIONAL). Records -- never asserts -- how the agent responds to
    a batch mixing a call-shaped entry (has `method`) with a response-shaped entry (has `result`,
    no `method`) in the same array. The schema forbids mixing kinds structurally, but no prose
    states this and JSON-RPC 2.0 itself does not either."""
    async with _v2_only_agent(agent_launch) as agent:
        await agent.send_raw(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": "tck-mixed-call", "method": "_tck/does_not_exist"},
                    {"jsonrpc": "2.0", "id": "tck-mixed-response", "result": {}},
                ]
            )
        )
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
        except AgentTimeout:
            record_property("behaviour", "silent")
        except AgentExited as exc:
            record_property("behaviour", f"exited (code={exc.exit_code!r})")
        else:
            record_property("behaviour", f"responded: {entry.raw!r}")
