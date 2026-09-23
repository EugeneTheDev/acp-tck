#!/usr/bin/env python3
"""Non-conforming fixture: sends an `agent_message_chunk` update with no `messageId` at all.

FAILs `ACP-PATCH-201` (every message-kind update must carry a non-empty string `messageId`).
Also cascades into `ACP-SCHEMA-001`: `ContentChunk` requires `messageId` (`schema/v2/schema.json`
`$defs/ContentChunk`, `required: ["messageId", "content"]`). No tool-call/plan update is ever
sent, so `ACP-PATCH-204/205/208` and `ACP-ENUM-201` SKIP "no <variant> observed".

Since `_send_rich_turn_updates` runs on every turn, this also cascades into `ACP-PROMPT-205`
(CAPABILITY, affects the verdict) whenever this fixture is run unscoped -- see the widened `-k`
scope on its self-test in `tests/v2/test_cli.py`.
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
