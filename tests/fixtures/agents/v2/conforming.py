#!/usr/bin/env python3
"""A conforming ACP v2 (Draft) fixture agent: deterministic, offline, stdlib only.

See `_base.ConformingAgent` for the behavior. Mirrors `tests/fixtures/agents/v1/conforming.py`'s
role as the harness's known-good baseline, for the v2 conformance suite. Advertises
`capabilities: {"session": {}}` so every `capabilities.session`-gated test (e.g.
`ACP-SESSION-001/002`) actually runs and PASSes, rather than SKIPping.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def main() -> None:
    ConformingAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
