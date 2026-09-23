"""Transport hygiene: ACP-TRANSPORT-002, ACP-TRANSPORT-201, ACP-TRANSPORT-203.

Batch-aware v2 counterpart of `tck.v1.conformance.test_transport` (honest duplication, not
shared machinery). v1's rule "every stdout line is exactly one JSON-RPC 2.0 object" widens in
v2 to "...or a non-empty array of them" (`ACP-TRANSPORT-201`, a fresh id since the wording
changed). `ACP-TRANSPORT-002` (UTF-8) is judged identically to v1. `ACP-TRANSPORT-203` (no
embedded newlines) is new to v2.

`_drive_full_exchange` does its own manual `initialize` (mirroring
`test_initialize.py`/`test_batch.py`) and calls `skip_if_version_mismatch` before touching
`session/new`/`run_prompt` -- otherwise a version-mismatched agent that never sends v2's
`state_update` pair would hang every row here until `AgentTimeout`.
"""

from __future__ import annotations

import json

import pytest

from tck.common.harness import Direction

from ._helpers import new_session, run_prompt, v2_only_agent


async def _drive_full_exchange(agent_launch, tmp_path):
    """Run initialize (skips on version mismatch, see module docstring) -> `session/new` -> one
    ordinary `session/prompt` turn to completion, and return the full RECEIVED transcript,
    collected only after the agent process has fully closed so post-response stdout garbage is
    included (mirrors v1's `_drive_full_exchange`)."""
    async with v2_only_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": "hello é中文 \U0001f600"}],
            timeout=agent_launch.default_timeout,
        )
    return [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]


@pytest.mark.requirement("ACP-TRANSPORT-201")
async def test_stdout_is_clean_ndjson_jsonrpc_or_batch(agent_launch, tmp_path):
    """ACP-TRANSPORT-201: every line on stdout is exactly one valid JSON-RPC 2.0 object, or a
    non-empty array whose every element is a JSON-RPC 2.0 message object -- an empty array is
    itself non-conformant (`ACP-BATCH-201` owns that specific wire evidence; this row only
    checks the general framing shape)."""
    received = await _drive_full_exchange(agent_launch, tmp_path)

    assert received, "the agent never wrote anything to stdout"
    for entry in received:
        assert entry.parse_error is None, f"line is not valid JSON: {entry.raw!r} ({entry.parse_error})"
        parsed = entry.parsed
        if isinstance(parsed, dict):
            assert parsed.get("jsonrpc") == "2.0", f'object line is missing jsonrpc == "2.0": {parsed!r}'
        elif isinstance(parsed, list):
            assert parsed, f"batch array line must not be empty: {entry.raw!r}"
            for item in parsed:
                assert isinstance(item, dict), f"batch element is not a JSON object: {item!r}"
                assert item.get("jsonrpc") == "2.0", (
                    f'batch element is missing jsonrpc == "2.0": {item!r}'
                )
        else:
            pytest.fail(f"line did not parse to a JSON object or array: {entry.raw!r}")


@pytest.mark.requirement("ACP-TRANSPORT-002")
async def test_stdout_is_valid_utf8(agent_launch, tmp_path):
    """ACP-TRANSPORT-002: every line on stdout decodes as UTF-8, independent of framing/shape --
    a plain-ASCII framing violation must not fail this requirement, and only a genuinely
    undecodable line may (mirrors v1's ACP-TRANSPORT-002 split rationale)."""
    received = await _drive_full_exchange(agent_launch, tmp_path)

    assert received, "the agent never wrote anything to stdout"
    for entry in received:
        assert entry.text_error is None, f"non-UTF-8 line from the agent: {entry.raw!r} ({entry.text_error})"


@pytest.mark.requirement("ACP-TRANSPORT-203")
async def test_no_embedded_newlines(agent_launch, tmp_path):
    """ACP-TRANSPORT-203: messages are newline-delimited and MUST NOT contain an embedded literal
    newline -- a batch array is therefore serialised on one line too.

    The harness's `readuntil(b"\\n")` reader makes an embedded newline unobservable within one
    entry -- any literal `\\n` the agent writes ends that read right there. The real signal is
    reassembly: if an entry failed to parse (an incomplete fragment) but concatenating it with
    the next entry's raw bytes (rejoined by the stripped newline) parses as valid JSON, the agent
    split one message across a literal embedded newline.
    """
    received = await _drive_full_exchange(agent_launch, tmp_path)

    assert received, "the agent never wrote anything to stdout"
    for index in range(len(received) - 1):
        entry = received[index]
        if entry.parse_error is None:
            continue  # already a complete, valid message (or batch) on its own line
        combined = entry.raw + b"\n" + received[index + 1].raw
        try:
            json.loads(combined.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        pytest.fail(
            "a message appears to have been split across a literal embedded newline: "
            f"{entry.raw!r} + {received[index + 1].raw!r}"
        )
