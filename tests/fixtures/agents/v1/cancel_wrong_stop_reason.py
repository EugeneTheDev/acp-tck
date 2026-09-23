#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel`, but on cancel it responds
to the prompt with `stopReason: "end_turn"` instead of `"cancelled"`. Violates ACP-CANCEL-001.

Replying immediately would land inside the TCK's cancel-race window
(`tck.v1.conformance._helpers.quiet_period`, derived from `--tck-timeout`); since `"end_turn"` is
itself a valid `StopReason`, that would SKIP instead of FAIL. Sleeping 1.2s clears the window for
any `--tck-timeout` this fixture runs under (self-test uses `--timeout 5`, a 0.5s window).
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
