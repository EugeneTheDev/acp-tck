#!/usr/bin/env python3
"""Conforming fixture: pushes an unprompted `_fixture/status_update` notification right after
answering `initialize`, and from then on right before handling every inbound line (so ahead of
every reply, and in the quiet period after every notification). Otherwise identical to
`ConformingAgent`.

Models a real agent that reports connection-level status at any time once initialized. Such a
push is a notification, not a reply, so it must neither fail a "no reply" check
(`ACP-JSONRPC-003`) nor be mistaken for the reply a check is waiting for (e.g. the
`ACP-INFO-*` probes' recorded behaviour).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class PushesStatusNotificationsAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(on_message=self._on_line, **kwargs)
        self._initialized = False

    def _push_status(self) -> None:
        self._notify("_fixture/status_update", {"status": "ready"})

    def _on_line(self, line: str) -> None:
        if self._initialized:
            self._push_status()

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        super()._handle_request(method, msg_id, params)
        if method == "initialize":
            self._initialized = True
            self._push_status()


def main() -> None:
    PushesStatusNotificationsAgent().run()


if __name__ == "__main__":
    main()
