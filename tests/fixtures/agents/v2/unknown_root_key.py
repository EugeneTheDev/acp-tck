#!/usr/bin/env python3
"""Non-conforming fixture: the `initialize` result carries an unrecognized root-level key
(`"unknownRootKey"`) alongside the normal `protocolVersion`/`capabilities`/`info`.

FAILs `ACP-SCHEMA-002` (no agent-authored response `result` may carry an unrecognized root-level
key -- the vendored schema itself never sets `additionalProperties: false`, so this is only
caught by `tck.v2.validation.find_unknown_root_keys`'s hand-written check, not by schema
validation; `ACP-INIT-001`/`ACP-SCHEMA-001` are unaffected, since the schema does not forbid an
extra property here). Does not touch `capabilities` itself, so `ACP-EXT-202` (which checks
`capabilities`'s own root keys specifically) is unaffected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class UnknownRootKeyAgent(ConformingAgent):
    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        result = super()._initialize_result(params)
        result["unknownRootKey"] = True
        return result


def main() -> None:
    UnknownRootKeyAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
