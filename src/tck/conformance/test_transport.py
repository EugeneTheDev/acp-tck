"""Transport hygiene: ACP-TRANSPORT-001, ACP-TRANSPORT-002.

Drives a full exchange (`initialize` -> `session/new` -> `session/prompt`) and then asserts
that every line the agent wrote to stdout, in either direction of that exchange, decoded as
UTF-8 and parsed as a single valid JSON-RPC 2.0 object -- the highest-value structural check a
client-side TCK can make (`.agents/research/acp-v1-transport-and-jsonrpc.md` Testability
note 1).
"""

from __future__ import annotations

import pytest

from tck.harness import Direction

from ._helpers import connected_agent


@pytest.mark.requirement("ACP-TRANSPORT-001", "ACP-TRANSPORT-002")
async def test_full_exchange_is_clean_ndjson(agent_launch, tmp_path):
    """ACP-TRANSPORT-001, ACP-TRANSPORT-002.

    Includes a non-ASCII prompt (both SDKs emit `\\uXXXX`-escaped JSON, which is still valid
    UTF-8/JSON -- see Testability note 2) so the non-ASCII path is exercised too.
    """
    async with connected_agent(agent_launch) as agent:
        session_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        session_entry = await agent.wait_for_response(session_req, timeout=agent_launch.default_timeout)
        session_id = session_entry.parsed["result"]["sessionId"]

        prompt_req = await agent.send_request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello é中文 \U0001f600"}],
            },
        )
        await agent.wait_for_response(prompt_req, timeout=agent_launch.default_timeout)

        received = [entry for entry in agent.transcript if entry.direction is Direction.RECEIVED]

    assert received, "the agent never wrote anything to stdout"
    for entry in received:
        assert entry.text_error is None, f"non-UTF-8 line from the agent: {entry.raw!r} ({entry.text_error})"
        assert entry.parse_error is None, f"line is not valid JSON: {entry.raw!r} ({entry.parse_error})"
        assert isinstance(entry.parsed, dict), f"line did not parse to a JSON object: {entry.raw!r}"
        assert entry.parsed.get("jsonrpc") == "2.0", f'line is missing jsonrpc == "2.0": {entry.parsed!r}'
