#!/usr/bin/env python3
"""Non-conforming fixture: writes one line of invalid UTF-8 bytes to stdout before behaving
like a conforming agent. Violates ACP-TRANSPORT-002 ("the agent's stdout is valid UTF-8").

The only real negative control for ACP-TRANSPORT-002 in the self-test suite (review S2) --
`banner_on_stdout.py`'s banner is plain ASCII, so it is valid UTF-8 and must PASS this
requirement even though it FAILs ACP-TRANSPORT-001.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def _write_invalid_utf8() -> None:
    sys.stdout.buffer.write(b"\xff\xfe not valid utf-8\n")
    sys.stdout.buffer.flush()


def main() -> None:
    ConformingAgent(on_start=_write_invalid_utf8).run()


if __name__ == "__main__":
    main()
