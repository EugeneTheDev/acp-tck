#!/usr/bin/env python3
"""A defect fixture for ACP-CONFIG-003: advertises a `type: "boolean"` config option
unconditionally, even to a client that never advertised
`clientCapabilities.session.configOptions.boolean` (Req 33's MUST NOT).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CONFIG_OPTIONS = [
    {
        "id": "verbose",
        "name": "Verbose",
        "type": "boolean",
        "currentValue": False,
    },
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-boolean-option-unadvertised",
        config_options=[dict(opt) for opt in CONFIG_OPTIONS],
        ignore_boolean_gating=True,
    ).run()


if __name__ == "__main__":
    main()
