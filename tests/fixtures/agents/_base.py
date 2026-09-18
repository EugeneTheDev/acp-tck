"""Shared core for the conforming fixture agent, reused by several fixture scripts.

Not part of the installed `tck` package: fixture scripts are launched as standalone
subprocesses (`python .../conforming.py`), so they import this module by inserting their own
directory onto `sys.path` rather than a package-relative import.

Wire shapes here are taken from `.agents/research/acp-v1-protocol-surface.md` (§Details 1, 2,
3) -- verify against that report, not memory, before changing a field name.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

PROTOCOL_VERSION = 1


class ConformingAgent:
    """A minimal, deterministic, offline ACP v1 agent.

    Handles `initialize`, `session/new`, `session/prompt`, `session/cancel`, and the
    harness-only `_tck/env` extension method used to prove env-var overrides reach the child.
    Any other method gets `-32601`. Exits cleanly on stdin EOF (the `for` loop over
    `sys.stdin` simply ends).

    `capabilities`, if given, is merged verbatim into the `initialize` result's
    `agentCapabilities` (used by `conforming_full.py` to advertise `loadSession` and every
    `sessionCapabilities` marker; `conforming.py` passes `None`, i.e. `{}`, so every
    capability-conditional test SKIPs against it -- `.agents/research/acp-v1-session-
    capabilities.md`). The `session/load`, `session/resume`, `session/list`, `session/delete`,
    and `session/close` handlers below are implemented unconditionally (not gated on whether
    `capabilities` mentions them) since the conformance suite itself only ever calls them
    behind a `@pytest.mark.capability(...)` marker that already SKIPs when unadvertised --
    keeping the logic ungated here just means it's available to any fixture that wants it via
    subclassing (see the `ACP-LOAD-*`/`ACP-RESUME-*` defect fixtures).
    """

    def __init__(
        self,
        *,
        on_start: Callable[[], None] | None = None,
        on_message: Callable[[str], None] | None = None,
        capabilities: dict[str, Any] | None = None,
        agent_name: str = "tck-fixture-conforming",
        modes: dict[str, Any] | None = None,
        config_options: list[dict[str, Any]] | None = None,
        auth_methods: list[dict[str, Any]] | None = None,
        require_auth: bool = False,
        emit_mode_update: bool = False,
        mode_update_field: str = "currentModeId",
        ignore_boolean_gating: bool = False,
    ) -> None:
        self._session_count = 0
        self._pending_prompt: dict[str, Any] | None = None
        self._on_start = on_start
        self._on_message = on_message
        self._capabilities = capabilities if capabilities is not None else {}
        self._agent_name = agent_name
        self._sessions: dict[str, dict[str, Any]] = {}
        self._modes = modes
        self._config_options = config_options
        self._auth_methods = auth_methods
        self._require_auth = require_auth
        self._authenticated = False
        self._emit_mode_update = emit_mode_update
        self._mode_update_field = mode_update_field
        self._ignore_boolean_gating = ignore_boolean_gating
        self._client_capabilities: dict[str, Any] = {}

    def run(self) -> None:
        if self._on_start is not None:
            self._on_start()
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            if self._on_message is not None:
                self._on_message(line)
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
        else:
            self._handle_notification(method, params)

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._client_capabilities = params.get("clientCapabilities") or {}
            self._reply(msg_id, self._initialize_result())
        elif method == "session/new":
            self._handle_new_session(msg_id, params)
        elif method == "session/prompt":
            self._handle_prompt(msg_id, params)
        elif method == "session/load":
            self._handle_load(msg_id, params)
        elif method == "session/resume":
            self._handle_resume(msg_id, params)
        elif method == "session/list":
            self._handle_list(msg_id, params)
        elif method == "session/delete":
            self._handle_delete(msg_id, params)
        elif method == "session/close":
            self._handle_close(msg_id, params)
        elif method == "session/set_mode":
            self._handle_set_mode(msg_id, params)
        elif method == "session/set_config_option":
            self._handle_set_config_option(msg_id, params)
        elif method == "authenticate":
            self._handle_authenticate(msg_id, params)
        elif method == "logout":
            self._handle_logout(msg_id, params)
        elif method == "_tck/env":
            self._reply(msg_id, {"value": os.environ.get(params.get("name", ""))})
        elif method == "_tck/big":
            # Harness-only probe (`_`-prefixed, per Req 42): reply with a `size`-byte string so
            # tests can exercise the line-limit handling in `AgentProcess._read_raw_line`
            # (`.agents/research/review-slices-1-4.md` B1) without needing a dedicated fixture.
            size = params.get("size", 2_000_000)
            self._reply(msg_id, {"value": "x" * size})
        else:
            self._error(msg_id, -32601, "Method not found")

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel" and self._pending_prompt is not None:
            if self._pending_prompt["session_id"] == params.get("sessionId"):
                pending = self._pending_prompt
                self._pending_prompt = None
                self._reply(pending["id"], {"stopReason": "cancelled"})
        # other/unknown notifications (including unrecognized `_`-prefixed ones) are ignored

    def _initialize_result(self) -> dict[str, Any]:
        # Only version 1 is supported, so the response is always 1 -- never echo a version
        # the agent does not actually support (protocol-surface report, Req #5).
        result: dict[str, Any] = {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": dict(self._capabilities),
            "agentInfo": {"name": self._agent_name, "version": "0.0.0"},
        }
        if self._auth_methods is not None:
            result["authMethods"] = self._auth_methods
        return result

    def _client_advertised_boolean_config(self) -> bool:
        session_caps = self._client_capabilities.get("session")
        if not isinstance(session_caps, dict):
            return False
        return session_caps.get("configOptions", {}).get("boolean") is not None

    def _visible_config_options(self) -> list[dict[str, Any]] | None:
        """`self._config_options`, filtered to honor Req 33: a `type: "boolean"` option is
        dropped unless the client advertised `clientCapabilities.session.configOptions.boolean`
        -- unless `ignore_boolean_gating` is set (used by the `boolean_option_unadvertised.py`
        defect fixture, which deliberately violates this MUST NOT for ACP-CONFIG-003)."""
        if self._config_options is None:
            return None
        if self._ignore_boolean_gating or self._client_advertised_boolean_config():
            return list(self._config_options)
        return [opt for opt in self._config_options if opt.get("type") != "boolean"]

    def _handle_new_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        if self._require_auth and not self._authenticated:
            self._error(msg_id, -32000, "Authentication required")
            return
        self._session_count += 1
        session_id = f"sess-{self._session_count:04d}"
        self._sessions[session_id] = {"cwd": params.get("cwd"), "history": []}
        result: dict[str, Any] = {"sessionId": session_id}
        if self._modes is not None:
            result["modes"] = self._modes
        visible_config = self._visible_config_options()
        if visible_config is not None:
            result["configOptions"] = visible_config
        self._reply(msg_id, result)

    def _handle_set_mode(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        mode_id = params.get("modeId")
        if self._modes is not None:
            self._modes["currentModeId"] = mode_id
        self._reply(msg_id, {})
        if self._emit_mode_update:
            self._notify(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "current_mode_update",
                        self._mode_update_field: mode_id,
                    },
                },
            )

    def _handle_set_config_option(self, msg_id: Any, params: dict[str, Any]) -> None:
        config_id = params.get("configId")
        value = params.get("value")
        if self._config_options is not None:
            for option in self._config_options:
                if option.get("id") == config_id:
                    option["currentValue"] = value
                    break
        self._reply(msg_id, {"configOptions": self._visible_config_options() or []})

    def _handle_authenticate(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._authenticated = True
        self._reply(msg_id, {})

    def _handle_logout(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._authenticated = False
        self._reply(msg_id, {})

    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        prompt = params.get("prompt") or []
        first_text = next(
            (
                block.get("text", "")
                for block in prompt
                if isinstance(block, dict) and block.get("type") == "text"
            ),
            "",
        )
        self._send_update(session_id, first_text)
        if first_text == "__hang__":
            # Deliberately do not respond until `session/cancel` arrives for this session --
            # this is how the cancel flow is made testable (see task spec, fixture #1). The
            # update above still goes out immediately, so it always precedes the eventual
            # (cancelled) response.
            self._pending_prompt = {"id": msg_id, "session_id": session_id}
            return
        self._reply(msg_id, {"stopReason": "end_turn"})

    def _send_update(self, session_id: str, text: str) -> None:
        update_params = {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        }
        session = self._sessions.get(session_id)
        if session is not None:
            session["history"].append(update_params)
        self._notify("session/update", update_params)

    def _handle_load(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        session = self._sessions.get(session_id)
        if session is None:
            session = {"cwd": params.get("cwd"), "history": []}
            self._sessions[session_id] = session
        for update_params in session["history"]:
            self._notify("session/update", update_params)
        self._reply(msg_id, {})

    def _handle_resume(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            self._sessions[session_id] = {"cwd": params.get("cwd"), "history": []}
        # Deliberately no replay -- ACP-RESUME-002 requires history-kind updates not be sent
        # before this response (`.agents/research/acp-v1-session-capabilities.md` R2).
        self._reply(msg_id, {})

    def _handle_list(self, msg_id: Any, params: dict[str, Any]) -> None:
        cwd_filter = params.get("cwd")
        sessions = []
        for session_id, session in self._sessions.items():
            if cwd_filter is not None and session.get("cwd") != cwd_filter:
                continue
            sessions.append({"sessionId": session_id, "cwd": session.get("cwd")})
        self._reply(msg_id, {"sessions": sessions})

    def _handle_delete(self, msg_id: Any, params: dict[str, Any]) -> None:
        # SHOULD succeed silently even for an unknown sessionId (research D2) -- `dict.pop`
        # with a default already gives us that for free.
        self._sessions.pop(params.get("sessionId"), None)
        self._reply(msg_id, {})

    def _handle_close(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if self._pending_prompt is not None and self._pending_prompt["session_id"] == session_id:
            pending = self._pending_prompt
            self._pending_prompt = None
            self._reply(pending["id"], {"stopReason": "cancelled"})
        self._sessions.pop(session_id, None)
        self._reply(msg_id, {})

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


class SendsClientRequestAgent(ConformingAgent):
    """Shared base for the `ACP-CLIENTCAP-00*` defect fixtures: on `session/prompt`, sends one
    agent -> client request (`_client_method`/`_client_params`, set by a subclass) mid-turn,
    waits for whatever reply the mock client sends back (the TCK's mock client advertises
    `clientCapabilities: {}` and answers with `-32601`, per `_helpers.run_prompt`, since none of
    `fs`/`terminal`/`elicitation` is ever advertised in `test_client_capabilities.py`), and only
    then completes the turn normally with `stopReason: "end_turn"` -- regardless of how the
    client answered, since the point of the fixture is that the *request itself* should never
    have been sent, not how the client reacts to it.

    Modeled directly on `asks_permission.py`'s `AsksPermissionAgent`: same
    intercept-ID-less-replies-in-`_handle`, same outstanding-request bookkeeping, same
    cancel-notification passthrough.
    """

    _client_method: str = ""
    _client_params: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._awaiting_client_reply: dict[str, Any] | None = None
        self._req_id_counter = 0

    def _handle(self, message: dict[str, Any]) -> None:
        if message.get("method") is None:
            self._handle_client_response(message)
            return
        super()._handle(message)

    def _handle_client_response(self, message: dict[str, Any]) -> None:
        pending = self._awaiting_client_reply
        if pending is None or message.get("id") != pending["req_id"]:
            return  # not a reply to our own outstanding request
        self._awaiting_client_reply = None
        self._reply(pending["prompt_id"], {"stopReason": "end_turn"})

    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        self._req_id_counter += 1
        req_id = f"tck-clientcap-{self._req_id_counter}"
        self._awaiting_client_reply = {"prompt_id": msg_id, "req_id": req_id}
        client_params = dict(self._client_params)
        client_params.setdefault("sessionId", session_id)
        self._write(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": self._client_method,
                "params": client_params,
            }
        )

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel" and self._awaiting_client_reply is not None:
            return  # nothing else to do; no reply expected before the client answers our request
        super()._handle_notification(method, params)
