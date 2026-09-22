#!/usr/bin/env python3
"""Non-conforming fixture: advertises `capabilities.session.delete: {}` but `session/delete`
always errors, regardless of the sessionId given.

FAILs `ACP-DELETE-201` (delete of an existing session must succeed), `ACP-DELETE-202` (cascades:
its own `session/delete` call fails the same way before it can compare before/after
`session/list` results), and `ACP-DELETE-203` (ADVISORY: deleting an unknown sessionId should
also succeed silently, but this fixture errors unconditionally). `ACP-DELETE-201`/`202` are
`Tier.CAPABILITY`, so this flips the overall verdict to NOT CONFORMANT; `ACP-DELETE-203` being
ADVISORY does not add to that on its own. Mirrors v1's `advertises_load_but_errors.py`.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class AdvertisesDeleteButErrorsAgent(ConformingAgent):
    def _handle_delete_session(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._error(msg_id, -32603, "Internal error: delete is not actually implemented")


def main() -> None:
    AdvertisesDeleteButErrorsAgent(capabilities={"session": {"delete": {}}}).run()


if __name__ == "__main__":
    main()
