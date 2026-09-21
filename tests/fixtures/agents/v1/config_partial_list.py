#!/usr/bin/env python3
"""A defect fixture for ACP-CONFIG-002: `session/set_config_option` responds with only the
changed option, instead of the complete `configOptions` list the spec requires.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

CONFIG_OPTIONS = [
    {
        "id": "model",
        "name": "Model",
        "type": "select",
        "currentValue": "fast",
        "options": [
            {"value": "fast", "name": "Fast"},
            {"value": "slow", "name": "Slow"},
        ],
    },
    {
        "id": "theme",
        "name": "Theme",
        "type": "select",
        "currentValue": "light",
        "options": [
            {"value": "light", "name": "Light"},
            {"value": "dark", "name": "Dark"},
        ],
    },
]


class PartialListAgent(ConformingAgent):
    def _handle_set_config_option(self, msg_id: Any, params: dict[str, Any]) -> None:
        config_id = params.get("configId")
        value = params.get("value")
        changed = None
        for option in self._config_options or []:
            if option.get("id") == config_id:
                option["currentValue"] = value
                changed = option
                break
        # Defect: only the changed option, not the complete list.
        self._reply(msg_id, {"configOptions": [changed] if changed else []})


def main() -> None:
    PartialListAgent(
        agent_name="tck-fixture-config-partial-list",
        config_options=[dict(opt) for opt in CONFIG_OPTIONS],
    ).run()


if __name__ == "__main__":
    main()
