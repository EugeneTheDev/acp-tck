"""Capability-conditional session-method conformance: `session/load`, `session/resume`,
`session/list`, `session/delete`, `session/close`, and `additionalDirectories`
(ACP-LOAD-001..003, ACP-RESUME-001/002, ACP-LIST-001/002, ACP-DELETE-001/002,
ACP-CLOSE-001/002, ACP-ADDDIRS-001).

See `.agents/research/acp-v1-session-capabilities.md` for the wire shapes and the exhaustive
"must NOT be asserted" list this module deliberately stays within (no claim about which/how
many `sessionUpdate` kinds a load replay carries, no ordering claim between a `session/close`
response and the prompt response it triggers, no claim about error codes for unknown
sessionIds, etc.).

Every test here is gated by `@pytest.mark.capability(...)` -- both CAPABILITY-tier and
ADVISORY-tier tests carry this marker; per `tck.common.plugin._tck_capability_gate`, the marker's
effect (SKIP if unadvertised) is independent of the bound `Requirement`'s own tier, which is
why an ADVISORY requirement (`ACP-LOAD-003`, `ACP-DELETE-002`) can still be gated on a
capability without violating the `Requirement.capability` invariant (must be `None` for
non-CAPABILITY tiers, checked in `tck.v1.requirements`).
"""

from __future__ import annotations

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v1.protocol import STOP_REASONS
from tck.v1.validation import validate_agent_response

from ._helpers import connected_agent, new_session, quiet_period, run_prompt, skip_if_auth_gated


# --- session/load ---


@pytest.mark.requirement("ACP-LOAD-001")
@pytest.mark.capability("agentCapabilities.loadSession", boolean=True)
async def test_load_succeeds_and_validates(agent_launch, tmp_path):
    """ACP-LOAD-001."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent, session_id, [{"type": "text", "text": "hello"}], timeout=agent_launch.default_timeout
        )

        req_id = await agent.send_request(
            "session/load",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        # A load may legitimately replay history before its response -- drain it like
        # `run_prompt` does, rather than assuming the very next line is the response.
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/load did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/load", msg)
        assert not issues, f"session/load result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-LOAD-002")
@pytest.mark.capability("agentCapabilities.loadSession", boolean=True)
async def test_load_replays_before_responding_and_nothing_after(agent_launch, tmp_path):
    """ACP-LOAD-002. The "before" half is structural: `wait_for_response` reads stdout
    strictly line-by-line and stops at the matching response, so anything it saw along the
    way (recorded in `pending()`) necessarily arrived first. This test adds the "after" half:
    once the response is in hand, no further `session/update` for this session may arrive
    within a quiet period."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent, session_id, [{"type": "text", "text": "hello"}], timeout=agent_launch.default_timeout
        )

        req_id = await agent.send_request(
            "session/load",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/load did not succeed: {entry.text!r}"
        )

        def _is_update_for_this_session(candidate_entry) -> bool:
            candidate = candidate_entry.parsed
            return (
                isinstance(candidate, dict)
                and candidate.get("method") == "session/update"
                and (candidate.get("params") or {}).get("sessionId") == session_id
            )

        # An agent that exits promptly rather than staying connected through the quiet period
        # raises AgentExited on EOF, not AgentTimeout -- still "no late update arrived," not a
        # defect this requirement is about (review-slices-5-6.md N14).
        with pytest.raises((AgentTimeout, AgentExited)):
            await agent.wait_for_message(
                _is_update_for_this_session, timeout=quiet_period(agent_launch.default_timeout)
            )


