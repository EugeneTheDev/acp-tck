#!/usr/bin/env python3
"""Non-conforming fixture: advertises `sessionCapabilities.resume` but replays stored
`session/update` history BEFORE responding to `session/resume`, which `session/resume` MUST
NOT do (`.agents/research/acp-v1-session-capabilities.md` R2 -- unlike `session/load`,
resume must not replay history-kind updates before its response). ACP-RESUME-001 still
PASSes (the response is a valid, schema-conformant `{}`); only ACP-RESUME-002 fails.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CAPABILITIES = {"sessionCapabilities": {"resume": {}}}


class ResumeReplaysHistoryAgent(ConformingAgent):
    def _handle_resume(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        session = self._sessions.get(session_id)
        if session is None:
            session = {"cwd": params.get("cwd"), "history": []}
            self._sessions[session_id] = session
        # Deliberately violates R2: replay history before responding.
        for update_params in session["history"]:
            self._notify("session/update", update_params)
        self._reply(msg_id, {})


def main() -> None:
    ResumeReplaysHistoryAgent(
        capabilities=CAPABILITIES, agent_name="tck-fixture-resume-replays-history"
    ).run()


if __name__ == "__main__":
    main()
