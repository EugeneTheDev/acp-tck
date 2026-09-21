#!/usr/bin/env python3
"""Fixture combining two INFORMATIONAL-probe behaviours that the base `ConformingAgent` does not
exhibit, for exercising `ACP-STDERR-001`/`ACP-INFO-PARSE-001` self-tests against a *known*
behaviour instead of an unknown SDK's:

- logs every raw line it receives to stderr (same pattern as `stderr_chatter.py`), so
  `ACP-STDERR-001`'s recorded `acp_tck_stderr_bytes` is reliably non-zero;
- replies `{"jsonrpc": "2.0", "id": null, "error": {"code": -32700, "message": "Parse error"}}`
  to a line that fails to parse as JSON at all, instead of silently swallowing it like the base
  class's `run()` does -- so `ACP-INFO-PARSE-001`'s self-test has a fixture that deterministically
  exercises the "replied -32700 with id:null" branch rather than "silent".

Cannot simply pass `on_message=...` to the base `ConformingAgent` for the second part: the
parse-error reply has to happen *instead of* the base class's `except json.JSONDecodeError:
continue`, which only `run()` itself controls -- hence the full override below.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class NoisyStderrAndParseErrorReplyAgent(ConformingAgent):
    def run(self) -> None:
        if self._on_start is not None:
            self._on_start()
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            print(f"noisy_stderr received: {line}", file=sys.stderr, flush=True)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                )
                continue
            if isinstance(message, dict):
                self._handle(message)


def main() -> None:
    NoisyStderrAndParseErrorReplyAgent().run()


if __name__ == "__main__":
    main()
