#!/usr/bin/env python3
"""Non-conforming fixture: the `user_message` update echoing the inserted prompt carries a
different `messageId` than the one the `session/prompt` response actually returned.

FAILs exactly `ACP-PROMPT-203` (the echoed `messageId` must match the response's). `ACP-PROMPT-
201` (response shape) is unaffected -- the response itself is still well-formed. `ACP-STATE-201/
202/203` and `ACP-PROMPT-002` are unaffected: `running`/idle/schema/sessionId are all otherwise
normal.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class EchoWrongMessageIdAgent(ConformingAgent):
    def _send_user_message_update(self, session_id: Any, message_id: str, prompt: Any) -> None:
        self._send_update(
            session_id,
            {
                "sessionUpdate": "user_message",
                "messageId": "wrong-" + message_id,
                "content": prompt,
            },
        )


def main() -> None:
    EchoWrongMessageIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
