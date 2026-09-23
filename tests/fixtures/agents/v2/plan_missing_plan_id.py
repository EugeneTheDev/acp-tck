#!/usr/bin/env python3
"""Non-conforming fixture: sends a `plan_update` whose `plan` object has no `planId` at all.

FAILs `ACP-PATCH-205` (every `plan_update.plan` must carry a non-empty `planId`). Also cascades
into `ACP-SCHEMA-001`: `PlanItems` requires `planId` (`schema/v2/schema.json` `$defs/PlanItems`,
`required: ["planId", "entries"]`) -- same cascade pattern as `missing_message_id.py`.

`_send_rich_turn_updates` is overridden outright, so `ACP-PATCH-204`/`208` SKIP "no <variant>
observed", but `ACP-ENUM-201` still PASSes via the plan entry's correctly-shaped
`priority`/`status`.

`_base.ConformingAgent._reply_to_prompt` calls `_send_rich_turn_updates` on every turn, so this
malformed `plan_update` is emitted on every `run_prompt` call any other test makes against this
fixture too -- `ACP-PROMPT-205` (CAPABILITY, affects the verdict) then also FAILs whenever this
fixture is run unscoped (see `tests/v2/test_cli.py`'s corresponding self-test, `-k` widened to
catch this).
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
