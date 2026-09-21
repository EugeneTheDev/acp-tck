"""Shared core for the conforming ACP v2 (Draft) fixture agent.

Not part of the installed `tck` package: fixture scripts are launched as standalone
subprocesses (`python .../conforming.py`), so they import this module by inserting their own
directory onto `sys.path` rather than a package-relative import -- same pattern as v1's
`tests/fixtures/agents/v1/_base.py`, but a fresh, much smaller implementation (not imported from
v1).

Wire shapes are taken from the vendored `src/tck/v2/schema/schema.json` (`InitializeRequest`/
`InitializeResponse`/`NewSessionRequest`/`NewSessionResponse`/...) -- verify against that schema,
not memory, before changing a field name. Two v2-specific renames vs. v1: the agent's own identity
is `info` (not `agentInfo`) and its capabilities are `capabilities` (not `agentCapabilities`).

Slice V2-1b adds the rest of the `capabilities.session` baseline (`.agents/research/
acp-v2-session-management.md` B1: advertising `session` even as `{}` commits the agent to
`session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`,
`session/cancel`, `session/update`) -- `session/list`, `session/resume`, `session/close`, and a
minimal but wire-correct `session/prompt` turn. None of this is exercised by any test *this*
slice (only `session/new` is, via `ACP-SESSION-001/002`); it exists so a follow-up slice's
prompt-lifecycle/session-capability tests have a conforming baseline to run against from day one,
per the exact shapes cited on each handler below.

Slice V2-2b adds three `_handle_prompt` hooks (`_prompt_rejection`, `_mid_turn_action`,
`_finish_turn` -- see their docstrings) and two shared subclasses built on top of them:
`AsksPermissionAgent` (sends `session/request_permission` mid-turn, defers finishing the turn
until the client answers -- `ACP-PERM-201`'s self-test) and `SendsClientRequestAgent` (fires an
arbitrary agent -> client request mid-turn and continues immediately, not waiting for a reply --
`ACP-CLIENTCAP-201`/`202`'s defect fixtures and the `_`-prefixed positive control). All three
hooks default to a no-op/pass-through, so every V2-2a fixture above is unaffected.

Slice V2-3 adds two independent things, both opt-in/no-op by default so every earlier fixture is
unaffected:

- A `__hang__` cancel sentinel, mirroring v1's `conforming.py`: a prompt whose content is a
  single `{"type": "text", "text": "__hang__"}` block withholds its terminating idle update
  (`_finish_turn`) until `session/cancel` actually arrives for that session (`_handle_cancel`),
  making `ACP-CANCEL-201..20*` testable end to end. `session/close` on a still-hanging session
  cancels it the same way first (`_handle_close_session`, `ACP-CANCEL-208`). The hang check runs
  right after the running update and *before* `_mid_turn_action`, so it preempts (rather than
  combines with) a subclass's own mid-turn behavior for that one sentinel prompt -- irrelevant
  for every non-hang prompt, which is unaffected.
- JSON-RPC batch dispatch (`.agents/research/acp-v2-cancellation-and-batching.md` §6): `run()`
  now also accepts a top-level JSON array line. `_write` is split into an instance method that
  buffers a *response* object into `self._batch_collector` while one is active (never a
  request/notification the agent itself originates -- those always stream out immediately, same
  as outside a batch) and a `_write_line` staticmethod that actually emits a line; this makes
  `_handle_batch`/`_handle_batch_entry` able to reuse every existing `_handle_request`/
  `_handle_cancel` method unchanged, just redirecting where their replies land.
"""

from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = 2

# v2 negotiation rule (initialization.mdx:92-96): if the agent supports the requested version, it
# echoes it back; otherwise it answers with its own latest supported version. This fixture
# supports both defined versions, 1 and 2.
_SUPPORTED_VERSIONS = frozenset({1, 2})


