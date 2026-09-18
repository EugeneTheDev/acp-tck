"""Transport hygiene: ACP-TRANSPORT-001, ACP-TRANSPORT-002.

Drives a full exchange (`initialize` -> `session/new` -> `session/prompt`) through the mock
client (`run_prompt`) so an agent that asks for permission mid-turn does not deadlock the
transport tests (review S4), then asserts over every line the agent wrote to stdout, in either
direction of that exchange -- including whatever the agent writes to stdout *after* the last
response ever awaited, which `close()` drains into the transcript before the process exits
(review S8) -- the highest-value structural check a client-side TCK can make
(`.agents/research/acp-v1-transport-and-jsonrpc.md` Testability note 1).

Split into two tests (review S2) so a plain-ASCII framing violation (e.g. a banner on stdout)
cannot be misreported as a UTF-8 violation: ACP-TRANSPORT-001 checks JSON-RPC framing/shape,
ACP-TRANSPORT-002 checks UTF-8 decoding, each over the *same* recorded transcript but with its
own independent evidence.
"""

from __future__ import annotations

import pytest

from tck.harness import Direction

from ._helpers import connected_agent, new_session, run_prompt


async def _drive_full_exchange(agent_launch, tmp_path):
    """Perform `initialize` -> `session/new` -> `session/prompt` (with a non-ASCII prompt --
    both SDKs emit `\\uXXXX`-escaped JSON, which is still valid UTF-8/JSON, exercising the
    non-ASCII path too -- Testability note 2) and return the full transcript, collected only
    after the agent process has fully closed so post-response stdout garbage is included."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello é中文 \U0001f600"}],
            timeout=agent_launch.default_timeout,
        )
    # Collected after the `async with` block exits: `close()` has already drained whatever the
    # agent wrote after the last response we awaited (review S8).
    return [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]


@pytest.mark.requirement("ACP-TRANSPORT-001")
async def test_stdout_is_clean_ndjson_jsonrpc(agent_launch, tmp_path):
    """ACP-TRANSPORT-001: every line on stdout is exactly one valid JSON-RPC 2.0 object."""
    received = await _drive_full_exchange(agent_launch, tmp_path)

    assert received, "the agent never wrote anything to stdout"
    for entry in received:
        assert entry.parse_error is None, f"line is not valid JSON: {entry.raw!r} ({entry.parse_error})"
        assert isinstance(entry.parsed, dict), f"line did not parse to a JSON object: {entry.raw!r}"
        assert entry.parsed.get("jsonrpc") == "2.0", f'line is missing jsonrpc == "2.0": {entry.parsed!r}'


@pytest.mark.requirement("ACP-TRANSPORT-002")
async def test_stdout_is_valid_utf8(agent_launch, tmp_path):
    """ACP-TRANSPORT-002: every line on stdout decodes as UTF-8, independent of framing/shape --
    a plain-ASCII framing violation (e.g. a banner) must not fail this requirement, and only a
    genuinely undecodable line may (review S2)."""
    received = await _drive_full_exchange(agent_launch, tmp_path)

    assert received, "the agent never wrote anything to stdout"
    for entry in received:
        assert entry.text_error is None, f"non-UTF-8 line from the agent: {entry.raw!r} ({entry.text_error})"
