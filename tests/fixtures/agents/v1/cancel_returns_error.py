#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel`, but on cancel it responds
to the prompt with a JSON-RPC error (`-32800`) instead of a successful `cancelled` result.
Violates ACP-CANCEL-001 (Reqs 25, 26 -- the agent must return `stopReason: "cancelled"`, not an
error, even when it does catch the cancellation).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CancelReturnsErrorAgent(ConformingAgent):
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
        self._pending_prompt = {"id": msg_id, "session_id": session_id}

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel" and self._pending_prompt is not None:
            if self._pending_prompt["session_id"] == params.get("sessionId"):
                pending = self._pending_prompt
                self._pending_prompt = None
                self._error(pending["id"], -32800, "Request cancelled")
                return
        super()._handle_notification(method, params)


def main() -> None:
    CancelReturnsErrorAgent().run()


if __name__ == "__main__":
    main()
