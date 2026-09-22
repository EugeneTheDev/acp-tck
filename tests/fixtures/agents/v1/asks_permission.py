#!/usr/bin/env python3
"""Conforming fixture that asks for permission mid-turn: on `session/prompt` it sends
`session/request_permission` (the normal shape a real tool-using agent produces --
`docs/protocol/v1/prompt-turn.mdx:32-43`) and only resolves the prompt once the client answers,
honoring whichever option the client selected (or the "cancelled" outcome if the client answers
that way after `session/cancel`).

Exists to exercise the mock client's permission-answering path
(`tck.v1.conformance._helpers.run_prompt`), which nothing else in `tests/fixtures/agents/`
exercises -- every prompt/cancel test in the real suite depends on that path working, so it
needs its own self-test coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class AsksPermissionAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._awaiting_permission: dict[str, Any] | None = None
        self._perm_id_counter = 0

    def _handle(self, message: dict[str, Any]) -> None:
        if message.get("method") is None:
            self._handle_client_response(message)
            return
        super()._handle(message)

    def _handle_client_response(self, message: dict[str, Any]) -> None:
        pending = self._awaiting_permission
        if pending is None or message.get("id") != pending["perm_id"]:
            return  # not a reply to our own outstanding permission request
        self._awaiting_permission = None
        result = message.get("result") or {}
        outcome = (result.get("outcome") or {}).get("outcome")
        stop_reason = "cancelled" if outcome == "cancelled" else "end_turn"
        self._reply(pending["prompt_id"], {"stopReason": stop_reason})

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

        self._perm_id_counter += 1
        perm_id = f"perm-{self._perm_id_counter}"
        self._awaiting_permission = {"prompt_id": msg_id, "perm_id": perm_id}
        self._write(
            {
                "jsonrpc": "2.0",
                "id": perm_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": session_id,
                    "toolCall": {"toolCallId": "tool-1"},
                    "options": [
                        {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            }
        )

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel" and self._awaiting_permission is not None:
            # Cancellation while a permission request is outstanding: the mock client answers
            # the outstanding request with the "cancelled" outcome (see `run_prompt`), which
            # `_handle_client_response` above turns into the prompt's own cancelled response --
            # nothing else to do here, just don't fall through to the base class's
            # `_pending_prompt`-based cancel handling (unused by this fixture).
            return
        super()._handle_notification(method, params)


def main() -> None:
    AsksPermissionAgent().run()


if __name__ == "__main__":
    main()
