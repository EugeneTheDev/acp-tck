"""Session management: `session/resume` (ACP-SESSION-203, ACP-RESUME-201..205),
`session/list` (ACP-LIST-201..204), `session/close`'s own baseline contract (ACP-CLOSE-201 --
`ACP-CLOSE-202` is covered by `test_cancel.py`'s `test_close_cancels_foreground_work`, see
`tck.v2.requirements`'s module docstring), `session/delete` (ACP-DELETE-201..203), the
`additionalDirectories` carrier on `session/new`/`session/resume` (ACP-ADDDIRS-201/202), and the
two INFORMATIONAL MCP-server-acceptance probes (ACP-MCP-201/202).

Every id here except `ACP-DELETE-203`/`ACP-MCP-201`/`ACP-MCP-202` is `Tier.CAPABILITY`; see the
requirements module docstring for the exact capability path each uses. `ACP-DELETE-203` and
`ACP-MCP-201`/`202` still carry a `@pytest.mark.capability(...)` marker purely for the SKIP gate
even though `Requirement.capability` is `None` for all three (ADVISORY/INFORMATIONAL tier) -- the
same independence used throughout this registry (e.g. `ACP-CANCEL-204`).
"""

from __future__ import annotations

from typing import Any

import pytest

from tck.v2.validation import validate_agent_response

from ._helpers import (
    close_session,
    connected_agent,
    delete_session,
    drain_quiet,
    list_sessions,
    new_session,
    obtain_resumable_session,
    quiet_period,
    resume_session,
    run_prompt,
)

_HISTORY_KINDS = {"user_message", "agent_message", "agent_thought"}
_CHUNK_KINDS = {"user_message_chunk", "agent_message_chunk", "agent_thought_chunk"}


def _update_of(entry: Any) -> dict[str, Any] | None:
    """Extract the `update` payload from a `session/update` transcript entry, or `None` if the
    entry is not a well-formed `session/update` notification."""
    msg = entry.parsed
    if not isinstance(msg, dict) or msg.get("method") != "session/update":
        return None
    params = msg.get("params")
    if not isinstance(params, dict):
        return None
    update = params.get("update")
    return update if isinstance(update, dict) else None


# --- session/new / session/resume (ACP-SESSION-203, ACP-RESUME-201..205) ---


@pytest.mark.requirement("ACP-SESSION-203")
@pytest.mark.capability("capabilities.session")
async def test_session_new_mcp_servers_omitted_or_empty_are_equivalent(agent_launch, tmp_path):
    """ACP-SESSION-203."""
    async with connected_agent(agent_launch) as agent:
        omitted_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert omitted_id
        req_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/new with mcpServers: [] did not succeed: {entry.text!r}"
        )


@pytest.mark.requirement("ACP-RESUME-201")
@pytest.mark.capability("capabilities.session")
async def test_resume_a_resumable_session_succeeds(agent_launch, tmp_path):
    """ACP-RESUME-201."""
    async with obtain_resumable_session(
        agent_launch, tmp_path, timeout=agent_launch.default_timeout
    ) as (_agent, _session_id, entry):
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/resume of a resumable session did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/resume", msg)
        assert not issues, f"session/resume result failed schema validation: {issues!r}"


async def _session_with_history(agent, cwd, *, timeout):
    """Create a session and run one ordinary prompt turn on it, so the fixture/agent under test
    has something to (optionally) replay. Returns `(session_id, prompt_turn)`."""
    session_id = await new_session(agent, cwd, timeout=timeout)
    turn = await run_prompt(
        agent, session_id, [{"type": "text", "text": "remember this"}], timeout=timeout
    )
    return session_id, turn


@pytest.mark.requirement("ACP-RESUME-202")
@pytest.mark.capability("capabilities.session")
async def test_resume_with_replay_from_start_replays_before_responding(
    agent_launch, tmp_path, record_property
):
    """ACP-RESUME-202. Zero replayed updates is itself conforming (R5's retention escape
    hatch) -- recorded, never FAILed."""
    async with connected_agent(agent_launch) as agent:
        session_id, _turn = await _session_with_history(
            agent, tmp_path, timeout=agent_launch.default_timeout
        )
        response_entry, updates = await resume_session(
            agent,
            session_id,
            tmp_path,
            replay_from={"type": "start"},
            timeout=agent_launch.default_timeout,
        )
        msg = response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/resume with replayFrom: start did not succeed: {response_entry.text!r}"
        )
        record_property("acp_tck_resume_replayed_update_count", len(updates))
        trailing = await drain_quiet(agent, quiet_period(agent_launch.default_timeout))
        trailing_updates = [e for e in trailing if _update_of(e) is not None]
        assert not trailing_updates, (
            "a session/update arrived after session/resume's response instead of before it: "
            f"{[e.text for e in trailing_updates]!r}"
        )


