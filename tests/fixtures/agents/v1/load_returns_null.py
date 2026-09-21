#!/usr/bin/env python3
"""Non-conforming (ADVISORY-only) fixture: advertises `loadSession`, replays history correctly
(so ACP-LOAD-001/002 PASS -- the schema layer accepts a literal JSON `null` result for an
all-optional object response, per `.agents/research/acp-v1-session-capabilities.md` L4's
leniency note), but responds to `session/load` with `null` instead of `{}`. This should FAIL
only the ADVISORY ACP-LOAD-003 check, which is stricter than schema validation.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CAPABILITIES = {"loadSession": True}


class LoadReturnsNullAgent(ConformingAgent):
    def _handle_load(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        session = self._sessions.get(session_id)
        if session is None:
            session = {"cwd": params.get("cwd"), "history": []}
            self._sessions[session_id] = session
        for update_params in session["history"]:
            self._notify("session/update", update_params)
        self._reply(msg_id, None)


def main() -> None:
    LoadReturnsNullAgent(capabilities=CAPABILITIES, agent_name="tck-fixture-load-returns-null").run()


if __name__ == "__main__":
    main()
