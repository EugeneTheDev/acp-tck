#!/usr/bin/env python3
"""Non-conforming fixture: `session/list` returns a JSON-RPC error instead of `{"sessions": []}`
whenever the (possibly `cwd`-filtered) result set would be empty -- v2's L1 rule that an empty
result MUST be a normal, empty array, never an error.

FAILs exactly `ACP-LIST-202` (the only test that filters to a guaranteed-empty result).
`ACP-LIST-201`/`203`/`204` all list with at least one session present in the result, so they
never hit the empty branch and PASS unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ListErrorsWhenEmptyAgent(ConformingAgent):
    def _handle_list_sessions(self, msg_id: Any, params: dict[str, Any]) -> None:
        cwd_filter = params.get("cwd")
        sessions = [
            {"sessionId": session_id, "cwd": cwd}
            for session_id, cwd in self._sessions.items()
            if cwd_filter is None or cwd == cwd_filter
        ]
        if not sessions:
            self._error(msg_id, -32603, "Internal error: no sessions to list")
            return
        self._reply(msg_id, {"sessions": sessions})


def main() -> None:
    ListErrorsWhenEmptyAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
