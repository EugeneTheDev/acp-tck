#!/usr/bin/env python3
"""Non-conforming fixture: like `pushes_status_notifications.py`, but after pushing its status
notification it also replies to every notification it receives with a bogus response
(`{"id": null, "result": null}`).

Proves a leading agent notification does not hide a later reply: FAILs `ACP-JSONRPC-003`.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from pushes_status_notifications import PushesStatusNotificationsAgent  # noqa: E402


class PushesStatusAndAnswersNotificationsAgent(PushesStatusNotificationsAgent):
    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        super()._handle_notification(method, params)
        self._write({"jsonrpc": "2.0", "id": None, "result": None})


def main() -> None:
    PushesStatusAndAnswersNotificationsAgent().run()


if __name__ == "__main__":
    main()
