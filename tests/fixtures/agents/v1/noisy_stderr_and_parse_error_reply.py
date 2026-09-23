#!/usr/bin/env python3
"""Combines two behaviours the base `ConformingAgent` doesn't exhibit, to exercise
`ACP-STDERR-001`/`ACP-INFO-PARSE-001` self-tests deterministically:

- logs every raw line to stderr, so `acp_tck_stderr_bytes` is reliably non-zero;
- replies `{"jsonrpc": "2.0", "id": null, "error": {"code": -32700, "message": "Parse error"}}`
  on unparseable JSON instead of silently swallowing it.

`run()` is fully overridden rather than using `on_message=...`: the parse-error reply must
happen *instead of* the base class's `except json.JSONDecodeError: continue`, which only `run()`
itself controls.
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
