#!/usr/bin/env python3
"""Non-conforming fixture: `session/close` on a session with a still-hanging `__hang__` prompt
replies to the close normally, but resolves the hanging turn with `stopReason: "end_turn"`
instead of `"cancelled"` -- and only after sleeping past the TCK's cancel-race window, so the
deviation is unambiguously observed rather than mistaken for an honest race and SKIPped.

Deliberately keeps `ConformingAgent`'s default `_is_hang_prompt` (hangs only on the literal
`__hang__` sentinel, exactly like `conforming.py`) so the defect stays bounded: driving this
fixture requires `--cancel-prompt __hang__` (as `test_close_cancels_foreground_work` itself uses
`cancel_prompt_text`, which is that sentinel only when explicitly overridden -- see
`tests/v2/test_cli.py`'s self-test). Every other prompt in the suite finishes normally on its
own, so no other test's `run_prompt` call ever hangs.

FAILs exactly `ACP-CANCEL-208`/`ACP-CLOSE-202` (dual-bound to the same test,
`test_close_cancels_foreground_work`) when run with `--cancel-prompt __hang__`. Every other id,
including plain `ACP-CANCEL-201..207` (which use `session/cancel`, not `session/close`, to end
the turn) and `ACP-CLOSE-201` (closing an already-idle session, no hang involved), is
unaffected.
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
