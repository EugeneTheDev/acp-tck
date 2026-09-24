#!/usr/bin/env python3
"""Conforming fixture: pushes an unprompted `_fixture/status_update` notification right after
answering `initialize`, and again right after receiving any notification. Otherwise identical to
`ConformingAgent`.

Models a real agent that reports connection-level status as soon as it is initialized. Such a
push is a notification, not a reply, so it must not fail `ACP-JSONRPC-003` (a notification gets
no response) when it lands in that check's quiet period.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class PushesStatusNotificationsAgent(ConformingAgent):
    def _push_status(self) -> None:
        self._notify("_fixture/status_update", {"status": "ready"})

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        super()._handle_request(method, msg_id, params)
        if method == "initialize":
            self._push_status()

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        self._push_status()
        super()._handle_notification(method, params)


def main() -> None:
    PushesStatusNotificationsAgent().run()


if __name__ == "__main__":
    main()
