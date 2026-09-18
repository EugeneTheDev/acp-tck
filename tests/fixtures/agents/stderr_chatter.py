#!/usr/bin/env python3
"""Conforming fixture that also logs to stderr on every message it receives.

Used to prove the harness's `stderr_text()` capture works without blocking the child.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def _log(line: str) -> None:
    print(f"stderr_chatter received: {line}", file=sys.stderr, flush=True)


def main() -> None:
    ConformingAgent(on_message=_log).run()


if __name__ == "__main__":
    main()
