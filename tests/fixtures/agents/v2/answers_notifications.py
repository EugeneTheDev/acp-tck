#!/usr/bin/env python3
"""Non-conforming fixture: replies to the `session/cancel` notification with a bogus response
(`{"id": null, "result": null}`). Violates ACP-JSONRPC-003 -- notifications never receive a
response. Mirrors v1's `answers_notifications.py` on top of v2's `_base.py`.

v2's `_base.py` has no generic `_handle_notification` hook -- `session/cancel` is the only
notification `ConformingAgent._handle` recognizes, dispatched to `_handle_cancel` -- so this
overrides that method unconditionally, never calling `super()._handle_cancel(...)`, so no
prompt is ever legitimately cancelled either.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class AnswersNotificationsAgent(ConformingAgent):
    def _handle_cancel(self, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "id": None, "result": None})


def main() -> None:
    AnswersNotificationsAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
