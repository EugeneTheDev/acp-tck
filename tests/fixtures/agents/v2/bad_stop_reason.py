#!/usr/bin/env python3
"""Non-conforming fixture: the turn-ending idle carries a `stopReason` that is not one of the
five defined constants and does not begin with `_` -- an illegal, non-extension value.

FAILs exactly `ACP-STATE-203` (the idle's `stopReason` must be a defined constant or an
open-enum `_`-prefixed extension). `ACP-STATE-201` (`running` observed before the idle) and
`ACP-STATE-202` (idle arrives after `running`) are unaffected -- both `running` and a
stop-reason-bearing idle are still observed, just with an illegal value. `ACP-PROMPT-201`/
`ACP-PROMPT-203`/`ACP-PROMPT-002` are all unaffected too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class BadStopReasonAgent(ConformingAgent):
    def _stop_reason(self) -> str:
        return "done"


def main() -> None:
    BadStopReasonAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
