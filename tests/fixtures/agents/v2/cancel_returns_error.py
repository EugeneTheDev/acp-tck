#!/usr/bin/env python3
"""Non-conforming fixture: withholds the `session/prompt` acceptance receipt entirely (no
`user_message`/`running` update either) until `session/cancel` arrives, then answers the
*original* `session/prompt` request with a JSON-RPC error instead of ever sending a terminating
idle `state_update`.

FAILs `ACP-CANCEL-203` (cancellation surfaced as a generic JSON-RPC failure) and `ACP-CANCEL-208`
(a `session/close` sent instead of `session/cancel` cannot rescue the pending prompt either --
`_handle_prompt` never registers the session in `_hanging_sessions`, so the inherited
`_handle_close_session` has nothing to resolve, and the original `session/prompt` request is
simply never answered at all -- `run_prompt` itself times out). `ACP-CANCEL-201`/`202`/`206`/`207`
SKIP, deferring to `ACP-CANCEL-203` -- the turn never reaches a terminating idle at all, so they
have nothing of their own to check.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CancelReturnsErrorAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pending_prompt: dict[str, Any] | None = None

    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._pending_prompt = {"msg_id": msg_id, "session_id": params.get("sessionId")}

    def _handle_cancel(self, params: dict[str, Any]) -> None:
        pending = self._pending_prompt
        if pending is not None and pending["session_id"] == params.get("sessionId"):
            self._pending_prompt = None
            self._error(pending["msg_id"], -32603, "cancelled")
            return
        super()._handle_cancel(params)


def main() -> None:
    CancelReturnsErrorAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
