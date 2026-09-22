#!/usr/bin/env python3
"""Positive control: sends a `session/update` whose `sessionUpdate` discriminator is a
`_`-prefixed custom value (`"_tck_custom_update"`) -- legal per the open-enum extensibility rule.

Must PASS `ACP-ENUM-202`: its check is `is_valid_open_enum_value`, which accepts any
`_`-prefixed string regardless of whether it's a defined constant. Paired with
`unprefixed_custom_session_update.py`'s negative control (same site, unprefixed unknown value).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class PrefixedCustomSessionUpdateAgent(ConformingAgent):
    def _mid_turn_action(self, session_id: Any) -> bool:
        self._send_update(session_id, {"sessionUpdate": "_tck_custom_update"})
        return False  # fire-and-forget: finish the turn immediately, in the same call


def main() -> None:
    PrefixedCustomSessionUpdateAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
