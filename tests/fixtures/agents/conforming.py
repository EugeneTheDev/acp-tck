#!/usr/bin/env python3
"""A conforming ACP v1 fixture agent: deterministic, offline, stdlib only.

See `_base.ConformingAgent` for the behavior. This is the harness's known-good baseline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def main() -> None:
    ConformingAgent().run()


if __name__ == "__main__":
    main()
