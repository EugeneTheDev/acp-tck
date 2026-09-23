#!/usr/bin/env python3
"""Non-conforming fixture: exits the moment it sees any batch-shaped (top-level JSON array) line
on stdin -- otherwise fully conforming. FAILs only the requirements whose tests send a batch
line (`ACP-BATCH-*`, `ACP-INFO-BATCH-*`) via `AgentExited`; unrelated ids are unaffected since
their tests never send a batch-shaped line.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CrashesOnBatchAgent(ConformingAgent):
    def _handle_batch(self, items: list[Any]) -> None:
        sys.exit(1)


def main() -> None:
    CrashesOnBatchAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
