"""Shared helpers for the v2 conformance suite.

Slice V2-1b scope was `connected_agent()`, `new_session()`, and `skip_if_version_mismatch()`.
Slice V2-2a adds the v2 mock-client prompt driver: `run_prompt()`/`PromptTurn`/
`cancel_race_peek()`, the v2 counterpart of `tck.v1.conformance._helpers`'s same-named machinery
-- deliberately a separate, non-shared implementation (`.agents/plan.md` D6: "honest duplication,
not shared machinery"), because the v2 turn-end contract is fundamentally different: v1's
`session/prompt` response *is* the turn result (carries `stopReason`); v2's response is only an
acceptance receipt (`{messageId}`) sent at insertion time, and the turn's end is learned solely
from a `session/update` `state_update {state: "idle"}` notification
(`.agents/research/acp-v2-prompt-lifecycle.md` "Answer", §4). No v2 auth flow is in scope yet
either (`skip_if_auth_gated`'s v1 counterpart still has no v2 twin).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest

from tck.common.harness import AgentLaunch, AgentProcess, AgentTimeout, TranscriptEntry
from tck.common.plugin import current_auth_method_id, register_active_process

from .. import SPEC
from ..protocol import METHOD_NOT_FOUND, PROTOCOL_VERSION


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


def cancel_race_peek(timeout: float) -> float:
    """Like v1's `cancel_race_peek` (same formula, deliberately re-implemented rather than
    imported -- `.agents/plan.md` D6): a short, bounded look for a line that may already be
    sitting in the pipe, used by `run_prompt` right after it decides the turn has ended, to give
    a trailing/out-of-order response (e.g. `on_action`'s) one last chance to be captured before
    returning."""
    return max(0.05, min(0.5, timeout / 50))


def quiet_period(timeout: float) -> float:
    """V2-2b twin of v1's `quiet_period` (identical formula, deliberately re-implemented rather
    than imported -- `.agents/plan.md` D6, "honest duplication, not shared machinery"): the
    heuristic "nothing more is coming" wait used by INFORMATIONAL probes that conclude absence
    (e.g. `ACP-INFO-CONCURRENT-201`'s "did a second, concurrent `session/prompt` get a
    response at all") -- derived from `--tck-timeout` rather than a hard-coded sub-second
    constant, clamped to a sane range."""
    return max(0.5, min(2.0, timeout / 10))


@dataclass(frozen=True)
class PromptTurn:
    """The outcome of one v2 `session/prompt` turn driven by `run_prompt`.

    Unlike v1's `PromptTurn` (whose `response_entry` *is* the turn result), v2's response is only
    an acceptance receipt -- the turn's actual outcome (`running_seen`/`idle_update`/
    `stop_reason`) is learned entirely from `session/update` notifications
    (`.agents/research/acp-v2-prompt-lifecycle.md` §4).
    """

    response_entry: TranscriptEntry
    """The transcript entry for the `session/prompt` response (the acceptance receipt, or a
    JSON-RPC error if the agent rejected the prompt before insertion)."""
    message_id: str | None
    """The response result's `messageId`, if it was present and a string; `None` otherwise
    (including when the response was a JSON-RPC error, or a malformed/missing `messageId`)."""
    running_seen: bool
    """Whether a `state_update {state: "running"}` for `session_id` was observed at any point
    during the turn."""
    idle_update: TranscriptEntry | None
    """The `session/update` entry carrying the turn-ending `state_update {state: "idle"}` for
    `session_id` -- i.e. the one that satisfied the turn-end predicate (see `run_prompt`) --
    or `None` if the turn ended via a JSON-RPC error instead, or via the caller's
    `--timeout`/`--tck-test-timeout` giving up (in which case `run_prompt` never returns at all;
    it raises `AgentTimeout`)."""
    stop_reason: Any = None
    """The terminating idle's `stopReason` value, exactly as sent (including if it is missing,
    `None`, or an illegal value -- validity is the caller's job, not the driver's). `None` when
    `idle_update` is `None`."""
    updates: list[tuple[int, TranscriptEntry]] = field(default_factory=list)
    """`(transcript_index, entry)` for every `session/update` notification observed during the
    turn, in the order they arrived on the wire -- regardless of which `sessionId` they carried
    (a misattributed `sessionId` is exactly what `ACP-PROMPT-205` checks for; the driver still
    records it rather than discarding it)."""
    client_requests_seen: list[TranscriptEntry] = field(default_factory=list)
    """Every agent -> client request the mock client had to answer during the turn:
    `session/request_permission` (answered normally) plus anything else (`elicitation/create`,
    and anything v1-shaped like `fs/*`/`terminal/*`, which do not exist as client methods in v2
    at all), which gets `-32601` since our mock client advertises `capabilities: {}` -- a later
    slice (V2-2b) turns "the agent called an unadvertised/nonexistent method" into its own
    negative tests using this list."""
    cancelled_at_index: int | None = None
    """The transcript index at which `run_prompt` sent `session/cancel`, or `None` if
    `on_cancel` was false or the prompt turn ended before a cancel was ever sent."""
    action_response: TranscriptEntry | None = None
    """The response to `on_action`'s request, if `on_action` was given and fired -- `None`
    otherwise (mirrors v1's `PromptTurn.action_response`, for a future `session/close`-mid-turn
    slice; V2-2a itself has no test that uses `on_action`)."""
    action_sent_at_index: int | None = None
    """The transcript index at which `on_action`'s request was sent, mirroring
    `cancelled_at_index`."""


async def run_prompt(
    agent: AgentProcess,
    session_id: str,
    blocks: list[dict[str, Any]],
    *,
    on_cancel: bool = False,
    on_action: Callable[[], Awaitable[Any]] | None = None,
    cancel_wait: float = 0.5,
    cancel_meta: dict[str, Any] | None = None,
    extra_params: dict[str, Any] | None = None,
    timeout: float,
) -> PromptTurn:
    """Drive one v2 `session/prompt` turn to completion, acting as a minimal mock ACP client for
    whatever the agent sends meanwhile.

    The v1 `run_prompt` contract inverts in v2: the `session/prompt` response is no longer the
    turn's terminator (it is only an acceptance receipt, `{messageId}`, sent at insertion time --
    `.agents/research/acp-v2-prompt-lifecycle.md` P5-P7). The turn ends only when a
    `session/update` `state_update {state: "idle"}` for `session_id` is observed
    (`prompt-lifecycle.mdx:348`), or when the prompt is rejected outright with a JSON-RPC error
    (no insertion happened, so no further obligations apply -- P6). Every wait below is bounded
    by `timeout`, so a non-conforming agent that never reaches either terminator produces an
    `AgentTimeout` (a FAIL for whatever the caller was asserting), never a hang.

    **Turn-end predicate** (`.agents/research/acp-v2-prompt-lifecycle.md` "Mock-client prompt
    driver design note", point 3): a `state_update {state: "idle"}` observed for `session_id`
    ends the turn iff it carries a `stopReason`, *or* a `state_update {state: "running"}` for
    `session_id` was observed earlier in the same call. This deliberately excludes the legal
    "session-ready idle" a spec-conforming agent may send with no preceding prompt at all (e.g.
    right after `session/new` -- research §4 point 2, observed live in the Python SDK's own v2
    test agent) from ever being mistaken for a turn's end. A bare idle matching neither condition
    is simply not treated as a terminator; it is recorded like any other update, and reading
    continues (bounded by `timeout` as always) -- this is a deliberate simplification of the
    design note's "hold as a candidate terminator, wait one `quiet_period`" refinement: no
    requirement or fixture in this slice needs that extra nuance, and every wait already has a
    hard, honest bound.

    **Tolerating an initial ready-idle sent *before* `session/prompt`.** Unlike v1's
    `run_prompt`, this does **not** drain `agent.pending()` before sending the request: doing so
    would replay a ready-idle the caller's own earlier reads (e.g. after `session/new`) left
    buffered there, and -- since it carries no `stopReason` and no `running` precedes it in
    *this* call -- it is harmless either way, but draining it here would make its transcript
    index appear to be part of this turn's own `updates`, which is not accurate. Any such
    notification stays in `agent.pending()` for the caller to inspect directly if it cares
    (mirrors `idle_before_running.py`'s fixture design: the ready-idle is sent before
    `session/prompt` is even issued).

    While waiting:
    - `session/update` notifications are recorded (`updates`), in order, regardless of which
      `sessionId` they carry -- a mismatched one is `ACP-PROMPT-205`'s evidence, not the driver's
      business to filter out. Only `state_update`s whose enclosing `sessionId == session_id` are
      considered for `running_seen`/the turn-end predicate.
    - `session/request_permission` is answered `{"outcome": {"outcome": "selected", "optionId":
      <first option's optionId>}}`, or `{"outcome": {"outcome": "cancelled"}}` once
      `session/cancel` has actually been sent for this turn (`tool-calls.mdx:304`) -- defensively
      tolerates `options: []` (no indexing crash) rather than assuming a conforming agent.
    - any other agent -> client request gets `-32601` (the mock client advertises
      `capabilities: {}`), and is recorded on `PromptTurn.client_requests_seen`.

    `cancel_meta`, if given, is merged into the `session/cancel` notification's params as `_meta`
    (Slice V2-3, `ACP-CANCEL-206`'s "accepts a cancel that additionally carries `_meta`" check) --
    `None` (the default) sends the bare `{"sessionId": session_id}` params every other caller
    relies on.

    `on_cancel`/`on_action`/`cancel_wait`/`extra_params` mirror v1's `run_prompt` in shape and
    fallback timing, but **not** in trigger condition (Slice V2-3,
    `.agents/research/acp-v2-cancellation-and-batching.md` "Testability notes" > "The v2 cancel
    driver"): v1 fires its trigger on the *first* `session/update` of any kind; v2 fires it
    specifically on the transition to `state_update {state: "running"}` for `session_id` -- the
    MUST-guaranteed turn-start marker (`prompt-lifecycle.mdx:159`) -- because v2's `user_message`
    echo update (which may arrive before `running`) is not itself evidence that foreground work
    has started. If `session_id` never reaches `running` (e.g. a non-conforming agent, or the
    prompt is rejected outright), the trigger still fires once `cancel_wait` elapses, exactly as
    in v1.

    Callers must serialize prompts per session themselves (never call this a second time for the
    same session before a previous call has returned) -- v2 leaves concurrent `session/prompt`
    on one session unspecified, and both reference agents reject it
    (`.agents/research/acp-v2-prompt-lifecycle.md` X1).
    """
    params = {"sessionId": session_id, "prompt": blocks}
    if extra_params:
        params.update(extra_params)
    prompt_id = await agent.send_request("session/prompt", params)

    response_entry: TranscriptEntry | None = None
    message_id: str | None = None
    running_seen = False
    idle_update: TranscriptEntry | None = None
    stop_reason: Any = None
    updates: list[tuple[int, TranscriptEntry]] = []
    client_requests_seen: list[TranscriptEntry] = []
    cancelled_at_index: int | None = None
    action_response: TranscriptEntry | None = None
    action_sent_at_index: int | None = None
    action_id: Any = None
    ended_by_error = False

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
            cancel_params: dict[str, Any] = {"sessionId": session_id}
            if cancel_meta is not None:
                cancel_params["_meta"] = cancel_meta
            await agent.send_notification("session/cancel", cancel_params)
            cancelled_at_index = len(agent.transcript) - 1
        if on_action is not None:
            action_id = await on_action()
            action_sent_at_index = len(agent.transcript) - 1

    def _turn_ended() -> bool:
        return response_entry is not None and (ended_by_error or idle_update is not None)

    async def _handle_one(entry: TranscriptEntry) -> None:
        """Dispatch one already-read line: mutate the outer turn state via `nonlocal`. Never
        returns anything -- callers check `_turn_ended()` themselves after each call.

        `entry.parsed` may itself be a JSON-RPC batch array rather than a single object --
        `ACP-BATCH-207` permits an agent to spontaneously emit a batch of `session/update`
        notifications, and this driver must not simply go blind to a turn's own updates just
        because the agent chose to deliver them that way (`emits_batch_updates.py`'s self-test,
        added alongside V2-3's transport/JSON-RPC negative controls, is exactly this scenario).
        Each dict-shaped element is dispatched via `_handle_message` through a synthetic
        per-item entry (`dataclasses.replace(entry, parsed=item)`) that shares the parent line's
        `raw`/`timestamp`/`direction` but carries just that one element as `.parsed`, so every
        downstream consumer -- this function's own id/method matching, and any test that later
        inspects `PromptTurn.updates`/`.response_entry` -- sees the same per-message shape it
        would for an unbatched line. The transcript index recorded for an update extracted this
        way is the *line's* own index (a batch has no separate transcript slot per element)."""
        raw_msg = entry.parsed
        if isinstance(raw_msg, list):
            line_index = agent.transcript.index(entry)
            for item in raw_msg:
                if isinstance(item, dict):
                    await _handle_message(replace(entry, parsed=item), line_index)
            return
        if isinstance(raw_msg, dict):
            await _handle_message(entry, agent.transcript.index(entry))

    async def _handle_message(entry: TranscriptEntry, line_index: int) -> None:
        nonlocal response_entry, message_id, running_seen, idle_update, stop_reason
        nonlocal action_response, ended_by_error
        msg = entry.parsed
        if entry.matches_id(prompt_id):
            response_entry = entry
            if "error" in msg:
                ended_by_error = True
            else:
                result = msg.get("result")
                if isinstance(result, dict):
                    candidate = result.get("messageId")
                    if isinstance(candidate, str):
                        message_id = candidate
            return
        if action_id is not None and entry.matches_id(action_id):
            action_response = entry
            return

        method = msg.get("method")
        if method == "session/update":
            updates.append((line_index, entry))
            params_ = msg.get("params")
            if isinstance(params_, dict) and params_.get("sessionId") == session_id:
                update = params_.get("update")
                if isinstance(update, dict) and update.get("sessionUpdate") == "state_update":
                    state = update.get("state")
                    if state == "running":
                        running_seen = True
                    elif state == "idle" and idle_update is None:
                        sr = update.get("stopReason")
                        if sr is not None or running_seen:
                            idle_update = entry
                            stop_reason = sr
            return

        if method == "session/request_permission" and "id" in msg:
            options = (msg.get("params") or {}).get("options") or []
            if trigger_sent:
                outcome: dict[str, Any] = {"outcome": "cancelled"}
            else:
                first_option_id = options[0].get("optionId") if options else None
                outcome = {"outcome": "selected", "optionId": first_option_id}
            await agent.send_message(
                {"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": outcome}}
            )
            client_requests_seen.append(entry)
            return

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
            return

        # Any other agent-authored notification (e.g. `elicitation/complete`) -- not our concern
        # here, ignore and keep waiting for the turn to end.
        return

    while not _turn_ended():
        now = loop.time()
        remaining = overall_deadline - now
        if remaining <= 0:
            raise AgentTimeout(
                f"session/prompt {prompt_id!r} on session {session_id!r} did not reach a "
                f"terminating idle state_update within {timeout}s",
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

        was_running = running_seen
        await _handle_one(entry)
        just_started_running = running_seen and not was_running

        if not _turn_ended() and trigger_armed and not trigger_sent and just_started_running:
            try:
                peek_entry = await agent.read_line(timeout=peek_timeout)
            except AgentTimeout:
                await _fire_trigger()
            else:
                await _handle_one(peek_entry)
                if not _turn_ended():
                    await _fire_trigger()

    assert response_entry is not None  # for type checkers; `_turn_ended()` guarantees this

    if not ended_by_error:
        # One short trailing peek for a response to `on_action` arriving just after the turn
        # ended (mirrors v1's same peek right before returning) -- never for the error case,
        # where no further obligations exist at all (P6).
        if action_id is not None and action_response is None:
            try:
                peek_entry = await agent.read_line(timeout=peek_timeout)
            except AgentTimeout:
                pass
            else:
                await _handle_one(peek_entry)

    return PromptTurn(
        response_entry,
        message_id,
        running_seen,
        idle_update,
        stop_reason,
        updates,
        client_requests_seen,
        cancelled_at_index,
        action_response,
        action_sent_at_index,
    )
