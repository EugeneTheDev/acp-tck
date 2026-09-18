#!/usr/bin/env python3
"""Non-conforming fixture: replies to the `session/cancel` notification with a bogus response
(`{"id": null, "result": null}`). Violates J2 / ACP-JSONRPC-003 -- notifications never receive
a response.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class AnswersNotificationsAgent(ConformingAgent):
    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel":
            self._write({"jsonrpc": "2.0", "id": None, "result": None})
            return
        super()._handle_notification(method, params)


def main() -> None:
    AnswersNotificationsAgent().run()


if __name__ == "__main__":
    main()
