#!/usr/bin/env python3
"""Non-conforming fixture: skips `state_update {state: "running"}` entirely and jumps straight
to a turn-ending idle carrying `stopReason: "end_turn"`.

FAILs exactly `ACP-STATE-201` (the idle carries a `stopReason`, so its gate is satisfied and the
assertion that a `running` update preceded it fails). `ACP-STATE-202`/`ACP-STATE-203` SKIP as "no
foreground work observed": their gate is `running_seen`, which this fixture never sets -- see
`tck.v2.requirements`'s `ACP-STATE-201` docstring for why it needed its own gate.
`ACP-PROMPT-201`/`ACP-PROMPT-203`/`ACP-PROMPT-205` are unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class NoRunningUpdateAgent(ConformingAgent):
    def _send_running_update(self, session_id: Any) -> None:
        pass  # deliberately omitted


def main() -> None:
    NoRunningUpdateAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
