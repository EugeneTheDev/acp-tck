#!/usr/bin/env python3
"""Conforming fixture: pushes an unsolicited `_fixture/status_update` notification right after
answering `initialize`, and from then on right before handling every inbound message (so ahead
of every reply, and in the quiet period after every notification). Ahead of a batch's reply
array it also pushes a batch of its own made only of such notifications (`ACP-BATCH-207` permits
one). Otherwise identical to `ConformingAgent`.

These pushes are notifications, not replies: they must neither fail a "no reply" check
(`ACP-JSONRPC-003`, `ACP-BATCH-202`, `ACP-EXT-201`) nor be mistaken for the reply a check is
waiting for (`ACP-BATCH-201`/`203`/`204`, the `ACP-INFO-*` probes' recorded behaviour).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

_STATUS = {"jsonrpc": "2.0", "method": "_fixture/status_update", "params": {"status": "ready"}}


class PushesStatusNotificationsAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._initialized = False

    def _push_status(self) -> None:
        self._write_line(_STATUS)

    def _handle(self, message: dict[str, Any]) -> None:
        if self._initialized:
            self._push_status()
        super()._handle(message)
        if message.get("method") == "initialize" and "id" in message:
            self._initialized = True
            self._push_status()

    def _handle_batch(self, items: list[Any]) -> None:
        if self._initialized:
            self._push_status()
            self._write_line([_STATUS, _STATUS])
        super()._handle_batch(items)


def main() -> None:
    PushesStatusNotificationsAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
