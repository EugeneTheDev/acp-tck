"""INFORMATIONAL-tier probes: ACP-INFO-CONCURRENT-201 (new), ACP-INFO-UNKNOWNSESSION-001 (reused
from v1), and ACP-INFO-PARSE-001/ACP-INFO-INVALIDREQ-001 (re-cited from v1, unchanged --
`.agents/research/acp-v2-patches-enums-extensibility.md` does not mention them, but they are
version-agnostic transport-level probes with nothing v2-specific to revisit).

All four are explicitly out of scope of the v2 design or of the spec entirely (concurrency:
`docs/rfds/v2/prompt.mdx:86`; the unknown-`sessionId` error code and malformed/non-envelope input:
`docs/protocol/v2/error.mdx`, still "Documentation coming soon"), so none of them ever asserts on
the probed behaviour itself -- each records what the agent actually does via `record_property`,
for a human reading the report. (They can still FAIL if the prerequisite handshake --
`initialize`/`session/new` -- itself fails; that is a real conformance problem the probe correctly
surfaces, not a probe bug.) ACP-INFO-CONCURRENT-201/ACP-INFO-UNKNOWNSESSION-001 are gated on
`capabilities.session` like every other prompt-turn requirement in this slice, even though the
`Requirement` itself is INFORMATIONAL (`capability=None` on the registry entry -- see
`tck.v2.requirements`'s module docstring for why the test marker and the registry's own
tier/capability fields are independent). ACP-INFO-PARSE-001/ACP-INFO-INVALIDREQ-001 carry no such
marker, mirroring v1: their own `_probe_connection_usable_after` helper already swallows a
`session/new` failure (including "capability not advertised at all") into an "unusable" behaviour
string rather than letting it propagate as a real failure.

Concluding "the agent stayed silent" for the concurrency/parse/invalid-request probes uses
`quiet_period()`, not the full `--tck-timeout` -- a v2 TCK must not burn the full per-response
deadline to conclude "no response at all". The unknown-`sessionId` probe uses the full timeout
instead, mirroring v1's own choice there: an agent may legitimately take a normal amount of time
to notice and reject a bogus `sessionId`, and that is not itself evidence of silence the way a
truly unanswered concurrent-prompt probe would be.
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v2 import SPEC

from ._helpers import connected_agent, new_session, quiet_period

_PROMPT_TEXT = "hi"


async def _probe_connection_usable_after(agent, tmp_path, timeout: float) -> str:
    """Send an ordinary `session/new` and report whether it still gets a normal response.
    v2 twin of `tck.v1.conformance.test_informational._probe_connection_usable_after`."""
    try:
        session_id = await new_session(agent, tmp_path, timeout=timeout)
    except AssertionError:
        return "unusable (session/new did not return a well-formed result)"
    except pytest.skip.Exception:
        return "unusable (session/new is auth-gated)"
    except (AgentTimeout, AgentExited):
        return "unusable (no response / agent exited)"
    else:
        return f"usable (sessionId={session_id!r})"


@pytest.mark.requirement("ACP-INFO-CONCURRENT-201")
@pytest.mark.capability("capabilities.session")
async def test_concurrent_prompt_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-CONCURRENT-201 (INFORMATIONAL). Sends a second `session/prompt` for the same
    session before the first has reached its terminating idle, and records how the agent
    reacts: a JSON-RPC error, a normal acceptance receipt, or silence. Never asserts."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        first_id = await agent.send_request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": _PROMPT_TEXT}]},
        )
        second_id = await agent.send_request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": _PROMPT_TEXT}]},
        )
        try:
            entry = await agent.wait_for_response(
                second_id, timeout=quiet_period(agent_launch.default_timeout)
            )
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            error = msg.get("error") if isinstance(msg, dict) else None
            if isinstance(error, dict):
                behaviour = f"replied with error code {error.get('code')!r}"
            elif isinstance(msg, dict) and "result" in msg:
                behaviour = "replied with a result (no error)"
            else:
                behaviour = f"replied: {entry.text!r}"

        # Best-effort drain of the first prompt's own response, so this connection's teardown
        # doesn't race a still-in-flight turn; never asserts, never raises.
        try:
            await agent.wait_for_response(first_id, timeout=agent_launch.default_timeout)
        except (AgentTimeout, AgentExited):
            pass

    record_property("behaviour", behaviour)


@pytest.mark.requirement("ACP-INFO-UNKNOWNSESSION-001")
@pytest.mark.capability("capabilities.session")
async def test_unknown_session_id_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-UNKNOWNSESSION-001 (INFORMATIONAL, reused from v1). `session/prompt` for a
    `sessionId` the agent never created. Records the error code, if any (v2's `error.mdx` is
    still a stub). Never asserts."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        prompt_id = await agent.send_request(
            "session/prompt",
            {"sessionId": "tck-does-not-exist", "prompt": [{"type": "text", "text": _PROMPT_TEXT}]},
        )
        try:
            entry = await agent.wait_for_response(prompt_id, timeout=agent_launch.default_timeout)
        except AgentTimeout:
            outstanding = [
                entry.parsed.get("method")
                for entry in agent.pending()
                if isinstance(entry.parsed, dict)
                and entry.parsed.get("method")
                and "id" in entry.parsed
            ]
            if outstanding:
                behaviour = (
                    f"silent (agent had {len(outstanding)} outstanding client "
                    f"request(s): {outstanding})"
                )
            else:
                behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            error = msg.get("error") if isinstance(msg, dict) else None
            if isinstance(error, dict):
                behaviour = f"replied with error code {error.get('code')!r}"
            elif isinstance(msg, dict) and "result" in msg:
                behaviour = "replied with a result (no error)"
            else:
                behaviour = f"replied: {entry.text!r}"

    record_property("behaviour", behaviour)


@pytest.mark.requirement("ACP-INFO-PARSE-001")
async def test_malformed_json_line_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-PARSE-001 (INFORMATIONAL, re-cited from v1 unchanged). Sends a line that is not
    valid JSON at all after a normal `initialize`, and records how the agent reacts: a JSON-RPC
    error, silence, or an exit. Never asserts on the behaviour itself; still records whether the
    connection is usable afterwards for a human reading the report."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", SPEC.initialize_params())
        await agent.wait_for_response(init_id, timeout=agent_launch.startup_timeout)

        await agent.send_raw(b"{not valid json at all")
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            error = msg.get("error") if isinstance(msg, dict) else None
            if isinstance(error, dict):
                behaviour = f"replied with error code {error.get('code')!r}"
            else:
                behaviour = f"replied: {entry.text!r}"

        usable_after = await _probe_connection_usable_after(
            agent, tmp_path, agent_launch.default_timeout
        )

    record_property("behaviour", behaviour)
    record_property("connection_usable_after", usable_after)


@pytest.mark.requirement("ACP-INFO-INVALIDREQ-001")
async def test_structurally_invalid_request_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-INVALIDREQ-001 (INFORMATIONAL, re-cited from v1 unchanged). Sends a
    well-formed-JSON line that is not a valid JSON-RPC envelope at all (no `jsonrpc`/`method`)
    after a normal `initialize`, and records how the agent reacts. Never asserts on the
    behaviour itself; still records whether the connection is usable afterwards."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", SPEC.initialize_params())
        await agent.wait_for_response(init_id, timeout=agent_launch.startup_timeout)

        await agent.send_raw(b'{"foo": "bar"}')
        try:
            entry = await agent.read_line(timeout=quiet_period(agent_launch.default_timeout))
        except AgentTimeout:
            behaviour = "silent"
        except AgentExited as exc:
            behaviour = f"agent exited (exit_code={exc.exit_code!r})"
        else:
            msg = entry.parsed
            error = msg.get("error") if isinstance(msg, dict) else None
            if isinstance(error, dict):
                behaviour = f"replied with error code {error.get('code')!r}"
            else:
                behaviour = f"replied: {entry.text!r}"

        usable_after = await _probe_connection_usable_after(
            agent, tmp_path, agent_launch.default_timeout
        )

    record_property("behaviour", behaviour)
    record_property("connection_usable_after", usable_after)
