#!/usr/bin/env python3
"""Non-conforming fixture: a strict v2-only agent that answers a `protocolVersion: 1` request
with a JSON-RPC error instead of downgrading gracefully (or answering with its own latest
supported version), violating the negotiation rule's `N < min(S)` case
(`.agents/research/acp-v2-version-negotiation.md` requirement 10) -- the same shortcut both
reference SDKs' *strict* v2 endpoints take (see `tck.v2.requirements`'s ACP-INIT-202 docstring).

FAILs exactly `ACP-INIT-202`. Every other `protocolVersion` this fixture is ever asked for in the
suite is `PROTOCOL_VERSION` (2) or `65535`, both of which still hit the normal, correct
negotiation path in `ConformingAgent._initialize_result`, so no other requirement is affected.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class V2OnlyErrorsOnV1Agent(ConformingAgent):
    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize" and params.get("protocolVersion") == 1:
            self._error(msg_id, -32602, "Invalid params: protocol version 1 is not supported")
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    V2OnlyErrorsOnV1Agent().run()


if __name__ == "__main__":
    main()
