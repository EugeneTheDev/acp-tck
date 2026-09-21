#!/usr/bin/env python3
"""Defect fixture for ACP-CLIENTCAP-003: calls `elicitation/create` mid-turn even though the
TCK's mock client never advertised any elicitation mode in `clientCapabilities` (Req 32 -- MUST
NOT).

`elicitation/create`'s params schema requires only `message` (`sessionId` is not even a
declared property of this def, per direct schema introspection) -- `SendsClientRequestAgent`
still adds a `sessionId` on top since the vendored schema has no `additionalProperties: false`
anywhere, so the extra key is harmless and the mock client only ever answers `-32601` in this
scenario regardless.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsElicitationUnadvertisedAgent(SendsClientRequestAgent):
    _client_method = "elicitation/create"
    _client_params = {"message": "Please confirm this unadvertised elicitation."}


def main() -> None:
    CallsElicitationUnadvertisedAgent().run()


if __name__ == "__main__":
    main()
