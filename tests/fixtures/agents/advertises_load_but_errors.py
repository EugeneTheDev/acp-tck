#!/usr/bin/env python3
"""Non-conforming fixture: advertises `loadSession: true` in `agentCapabilities` but always
responds to `session/load` with a JSON-RPC error (`-32601`, as if the method did not exist).
This should FAIL ACP-LOAD-001 (and therefore ACP-LOAD-002, which depends on a load ever
succeeding) -- proving that a CAPABILITY-tier FAIL flips the overall verdict to NOT
CONFORMANT, since a capability was advertised but not actually honored.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CAPABILITIES = {"loadSession": True}


class AdvertisesLoadButErrorsAgent(ConformingAgent):
    def _handle_load(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._error(msg_id, -32601, "Method not found")


def main() -> None:
    AdvertisesLoadButErrorsAgent(
        capabilities=CAPABILITIES, agent_name="tck-fixture-advertises-load-but-errors"
    ).run()


if __name__ == "__main__":
    main()
