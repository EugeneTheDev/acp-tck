#!/usr/bin/env python3
"""Non-conforming fixture: sends `fs/read_text_file` mid-turn, a v1-shaped method name removed
entirely from v2 (`fs/*`/`terminal/*`; see `tck.v2.protocol.CLIENT_METHODS`).

FAILs `ACP-CLIENTCAP-202` (agent -> client methods must be a defined v2 method or `_`-prefixed)
and, as an expected cascade, `ACP-SCHEMA-001` (unknown agent-authored method, same pattern as
`ACP-INIT-204`). `ACP-CLIENTCAP-201` is unaffected since this isn't `elicitation/create`.
Fires-and-forgets via `SendsClientRequestAgent`, so the turn otherwise finishes normally.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsFsUnadvertisedAgent(SendsClientRequestAgent):
    def _client_request_method(self) -> str:
        return "fs/read_text_file"

    def _client_request_params(self, session_id: Any) -> dict[str, Any]:
        return {"sessionId": session_id, "path": "/tmp/tck-example.txt"}


def main() -> None:
    CallsFsUnadvertisedAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
