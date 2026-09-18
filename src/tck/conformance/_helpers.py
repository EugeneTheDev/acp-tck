"""Shared helpers for conformance tests."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from tck.harness import AgentLaunch, AgentProcess, AgentTimeout, TranscriptEntry
from tck.plugin import register_active_process
from tck.protocol import METHOD_NOT_FOUND, PROTOCOL_VERSION


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


async def new_session(agent: AgentProcess, cwd: Path, *, timeout: float | None = None) -> str:
    """Send `session/new` with an absolute `cwd` and no MCP servers; return the `sessionId`
    from the response (Req 9, `.agents/research/acp-v1-protocol-surface.md` §3).

    Raises `AssertionError` with a protocol-level message (not a bare `TypeError`/`KeyError`)
    if the response is not a well-formed success -- callers see a diagnosis, not a Python
    traceback, when the agent errors or replies with a malformed shape (review N14)."""
    req_id = await agent.send_request("session/new", {"cwd": str(cwd), "mcpServers": []})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    session_id = msg["result"].get("sessionId")
    assert isinstance(session_id, str), f"session/new result has no string sessionId: {msg['result']!r}"
    return session_id


def quiet_period(timeout: float) -> float:
    """The heuristic "nothing more is coming" wait used by tests that conclude absence (e.g. "no
    response to a notification", "no update follows the response") -- derived from the same
    `--tck-timeout` users are told to raise for a slow agent, instead of a hard-coded
    sub-second constant that is a false negative by construction on a loaded machine (review
    S9). Clamped to a sane range: never so short a fast local test is flaky, never so long a
    single quiet-period check dominates the suite's runtime."""
    return max(0.5, min(2.0, timeout / 10))


def cancel_race_peek(timeout: float) -> float:
    """Like `quiet_period`, but for the much shorter peek `run_prompt` does right after an
    update and before committing to send `session/cancel` (see its docstring) -- this only
    needs to be long enough to catch a response that is already sitting in the pipe, not to
    conclude general absence, so it stays a small fraction of `quiet_period`."""
    return max(0.05, min(0.5, timeout / 50))


@dataclass(frozen=True)
class PromptTurn:
    """The outcome of one `session/prompt` turn driven by `run_prompt`."""

    response_entry: TranscriptEntry
    """The transcript entry for the `session/prompt` response."""
    updates: list[tuple[int, TranscriptEntry]] = field(default_factory=list)
    """`(transcript_index, entry)` for every `session/update` notification observed, in the
    order they arrived on the wire -- and therefore strictly before `response_entry`, since
    they were read off the same stdout stream before the matching response line."""
    client_requests_seen: list[TranscriptEntry] = field(default_factory=list)
    """Every agent -> client request the mock client had to answer during the turn:
    `session/request_permission` (answered normally) plus anything else (`fs/*`, `terminal/*`,
    `elicitation/create`, ...), which gets `-32601` since our client advertised
    `clientCapabilities: {}` -- slice 6 turns "the agent called an unadvertised method" into its
    own negative tests using this list."""
    cancelled_at_index: int | None = None
    """The transcript index at which `run_prompt` sent `session/cancel`, or `None` if
    `on_cancel` was false or the prompt resolved before a cancel was ever sent (a race the TCK
    cannot always avoid -- see `test_cancel.py`)."""


async def run_prompt(
    agent: AgentProcess,
    session_id: str,
    blocks: list[dict[str, Any]],
    *,
    on_cancel: bool = False,
    cancel_wait: float = 0.5,
    timeout: float,
) -> PromptTurn:
    """Drive one `session/prompt` turn, acting as a minimal mock ACP client for whatever the
    agent sends meanwhile, until the prompt's own response arrives.

    While waiting:
    - `session/request_permission` is answered `{"outcome": {"outcome": "selected",
      "optionId": <first option's optionId>}}`, or `{"outcome": {"outcome": "cancelled"}}` once
      `session/cancel` has been sent for this turn (`docs/protocol/v1/prompt-turn.mdx:328`).
    - any other agent -> client request (`fs/*`, `terminal/*`, `elicitation/create`, ...) gets
      `-32601`, since the mock client advertised `clientCapabilities: {}`; the request is also
      recorded on `PromptTurn.client_requests_seen`.
    - `session/update` notifications are recorded in order.

    If `on_cancel` is true, `session/cancel` is sent for `session_id` as soon as either the
    first `session/update` arrives or `cancel_wait` seconds have elapsed, whichever is first --
    an agent that emits nothing before responding is still a valid target for cancellation, it
    is just unlikely the cancel will land while the turn is still in flight (see `test_cancel.py`
    for how the resulting race is handled).

    A subtlety: an agent that emits an update and then *immediately* replies (e.g. a non-hanging
    fixture) may have already written its response to the pipe before we ever decide to send
    `session/cancel` -- we just haven't read it yet. If we committed to sending cancel purely
    because we had just read an update, we would misreport "cancel was sent while the turn was
    still in flight" for a turn that, in reality, had already finished. To keep
    `cancelled_at_index` an honest signal, we give a brief (`cancel_race_peek(timeout)`)
    non-blocking-ish look for the response immediately after an update and before committing to
    cancel; if the
    response is already sitting there, we return it with `cancelled_at_index=None` (a race),
    exactly as if it had arrived before we ever considered cancelling.
    """
    prompt_id = await agent.send_request(
        "session/prompt", {"sessionId": session_id, "prompt": blocks}
    )
    updates: list[tuple[int, TranscriptEntry]] = []
    client_requests_seen: list[TranscriptEntry] = []
    cancelled_at_index: int | None = None
    cancel_sent = False

    loop = asyncio.get_running_loop()
    overall_deadline = loop.time() + timeout
    cancel_deadline = loop.time() + cancel_wait if on_cancel else None
    peek_timeout = cancel_race_peek(timeout)

    async def _send_cancel() -> None:
        nonlocal cancel_sent, cancelled_at_index
        if not cancel_sent:
            await agent.send_notification("session/cancel", {"sessionId": session_id})
            cancel_sent = True
            cancelled_at_index = len(agent.transcript) - 1

    async def _handle_one(entry: TranscriptEntry) -> PromptTurn | None:
        """Dispatch one already-read line. Returns the finished `PromptTurn` if `entry` was the
        prompt's own response, else `None` after doing whatever mock-client bookkeeping it
        implies (recording an update, answering a permission/other request)."""
        msg = entry.parsed
        if not isinstance(msg, dict):
            return None
        if entry.matches_id(prompt_id):
            return PromptTurn(entry, updates, client_requests_seen, cancelled_at_index)

        index = agent.transcript.index(entry)
        method = msg.get("method")
        if method == "session/update":
            updates.append((index, entry))
            return None

        if method == "session/request_permission" and "id" in msg:
            options = (msg.get("params") or {}).get("options") or []
            if cancelled_at_index is not None:
                outcome: dict[str, Any] = {"outcome": "cancelled"}
            else:
                first_option_id = options[0].get("optionId") if options else None
                outcome = {"outcome": "selected", "optionId": first_option_id}
            await agent.send_message(
                {"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": outcome}}
            )
            client_requests_seen.append(entry)
            return None

        if method is not None and "id" in msg:
            # Any other agent -> client request: our mock client advertised no capabilities.
            client_requests_seen.append(entry)
            await agent.send_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
                }
            )
            return None

        # Any other agent-authored notification (e.g. `elicitation/complete`) -- not our concern
        # here, ignore and keep waiting for the prompt's own response.
        return None

    # Lines read while waiting on `initialize`/`session/new` (or, in principle, an earlier
    # `read_line` of the caller's own) sit in `pending()` and would otherwise be invisible to
    # ACP-PROMPT-002 / ACP-CANCEL-002 (review N15) -- process them exactly like freshly-read
    # lines before ever blocking on the network.
    for pending_entry in agent.pending():
        pending_result = await _handle_one(pending_entry)
        if pending_result is not None:
            return pending_result

    while True:
        now = loop.time()
        remaining = overall_deadline - now
        if remaining <= 0:
            raise AgentTimeout(
                f"session/prompt {prompt_id!r} did not resolve within {timeout}s",
                agent.transcript,
                stderr=agent.stderr_text(),
            )

        if on_cancel and not cancel_sent:
            wait_remaining = cancel_deadline - now  # type: ignore[operator]
            read_timeout = (
                min(remaining, wait_remaining) if wait_remaining > 0 else min(remaining, 0.05)
            )
        else:
            read_timeout = remaining

        try:
            entry = await agent.read_line(timeout=read_timeout)
        except AgentTimeout:
            if on_cancel and not cancel_sent:
                await _send_cancel()
                continue
            raise

        result = await _handle_one(entry)
        if result is not None:
            return result

        if (
            on_cancel
            and not cancel_sent
            and isinstance(entry.parsed, dict)
            and entry.parsed.get("method") == "session/update"
        ):
            try:
                peek_entry = await agent.read_line(timeout=peek_timeout)
            except AgentTimeout:
                await _send_cancel()
            else:
                peek_result = await _handle_one(peek_entry)
                if peek_result is not None:
                    return peek_result
                await _send_cancel()