@pytest.mark.requirement("ACP-LOAD-003")
@pytest.mark.capability("agentCapabilities.loadSession", boolean=True)
async def test_load_empty_result_is_object_not_null(agent_launch, tmp_path):
    """ACP-LOAD-003 (ADVISORY). Mandatory schema validation (ACP-LOAD-001) already tolerates a
    literal `null` result for this all-optional-fields response, so this test asserts the
    stricter, non-schema-visible fact directly: the result must be `{}`-shaped, not `null`."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        req_id = await agent.send_request(
            "session/load",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/load did not succeed: {entry.text!r}"
        )
        assert isinstance(msg["result"], dict), (
            f"session/load result should be an object ({{}}), not {msg['result']!r}"
        )


# --- session/resume ---


@pytest.mark.requirement("ACP-RESUME-001")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.resume")
async def test_resume_succeeds_and_validates(agent_launch, tmp_path):
    """ACP-RESUME-001."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        req_id = await agent.send_request(
            "session/resume", {"sessionId": session_id, "cwd": str(tmp_path)}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/resume did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/resume", msg)
        assert not issues, f"session/resume result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-RESUME-002")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.resume")
async def test_resume_sends_no_history_before_responding(agent_launch, tmp_path):
    """ACP-RESUME-002. Scoped narrowly per R2: only history-kind `sessionUpdate`s
    (`user_message_chunk`, `agent_message_chunk`, `agent_thought_chunk`) are forbidden before
    the response; other kinds are not."""
    _HISTORY_KINDS = {"user_message_chunk", "agent_message_chunk", "agent_thought_chunk"}

    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        await run_prompt(
            agent, session_id, [{"type": "text", "text": "hello"}], timeout=agent_launch.default_timeout
        )

        pre_request_index = len(agent.transcript)
        req_id = await agent.send_request(
            "session/resume", {"sessionId": session_id, "cwd": str(tmp_path)}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/resume did not succeed: {entry.text!r}"
        )
        response_index = agent.transcript.index(entry)

        offending = []
        for candidate_entry in agent.transcript[pre_request_index:response_index]:
            candidate = candidate_entry.parsed
            if not (isinstance(candidate, dict) and candidate.get("method") == "session/update"):
                continue
            update_params = candidate.get("params") or {}
            if update_params.get("sessionId") != session_id:
                continue
            kind = (update_params.get("update") or {}).get("sessionUpdate")
            if kind in _HISTORY_KINDS:
                offending.append(candidate)
        assert not offending, (
            f"session/resume replayed history-kind update(s) before responding: {offending!r}"
        )


# --- session/list ---


@pytest.mark.requirement("ACP-LIST-001")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.list")
async def test_list_succeeds_and_validates(agent_launch, tmp_path):
    """ACP-LIST-001."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        req_id = await agent.send_request("session/list", {})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/list did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/list", msg)
        assert not issues, f"session/list result failed schema validation: {issues!r}"
        assert isinstance(msg["result"].get("sessions"), list), (
            f"session/list result.sessions is not an array: {msg['result']!r}"
        )


@pytest.mark.requirement("ACP-LIST-002")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.list")
async def test_list_with_unmatched_cwd_filter_returns_empty_array(agent_launch, tmp_path):
    """ACP-LIST-002."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        empty_dir = tmp_path / "no-session-here"
        empty_dir.mkdir()

        req_id = await agent.send_request("session/list", {"cwd": str(empty_dir)})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/list did not succeed: {entry.text!r}"
        )
        assert msg["result"].get("sessions") == [], (
            f"session/list with an unmatched cwd filter must return sessions: [], got "
            f"{msg['result']!r}"
        )


# --- session/delete ---


@pytest.mark.requirement("ACP-DELETE-001")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.delete")
async def test_delete_existing_session_succeeds(agent_launch, tmp_path):
    """ACP-DELETE-001."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        req_id = await agent.send_request("session/delete", {"sessionId": session_id})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/delete did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/delete", msg)
        assert not issues, f"session/delete result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-DELETE-002")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.delete")
async def test_delete_unknown_session_succeeds_silently(agent_launch):
    """ACP-DELETE-002 (ADVISORY). No `session/new` is ever sent -- this sessionId was never
    created on this connection."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/delete", {"sessionId": "tck-never-created-session"}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"deleting an unknown sessionId should succeed silently, got: {entry.text!r}"
        )


# --- session/close ---