@pytest.mark.requirement("ACP-RESUME-203")
@pytest.mark.capability("capabilities.session")
async def test_resume_without_replay_from_replays_no_history(agent_launch, tmp_path, record_property):
    """ACP-RESUME-203. Vacuous -- and recorded, never FAILed on that account -- for an agent
    that retains no history to replay."""
    async with connected_agent(agent_launch) as agent:
        session_id, _turn = await _session_with_history(
            agent, tmp_path, timeout=agent_launch.default_timeout
        )
        response_entry, updates = await resume_session(
            agent, session_id, tmp_path, timeout=agent_launch.default_timeout
        )
        msg = response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/resume with replayFrom omitted did not succeed: {response_entry.text!r}"
        )
        history_updates = [
            update
            for _, entry in updates
            if (update := _update_of(entry)) is not None
            and update.get("sessionUpdate") in (_HISTORY_KINDS | _CHUNK_KINDS)
        ]
        record_property("acp_tck_resume_no_replay_history_update_count", len(history_updates))
        assert not history_updates, (
            "session/resume with replayFrom omitted MUST NOT replay conversation history "
            f"before responding, but observed: {history_updates!r}"
        )


@pytest.mark.requirement("ACP-RESUME-204")
@pytest.mark.capability("capabilities.session")
async def test_resume_replays_retained_user_message_with_same_message_id(agent_launch, tmp_path):
    """ACP-RESUME-204. Absence of the message from replay is itself conforming (R5) -- SKIPs
    this check rather than FAILing it."""
    async with connected_agent(agent_launch) as agent:
        session_id, turn = await _session_with_history(
            agent, tmp_path, timeout=agent_launch.default_timeout
        )
        if turn.message_id is None:
            pytest.skip(
                "session/prompt response carried no usable messageId -- see ACP-PROMPT-201"
            )
        _response_entry, updates = await resume_session(
            agent,
            session_id,
            tmp_path,
            replay_from={"type": "start"},
            timeout=agent_launch.default_timeout,
        )
        user_message_updates = [
            update
            for _, entry in updates
            if (update := _update_of(entry)) is not None and update.get("sessionUpdate") == "user_message"
        ]
        if not user_message_updates:
            pytest.skip(
                "the retained user message was not replayed at all -- conforming per R5, "
                "nothing to check"
            )
        replayed_ids = {update.get("messageId") for update in user_message_updates}
        assert turn.message_id in replayed_ids, (
            f"replayed user_message messageId(s) {replayed_ids!r} do not include the original "
            f"prompt response's messageId {turn.message_id!r}"
        )


@pytest.mark.requirement("ACP-RESUME-205")
@pytest.mark.capability("capabilities.session")
async def test_resume_chunk_replay_preceded_by_whole_message_primer(
    agent_launch, tmp_path, record_property
):
    """ACP-RESUME-205. Vacuous -- recorded, never FAILed -- for an agent whose replay uses only
    whole-message updates (this fixture's own case: `_base.ConformingAgent` never emits a
    `*_chunk` update)."""
    async with connected_agent(agent_launch) as agent:
        session_id, _turn = await _session_with_history(
            agent, tmp_path, timeout=agent_launch.default_timeout
        )
        _response_entry, updates = await resume_session(
            agent,
            session_id,
            tmp_path,
            replay_from={"type": "start"},
            timeout=agent_launch.default_timeout,
        )
        replayed = [update for _, entry in updates if (update := _update_of(entry)) is not None]
        chunk_count = 0
        for index, update in enumerate(replayed):
            kind = update.get("sessionUpdate")
            if kind not in _CHUNK_KINDS:
                continue
            chunk_count += 1
            message_id = update.get("messageId")
            whole_kind = kind[: -len("_chunk")]
            preceded = any(
                prior.get("sessionUpdate") == whole_kind
                and prior.get("messageId") == message_id
                and prior.get("content") == []
                for prior in replayed[:index]
            )
            assert preceded, (
                f"replayed {kind} for messageId {message_id!r} was not preceded by a matching "
                f"whole-message primer (sessionUpdate={whole_kind!r}, content: []): {replayed!r}"
            )
        record_property("acp_tck_resume_replayed_chunk_count", chunk_count)


