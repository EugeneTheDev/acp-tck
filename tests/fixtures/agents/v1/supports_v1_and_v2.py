#!/usr/bin/env python3
"""Conforming fixture: legitimately supports two protocol versions. Returns `1` when the
client requests exactly `1`, and `2` for anything else (including the TCK's unsupported-version
probe, 65535) -- i.e. "its own latest supported version" is genuinely higher than its v1
answer.

Exists as a self-test canary for ACP-INIT-003's `!= 65535 and >= latest_supported` rule: a
naive equality rule (`version == latest_supported`) would falsely FAIL this agent even though it
never echoes 65535 verbatim and never answers lower than its v1 answer. Must PASS INIT-003.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class SupportsV1AndV2Agent(ConformingAgent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(agent_name="tck-fixture-supports-v1-and-v2", **kwargs)

    def _handle_request(self, method: str, msg_id: Any, params: dict[str, Any]) -> None:
        if method == "initialize":
            self._client_capabilities = params.get("clientCapabilities") or {}
            requested = params.get("protocolVersion")
            version = 1 if requested == 1 else 2
            result = self._initialize_result()
            result["protocolVersion"] = version
            self._reply(msg_id, result)
            return
        super()._handle_request(method, msg_id, params)


def main() -> None:
    SupportsV1AndV2Agent().run()


if __name__ == "__main__":
    main()
