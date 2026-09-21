"""ACP v2 (Draft) requirement registry.

This is the skeleton slice's registry: exactly two requirements, both about `initialize`. Full
initialize/capabilities/session coverage (mirroring `tck.v1.requirements`'s breadth) is deferred
to the next v2 slice -- see `.agents/plan.md`'s slice order.

## `ACP-INIT-001` vs `ACP-INIT-201`: id-namespacing decision (D3, `.agents/plan.md`)

Two candidate requirements were considered against v1's `_DECLARATIONS`:

- The "`initialize` succeeds and the result validates against the schema, with an integer
  `protocolVersion`" check is the *same* requirement v1's `ACP-INIT-001` already names (only the
  cited spec source and schema `$def` line numbers change, from v1's initialization.mdx/schema.json
  to v2's) -- so it keeps the `ACP-INIT-001` id, re-cited below, per D3's "reuse only if the v2
  requirement is truly the same".
- v1's `ACP-INIT-002` text is "When the client requests protocol version 1, the agent returns
  1." -- a strict single-branch equality that only makes sense because a v1-only TCK only ever
  requests version 1. The v2 analogue is *not* that text: the v2 negotiation rule
  (initialization.mdx:92-96) is "if the Agent supports the requested version, respond with the
  same version; otherwise, respond with its own latest supported version" -- a two-branch rule,
  because a v2-requesting TCK's request can legitimately be answered with a *lower* version by an
  agent that does not yet support v2. Since the text does not match, this does NOT reuse
  `ACP-INIT-002` -- it is `ACP-INIT-201` instead, per D3's explicit fallback.
"""

from __future__ import annotations

from ..common.requirements import Requirement, Tier, make_cite
from .protocol import SCHEMA_REVISION

SPEC_REVISION = SCHEMA_REVISION
_cite = make_cite(SPEC_REVISION)

_DECLARATIONS: tuple[Requirement, ...] = (
    Requirement(
        id="ACP-INIT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "`initialize` succeeds and the result validates against the v2 schema, with an "
            "integer `protocolVersion`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:24,47; schema/v2/schema.json $defs/"
            "InitializeResponse"
        ),
        source_report="acp-v2-initialize-capabilities-baseline.md",
    ),
    Requirement(
        id="ACP-INIT-201",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The result's `protocolVersion` is an integer, and the negotiated value is either "
            "the requested `2`, or -- if the agent does not support `2` -- the agent's own "
            "latest supported version (never something else, and never the literal request "
            "echoed back unconditionally)."
        ),
        citation=_cite("docs/protocol/v2/initialization.mdx:92-96"),
        source_report="acp-v2-initialize-capabilities-baseline.md",
    ),
)

REGISTRY: dict[str, Requirement] = {requirement.id: requirement for requirement in _DECLARATIONS}


def get(requirement_id: str) -> Requirement:
    """Look up a requirement by id, raising a helpful `KeyError` if it is not registered."""
    try:
        return REGISTRY[requirement_id]
    except KeyError:
        raise KeyError(
            f"{requirement_id!r} is not a registered requirement id; known ids: "
            f"{sorted(REGISTRY)}"
        ) from None
