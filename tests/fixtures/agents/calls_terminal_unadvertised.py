#!/usr/bin/env python3
"""Defect fixture for ACP-CLIENTCAP-002: calls `terminal/create` mid-turn even though the TCK's
mock client never advertised `terminal` in `clientCapabilities` (Req 30 -- MUST NOT).

`terminal/create`'s params schema requires `sessionId` and `command`
(`.agents/research/acp-v1-protocol-surface.md`); `command` is a harmless placeholder since the
mock client only ever answers `-32601` in this scenario.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsTerminalUnadvertisedAgent(SendsClientRequestAgent):
    _client_method = "terminal/create"
    _client_params = {"command": "true"}


def main() -> None:
    CallsTerminalUnadvertisedAgent().run()


if __name__ == "__main__":
    main()
