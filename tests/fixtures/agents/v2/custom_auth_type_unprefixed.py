#!/usr/bin/env python3
"""A defect fixture for ACP-AUTH-206 (MANDATORY): advertises an `authMethods` entry whose `type`
is neither `"agent"` nor `"terminal"` nor `_`-prefixed -- violating the open-enum extensibility
rule (`docs/protocol/v2/authentication.mdx:120-122`). No v1 analogue: v1 had no closed/open enum
rule on this field at all.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

AUTH_METHODS = [
    {"methodId": "custom", "type": "sso", "name": "Custom SSO"},
]


def main() -> None:
    ConformingAgent(
        agent_name="tck-fixture-custom-auth-type-unprefixed",
        auth_methods=AUTH_METHODS,
    ).run()


if __name__ == "__main__":
    main()
