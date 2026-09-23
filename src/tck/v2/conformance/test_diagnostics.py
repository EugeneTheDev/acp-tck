"""Advisory/informational diagnostics, re-cited from v1 unchanged: `ACP-ERROR-001`,
`ACP-SHUTDOWN-001`, `ACP-STDERR-001`. `Error` `$def` is byte-identical to v1; v2 still has no
shutdown method; the spec has nothing to say about stderr in either version. All
connection-level, `capability=None` -- none needs a turn."""

from __future__ import annotations

import pytest

from tck.v2 import SPEC

from ._helpers import connected_agent, new_session


@pytest.mark.requirement("ACP-ERROR-001")
async def test_error_messages_are_non_empty_single_line(agent_launch):
    """ACP-ERROR-001 (ADVISORY, re-cited from v1 unchanged -- `error.mdx` is still a stub in v2
    too; `Error` `$def` is byte-identical, `schema/v2/schema.json:4127-4149`). Evidence: the
    reply to an unrecognised method, and the reply to a `session/new` missing its required
    `cwd`."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", SPEC.initialize_params())
        await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)

        unknown_id = await agent.send_request("_tck/does_not_exist")
        unknown_entry = await agent.wait_for_response(unknown_id, timeout=agent_launch.default_timeout)

        bad_id = await agent.send_request("session/new", {})  # missing required cwd
        bad_entry = await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)

    for what, entry in (("_tck/does_not_exist", unknown_entry), ("session/new (missing cwd)", bad_entry)):
        msg = entry.parsed
        error = msg.get("error") if isinstance(msg, dict) else None
        if not isinstance(error, dict):
            continue  # envelope shape is ACP-JSONRPC-002/004's concern, not this test's
        message = error.get("message")
        if not isinstance(message, str):
            continue
        assert message != "", f"{what}: error.message must not be empty"
        assert "\n" not in message, f"{what}: error.message must not contain a newline: {message!r}"
        # error.data's structure is genuinely unspecified (JSON-RPC 2.0 leaves it to the
        # implementation) -- nothing to assert on it.


@pytest.mark.requirement("ACP-SHUTDOWN-001")
async def test_agent_exits_promptly_after_stdin_close(agent_launch, tmp_path):
    """ACP-SHUTDOWN-001 (ADVISORY, re-cited from v1 unchanged -- v2 still has no dedicated
    shutdown method, `docs/protocol/v2/transports.mdx:41`). Relies on `connected_agent`'s
    `close()` ladder and reports whether the agent exited during the first rung
    (`AgentProcess.exited_on_stdin_close`)."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

    assert agent.exited_on_stdin_close, (
        "agent did not exit within the grace period after stdin closed; it needed SIGTERM/"
        "SIGKILL to terminate (advisory -- the spec does not mandate shutdown timing, but a "
        "prompt exit on stdin EOF is expected of a well-behaved agent)"
    )


@pytest.mark.requirement("ACP-STDERR-001")
async def test_stderr_byte_count_is_recorded(agent_launch, tmp_path, record_property):
    """ACP-STDERR-001 (INFORMATIONAL, re-cited from v1 unchanged -- the spec has nothing to say
    about stderr at all). Always PASSes; exists purely to surface stderr chattiness for a human
    reading the report."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

    stderr_bytes = len(agent.stderr_text().encode("utf-8"))
    record_property("acp_tck_stderr_bytes", stderr_bytes)
