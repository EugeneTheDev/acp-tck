#!/usr/bin/env python3
"""Conforming fixture used by the TCK's own self-tests, not a defect fixture: every prompt
withholds its response until `session/cancel` arrives (`conforming.py` only does this for the
`__hang__` prompt text). Used to drive ACP-CANCEL-001/002 deterministically in a self-test,
since the conformance suite itself must not depend on `conforming.py`'s `__hang__` special case.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class HangsUntilCancelAgent(ConformingAgent):
    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        prompt = params.get("prompt") or []
        first_text = next(
            (
                block.get("text", "")
                for block in prompt
                if isinstance(block, dict) and block.get("type") == "text"
            ),
            "",
        )
        self._send_update(session_id, first_text)
        self._pending_prompt = {"id": msg_id, "session_id": session_id}


def main() -> None:
    HangsUntilCancelAgent().run()


if __name__ == "__main__":
    main()
