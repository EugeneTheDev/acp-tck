#!/usr/bin/env python3
"""Non-conforming fixture: like `pushes_status_notifications.py`, but answers a batch with one
line per response object instead of one reply array, with a status notification pushed between
them.

Proves skipping the agent's own notifications does not change how a batch reply's shape is
judged: FAILs exactly the `ACP-BATCH-204`/`205` test (one reply array expected), which also
carries `ACP-JSONRPC-001`. `ACP-BATCH-203` still PASSes, since it counts response objects across
lines.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from pushes_status_notifications import PushesStatusNotificationsAgent  # noqa: E402


class PushesStatusAndSplitsBatchRepliesAgent(PushesStatusNotificationsAgent):
    def _write_line(self, obj: dict[str, Any] | list[Any]) -> None:
        is_reply_array = isinstance(obj, list) and any(
            not isinstance(item, dict) or "method" not in item for item in obj
        )
        if not is_reply_array:
            super()._write_line(obj)
            return
        for index, item in enumerate(obj):
            if index:
                self._push_status()
            super()._write_line(item)


def main() -> None:
    PushesStatusAndSplitsBatchRepliesAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
