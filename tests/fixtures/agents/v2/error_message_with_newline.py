#!/usr/bin/env python3
"""Non-conforming fixture: the `-32601` (Method not found) error message for an unrecognized
method carries an embedded newline.

FAILs `ACP-ERROR-001` (an error's `message` must be non-empty and single-line) via the
`_tck/does_not_exist` probe `test_error_messages_are_non_empty_single_line` sends. Every other
error path (and every other method) is unaffected -- only the `-32601` branch is touched.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class ErrorMessageWithNewlineAgent(ConformingAgent):
    def _error(self, msg_id: Any, code: int, message: str) -> None:
        if code == -32601:
            message = message + "\nunexpected trailing line"
        super()._error(msg_id, code, message)


def main() -> None:
    ErrorMessageWithNewlineAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
