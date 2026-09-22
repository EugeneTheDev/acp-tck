#!/usr/bin/env python3
"""Conforming for every normal exchange, but logs every raw line received to stderr, and
replies to a malformed (non-JSON) stdin line with an explicit `-32700` (Parse error) response
instead of silently swallowing it. v2 twin of v1's `noisy_stderr_and_parse_error_reply.py`.

Self-test only: deterministically exercises `ACP-STDERR-001`'s (INFORMATIONAL, non-zero stderr
byte count) and `ACP-INFO-PARSE-001`'s (INFORMATIONAL, "replied with error code -32700" instead
of the default "silent") non-default branches -- neither is asserted on, so this fixture does
not FAIL anything; it exists purely so `tests/v2/test_cli.py` can check the recorded
`record_property` values take their non-default shape at least once.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class NoisyStderrAndParseErrorReplyAgent(ConformingAgent):
    def run(self) -> None:
        for raw_line in sys.stdin:
            print(f"received: {raw_line!r}", file=sys.stderr)
            line = raw_line.rstrip("\n")
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._write(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                )
                continue
            if isinstance(message, dict):
                self._handle(message)
            elif isinstance(message, list):
                self._handle_batch(message)


def main() -> None:
    NoisyStderrAndParseErrorReplyAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
