#!/usr/bin/env python3
"""Conforming fixture: sends an unsolicited "session-ready" `state_update {state: "idle"}` (no
`stopReason`) for a session right after answering `session/new`, *before* any `session/prompt`
is ever issued for it -- the legal initial-ready-idle pattern
(`.agents/research/acp-v2-prompt-lifecycle.md` §4 point 2, observed live in the Python SDK's own
v2 reference agent). Every subsequent `session/prompt` turn on that session behaves exactly like
`ConformingAgent`'s baseline.

Must PASS every V2-2a requirement: `run_prompt` never drains `agent.pending()` before sending
`session/prompt`, so this pre-prompt idle is either consumed by the test's own `new_session()`
read (and left unread in `agent.pending()`, never seen by `run_prompt` at all) or -- if it
arrives after that read -- picked up as the first line `run_prompt` itself reads, where it fails
the turn-end predicate (`running_seen` is `False` and it carries no `stopReason`) and is simply
recorded as an ordinary update, never mistaken for *this* turn's terminator.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class IdleBeforeRunningAgent(ConformingAgent):
    def _handle_new_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        super()._handle_new_session(msg_id, params)
        session_id = f"sess-{self._session_count:04d}"
        self._send_update(session_id, {"sessionUpdate": "state_update", "state": "idle"})


def main() -> None:
    IdleBeforeRunningAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
