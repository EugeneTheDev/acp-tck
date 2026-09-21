#!/usr/bin/env python3
"""Conforming fixture: the turn-ending idle carries a `stopReason` of `"_tck/throttled"` -- a
`_`-prefixed, implementation-specific extension value, legal per the open-enum extensibility
rule (`tck.v2.protocol.is_valid_open_enum_value`).

Must PASS every V2-2a requirement, including `ACP-STATE-203` -- this is the positive control
proving the `_`-prefix rule itself, paired with `bad_stop_reason.py`'s negative control (a
non-`_`-prefixed, non-defined value, which FAILs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402


class VendorStopReasonAgent(ConformingAgent):
    def _stop_reason(self) -> str:
        return "_tck/throttled"


def main() -> None:
    VendorStopReasonAgent(capabilities={"session": {}}).run()


if __name__ == "__main__":
    main()
