#!/usr/bin/env python3
"""Positive control: sends a `_`-prefixed custom agent -> client method mid-turn -- legal per
the open-enum extensibility rule, since custom methods MUST begin with `_` (mirrors v1's
`_tck/...`-prefixed probe convention).

`ACP-CLIENTCAP-202`'s check is `not in known methods and not _-prefixed`, so a `_`-prefixed
method never trips it (paired with `calls_fs_unadvertised.py`'s negative control).
`ACP-CLIENTCAP-201` is unaffected (not `elicitation/create`).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import SendsClientRequestAgent  # noqa: E402


class CallsCustomMethodAgent(SendsClientRequestAgent):
    def _client_request_method(self) -> str:
        return "_tck/ping"

    def _client_request_params(self, session_id: Any) -> dict[str, Any]:
        return {"sessionId": session_id}


def main() -> None:
    CallsCustomMethodAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