# --- session/list (ACP-LIST-201..204) ---


@pytest.mark.requirement("ACP-LIST-201")
@pytest.mark.capability("capabilities.session")
async def test_list_sessions_succeeds_and_validates(agent_launch, tmp_path):
    """ACP-LIST-201."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        entry = await list_sessions(agent, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/list did not succeed: {entry.text!r}"
        )
        sessions = msg["result"].get("sessions")
        assert isinstance(sessions, list), f"result.sessions must be an array, got {sessions!r}"
        issues = validate_agent_response("session/list", msg)
        assert not issues, f"session/list result failed schema validation: {issues!r}"


@pytest.mark.requirement("ACP-LIST-202")
@pytest.mark.capability("capabilities.session")
async def test_list_sessions_filtered_to_no_match_returns_empty_array(agent_launch, tmp_path):
    """ACP-LIST-202."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        unused_cwd = tmp_path / "no-session-here"
        entry = await list_sessions(agent, cwd=unused_cwd, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/list with a non-matching cwd filter must not error: {entry.text!r}"
        )
        sessions = msg["result"].get("sessions")
        assert sessions == [], f"result.sessions must be [], got {sessions!r}"


@pytest.mark.requirement("ACP-LIST-203")
@pytest.mark.capability("capabilities.session")
async def test_list_sessions_filtered_by_cwd_matches_requested_cwd(agent_launch, tmp_path):
    """ACP-LIST-203. A per-entry check only -- the reverse direction (a session at that `cwd`
    is guaranteed to be returned) is not asserted."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        entry = await list_sessions(agent, cwd=tmp_path, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/list filtered by cwd did not succeed: {entry.text!r}"
        )
        sessions = msg["result"].get("sessions") or []
        for session in sessions:
            assert isinstance(session, dict) and session.get("cwd") == str(tmp_path), (
                f"session/list filtered by cwd={tmp_path!r} returned a session with a "
                f"different cwd: {session!r}"
            )


@pytest.mark.requirement("ACP-LIST-204")
@pytest.mark.capability("capabilities.session")
async def test_list_sessions_cwds_are_absolute(agent_launch, tmp_path):
    """ACP-LIST-204."""
    async with connected_agent(agent_launch) as agent:
        await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        entry = await list_sessions(agent, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/list did not succeed: {entry.text!r}"
        )
        sessions = msg["result"].get("sessions") or []
        for session in sessions:
            cwd = session.get("cwd") if isinstance(session, dict) else None
            assert isinstance(cwd, str) and cwd.startswith("/"), (
                f"SessionInfo.cwd must be an absolute path, got {cwd!r}"
            )


# --- session/close (ACP-CLOSE-201 -- ACP-CLOSE-202 lives in test_cancel.py) ---


@pytest.mark.requirement("ACP-CLOSE-201")
@pytest.mark.capability("capabilities.session")
async def test_close_idle_session_succeeds(agent_launch, tmp_path):
    """ACP-CLOSE-201. `session/close` of a live, idle session (no foreground work in flight) --
    distinct from `ACP-CLOSE-202`'s cancellation side effect."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        entry = await close_session(agent, session_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/close of an idle session did not succeed: {entry.text!r}"
        )
        issues = validate_agent_response("session/close", msg)
        assert not issues, f"session/close result failed schema validation: {issues!r}"


# --- session/delete (ACP-DELETE-201..203) ---


