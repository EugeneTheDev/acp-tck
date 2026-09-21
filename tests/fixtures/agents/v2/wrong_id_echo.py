#!/usr/bin/env python3
"""Non-conforming fixture: mangles every response id -- adds 1 to integer ids and appends a
suffix to string ids -- instead of echoing the request id verbatim. Violates ACP-JSONRPC-001.
Mirrors v1's `wrong_id_echo.py` on top of v2's `_base.py` (D6).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def _mangle(msg_id: Any) -> Any:
    if isinstance(msg_id, bool):
        return msg_id
    if isinstance(msg_id, int):
        return msg_id + 1
    if isinstance(msg_id, str):
        return msg_id + "-wrong"
    return msg_id


class WrongIdEchoAgent(ConformingAgent):
    def _reply(self, msg_id: Any, result: dict[str, Any]) -> None:
        super()._reply(_mangle(msg_id), result)

    def _error(self, msg_id: Any, code: int, message: str) -> None:
        super()._error(_mangle(msg_id), code, message)


def main() -> None:
    WrongIdEchoAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
