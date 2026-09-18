#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel`, but on cancel it responds
to the prompt with `stopReason: "end_turn"` instead of `"cancelled"`. Violates ACP-CANCEL-001
(Req 25).

Answering *immediately* on cancel would land inside the TCK's 1.0s "was this actually
exercised" race window (`test_cancel.py::_CANCEL_RACE_WINDOW`) -- since `"end_turn"` is itself a
valid `StopReason`, an instant reply would make ACP-CANCEL-001 SKIP instead of FAIL, hiding this
fixture's whole reason for existing. Sleeping past the window keeps the defect detectable.
"""

import sys
import time
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
                time.sleep(1.2)  # stay outside the TCK's 1.0s race window -- see module docstring
                self._reply(pending["id"], {"stopReason": "end_turn"})
                return
        super()._handle_notification(method, params)


def main() -> None:
    CancelWrongStopReasonAgent().run()


if __name__ == "__main__":
    main()
