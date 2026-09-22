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
(zero FAILs, full `VERSION-MISMATCH:` coverage for every non-negotiation id). `_helpers.
v2_only_agent` implements this "manual initialize + skip on mismatch" pattern.

Batch probes each use their own fresh connection (one `v2_only_agent` per test): a batch line is
exactly the kind of traffic that could crash a less battle-tested agent implementation
(`.agents/research/acp-v2-cancellation-and-batching.md`'s own testability note), and isolating
each probe into its own process means one crash cannot cascade into or pollute a sibling
assertion.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tck.common.harness import AgentTimeout
from tck.v2.protocol import INVALID_REQUEST

from ._helpers import probe_behaviour, quiet_period, v2_only_agent


@pytest.mark.requirement("ACP-BATCH-201")
async def test_empty_batch_yields_a_single_invalid_request_object(agent_launch):
    """ACP-BATCH-201 (MANDATORY). An empty array on stdin gets back a single Invalid Request
    (`-32600`) response *object* with `id: null` -- never a response array.

    Reads until a response-shaped line arrives (a dict with no `method`), bounded by
    `agent_launch.default_timeout`, rather than judging exactly one line: a single spontaneous
    notification arriving first (e.g. a `session/update` from unrelated background activity)
    must not fail this MANDATORY row just because it happened to be first on the wire."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw("[]")

        def _is_not_a_spontaneous_notification(entry) -> bool:
            parsed = entry.parsed
            if isinstance(parsed, dict):
                return "method" not in parsed  # skip bare notifications only
            return True  # anything else (a batch array, malformed JSON, ...) -- stop and judge it

        entry = await agent.wait_for_message(
            _is_not_a_spontaneous_notification, timeout=agent_launch.default_timeout
        )
        msg = entry.parsed
        assert isinstance(msg, dict), f"expected a single response object, got {entry.raw!r}"
        assert msg.get("id") is None, f"expected id: null, got {msg.get('id')!r}"
        error = msg.get("error")
        assert isinstance(error, dict), f"expected an error object, got {msg!r}"
        assert error.get("code") == INVALID_REQUEST, f"expected -32600, got {error.get('code')!r}"


@pytest.mark.requirement("ACP-BATCH-202", "ACP-JSONRPC-003")
async def test_notification_only_batch_produces_no_output(agent_launch):
    """ACP-BATCH-202 (MANDATORY). A batch containing only notifications (no `id` on any entry)
    must not be replied to at all -- not even an empty array.

    Also the sole evidence for `ACP-JSONRPC-003`'s batch-delivered half: `test_jsonrpc.py`'s own
    probe for that id is a bare single notification, never a batch -- this is the one place a
    notification-inside-a-batch is actually sent and checked."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw(json.dumps([{"jsonrpc": "2.0", "method": "_tck/notify_only"}]))
        wait = quiet_period(agent_launch.default_timeout)
        with pytest.raises(AgentTimeout):
            await agent.read_line(timeout=wait)


async def _collect_flattened_responses(agent, count: int, *, timeout: float) -> list[dict]:
    """Read lines until `count` response objects have been observed, flattening both a
    conforming single response array and a non-conforming agent's separate top-level object
    lines -- this helper's own job is only to gather evidence, not to judge `ACP-BATCH-204`.

    `timeout` bounds the *whole* collection, not each individual read: an agent that trickles
    one response object per line, each safely within `timeout` of the last, would otherwise let
    this loop run arbitrarily long -- far past
    `--tck-timeout` -- since a fresh per-read deadline never itself expires. The deadline is
    computed once up front and each read gets whatever of it remains."""
    collected: list[dict] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(collected) < count:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AgentTimeout(
                f"only collected {len(collected)}/{count} batch response object(s) within "
                f"{timeout}s",
                agent.transcript,
                stderr=agent.stderr_text(),
            )
        entry = await agent.read_line(timeout=remaining)
        parsed = entry.parsed
        if isinstance(parsed, list):
            collected.extend(parsed)
        elif isinstance(parsed, dict):
            collected.append(parsed)
        else:
            pytest.fail(f"unexpected line while collecting batch responses: {entry.raw!r}")
    return collected


@pytest.mark.requirement("ACP-BATCH-203", "ACP-JSONRPC-005")
async def test_invalid_batch_entries_get_per_entry_invalid_request(agent_launch):
    """ACP-BATCH-203 (ADVISORY -- report's own text carries no RFC-2119 keyword). A non-empty
    batch of entries that are each structurally invalid (not a JSON-RPC object at all: a number,
    a boolean, `null`) gets back an array of exactly that many `-32600`/`id: null` error objects
    -- one per entry, all invalid, none of them dependent on the agent recognizing/rejecting an
    unknown method (a SHOULD, not a guarantee; a former version of this test batched
    `_tck/does_not_exist` for its "valid" sibling, which only exercises `ACP-JSONRPC-004`'s own
    SHOULD, not this requirement).

    Also the sole evidence for `ACP-JSONRPC-005`'s batch-delivered half: after the erroneous
    batch, a follow-up ordinary request (`session/list`) must still get an ordinary reply --
    proving the connection is still usable, not just that this one malformed batch was
    rejected."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw(json.dumps([17, True, None]))
        responses = await _collect_flattened_responses(
            agent, 3, timeout=agent_launch.default_timeout
        )
        assert len(responses) == 3, f"expected exactly 3 error objects: {responses!r}"
        for response in responses:
            assert response.get("id") is None, f"expected id: null, got {response!r}"
            error = response.get("error")
            assert isinstance(error, dict) and error.get("code") == INVALID_REQUEST, (
                f"expected -32600 for a structurally invalid entry, got {response!r}"
            )

        follow_up_id = await agent.send_request("session/list")
        follow_up = await agent.wait_for_response(
            follow_up_id, timeout=agent_launch.default_timeout
        )
        assert isinstance(follow_up.parsed, dict) and (
            "result" in follow_up.parsed or "error" in follow_up.parsed
        ), f"connection did not survive the erroneous batch: {follow_up.raw!r}"


@pytest.mark.requirement("ACP-BATCH-204", "ACP-BATCH-205", "ACP-JSONRPC-001")
async def test_batch_of_requests_replies_with_matching_responses(agent_launch):
    """ACP-BATCH-204/205 (both ADVISORY, shared test -- see `tck.v2.requirements`'s "Batching"
    docstring section for why sharing is safe here: identical wire evidence, neither is the sole
    cause of a failing verdict). `204`: the agent SHOULD reply to a batch containing at least one
    request
    with one array of the corresponding response objects. `205`: responses MAY appear in any
    order; matching is done here by `id`, never by position -- this test's own lookup-by-id
    (rather than assuming array-index correspondence) is exactly the practice `205` calls for,
    regardless of which order the agent's array actually uses.

    Also the sole evidence for `ACP-JSONRPC-001`'s batch-delivered half: `test_jsonrpc.py`'s own
    id-echo probes are both single-message; this test's match-by-`id` below is exactly the
    batch-response-array case that id echo must also hold for.

    Uses two `session/list` calls, never `session/new`: `transports.mdx`'s own guidance is that
    a client SHOULD NOT batch lifecycle-sensitive methods
    -- exactly what `ACP-BATCH-208` (this file, below) tests for -- so a probe for 204/205 must
    not itself rely on batching one. `session/list` is side-effect-free and requires no session
    to already exist, so it needs no `skip_if_auth_gated_msg`/`tmp_path` plumbing either."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": "tck-batch-a", "method": "session/list"},
                    {"jsonrpc": "2.0", "id": "tck-batch-b", "method": "session/list"},
                ]
            )
        )
        entry = await agent.read_line(timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, list) and len(msg) == 2, (
            f"expected one array with both responses: {entry.raw!r}"
        )
        by_id = {item.get("id"): item for item in msg if isinstance(item, dict)}
        assert "tck-batch-a" in by_id and "tck-batch-b" in by_id, (
            f"response array is missing an id, matched by id (not position): {msg!r}"
        )
        for key in ("tck-batch-a", "tck-batch-b"):
            response = by_id[key]
            assert "result" in response, (
                f"session/list entry {key!r} did not resolve to a result, matched by id: "
                f"{response!r}"
            )


