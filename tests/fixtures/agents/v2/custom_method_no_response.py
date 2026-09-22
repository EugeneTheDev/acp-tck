#!/usr/bin/env python3
"""Non-conforming fixture: silently swallows every `_`-prefixed custom method request instead
of sending *any* response (result or error).

FAILs `ACP-EXT-001` (a `_`-prefixed custom method request MUST receive a response of some
shape). Every other, non-`_`-prefixed method is dispatched normally (via `super()`), so the
`initialize`/`session/new` handshake and the rest of the turn are unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class CustomMethodNoResponseAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method.startswith("_"):
            return  # deliberately no response at all -- FAILs ACP-EXT-001
        super()._handle_request(method, msg_id, params)


def main() -> None:
    CustomMethodNoResponseAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
