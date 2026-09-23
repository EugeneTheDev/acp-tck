"""Shared helpers for conformance tests."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest

from tck.common.harness import AgentLaunch, AgentProcess, AgentTimeout, TranscriptEntry
from tck.common.plugin import current_auth_method_id, current_initialize_auth_methods, register_active_process
from tck.v1.protocol import AUTHENTICATION_REQUIRED, METHOD_NOT_FOUND, PROTOCOL_VERSION


@contextlib.asynccontextmanager
async def connected_agent(
    launch: AgentLaunch,
    *,
    handshake: bool = True,
    client_capabilities: dict[str, Any] | None = None,
) -> AsyncIterator[AgentProcess]:
    """Spawn a fresh `AgentProcess` for `launch`, optionally perform an `initialize` handshake,
    yield it, and always close it.

    Registers the process with the plugin's failure-diagnostics tracker (`tck.common.plugin`) so a
    test failure attaches its transcript and stderr to the pytest report, regardless of which
    requirement(s) the test is checking.

    When `handshake` is true and `--tck-auth-method` was given (`current_auth_method_id()`),
    an `authenticate` call for that method id is sent right after `initialize` -- this lets
    every existing/new test that calls `new_session()` afterwards just work against an agent
    that requires authentication before `session/new`, without each test having to know about
    auth at all. Note: this auto-authenticate step only fires for `handshake=True` callers --
    `test_initialize.py::test_full_exchange_validates_against_schema` deliberately drives its
    own `initialize` with `handshake=False` and is out of scope for auth-gating (it never
    exercises an auth-gated fixture).
    """
    async with AgentProcess(launch) as agent:
        register_active_process(agent)
        if handshake:
            req_id = await agent.send_request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "clientCapabilities": client_capabilities
                    if client_capabilities is not None
                    else {},
                },
            )
            await agent.wait_for_response(req_id, timeout=launch.startup_timeout)
            method_id = current_auth_method_id()
            if method_id is not None:
                auth_id = await agent.send_request("authenticate", {"methodId": method_id})
                auth_entry = await agent.wait_for_response(auth_id, timeout=launch.startup_timeout)
                auth_msg = auth_entry.parsed
                # `authenticate` succeeding is never a MANDATORY assertion -- a real agent may
                # legitimately reject bad/expired/cancelled credentials. An error response here
                # means the TCK can't exercise session-dependent tests with this --auth-method,
                # so they SKIP with a clear reason instead of failing on an AssertionError.
                if not (isinstance(auth_msg, dict) and isinstance(auth_msg.get("result"), dict)):
                    detail = (
                        auth_msg.get("error") if isinstance(auth_msg, dict) else None
                    ) or auth_entry.text
                    pytest.skip(
                        f"AUTH-GATED: authenticate with methodId={method_id!r} failed: {detail!r} "
                        "-- check --tck-auth-method"
                    )
        yield agent


def skip_if_auth_gated(entry: TranscriptEntry) -> None:
    """Skip the current test, with a message pointing at `--auth-method`, if `entry` (a
    `session/new` response) is the `AUTHENTICATION_REQUIRED` (`-32000`) error.

    v1 never requires an agent to gate `session/new` behind authentication (it's a MAY, not a
    MUST), so this is not itself a conformance failure; but it does mean the TCK cannot exercise
    session/prompt-dependent requirements against this agent unless the harness operator
    supplies a valid `--auth-method <id>`. The message is prefixed with the literal marker
    string `AUTH-GATED:` so `tck.common.plugin` can detect this specific reason (as opposed to
    an ordinary capability-not-advertised skip) and set `Verdict.blocked_by_auth`.

    Only excuses the `-32000` when the cached `initialize` result actually advertised at least
    one `authMethods` entry (AUTH-A1) -- an agent that advertises none and still returns
    `-32000` has no defined remedy; left as an ordinary, un-excused failure (see
    `ACP-AUTH-005`), not something the TCK can route around.
    """
    msg = entry.parsed
    if not (
        isinstance(msg, dict)
        and isinstance(msg.get("error"), dict)
        and msg["error"].get("code") == AUTHENTICATION_REQUIRED
        and current_auth_method_id() is None
    ):
        return
    if not current_initialize_auth_methods():
        return  # AUTH-A1: no advertised authMethods -- not excusable, let the caller's own assert fail
    pytest.skip(
        "AUTH-GATED: session/new returned -32000 (authentication required) and no "
        "--auth-method was given; pass --auth-method <id> (one of the ids advertised in "
        "initialize's authMethods) to test session-dependent requirements against this agent"
    )


async def new_session(agent: AgentProcess, cwd: Path, *, timeout: float | None = None) -> str:
    """Send `session/new` with an absolute `cwd` and no MCP servers; return the `sessionId`
    from the response.

    Raises `AssertionError` with a protocol-level message (not a bare `TypeError`/`KeyError`)
    if the response is not a well-formed success -- callers see a diagnosis, not a Python
    traceback, when the agent errors or replies with a malformed shape.

    SKIPs (via `skip_if_auth_gated`) rather than failing when the agent requires authentication
    and no `--auth-method` was configured."""
    req_id = await agent.send_request("session/new", {"cwd": str(cwd), "mcpServers": []})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    skip_if_auth_gated(entry)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    session_id = msg["result"].get("sessionId")
    assert isinstance(session_id, str), f"session/new result has no string sessionId: {msg['result']!r}"
    return session_id


def skip_if_version_mismatch(init_result: dict[str, Any]) -> None:
    """Skip with the `VERSION-MISMATCH: ` marker (`tck.common.plugin`'s `_VERSION_MISMATCH_MARKER`
    substring, scanned by `_build_report()` to set `Verdict.blocked_by_version_mismatch`) unless
    `init_result`'s negotiated `protocolVersion` is this suite's own `PROTOCOL_VERSION` (1).

    An agent negotiating a different version isn't thereby "broken" -- `ACP-INIT-001`/`003`
    judge the negotiation outcome itself normally. But tests asserting v1-shape requirements on
    that result (`ACP-INIT-002`/`004`, `ACP-SCHEMA-001`/`002`, `ACP-META-001`, `ACP-PROMPT-001`)
    can't honestly judge a result the agent never claimed was v1-shaped; call this right after
    such a test has its own `init_result` in hand, before evaluating any v1-shape assertion."""
    negotiated = init_result.get("protocolVersion")
    if negotiated != PROTOCOL_VERSION:
        pytest.skip(
            f"VERSION-MISMATCH: negotiated protocolVersion={negotiated!r}, expected "
            f"{PROTOCOL_VERSION!r} -- this agent does not speak v1, so its result cannot be "
            "judged against v1-only shape requirements"
        )


def quiet_period(timeout: float) -> float:
    """The heuristic "nothing more is coming" wait used by tests that conclude absence (e.g. "no
    response to a notification"). Derived from `--tck-timeout` rather than a hard-coded
    sub-second constant, so it scales on a slow/loaded machine; clamped so it's never flaky-short
    nor dominates the suite's runtime."""
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
    `clientCapabilities: {}` -- `test_client_capabilities.py` turns "the agent called an
    unadvertised method" into its own negative tests using this list."""
    cancelled_at_index: int | None = None
    """The transcript index at which `run_prompt` sent `session/cancel`, or `None` if
    `on_cancel` was false or the prompt resolved before a cancel was ever sent (a race the TCK
    cannot always avoid -- see `test_cancel.py`)."""
    action_response: TranscriptEntry | None = None
    """The response to `on_action`'s request, if `on_action` was given and fired (see
    `run_prompt`'s docstring) -- `None` if `on_action` was not given, or was given but the
    prompt resolved before it ever fired."""
    action_sent_at_index: int | None = None
    """The transcript index at which `on_action`'s request was sent, mirroring
    `cancelled_at_index` -- `None` if `on_action` was not given or never fired."""


async def run_prompt(
    agent: AgentProcess,
    session_id: str,
    blocks: list[dict[str, Any]],
    *,
    on_cancel: bool = False,
    on_action: Callable[[], Awaitable[Any]] | None = None,
    cancel_wait: float = 0.5,
    extra_params: dict[str, Any] | None = None,
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

    `on_action`, if given, is a zero-argument async callable fired at that same trigger point
    (instead of, or alongside, `on_cancel`'s `session/cancel`) -- it must send whatever request
    it wants (e.g. `session/close`) and return the id used. Whatever else the agent sends while
    the mock client is waiting for the prompt's own response -- including that action's own
    response, and any agent -> client request the action's send provokes (e.g. resolving an
    in-flight `session/request_permission` as cancelled) -- is still handled by this same
    dispatcher: nothing sent during an in-flight prompt turn is ever silently dropped. The
    action's response comes back as `PromptTurn.action_response`.

    A subtlety: an agent that emits an update and then *immediately* replies may already have
    written its response before we decide to cancel -- we just haven't read it yet. To keep
    `cancelled_at_index` honest, we give a brief (`cancel_race_peek(timeout)`) look for the
    response right after an update and before committing to cancel; if it's already there, we
    return it with `cancelled_at_index=None` (a race), as if it arrived before cancel was ever
    considered.

    `extra_params`, if given, is merged into the `session/prompt` request's own params
    (e.g. `{"_meta": {...}}` for ACP-META-001) -- it never overrides `sessionId`/`prompt`.
    """
    params = {"sessionId": session_id, "prompt": blocks}
    if extra_params:
        params.update(extra_params)
    prompt_id = await agent.send_request("session/prompt", params)
    updates: list[tuple[int, TranscriptEntry]] = []
    client_requests_seen: list[TranscriptEntry] = []
    cancelled_at_index: int | None = None
    action_response: TranscriptEntry | None = None
    action_sent_at_index: int | None = None
    action_id: Any = None
    trigger_armed = on_cancel or on_action is not None
    trigger_sent = False

    loop = asyncio.get_running_loop()
    overall_deadline = loop.time() + timeout
    trigger_deadline = loop.time() + cancel_wait if trigger_armed else None
    peek_timeout = cancel_race_peek(timeout)

    async def _fire_trigger() -> None:
        nonlocal trigger_sent, cancelled_at_index, action_id, action_sent_at_index
        if trigger_sent:
            return
        trigger_sent = True
        if on_cancel:
            await agent.send_notification("session/cancel", {"sessionId": session_id})
            cancelled_at_index = len(agent.transcript) - 1
        if on_action is not None:
            action_id = await on_action()
            action_sent_at_index = len(agent.transcript) - 1

    async def _handle_one(entry: TranscriptEntry) -> PromptTurn | None:
        """Dispatch one already-read line. Returns the finished `PromptTurn` if `entry` was the
        prompt's own response, else `None` after doing whatever mock-client bookkeeping it
        implies (recording an update, answering a permission/other request, or recording the
        `on_action` request's own response)."""
        nonlocal action_response
        msg = entry.parsed
        if not isinstance(msg, dict):
            return None
        if entry.matches_id(prompt_id):
            if action_id is not None and action_response is None:
                # The prompt's own response arrived before the `on_action` request's response --
                # a valid ordering (no claim is made about relative order). Give the action's
                # response the same short already-in-the-pipe-or-not look `cancel_race_peek`
                # gives an update, so it isn't lost just because we're about to return.
                try:
                    peek_entry = await agent.read_line(timeout=peek_timeout)
                except AgentTimeout:
                    pass
                else:
                    await _handle_one(peek_entry)
            return PromptTurn(
                entry,
                updates,
                client_requests_seen,
                cancelled_at_index,
                action_response,
                action_sent_at_index,
            )
        if action_id is not None and entry.matches_id(action_id):
            action_response = entry
            return None

        index = agent.transcript.index(entry)
        method = msg.get("method")
        if method == "session/update":
            updates.append((index, entry))
            return None

        if method == "session/request_permission" and "id" in msg:
            options = (msg.get("params") or {}).get("options") or []
            if trigger_sent:
                # Once `session/cancel` or the `on_action` request (e.g. `session/close`) has
                # fired, a real client would resolve an in-flight permission prompt as
                # cancelled rather than picking an option on the user's behalf.
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
    # ACP-PROMPT-002 / ACP-CANCEL-002 -- process them exactly like freshly-read lines before
    # ever blocking on the network.
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

        if trigger_armed and not trigger_sent:
            wait_remaining = trigger_deadline - now  # type: ignore[operator]
            read_timeout = (
                min(remaining, wait_remaining) if wait_remaining > 0 else min(remaining, 0.05)
            )
        else:
            read_timeout = remaining

        try:
            entry = await agent.read_line(timeout=read_timeout)
        except AgentTimeout:
            if trigger_armed and not trigger_sent:
                await _fire_trigger()
                continue
            raise

        result = await _handle_one(entry)
        if result is not None:
            return result

        if (
            trigger_armed
            and not trigger_sent
            and isinstance(entry.parsed, dict)
            and entry.parsed.get("method") == "session/update"
        ):
            try:
                peek_entry = await agent.read_line(timeout=peek_timeout)
            except AgentTimeout:
                await _fire_trigger()
            else:
                peek_result = await _handle_one(peek_entry)
                if peek_result is not None:
                    return peek_result
                await _fire_trigger()
