#!/usr/bin/env python3
"""Non-conforming fixture: every `session/update` notification carries `sessionId: "other"`
instead of the session actually being prompted. Violates ACP-PROMPT-002.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class UpdateWrongSessionAgent(ConformingAgent):
    def _send_update(self, session_id: str, text: str) -> None:
        super()._send_update("other", text)


def main() -> None:
    UpdateWrongSessionAgent().run()


if __name__ == "__main__":
    main()
