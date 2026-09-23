#!/usr/bin/env python3
"""Non-conforming fixture: the `session/prompt` response is `{}` -- no `messageId` at all.

FAILs `ACP-PROMPT-201` (the response must be an object with a non-empty string `messageId`) and
`ACP-SCHEMA-001`'s prompt-turn extension (`NewPromptResponse` requires `messageId`).
`ACP-PROMPT-203` SKIPs rather than cascading: its test guards on `turn.message_id` being a valid
non-empty string before asserting the echo, so it doesn't produce a less precise diagnostic than
`ACP-PROMPT-201`'s own. `ACP-STATE-201/202/203` and the sessionId portion of `ACP-PROMPT-205` are
unaffected.
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
