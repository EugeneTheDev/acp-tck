#!/usr/bin/env python3
"""Non-conforming fixture: silently swallows every `_`-prefixed custom method request instead
of sending *any* response (result or error).

FAILs `ACP-EXT-001` (a `_`-prefixed custom method request MUST receive a response of some
shape). Every other method is dispatched normally via `super()`, so the handshake and prompt
turn are unaffected.

Also FAILs `ACP-ERROR-001`: that requirement's own probe is a `_`-prefixed unknown method and
gets no reply at all against this fixture (see `tests/v2/test_cli.py`'s widened `-k` scope for
this fixture). Does NOT cascade into `ACP-BATCH-203/204/205`, since batch requests don't wait
per-item on a response that never arrives.
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
