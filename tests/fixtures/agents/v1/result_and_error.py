#!/usr/bin/env python3
"""Non-conforming fixture: the `initialize` response carries both `result` and `error`.
Violates J1 / ACP-JSONRPC-002 (a response must have exactly one of `result`/`error`).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ResultAndErrorAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": self._initialize_result(),
                    "error": {"code": -32603, "message": "also an error, illegally"},
                }
            )
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    ResultAndErrorAgent().run()


if __name__ == "__main__":
    main()
