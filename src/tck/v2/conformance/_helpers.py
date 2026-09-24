"""Shared helpers for the v2 conformance suite.

`connected_agent()`/`new_session()`/`skip_if_version_mismatch()` are the basic connection/session
helpers. `run_prompt()`/`PromptTurn`/`cancel_race_peek()` are the v2 mock-client prompt driver,
the v2 counterpart of `tck.v1.conformance._helpers`'s same-named machinery -- deliberately a
separate, non-shared implementation, because the v2 turn-end contract is fundamentally
different: v1's `session/prompt` response *is* the turn result (carries `stopReason`); v2's
response is only an acceptance receipt (`{messageId}`) sent at insertion time, and the turn's
end is learned solely from a `session/update` `state_update {state: "idle"}` notification.

`skip_if_auth_gated()` is the v2 twin of v1's same-named helper, wired into `new_session()`.

The session-management wire helpers (`resume_session`, `list_sessions`, `close_session`,
`delete_session`, `set_config_option`) and `obtain_resumable_session` address a hard problem:
there is no spec-guaranteed way for a black-box client to obtain a session id it is entitled to
`session/resume`. It tries, in order: (1) resuming the session just created on
this connection; (3) `session/list` then resuming its first entry; (2) `session/close` then
resume -- recording every route's error -- and raises `pytest.skip.Exception` with all three
recorded errors if none succeeds, *unless* `session/resume` itself answered `-32601` (Method not
found) on any attempt, which is instead surfaced as a hard failure (the method is
baseline-mandatory once `capabilities.session` is advertised at all, so `-32601` is
unambiguously non-conformant, never just "this particular id didn't work").
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest

from tck.common.harness import AgentExited, AgentLaunch, AgentProcess, AgentTimeout, TranscriptEntry
from tck.common.plugin import current_auth_method_id, current_initialize_auth_methods, register_active_process

from .. import SPEC
from ..protocol import AUTHENTICATION_REQUIRED, METHOD_NOT_FOUND, PROTOCOL_VERSION


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
            await login_if_needed(agent, timeout=launch.startup_timeout)
        yield agent


def validate_login_method_id(auth_methods: list[Any], method_id: str) -> dict[str, Any]:
    """Return the `authMethods` entry matching `method_id`, or `pytest.skip(...)` with an
    `AUTH-GATED:` reason if the id is not among `auth_methods` at all, or names a
    `type: "terminal"` entry -- two client MUST NOTs the TCK holds itself to just as strictly as
    it holds the agent under test to its own: sending `auth/login` with a `terminal` `methodId`,
    or with a `methodId` the agent did not advertise, are both client MUST-NOTs (V13). Callers
    that already know `auth_methods` is non-empty (see `login_if_needed`'s own empty-list no-op,
    must-NOT #7) call this right before actually sending `auth/login`.
    """
    matching = next(
        (m for m in auth_methods if isinstance(m, dict) and m.get("methodId") == method_id),
        None,
    )
    if matching is None:
        advertised = [m.get("methodId") for m in auth_methods if isinstance(m, dict)]
        pytest.skip(
            f"AUTH-GATED: --auth-method {method_id!r} is not among this agent's advertised "
            f"authMethods {advertised!r} -- the TCK will not send auth/login with an "
            "unadvertised methodId (client MUST NOT, V13)"
        )
    if matching.get("type") == "terminal":
        pytest.skip(
            f"AUTH-GATED: --auth-method {method_id!r} names a type: 'terminal' authMethods "
            "entry -- the TCK will not send auth/login for it (client MUST NOT, V13); terminal "
            "auth is an out-of-band, client-side relaunch flow the TCK cannot drive"
        )
    return matching


async def login_if_needed(agent: AgentProcess, *, timeout: float | None = None) -> None:
    """Send `auth/login` for `current_auth_method_id()` (`--auth-method`) if one was configured,
    on a connection that is past its own `initialize` response.

    `connected_agent(..., handshake=True)` (the default) already calls this right after its own
    `initialize`; this standalone entry point exists for the several tests that instead perform a
    *manual* `initialize` on a `handshake=False` connection -- e.g. to control
    `skip_if_version_mismatch` themselves (`test_transport.py`, `test_batch.py`,
    `test_session_config.py`, `test_initialize.py`'s ACP-SCHEMA-001 full-exchange test) -- and
    then go on to call `session/new`: without an explicit login step on *that* connection, an
    agent gated behind authentication (e.g. `gated_by_auth.py`) still answers `session/new` with
    `-32000` even though a valid `--auth-method` was given, and `skip_if_auth_gated`'s excuse for
    `-32000` only applies when `current_auth_method_id() is None` -- so the test would fail for
    real instead of either succeeding or SKIPping with a clear reason.

    No-op when no `--auth-method` was given (`current_auth_method_id() is None`), and also when
    the agent's own `initialize` advertised no `authMethods` at all -- the TCK must not send
    `auth/login` in that situation regardless of what `--auth-method` says (must-NOT #7).
    SKIPs -- with an `AUTH-GATED:` reason, via `validate_login_method_id`
    -- if the configured id is not among the advertised `authMethods`, or names a `type:
    "terminal"` entry (must-NOT #12/#13); also SKIPs -- not fails -- if `auth/login` itself does
    not succeed, mirroring `connected_agent`'s own embedded login: a failing login means the TCK
    cannot exercise anything session-dependent against this agent with the given `--auth-method`,
    not that the caller's own requirement failed.
    """
    method_id = current_auth_method_id()
    if method_id is None:
        return
    auth_methods = current_initialize_auth_methods()
    if not auth_methods:
        # V9/must-NOT #7: the client MUST NOT call `auth/login` (or `auth/logout`) at all when
        # `authMethods` is empty -- the agent's response to a call the spec forbids is undefined.
        # Proceed unauthenticated rather than violate that MUST NOT just because a
        # (now-irrelevant) `--auth-method` id was supplied on the command line.
        return
    validate_login_method_id(auth_methods, method_id)
    auth_id = await agent.send_request("auth/login", {"methodId": method_id})
    auth_entry = await agent.wait_for_response(auth_id, timeout=timeout)
    auth_msg = auth_entry.parsed
    if not (isinstance(auth_msg, dict) and isinstance(auth_msg.get("result"), dict)):
        detail = (auth_msg.get("error") if isinstance(auth_msg, dict) else None) or auth_entry.text
        pytest.skip(
            f"AUTH-GATED: auth/login with methodId={method_id!r} failed: {detail!r} "
            "-- check --tck-auth-method"
        )


def skip_if_auth_gated_msg(msg: Any) -> None:
    """Message-shaped core of `skip_if_auth_gated()` below -- operates on an already-parsed
    JSON-RPC response object (`{"error": {...}}` or `{"result": {...}}`) rather than a
    `TranscriptEntry`, so a caller that pulls a `session/new` reply out of something other than a
    single top-level response -- e.g. `test_batch.py`, matching one entry out of a batch response
    array by id -- can still route it through the same auth-gate check `new_session()` uses.

    Skips the current test, with a message pointing at `--auth-method`, if `msg` is the
    `AUTHENTICATION_REQUIRED` (`-32000`) error. v2 twin of
    `tck.v1.conformance._helpers.skip_if_auth_gated`.

    v2 never requires an agent to gate `session/new` behind authentication (`-32000` there is
    still only a MAY, same as v1), so this is not itself a conformance failure; but it does mean
    the TCK cannot exercise session-dependent
    requirements against this agent unless the harness operator supplies a valid
    `--auth-method <id>`. The message is prefixed with the literal marker string `AUTH-GATED:`
    so `tck.common.plugin` can detect this specific reason (as opposed to an ordinary
    capability-not-advertised skip) and set `Verdict.blocked_by_auth`.

    Only excuses the `-32000` when the cached `initialize` result actually advertised at least
    one `authMethods` entry (mirrors v1's AUTH-A1 rule, re-cited as `ACP-AUTH-205`) -- an agent
    that advertises none and still returns `-32000` has no defined remedy; this is left as an
    ordinary, un-excused failure of whatever the caller was asserting, not something the TCK can
    route around.
    """
    if not (
        isinstance(msg, dict)
        and isinstance(msg.get("error"), dict)
        and msg["error"].get("code") == AUTHENTICATION_REQUIRED
        and current_auth_method_id() is None
    ):
        return
    if not current_initialize_auth_methods():
        return  # no advertised authMethods -- not excusable, let the caller's own assert fail
    pytest.skip(
        "AUTH-GATED: session/new returned -32000 (authentication required) and no "
        "--auth-method was given; pass --auth-method <id> (one of the ids advertised in "
        "initialize's authMethods) to test session-dependent requirements against this agent"
    )


def skip_if_auth_gated(entry: TranscriptEntry) -> None:
    """Skip the current test, with a message pointing at `--auth-method`, if `entry` (a
    `session/new` response) is the `AUTHENTICATION_REQUIRED` (`-32000`) error. See
    `skip_if_auth_gated_msg()` above for the full rationale; this is a thin `TranscriptEntry`
    adapter over it for the common single-response case."""
    skip_if_auth_gated_msg(entry.parsed)


async def new_session(agent: AgentProcess, cwd: Any, *, timeout: float | None = None) -> str:
    """Send `session/new` for `cwd` and return the resulting `sessionId`.

    Unlike v1's `new_session`, `mcpServers` is omitted entirely rather than sent as an empty
    list -- v2's `session/new` params require only `cwd` (`schema/v2/schema.json`
    `required: ["cwd"]`, `mcpServers` optional), and omitting it avoids the MCP-capability check.

    SKIPs (via `skip_if_auth_gated`) rather than failing when the agent requires authentication
    and no `--auth-method` was configured.
    """
    req_id = await agent.send_request("session/new", {"cwd": str(cwd)})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    skip_if_auth_gated(entry)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    session_id = msg["result"].get("sessionId")
    assert isinstance(session_id, str) and session_id, (
        f"session/new result.sessionId must be a non-empty string, got {session_id!r}"
    )
    return session_id


async def resume_session(
    agent: AgentProcess,
    session_id: str,
    cwd: Any,
    *,
    replay_from: dict[str, Any] | None = None,
    additional_directories: list[str] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
) -> tuple[TranscriptEntry, list[tuple[int, TranscriptEntry]]]:
    """Send `session/resume` and collect every `session/update` notification observed on the
    wire before its response arrives, in wire order -- this *is* the replay stream
    `ACP-RESUME-202..205` need to inspect. `session/resume`'s response is not an acceptance
    receipt (unlike `session/prompt`'s): it carries the actual result directly, so unlike
    `run_prompt` there is no separate turn-end predicate to wait for, just the matching response.

    Returns `(response_entry, updates)`. Any agent -> client request arriving meanwhile (none is
    expected during `session/resume`) is simply left unanswered in the transcript for the caller
    to notice -- answering it here would risk masking a genuine defect with an invented outcome.
    """
    params: dict[str, Any] = {"sessionId": session_id, "cwd": str(cwd)}
    if replay_from is not None:
        params["replayFrom"] = replay_from
    if additional_directories is not None:
        params["additionalDirectories"] = additional_directories
    if mcp_servers is not None:
        params["mcpServers"] = mcp_servers
    req_id = await agent.send_request("session/resume", params)

    updates: list[tuple[int, TranscriptEntry]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout if timeout is not None else None
    while True:
        remaining = (deadline - loop.time()) if deadline is not None else None
        if remaining is not None and remaining <= 0:
            raise AgentTimeout(
                f"session/resume {req_id!r} for session {session_id!r} did not respond within "
                f"{timeout}s",
                agent.transcript,
                stderr=agent.stderr_text(),
            )
        entry = await agent.read_line(timeout=remaining)
        line_index = agent.transcript.index(entry)
        for msg in iter_messages(entry):
            if "method" not in msg and msg.get("id") == req_id:
                return entry, updates
            if msg.get("method") == "session/update":
                updates.append((line_index, entry))
        # Anything else observed on the wire while waiting (an unrelated notification, a
        # malformed line) is not this helper's concern; keep waiting for the response.


async def drain_quiet(agent: AgentProcess, quiet: float) -> list[TranscriptEntry]:
    """Read whatever the agent sends for up to `quiet` seconds and return everything observed
    (`session/update` notifications and anything else alike) -- the generic "nothing more is
    coming" drain `ACP-RESUME-202` uses to confirm no replay update trails the response."""
    collected: list[TranscriptEntry] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + quiet
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            entry = await agent.read_line(timeout=remaining)
        except AgentTimeout:
            break
        collected.append(entry)
    return collected


async def list_sessions(
    agent: AgentProcess,
    *,
    cwd: Any = None,
    cursor: str | None = None,
    timeout: float | None = None,
) -> TranscriptEntry:
    """Send `session/list` and return its response entry (the caller inspects `.parsed` itself --
    unlike `new_session`, several tests need to see a raw error response too, e.g. a cursor round
    trip is out of scope but an empty-list-vs-error check is not)."""
    params: dict[str, Any] = {}
    if cwd is not None:
        params["cwd"] = str(cwd)
    if cursor is not None:
        params["cursor"] = cursor
    req_id = await agent.send_request("session/list", params)
    return await agent.wait_for_response(req_id, timeout=timeout)


async def close_session(
    agent: AgentProcess, session_id: str, *, timeout: float | None = None
) -> TranscriptEntry:
    """Send `session/close` for `session_id` and return its response entry."""
    req_id = await agent.send_request("session/close", {"sessionId": session_id})
    return await agent.wait_for_response(req_id, timeout=timeout)


async def delete_session(
    agent: AgentProcess, session_id: str, *, timeout: float | None = None
) -> TranscriptEntry:
    """Send `session/delete` for `session_id` and return its response entry."""
    req_id = await agent.send_request("session/delete", {"sessionId": session_id})
    return await agent.wait_for_response(req_id, timeout=timeout)


async def set_config_option(
    agent: AgentProcess,
    session_id: str,
    config_id: str,
    *,
    type: str,
    value: Any,
    timeout: float | None = None,
) -> TranscriptEntry:
    """Send `session/set_config_option` (`schema/v2/schema.json` `SetSessionConfigOptionRequest`:
    `sessionId`+`configId` plus a `type`/`value` pair, e.g. `type="boolean", value=True` or
    `type="id", value=<SessionConfigValueId>`) and return its response entry."""
    params = {"sessionId": session_id, "configId": config_id, "type": type, "value": value}
    req_id = await agent.send_request("session/set_config_option", params)
    return await agent.wait_for_response(req_id, timeout=timeout)


async def _route_just_created(agent: AgentProcess, cwd: Any, timeout: float | None) -> str:
    """Route (1): the session `session/new` just created on this same fresh connection."""
    return await new_session(agent, cwd, timeout=timeout)


async def _route_from_list(agent: AgentProcess, cwd: Any, timeout: float | None) -> str:
    """Route (3): the first entry `session/list` reports on this fresh connection. Raises if the
    list is empty or malformed -- a fresh, just-opened connection has no session of its own yet,
    so this route only ever helps against an agent that persists sessions across connections."""
    entry = await list_sessions(agent, timeout=timeout)
    msg = entry.parsed
    result = msg.get("result") if isinstance(msg, dict) else None
    sessions = result.get("sessions") if isinstance(result, dict) else None
    if not sessions:
        raise RuntimeError(f"session/list returned no sessions to resume: {entry.text!r}")
    first = sessions[0]
    session_id = first.get("sessionId") if isinstance(first, dict) else None
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"session/list's first entry has no usable sessionId: {first!r}")
    return session_id


async def _route_after_close(agent: AgentProcess, cwd: Any, timeout: float | None) -> str:
    """Route (2): create a session, `session/close` it, then attempt to resume the closed id."""
    session_id = await new_session(agent, cwd, timeout=timeout)
    await close_session(agent, session_id, timeout=timeout)
    return session_id


async def _attempt_resumable_route(
    launch: AgentLaunch,
    cwd: Any,
    timeout: float | None,
    errors: list[str],
    route_setup: Callable[[AgentProcess, Any, float | None], Awaitable[str]],
) -> tuple[AgentProcess, str, TranscriptEntry, contextlib.AsyncExitStack] | None:
    """Try one route of `obtain_resumable_session` on its own fresh connection. Returns
    `(agent, session_id, resume_response_entry, stack)` -- with the connection detached from
    local cleanup via `stack.pop_all()` -- on success, so the caller can keep it open; `None` on
    any failure, with the connection already closed and the failure appended to `errors`.

    A `-32601` from `session/resume` itself is not a route failure to record and move past: `B3`
    makes `session/resume` baseline-mandatory once `capabilities.session` is advertised at all,
    so this is unconditionally a conformance failure and is raised via `pytest.fail(...)`
    immediately, regardless of which route surfaced it.
    """
    attempt_stack = contextlib.AsyncExitStack()
    try:
        agent = await attempt_stack.enter_async_context(connected_agent(launch))
        session_id = await route_setup(agent, cwd, timeout)
        req_id = await agent.send_request(
            "session/resume", {"sessionId": session_id, "cwd": str(cwd)}
        )
        entry = await agent.wait_for_response(req_id, timeout=timeout)
    except pytest.skip.Exception:
        await attempt_stack.aclose()
        raise
    except Exception as exc:  # noqa: BLE001 -- record and let the next route try
        errors.append(repr(exc))
        await attempt_stack.aclose()
        return None

    msg = entry.parsed
    if isinstance(msg, dict) and isinstance(msg.get("result"), dict):
        return agent, session_id, entry, attempt_stack.pop_all()

    if isinstance(msg, dict) and isinstance(msg.get("error"), dict):
        code = msg["error"].get("code")
        await attempt_stack.aclose()
        if code == METHOD_NOT_FOUND:
            pytest.fail(
                "session/resume answered -32601 Method not found -- session/resume is "
                "baseline-mandatory once capabilities.session is advertised at all (B3), so "
                "this is a hard failure of ACP-RESUME-201, not a route-specific SKIP"
            )
        errors.append(f"session/resume error: {msg['error']!r}")
        return None

    await attempt_stack.aclose()
    errors.append(f"malformed session/resume response: {entry.text!r}")
    return None


@contextlib.asynccontextmanager
async def obtain_resumable_session(
    launch: AgentLaunch, cwd: Any, *, timeout: float | None = None
) -> AsyncIterator[tuple[AgentProcess, str, TranscriptEntry]]:
    """Yield `(agent, session_id, resume_response_entry)` for a connected, initialized agent, a
    session id this helper found `session/resume` accepts for `cwd`, and the response entry from
    the successful probe call that proved it (`ACP-RESUME-201` uses this directly rather than
    issuing a second, redundant `session/resume` for the same id).

    No route for obtaining a legally resumable session id is spec-guaranteed. Tries, in order,
    each on its own fresh connection: (1) resuming the session `session/new` just created on this
    same connection; (3) `session/list`'s first entry; (2) creating a session, `session/close`-ing it,
    then resuming it. `pytest.skip(...)`s with all three routes' recorded errors if none
    succeeds -- *unless* `session/resume` itself ever answered `-32601`, which is instead a hard
    `pytest.fail(...)` (see `_attempt_resumable_route`).

    The yielded connection is whichever attempt succeeded; a caller that needs a *second*
    `session/resume` call with different params (e.g. a specific `replayFrom`) is free to issue
    one against the same session/connection.
    """
    errors: list[str] = []
    result = None
    for route_setup in (_route_just_created, _route_from_list, _route_after_close):
        result = await _attempt_resumable_route(launch, cwd, timeout, errors, route_setup)
        if result is not None:
            break
    if result is None:
        pytest.skip(
            "no resumable session obtainable via any of the three routes (create-then-resume, "
            "list-then-resume, close-then-resume): " + "; ".join(errors)
        )
    agent, session_id, entry, stack = result
    try:
        yield agent, session_id, entry
    finally:
        await stack.aclose()


@contextlib.asynccontextmanager
async def v2_only_agent(
    agent_launch: AgentLaunch,
    *,
    capabilities: dict[str, Any] | None = None,
    yield_result: bool = False,
) -> AsyncIterator[Any]:
    """Shared "fresh connection, manual `initialize` routed through `SPEC.initialize_params()`,
    `VERSION-MISMATCH:` skip unless the agent actually negotiated v2, then `login_if_needed`"
    pattern used by every module that must control its own `initialize`/
    `skip_if_version_mismatch` call instead of `connected_agent`'s default v2-negotiating
    handshake -- `test_batch.py`, `test_session_config.py`, `test_authentication.py`,
    `test_transport.py`.

    Yields the connected `AgentProcess`, or `(agent, init_result)` when `yield_result=True` (for
    callers that need to inspect the negotiated result, e.g. a capabilities marker)."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        params = SPEC.initialize_params()
        if capabilities is not None:
            params = {**params, "capabilities": capabilities}
        req_id = await agent.send_request("initialize", params)
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.startup_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        await login_if_needed(agent, timeout=agent_launch.startup_timeout)
        if yield_result:
            yield agent, msg["result"]
        else:
            yield agent


def iter_messages(entry: TranscriptEntry) -> list[dict[str, Any]]:
    """Flatten one transcript entry into the list of dict-shaped JSON-RPC messages it carries:
    `[entry.parsed]` for an ordinary object line, every dict element of a batch array line (a
    non-dict element, e.g. a stray scalar in a malformed batch, is dropped -- nothing meaningful
    to dispatch), or `[]` for anything else (a parse failure, a bare scalar line, ...).

    Several transcript scans matched only `isinstance(entry.parsed, dict)` and so were blind to
    a message delivered inside a JSON-RPC batch array (`emits_batch_updates.py` proves this is a
    real scenario an agent may choose) --
    `run_prompt`/`test_transport.py`/`test_enums.py`/`test_initialize.py`/parts of `test_cancel.py`
    already unwrapped a batch line by hand; this is the one shared helper every such site (and
    `ACP-JSONRPC-003`, `ACP-CANCEL-202`, `ACP-SCHEMA-002`, `resume_session`, which did not) should
    use instead of re-deriving the same six-line flattening."""
    parsed = entry.parsed
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def is_response_line(entry: TranscriptEntry) -> bool:
    """True if `entry` carries a reply: any JSON-RPC object without `method`, bare or inside a
    batch array, even a malformed one missing `id`/`result`/`error`.

    The one rule every "a notification gets no response" check uses. ACP and JSON-RPC 2.0
    §4.1/§6 forbid only *replies* to a notification. The agent's own notifications and agent ->
    client requests carry `method`, are not replies, and may arrive at any time after
    `initialize`. A non-JSON line is not a reply either; the transport rows judge it."""
    return any("method" not in msg for msg in iter_messages(entry))


async def first_response_within(agent: AgentProcess, quiet: float) -> TranscriptEntry | None:
    """Wait up to `quiet` seconds for a reply (`is_response_line`) and return it, or `None` if
    none arrived. Agent-initiated messages read meanwhile are skipped and left in
    `agent.pending()`. An agent -> client request among them is left unanswered, like in every
    other wait outside `run_prompt`: the check is about what the agent sends, not about driving
    it further. `AgentExited` propagates."""
    try:
        return await agent.wait_for_message(is_response_line, timeout=quiet)
    except AgentTimeout:
        return None


def is_agent_initiated(entry: TranscriptEntry) -> bool:
    """True if `entry` is made only of messages the agent initiated on its own: a JSON-RPC
    object carrying `method` (a notification or an agent -> client request), or a non-empty
    batch array whose every element is one (`ACP-BATCH-207` lets an agent batch its own
    notifications). Such a line may arrive at any time after `initialize`, so it is never the
    reply a check is waiting for.

    An array with even one other element (a response, a scalar) is not agent-initiated: it is
    left for the caller to judge as a reply, malformed or not. Neither is `[]`."""
    parsed = entry.parsed
    if isinstance(parsed, dict):
        return "method" in parsed
    if isinstance(parsed, list) and parsed:
        return all(isinstance(item, dict) and "method" in item for item in parsed)
    return False


async def next_reply_line(agent: AgentProcess, timeout: float) -> TranscriptEntry:
    """Return the first line within `timeout` that is not agent-initiated
    (`is_agent_initiated`), for the caller to judge as the reply it waits for. Anything else --
    a response object or array, but also a non-JSON or otherwise malformed line -- is returned
    as-is, so the caller still judges the reply's shape (one array or separate objects, one line
    or several). Skipped lines stay in `agent.pending()`, and an agent -> client request among
    them is left unanswered. `AgentTimeout`/`AgentExited` propagate."""
    return await agent.wait_for_message(lambda entry: not is_agent_initiated(entry), timeout=timeout)


async def probe_behaviour(
    read: Awaitable[TranscriptEntry],
    on_reply: Callable[[TranscriptEntry], str],
    *,
    on_silent: Callable[[], str] | None = None,
) -> str:
    """Run one already-started read `read` and classify the outcome as "silent" / "agent exited
    (exit_code=...)" / whatever `on_reply` returns for a reply that did arrive.

    Shared by the seven near-identical "did the agent stay silent, exit, or reply" INFORMATIONAL
    probes across `test_informational.py`, `test_batch.py`, and `test_cancel.py` -- only the
    common `AgentTimeout`/`AgentExited` ladder is identical between all seven; each site still
    supplies its own read call (a specific
    `wait_for_response`/`wait_for_message`/`read_line`, each with its own predicate/timeout) and
    its own `on_reply` classifier, since what counts as "a reply" differs (a JSON-RPC
    error/result split vs. a raw-text dump). `on_silent`, if given, overrides the default
    `"silent"` string for the `AgentTimeout` branch -- used by
    `test_informational.test_unknown_session_id_behaviour`, whose silent case additionally
    reports any outstanding agent->client requests."""
    try:
        entry = await read
    except AgentTimeout:
        return on_silent() if on_silent is not None else "silent"
    except AgentExited as exc:
        return f"agent exited (exit_code={exc.exit_code!r})"
    else:
        return on_reply(entry)


def update_of(entry: TranscriptEntry) -> dict[str, Any] | None:
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
    imported): a short, bounded look for a line that may already be sitting in the pipe, used by
    `run_prompt` right after it decides the turn has ended, to give a trailing/out-of-order
    response (e.g. `on_action`'s) one last chance to be captured before returning."""
    return max(0.05, min(0.5, timeout / 50))


def quiet_period(timeout: float) -> float:
    """v2 twin of v1's `quiet_period` (identical formula, deliberately re-implemented rather than
    imported -- honest duplication, not shared machinery): the heuristic "nothing more is
    coming" wait used by INFORMATIONAL probes that conclude absence
    (e.g. `ACP-INFO-CONCURRENT-201`'s "did a second, concurrent `session/prompt` get a
    response at all") -- derived from `--tck-timeout` rather than a hard-coded sub-second
    constant, clamped to a sane range."""
    return max(0.5, min(2.0, timeout / 10))


@dataclass(frozen=True)
class PromptTurn:
    """The outcome of one v2 `session/prompt` turn driven by `run_prompt`.

    Unlike v1's `PromptTurn` (whose `response_entry` *is* the turn result), v2's response is only
    an acceptance receipt -- the turn's actual outcome (`running_seen`/`idle_update`/
    `stop_reason`) is learned entirely from `session/update` notifications.
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
    at all), which gets `-32601` since our mock client advertises `capabilities: {}` -- used by
    the negative tests asserting "the agent called an unadvertised/nonexistent method"
    (`ACP-CLIENTCAP-201`/`202`).

    Also carries every agent -> client *notification* other than `session/update` (e.g.
    `elicitation/complete`, or an undefined/misspelled method name), since `ACP-CLIENTCAP-202`
    covers requests and notifications alike and the driver must not go blind to a notification
    just because it needs no reply. Callers that only care about requests (e.g.
    `session/request_permission`) filter this list by `.parsed.get("method")` themselves."""
    cancelled_at_index: int | None = None
    """The transcript index at which `run_prompt` sent `session/cancel`, or `None` if
    `on_cancel` was false or the prompt turn ended before a cancel was ever sent."""
    action_response: TranscriptEntry | None = None
    """The response to `on_action`'s request, if `on_action` was given and fired -- `None`
    otherwise (mirrors v1's `PromptTurn.action_response`; used by `test_cancel.py` to drive
    `session/close` mid-turn)."""
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
    turn's terminator (it is only an acceptance receipt, `{messageId}`, sent at insertion time).
    The turn ends only when a `session/update` `state_update {state: "idle"}` for `session_id` is
    observed (`prompt-lifecycle.mdx:348`), or when the prompt is rejected outright with a
    JSON-RPC error (no insertion happened, so no further obligations apply -- P6). Every wait
    below is bounded by `timeout`, so a non-conforming agent that never reaches either terminator
    produces an `AgentTimeout` (a FAIL for whatever the caller was asserting), never a hang.

    **Turn-end predicate**: a `state_update {state: "idle"}` observed for `session_id` ends the
    turn iff it carries a `stopReason`, *or* a `state_update {state: "running"}` for `session_id`
    was observed earlier in the same call. This deliberately excludes the legal "session-ready
    idle" a spec-conforming agent may send with no preceding prompt at all (e.g. right after
    `session/new`, observed live in the Python SDK's own v2 test agent) from ever being mistaken
    for a turn's end. A bare idle matching neither condition is simply not treated as a
    terminator; it is recorded like any other update, and reading continues (bounded by `timeout`
    as always) -- no requirement or fixture needs finer-grained handling than that.

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
      `capabilities: {}`), and is recorded on `PromptTurn.client_requests_seen`; any other
      agent -> client *notification* (needs no reply) is recorded there too, unacted-on.

    `cancel_meta`, if given, is merged into the `session/cancel` notification's params as `_meta`
    (`ACP-CANCEL-206`'s "accepts a cancel that additionally carries `_meta`" check) -- `None`
    (the default) sends the bare `{"sessionId": session_id}` params every other caller relies on.

    `on_cancel`/`on_action`/`cancel_wait`/`extra_params` mirror v1's `run_prompt` in shape and
    fallback timing, but **not** in trigger condition: v1 fires its trigger on the *first*
    `session/update` of any kind; v2 fires it specifically on the transition to `state_update
    {state: "running"}` for `session_id` -- the MUST-guaranteed turn-start marker
    (`prompt-lifecycle.mdx:159`) -- because v2's `user_message` echo update (which may arrive
    before `running`) is not itself evidence that foreground work has started. If `session_id`
    never reaches `running` (e.g. a non-conforming agent, or the prompt is rejected outright), the
    trigger still fires once `cancel_wait` elapses, exactly as in v1.

    Callers must serialize prompts per session themselves (never call this a second time for the
    same session before a previous call has returned) -- v2 leaves concurrent `session/prompt`
    on one session unspecified, and both reference agents reject it.
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
        because the agent chose to deliver them that way (`emits_batch_updates.py`'s self-test
        is exactly this scenario). Each dict-shaped element is dispatched via `_handle_message`
        through a synthetic
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

        # Any other agent-authored notification (e.g. `elicitation/complete`, or an
        # undefined/misspelled method name) -- not our concern to act on, but still recorded so
        # `ACP-CLIENTCAP-202` can check it.
        if method is not None:
            client_requests_seen.append(entry)
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
            # Clamped to whatever of `overall_deadline` remains -- `peek_timeout` alone could
            # otherwise push this call past `timeout` by up to ~1s, contradicting this function's
            # own "every wait below is bounded by `timeout`" docstring claim. A non-positive
            # remainder still resolves immediately: `read_line` forwards it to
            # `asyncio.wait_for`, which treats `timeout <= 0` as "check once, don't block" rather
            # than raising.
            try:
                peek_entry = await agent.read_line(
                    timeout=min(peek_timeout, overall_deadline - loop.time())
                )
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
            # Same clamp as the peek above, and for the same reason.
            try:
                peek_entry = await agent.read_line(
                    timeout=min(peek_timeout, overall_deadline - loop.time())
                )
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