@pytest.mark.requirement("ACP-BATCH-206")
def test_concurrent_batch_processing_is_unobservable(record_property) -> None:
    """ACP-BATCH-206 (INFORMATIONAL, record-only -- a row that can never be judged belongs in
    the record-only tier). The receiver MAY process batch entries concurrently, in any order,
    with any parallelism -- no ordering assertion a
    client-side TCK makes could legitimately distinguish conforming concurrent processing from
    conforming sequential processing. Always SKIPped."""
    record_property("acp_tck_reason", "no client-observable signal distinguishes concurrent from sequential processing (MAY)")
    pytest.skip("record-only: batch-entry processing order/concurrency is not asserted (MAY)")


@pytest.mark.requirement("ACP-BATCH-207")
def test_agent_initiated_batches_cannot_be_forced(record_property) -> None:
    """ACP-BATCH-207 (INFORMATIONAL, record-only -- a row that can never be judged belongs in
    the record-only tier). An agent MAY spontaneously emit a batch of `session/update`
    notifications; a client-only TCK cannot make an agent choose to do this. Always SKIPped."""
    record_property("acp_tck_reason", "a client-only TCK cannot force an agent to spontaneously emit a batch (MAY)")
    pytest.skip("record-only: cannot force an agent to spontaneously emit a batch (MAY)")


