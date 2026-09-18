#!/usr/bin/env python3
"""Non-conforming fixture: prints a human banner line to stdout before behaving like a
conforming agent -- violates T7 ("agent MUST NOT write anything to stdout that is not a
valid ACP message"). Used to prove the harness records the resulting parse error instead of
dropping the line or crashing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def _print_banner() -> None:
    print("Hello from banner_on_stdout, a proudly non-conforming agent!")
    sys.stdout.flush()


def main() -> None:
    ConformingAgent(on_start=_print_banner).run()


if __name__ == "__main__":
    main()
