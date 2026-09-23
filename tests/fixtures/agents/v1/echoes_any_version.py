#!/usr/bin/env python3
"""Non-conforming fixture: echoes back whatever `protocolVersion` the client requested in
`initialize`, instead of returning its own latest supported version for an unsupported
request. Violates the strengthened ACP-INIT-003.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class EchoesAnyVersionAgent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            requested = params.get("protocolVersion")
            self._reply(
                msg_id,
                {
                    "protocolVersion": requested,
                    "agentCapabilities": {},
                    "agentInfo": {"name": "tck-fixture-echoes-any-version", "version": "0.0.0"},
                },
            )
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    EchoesAnyVersionAgent().run()


if __name__ == "__main__":
    main()
