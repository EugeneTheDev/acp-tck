#!/usr/bin/env python3
"""Non-conforming fixture: advertises `capabilities.session.prompt.{image,audio,
embeddedContext}` (all three), but rejects any `session/prompt` whose blocks include an `image`
content block with a JSON-RPC error, instead of accepting it as advertised.

FAILs exactly `ACP-PROMPTCAP-001`. `ACP-PROMPTCAP-002`/`003` PASS -- audio/resource blocks are
still accepted normally, and both capabilities are advertised so those tests actually run
(rather than SKIPping).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class RejectsImageWhenAdvertisedAgent(ConformingAgent):
    def _prompt_rejection(self, prompt: list[Any]) -> tuple[int, str] | None:
        for block in prompt:
            if isinstance(block, dict) and block.get("type") == "image":
                return -32602, "image content is not actually supported by this agent"
        return None


def main() -> None:
    RejectsImageWhenAdvertisedAgent(
        capabilities={
            "session": {
                "prompt": {"image": {}, "audio": {}, "embeddedContext": {}},
            },
        }
    ).run()


if __name__ == "__main__":
    main()
