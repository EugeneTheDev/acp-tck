#!/usr/bin/env python3
"""Conforming fixture: the `initialize` result advertises `capabilities.providers: {}` --
a root key of `AgentCapabilities` that only the Draft `schema.unstable.json` defines (RFD
`docs/rfds/custom-llm-endpoint.mdx`), not `schema.json`. This is not a vendor extension; it is a
real, spec-typed field of an unstable RFD, so `ACP-EXT-202` must not flag it as an unrecognized
`capabilities` root key. Everything else stays the plain baseline, so this fixture FAILs nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


def main() -> None:
    ConformingAgent(capabilities={"session": {}, "providers": {}}).run()


if __name__ == "__main__":
    main()
