#!/usr/bin/env python3
"""Non-conforming fixture: every (non-`__hang__`) prompt resolves with `stopReason: "done"`,
which is not one of the five defined `StopReason` values. Violates ACP-PROMPT-001 (Req 24) and,
incidentally, ACP-SCHEMA-001 (the enum is closed in the schema).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class BadStopReasonAgent(ConformingAgent):
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
            self._pending_prompt = {"id": msg_id, "session_id": session_id}
            return
        self._reply(msg_id, {"stopReason": "done"})


def main() -> None:
    BadStopReasonAgent().run()


if __name__ == "__main__":
    main()
