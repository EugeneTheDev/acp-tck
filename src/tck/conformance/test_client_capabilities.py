"""Client-capability negative tests: ACP-CLIENTCAP-001..003 (Reqs 29, 30, 32).

The mock client (`_helpers.run_prompt`) advertises `clientCapabilities: {}` during every prompt
turn in this suite -- no `fs`, no `terminal`, no elicitation mode. During *any* prompt turn the
agent MUST NOT call `fs/read_text_file`, `fs/write_text_file`, any `terminal/*` method, or
`elicitation/create` (Reqs 29, 30, 32) -- these are all client-controlled MUST NOTs, and the TCK
controls the advertisement, so they are directly observable negative tests, not something a
real client could get wrong.

Implemented as a single sweep bound to all three ids at once (task spec: "Implement as a
sweep"): one prompt whose text invites file access is sent, and every agent -> client request
`run_prompt` had to answer is recorded in `PromptTurn.client_requests_seen` (it replies
`-32601` to anything beyond `session/request_permission`, since the mock client advertised no
capabilities) -- this test just filters that list by method prefix.

PASS is vacuous for an agent that never needs any client tool at all -- Reqs 29/30/32 only
forbid *calling* the unadvertised capability, they do not require an agent to try and be
refused.
"""

from __future__ import annotations

import pytest

from ._helpers import connected_agent, new_session, run_prompt


@pytest.mark.requirement("ACP-CLIENTCAP-001", "ACP-CLIENTCAP-002", "ACP-CLIENTCAP-003")
async def test_no_unadvertised_clientcap_is_called(agent_launch, tmp_path):
    """ACP-CLIENTCAP-001/002/003 (Reqs 29, 30, 32). See module docstring."""
    async with connected_agent(agent_launch, client_capabilities={}) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [
                {
                    "type": "text",
                    "text": "Read the file README.md in the current directory and summarize it.",
                }
            ],
            timeout=agent_launch.default_timeout,
        )

    methods_seen = [
        entry.parsed.get("method")
        for entry in turn.client_requests_seen
        if isinstance(entry.parsed, dict)
    ]

    fs_calls = [m for m in methods_seen if isinstance(m, str) and m.startswith("fs/")]
    assert not fs_calls, f"ACP-CLIENTCAP-001: fs/* called without fs advertised: {fs_calls!r}"

    terminal_calls = [m for m in methods_seen if isinstance(m, str) and m.startswith("terminal/")]
    assert not terminal_calls, (
        f"ACP-CLIENTCAP-002: terminal/* called without terminal advertised: {terminal_calls!r}"
    )

    elicitation_calls = [m for m in methods_seen if m == "elicitation/create"]
    assert not elicitation_calls, (
        f"ACP-CLIENTCAP-003: elicitation/create called without an elicitation mode advertised: "
        f"{elicitation_calls!r}"
    )
