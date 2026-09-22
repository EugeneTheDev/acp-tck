#!/usr/bin/env python3
"""A defect fixture for ACP-AUTH-203 (CAPABILITY, `inferred:authMethods`): otherwise conforming,
advertises a `type: "agent"` auth method and implements `auth/login` normally, but `auth/logout`
always errors. No v1 analogue (v1's logout test had no `--allow-logout` opt-in gate at all).

Must FAIL ACP-AUTH-203 only when run with `--allow-logout` (the flag that actually exercises
`auth/logout`); without it, ACP-AUTH-203 SKIPs like it does for any other agent, since the TCK
never calls the destructive method at all.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"methodId": "tck", "type": "agent", "name": "TCK"},
]


class LogoutErrorsAgent(ConformingAgent):
    def _handle_logout(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._error(msg_id, -32603, "Internal error: logout always fails")


def main() -> None:
    LogoutErrorsAgent(
        agent_name="tck-fixture-advertises-auth-but-logout-errors",
        auth_methods=AUTH_METHODS,
    ).run()


if __name__ == "__main__":
    main()
