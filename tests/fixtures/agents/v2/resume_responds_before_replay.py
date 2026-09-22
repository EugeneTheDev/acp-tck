#!/usr/bin/env python3
"""Non-conforming fixture: `session/resume` with `replayFrom: {"type": "start"}` replies to the
`session/resume` request *before* replaying the session's retained history, instead of after --
the reverse of R2's required ordering.

FAILs exactly `ACP-RESUME-202` (the replay-before-response ordering check). `ACP-RESUME-201`
(resume itself succeeds) is unaffected. `ACP-RESUME-203` (no `replayFrom` -> no replay) is also
unaffected -- this fixture only reorders the `{"type": "start"}` case. `ACP-RESUME-204` (the
replayed message's `messageId` matches) legitimately SKIPs rather than FAILs here: the helper's
single-response-tracking read loop (`_helpers.resume_session`) returns as soon as it sees the
response, before ever reading the trailing replay notifications that are still queued in the
pipe -- so `updates` comes back empty and ACP-RESUME-204 correctly reports "the retained user
message was not replayed at all" (from its own perspective) rather than fabricating a false
FAIL/PASS from data it never actually observed.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ResumeRespondsBeforeReplayAgent(ConformingAgent):
    def _handle_resume_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            self._sessions[session_id] = params.get("cwd", "")
        result: dict[str, Any] = {}
        if self._config_options:
            result["configOptions"] = self._current_config_options()
        self._reply(msg_id, result)
        replay_from = params.get("replayFrom")
        if isinstance(replay_from, dict) and replay_from.get("type") == "start":
            for update in self._history.get(session_id, []):
                self._notify("session/update", {"sessionId": session_id, "update": update})


def main() -> None:
    ResumeRespondsBeforeReplayAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
