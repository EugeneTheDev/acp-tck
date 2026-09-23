#!/usr/bin/env python3
"""Non-conforming fixture: prints a human banner line to stdout before behaving like a
conforming agent -- violates the v2 "agent MUST NOT write anything to stdout that is not a
valid ACP message" transport rule (`ACP-TRANSPORT-201`). Mirrors v1's `banner_on_stdout.py`
on top of v2's `_base.py` -- never imports v1's own fixture module.

v2's `ConformingAgent` has no `on_start` hook (unlike v1's), so the banner is printed directly
in `main()` before `run()` ever touches stdout.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def main() -> None:
    print("Hello from banner_on_stdout, a proudly non-conforming agent!")
    sys.stdout.flush()
    ConformingAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
