#!/usr/bin/env python3
"""Non-conforming fixture: silently swallows every `_`-prefixed custom method request instead
of sending *any* response (result or error).

FAILs `ACP-EXT-001` (a `_`-prefixed custom method request MUST receive a response of some
shape). Every other, non-`_`-prefixed method is dispatched normally (via `super()`), so the
`initialize`/`session/new` handshake and the prompt turn itself are unaffected.

Not unaffected beyond the turn, though: `test_diagnostics.py`'s own `ACP-ERROR-001` probe sends a
`_`-prefixed unknown-method request and expects *some* well-formed error/result back to check
its shape -- against this fixture it gets no reply at all, so `ACP-ERROR-001` also FAILs
whenever this fixture is run unscoped (confirmed; see `tests/v2/test_cli.py`'s corresponding
self-test, whose `-k` scope is widened to catch this). It does NOT cascade into
`ACP-BATCH-203/204/205`, since batch requests do not wait on a per-item basis for a response
that never arrives.
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
