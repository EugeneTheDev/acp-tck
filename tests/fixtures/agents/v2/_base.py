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

    def _handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method is None:
            return  # a response, or otherwise not a request/notification -- ignore
        params = message.get("params") or {}
        if "id" in message:
            self._handle_request(method, message["id"], params)
        elif method == "session/cancel":
            pass  # no-op: this fixture's session/prompt never blocks awaiting cancellation

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
        session_id = params.get("sessionId")
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
        session_id = params.get("sessionId")
        self._message_count += 1
        message_id = f"msg-{self._message_count:04d}"
        self._reply_to_prompt(msg_id, message_id)
        prompt = params.get("prompt") or []
        self._send_user_message_update(session_id, message_id, prompt)
        self._send_running_update(session_id)
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
        self._send_idle_update(session_id, self._stop_reason())

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

    @staticmethod
    def _write(obj: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()
