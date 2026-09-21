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

## V2-2a additions: the mock-client prompt driver and the core prompt-turn requirements

All six rows below are `Tier.CAPABILITY`, `capability="capabilities.session"` -- **not**
`Tier.MANDATORY` (corrected after review; see `.agents/plan.md` "v2 initialize / capabilities /
baseline -- decisions" and `acp-v2-initialize-capabilities-baseline.md`). In v2 only
`initialize` itself is unconditionally required; `session/prompt` is part of the seven-method
baseline (`session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`,
`session/cancel`, `session/update`) an agent commits to by advertising `capabilities.session` at
all, exactly like `ACP-SESSION-001`/`002` above -- a MANDATORY row that legitimately SKIPs for
every non-session agent would misrepresent the tier in the summary table. Each still carries the
test's own `@pytest.mark.capability("capabilities.session")` marker (the normal, and now
tier-consistent, way `tck.common.plugin._tck_capability_gate` wires a CAPABILITY row's SKIP
behavior -- see `ACP-SESSION-001`/`002`).

- `ACP-PROMPT-205` (new id, **not** a reuse of v1's `ACP-PROMPT-002`): "every `session/update`
  the agent emits validates against the schema and carries the prompted `sessionId`" is the same
  requirement *text* v1's `ACP-PROMPT-002` names, re-cited to v2's `session/update` envelope
  (`UpdateSessionNotification`, required `sessionId`+`update`) and the 17-variant `SessionUpdate`
  union, per `.agents/research/acp-v2-prompt-lifecycle.md` requirement U1 and its own suggested
  table row -- but the *tier* differs (v1: `Tier.MANDATORY`; v2: `Tier.CAPABILITY`, since v2's
  session surface is opt-in and v1's is not), and D3's reuse rule is about the whole requirement,
  tier included, not text alone. A changed tier is a changed requirement, so this needed a fresh
  2xx id rather than reusing `ACP-PROMPT-002`; picked `205` specifically to avoid colliding with
  the research report's own already-reserved `ACP-PROMPT-202` (acceptance-before-idle ordering)
  and `ACP-PROMPT-204` (distinct `messageId`s across turns), both still out of scope below.
  Vacuous pass if the agent emits no updates during the turn.
- `ACP-PROMPT-201` (new): the `session/prompt` response is an object with a non-empty string
  `messageId` -- the acceptance-receipt shape that replaces v1's turn-result response entirely
  (no `stopReason` here at all; that moved to `ACP-STATE-203`). Research table row
  `ACP-PROMPT-201`.
- `ACP-PROMPT-203` (new): the agent echoes the inserted user message -- a `user_message` update
  (with `content`) or at least one `user_message_chunk` update -- carrying the **same**
  `messageId` as the `session/prompt` response, for the prompted session. Research table row
  `ACP-PROMPT-203` (`ACP-PROMPT-202`, the response-before-idle ordering row, and `ACP-PROMPT-204`,
  the distinct-`messageId`s-across-turns row, are both out of this slice's explicit task list --
  left for a follow-up).
- `ACP-STATE-201` (new): if a turn-ending idle `state_update` (one carrying a `stopReason`) is
  observed for the prompted session, a `state_update {state: "running"}` for that session must
  have been observed *earlier in the same turn*. Gated on the idle, not on `running` itself:
  SKIPPED as "no turn-ending idle observed" only when the turn never reached a stop-reason-
  bearing idle at all (e.g. it timed out first, or ended on a bare idle with no `stopReason`); a
  turn whose idle *does* carry a `stopReason` but was never preceded by `running` is exactly the
  defect this row exists to catch, and FAILs -- this SKIP gate is deliberately *not* the same as
  `ACP-STATE-202`/`ACP-STATE-203` below, whose own gate is `running` not being observed (research
  table row `ACP-STATE-201`: "Vacuous if no stop-reason-bearing idle was seen (then
  `ACP-STATE-203` reports it)"; `.agents/plan.md` "v2 prompt lifecycle -- decisions"; inference
  §4 point 3). This SKIP is layered on top of, not instead of, the `capabilities.session` gate:
  a non-session agent SKIPs via the capability marker before ever reaching this row's own
  "no turn-ending idle observed" logic.
- `ACP-STATE-202` (new): after an accepted prompt for a session that *did* show `running`, an
  idle `state_update` for that session arrives within the turn's `--timeout` budget. Asserted
  only when `running` was observed; SKIPPED as "no foreground work observed" otherwise --
  `.agents/plan.md`: "assert only when `running` was observed; a turn that never shows `running`
  is recorded (property) and SKIPped ... the spec does not say whether a zero-work prompt must
  emit idle (open upstream question, do not guess)." Research table row `ACP-STATE-202`.
- `ACP-STATE-203` (new): the idle `state_update` that terminates an *observed* `running` turn
  carries a `stopReason`, and that value is one of the five defined constants or begins with `_`
  (`tck.v2.protocol.is_valid_open_enum_value`). `.agents/plan.md`'s explicit tier-resolution
  decision for the MUST-prose-vs-optional-schema conflict on presence
  (`.agents/research/acp-v2-patches-enums-extensibility.md`): "MANDATORY [construed as: normally
  required once the capability applies -- see the CAPABILITY-tier correction above], scoped to
  the idle that terminates an observed `running` turn; an unscoped 'every idle has a stopReason'
  check is forbidden." Folds in the separate value-legality check the prompt-lifecycle report
  lists as its own `ACP-STATE-204` row -- this slice's task list asked for one combined
  "turn-ending idle carries a *valid* `stopReason`" row, not two; a future slice may still split
  presence and value-legality into separate ids if a defect fixture needs the more precise
  diagnostic. SKIPPED as "no foreground work observed" (same gate as `ACP-STATE-202`) whenever
  `running` was never observed.

