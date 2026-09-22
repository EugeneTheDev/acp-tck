#!/usr/bin/env python3
"""A defect fixture for ACP-AUTH-201 (ADVISORY): advertises two `authMethods` entries sharing
the same `methodId`. No v1 analogue -- new fixture for this slice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"methodId": "dup", "type": "agent", "name": "First"},
    {"methodId": "dup", "type": "agent", "name": "Second"},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-duplicate-method-id",
        auth_methods=AUTH_METHODS,
    ).run()


if __name__ == "__main__":
    main()
