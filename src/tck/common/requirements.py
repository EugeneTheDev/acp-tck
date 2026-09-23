"""Version-agnostic requirement registry machinery.

`Tier` and `Requirement` carry no protocol content -- each ACP version (`tck.v1`, `tck.v2`)
declares its own `_DECLARATIONS`/`REGISTRY` built from these types, citing that version's own
spec revision. Each version calls `make_cite(SPEC_REVISION)` once to get its own citation
helper bound to its own revision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    MANDATORY = "MANDATORY"
    CAPABILITY = "CAPABILITY"
    ADVISORY = "ADVISORY"
    INFORMATIONAL = "INFORMATIONAL"


@dataclass(frozen=True)
class Requirement:
    """One conformance requirement the TCK can test for.

    `capability` is a JSON path under the `initialize` result (e.g.
    `agentCapabilities.loadSession`) that gates whether the requirement even applies; it is
    required iff `tier is Tier.CAPABILITY` and must be `None` otherwise.
    """

    id: str
    tier: Tier
    capability: str | None
    text: str
    citation: str

    def __post_init__(self) -> None:
        if self.tier is Tier.CAPABILITY and not self.capability:
            raise ValueError(f"{self.id}: tier is CAPABILITY but no capability path was given")
        if self.tier is not Tier.CAPABILITY and self.capability is not None:
            raise ValueError(f"{self.id}: tier is {self.tier.value}, not CAPABILITY, but capability={self.capability!r}")


def make_cite(revision: str) -> Callable[[str], str]:
    """Return a `_cite`-style helper bound to `revision`, for a version's own `_DECLARATIONS`."""

    def _cite(path_and_lines: str) -> str:
        return f"{path_and_lines} @ {revision}"

    return _cite
