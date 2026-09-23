#!/usr/bin/env python3
"""Non-conforming fixture: every `session/update` notification carries `sessionId: "other"`
instead of the session the prompt was actually sent for.

`run_prompt`'s turn-end predicate only recognizes an idle `state_update` as the terminator when
its enclosing `sessionId == session_id`, so with every update misattributed to `"other"`,
`run_prompt` never observes a matching `running`/idle and blocks until it times out
(`AgentTimeout`). Every test driving a turn through `run_prompt` FAILs the same way, since none
get far enough to inspect `turn.updates` -- indistinguishable from an agent that never responds
to the prompted session at all.
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
