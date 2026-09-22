#!/usr/bin/env python3
"""Non-conforming fixture: `session/resume` with `replayFrom: {"type": "start"}` replays history
correctly (before responding), but strips `messageId` from every replayed update -- so a
replayed `user_message` can never be matched back to the original prompt turn it came from.

FAILs exactly `ACP-RESUME-204`. `ACP-RESUME-201`/`202`/`203` (resume itself, replay-before-
response ordering, and the no-`replayFrom` no-replay rule) are unaffected -- none of them inspect
`messageId`. `ACP-RESUME-205` is vacuous here regardless (this fixture, like `ConformingAgent`,
never emits a `*_chunk` update).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ResumeReplayMissingMessageIdAgent(ConformingAgent):
    def _handle_resume_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            self._sessions[session_id] = params.get("cwd", "")
        replay_from = params.get("replayFrom")
        if isinstance(replay_from, dict) and replay_from.get("type") == "start":
            for update in self._history.get(session_id, []):
                mangled = dict(update)
                mangled.pop("messageId", None)
                self._notify("session/update", {"sessionId": session_id, "update": mangled})
        result: dict[str, Any] = {}
        if self._config_options:
            result["configOptions"] = self._current_config_options()
        self._reply(msg_id, result)


def main() -> None:
    ResumeReplayMissingMessageIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