class ConformingAgent:
    """A minimal, deterministic, offline ACP v2 agent.

    Handles `initialize` (honest version negotiation across `_SUPPORTED_VERSIONS`) and the full
    `capabilities.session` baseline: `session/new`, `session/list`, `session/resume`,
    `session/close`, `session/prompt`, `session/cancel`. Any other method gets `-32601`. Exits
    cleanly on stdin EOF (the `for` loop over `sys.stdin` simply ends).

    `capabilities`, if given, is merged verbatim into the `initialize` result's `capabilities`
    (empty by default: `{}` still commits the agent to the baseline session methods per the
    vendored schema's own description text on `AgentCapabilities.session`).
    """

    def __init__(
        self,
        *,
        capabilities: dict[str, Any] | None = None,
        agent_name: str = "tck-fixture-conforming-v2",
    ) -> None:
        self._session_count = 0
        self._message_count = 0
        self._capabilities = capabilities if capabilities is not None else {}
        self._agent_name = agent_name
        self._sessions: dict[str, str] = {}  # sessionId -> cwd
        self._hanging_sessions: dict[Any, bool] = {}  # sessionId -> awaiting session/cancel
        self._batch_collector: list[Any] | None = None  # non-None while inside `_handle_batch`

    def run(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # malformed input is a harness test concern, not ours to crash on
            if isinstance(message, dict):
                self._handle(message)
            elif isinstance(message, list):
                self._handle_batch(message)

    def _handle_batch(self, items: list[Any]) -> None:
        """JSON-RPC 2.0 batch dispatch (§6): an empty array is itself an Invalid Request --
        answered with a single error *object*, never an array. A non-empty array dispatches
        each entry through the normal single-message path (`_handle`), collecting whatever
        responses that produces (never a bare notification's non-reply) into one reply array --
        or no output line at all if every entry was a notification. A malformed entry (not an
        object, or missing/wrong-typed `jsonrpc`/`method`) gets its own `-32600` with `id: null`,
        same as a top-level malformed request would.
        """
        if not items:
            self._write_line(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
            )
            return
        self._batch_collector = []
        for item in items:
            self._handle_batch_entry(item)
        responses, self._batch_collector = self._batch_collector, None
        if responses:
            self._write_line(responses)

    def _handle_batch_entry(self, item: Any) -> None:
        if (
            not isinstance(item, dict)
            or item.get("jsonrpc") != "2.0"
            or not isinstance(item.get("method"), str)
        ):
            self._write(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
            )
            return
        self._handle(item)

    def _handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method is None:
            self._handle_response(message)
            return
        params = message.get("params") or {}
        if "id" in message:
            self._handle_request(method, message["id"], params)
        elif method == "session/cancel":
            self._handle_cancel(params)

    def _handle_response(self, message: dict[str, Any]) -> None:
        """Hook for a subclass that itself sent an agent -> client request mid-turn (a
        permission request, or an arbitrary probe method) to notice the client's reply and
        resume the turn. No-op by default -- `ConformingAgent` itself never sends one."""
        pass

    def _handle_cancel(self, params: dict[str, Any]) -> None:
        """`session/cancel` notification: resolve a hanging `__hang__` prompt (see
        `_handle_prompt`/`_is_hang_prompt`) for this session as `cancelled`. No-op if this
        session has no such prompt outstanding -- e.g. every non-hang prompt, which always
        finishes on its own before `session/cancel` could ever be sent."""
        session_id = params.get("sessionId")
        if self._hanging_sessions.pop(session_id, None) is not None:
            self._finish_turn(session_id, "cancelled")

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._reply(msg_id, self._initialize_result(params))
        elif method == "session/new":
            self._handle_new_session(msg_id, params)
        elif method == "session/list":
            self._handle_list_sessions(msg_id, params)
        elif method == "session/resume":
            self._handle_resume_session(msg_id, params)
        elif method == "session/close":
            self._handle_close_session(msg_id, params)
        elif method == "session/prompt":
            self._handle_prompt(msg_id, params)
        else:
            self._error(msg_id, -32601, "Method not found")

    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        negotiated = requested if requested in _SUPPORTED_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": dict(self._capabilities),
            "info": {"name": self._agent_name, "version": "0.0.0"},
        }

    def _handle_new_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._session_count += 1
        session_id = f"sess-{self._session_count:04d}"
        self._sessions[session_id] = params.get("cwd", "")
        self._reply(msg_id, {"sessionId": session_id})

    def _handle_list_sessions(self, msg_id: Any, params: dict[str, Any]) -> None:
        # `.agents/research/acp-v2-session-management.md` L1/L5: all params optional;
        # `SessionInfo` requires only `sessionId`/`cwd`. Filter by `cwd` when given (L1's
        # "returns the first page" is trivially satisfied here -- no pagination, ever).
        cwd_filter = params.get("cwd")
        sessions = [
            {"sessionId": session_id, "cwd": cwd}
            for session_id, cwd in self._sessions.items()
            if cwd_filter is None or cwd == cwd_filter
        ]
        self._reply(msg_id, {"sessions": sessions})

    def _handle_resume_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        # R2: `replayFrom` omitted/`null` -> MUST NOT replay history before responding. This
        # fixture never retains history, so there is nothing to replay in the `{"type":"start"}`
        # case either -- both branches respond immediately with the documented empty form `{}`
        # (R12).
        self._reply(msg_id, {})

    def _handle_close_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        # ACP-CANCEL-208: closing a session with a still-hanging `__hang__` prompt MUST cancel
        # that work as if `session/cancel` had been sent -- same resolution path, just triggered
        # by a different wire event, before the close itself is acknowledged.
        session_id = params.get("sessionId")
        if self._hanging_sessions.pop(session_id, None) is not None:
            self._finish_turn(session_id, "cancelled")
        self._sessions.pop(session_id, None)
        self._reply(msg_id, {})

    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        # `.agents/research/acp-v2-prompt-lifecycle.md` §5 minimal conforming sequence:
        # result{messageId} -> user_message -> state_update{running} -> agent_message_chunk ->
        # state_update{idle, stopReason:"end_turn"}. The response is an acceptance receipt only
        # (no `stopReason`) -- P7/§2.
        #
        # Slice V2-2a splits this into small overridable steps (`_reply_to_prompt`,
        # `_send_user_message_update`, `_send_running_update`, `_stop_reason`,
        # `_send_idle_update`) purely so single-defect fixtures under `tests/fixtures/agents/v2/`
        # can override exactly one step -- `ConformingAgent`'s own behavior here is unchanged.
        #
        # Slice V2-2b adds three more hooks, all no-ops/pass-through by default so every
        # existing fixture above is unaffected: `_prompt_rejection` (reject the prompt outright,
        # e.g. `rejects_image_when_advertised.py`) and `_mid_turn_action` (fire something -- a
        # permission request, an arbitrary agent -> client probe -- after the running update;
        # returning `True` defers the rest of the turn to a later `_handle_response` call
        # instead of finishing it immediately, for `AsksPermissionAgent`).
        session_id = params.get("sessionId")
        prompt = params.get("prompt") or []
        rejection = self._prompt_rejection(prompt)
        if rejection is not None:
            code, error_message = rejection
            self._error(msg_id, code, error_message)
            return
        self._message_count += 1
        message_id = f"msg-{self._message_count:04d}"
        self._reply_to_prompt(msg_id, message_id)
        self._send_user_message_update(session_id, message_id, prompt)
        self._send_running_update(session_id)
        if self._is_hang_prompt(prompt):
            # Slice V2-3's cancel sentinel: withhold the terminating idle until `session/cancel`
            # (or `session/close`) actually arrives for this session -- see `_handle_cancel`/
            # `_handle_close_session`. Preempts `_mid_turn_action` for this one prompt only;
            # every other prompt is unaffected.
            self._hanging_sessions[session_id] = True
            return
        if self._mid_turn_action(session_id):
            return  # the subclass deferred the rest of the turn to `_handle_response`
        self._finish_turn(session_id)

    @staticmethod
    def _is_hang_prompt(prompt: list[Any]) -> bool:
        """`True` iff `prompt` is the `__hang__` cancel sentinel: a single text block whose text
        is exactly `"__hang__"` (mirrors v1's `conforming.py` sentinel)."""
        return any(
            isinstance(block, dict) and block.get("type") == "text" and block.get("text") == "__hang__"
            for block in prompt
        )

    def _prompt_rejection(self, prompt: list[Any]) -> tuple[int, str] | None:
        """Hook: return `(code, message)` to reject this prompt outright with a JSON-RPC error
        instead of accepting it (e.g. an unadvertised/rejected content block type). `None` (the
        default) always accepts."""
        return None

    def _mid_turn_action(self, session_id: Any) -> bool:
        """Hook fired once, right after the running update, before the reply chunk/idle. Return
        `True` to defer finishing the turn to a later `_handle_response` call (the action itself
        must arrange to call `_finish_turn` once it resolves); `False` (the default -- also used
        by an action that fires-and-forgets, not waiting for any reply) to finish the turn
        immediately, in the same call."""
        return False

    def _finish_turn(self, session_id: Any, stop_reason: str | None = None) -> None:
        """Send the closing `agent_message_chunk` and the terminating idle. `stop_reason`
        defaults to `self._stop_reason()` when omitted -- callers that already know the outcome
        (e.g. `AsksPermissionAgent`, once the permission answer is in) can pass it explicitly."""
        self._message_count += 1
        reply_message_id = f"msg-{self._message_count:04d}"
        self._send_update(
            session_id,
            {
                "sessionUpdate": "agent_message_chunk",
                "messageId": reply_message_id,
                "content": {"type": "text", "text": "ok"},
            },
        )
        self._send_idle_update(
            session_id, stop_reason if stop_reason is not None else self._stop_reason()
        )

    def _reply_to_prompt(self, msg_id: Any, message_id: str) -> None:
        self._reply(msg_id, {"messageId": message_id})

    def _send_user_message_update(self, session_id: Any, message_id: str, prompt: Any) -> None:
        self._send_update(
            session_id,
            {"sessionUpdate": "user_message", "messageId": message_id, "content": prompt},
        )

    def _send_running_update(self, session_id: Any) -> None:
        self._send_update(session_id, {"sessionUpdate": "state_update", "state": "running"})

    def _stop_reason(self) -> str:
        return "end_turn"

    def _send_idle_update(self, session_id: Any, stop_reason: str | None) -> None:
        update: dict[str, Any] = {"sessionUpdate": "state_update", "state": "idle"}
        if stop_reason is not None:
            update["stopReason"] = stop_reason
        self._send_update(session_id, update)

    def _send_update(self, session_id: Any, update: dict[str, Any]) -> None:
        self._notify("session/update", {"sessionId": session_id, "update": update})

    def _reply(self, msg_id: Any, result: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _error(self, msg_id: Any, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, obj: dict[str, Any]) -> None:
        # While a batch is being dispatched (`_handle_batch`), a *response* (no `method` key --
        # a `result`/`error` reply to one of the batch's own request entries) is buffered into
        # the collector instead of written immediately, so the whole batch's responses can be
        # emitted as one reply array. A notification the agent itself originates (`method`
        # present -- e.g. `session/update`) always streams out immediately, batch or not: only
        # *replies to the batch's own entries* belong in the response array.
        if self._batch_collector is not None and "method" not in obj:
            self._batch_collector.append(obj)
            return
        self._write_line(obj)

    @staticmethod
    def _write_line(obj: dict[str, Any] | list[Any]) -> None:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()


class AsksPermissionAgent(ConformingAgent):
    """Conforming, but sends `session/request_permission` mid-turn (after the running update)
    and only finishes the turn once the client answers -- the normal shape a real tool-using
    agent produces (`.agents/research/acp-v2-prompt-lifecycle.md` C1-C3: `title`/`options`
    required, each option carrying `optionId`/`name`/`kind`). Honors the outcome: `"cancelled"`
    becomes the turn's `stopReason`, anything else (including `"selected"`) becomes
    `"end_turn"`. `ACP-PERM-201`'s self-test -- exercises `run_prompt`'s permission-answering
    path, which nothing else under `tests/fixtures/agents/v2/` exercises.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._perm_counter = 0
        self._pending_permission: dict[str, Any] | None = None

    def _mid_turn_action(self, session_id: Any) -> bool:
        self._perm_counter += 1
        perm_id = f"perm-{self._perm_counter}"
        self._pending_permission = {"perm_id": perm_id, "session_id": session_id}
        self._write(
            {
                "jsonrpc": "2.0",
                "id": perm_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": session_id,
                    "title": "Allow this action?",
                    "options": [
                        {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            }
        )
        return True  # defer finishing the turn to `_handle_response`, below

    def _handle_response(self, message: dict[str, Any]) -> None:
        pending = self._pending_permission
        if pending is None or message.get("id") != pending["perm_id"]:
            return  # not a reply to our own outstanding permission request
        self._pending_permission = None
        result = message.get("result") or {}
        outcome = (result.get("outcome") or {}).get("outcome")
        stop_reason = "cancelled" if outcome == "cancelled" else "end_turn"
        self._finish_turn(pending["session_id"], stop_reason)


class SendsClientRequestAgent(ConformingAgent):
    """Conforming, but fires one arbitrary agent -> client request mid-turn (after the running
    update) and continues immediately -- it never waits for a reply, since the CLIENTCAP
    fixtures built on this only care *whether/what* was sent, not how the mock client answered
    it. Subclasses provide the method name (`_client_request_method`) and, optionally, its
    params (`_client_request_params`, empty `{}` by default).
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._probe_counter = 0

    def _client_request_method(self) -> str:
        raise NotImplementedError

    def _client_request_params(self, session_id: Any) -> dict[str, Any]:
        return {}

    def _mid_turn_action(self, session_id: Any) -> bool:
        self._probe_counter += 1
        self._write(
            {
                "jsonrpc": "2.0",
                "id": f"probe-{self._probe_counter}",
                "method": self._client_request_method(),
                "params": self._client_request_params(session_id),
            }
        )
        return False  # fire-and-forget: finish the turn immediately, in the same call