@pytest.mark.requirement("ACP-BATCH-208")
def test_lifecycle_batching_is_a_sender_property(record_property) -> None:
    """ACP-BATCH-208 (INFORMATIONAL, record-only -- a row that can never be judged belongs in
    the record-only tier). "Clients and agents SHOULD NOT batch lifecycle-sensitive messages" is
    a property of whichever side sends a batch, not of the agent under test as a receiver -- the
    TCK itself never batches these, and cannot observe what a would-be batching agent-as-sender
    would do without an inbound-message scenario it does not otherwise exercise. Always
    SKIPped."""
    record_property("acp_tck_reason", "lifecycle-batching restraint is a sender property, not a receiver one")
    pytest.skip("record-only: lifecycle-batching restraint is a sender property, not a receiver one")


@pytest.mark.requirement("ACP-INFO-BATCH-201")
async def test_invalid_json_batch_line_behaviour(agent_launch, record_property):
    """ACP-INFO-BATCH-201 (INFORMATIONAL). Records -- never asserts -- how the agent responds to
    a line that looks like it wants to be a batch but is not valid JSON at all. The spec says a
    single Parse error (`-32700`) with `id: null`, but SDKs disagree (same unasserted rationale
    as v1's ACP-INFO-PARSE-001)."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw('[{"jsonrpc": "2.0", "id": 1, "method": ')  # truncated/malformed

        def _on_reply(entry) -> str:
            msg = entry.parsed
            if isinstance(msg, dict) and isinstance(msg.get("error"), dict):
                return f"error response (code={msg['error'].get('code')!r})"
            return f"other: {entry.raw!r}"

        behaviour = await probe_behaviour(
            agent.read_line(timeout=quiet_period(agent_launch.default_timeout)), _on_reply
        )
        record_property("behaviour", behaviour)


@pytest.mark.requirement("ACP-INFO-BATCH-202")
async def test_mixed_call_and_response_shaped_batch_behaviour(agent_launch, record_property):
    """ACP-INFO-BATCH-202 (INFORMATIONAL). Records -- never asserts -- how the agent responds to
    a batch mixing a call-shaped entry (has `method`) with a response-shaped entry (has `result`,
    no `method`) in the same array. The schema forbids mixing kinds structurally, but no prose
    states this and JSON-RPC 2.0 itself does not either."""
    async with v2_only_agent(agent_launch) as agent:
        await agent.send_raw(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": "tck-mixed-call", "method": "_tck/does_not_exist"},
                    {"jsonrpc": "2.0", "id": "tck-mixed-response", "result": {}},
                ]
            )
        )
        behaviour = await probe_behaviour(
            agent.read_line(timeout=quiet_period(agent_launch.default_timeout)),
            lambda entry: f"responded: {entry.raw!r}",
        )
        record_property("behaviour", behaviour)
