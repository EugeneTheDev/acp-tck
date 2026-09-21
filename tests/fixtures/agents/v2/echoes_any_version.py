#!/usr/bin/env python3
"""Non-conforming fixture: echoes back whatever `protocolVersion` the client requested in
`initialize`, instead of returning its own latest supported version for a version it does not
support. Mirrors `tests/fixtures/agents/v1/echoes_any_version.py`.

FAILs exactly `ACP-INIT-003` and `ACP-INIT-201`: both probe the unsupported-version (`65535`)
case and assert the response does not echo it back verbatim. Does NOT fail `ACP-INIT-202` (the
downgrade probe, `protocolVersion: 1`): echoing `1` back is itself a valid answer to that probe
(`1` is one of the two accepted values), so that assertion is unaffected by this defect.

Advertises `capabilities: {"session": {}}`, same as `conforming.py`, so `ACP-SESSION-001/002`
PASS (session/new is otherwise unmodified and correct) instead of SKIPping "not advertised".
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class EchoesAnyVersionAgent(ConformingAgent):
    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested,
            "capabilities": dict(self._capabilities),
            "info": {"name": "tck-fixture-echoes-any-version-v2", "version": "0.0.0"},
        }


def main() -> None:
    EchoesAnyVersionAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
