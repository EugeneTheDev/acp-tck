#!/usr/bin/env python3
"""`AsksPermissionAgent` plus `sessionCapabilities.close` support, used as the self-test for
`ACP-CLOSE-002` against a conforming, permission-asking agent: `session/close` on an in-flight,
permission-pending prompt must resolve it as cancelled, and `run_prompt`'s `on_action` hook must
answer the outstanding `session/request_permission` instead of deadlocking.

`_handle_prompt` delays sending the permission request past `run_prompt`'s post-update peek
window (`cancel_race_peek`) so `session/close` is deterministically sent first, making the
permission response resolve as "cancelled" rather than racing and getting "selected". Without
the delay this would flakily `pytest.skip` instead of `PASS`.

`_handle_close` also resolves `self._awaiting_permission` itself, since `_base.py`'s stock
`_handle_close` only knows about `self._pending_prompt` (the `__hang__` mechanism), which this
agent never sets.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from asks_permission import AsksPermissionAgent  # noqa: E402

CAPABILITIES = {"sessionCapabilities": {"close": {}}}

# Longer than `cancel_race_peek(5) == 0.1` (the `--timeout 5` self-tests use) so the peek always
# misses this fixture's permission request, but short enough to not pad every prompt turn much,
# since more than one self-test pays this delay.
_PERMISSION_REQUEST_DELAY_S = 0.3


class AsksPermissionClosableAgent(AsksPermissionAgent):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("capabilities", CAPABILITIES)
        super().__init__(**kwargs)

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
        time.sleep(_PERMISSION_REQUEST_DELAY_S)

        self._perm_id_counter += 1
        perm_id = f"perm-{self._perm_id_counter}"
        self._awaiting_permission = {"prompt_id": msg_id, "perm_id": perm_id}
        self._write(
            {
                "jsonrpc": "2.0",
                "id": perm_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": session_id,
                    "toolCall": {"toolCallId": "tool-1"},
                    "options": [
                        {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            }
        )

    def _handle_close(self, msg_id: Any, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        pending = self._awaiting_permission
        self._sessions.pop(session_id, None)
        # Reply to `session/close` before resolving the pending prompt, or the close response
        # would still be unread when the test returns and it would `pytest.skip` instead of
        # asserting the close-cancellation behavior.
        self._reply(msg_id, {})
        if pending is not None:
            self._awaiting_permission = None
            self._reply(pending["prompt_id"], {"stopReason": "cancelled"})


def main() -> None:
    AsksPermissionClosableAgent().run()


if __name__ == "__main__":
    main()
