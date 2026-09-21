#!/usr/bin/env python3
"""Strict (still-conforming) fixture: answers a repeat `initialize` on an already-initialized
connection with `-32600` (Invalid Request) instead of a second successful result.

v1 does not specify what happens on a second `initialize`, so this behaviour is not itself a
conformance violation -- it exists specifically as a self-test canary for
review-slices-5-6.md B1: any conformance test that sends a second `initialize` on a connection
it already initialized must not FAIL against this otherwise-fully-conforming agent. A full run
against this fixture must be CONFORMANT.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class RejectsSecondInitializeAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(agent_name="tck-fixture-rejects-second-initialize", **kwargs)
        self._initialized = False

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            if self._initialized:
                self._error(msg_id, -32600, "already initialized")
                return
            self._initialized = True
        super()._handle_request(method, msg_id, params)


def main() -> None:
    RejectsSecondInitializeAgent().run()


if __name__ == "__main__":
    main()
