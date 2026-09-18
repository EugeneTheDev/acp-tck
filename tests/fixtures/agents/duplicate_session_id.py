#!/usr/bin/env python3
"""Non-conforming fixture: `session/new` always returns the same `sessionId`
(`"sess-0001"`) regardless of how many sessions have been created. Violates ACP-SESSION-002
(Req 9 "unique").
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class DuplicateSessionIdAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "session/new":
            self._reply(msg_id, {"sessionId": "sess-0001"})
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    DuplicateSessionIdAgent().run()


if __name__ == "__main__":
    main()
