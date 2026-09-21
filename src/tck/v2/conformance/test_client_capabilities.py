"""Client-capability negative tests: ACP-CLIENTCAP-201 (elicitation unadvertised MUST NOT be
called) and ACP-CLIENTCAP-202 (every agent -> client method observed during a turn is a defined
v2 client/protocol method, or `_`-prefixed) -- the v2 collapse of v1's three separate
`ACP-CLIENTCAP-001/002/003` rows: v2 has no `fs/*`/`terminal/*` methods at all (they were
removed, not merely capability-gated), so calling either FAILs here as simply an undefined
method, indistinguishable from any other made-up non-`_` method name.

Both rows are `Tier.CAPABILITY`, `capability="capabilities.session"` per the "v2 tiering rule for
session-baseline rows" (`.agents/plan.md`) even though the underlying rules themselves are
unconditional MUSTs -- see `tck.v2.requirements`'s module docstring for the D3/ownership
reasoning. The mock client (`_helpers.run_prompt`) advertises `capabilities: {}` -- no
elicitation mode -- for every prompt turn driven by `connected_agent`'s default (no explicit
`capabilities=` override needed here, since v2's own `SPEC.initialize_params()` already sends
`capabilities: {}`).
"""

from __future__ import annotations

import pytest

from tck.v2.protocol import CLIENT_METHODS, PROTOCOL_METHODS

from ._helpers import connected_agent, new_session, run_prompt

_PROMPT_TEXT = "hi"

_KNOWN_CLIENT_SIDE_METHODS = CLIENT_METHODS | PROTOCOL_METHODS


async def _agent_to_client_methods_seen(agent_launch, tmp_path) -> list[str | None]:
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )
    return [
        entry.parsed.get("method")
        for entry in turn.client_requests_seen
        if isinstance(entry.parsed, dict)
    ]


@pytest.mark.requirement("ACP-CLIENTCAP-201")
@pytest.mark.capability("capabilities.session")
async def test_no_unadvertised_elicitation_call(agent_launch, tmp_path):
    """ACP-CLIENTCAP-201 (`elicitation.mdx:54`: agents MUST NOT request an elicitation mode the
    client has not advertised). PASS is vacuous for an agent that never uses elicitation at
    all."""
    methods_seen = await _agent_to_client_methods_seen(agent_launch, tmp_path)
    elicitation_calls = [m for m in methods_seen if m == "elicitation/create"]
    assert not elicitation_calls, (
        f"ACP-CLIENTCAP-201: elicitation/create called without an elicitation mode advertised: "
        f"{elicitation_calls!r}"
    )


@pytest.mark.requirement("ACP-CLIENTCAP-202")
@pytest.mark.capability("capabilities.session")
async def test_no_undefined_client_methods(agent_launch, tmp_path):
    """ACP-CLIENTCAP-202. Every agent -> client request/notification method observed during a
    prompt turn is one of v2's defined client-side methods (`CLIENT_METHODS`) or a
    bidirectional protocol-level method (`PROTOCOL_METHODS`, e.g. `$/cancel_request`), or begins
    with `_` (custom extension methods, Req 42)."""
    methods_seen = await _agent_to_client_methods_seen(agent_launch, tmp_path)
    undefined = [
        m
        for m in methods_seen
        if isinstance(m, str) and m not in _KNOWN_CLIENT_SIDE_METHODS and not m.startswith("_")
    ]
    assert not undefined, (
        f"ACP-CLIENTCAP-202: undefined agent -> client method(s) observed: {undefined!r}"
    )
