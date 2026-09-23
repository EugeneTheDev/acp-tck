#!/usr/bin/env python3
"""Non-conforming fixture: omits the (v2-REQUIRED) `info` field from the `initialize` result.

FAILs `ACP-INIT-203` directly and cascades into `ACP-SCHEMA-001` (both validate the same
`initialize` result against the vendored schema, which lists `info` as required). Does not
cascade into `ACP-INIT-001`, which only checks for a non-error result, not its shape.

Advertises `capabilities: {"session": {}}`, same as `conforming.py`, so `ACP-SESSION-001/002`
PASS instead of SKIPping "not advertised".
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent, PROTOCOL_VERSION, _SUPPORTED_VERSIONS  # noqa: E402


class MissingInfoAgent(ConformingAgent):
    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        negotiated = requested if requested in _SUPPORTED_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": dict(self._capabilities),
        }


def main() -> None:
    MissingInfoAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