Deliberately **not** added in V2-2a (added below, in V2-2b, or -- for one id -- permanently
declined): `ACP-PROMPT-202` (acceptance-before-idle ordering, ADVISORY/race-skipped, still not
added -- out of this slice's task list too), `ACP-PROMPT-204` (distinct `messageId`s across
turns, still not added), `ACP-STATE-204`/`ACP-STATE-205` (as separate ids -- `204`'s content is
folded into `ACP-STATE-203` above; `205`, `state` value legality, still has no fixture/test
driving it and is not added below either), `ACP-STATE-206`/`ACP-STATE-207` (permission-driven
state transitions; post-idle update recording -- still not added), `ACP-MSG-201` (already fully
covered by `ACP-PROMPT-205`'s schema validation -- the research report itself says "keep a
separate id only for report legibility", which this repo permanently declines).

## V2-2b additions: prompt content capabilities, permission-request shape, the agent->client
## method rules, `ACP-PROMPT-003`, and two INFORMATIONAL prompt-lifecycle probes

Per `.agents/plan.md`'s "v2 tiering rule for session-baseline rows" (2026-09-21, slice V2-2a):
every one of the seven rows below is only ever observable during a `session/prompt` turn, which
itself only exists once the agent has advertised `capabilities.session` at all -- so
`ACP-PERM-201`, `ACP-CLIENTCAP-201`, and `ACP-CLIENTCAP-202` are `Tier.CAPABILITY`,
`capability="capabilities.session"`, exactly like `ACP-PROMPT-201`/`203`/`205` and
`ACP-STATE-201..203` above, **not** `Tier.MANDATORY` as the source report's own table suggests --
the report predates that tiering decision. `ACP-PROMPT-003` and the two INFORMATIONAL rows keep
`capability=None` on the `Requirement` itself (`Requirement.__post_init__`'s invariant: non-
`CAPABILITY` tiers must not carry a capability path), but their *tests* still carry
`@pytest.mark.capability("capabilities.session")` -- `tck.common.plugin._tck_capability_gate`
reads only the pytest marker, independent of the registered `Requirement`'s own tier, so a test
can SKIP on the marker even though its `Requirement` is ADVISORY/INFORMATIONAL.

- `ACP-PROMPTCAP-001`/`002`/`003` (reused from v1, new gate): "a prompt containing an
  `image`/`audio`/`resource` (embedded context) block alongside text is accepted and the turn
  reaches idle without a JSON-RPC error" is the same requirement v1's `ACP-PROMPTCAP-001..003`
  name, re-cited to v2's content-block shapes and gated on the **object-marker** capability
  paths `capabilities.session.prompt.image`/`.audio`/`.embeddedContext` -- v1 used a boolean gate
  (`agentCapabilities.promptCapabilities.*`, `boolean=True`), but v2 has no boolean-encoded
  capabilities anywhere (`ACP-INIT-204`), so the gate encoding changes without changing the
  requirement's own text/tier; D3 treats a gate-encoding change (not a tier change) as still the
  same requirement, so these ids are reused. Assertion target changes from v1's "valid
  `stopReason` in the response" to v2's turn shape: a non-error acceptance receipt, which -- per
  `run_prompt`'s own turn-end predicate -- is only returned once the turn has also reached an
  idle (see `test_prompt.py`'s `ACP-PROMPT-201` precedent for why no separate idle assertion is
  needed here).
- `ACP-PROMPT-003` (reused from v1, unchanged tier): "a prompt of `text` + `resource_link` is
  accepted, and the turn completes" is the same requirement text and tier (ADVISORY) v1's
  `ACP-PROMPT-003` names -- the v1/v2 doc conflict (`initialization.mdx:203`'s "MUST support
  `text` and `resource_link`" vs `content.mdx:33`'s "MUST support text[-only]") survives
  verbatim into v2 (research report's own "Discrepancy 2"), so this reuses the id per D3 (same
  text, same tier, only the citation moves to v2 sources).
- `ACP-PERM-201` (new id): any `session/request_permission` the agent sends during a turn
  validates -- `sessionId`, non-empty `title`, `options` with >=1 entry, each option carrying
  `optionId`/`name`/`kind` -- and, once the client answers with a `selected` outcome, the turn
  still reaches an idle. New id (no v1 counterpart at all: v1's `PermissionOption`/params shape
  differs, has no `title`) in the `PERM` area the research report itself proposes. Tiered
  `Tier.CAPABILITY` per the session-baseline rule above (report's own table suggests MANDATORY
  "vacuous when unseen" -- superseded). SKIPs "no permission request observed" whenever the
  fixture agent's turn never sends one at all, rather than treating that as either a PASS or a
  FAIL -- the send itself is only MAY (`prompt-lifecycle.mdx:369`, research row C1), so there is
  nothing to validate against for an agent that simply never asks.
- `ACP-CLIENTCAP-201` (new id): with a mock client advertising no `capabilities.elicitation.*`
  mode, no `elicitation/create` request is observed during a prompt turn (Req C5's MUST NOT).
  New id (v1 has no elicitation capability or method at all). `Tier.CAPABILITY` per the
  session-baseline rule (report's table suggests MANDATORY -- superseded).
- `ACP-CLIENTCAP-202` (new id): every agent->client request/notification method observed during
  a prompt turn is a member of v2's client method inventory (`CLIENT_METHODS`) or a
  bidirectional protocol-level method (`PROTOCOL_METHODS`, e.g. `$/cancel_request`), or begins
  with `_` (custom extension methods, Req 42/extensibility.mdx). This is the v2 **collapse** of
  v1's three separate `ACP-CLIENTCAP-001/002/003` fs/terminal/elicitation rows into one: v2 has
  no `fs/*`/`terminal/*` methods at all (Req C7 -- they were removed, not merely capability-
  gated), so "calling one" is simply "calling an undefined method", indistinguishable from any
  other made-up non-`_` method name; `elicitation/create`'s own capability-gated negative is
  `ACP-CLIENTCAP-201` above, not duplicated here (an unadvertised elicitation call IS a defined
  method, so it would otherwise pass this row's check trivially). New id (the fs/terminal
  collapse means the requirement text is not the same as any single v1 id). Ownership: per
  `.agents/plan.md`'s "v2 effort -- slices" list (the final, dated slice order), `ACP-CLIENTCAP-
  201`+`202` are both owned by the V2-2 (prompt-lifecycle) slice, not the initialize/capabilities
  slice -- an earlier draft decision in the same plan file suggesting the opposite ownership
  predates that final ordering and is superseded by it. `Tier.CAPABILITY` per the session-
  baseline rule (report's table suggests MANDATORY -- superseded).
- `ACP-INFO-CONCURRENT-001` (new id, INFORMATIONAL): records what the agent does when a second
  `session/prompt` for the same session is sent before the first has reached its terminating
  idle -- accepted, a JSON-RPC error, or silence -- and never asserts on it: concurrency is
  explicitly out of scope of the v2 design (research row X1, `docs/rfds/v2/prompt.mdx:86`: "This
  RFD does not specify queueing, steering, or whether agents insert new prompts while busy").
- `ACP-INFO-UNKNOWNSESSION-001` (reused from v1, INFORMATIONAL): records the agent's response to
  `session/prompt` with a `sessionId` it never created, never asserting on it -- same
  requirement v1's id names (spec silence on the error code), re-cited: v2's own `error.mdx` is
  still "Documentation coming soon" (research row X2), so the code remains unspecified in v2
  too.

Deliberately **not** added this slice, per the already-recorded, explicit supersession in
`.agents/plan.md`'s "v2 patches / open enums / extensibility -- decisions": custom `sessionUpdate`
values MUST begin with `_`; an unknown *non*-`_`-prefixed discriminator is a MANDATORY FAIL, not
an INFORMATIONAL probe -- so `ACP-INFO-V2UNKNOWNUPDATE-001` (the research report's own suggested
INFORMATIONAL row for this) is never added at all, in this slice or later; the MANDATORY
`ACP-ENUM-20x` check that supersedes it is explicitly slotted into slice V2-6.
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
    Requirement(
        id="ACP-PROMPT-205",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every `session/update` notification the agent emits during a `session/prompt` "
            "turn validates against the v2 schema and carries the prompted `sessionId`. "
            "Vacuous pass if the agent emits no updates during the turn. NOT a reuse of v1's "
            "`ACP-PROMPT-002` under D3: the requirement text is the same schema/sessionId "
            "check, but the *tier* differs -- v1 registers it `Tier.MANDATORY` (v1's whole "
            "session surface is unconditional), whereas v2's `session/prompt` only exists once "
            "the agent has advertised the optional `capabilities.session` at all, exactly like "
            "`ACP-SESSION-001`/`002` above, so this row is `Tier.CAPABILITY`. A changed tier is "
            "a changed requirement under D3's reuse rule, so this gets a fresh 2xx id "
            "(`ACP-PROMPT-205`, not the already-reserved `ACP-PROMPT-202`/`204` -- see the "
            "research report's own id table) instead of reusing `ACP-PROMPT-002`."
        ),
        citation=_cite(
            "schema/v2/schema.json:4269 (UpdateSessionNotification, required "
            "[\"sessionId\",\"update\"]), :4300 (SessionUpdate union)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PROMPT-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The `session/prompt` result is a non-error object carrying a non-empty string "
            "`messageId` -- the acceptance receipt sent at insertion time, not a turn result "
            "(there is no `stopReason` here at all in v2)."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:124-127; schema/v2/schema.json:4097 "
            "(PromptResponse, required [\"messageId\"]), :4120 (MessageId = string)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PROMPT-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The agent reports the inserted user message via a `user_message` update or at "
            "least one `user_message_chunk` update, carrying the same `messageId` as the "
            "`session/prompt` response, for the prompted session -- before or after the "
            "response, no later than the turn-ending idle."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:129; docs/protocol/v2/migration.mdx:261; "
            "schema/v2/schema.json:4767 (UserMessage), :4738 (ContentChunk)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-STATE-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "If a turn-ending idle `state_update` (one carrying a `stopReason`) is observed "
            "for the prompted session, a `state_update {state: \"running\"}` for that session "
            "was observed earlier in the same turn. SKIPPED as 'no turn-ending idle observed' "
            "only when the turn never reached a stop-reason-bearing idle at all -- unlike "
            "`ACP-STATE-202`/`ACP-STATE-203`, this row's SKIP gate is the idle, not `running`; "
            "a turn-ending idle with no preceding `running` FAILs this row rather than "
            "SKIPping it."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:159,348 (inference); "
            "docs/protocol/v2/migration.mdx:278"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-STATE-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "After an accepted prompt for a session that showed `state_update "
            "{state: \"running\"}`, an idle `state_update` for that session arrives within the "
            "turn's timeout budget. Asserted only when `running` was observed; SKIPPED as 'no "
            "foreground work observed' otherwise."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:348; docs/protocol/v2/migration.mdx:282"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-STATE-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The idle `state_update` that terminates an observed `running` turn carries a "
            "`stopReason`, and its value is one of the five defined constants (`end_turn`, "
            "`max_tokens`, `max_turn_requests`, `refusal`, `cancelled`) or begins with `_`. "
            "CAPABILITY (gated on `capabilities.session`), scoped to the idle that terminates "
            "an observed `running` turn -- an unscoped 'every idle has a stopReason' check is "
            "forbidden. SKIPPED as 'no foreground work observed' (same gate as "
            "`ACP-STATE-202`) when `running` was never observed."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:348,464-481; schema/v2/schema.json:4904 "
            "(IdleStateUpdate), :4869 (StopReason); docs/protocol/v2/extensibility.mdx:113-118"
        ),
        source_report="acp-v2-patches-enums-extensibility.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-001",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.image",
        text=(
            "A prompt containing an `image` content block alongside text is accepted (a "
            "non-error `session/prompt` result), and the turn reaches idle, when the agent "
            "advertises `capabilities.session.prompt.image`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1194 (ImageContent)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-002",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.audio",
        text=(
            "A prompt containing an `audio` content block alongside text is accepted (a "
            "non-error `session/prompt` result), and the turn reaches idle, when the agent "
            "advertises `capabilities.session.prompt.audio`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1238 (AudioContent)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-003",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.embeddedContext",
        text=(
            "A prompt containing a `resource` (embedded context) content block alongside text "
            "is accepted (a non-error `session/prompt` result), and the turn reaches idle, "
            "when the agent advertises `capabilities.session.prompt.embeddedContext`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1504 (EmbeddedResource)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PROMPT-003",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A prompt of `text` + `resource_link` content blocks is accepted, and the turn "
            "reaches idle -- ADVISORY, since `initialization.mdx:203` ('agents advertising "
            "`session` MUST support `text` and `resource_link`') conflicts with "
            "`content.mdx:33` ('all agents MUST support text content blocks', silent on "
            "`resource_link`); the conflict survives verbatim from v1 into v2."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:203; docs/protocol/v2/content.mdx:33; "
            "schema/v2/schema.json:1341 (ResourceLink), :6531 (PromptRequest.prompt)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-PERM-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Any `session/request_permission` request the agent sends during a turn "
            "validates: `sessionId`, a non-empty string `title`, and a non-empty `options` "
            "array, each option carrying `optionId`/`name`/`kind`. Once the client answers "
            "with a `selected` outcome, the turn still reaches an idle. Vacuous (SKIPPED) when "
            "no permission request was observed during the turn -- sending one is only MAY."
        ),
        citation=_cite(
            "schema/v2/schema.json:545 (RequestPermissionRequest, required "
            "[\"sessionId\",\"title\",\"options\"], options.minItems:1), :1999 "
            "(PermissionOption, required [\"optionId\",\"name\",\"kind\"]); "
            "docs/protocol/v2/tool-calls.mdx:194,233,253"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-CLIENTCAP-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "With a mock client advertising no `capabilities.elicitation.*` mode, no "
            "`elicitation/create` request is observed during a prompt turn."
        ),
        citation=_cite(
            "docs/protocol/v2/elicitation.mdx:54,166; schema/v2/schema.json:5842 "
            "(x-method: elicitation/create)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-CLIENTCAP-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every agent->client request/notification method observed during a prompt turn "
            "is a member of `CLIENT_METHODS` or `PROTOCOL_METHODS` (e.g. `$/cancel_request`), "
            "or begins with `_`. `fs/*`/`terminal/*` do not exist as v2 methods at all, so "
            "calling either FAILs here as an undefined method (the v2 collapse of v1's "
            "separate `ACP-CLIENTCAP-001/002` rows)."
        ),
        citation=_cite(
            "schema/v2/meta.json:16-21 (agent->client method inventory); "
            "docs/protocol/v2/migration.mdx:53-54,628-637 (fs/terminal removed); "
            "docs/protocol/v2/extensibility.mdx:43,52 (MUST NOT call undefined methods)"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-INFO-CONCURRENT-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) what the agent does when a second `session/prompt` for the "
            "same session is sent before the first has reached its terminating idle: accepted, "
            "a JSON-RPC error, or silence. Concurrency is explicitly out of scope of the v2 "
            "design."
        ),
        citation=_cite(
            "docs/rfds/v2/prompt.mdx:86 ('This RFD does not specify queueing, steering, or "
            "whether agents insert new prompts while busy')"
        ),
        source_report="acp-v2-prompt-lifecycle.md",
    ),
    Requirement(
        id="ACP-INFO-UNKNOWNSESSION-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) the agent's response to `session/prompt` with a "
            "`sessionId` it never created -- v2's `error.mdx` is still 'Documentation coming "
            "soon', so the error code (if any) is unspecified."
        ),
        citation=_cite("docs/protocol/v2/error.mdx"),
        source_report="acp-v2-prompt-lifecycle.md",
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
