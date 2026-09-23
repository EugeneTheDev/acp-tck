#!/usr/bin/env python3
"""Non-conforming fixture: `session/resume` replays the session's full retained history
unconditionally, even when `replayFrom` is omitted/`null` (which MUST NOT replay history before
responding).

FAILs exactly `ACP-RESUME-203`. `ACP-RESUME-201` (the resume itself still succeeds) and
`ACP-RESUME-202`/`204`/`205` (the replay-`{"type": "start"}` scenarios, which this fixture
answers identically to `ConformingAgent` since it always replays regardless of `replayFrom`) are
unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ResumeReplaysWhenNotAskedAgent(ConformingAgent):
    def _handle_resume_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            self._sessions[session_id] = params.get("cwd", "")
        for update in self._history.get(session_id, []):
            self._notify("session/update", {"sessionId": session_id, "update": update})
        self._reply(msg_id, {})


def main() -> None:
    ResumeReplaysWhenNotAskedAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
