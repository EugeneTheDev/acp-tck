#!/usr/bin/env python3
"""Conforming fixture that asks for permission mid-turn, but advertises only the plain
`session: {}` baseline (no prompt-content capabilities). Isolates `ACP-PERM-201`'s self-test
from `conforming_full.py`'s broader capability set -- must PASS every V2-2b id whose gate this
fixture actually satisfies: PERM-201, CLIENTCAP-201/202, PROMPT-003, and both INFORMATIONAL
probes. PROMPTCAP-001/002/003 SKIP ("not advertised"), since this fixture does not advertise
`capabilities.session.prompt.*`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import AsksPermissionAgent  # noqa: E402


def main() -> None:
    AsksPermissionAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
