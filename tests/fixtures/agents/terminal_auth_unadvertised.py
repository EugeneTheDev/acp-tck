#!/usr/bin/env python3
"""A defect fixture for the ACP-AUTH-002 (Req 23) MUST NOT: advertises an `authMethods` entry
with `type: "terminal"` unconditionally, even to a client that never advertised
`clientCapabilities.auth.terminal`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"id": "term", "name": "Terminal", "type": "terminal"},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-terminal-auth-unadvertised",
        auth_methods=AUTH_METHODS,
    ).run()


if __name__ == "__main__":
    main()
