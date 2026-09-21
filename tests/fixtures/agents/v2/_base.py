"""Shared core for the conforming ACP v2 (Draft) fixture agent.

Not part of the installed `tck` package: fixture scripts are launched as standalone
subprocesses (`python .../conforming.py`), so they import this module by inserting their own
directory onto `sys.path` rather than a package-relative import -- same pattern as v1's
`tests/fixtures/agents/v1/_base.py`, but a fresh, much smaller implementation (not imported from
v1): this skeleton slice's registry only exercises `initialize`, so only `initialize` and
`session/new` need real behavior; every other v2 method is left for a follow-up slice.

Wire shapes are taken from the vendored `src/tck/v2/schema/schema.json` (`InitializeRequest`/
`InitializeResponse`/`NewSessionRequest`/`NewSessionResponse`) -- verify against that schema, not
memory, before changing a field name. Two v2-specific renames vs. v1: the agent's own identity is
`info` (not `agentInfo`) and its capabilities are `capabilities` (not `agentCapabilities`).
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

    Handles `initialize` (honest version negotiation across `_SUPPORTED_VERSIONS`) and
    `session/new` (unique `sessionId`). Any other method gets `-32601`. Exits cleanly on stdin
    EOF (the `for` loop over `sys.stdin` simply ends).

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
        self._capabilities = capabilities if capabilities is not None else {}
        self._agent_name = agent_name

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
        # no notifications are handled by this skeleton core -- session/cancel is a no-op here

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._reply(msg_id, self._initialize_result(params))
        elif method == "session/new":
            self._handle_new_session(msg_id, params)
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
        self._reply(msg_id, {"sessionId": session_id})

    def _reply(self, msg_id: Any, result: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _error(self, msg_id: Any, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})

    @staticmethod
    def _write(obj: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()
