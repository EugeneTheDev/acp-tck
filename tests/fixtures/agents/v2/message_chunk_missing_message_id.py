#!/usr/bin/env python3
"""Non-conforming fixture: sends an `agent_message_chunk` update with no `messageId` at all.

FAILs `ACP-PATCH-201` (every message-kind update must carry a non-empty string `messageId`) --
the base turn's own `user_message`/closing `agent_message_chunk` are still correctly shaped, but
`ACP-PATCH-201` checks *every* message-kind update observed, so this one extra, malformed chunk
is enough to FAIL it on its own. Also cascades into `ACP-SCHEMA-001`: `ContentChunk` requires
`messageId` (`schema/v2/schema.json` `$defs/ContentChunk`, `required: ["messageId",
"content"]`) -- same documented cascade pattern as `missing_message_id.py`. No tool-call/plan
update is ever sent here, so `ACP-PATCH-204/205/208` and `ACP-ENUM-201` all SKIP "no <variant>
observed".
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class MessageChunkMissingMessageIdAgent(ConformingAgent):
    def _send_rich_turn_updates(self, session_id: Any) -> None:
        self._send_update(
            session_id,
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "oops"}},
        )


def main() -> None:
    MessageChunkMissingMessageIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
