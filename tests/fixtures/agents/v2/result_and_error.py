#!/usr/bin/env python3
"""Non-conforming fixture: the `initialize` response carries both `result` and `error`.
Violates ACP-JSONRPC-002 (a response must have exactly one of `result`/`error`) and, since
`validate_response_envelope` is also part of the full-exchange schema check, ACP-SCHEMA-001 too.
Mirrors v1's `result_and_error.py` on top of v2's `_base.py`.

Note this does NOT fail ACP-INIT-001: that check only asserts `"result" in msg`, which is still
true even though `error` is illegally present too -- the narrower envelope/schema checks above
are what actually catch this defect in v2.
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
                    "result": self._initialize_result(params),
                    "error": {"code": -32603, "message": "also an error, illegally"},
                }
            )
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    ResultAndErrorAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
