#!/usr/bin/env python3
"""A conforming ACP v1 fixture agent that additionally advertises and correctly implements
`loadSession` and every `sessionCapabilities` marker (`list`, `delete`, `resume`, `close`,
`additionalDirectories`).

Used to exercise the CAPABILITY-tier session-capability tests (`ACP-LOAD-*`, `ACP-RESUME-*`,
`ACP-LIST-*`, `ACP-DELETE-*`, `ACP-CLOSE-*`, `ACP-ADDDIRS-001`) end to end -- `_base.py`
already implements all the required behavior (replay-before-response on load, no replay on
resume, cwd-filtered list, silent delete/close); this fixture only needs to turn the
capabilities on. `conforming.py` deliberately stays at `agentCapabilities: {}` so these tests
SKIP against it instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CAPABILITIES = {
    "loadSession": True,
    "sessionCapabilities": {
        "list": {},
        "delete": {},
        "resume": {},
        "close": {},
        "additionalDirectories": {},
    },
}


def main() -> None:
    ConformingAgent(capabilities=CAPABILITIES, agent_name="tck-fixture-conforming-full").run()


if __name__ == "__main__":
    main()
