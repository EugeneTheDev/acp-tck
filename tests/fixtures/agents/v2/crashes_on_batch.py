#!/usr/bin/env python3
"""Non-conforming fixture: exits the moment it sees any batch-shaped (top-level JSON array) line
on stdin -- otherwise fully conforming, including for every non-batch single-message exchange.

FAILs every requirement whose own test actually sends a batch line: `ACP-BATCH-201`/`202`/`203`,
the shared `ACP-BATCH-204`/`205` test, and `ACP-INFO-BATCH-201`/`202` (INFORMATIONAL -- but the
prerequisite handshake inside `_v2_only_agent` still succeeds, only the batch probe itself dies,
so these become `AgentExited` FAILs rather than a recorded behaviour). `ACP-BATCH-206`/`207`/`208`
are unaffected -- they are unconditional record-only SKIPs that never send anything at all.
Every other id in this slice (`ACP-TRANSPORT-*`, `ACP-JSONRPC-*`, and everything cancellation-
related) is unaffected: none of those tests ever sends a batch-shaped line, so this fixture's
only defect is never triggered outside `test_batch.py` -- the acceptance-criteria example of a
fixture that must fail *only* batch rows.
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
