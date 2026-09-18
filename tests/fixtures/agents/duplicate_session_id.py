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
            # Still register the session (just under the same, reused id) so everything *other*
            # than the uniqueness violation this fixture exists to demonstrate keeps working --
            # e.g. `_base.py`'s `_handle_prompt` now rejects an unrecognized `sessionId` (review-
            # slices-5-6.md S9), which would otherwise turn this into an unintended
            # ACP-PROMPT-001/META-001 FAIL too.
            self._sessions["sess-0001"] = {"cwd": params.get("cwd"), "history": []}
            self._reply(msg_id, {"sessionId": "sess-0001"})
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    DuplicateSessionIdAgent().run()


if __name__ == "__main__":
    main()
