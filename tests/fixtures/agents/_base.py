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
    """

    def __init__(
        self,
        *,
        on_start: Callable[[], None] | None = None,
        on_message: Callable[[str], None] | None = None,
    ) -> None:
        self._session_count = 0
        self._pending_prompt: dict[str, Any] | None = None
        self._on_start = on_start
        self._on_message = on_message

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
            self._reply(msg_id, self._initialize_result())
        elif method == "session/new":
            self._session_count += 1
            self._reply(msg_id, {"sessionId": f"sess-{self._session_count:04d}"})
        elif method == "session/prompt":
            self._handle_prompt(msg_id, params)
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

    @staticmethod
    def _initialize_result() -> dict[str, Any]:
        # Only version 1 is supported, so the response is always 1 -- never echo a version
        # the agent does not actually support (protocol-surface report, Req #5).
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": {},
            "agentInfo": {"name": "tck-fixture-conforming", "version": "0.0.0"},
        }

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
        self._notify(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        )

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
