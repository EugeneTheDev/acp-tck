#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel`, but on cancel it responds
to the prompt with `stopReason: "end_turn"` instead of `"cancelled"`. Violates ACP-CANCEL-001
(Req 25).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CancelWrongStopReasonAgent(ConformingAgent):
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
                self._reply(pending["id"], {"stopReason": "end_turn"})
                return
        super()._handle_notification(method, params)


def main() -> None:
    CancelWrongStopReasonAgent().run()


if __name__ == "__main__":
    main()