@pytest.mark.requirement("ACP-CLOSE-001")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.close")
async def test_close_idle_session_succeeds(agent_launch, tmp_path):
    """ACP-CLOSE-001."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        req_id = await agent.send_request("session/close", {"sessionId": session_id})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/close did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/close", msg)
        assert not issues, f"session/close result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-CLOSE-002")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.close")
async def test_close_in_flight_prompt_resolves_cancelled(
    agent_launch, tmp_path, cancel_prompt_text, record_property
):
    """ACP-CLOSE-002. Modeled on `test_cancel.py`'s SKIP-vs-FAIL race handling (module
    docstring there), but driving a `session/close` *request* instead of a `session/cancel`
    *notification* at the same timing heuristic: sent as soon as either the first
    `session/update` arrives or `cancel_wait` seconds elapse. No claim is made about the
    ordering between the `session/close` response and the prompt's own response (research's
    "must NOT assert" list) -- both are simply awaited independently, in whichever order they
    arrive.

    Driven through `run_prompt`'s `on_action` hook (review-slices-5-6.md S3) instead of a
    hand-rolled read loop: the previous version of this test only dispatched three message
    shapes and silently dropped any agent -> client *request* (e.g. `session/request_permission`)
    the agent sent while the close was in flight, deadlocking against a conforming,
    permission-asking agent. `run_prompt` answers everything a mock client is expected to.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)

        async def _send_close() -> str:
            close_id = "tck-close"
            await agent.send_request("session/close", {"sessionId": session_id}, id=close_id)
            return close_id

        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": cancel_prompt_text}],
            on_action=_send_close,
            timeout=agent_launch.default_timeout,
        )

        close_response_entry = turn.action_response
        if close_response_entry is None:
            pytest.skip(
                "close-cancellation not exercised: prompt turn completed before session/close "
                "could be sent"
            )
        close_msg = close_response_entry.parsed
        if not (isinstance(close_msg, dict) and "result" in close_msg):
            # An error-shaped session/close response is ACP-CLOSE-001's finding to make, not
            # this test's -- asserting it here too would double-report the same defect against
            # both requirements (review-slices-5-6.md N15).
            pytest.skip(
                "prerequisite not met: session/close did not succeed (see ACP-CLOSE-001): "
                f"{close_response_entry.text!r}"
            )

        closed_at_index = turn.action_sent_at_index
        prompt_response_entry = turn.response_entry
        prompt_msg = prompt_response_entry.parsed
        if isinstance(prompt_msg, dict) and "result" in prompt_msg:
            stop_reason = prompt_msg["result"].get("stopReason")
            if stop_reason != "cancelled" and stop_reason in STOP_REASONS:
                race_window = quiet_period(agent_launch.default_timeout)
                close_timestamp = agent.transcript[closed_at_index].timestamp
                elapsed_ms = (prompt_response_entry.timestamp - close_timestamp) * 1000
                record_property("acp_tck_close_race_window_ms", f"{race_window * 1000:.0f}")
                if elapsed_ms < race_window * 1000:
                    record_property("acp_tck_close_race_ms", f"{elapsed_ms:.0f}")
                    pytest.skip(
                        f"close-cancellation not exercised: prompt response arrived "
                        f"{elapsed_ms:.0f} ms after session/close; agent may have finished "
                        "before reading it"
                    )

        assert isinstance(prompt_msg, dict) and "result" in prompt_msg, (
            f"session/close on an in-flight prompt must resolve it with a success result, not "
            f"an error: {prompt_msg!r}"
        )
        stop_reason = prompt_msg["result"].get("stopReason")
        assert stop_reason == "cancelled", (
            f"expected stopReason 'cancelled' after session/close on an in-flight prompt, got "
            f"{stop_reason!r}"
        )


# --- additionalDirectories ---


@pytest.mark.requirement("ACP-ADDDIRS-001")
@pytest.mark.capability("agentCapabilities.sessionCapabilities.additionalDirectories")
async def test_new_session_with_additional_directories_is_accepted(agent_launch, tmp_path):
    """ACP-ADDDIRS-001."""
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/new",
            {
                "cwd": str(tmp_path),
                "mcpServers": [],
                "additionalDirectories": [str(extra_dir)],
            },
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        skip_if_auth_gated(entry)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/new with an additionalDirectories entry did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/new", msg)
        assert not issues, f"session/new result failed schema validation: {issues!r}"
