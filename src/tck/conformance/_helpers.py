"""Shared helpers for conformance tests."""

from __future__ import annotations

import contextlib
from typing import AsyncIterator

from tck.harness import AgentLaunch, AgentProcess
from tck.plugin import register_active_process
from tck.protocol import PROTOCOL_VERSION


@contextlib.asynccontextmanager
async def connected_agent(
    launch: AgentLaunch, *, handshake: bool = True
) -> AsyncIterator[AgentProcess]:
    """Spawn a fresh `AgentProcess` for `launch`, optionally perform an `initialize` handshake,
    yield it, and always close it.

    Registers the process with the plugin's failure-diagnostics tracker (`tck.plugin`) so a
    test failure attaches its transcript and stderr to the pytest report, regardless of which
    requirement(s) the test is checking.
    """
    async with AgentProcess(launch) as agent:
        register_active_process(agent)
        if handshake:
            req_id = await agent.send_request(
                "initialize",
                {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}},
            )
            await agent.wait_for_response(req_id, timeout=launch.startup_timeout)
        yield agent
