#!/usr/bin/env python3
"""`AsksPermissionAgent` plus `sessionCapabilities.close` support, used as the self-test for
`ACP-CLOSE-002` against a conforming, permission-asking agent (review-slices-5-6.md S3).

Before the S3 fix, `test_close_in_flight_prompt_resolves_cancelled` drove its own hand-rolled
read loop that only understood three message shapes and silently dropped any agent -> client
*request* it didn't recognize -- so a `session/request_permission` arriving while `session/close`
was in flight deadlocked the test (`AgentTimeout`) instead of exercising the close-cancellation
path. `run_prompt`'s `on_action` hook now answers everything a mock client is expected to,
including that permission request, so this fixture should make `ACP-CLOSE-002` PASS.

`_handle_prompt` deliberately delays sending the permission request past `run_prompt`'s short
post-update peek window (`cancel_race_peek`) so the mock client has already committed to firing
`session/close` (the "trigger") by the time the permission request is read: this makes the
permission response deterministically "cancelled" (`run_prompt` only answers "cancelled" once its
trigger has fired) rather than racing against the peek and getting resolved as "selected" before
`session/close` is even sent. Without the delay, the fixture would still work but flakily
`pytest.skip` instead of `PASS` depending on scheduling.

`_handle_close` also has to resolve `self._awaiting_permission` (the state
`AsksPermissionAgent` uses for its own outstanding permission request) as cancelled itself:
`_base.py`'s stock `_handle_close` only knows about `self._pending_prompt` (the `__hang__`
mechanism used by fixtures that don't ask permission), which this agent never sets.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from asks_permission import AsksPermissionAgent  # noqa: E402

CAPABILITIES = {"sessionCapabilities": {"close": {}}}

# Comfortably longer than `cancel_race_peek`'s value at the `--timeout 5` the self-tests use
# (`cancel_race_peek(5) == 0.1`) so the mock client's post-update peek always misses this
# fixture's permission request and falls through to firing `session/close`, and comfortably
# shorter than the test's own timeout (`default_timeout`). Kept small (rather than the widest
# possible `cancel_race_peek` value, 0.5s) since every prompt turn against this fixture pays this
# delay and it is used by more than one self-test (review-slices-5-6.md item 10/S11 runtime).
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
        # Reply to `session/close` itself before resolving the pending prompt: this fixture's
        # self-test (`test_close_in_flight_prompt_resolves_cancelled`) records the close response
        # as soon as it sees it, then returns as soon as it sees the prompt's own response -- if
        # the prompt response went out first, the close response would still be sitting unread
        # on `run_prompt`'s side when it returned, and the test would `pytest.skip` ("not
        # exercised") instead of asserting the close-cancellation behavior it exists to check.
        self._reply(msg_id, {})
        if pending is not None:
            # Mirror `_base.py`'s own `_pending_prompt`-cancellation handling in `_handle_close`,
            # but for this subclass's permission-based pending state: resolve the prompt as
            # cancelled and stop waiting for the client's permission answer, which may never
            # come once the session is closing.
            self._awaiting_permission = None
            self._reply(pending["prompt_id"], {"stopReason": "cancelled"})


def main() -> None:
    AsksPermissionClosableAgent().run()


if __name__ == "__main__":
    main()
