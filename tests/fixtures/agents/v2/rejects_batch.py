#!/usr/bin/env python3
"""Non-conforming fixture: every batch, empty or not, gets the empty-batch response -- a single
top-level Invalid Request (`-32600`, `id: null`) object, never per-entry handling.

Coincidentally still PASSes `ACP-BATCH-201` (the empty-array case is exactly this behavior).
FAILs `ACP-BATCH-202` (notification-only batch gets a bogus reply instead of silence),
`ACP-BATCH-203` (a valid entry alongside an invalid one never runs), and `ACP-BATCH-204`/`205`
(no response array is ever produced).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class RejectsBatchAgent(ConformingAgent):
    def _handle_batch(self, items: list[Any]) -> None:
        self._write_line(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        )


def main() -> None:
    RejectsBatchAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
