#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel`; on cancel it replies
`stopReason: "cancelled"` correctly, but then sends one more `session/update` for that session
afterwards. Violates ACP-CANCEL-002 (Req 28 -- updates may follow cancellation, but never the
prompt response).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class UpdateAfterResponseAgent(ConformingAgent):
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
                self._reply(pending["id"], {"stopReason": "cancelled"})
                self._send_update(pending["session_id"], "late update sent after the response")
                return
        super()._handle_notification(method, params)


def main() -> None:
    UpdateAfterResponseAgent().run()


if __name__ == "__main__":
    main()
