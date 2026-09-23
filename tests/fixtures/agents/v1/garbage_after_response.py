#!/usr/bin/env python3
"""Non-conforming fixture: behaves like a conforming agent, then -- after stdin closes, strictly
after the last response any test awaits -- writes one line of plain-text garbage to stdout before
exiting. Violates ACP-TRANSPORT-001 ("every line the agent writes to stdout is a single valid
JSON-RPC 2.0 message").

Exists to prove `AgentProcess.close()` drains and records stdout written after the harness stops
reading it; without that drain this defect would be invisible to the transport test.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class GarbageAfterResponseAgent(ConformingAgent):
    def run(self) -> None:
        super().run()  # returns once stdin hits EOF (the client closed it)
        sys.stdout.write("not-json garbage written after stdin closed\n")
        sys.stdout.flush()


def main() -> None:
    GarbageAfterResponseAgent().run()


if __name__ == "__main__":
    main()
