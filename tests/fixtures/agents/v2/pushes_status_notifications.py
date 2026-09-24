#!/usr/bin/env python3
"""Conforming fixture: pushes an unsolicited `_fixture/status_update` notification right after
receiving any notification (single or inside a batch). Otherwise identical to `ConformingAgent`.

The push is a notification, not a reply, so it lands in the quiet period of every "a
notification gets no response" check (`ACP-JSONRPC-003`, `ACP-BATCH-202`, `ACP-EXT-201`) without
violating any of them. It is deliberately not also sent right after `initialize`: the batch
reply checks (`ACP-BATCH-203`/`204`) read the first line after their batch as its reply, so an
early push would fail them for an unrelated reason.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class PushesStatusNotificationsAgent(ConformingAgent):
    def _push_status(self) -> None:
        self._notify("_fixture/status_update", {"status": "ready"})

    def _handle(self, message: dict[str, Any]) -> None:
        is_notification = "method" in message and "id" not in message
        if is_notification:
            self._push_status()
        super()._handle(message)


def main() -> None:
    PushesStatusNotificationsAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
