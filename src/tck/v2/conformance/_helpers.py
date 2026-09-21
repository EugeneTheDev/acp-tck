"""Shared helpers for the v2 conformance suite.

Slice V2-1b scope: `connected_agent()`, `new_session()`, and `skip_if_version_mismatch()`. v1's
`run_prompt`/`skip_if_auth_gated`/`quiet_period`/`cancel_race_peek`/`PromptTurn` machinery still
has no v2 counterpart -- no test in this slice drives a full prompt turn (`ACP-SCHEMA-001` is
deliberately scoped to the `initialize` exchange only this slice, see `test_initialize.py`), and
no v2 auth flow is in scope yet either. Both are expected to gain a v2 counterpart in a
follow-up slice, mirroring `tck.v1.conformance._helpers` (see this package's module docstring /
`.agents/plan.md`).
"""

from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator

import pytest

from tck.common.harness import AgentLaunch, AgentProcess
from tck.common.plugin import current_auth_method_id, register_active_process

from .. import SPEC
from ..protocol import PROTOCOL_VERSION


@contextlib.asynccontextmanager
async def connected_agent(
    launch: AgentLaunch,
    *,
    handshake: bool = True,
    capabilities: dict[str, Any] | None = None,
) -> AsyncIterator[AgentProcess]:
    """Spawn a fresh `AgentProcess` for `launch`, optionally perform an `initialize` handshake,
    yield it, and always close it. Mirrors `tck.v1.conformance._helpers.connected_agent`.

    Registers the process with the plugin's failure-diagnostics tracker (`tck.common.plugin`) so
    a test failure attaches its transcript and stderr to the pytest report.

    When `handshake` is true and `--tck-auth-method` was given (`current_auth_method_id()`), an
    `auth/login` call for that method id is sent right after `initialize` -- v2's renamed
    counterpart of v1's `authenticate` (same `{"methodId": ...}` params shape,
    `schema/v2/schema.json` `$defs/LoginAuthRequest`). As in v1, a failing `auth/login` here is
    not itself a conformance assertion -- it means the TCK cannot exercise anything
    session-dependent against this agent with the given `--auth-method`, so the test SKIPs with
    a clear reason instead of raising.
    """
    async with AgentProcess(launch) as agent:
        register_active_process(agent)
        if handshake:
            params = SPEC.initialize_params()
            if capabilities is not None:
                params = {**params, "capabilities": capabilities}
            req_id = await agent.send_request("initialize", params)
            await agent.wait_for_response(req_id, timeout=launch.startup_timeout)
            method_id = current_auth_method_id()
            if method_id is not None:
                auth_id = await agent.send_request("auth/login", {"methodId": method_id})
                auth_entry = await agent.wait_for_response(auth_id, timeout=launch.startup_timeout)
                auth_msg = auth_entry.parsed
                if not (isinstance(auth_msg, dict) and isinstance(auth_msg.get("result"), dict)):
                    detail = (
                        auth_msg.get("error") if isinstance(auth_msg, dict) else None
                    ) or auth_entry.text
                    pytest.skip(
                        f"AUTH-GATED: auth/login with methodId={method_id!r} failed: {detail!r} "
                        "-- check --tck-auth-method"
                    )
        yield agent


async def new_session(agent: AgentProcess, cwd: Any, *, timeout: float | None = None) -> str:
    """Send `session/new` for `cwd` and return the resulting `sessionId`.

    Unlike v1's `new_session`, `mcpServers` is omitted entirely rather than sent as an empty
    list -- v2's `session/new` params require only `cwd`
    (`.agents/research/acp-v2-session-management.md`: "omit `mcpServers` entirely -- this is the
    cleanest v2-vs-v1 difference and avoids the MCP-capability check"; `schema/v2/schema.json`
    `required: ["cwd"]`, `mcpServers` optional).
    """
    req_id = await agent.send_request("session/new", {"cwd": str(cwd)})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    session_id = msg["result"].get("sessionId")
    assert isinstance(session_id, str) and session_id, (
        f"session/new result.sessionId must be a non-empty string, got {session_id!r}"
    )
    return session_id


def skip_if_version_mismatch(init_result: dict[str, Any]) -> None:
    """Skip with the `VERSION-MISMATCH: ` marker (`tck.common.plugin`'s `_VERSION_MISMATCH_MARKER`
    substring, scanned by `_build_report()` to set `Verdict.blocked_by_version_mismatch`) unless
    `init_result`'s negotiated `protocolVersion` is this suite's own `PROTOCOL_VERSION` (2).

    An agent that honestly negotiates down to a lower version (e.g. a v1-only agent answering `1`
    to a v2 client, per the two-branch negotiation rule -- see `ACP-INIT-201`) is not thereby
    "broken": the negotiation itself is judged normally by `ACP-INIT-001`/`003`/`201`/`202`, which
    only ever assert on the negotiation outcome, never on the *shape* of the result payload. But
    a test that goes on to assert v2-only shape requirements against that same result -- `info`
    being REQUIRED (`ACP-INIT-203`), capability markers being objects (`ACP-INIT-204`), or the
    exchange validating against the v2 schema (`ACP-SCHEMA-001`) -- cannot honestly judge a
    result the agent never claimed was v2-shaped; call this right after such a test has its own
    `init_result` in hand, before evaluating any v2-shape assertion.

    Unlike `tck.common.plugin`'s `_tck_capability_gate`, which only runs for
    `@pytest.mark.capability(...)`-marked tests sharing the session-scoped
    `agent_initialize_result` fixture, every test in `test_initialize.py` spawns its own fresh
    process and sends its own `initialize` (mirroring v1's "never send a second `initialize` on
    one connection" rule) -- so this has to be called explicitly rather than picked up by an
    autouse fixture.
    """
    negotiated = init_result.get("protocolVersion")
    if negotiated != PROTOCOL_VERSION:
        pytest.skip(
            f"VERSION-MISMATCH: negotiated protocolVersion={negotiated!r}, expected "
            f"{PROTOCOL_VERSION!r} -- this agent does not speak v2, so its result cannot be "
            "judged against v2-only shape requirements"
        )
