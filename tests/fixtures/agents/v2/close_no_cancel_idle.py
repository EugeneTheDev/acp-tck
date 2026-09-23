#!/usr/bin/env python3
"""Non-conforming fixture: `session/close` on a session with a still-hanging `__hang__` prompt
replies to the close normally, but resolves the hanging turn with `stopReason: "end_turn"`
instead of `"cancelled"` -- after sleeping past the TCK's cancel-race window so the deviation
isn't mistaken for an honest race and SKIPped.

Only requires `--cancel-prompt __hang__` to trigger, since `_is_hang_prompt` still hangs only on
that literal sentinel (see `conforming.py`). Every other prompt finishes normally.

FAILs exactly `ACP-CANCEL-208`/`ACP-CLOSE-202` (both bound to
`test_close_cancels_foreground_work`, see `tests/v2/test_cli.py`) when run with that flag; other
ids (`ACP-CANCEL-201..207`, `ACP-CLOSE-201`) are unaffected.
"""

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CloseNoCancelIdleAgent(ConformingAgent):
    def _handle_close_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        self._sessions.pop(session_id, None)
        self._reply(msg_id, {})
        if self._hanging_sessions.pop(session_id, None) is not None:
            time.sleep(1.2)  # stay outside the TCK's race window
            self._finish_turn(session_id, "end_turn")


def main() -> None:
    CloseNoCancelIdleAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
