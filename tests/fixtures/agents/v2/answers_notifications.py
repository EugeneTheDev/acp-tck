#!/usr/bin/env python3
"""Non-conforming fixture: replies to the `session/cancel` notification with a bogus response
(`{"id": null, "result": null}`). Violates ACP-JSONRPC-003 -- notifications never receive a
response. Mirrors v1's `answers_notifications.py` on top of v2's `_base.py` (D6).

v2's `_base.py` has no generic `_handle_notification` hook like v1's -- `session/cancel` is the
only notification method `ConformingAgent._handle` recognizes at all, dispatched straight to
`_handle_cancel` -- so this overrides that method instead, unconditionally, regardless of
whether a hanging `__hang__` prompt is actually outstanding for the session (deliberately never
calling `super()._handle_cancel(...)`, so no prompt is ever legitimately cancelled either).
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
