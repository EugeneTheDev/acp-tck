#!/usr/bin/env python3
"""Non-conforming fixture: like `pushes_status_notifications.py`, but after pushing its status
notification it also replies to every notification it receives with a bogus response
(`{"id": null, "result": null}`) -- folded into the reply array when the notification arrived
inside a batch.

Proves a leading agent notification does not hide a later reply: FAILs exactly
`ACP-JSONRPC-003`, `ACP-BATCH-202` and `ACP-EXT-201`.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from pushes_status_notifications import PushesStatusNotificationsAgent  # noqa: E402


class PushesStatusAndAnswersNotificationsAgent(PushesStatusNotificationsAgent):
    def _handle(self, message: dict[str, Any]) -> None:
        super()._handle(message)
        if "method" in message and "id" not in message:
            self._write({"jsonrpc": "2.0", "id": None, "result": None})


def main() -> None:
    PushesStatusAndAnswersNotificationsAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
