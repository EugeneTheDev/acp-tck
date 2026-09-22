#!/usr/bin/env python3
"""Non-conforming fixture: sends a `session/update` whose `sessionUpdate` discriminator is an
unrecognized value that does *not* begin with `_` (`"surprise"`).

FAILs `ACP-ENUM-202` (every open-enum value at a site the prose doesn't individually restate --
including `sessionUpdate` itself -- must be a defined constant or `_`-prefixed). Schema-valid on
its own (the vendored schema's `SessionUpdate` `other` branch only requires `sessionUpdate` to be
a string and allows arbitrary extra properties, `schema/v2/schema.json`'s `not`-guarded fallback
branch), so `ACP-SCHEMA-001` does not cascade here -- this is a purely prose-level violation, the
whole point of `ACP-ENUM-202` existing as a separate, hand-written check.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class UnprefixedCustomSessionUpdateAgent(ConformingAgent):
    def _mid_turn_action(self, session_id: Any) -> bool:
        self._send_update(session_id, {"sessionUpdate": "surprise"})
        return False  # fire-and-forget: finish the turn immediately, in the same call


def main() -> None:
    UnprefixedCustomSessionUpdateAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
