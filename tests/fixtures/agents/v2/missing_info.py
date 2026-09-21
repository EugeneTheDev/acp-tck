#!/usr/bin/env python3
"""Non-conforming fixture: omits the (v2-REQUIRED) `info` field from the `initialize` result.

Documented cascade (`tck.v2.requirements`'s ACP-INIT-204 docstring style note applies here too):
FAILs `ACP-INIT-203` (the dedicated "info required" check) directly, and cascades into
`ACP-SCHEMA-001` -- both validate the same `initialize` result against the vendored schema,
whose `InitializeResponse` lists `info` in `required`. Does NOT cascade into `ACP-INIT-001`:
that row only asserts `initialize` returned a non-error result (this fixture still does), never
the result's shape -- schema/shape validation lives in `ACP-SCHEMA-001` alone.
`ACP-INIT-201/202/003/204` are unaffected: none of them inspect `info`.

Advertises `capabilities: {"session": {}}`, same as `conforming.py`, so `ACP-SESSION-001/002`
PASS (session/new is otherwise unmodified and correct) instead of SKIPping "not advertised".
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
