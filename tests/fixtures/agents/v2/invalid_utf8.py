#!/usr/bin/env python3
"""Non-conforming fixture: writes one line of invalid UTF-8 bytes to stdout before behaving
like a conforming agent. Violates ACP-TRANSPORT-002 ("the agent's stdout is valid UTF-8").
Mirrors v1's `invalid_utf8.py` on top of v2's `_base.py` (D6).

The only real negative control for ACP-TRANSPORT-002 in the v2 self-test suite --
`banner_on_stdout.py`'s banner is plain ASCII, so it is valid UTF-8 and must still PASS this
requirement even though it FAILs ACP-TRANSPORT-201.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def main() -> None:
    sys.stdout.buffer.write(b"\xff\xfe not valid utf-8\n")
    sys.stdout.buffer.flush()
    ConformingAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
