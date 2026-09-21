#!/usr/bin/env python3
"""Non-conforming (ADVISORY-only) fixture: replies to unknown methods with an empty success
result instead of `-32601 "Method not found"`. Should only trip the ADVISORY
`ACP-JSONRPC-004`, not any MANDATORY/CAPABILITY requirement. Mirrors v1's
`unknown_method_no_error.py` on top of v2's `_base.py` (D6).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

_KNOWN_METHODS = {
    "initialize",
    "session/new",
    "session/list",
    "session/resume",
    "session/close",
    "session/prompt",
}


class UnknownMethodNoErrorAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method in _KNOWN_METHODS:
            super()._handle_request(method, msg_id, params)
            return
        self._reply(msg_id, {})


def main() -> None:
    UnknownMethodNoErrorAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
