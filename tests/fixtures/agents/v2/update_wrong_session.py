#!/usr/bin/env python3
"""Non-conforming fixture: every `session/update` notification carries `sessionId: "other"`
instead of the session the prompt was actually sent for.

Large, honest, documented cascade -- `run_prompt`'s turn-end predicate only recognizes an idle
`state_update` as the terminator when its enclosing `sessionId == session_id`, so with every
update misattributed to `"other"`, `run_prompt` itself never observes a matching `running` or a
matching terminating idle and blocks until its own `timeout` elapses, then raises
`AgentTimeout`. Every test that drives its own turn through `run_prompt` and inspects the
returned `PromptTurn` (`ACP-PROMPT-201`, `ACP-PROMPT-203`, `ACP-STATE-201`, `ACP-STATE-202`,
`ACP-STATE-203`, `ACP-PROMPT-205`) independently FAILs via that same `AgentTimeout` -- none of
them get far enough to inspect `turn.updates` at all.
This is the intended, honest outcome of misattributing every update's `sessionId`: it is
indistinguishable, from the mock client's point of view, from an agent that never responds to
the prompted session at all.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class UpdateWrongSessionAgent(ConformingAgent):
    def _send_update(self, session_id: Any, update: dict[str, Any]) -> None:
        super()._send_update("other", update)


def main() -> None:
    UpdateWrongSessionAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
