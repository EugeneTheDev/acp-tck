#!/usr/bin/env python3
"""Non-conforming fixture: handles every request normally, but never exits once stdin closes --
it needs SIGTERM/SIGKILL to actually terminate.

FAILs `ACP-SHUTDOWN-001` (`agent.exited_on_stdin_close` after an ordinary close). Self-test
only: its own `tests/v2/test_cli.py` entry keeps `--close-grace` small so the self-test doesn't
have to wait out the default grace period at every rung of the shutdown ladder.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class NeverExitsOnStdinCloseAgent(ConformingAgent):
    def run(self) -> None:
        super().run()  # processes every line normally; returns once stdin hits EOF
        while True:
            time.sleep(3600)  # ...then refuses to exit on its own


def main() -> None:
    NeverExitsOnStdinCloseAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
