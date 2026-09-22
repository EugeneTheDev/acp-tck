#!/usr/bin/env python3
"""An agent that requires authentication before `session/new` will succeed: advertises one
`type: "agent"` auth method (`methodId: "tck"`) and answers `session/new` with `-32000`
(authentication required) until `auth/login` has been called with that `methodId`. v2 port of
`tests/fixtures/agents/v1/gated_by_auth.py` (method renamed `authenticate` -> `auth/login`,
`AuthMethod` field renamed `id` -> `methodId`, `type` now required).

Used to exercise both branches of the `--tck-auth-method` flow: without it, session-dependent
tests must SKIP with the `AUTH-GATED:` marker (not FAIL) and the overall verdict must be NOT
CONFORMANT (`Verdict.blocked_by_auth`); with `--tck-auth-method tck`, everything behaves like a
normal conforming agent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"methodId": "tck", "type": "agent", "name": "TCK"},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-gated-by-auth-v2",
        auth_methods=AUTH_METHODS,
        require_auth=True,
    ).run()


if __name__ == "__main__":
    main()
