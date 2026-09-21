#!/usr/bin/env python3
"""Non-conforming fixture: advertises `capabilities.session` as the literal boolean `true`
instead of an object marker -- there are no boolean-encoded capabilities anywhere in v2
(`docs/protocol/v2/migration.mdx:181`).

Documented cascade: FAILs `ACP-INIT-204` (the dedicated object-marker check) directly, and
cascades into `ACP-SCHEMA-001` -- both validate the `initialize` result against the vendored
schema, whose `AgentCapabilities.session` is `anyOf [SessionCapabilities, null]`, which a bare
`true` does not satisfy. Does NOT cascade into `ACP-INIT-001`: that row only asserts
`initialize` returned a non-error result (this fixture still does), never the result's shape.
Does NOT cascade into `ACP-SESSION-001/002` either: the capability gate
(`capability_is_supported`, object-marker mode) only checks `value is not None`, so a literal
`true` still reads as "advertised", and this fixture's `session/new` handling (inherited from
`ConformingAgent`, unmodified) still works correctly -- those CAPABILITY-tier tests still PASS.
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
