#!/usr/bin/env python3
"""A v2-only agent: always answers `initialize` with `protocolVersion: 2`, its own latest and
only supported version, regardless of what the client requested -- including a v1-shaped
`initialize` (`{"protocolVersion": 1, "clientCapabilities": {}}`). This is the honest,
conforming answer for an agent that does not speak v1 at all (per the negotiation rule: answer
the requested version if supported, else your own latest).

Used to prove `blocked_by_version_mismatch` is symmetric: run under `--protocol-version 1` (see
`tests/v1/test_cli.py`), this agent's v2-shaped result (`info`/`capabilities`, not
`agentInfo`/`agentCapabilities`) cannot be judged against v1's shape rules, so every
v1-shape-dependent row SKIPs with the `VERSION-MISMATCH:` marker while the negotiation-outcome
rows PASS -- the mirror image of a v1-only agent run under `--protocol-version 2`.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import PROTOCOL_VERSION, ConformingAgent  # noqa: E402


class V2OnlyHonestAgent(ConformingAgent):
    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        result = super()._initialize_result(params)
        result["protocolVersion"] = PROTOCOL_VERSION
        return result


def main() -> None:
    V2OnlyHonestAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
