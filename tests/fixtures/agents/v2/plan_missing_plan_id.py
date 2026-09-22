#!/usr/bin/env python3
"""Non-conforming fixture: sends a `plan_update` whose `plan` object has no `planId` at all.

FAILs `ACP-PATCH-205` (every `plan_update.plan` must carry a non-empty `planId`). Also cascades
into `ACP-SCHEMA-001`: `PlanItems` requires `planId` (`schema/v2/schema.json` `$defs/PlanItems`,
`required: ["planId", "entries"]`) -- same documented cascade pattern as
`missing_message_id.py`. `_send_rich_turn_updates` is overridden outright, so no message chunk
or tool-call update is emitted here beyond the base turn's own correctly-shaped
`user_message`/closing `agent_message_chunk` -- `ACP-PATCH-201` still has evidence and no
violation; `ACP-PATCH-204`/`208` SKIP "no <variant> observed"; `ACP-ENUM-201` still has evidence
via `priority`/`status` on the plan entry (both correctly shaped), so it still PASSes even
though the surrounding `plan` object is missing its id.

NOT unaffected otherwise, contrary to an earlier version of this docstring (review-v2-slices-
1b-6 finding 16): `_base.ConformingAgent._reply_to_prompt` calls `_send_rich_turn_updates` on
*every* turn a driven prompt observes, so this malformed `plan_update` is emitted on every
`run_prompt` call any other test in the suite makes against this fixture too -- and
`ACP-PROMPT-205` (CAPABILITY, affects the verdict) schema-validates every `session/update` it
sees, so it also FAILs whenever this fixture is run unscoped (confirmed; see
`tests/v2/test_cli.py`'s corresponding self-test, whose `-k` scope is widened to catch this).
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
