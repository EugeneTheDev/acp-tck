#!/usr/bin/env python3
"""A defect fixture for ACP-AUTH-202's MUST NOT: advertises an `authMethods` entry with
`type: "terminal"` unconditionally, even to a client that never advertised
`capabilities.auth.terminal`. v2 port of `tests/fixtures/agents/v1/terminal_auth_unadvertised.py`
(field renamed `id` -> `methodId`).

Fails only ACP-AUTH-202 (MANDATORY): the terminal descriptor itself is otherwise well-formed (no
`args`/`env`), so it does not also trip ACP-AUTH-207 on the dedicated second connection that does
advertise `capabilities.auth.terminal`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"methodId": "term", "type": "terminal", "name": "Terminal"},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-terminal-auth-unadvertised-v2",
        auth_methods=AUTH_METHODS,
    ).run()


if __name__ == "__main__":
    main()
