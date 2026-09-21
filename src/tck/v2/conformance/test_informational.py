"""INFORMATIONAL-tier prompt-lifecycle probes: ACP-INFO-CONCURRENT-001 (new) and
ACP-INFO-UNKNOWNSESSION-001 (reused from v1).

Both are explicitly out of scope of the v2 design (concurrency: `docs/rfds/v2/prompt.mdx:86`;
the unknown-`sessionId` error code: `docs/protocol/v2/error.mdx`, still "Documentation coming
soon"), so neither ever asserts on the probed behaviour itself -- each records what the agent
actually does via `record_property`, for a human reading the report. (They can still FAIL if the
prerequisite handshake -- `initialize`/`session/new` -- itself fails; that is a real conformance
problem the probe correctly surfaces, not a probe bug.) Gated on `capabilities.session` like
every other prompt-turn requirement in this slice, even though the `Requirement` itself is
INFORMATIONAL (`capability=None` on the registry entry -- see `tck.v2.requirements`'s module
docstring for why the test marker and the registry's own tier/capability fields are independent).

Concluding "the agent stayed silent" for the concurrency probe uses `quiet_period()`, not the
full `--tck-timeout` -- same rationale as v1's PARSE-001/INVALIDREQ-001 probes (a v2 TCK must not
burn the full per-response deadline to conclude "no response at all"). The unknown-`sessionId`
probe uses the full timeout instead, mirroring v1's own choice there: an agent may legitimately
take a normal amount of time to notice and reject a bogus `sessionId`, and that is not itself
evidence of silence the way a truly unanswered concurrent-prompt probe would be.
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout

from ._helpers import connected_agent, new_session, quiet_period

_PROMPT_TEXT = "hi"


@pytest.mark.requirement("ACP-INFO-CONCURRENT-001")
@pytest.mark.capability("capabilities.session")
async def test_concurrent_prompt_behaviour(agent_launch, tmp_path, record_property):
    """ACP-INFO-CONCURRENT-001 (INFORMATIONAL). Sends a second `session/prompt` for the same
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