@pytest.mark.requirement("ACP-DELETE-201")
@pytest.mark.capability("capabilities.session.delete")
async def test_delete_existing_session_succeeds(agent_launch, tmp_path):
    """ACP-DELETE-201."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        entry = await delete_session(agent, session_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/delete of an existing session did not succeed: {entry.text!r}"
        )


@pytest.mark.requirement("ACP-DELETE-202")
@pytest.mark.capability("capabilities.session.delete")
async def test_deleted_session_no_longer_listed(agent_launch, tmp_path):
    """ACP-DELETE-202. SKIPs when the session was never observed in `session/list` in the first
    place -- nothing to compare against."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        before_entry = await list_sessions(agent, timeout=agent_launch.default_timeout)
        before_msg = before_entry.parsed
        before_ids = {
            s.get("sessionId")
            for s in ((before_msg.get("result") or {}).get("sessions") or [])
            if isinstance(before_msg, dict) and isinstance(s, dict)
        }
        if session_id not in before_ids:
            pytest.skip("session/list never reported this session in the first place")

        delete_entry = await delete_session(agent, session_id, timeout=agent_launch.default_timeout)
        delete_msg = delete_entry.parsed
        assert isinstance(delete_msg, dict) and isinstance(delete_msg.get("result"), dict), (
            f"session/delete did not succeed: {delete_entry.text!r}"
        )

        after_entry = await list_sessions(agent, timeout=agent_launch.default_timeout)
        after_msg = after_entry.parsed
        after_ids = {
            s.get("sessionId")
            for s in ((after_msg.get("result") or {}).get("sessions") or [])
            if isinstance(after_msg, dict) and isinstance(s, dict)
        }
        assert session_id not in after_ids, (
            f"deleted session {session_id!r} still appears in session/list: {after_ids!r}"
        )


@pytest.mark.requirement("ACP-DELETE-203")
@pytest.mark.capability("capabilities.session.delete")
async def test_delete_unknown_session_succeeds_silently(agent_launch, tmp_path):
    """ACP-DELETE-203 (ADVISORY). Deleting an already-deleted or never-created sessionId SHOULD
    succeed silently, not error."""
    async with connected_agent(agent_launch) as agent:
        entry = await delete_session(agent, "tck-never-created", timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/delete of an unknown sessionId should succeed silently: {entry.text!r}"
        )


# --- additionalDirectories (ACP-ADDDIRS-201/202) ---


@pytest.mark.requirement("ACP-ADDDIRS-201")
@pytest.mark.capability("capabilities.session.additionalDirectories")
async def test_new_session_with_additional_directory_accepted(agent_launch, tmp_path):
    """ACP-ADDDIRS-201."""
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "additionalDirectories": [str(extra_dir)]}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/new with an absolute additionalDirectories entry did not succeed: "
            f"{entry.text!r}"
        )


@pytest.mark.requirement("ACP-ADDDIRS-202")
@pytest.mark.capability("capabilities.session.additionalDirectories")
async def test_resume_session_with_additional_directory_accepted(agent_launch, tmp_path):
    """ACP-ADDDIRS-202."""
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    async with obtain_resumable_session(
        agent_launch, tmp_path, timeout=agent_launch.default_timeout
    ) as (agent, session_id, _entry):
        response_entry, _updates = await resume_session(
            agent,
            session_id,
            tmp_path,
            additional_directories=[str(extra_dir)],
            timeout=agent_launch.default_timeout,
        )
        msg = response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/resume with an absolute additionalDirectories entry did not succeed: "
            f"{response_entry.text!r}"
        )


# --- MCP servers (ACP-MCP-201/202, INFORMATIONAL) ---


@pytest.mark.requirement("ACP-MCP-201")
@pytest.mark.capability("capabilities.session.mcp.stdio")
async def test_new_session_with_stdio_mcp_server_recorded(agent_launch, tmp_path, record_property):
    """ACP-MCP-201 (INFORMATIONAL). Never asserts on the outcome -- see the requirements module
    docstring's judgment-call note."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/new",
            {
                "cwd": str(tmp_path),
                "mcpServers": [
                    {"name": "tck-stdio", "command": "/bin/nonexistent-tck-mcp-server", "args": []}
                ],
            },
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        accepted = isinstance(msg, dict) and isinstance(msg.get("result"), dict)
        record_property("acp_tck_mcp_stdio_session_new_accepted", accepted)


@pytest.mark.requirement("ACP-MCP-202")
@pytest.mark.capability("capabilities.session.mcp.http")
async def test_new_session_with_http_mcp_server_recorded(agent_launch, tmp_path, record_property):
    """ACP-MCP-202 (INFORMATIONAL). Never asserts on the outcome."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request(
            "session/new",
            {
                "cwd": str(tmp_path),
                "mcpServers": [
                    {"name": "tck-http", "url": "http://127.0.0.1:1/tck-nonexistent"}
                ],
            },
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        accepted = isinstance(msg, dict) and isinstance(msg.get("result"), dict)
        record_property("acp_tck_mcp_http_session_new_accepted", accepted)
