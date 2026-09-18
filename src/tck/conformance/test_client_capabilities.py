"""Client-capability negative tests: ACP-CLIENTCAP-001..003 (Reqs 29, 30, 32).

The mock client (`_helpers.run_prompt`) advertises `clientCapabilities: {}` during every prompt
turn in this suite -- no `fs`, no `terminal`, no elicitation mode. During *any* prompt turn the
agent MUST NOT call `fs/read_text_file`, `fs/write_text_file`, any `terminal/*` method, or
`elicitation/create` (Reqs 29, 30, 32) -- these are all client-controlled MUST NOTs, and the TCK
controls the advertisement, so they are directly observable negative tests, not something a
real client could get wrong.

Implemented as three separate tests sharing one helper (review-slices-5-6.md S/item 9: a single
test bound to all three ids at once mis-attributes a one-capability violation to all three --
e.g. `calls_fs_unadvertised.py` only ever calls `fs/read_text_file`, but under the old combined
test its single FAIL outcome was recorded against `ACP-CLIENTCAP-002`/`-003` too, even though the
agent never touched `terminal/*` or `elicitation/create`). Each test sends its own prompt turn
(the mock client's own `run_prompt` call) and filters `PromptTurn.client_requests_seen` -- which
records every agent -> client request `run_prompt` had to answer, replying `-32601` to anything
beyond `session/request_permission` since the mock client advertised no capabilities -- by method
prefix, then asserts only against its own id.

PASS is vacuous for an agent that never needs any client tool at all -- Reqs 29/30/32 only
forbid *calling* the unadvertised capability, they do not require an agent to try and be
refused.
"""

from __future__ import annotations

import pytest

from ._helpers import connected_agent, new_session, run_prompt

# Each test uses its own capability-shaped prompt text rather than sharing one fs-flavoured
# prompt across all three (review-slices-7.md S8): the shared prompt gave the terminal/
# elicitation tests close to zero chance of ever provoking the behaviour they guard, making
# their PASS vacuous by construction rather than by the agent's own choice not to try.
_FS_PROMPT_TEXT = "Read the file README.md in the current directory and summarize it."
_TERMINAL_PROMPT_TEXT = "Run `ls -la` in a shell and show me the output."
_ELICITATION_PROMPT_TEXT = "Before you continue, ask me which of two options I'd prefer."


async def _methods_called_with_no_client_capabilities(agent_launch, tmp_path, prompt_text: str) -> list[str]:
    async with connected_agent(agent_launch, client_capabilities={}) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": prompt_text}],
            timeout=agent_launch.default_timeout,
        )
    return [
        entry.parsed.get("method")
        for entry in turn.client_requests_seen
        if isinstance(entry.parsed, dict)
    ]


@pytest.mark.requirement("ACP-CLIENTCAP-001")
async def test_no_unadvertised_clientcap_fs_call(agent_launch, tmp_path):
    """ACP-CLIENTCAP-001 (Req 29). See module docstring."""
    methods_seen = await _methods_called_with_no_client_capabilities(agent_launch, tmp_path, _FS_PROMPT_TEXT)
    fs_calls = [m for m in methods_seen if isinstance(m, str) and m.startswith("fs/")]
    assert not fs_calls, f"ACP-CLIENTCAP-001: fs/* called without fs advertised: {fs_calls!r}"


@pytest.mark.requirement("ACP-CLIENTCAP-002")
async def test_no_unadvertised_clientcap_terminal_call(agent_launch, tmp_path):
    """ACP-CLIENTCAP-002 (Req 30). See module docstring."""
    methods_seen = await _methods_called_with_no_client_capabilities(
        agent_launch, tmp_path, _TERMINAL_PROMPT_TEXT
    )
    terminal_calls = [m for m in methods_seen if isinstance(m, str) and m.startswith("terminal/")]
    assert not terminal_calls, (
        f"ACP-CLIENTCAP-002: terminal/* called without terminal advertised: {terminal_calls!r}"
    )


@pytest.mark.requirement("ACP-CLIENTCAP-003")
async def test_no_unadvertised_clientcap_elicitation_call(agent_launch, tmp_path):
    """ACP-CLIENTCAP-003 (Req 32). See module docstring."""
    methods_seen = await _methods_called_with_no_client_capabilities(
        agent_launch, tmp_path, _ELICITATION_PROMPT_TEXT
    )
    elicitation_calls = [m for m in methods_seen if m == "elicitation/create"]
    assert not elicitation_calls, (
        f"ACP-CLIENTCAP-003: elicitation/create called without an elicitation mode advertised: "
        f"{elicitation_calls!r}"
    )
