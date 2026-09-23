#!/usr/bin/env python3
"""Non-conforming-but-legal-to-encounter fixture: answers `initialize` normally, then exits
immediately (without replying) the moment it reads a line that is not valid JSON at all.

Exercises `AgentProcess.send_raw`'s translation of a dead-process write into `AgentExited`
rather than a bare traceback. `ACP-INFO-PARSE-001` (`_probe_connection_usable_after` in
`test_informational.py`) sends a malformed line then probes the connection with `session/new`;
against this fixture that probe write lands on a stdin pipe whose reader has already exited.

Not built on `_base.ConformingAgent`, whose `run()` loop swallows `json.JSONDecodeError` --
the opposite of what this fixture needs to do.
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
            # Die on the first malformed line, without replying or reading further.
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
        # Anything else well-formed is ignored.


if __name__ == "__main__":
    main()
