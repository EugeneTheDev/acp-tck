#!/usr/bin/env python3
"""Non-conforming fixture: the `session/prompt` response is `{}` -- no `messageId` at all --
even though the agent still uses a real internal message id for its own `user_message` update.

FAILs `ACP-PROMPT-201` (the response must be an object with a non-empty string `messageId`) and
`ACP-SCHEMA-001`'s prompt-turn extension (the response fails `NewPromptResponse`'s required
`messageId`). `ACP-PROMPT-203` SKIPs rather than FAILing or cascading: its own test guards on
`turn.message_id` actually being a valid non-empty string before asserting the echo, since a
response with no `messageId` gives the driver nothing to check the echo *against* -- asserting
against `None` here would be a different, less precise diagnostic than `ACP-PROMPT-201`'s own.
`ACP-STATE-201/202/203` and the sessionId portion of `ACP-PROMPT-205` are unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class MissingMessageIdAgent(ConformingAgent):
    def _reply_to_prompt(self, msg_id: Any, message_id: str) -> None:
        self._reply(msg_id, {})


def main() -> None:
    MissingMessageIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
