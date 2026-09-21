#!/usr/bin/env python3
"""Non-conforming fixture: every non-empty batch array, regardless of contents, gets treated as
if it were the *empty*-batch case -- a single top-level Invalid Request (`-32600`, `id: null`)
object, never a per-entry response, never a response array, and never silence for a
notification-only batch.

This coincidentally still satisfies `ACP-BATCH-201` (the empty-array case itself, `[]` -> one
`-32600`/`id: null` object, is exactly what this fixture already does for every batch). It FAILs
`ACP-BATCH-202` (a notification-only batch gets a bogus reply instead of no output at all),
`ACP-BATCH-203` (an invalid entry's valid sibling never runs -- there is no per-entry handling at
all), and the shared `ACP-BATCH-204`/`205` test (no response array matching the batch's own
requests is ever produced). None of `test_transport.py`/`test_jsonrpc.py` is affected: neither
drives a batch-shaped line at all.
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
