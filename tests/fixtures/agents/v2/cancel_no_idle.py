#!/usr/bin/env python3
"""Non-conforming fixture: hangs on every prompt (not just `__hang__`), and `session/cancel`
itself is silently ignored -- no terminating idle, no error, ever. `session/close` is
unaffected (inherits `ConformingAgent`'s own default `_handle_close_session`, which still
resolves a hanging session via `_finish_turn(..., "cancelled")`), so this fixture isolates
`session/cancel`'s own defect from `ACP-CANCEL-208`'s close-triggered path.

FAILs `ACP-CANCEL-201`/`202`/`203`/`205`/`206`/`207` (each times out inside `run_prompt`, since
the turn never reaches a terminating idle within `--tck-timeout`) and the ADVISORY
`ACP-CANCEL-204`/INFORMATIONAL `ACP-INFO-CANCEL-202` for the same reason (an uncaught
`AgentTimeout` is a `FAIL`, not a `SKIP` -- see `AGENTS.md` "Statuses"). `ACP-CANCEL-208` and
`ACP-INFO-CANCEL-201` are unaffected: neither one ever calls `session/cancel` on a session this
fixture is holding hostage.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CancelNoIdleAgent(ConformingAgent):
    @staticmethod
    def _is_hang_prompt(prompt: list[Any]) -> bool:
        return True  # hang on every prompt, not just the `__hang__` sentinel

    def _handle_cancel(self, params: dict[str, Any]) -> None:
        pass  # deliberately ignore session/cancel entirely -- no resolution, ever


def main() -> None:
    CancelNoIdleAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
