#!/usr/bin/env python3
"""Non-conforming fixture: replies to `session/prompt`, sends `state_update {state: "running"}`
and a content chunk, then goes silent forever -- no turn-ending idle ever arrives.

Large, honest, documented cascade: every V2-2a test that calls `run_prompt` (`ACP-PROMPT-201`,
`ACP-PROMPT-203`, `ACP-STATE-201`, `ACP-STATE-202`, `ACP-STATE-203`, `ACP-PROMPT-002`, and the
prompt-turn extension of `ACP-SCHEMA-001`) independently hits `AgentTimeout` waiting for the
idle that never comes, and each is recorded as its own `FAIL` -- `run_prompt`'s turn-end
predicate has no other way to end a turn short of a JSON-RPC error, which this fixture also
never sends. Each affected test's own `--timeout` bounds how long it waits, so the fixture never
actually hangs the suite; see `tests/v2/test_cli.py` for the observed wall-clock time.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class NoIdleAfterRunningAgent(ConformingAgent):
    def _send_idle_update(self, session_id: Any, stop_reason: str | None) -> None:
        pass  # deliberately omitted: the turn never ends


def main() -> None:
    NoIdleAfterRunningAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
