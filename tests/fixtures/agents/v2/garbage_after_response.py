#!/usr/bin/env python3
"""Non-conforming fixture: behaves like a conforming agent for the whole exchange, then --
after stdin closes (i.e. strictly after the last response any test ever awaits) -- writes one
line of plain-text garbage to stdout before exiting. Violates ACP-TRANSPORT-201 ("every line
the agent writes to stdout is a single valid JSON-RPC 2.0 message, or a non-empty array of
them"). Mirrors v1's `garbage_after_response.py` on top of v2's `_base.py`.

Exists to prove `AgentProcess.close()` actually drains and records stdout written after the
harness stops reading it -- without that drain, this fixture's whole defect would be invisible
to the transport test, a false negative on the TCK's own highest-value check.
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
    GarbageAfterResponseAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
