#!/usr/bin/env python3
"""Positive control: `conforming_full.py`'s capabilities/permission behavior, but every pair of
`session/update` notifications a single turn naturally sends back-to-back -- `user_message`+
`running` in `_handle_prompt`'s prologue, `agent_message_chunk`+the terminating idle in
`_finish_turn` -- is delivered as one JSON-RPC batch array line instead of two separate lines.
`ACP-BATCH-207` (ADVISORY, always-SKIPped as record-only in `test_batch.py` -- "cannot force an
agent to spontaneously emit a batch") explicitly permits this; nothing in the spec requires an
agent to keep every notification on its own line, and `ACP-TRANSPORT-201` itself says a batch
array is just as valid a stdout line as a single object.

Must PASS every requirement `conforming_full.py` itself PASSes (under `--cancel-prompt
__hang__`): this fixture exists to prove batching an agent's own spontaneous notifications is
conformant and does not, by itself, break anything the TCK checks -- if it did, that would be a
TCK bug (see `tck.v2.conformance._helpers.run_prompt`'s `_handle_one`, which unpacks a
batch-shaped line's dict elements exactly the same way it would unpacked, separate lines).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import AsksPermissionAgent  # noqa: E402


class EmitsBatchUpdatesAgent(AsksPermissionAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._update_batch: list[dict[str, Any]] | None = None

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        obj = {"jsonrpc": "2.0", "method": method, "params": params}
        if self._update_batch is not None and method == "session/update":
            self._update_batch.append(obj)
        else:
            self._write(obj)

    def _flush_update_batch(self) -> None:
        batch, self._update_batch = self._update_batch, None
        if batch:
            self._write_line(batch)

    def _handle_prompt(self, msg_id: Any, params: dict[str, Any]) -> None:
        self._update_batch = []
        super()._handle_prompt(msg_id, params)
        self._flush_update_batch()

    def _finish_turn(self, session_id: Any, stop_reason: str | None = None) -> None:
        self._update_batch = []
        super()._finish_turn(session_id, stop_reason)
        self._flush_update_batch()


def main() -> None:
    EmitsBatchUpdatesAgent(
        capabilities={
            "session": {
                "prompt": {"image": {}, "audio": {}, "embeddedContext": {}},
            },
        }
    ).run()


if __name__ == "__main__":
    main()
