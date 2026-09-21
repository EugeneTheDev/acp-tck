#!/usr/bin/env python3
"""Non-conforming fixture: every prompt hangs until `session/cancel` (not just the `__hang__`
sentinel), but on cancel it finishes the turn with `stopReason: "end_turn"` instead of
`"cancelled"`. FAILs `ACP-CANCEL-201`/`207`/`203`, and `ACP-CANCEL-206` (the `_meta`-carrying
cancel scenario hits the same overridden `_handle_cancel`, so it resolves wrong too).
`ACP-CANCEL-202` SKIPs, deferring to the rows above -- it requires the turn to have actually
resolved with `stopReason: "cancelled"` via `session/cancel` first, which it never does here.
`ACP-CANCEL-208` still PASSes, though: its own test drives the cancellation via `session/close`
(not `session/cancel`), which hits the base `ConformingAgent`'s unmodified close handling --
this fixture only overrides `_handle_cancel`, so the close-triggered path resolves correctly with
`stopReason: "cancelled"` regardless of this defect.

Finishing *immediately* on cancel would land inside the TCK's "was this actually exercised" race
window (`tck.v2.conformance._helpers.quiet_period`, derived from `--tck-timeout`) -- since
`"end_turn"` is itself a valid `StopReason`, an instant reply would make `ACP-CANCEL-201`/`203`/
`207` SKIP instead of FAIL, hiding this fixture's whole reason for existing. Sleeping 1.2s
comfortably clears that window for the self-test's `--timeout 2` (a 0.5s window).
"""

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CancelWrongStopReasonAgent(ConformingAgent):
    @staticmethod
    def _is_hang_prompt(prompt: list[Any]) -> bool:
        return True  # hang on every prompt, not just the `__hang__` sentinel

    def _handle_cancel(self, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if self._hanging_sessions.pop(session_id, None) is not None:
            time.sleep(1.2)  # stay outside the TCK's race window -- see module docstring
            self._finish_turn(session_id, "end_turn")


def main() -> None:
    CancelWrongStopReasonAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
