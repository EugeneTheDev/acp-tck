#!/usr/bin/env python3
"""Non-conforming fixture: advertises `loadSession` but responds to `session/load` BEFORE
replaying the stored `session/update` history, instead of after. Violates ACP-LOAD-002
(`.agents/research/acp-v1-session-capabilities.md` L2/L3: replay MUST happen before the
response). ACP-LOAD-001 still PASSes (the response itself is a valid, schema-conformant
`{}`) -- only the ordering requirement is violated.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CAPABILITIES = {"loadSession": True}


class LoadReplaysAfterResponseAgent(ConformingAgent):
    def _handle_load(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        session = self._sessions.get(session_id)
        if session is None:
            session = {"cwd": params.get("cwd"), "history": []}
            self._sessions[session_id] = session
        # Deliberately backwards: respond first, replay after.
        self._reply(msg_id, {})
        for update_params in session["history"]:
            self._notify("session/update", update_params)


def main() -> None:
    LoadReplaysAfterResponseAgent(
        capabilities=CAPABILITIES, agent_name="tck-fixture-load-replays-after-response"
    ).run()


if __name__ == "__main__":
    main()
