#!/usr/bin/env python3
"""An agent that requires authentication before `session/new` will succeed: advertises one
`authMethods` entry (`id: "tck"`) and answers `session/new` with `-32000` (authentication
required) until `authenticate` has been called with that methodId.

Used to exercise both branches of the `--tck-auth-method` flow: without it, session-dependent
tests must SKIP with a hint (not FAIL) and the overall verdict must be NOT CONFORMANT
(`Verdict.blocked_by_auth`); with `--tck-auth-method tck`, everything behaves like a normal
conforming agent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"id": "tck", "name": "TCK", "description": None},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-gated-by-auth",
        auth_methods=AUTH_METHODS,
        require_auth=True,
    ).run()


if __name__ == "__main__":
    main()
