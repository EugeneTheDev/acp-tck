#!/usr/bin/env python3
"""Non-conforming fixture: sends `elicitation/create` mid-turn regardless of whether the client
advertised `capabilities.elicitation.*` -- the mock client in `run_prompt` always advertises
`capabilities: {}`, so this is always unadvertised.

FAILs exactly `ACP-CLIENTCAP-201` (MUST NOT call `elicitation/create` when unadvertised).
`ACP-CLIENTCAP-202` is unaffected: `elicitation/create` is itself a defined v2 client method, so
it does not trip the "undefined method" check. Every other V2-2b/V2-2a id is unaffected -- the
turn otherwise finishes normally (this fixture fires-and-forgets, via
`SendsClientRequestAgent`, so it never waits for the mock client's `-32601` reply).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsElicitationUnadvertisedAgent(SendsClientRequestAgent):
    def _client_request_method(self) -> str:
        return "elicitation/create"

    def _client_request_params(self, session_id: Any) -> dict[str, Any]:
        return {
            "sessionId": session_id,
            "mode": "url",
            "message": "please confirm",
            "elicitationId": "elic-1",
            "url": "https://example.invalid/confirm",
        }


def main() -> None:
    CallsElicitationUnadvertisedAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
