#!/usr/bin/env python3
"""Non-conforming-but-legal-to-encounter fixture: answers `initialize` normally, then exits
immediately (without replying) the moment it reads a line that is not valid JSON at all.

Used to exercise `AgentProcess.send_raw`'s translation of a dead-process write into
`AgentExited`: it must translate `OSError`/`BrokenPipeError`/`ConnectionResetError` raised while
writing to a *dead* agent's stdin, not let it escape as a bare traceback. `ACP-INFO-PARSE-001`
sends a malformed line, then -- regardless of what it read back -- immediately tries an
ordinary `session/new` on the same connection to see if it is still usable
(`_probe_connection_usable_after` in `test_informational.py`). Against this fixture, that second
write lands on a stdin pipe whose reader has already exited, so it is exactly the
"write to a dead process" case this targets.

Not built on `_base.ConformingAgent`: its `run()` loop deliberately swallows
`json.JSONDecodeError` (malformed input is "a harness test concern, not ours to crash on"),
which is the opposite of what this fixture needs to do.
"""

import json
import sys


def _reply(msg_id, result) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.rstrip("\n")
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            # The one behaviour this fixture exists to exhibit: die on the first malformed line,
            # without replying and without reading anything further.
            sys.exit(1)
        if isinstance(message, dict) and message.get("method") == "initialize" and "id" in message:
            _reply(
                message["id"],
                {
                    "protocolVersion": 1,
                    "agentCapabilities": {},
                    "agentInfo": {"name": "tck-fixture-dies-on-bad-json", "version": "0.0.0"},
                },
            )
        # Anything else well-formed is ignored -- this fixture only ever needs to survive long
        # enough to answer `initialize` before the malformed line arrives.


if __name__ == "__main__":
    main()
