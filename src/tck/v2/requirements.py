"""ACP v2 (Draft) requirement registry.

Slice V2-1b expands the skeleton's two `initialize`-only requirements into full initialize/
negotiation/capabilities coverage plus the first `session/new` requirements. Full session-
lifecycle/prompt coverage (mirroring `tck.v1.requirements`'s breadth) is deferred to later v2
slices -- see `.agents/plan.md`'s slice order.

## `ACP-INIT-001` vs `ACP-INIT-201`: id-namespacing decision (D3, `.agents/plan.md`)

Two candidate requirements were considered against v1's `_DECLARATIONS`:

- The "`initialize` succeeds" check is the *same* requirement v1's `ACP-INIT-001` already names
  (only the cited spec source changes, from v1's initialization.mdx to v2's) -- so it keeps the
  `ACP-INIT-001` id, re-cited below, per D3's "reuse only if the v2 requirement is truly the
  same". Unlike v1 (where every agent under test necessarily speaks the one version the whole
  suite targets), v2's `ACP-INIT-001` was narrowed to *only* the non-error-result check (schema
  validation moved to `ACP-SCHEMA-001`) after a review found that judging a v1-shaped result
  against v2 schema rules mischaracterizes an agent that merely negotiated down honestly as
  "broken" -- see "Version-mismatch-aware v2-shape rows" below.
- v1's `ACP-INIT-002` text is "When the client requests protocol version 1, the agent returns
  1." -- a strict single-branch equality that only makes sense because a v1-only TCK only ever
  requests version 1. The v2 analogue is *not* that text: the v2 negotiation rule
  (initialization.mdx:92-96) is "if the Agent supports the requested version, respond with the
  same version; otherwise, respond with its own latest supported version" -- a two-branch rule,
  because a v2-requesting TCK's request can legitimately be answered with a *lower* version by an
  agent that does not yet support v2. Since the text does not match, this does NOT reuse
  `ACP-INIT-002` -- it is `ACP-INIT-201` instead, per D3's explicit fallback.

## V2-1b additions: id-namespacing decisions

- `ACP-INIT-003` (reused from v1): the unsupported-version (`65535`) probe -- "the agent responds
  with a successful result whose `protocolVersion` is not the literal unsupported request,
  echoed back" -- is the *same* requirement v1's `ACP-INIT-003` names, only re-cited to v2's
  negotiation text and given a v2-shaped probe (`info` required on the request in v2, not just a
  router-trap courtesy as in v1). Reused per D3's explicit example
  (`.agents/research/acp-v2-version-negotiation.md` requirement 10, case table row `N > M`).
  This does not duplicate `ACP-INIT-201`'s own internal 65535 probe: the two ids assert different
  consequences of the same negotiation rule, exactly mirroring how v1 keeps `ACP-INIT-002`
  ("requested-supported version echoed") and `ACP-INIT-003` ("requested-unsupported version
  answered with the agent's own latest, not echoed") as two separate ids rather than one merged
  test. A defect fixture that unconditionally echoes any requested version therefore correctly
  fails *both* `ACP-INIT-003` and `ACP-INIT-201` -- an expected, documented cascade, not a
  design flaw.
- `ACP-INIT-202` (new): the "downgrade" case of the same negotiation rule --
  `protocolVersion: 1` requested against a v2-only (or dual-version) agent must still produce a
  successful result (never a JSON-RPC error), whose value is `1` or `2`
  (`.agents/research/acp-v2-version-negotiation.md` requirement 10, case table row
  `N < min(S)`). The research report itself flags this row's tier as debatable (both reference
  SDKs' *strict* v2 endpoints violate the MUST by construction) and recommends ADVISORY, but the
  task for this slice explicitly calls for MANDATORY with a hard FAIL on error or on any other
  value -- honoring the spec's own unambiguous MUST text rather than the reference
  implementations' convenience shortcut (the same posture this repo already takes for
  `ACP-INIT-003`, which also has both reference SDKs on the "fails" side of its own documented
  cross-check baseline).
- `ACP-INIT-203` (new): `info` is REQUIRED in the v2 `initialize` result (v1's `agentInfo` was
  optional/ADVISORY) -- a genuine tier promotion, not the same requirement text as v1's
  ADVISORY `ACP-INIT-004`, so it gets its own id rather than reusing that one.
- `ACP-INIT-204` (new): every v2 capability marker is object-encoded, never boolean -- a
  dedicated diagnostic id so a defect fixture that sends `"session": true` has a specific,
  documented FAIL target, even though the same defect is *also* caught by `ACP-SCHEMA-001`'s
  general schema validation (`ACP-INIT-001` no longer duplicates that check -- see below). This
  id exists purely for report legibility, per the source report's own "keep as separate row only
  if a clearer diagnostic is wanted" framing
  (`.agents/research/acp-v2-initialize-capabilities-baseline.md` §7) and the task's explicit
  request for a dedicated row + defect fixture; the cascade into `ACP-SCHEMA-001` is expected and
  documented on the fixture itself.
- `ACP-SCHEMA-001` (reused from v1): "every agent message validates against the schema" is the
  same requirement, re-cited to the v2 schema; this slice scopes its test to the `initialize`
  exchange only (no `session/new`/`session/prompt` traffic yet -- those extend the same test in
  a later slice once the v2 prompt driver exists).

## Version-mismatch-aware v2-shape rows

`ACP-INIT-203`, `ACP-INIT-204`, and `ACP-SCHEMA-001` all judge the *shape* of the `initialize`
result against v2-only rules (`info` REQUIRED, object-only capability markers, the v2 schema
itself). An agent that honestly negotiates down to a version other than 2 (per `ACP-INIT-201`'s
two-branch rule -- e.g. a v1-only agent answering `1` to a v2 client) never claimed its result
was v2-shaped, so FAILing these rows against it would misleadingly report "this agent is
broken" when it merely does not speak v2 yet. Each of these three tests therefore calls
`tck.v2.conformance._helpers.skip_if_version_mismatch(init_result)` explicitly right after it has
its own `initialize` result in hand, SKIPping with the `VERSION-MISMATCH:` marker (which flags
the run `Verdict.blocked_by_version_mismatch`, forcing it NOT CONFORMANT regardless -- see
`tck.common.report`/`tck.common.plugin`) instead of FAILing. `ACP-INIT-001` (non-error result
only) and the negotiation rows `ACP-INIT-003`/`ACP-INIT-201`/`ACP-INIT-202` (which assert only on
the negotiation *outcome*, never on the result's shape) are judged normally either way and do
not call this helper -- an honest downgrade is not itself a negotiation defect.

This mirrors, but does not reuse, `tck.common.plugin`'s `_tck_capability_gate` autouse fixture:
that fixture only runs for `@pytest.mark.capability(...)`-marked tests sharing the session-scoped
`agent_initialize_result` fixture (e.g. `ACP-SESSION-001`/`002`, gated on `capabilities.session`)
-- every test in `test_initialize.py` spawns its own fresh process and sends its own
`initialize`, so there is no shared fixture for an autouse hook to gate on, and the check has to
be called explicitly instead.
- `ACP-SESSION-001`/`ACP-SESSION-002` (reused from v1): "`session/new` succeeds with a unique,
  non-empty string `sessionId` and the response validates" / "two calls return distinct ids" are
  the same requirements, re-cited to v2's `session/new` contract (`cwd`-only required params,
  `sessionId`-only required response -- `mcpServers` is optional in v2, unlike v1). Both are
  `Tier.CAPABILITY` here (gated on `capabilities.session`, since v2's session surface is
  opt-in), whereas v1 registers them `Tier.MANDATORY` -- this is fine because v1 and v2 keep
  fully separate `REGISTRY` dicts (`.agents/plan.md` D1), so the same id string can carry a
  different tier in each without conflict.
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
            "`initialize` succeeds with a non-error JSON-RPC result. Judged the same "
            "regardless of the negotiated `protocolVersion` -- unlike `ACP-INIT-203`/"
            "`ACP-INIT-204`/`ACP-SCHEMA-001`, this row does not SKIP on a version mismatch, "
            "since a MUST-succeed handshake applies even to an agent that honestly negotiates "
            "down to a version other than 2. Schema/shape validation of the result -- "
            "including v2-only requirements -- lives in `ACP-SCHEMA-001`."
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
    Requirement(
        id="ACP-INIT-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "An unsupported-version probe (`protocolVersion: 65535`) still succeeds, and the "
            "returned `protocolVersion` is not the literal unsupported request echoed back -- "
            "it is at least the agent's own latest supported version (as observed from a "
            "reference `protocolVersion: 2` request on the same agent)."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:94 (second clause); "
            "acp-v2-version-negotiation.md requirement 10, case table row `N > M`"
        ),
        source_report="acp-v2-version-negotiation.md",
    ),
    Requirement(
        id="ACP-INIT-202",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A downgrade probe (`protocolVersion: 1`) still succeeds -- never a JSON-RPC error "
            "-- and the returned `protocolVersion` is `1` or `2` (the agent's own latest "
            "supported version when it does not support `1`)."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:94,96; "
            "acp-v2-version-negotiation.md requirement 10, case table row `N < min(S)`"
        ),
        source_report="acp-v2-version-negotiation.md",
    ),
    Requirement(
        id="ACP-INIT-203",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The `initialize` result's `info` is present and is an object with non-empty "
            "string `name` and `version` (`title` optional, may be `null`) -- REQUIRED in v2, "
            "unlike v1's optional `agentInfo`. A v2-only shape requirement: SKIPPED with a "
            "`VERSION-MISMATCH` note whenever the agent honestly negotiated down to a version "
            "other than 2, since it never claimed its result was v2-shaped."
        ),
        citation=_cite(
            "schema/v2/schema.json:3052-3058,3086,3097-3122; "
            "docs/protocol/v2/initialization.mdx:248"
        ),
        source_report="acp-v2-version-negotiation.md",
    ),
    Requirement(
        id="ACP-INIT-204",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "When the `initialize` result's `capabilities` is present, it is an object, and "
            "every known capability marker within it (`session`, `auth`, and their known "
            "nested keys) is either absent/`null` or an object -- never a boolean. There are no "
            "boolean-encoded capabilities anywhere in v2. A v2-only shape requirement: SKIPPED "
            "with a `VERSION-MISMATCH` note whenever the agent honestly negotiated down to a "
            "version other than 2."
        ),
        citation=_cite(
            "docs/protocol/v2/migration.mdx:181; schema/v2/schema.json:3123-3158 "
            "(AgentCapabilities), :3159-3218 (SessionCapabilities) -- all `type: \"object\"`"
        ),
        source_report="acp-v2-initialize-capabilities-baseline.md",
    ),
    Requirement(
        id="ACP-SCHEMA-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every message the agent emits during the `initialize` exchange validates against "
            "the vendored v2 schema. A v2-only shape requirement: SKIPPED with a "
            "`VERSION-MISMATCH` note whenever the agent honestly negotiated down to a version "
            "other than 2, since a v1-shaped result cannot be judged against the v2 schema."
        ),
        citation=_cite("schema/v2/schema.json (top-level anyOf); docs/protocol/v2/initialization.mdx"),
        source_report="acp-v2-initialize-capabilities-baseline.md",
    ),
    Requirement(
        id="ACP-SESSION-001",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/new` with an absolute `cwd` and no `mcpServers` succeeds with a "
            "non-empty string `sessionId`, and the response validates against the v2 schema."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:69; schema/v2/schema.json:6011-6051 "
            "(required:[\"cwd\"]), :3627-3658 (required:[\"sessionId\"])"
        ),
        source_report="acp-v2-session-management.md",
    ),
    Requirement(
        id="ACP-SESSION-002",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text="Two `session/new` calls on one connection return distinct `sessionId`s.",
        citation=_cite("docs/protocol/v2/session-setup.mdx:69,306; schema/v2/schema.json:597"),
        source_report="acp-v2-session-management.md",
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
