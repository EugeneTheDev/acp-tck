#!/usr/bin/env python3
"""Non-conforming fixture: sends `fs/read_text_file` mid-turn -- a v1-shaped method name that
does not exist as a client method in v2 at all (`fs/*`/`terminal/*` were removed; see
`tck.v2.protocol.CLIENT_METHODS`).

FAILs `ACP-CLIENTCAP-202` (every agent -> client method during a turn must be a defined v2
client/protocol method, or `_`-prefixed) and, as an expected cascade, `ACP-SCHEMA-001` too --
`fs/read_text_file` isn't a known agent-authored method at all, so the schema validator flags it
as "not a known agent-authored request/notification method" (same documented
defect-cascades-into-schema pattern as `ACP-INIT-204`). `ACP-CLIENTCAP-201` is unaffected:
`fs/read_text_file` is not `elicitation/create`. Fires-and-forgets via `SendsClientRequestAgent`,
so the turn otherwise finishes normally.
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
