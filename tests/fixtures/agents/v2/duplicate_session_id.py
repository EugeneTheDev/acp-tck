#!/usr/bin/env python3
"""Non-conforming fixture: `session/new` always returns the same `sessionId`, regardless of how
many times it is called on one connection. Mirrors
`tests/fixtures/agents/v1/duplicate_session_id.py`.

FAILs exactly `ACP-SESSION-002`. `ACP-SESSION-001` (single-call shape: non-empty string
`sessionId`, schema-valid response) is unaffected -- one call in isolation still looks perfectly
conforming.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class DuplicateSessionIdAgent(ConformingAgent):
    def _handle_new_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._sessions["sess-0001"] = params.get("cwd", "")
        self._reply(msg_id, {"sessionId": "sess-0001"})


def main() -> None:
    DuplicateSessionIdAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
