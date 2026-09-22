#!/usr/bin/env python3
"""Non-conforming fixture: fires one agent -> client *notification* (no `id`) using a made-up,
non-`_`-prefixed method name mid-turn, then finishes the turn normally.

Self-test for `run_prompt`'s driver recording agent -> client *notifications* (not just
id-bearing requests) on `PromptTurn.client_requests_seen`: `ACP-CLIENTCAP-202`'s own text claims
"request/notification" coverage, so a notification using an undefined method name must not
silently escape the check; this fixture is the one place that actually exercises that code path.

FAILs exactly `ACP-CLIENTCAP-202` (undefined agent -> client method observed). Every other
requirement is unaffected -- the turn otherwise finishes normally.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class SendsUndefinedClientNotificationAgent(ConformingAgent):
    def _mid_turn_action(self, session_id: Any) -> bool:
        self._write(
            {
                "jsonrpc": "2.0",
                "method": "made_up/notify",
                "params": {"sessionId": session_id},
            }
        )
        return False  # fire-and-forget: finish the turn immediately, in the same call


def main() -> None:
    SendsUndefinedClientNotificationAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
