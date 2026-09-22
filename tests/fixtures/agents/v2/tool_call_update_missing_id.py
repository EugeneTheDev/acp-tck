#!/usr/bin/env python3
"""Non-conforming fixture: sends a `tool_call_update` with no `toolCallId` at all.

FAILs `ACP-PATCH-204` (every `tool_call_update`/`tool_call_content_chunk` must carry a non-empty
`toolCallId`). Also cascades into `ACP-SCHEMA-001`: `ToolCallUpdate` requires `toolCallId`
(`schema/v2/schema.json` `$defs/ToolCallUpdate`, `required: ["toolCallId"]`) -- same documented
cascade pattern as `missing_message_id.py`. `_send_rich_turn_updates` is overridden outright
(not `emit_rich_turn_updates=True` on the base class) so no plan update or extra message chunk
is emitted here -- `ACP-PATCH-201/203/205/208/209` and `ACP-ENUM-201/202` all SKIP "no <variant>
observed" for this fixture rather than FAILing or PASSing on borrowed evidence; the base turn's
own `user_message`/closing `agent_message_chunk` (both carrying a real `messageId`) are
unaffected, so `ACP-PATCH-201` still has *some* evidence -- but no violation, since those two
are correctly shaped.

NOT unaffected, contrary to an earlier version of this docstring (review-v2-slices-1b-6 finding
16): `_base.ConformingAgent._reply_to_prompt` calls `_send_rich_turn_updates` on *every* turn a
driven prompt observes, so this malformed `tool_call_update` is emitted on every `run_prompt`
call any other test in the suite makes against this fixture too -- and `ACP-PROMPT-205`
(CAPABILITY, affects the verdict) schema-validates every `session/update` it sees, so it also
FAILs whenever this fixture is run unscoped (confirmed; see `tests/v2/test_cli.py`'s
corresponding self-test, whose `-k` scope is widened to catch this)."""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ToolCallUpdateMissingIdAgent(ConformingAgent):
    def _send_rich_turn_updates(self, session_id: Any) -> None:
        self._send_update(
            session_id,
            {
                "sessionUpdate": "tool_call_update",
                "title": "Reading a file",
                "kind": "read",
                "status": "in_progress",
            },
        )


def main() -> None:
    ToolCallUpdateMissingIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
