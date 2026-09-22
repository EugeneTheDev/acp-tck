#!/usr/bin/env python3
"""Non-conforming fixture: sends a `plan_update` whose `plan` object has no `planId` at all.

FAILs `ACP-PATCH-205` (every `plan_update.plan` must carry a non-empty `planId`). Also cascades
into `ACP-SCHEMA-001`: `PlanItems` requires `planId` (`schema/v2/schema.json` `$defs/PlanItems`,
`required: ["planId", "entries"]`) -- same documented cascade pattern as
`missing_message_id.py`. Everything else about the turn is unaffected: `_send_rich_turn_updates`
is overridden outright, so no message chunk or tool-call update is emitted here beyond the base
turn's own correctly-shaped `user_message`/closing `agent_message_chunk` -- `ACP-PATCH-201`
still has evidence and no violation; `ACP-PATCH-204`/`208` SKIP "no <variant> observed";
`ACP-ENUM-201` still has evidence via `priority`/`status` on the plan entry (both correctly
shaped), so it still PASSes even though the surrounding `plan` object is missing its id.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class PlanMissingPlanIdAgent(ConformingAgent):
    def _send_rich_turn_updates(self, session_id: Any) -> None:
        self._send_update(
            session_id,
            {
                "sessionUpdate": "plan_update",
                "plan": {
                    "type": "items",
                    "entries": [
                        {"content": "Check the file", "priority": "medium", "status": "completed"}
                    ],
                },
            },
        )


def main() -> None:
    PlanMissingPlanIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
