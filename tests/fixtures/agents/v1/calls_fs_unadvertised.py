#!/usr/bin/env python3
"""Defect fixture for ACP-CLIENTCAP-001: calls `fs/read_text_file` mid-turn even though the TCK's
mock client never advertised `fs` in `clientCapabilities` (Req 29 -- MUST NOT).

`path` is a harmless placeholder since the mock client only ever answers `-32601` in this
scenario.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsFsUnadvertisedAgent(SendsClientRequestAgent):
    _client_method = "fs/read_text_file"
    _client_params = {"path": "/tmp/tck-unadvertised-fs-probe.txt"}


def main() -> None:
    CallsFsUnadvertisedAgent().run()


if __name__ == "__main__":
    main()
