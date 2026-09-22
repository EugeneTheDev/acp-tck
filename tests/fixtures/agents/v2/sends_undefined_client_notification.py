#!/usr/bin/env python3
"""Non-conforming fixture: fires one agent -> client *notification* (no `id`) using a made-up,
non-`_`-prefixed method name mid-turn, then finishes the turn normally.

Self-test for review-v2-slices-1b-6 finding 6: `run_prompt`'s driver used to only record
agent -> client *requests* (id-bearing messages) on `PromptTurn.client_requests_seen`, even
though `ACP-CLIENTCAP-202`'s own text claims "request/notification" coverage -- a notification
using an undefined method name would silently escape the check. `_helpers.py` was widened to also
record any agent -> client notification other than `session/update`; this fixture is the one
place that actually exercises the new code path.

FAILs exactly `ACP-CLIENTCAP-202` (undefined agent -> client method observed). Every other
V2-2b/V2-2a id is unaffected -- the turn otherwise finishes normally.
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
