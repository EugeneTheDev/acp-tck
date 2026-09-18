#!/usr/bin/env python3
"""Non-conforming fixture: replies to `initialize` with a `-32602` error whenever the
requested `protocolVersion` isn't exactly the one it supports, instead of succeeding with its
own latest version. Violates ACP-INIT-003.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import PROTOCOL_VERSION, ConformingAgent  # noqa: E402


class VersionMismatchErrorsAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize" and params.get("protocolVersion") != PROTOCOL_VERSION:
            self._error(msg_id, -32602, "Unsupported protocol version")
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    VersionMismatchErrorsAgent().run()


if __name__ == "__main__":
    main()
