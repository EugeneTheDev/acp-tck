#!/usr/bin/env python3
"""A defect fixture for ACP-MODES-002: advertises `modes` and, on `session/set_mode`, emits a
`current_mode_update` notification that uses the docs-bug field name `modeId` instead of the
schema-true `currentModeId` -- the notification is otherwise well-formed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

MODES = {
    "currentModeId": "default",
    "availableModes": [
        {"id": "default", "name": "Default"},
        {"id": "yolo", "name": "YOLO"},
    ],
}


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-mode-update-uses-modeId",
        modes=dict(MODES),
        emit_mode_update=True,
        mode_update_field="modeId",
    ).run()


if __name__ == "__main__":
    main()
