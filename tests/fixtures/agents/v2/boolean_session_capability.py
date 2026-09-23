#!/usr/bin/env python3
"""Non-conforming fixture: advertises `capabilities.session` as the literal boolean `true`
instead of an object marker -- there are no boolean-encoded capabilities anywhere in v2
(`docs/protocol/v2/migration.mdx:181`).

FAILs `ACP-INIT-204` and, via schema validation of the same result, `ACP-SCHEMA-001` (both
reject `true` against `AgentCapabilities.session`'s `anyOf [SessionCapabilities, null]`). Does
NOT cascade into `ACP-INIT-001` (only checks for a non-error result) or `ACP-SESSION-001/002`
(the object-marker gate only checks `value is not None`, so `true` still reads as advertised,
and `session/new` handling is otherwise unmodified) -- those still PASS.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent, PROTOCOL_VERSION, _SUPPORTED_VERSIONS  # noqa: E402


class BooleanSessionCapabilityAgent(ConformingAgent):
    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        negotiated = requested if requested in _SUPPORTED_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": negotiated,
            "capabilities": {"session": True},
            "info": {"name": "tck-fixture-boolean-session-capability", "version": "0.0.0"},
        }


def main() -> None:
    BooleanSessionCapabilityAgent().run()


if __name__ == "__main__":
    main()
