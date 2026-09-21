"""Shared helpers for the v2 conformance suite.

Skeleton-slice scope: only `connected_agent()` -- the two tests in `test_initialize.py` never
touch `session/new` or `session/prompt`, so v1's `new_session`/`run_prompt`/`skip_if_auth_gated`/
`quiet_period`/`cancel_race_peek`/`PromptTurn` machinery has no v2 counterpart yet. It is expected
to gain one in a follow-up slice, mirroring `tck.v1.conformance._helpers` (see this package's
module docstring / `.agents/plan.md`).
"""

from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator

import pytest

from tck.common.harness import AgentLaunch, AgentProcess
from tck.common.plugin import current_auth_method_id, register_active_process

from .. import SPEC


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
