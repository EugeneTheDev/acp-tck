#!/usr/bin/env python3
"""Conforming fixture modelling the reference SDKs' dual-version *protocol router*: supports
protocol versions 1 and 2. A request for exactly `1` gets an ordinary v1 handshake. A request
for anything `>= 2` (including the TCK's unsupported-version probe, 65535) is routed to v2 --
which means its params are validated as a v2 `InitializeRequest`, whose `info` field is
REQUIRED (`schema/v2/schema.json:5838`). A caller that omits `info` (or sends a malformed one)
gets `-32602` naming the missing field, exactly as `AgentProtocolRouter`/`role/acp.rs:633`
does; a caller that includes a valid `info` gets back `protocolVersion: 2` in an otherwise
v1-shaped result.

Self-test canary for ACP-INIT-003's 65535 probe carrying `info`: without it, this fixture's
`65535` request would fail with a spurious `-32602`, flipping the run NOT CONFORMANT.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class RouterRequiresInfoAgent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(agent_name="tck-fixture-router-requires-info", **kwargs)

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            requested = params.get("protocolVersion")
            if requested == 1:
                super()._handle_request(method, msg_id, params)
                return
            self._client_capabilities = params.get("clientCapabilities") or {}
            info = params.get("info")
            missing = self._missing_info_field(info)
            if missing is not None:
                self._error(msg_id, -32602, f"invalid params: info.{missing} is required")
                return
            result = self._initialize_result()
            result["protocolVersion"] = 2
            self._reply(msg_id, result)
            return
        super()._handle_request(method, msg_id, params)

    @staticmethod
    def _missing_info_field(info: Any) -> str | None:
        if not isinstance(info, dict):
            return "<object>"
        if not isinstance(info.get("name"), str):
            return "name"
        if not isinstance(info.get("version"), str):
            return "version"
        return None


def main() -> None:
    RouterRequiresInfoAgent().run()


if __name__ == "__main__":
    main()
