# Plan

## v2 effort — decided deliverable shape, part 1: package layout (approved by orchestrator, 2026-09-21)

Source: `research/common-v1-v2-split-analysis.md` (D1–D8, §5) and `research/acp-v2-status-and-delta-inventory.md`.
CLI routing between v1 and v2 is **not yet decided** — awaiting `research/acp-v2-version-negotiation.md`
(part 2 below). The mechanical v1 migration does not depend on it.

- **Layout:** `src/tck/common/` (harness, `requirements.py` base types `Tier`/`Requirement`, `report.py`,
  `plugin.py` core, `version.py` with `VersionSpec`), `src/tck/v1/` (`protocol.py`, `schema/` vendored v1,
  `requirements.py` with `SPEC_REVISION`+`_DECLARATIONS`+`REGISTRY`+`get`, `validation.py`,
  `conformance/`, `plugin.py` shim exporting the common plugin and stashing `tck.v1.SPEC`), `src/tck/v2/`
  (later; same shape). `tests/common/`, `tests/v1/`, `tests/fixtures/agents/v1/`.
- **D1 — `VersionSpec` dataclass in `common/version.py`** bundling `protocol_version`, `schema_revision`,
  `schema_dir`, `registry`, `initialize_params()` (the version's handshake params), `conformance_package`.
  One `config.stash` lookup in the common plugin replaces the six separate v1 imports.
- **D2 — `Tier`, `Status`, `Verdict`, `TestOutcome`, `RequirementResult` are shared** (no protocol content).
- **D3 — requirement ids are NOT namespaced per version.** Each version has its own registry; the report
  already carries `protocol_version` per run (D4), so `ACP-INIT-001` in a v2 report is unambiguous. Rule:
  a v2 registry entry reuses a v1 id **only** when it is the same requirement re-cited against v2 sources;
  genuinely new v2 requirements get new ids (`ACP-<AREA>-<NNN>`, same `_ID_PATTERN`). Cross-version docs
  must name the version in their headings.
- **D4 — report `protocol_version`/`schema_revision` stay per-run scalars** (v1 JSON byte-identical).
- **D5 — one version's suite per CLI/pytest invocation.** A combined run would break the per-run version,
  force id namespacing, and make `Verdict.conformant` wrong for a v1-only agent. The CLI may *probe* first
  (routing, part 2) but always runs exactly one `vN/conformance` suite with `-p tck.vN.plugin`.
- **D6 — `validation.py` moves to `src/tck/v1/validation.py` (not shared).** The v2 schema's top level is
  an `anyOf` of seven branches (adds four batch envelopes) and its `StopReason` is an open string — two of
  the five structural assumptions the v1 validator makes no longer hold. v2 gets its own validator;
  generalize only if the two turn out identical once written (honest duplication rule, `prompt.md`).
- **D7 — clean break on import paths** (no `tck.harness`/`tck.protocol` shims; the public surface is the
  `acp-tck` console script).
- **D8 — `--tck-*` option names identical across versions**, registered by exactly one module
  (`common/plugin.py`).
- **Fixture families:** v2 gets a parallel `tests/fixtures/agents/v2/_base.py`, not a parametrized v1
  `_base.py` — v2's method inventory is not a superset of v1's (8 methods removed, 2 renamed,
  `session/prompt` semantics redesigned, `initialize` restructured).
- **Invariant for the migration slice:** `uv run pytest` green; `acp-tck --cancel-prompt __hang__
  --auth-method tck -- python tests/fixtures/agents/v1/conforming_full.py` still exit 0 / CONFORMANT with a
  `--report-json` byte-identical to a pre-move baseline modulo timestamps and `agent_command` path.

## v2 effort — decided deliverable shape, part 2: CLI routing (approved by orchestrator, 2026-09-21)

Source: `research/acp-v2-version-negotiation.md` (spec @ 8f76d6c).

- **`--protocol-version {1,2}` (plugin: `--tck-protocol-version`), default `1`.** `1` keeps today's
  behavior byte-identical (v1 is the stable protocol; v2 is a Draft). `2` runs `-p tck.v2.plugin` on
  `src/tck/v2/conformance`. Exactly one suite per invocation (D5). The report's `protocol_version` field
  reflects the selected version. Sub-commands are rejected: same options, same output shape, one flag.
- **`auto` is deferred** (not in slice V2-1). Design, when scheduled: one probe `initialize` with
  `protocolVersion: 2` in its own fresh process (a second `initialize` on one connection is rejected with
  `-32600` by both SDKs and never sanctioned by the spec); select v2 iff the answer is `2` AND the result
  carries the v2-REQUIRED `info` object (an echoing v1 agent answers `2` without `info`); otherwise v1.
  Auto can never be the default while v1 is the stable version.
- **Negotiation facts the v2 suite encodes** (all MUST-level, verbatim from v1 — `v2/initialization.mdx:
  92-96`, `migration.mdx:26` "mechanism unchanged"): agent returns the requested version if supported,
  else the latest it supports; never errors on an unsupported version; `protocolVersion` is a required
  `uint16` scalar (no list, no capability hint). A v2 agent is NOT required to support v1 (dual support is
  non-normative guidance). Consequence: a v2-only agent asked for `1` MUST answer `2`, not an error — both
  reference SDKs violate this by design in strict-v2 mode (Rust `-32600`, Python `-32602`).
  **Tier decision: MANDATORY**, consistent with how ACP-INIT-003 already ships with a known upstream-fail
  baseline; document the baseline in `docs/cross-check.md` and add a draft to `research/upstream-issues.md`
  when the v2 init slice lands. Revisit only if the v2 text changes.
- **v1 fix scheduled (slice V2-0b, after the migration merges — same file):** ACP-INIT-003's `65535`
  probe must carry `"info": {"name": ..., "version": ...}` alongside `clientCapabilities`/`clientInfo`. A
  version-routing agent (Rust `testy` built with `unstable_protocol_v2`, Python `AgentProtocolRouter`)
  selects v2 for `65535` and validates the params as a v2 `InitializeRequest`, whose `info` is REQUIRED →
  spurious `-32602` for a params-shape reason. Rationale for the TCK: the `65535` probe *represents a
  future-version client*, so its params legitimately carry every version's required fields; extra keys
  are not rejected by the v1 schema or either SDK. Add a fixture agent reproducing the router behavior
  (v1+v2, validates params per selected version) so the fix is self-tested.
- **Vendor the stable v2 artifacts only**: `schema/v2/schema.json` + `schema/v2/meta.json` at a pinned
  commit; never the `.unstable.json` variants (the Python SDK's `meta.py` is generated from unstable meta,
  so its method inventory is wider than stable v2 — informational, not a TCK input).

### v2 upstream status (from `research/acp-v2-status-and-delta-inventory.md`, spec @ 8f76d6c, 2026-09-21)
v2 is a published **Draft** (`README.md:23` "current stable ACP protocol version is `1`"; docs nav tag
"Draft"; Rust `ProtocolVersion::V2` behind an opt-in `unstable_protocol_v2` feature; artifact
`2.0.0-alpha.5`). Vendorable: `schema/v2/schema.json` + `schema/v2/meta.json` (ignore `.unstable.json`
variants), same generator and `x-side`/`x-method` annotations as v1. Unchanged from v1: error codes,
five content block types, five stop-reason values, `_meta`/`_`-prefix extensibility, stdio framing.
Changed: `initialize` restructured (`info` REQUIRED, `capabilities`), all capability booleans → object
markers under `capabilities.session`, `session/load`/`set_mode`/`fs/*`/`terminal/*` removed,
`authenticate`→`auth/login`, `logout`→`auth/logout`, `session/prompt` returns `messageId` and turn
completion moves to `state_update` notifications, stdio gains JSON-RPC batch handling, most enums opened.
Consequence: v2 requirements will churn with upstream alphas; every v2 citation pins a commit and the
vendored revision must be re-checked before any release.

### Reference SDKs and v2 (from `research/reference-sdks-v2-status.md`, rust 2a78849, python 9d07d78 = 1.0.0rc2)
- Both SDKs implement draft v2 from `schema-v2.0.0-alpha.5`, both send integer `2`.
- **Rust `testy` dual build** is the v2 cross-check target: `cargo build -p agent-client-protocol-test
  --bin testy --no-default-features --features unstable_protocol_v2` picks v1 or v2 from the client's
  `initialize`; the existing v1 suite against that binary reproduces the documented v1 baseline. Its v2
  agent advertises only `capabilities.session: {}` and handles `initialize`, `session/new|list|resume|
  close|prompt|cancel` — most CAPABILITY-tier v2 tests will SKIP against it.
- **Python has no v2 example agent**; a v2 Python cross-check needs a ~60-line fixture this repo authors on
  `acp.experimental.v2`, pinned `agent-client-protocol==1.0.0rc2` (shape in the report; probe scripts were
  left in `/tmp/acpv2probe/`, disposable).
- **Hard constraints for the v2 helpers/harness use:** (a) never pipeline a request behind `initialize`
  before its response — native Rust v2 rejects with `-32600`; (b) v2 cancellation is deterministic
  (`state_update: idle` + `stopReason: "cancelled"`) — the v1 race/`quiet_period`/"cancellation not
  exercised" machinery is not needed for v2 (verify against the prompt-lifecycle research before dropping);
  (c) a `state_update: idle` may arrive *before* `running` as an initial ready state — wait for `running`;
  (d) `InitializeResponse.info` REQUIRED → v1 ADVISORY ACP-INIT-004 becomes MUST-shaped in v2.
- Native v2-only agents answer an unsupported `protocolVersion` with an error (Rust `-32600`, Python
  `-32602`); the SDKs' protocol *routers* normalize anything ≥ 2 to `2`. Matches the negotiation report.
- Open (routed to the initialize/capabilities researcher): schema crate contradicts itself on whether
  `capabilities.session: {}` implies `session/list|resume|close` support.

### v2 initialize / capabilities / baseline — decisions (from `research/acp-v2-initialize-capabilities-baseline.md`, spec 8f76d6c)
- `initialize` request `required: ["protocolVersion","info"]` (`schema/v2/schema.json:5838`); response the same
  pair (`:3086`). The TCK's v2 mock client sends `info: {name: "acp-tck", version: <tck version>}` and
  `capabilities: {}` by default. v1's ADVISORY `agentInfo` check is a MUST in v2.
- **Every v2 capability is an object marker** (present & non-null ⟹ supported). The plugin's `boolean=True`
  gate mode is v1-only. Agent surface: `capabilities.session{prompt{image,audio,embeddedContext},
  mcp{stdio,http}, delete, additionalDirectories}` + `capabilities.auth` (gates nothing). Client surface:
  `auth.terminal`, `elicitation.form`, `elicitation.url`.
- **`capabilities.session` (even `{}`) commits the agent to the 7-method baseline** `session/new|list|
  resume|close|prompt|cancel` + `session/update` (three independent spec statements; the 4-method comment
  in the schema crate is stale from before `a57b538`). Encode as `@pytest.mark.capability(
  "capabilities.session")`. `testy` v2 is correctly advertised.
- Non-empty `authMethods` commits the agent to `auth/login` + `auth/logout`; there is no logout marker.
- `session/set_config_option`: availability unstated upstream → `capability="inferred:configOptions"`.
- `session/new` minimal: params `{cwd}` (`mcpServers` optional), result `{sessionId}`, prose MUST unique.
- `migration.mdx:191` is stale: client capability fields exist; the terminal-auth gate stays MANDATORY.
- **Agent → client calls in v2:** `fs/*`/`terminal/*` no longer exist. Rather than deriving per-method
  "MUST NOT call fs/*" rows, encode ONE MANDATORY requirement cited to `extensibility.mdx:43,52`: an agent
  MUST NOT send a request/notification whose method is neither in the v2 client method inventory
  (`meta.json`) nor `_`-prefixed. Keep a separate capability-gated negative for `elicitation/*`
  (`capabilities.elicitation.*` unadvertised ⟹ MUST NOT call) and `auth.terminal`.
- `session/new` may-return-`-32000` appears only in generated `schema.mdx` → stays ADVISORY (as v1 AUTH-005).
- **Validator facts:** top level is 7 `anyOf` branches (`Agent`, `Client`, `AgentBatchCall`,
  `AgentBatchResponse`, `ClientBatchCall`, `ClientBatchResponse`, `ProtocolLevel`); a JSON array line is a
  valid stdout line; `x-side`/`x-method` cover all 16 `meta.json` methods; zero `additionalProperties:
  false` (keep `find_unknown_root_keys`); **no** v2 response `$def` permits `null` — do not carry over the
  v1 `session/load` null special case.
- **D3 refinement — id numbering:** a v2 registry entry that is the *same* requirement as a v1 one keeps
  the v1 id (re-cited). Requirements new to or changed in v2 use the **2xx block** within their area
  (`ACP-SESSION-201`, ...), so any id ≥ 200 in a v2 report is v2-specific at a glance and the v1
  `_ID_PATTERN` still matches. Never renumber a v1 id.

### v2 prompt lifecycle — decisions (from `research/acp-v2-prompt-lifecycle.md`, spec 8f76d6c)
- `session/prompt` request byte-identical to v1; response is an acceptance receipt `{messageId: string}`
  returned without waiting for foreground work (`prompt-lifecycle.mdx:110,124-127`). Agent MUST echo the
  user message under that `messageId` (`:129`, either order vs the response), MUST send `state_update
  {state: "running"}` when work starts (`:159`), and ends the turn only with `state_update {state:
  "idle"}` (`:348`). Updates after the turn-ending idle are legal (`:497`) — do not port v1's "nothing
  after the response" rule (ACP-CANCEL-002) literally; the cancel slice must reconcile its "flush before
  idle-cancelled" MUST with `:497` (post-idle updates legal in general) and cite both.
- **Tiers:** `stopReason` on the idle update is MUST in prose but optional in schema → **ADVISORY**
  (`ACP-STATE-203`; precedent ACP-PROMPT-003). Unknown `sessionUpdate` discriminators → **INFORMATIONAL**
  (open enum; Python SDK emits unstable-only `notice`). Concurrent `session/prompt` on one session is
  unspecified (`rfds/v2/prompt.mdx:86`; Rust rejects `-32602`) → the v2 driver serializes prompts; at most
  an INFORMATIONAL probe. `ACP-PROMPT-003` (text vs resource_link baseline conflict) stays ADVISORY.
- `ACP-STATE-202` ("running is followed by idle"): assert only when `running` was observed; a turn that
  never shows `running` is recorded (property) and SKIPped as "no foreground work observed" — the spec does
  not say whether a zero-work prompt must emit idle (open upstream question, do not guess).
- Ownership: the single MANDATORY "no undefined/non-`_` client methods" row (see initialize/capabilities
  decisions) is `ACP-CLIENTCAP-202`, owned by the initialize/capabilities slice; the prompt slice does not
  duplicate it. `ACP-CLIENTCAP-201` = elicitation unadvertised ⟹ MUST NOT call.
- Retire in v2 (no counterpart): `ACP-PROMPT-001` (stop reason in response), `ACP-MODES-001/002`,
  `ACP-CONFIG-003`. `ACP-PROMPTCAP-001..003` re-cited with object-marker gates
  `capabilities.session.prompt.{image,audio,embeddedContext}`.
- The v2 mock-client driver follows the report's design: turn-end predicate = idle `state_update` for the
  session after the `session/prompt` response (or an error response); bounded waits per the report's
  table; answers `session/request_permission` (first option / `cancelled` after cancel) and
  `elicitation/create` per advertised client capabilities (`-32601` when unadvertised, recorded).

### v2 patches / open enums / extensibility — decisions (from `research/acp-v2-patches-enums-extensibility.md`, spec 8f76d6c)
- **Emitter MUST on custom enum values** (`extensibility.mdx:111-122`, `prompt-lifecycle.mdx:481`, nine
  passages): every string enum / tagged-union discriminator in v2 is open (12 scalar enums + 18 unions
  with an `other` fallback; only `ElicitationSchemaType` and `jsonrpc` are closed), but custom values MUST
  begin with `_`. So v1's invalid-value FAILs stay **MANDATORY** in v2, restated as "defined constant OR
  `_`-prefixed" (`stopReason: "done"` FAILs, `"_vendor/x"` PASSes; same for `sessionUpdate` discriminators
  — this supersedes the "unknown `sessionUpdate` → INFORMATIONAL" line under prompt-lifecycle decisions:
  unknown non-`_` discriminators FAIL, `_`-prefixed are legal).
- **Tier resolution — `stopReason` on idle (conflict between the prompt-lifecycle report's ADVISORY and this
  report's MANDATORY):** the schema leaves `stopReason` optional because the same `IdleStateUpdate` `$def`
  also serves the *initial ready-state idle* (emitted right after `session/new` by the Rust reference,
  `simple_agent_v2.rs:363-368`), which has no turn to report on. That is not a contradiction of the prose
  MUST (`prompt-lifecycle.mdx:348`), which is about the idle that ends a turn. **Decision: MANDATORY,
  scoped to the idle that terminates an observed `running` turn** (`ACP-STATE-203`); an unscoped "every
  idle has a stopReason" check is forbidden.
- Patches/upserts: messages keyed by `messageId`, tool calls by `toolCallId`, display terminals by
  `terminalId`; omitted = unchanged, `null` = cleared, concrete = replace; `*_chunk` appends; an update for
  an unseen key *is* the create (no create-before-update MUST, no unknown-id error path). Agent-bound MUSTs
  reduce to id presence/uniqueness/stability, absolute `cwd`, `planId` on every plan variant, and the
  running/idle ordering (`ACP-PATCH-201..209` per report). Most patch text is client guidance → must-NOT-
  assert list applies.
- Byte-identical to v1 (diffed): `_meta`, `_`-method prefix, MUST respond with provided id, lowercase
  "should" on `-32601` (ACP-JSONRPC-004 stays ADVISORY), SHOULD ignore unknown notifications, MUST NOT add
  custom root fields, `Error` `$def`; `error.mdx` still a stub → ACP-ERROR-001 ADVISORY.
- **`$/` is a second reserved method prefix** (`meta.json` `protocolMethods`, e.g. `$/cancel_request`):
  the v2 method inventory must include `protocolMethods`, or the "no undefined client methods" check
  (`ACP-CLIENTCAP-202`) misclassifies protocol-level notifications.
- **v2 validator checklist** (10 items in the report): 7-branch root `anyOf` with object-vs-non-empty-array
  dispatch; unknown-root-key detection stays hand-written with a carve-out to skip `other`-branch
  variants; all 13 `*Response` defs non-nullable → do not port the v1 `null` special case; ignore
  `x-deserialize-*` annotations.
- Neither reference exercises v2 patch/upsert surfaces (`testy` v2 emits no tool calls, single-chunk
  messages only) → the repo's own v2 defect fixtures are the only coverage; cross-check will SKIP these.

### v2 cancellation and batching — decisions (from `research/acp-v2-cancellation-and-batching.md`, spec 8f76d6c)
- `session/cancel` is wire-identical to v1 (notification, `{sessionId}` + `_meta`). Confirmation moved to an
  idle `state_update` with `stopReason: "cancelled"` that the agent MUST send after aborting and flushing
  pending updates (`prompt-lifecycle.mdx:519-530`); the client MUST answer pending
  `session/request_permission` with outcome `cancelled` (`:515`) — the v2 mock driver does this.
- **Supersedes `reference-sdks-v2-status.md` item 9:** "v2 cancellation is deterministic" is SDK/scenario
  behavior (testy's `wait_for_cancel`), NOT spec-backed. Nothing holds a turn open; the v1 race reproduces
  against v2 testy. Keep the "cancellation not exercised" SKIP, `--cancel-prompt`, and `quiet_period` for
  v2; the improvement is a MUST-guaranteed `state_update: running` turn-start marker to trigger cancel on.
  `wait_for_cancel` prompt text still works against v2 testy.
- **Framing/batching:** stdio line framing unchanged; ACP v2 adopts JSON-RPC 2.0 §6 batching essentially
  verbatim plus "SHOULD NOT batch lifecycle-sensitive messages". v2 `ACP-TRANSPORT-001` must read: every
  stdout line is a single JSON-RPC object OR a non-empty JSON array of them. `ACP-JSONRPC-001..005` carry
  over with batch-aware wording (a response inside a batch response echoes its own id, etc.).
- **Tiers:** batch acceptance rows (`ACP-BATCH-201/202`) are MANDATORY per spec even though the Python SDK
  crashes on an array line (`connection.py:152-153`) — record as expected Python cross-check baseline and
  as an upstream issue draft; one fresh agent process per test already isolates the crash. The per-entry
  `-32600` rule (`transports.mdx:73-75`, no RFC-2119 keyword in ACP's own text) is **ADVISORY**, consistent
  with v1's ACP-JSONRPC-005 precedent (no normative ACP text ⟹ not MANDATORY).
- v2 validator: top level includes array branches — the v2 validator must dispatch on list-vs-dict before
  any `$def` lookup (already implied by D6; the v1 validator's dict-only assumption is not reused).

### v2 effort — slices (order fixed 2026-09-21; each is one programmer run in its own worktree)
Every slice: registry entries cite the named research report(s) (`path:line` @ spec 8f76d6c); conforming
+ single-defect fixtures under `tests/fixtures/agents/v2/`; `tests/v2/test_cli.py` id-set assertions;
`AGENTS.md` catalogue updated; `uv run pytest` green; v1 report byte-identical (regression guard from V2-0).
- **V2-0 (in flight): mechanical `common`/`v1` migration** — zero behavior change (split analysis §5.1,
  D6 = v1). No `v2/` code.
- **V2-0b: v1 ACP-INIT-003 probe carries `info`** (part 2) + router fixture (v1+v2 agent validating params
  per selected version). Parallel with V2-1 (disjoint files; AGENTS.md catalogue appends only).
- **V2-1: v2 skeleton + initialize/capabilities.** Vendor stable `schema/v2/{schema,meta}.json` @ 8f76d6c +
  `VENDORED.md`; `v2/protocol.py` (PROTOCOL_VERSION=2, inventories incl. `protocolMethods`/`$/`);
  `v2/validation.py` (7-branch root dispatch, object-or-non-empty-array, hand-written unknown-root-key check
  with `other`-branch carve-out, no `null` special case, `_`-prefix-aware enum check); `v2/requirements.py`
  + `v2/plugin.py` + `v2/__init__.py::SPEC`; `v2/conformance/_helpers.py` (`connected_agent` with v2
  handshake `info` + `capabilities: {}`, no terminal marker, `--auth-method` → `auth/login`; NO pipelining
  behind `initialize`); tests: INIT (negotiation rows incl. v2-only-answers-2 MANDATORY, `info` REQUIRED,
  capabilities object markers), SCHEMA-001 v2, SESSION-001/002 minimal `session/new`; v2 fixture base
  `tests/fixtures/agents/v2/_base.py` + conforming + echo-any-version + v2-only-errors-on-v1 + missing-info;
  CLI `--protocol-version {1,2}` default 1. Inputs: negotiation, initialize/capabilities, SDK-status reports.
- **V2-2: prompt lifecycle + mock driver.** `_helpers.run_prompt` v2 (turn-end predicate = idle for the
  session after the `{messageId}` response; bounded waits per report table; answers request_permission /
  elicitation per advertised caps; serializes prompts). Rows: PROMPT-20x, STATE-20x (202 scoped to observed
  `running`; 203 MANDATORY scoped to turn-ending idle), MSG-201, PROMPTCAP-001..003 re-gated, PERM-201,
  CLIENTCAP-201 (elicitation unadvertised) + CLIENTCAP-202 (no undefined non-`_`/non-`$/` client methods),
  informational probes. Input: prompt-lifecycle report (+ extensibility for the enum rule).
- **V2-3: cancellation + transport/JSON-RPC/batching.** CANCEL-201..208 (keep race SKIP, trigger on
  `running`, `--cancel-prompt` stays), TRANSPORT-201..203 (object OR non-empty array line), JSONRPC-201..205
  batch-aware, BATCH-201..208 (201/202 MANDATORY; per-entry -32600 ADVISORY). Input: cancellation+batching
  report (+ prompt-lifecycle `:497` for post-idle updates).
- **V2-4: session management.** RESUME-20x (replayFrom MUSTs; try-three-routes-then-SKIP for a resumable
  id), LIST-20x, CLOSE-201/202 (idle cancelled), DELETE-20x, ADDDIRS-20x, MCP-20x, CONFIG-20x
  (`inferred:configOptions`). Input: session-management report.
- **V2-5: authentication.** AUTH-201..207 per decisions; `--allow-logout` opt-in; second connection
  advertising `capabilities.auth.terminal` for 207. Input: authentication report.
- **V2-6: patches / enums / hygiene / informational.** PATCH-201..209, ENUM-201..203, META-201,
  EXT-201..203, re-cited EXT-001/META-001/ERROR-001/SHUTDOWN-001/SCHEMA-002, INFO probes. Input:
  patches-enums-extensibility report.
- **V2-7: cross-check + CI + docs.** `scripts/cross-check.sh` v2 leg: `testy` dual build
  (`--no-default-features --features unstable_protocol_v2`) with `--protocol-version 2`; repo-authored
  Python v2 fixture on `agent-client-protocol==1.0.0rc2`; `docs/cross-check.md` v2 table with expected
  baselines (Python crashes on batch lines; most CAPABILITY rows SKIP); CI job; README v2 section;
  `research/upstream-issues.md` additions (stale `schema.json:3128` comment, stale `migration.mdx:191/224`,
  Python batch crash, SDK strict-v2 negotiation errors). Then a review pass (researcher-as-reviewer) over
  all v2 slices before any merge to `main` (user decision).

---

# v1 effort (complete) — historical plan below

## Decided deliverable shape (approved by orchestrator, 2026-09-18)

Derived from research round 1 (`research/*.md`). Rationale in each bullet.

- **Installable package + CLI, tests shipped inside the package.** `acp-tck` is a wheel whose
  conformance suite lives under `src/tck/conformance/` so `uvx acp-tck -- <agent cmd>` works
  without a clone (A2A's biggest packaging mistake was not shipping its tests — `a2a-tck-structure.md`
  Discrepancy 5). The `acp-tck` console script (`tck:main`) parses TCK options and runs pytest
  programmatically on the packaged suite with `-p tck.plugin`. The plugin is *not* auto-registered via
  `pytest11` (avoid colliding with users' own pytest configs); it may be exposed later.
- **Agent under test = stdio subprocess.** CLI: `acp-tck [options] -- <command> [args...]`, plus
  `--agent-cwd`, repeatable `--agent-env KEY=VAL`, `--timeout` (per-response deadline, default 30s),
  `--startup-timeout`. Environment: inherit the parent env and overlay overrides (Rust-SDK style;
  `acp-v1-transport-and-jsonrpc.md` Discrepancy 10). One fresh agent process per test (clean state,
  crashes cannot cascade; `a2a-tck-structure.md` Testability notes).
- **Raw-first harness, no runtime dependency on the Python SDK.** The SDK's typed layer cannot emit
  malformed traffic and its transport silently drops non-JSON lines (`reference-sdks-as-harness.md`
  Requirements 1–5); the transport layer we need is ~100 lines. We hand-roll an asyncio NDJSON stdio
  client (`tck/harness/`) that records a full raw transcript (both directions, timestamps, parse
  failures), captures stderr, enforces deadlines on every read, and terminates with a
  close-stdin → SIGTERM → SIGKILL ladder on the process group.
- **Schema validation from the spec's JSON Schema.** Vendor `schema/v1/schema.json` (+ `meta.json`)
  from the spec repo at a pinned revision into `src/tck/schema/`, validate every agent-emitted
  message with the `jsonschema` library. This is the single highest-value structural check
  (`acp-v1-protocol-surface.md` Testability notes).
- **Requirement registry + tiers.** `tck/requirements.py` declares every requirement with an ID,
  tier, one-line text, and spec citation (path:line @ revision). Tiers: `mandatory`,
  `capability:<path>` (run iff the agent advertised it; otherwise SKIPPED = not applicable),
  `advisory` (SHOULD; report, never fails the verdict), `informational` (spec silent, SDKs disagree;
  reported only). Tests bind to requirements via a `@requirement("ACP-…")` marker. Meta-tests assert
  registry invariants.
- **Four-status verdict model** (from A2A): PASS / FAIL / SKIPPED (not applicable) / NOT TESTED
  (declared requirement produced no record, counts as failure so a dead agent can't score 100%).
  Reports: console summary + JSON (`--report-json PATH`). Exit code 0 iff no mandatory FAIL/NOT
  TESTED.
- **Self-tests.** Repo-only `tests/` runs the harness and the conformance suite against fixture
  agents in `tests/fixtures/agents/` — pure-Python raw-byte scripts: one conforming agent
  (deterministic, offline, fixed session id, honest version negotiation) and a catalogue of
  single-defect non-conforming agents. Rust `testy` may be added later as an optional CI-only
  cross-check (not a runtime dependency; note it echoes the client's protocolVersion, so it is not a
  valid negotiation fixture).
- **v1 only.** `PROTOCOL_VERSION = 1` in one place (`tck/protocol.py`). Batch arrays, pre-initialize
  gating, `auth/login`, v2 prompt lifecycle are excluded; see transport report Discrepancies 1, 7.

## Done
- License — Apache-2.0 `LICENSE` + PEP 639 `license`/`license-files` in pyproject; wheel METADATA verified.
- Slice 8b — review-slices-7 fixes: send_raw OSError→AgentExited, informational probes use quiet_period, close() per-stage exit check, deselection hint, AUTH-001 advisory, AUTH-003 inferred capability, EXT-001 scope, registry↔self-test tier cross-check, docs (135 passed, 99 s).
- CI — `.github/workflows/ci.yml` (test on 3.14; informational cross-check job pinned to upstream SHAs, `--expect-only-mandatory-fail ACP-INIT-003`); pyproject description/urls (132 passed).
- Slice 8 — `scripts/cross-check.sh` + `cross-check-summary.py`, `docs/cross-check.md`; testy and echo_agent (1.0.0rc1) both NOT CONFORMANT solely on INIT-003 (echo 65535) + advisory INIT-004; echo_agent also fails advisory JSONRPC-004 (upstream SDK returns `result: null` for unknown ext methods). Citation text fixes landed.
- Slice 7b — hardening per review-slices-5-6: no double initialize; INIT-003 `!= 65535 and >= latest`; CLOSE-002 via mock client; auth gating only with non-empty authMethods, authenticate failure → blocked not FAIL; collect-only untouched; `-k` hint; transcript cap; stricter fixtures; CLIENTCAP split; `--close-grace`; runtime 118 s (125 passed).
- Slice 7 — CLIENTCAP-001/002/003, EXT-001 (MANDATORY), META-001, ERROR-001, SHUTDOWN-001, SCHEMA-002 (unknown-root-keys checker), STDERR-001 + 3 ACP-INFO-* informational probes with terminal notes; 4 fixtures (123 passed; 57 requirements).
- Slice 6b — MODES-001/002, CONFIG-001/002/003, PROMPTCAP-001/002/003, AUTH-001..004; `--auth-method`; `verdict.blocked_by_auth`; inferred gates for modes/configOptions; 5 fixtures (113 passed, 1 skipped; 43 requirements).
- Slice 6a — INIT-003 strengthened; ACP-LOAD-001/002/003, RESUME-001/002, LIST-001/002, DELETE-001/002, CLOSE-001/002, ADDDIRS-001; `conforming_full.py` + 5 defect fixtures (102 passed, 1 skipped).
- Slice 5b — hardening per review: 64 MiB line limit with lossless oversize handling, write deadline, per-test watchdog (`--test-timeout`), close() drains stdout, TRANSPORT-002 split, mock client everywhere, JSONRPC-002 evidence from mandatory paths, `_tck/` probes, capability marker boolean/object encodings (94 passed, 3 skipped).
- Slice 5 — `tck/report.py` (Status/TestOutcome/RequirementResult/Verdict/Report), `--report-json`, verdict-based exit code, per-tier counts, meta-tests, README (79 passed, 3 skipped).
- Slice 4b — raced cancel → SKIPPED; `--cancel-prompt` / `--tck-cancel-prompt`; CLI passes `-rs`.
- Slice 4 — ACP-SESSION-001/002, ACP-PROMPT-001/002/003, ACP-CANCEL-001/002; `_helpers.run_prompt` mock-client driver; 7 defect fixtures (56 tests total).
- Slice 3 — `tck/requirements.py` (12 reqs), `tck/plugin.py`, `tck/conformance/{test_transport,test_jsonrpc,test_initialize}.py`, CLI `acp-tck -- <cmd>`, 5 defect fixtures, registry + CLI self-tests (49 tests total).
- Slice 2 — vendored spec schema @ 6d08f41 (`src/tck/schema/v1/`), `tck/protocol.py`, `tck/validation.py`, 19 tests.
- Slice 1 — harness core + fixture agents + 13 unit tests (`src/tck/harness/`, `tests/`).
- Research round 1: `research/acp-v1-protocol-surface.md`, `research/acp-v1-transport-and-jsonrpc.md`,
  `research/a2a-tck-structure.md`, `research/reference-sdks-as-harness.md`.

## In progress
- (nothing in progress; all planned slices done)

## Next slices (in order)
7b. **Hardening from `research/review-slices-5-6.md`** (2 blockers, 9 should-fix, 14 nits) — before slice 8:
    AUTH-001 and JSONRPC-003/… must not send a second `initialize` (use cached initialize result or
    `handshake=False`); INIT-003 rule becomes `version != 65535 and version >= latest_supported`; CLOSE-002 uses
    the mock-client dispatch (factor `run_prompt`'s handler into a reusable mock client with an on-first-update
    hook); `skip_if_auth_gated` only excuses `-32000` when `authMethods` is non-empty (else FAIL); auth flow must
    not assert `authenticate` succeeds as a MANDATORY requirement (research must-NOT #10) — on failure, SKIP
    session tests as blocked with a hint; `--collect-only` must not be overridden; `-k` deselection hint must not
    blame the agent; cap transcript size in the JSON report; `_base.py` validates `authenticate` params and
    prompt content blocks; runtime wins (wrong_id_echo run with tiny timeouts, shorter drain in watchdog test).
    Also from slice 7: split CLIENTCAP-001/002/003 into per-id attribution (one fixture calling only `fs/*` must
    fail only 001); `_base.py` should answer an unknown `sessionId` with an error, not a result; suite runtime
    back under ~120 s.
5b. **Hardening from `research/review-slices-1-4.md`** (1 blocker, 9 should-fix, 9 nits) — do before slice 6:
    raise asyncio stream `limit` (e.g. 64 MiB) and never lose bytes on overlong lines; deadline on `drain()`;
    per-test watchdog; `close()` drains remaining stdout into the transcript (post-response stdout garbage must
    fail TRANSPORT-001); split TRANSPORT-002 (UTF-8) into its own test; drive every prompt turn through
    `run_prompt` (mock client) incl. transport + SCHEMA-001 tests; JSONRPC-002 evidence must come from a
    mandatory path (e.g. the `initialize` response and a deliberately invalid-params request), not the SHOULD
    unknown-method reply; TCK probe methods `_`-prefixed (`_tck/does_not_exist`); `capability` marker
    implements boolean `=== true` gates and object-marker non-null; plus the remaining should-fix/nits.
2. Vendored v1 JSON schema + `tck/protocol.py` constants + `validate_agent_message()` + tests.
3. Requirement registry + pytest plugin (options, per-test agent fixture, `@requirement` marker,
   result collector) + CLI wiring + first conformance tests: transport hygiene (T1/T5/T7/J1–J4)
   and `initialize` (Reqs 3, 5, 6; version mismatch → success with agent's latest).
4. Session/prompt/cancel mandatory tests (Reqs 9, 24, 25, 26, 28) + non-conforming fixtures for each.
5. Reporting (console + JSON, four-status verdict, exit code) + meta-tests over the registry.
6. Capability-conditional tests (`loadSession` replay ordering, `session/resume`, `session/list`,
   `session/delete`, `session/close`, prompt content caps) + client-capability negative tests
   (fs/terminal/elicitation/boolean config never called when not advertised).
8. Cross-check script against `testy` and `echo_agent.py` (see decision above); optional GitHub Actions job.
7. Advisory/informational tier (unknown method −32601, error shape, stdin-EOF exit, `_meta` round-trip,
   `_ext` method response).

## Decisions from follow-up research
- **Authentication** (`research/acp-v1-authentication.md`): v1 never requires `-32000` gating; auth
  tests are surface checks (authMethods shape; no `terminal` method advertised unless client sent
  `clientCapabilities.auth.terminal`; `authenticate`/`logout` return objects) plus two conditional
  properties. Harness policy: CLI gets `--auth-method <id>`; when set, the per-test setup calls
  `authenticate` after `initialize`. If `session/new` returns `-32000` and no `--auth-method` was
  given, the test is reported as NOT TESTED with a pointer to the flag, not as FAIL. Auth lands in
  slice 6/7 alongside other capability-conditional work.

## Decisions (orchestrator) — from `research/review-slices-7.md`
- **ACP-AUTH-001** → ADVISORY (its only assertion, AUTH-A5, is advisory in the auth research).
- **ACP-EXT-001** stays MANDATORY: Req 42 (extensibility.mdx) says recipients MUST respond to custom `_`
  requests; the SHOULD in the transport report (J6) is about the *specific* `-32601` code, which remains
  ADVISORY under JSONRPC-004. Test must assert only "some response arrives" (result or error).
- **ACP-AUTH-003** → CAPABILITY with `capability="inferred:authMethods"` (runs only when `authMethods` is
  non-empty and `--auth-method` is given; otherwise SKIPPED), mirroring the modes/configOptions inferred gates.
- **Informational probes** use `quiet_period()` (short), never the full `--timeout`; harness `send_raw`
  translates `OSError`/`ConnectionResetError`/`BrokenPipeError` into `AgentExited`.
- **`close()`** must check process exit after each grace stage, not burn the grace twice.
- **License**: Apache-2.0 (user decision, 2026-09-18). **No v0.1.0 tag yet** (user). Upstream issue drafts remain
  internal (user).
- `requires-python = ">=3.14"` is a fixed constraint from `prompt.md`; keep.

## Decisions (orchestrator)
- **Spec drift** (`research/spec-drift-check.md`, upstream HEAD d3c1dd7): `schema/v1/` byte-identical → no
  re-vendor; registry citations stay pinned at 6d08f412 where line numbers are exact. Slice 8 fixes three
  citation texts: MODES-002 must not call `session-modes.mdx:117-119` a docs bug any more (fixed upstream in
  b96b439); LOAD-003 cites `ac82df6` as why `null` stays tolerated; INFO-UNKNOWNSESSION-001 path is
  `docs/protocol/v1/error.mdx`.
- **ACP-INIT-003 strengthening** (`research/testy-cross-check.md` finding 1): the response to an unsupported
  requested version (65535) must carry an integer `protocolVersion` that is *not* 65535 and equals the
  version the agent returns for a v1 request (its latest supported). Both `testy` and `echo_agent.py` echo
  65535 and must FAIL this. Add a defect fixture `echoes_any_version.py`. → slice 6.
- **Cross-check against independent agents** → slice 8: `scripts/cross-check.sh` builds `testy`
  (`cargo build -p agent-client-protocol-test --bin testy --no-default-features`) from the rust-sdk checkout
  path and runs `acp-tck --cancel-prompt wait_for_cancel`; also runs `echo_agent.py` pinned to
  `agent-client-protocol==1.0.0rc1`. Not part of `uv run pytest` (needs cargo); document in AGENTS.md.
  Expected: testy CONFORMANT except INIT-003 FAIL after strengthening, INIT-004 advisory FAIL.
- **Cancel tests and the race**: the TCK cannot force a real agent's turn to stay in flight. If the prompt
  response was read before `session/cancel` was written, or arrives with a valid non-`cancelled` stop
  reason within 1.0 s after the cancel was written, the cancel requirements are SKIPPED with reason
  "cancellation not exercised" — never PASS. A non-`cancelled` response later than that is FAIL. Users
  can supply `--cancel-prompt TEXT` (plugin `--tck-cancel-prompt`) to keep their agent busy.
- **Capability detection** (`research/acp-v1-session-capabilities.md`): boolean gates (`loadSession`,
  `promptCapabilities.*`, `mcpCapabilities.*`) are supported iff `=== true`; object markers
  (`sessionCapabilities.*`, `auth.logout`) iff present and non-null. The plugin's `capability` marker must
  implement both encodings (fix in slice 6 if slice 3 only did non-null).
- **`null` empty responses**: mandatory validation keeps accepting `null` for all-optional object responses
  (many agents follow the old docs), and an ADVISORY requirement reports `null` where `{}` is expected
  (upstream docs fixed in spec commit d89c8d3; `null` was never schema-valid).
- **Req 10 (stdio MCP MUST)**: not observable from the client (agents connect lazily); no test. Documented
  as untestable in the registry (INFORMATIONAL entry with no test) or omitted — programmer's call in slice 6.
- **Spec revision**: schema byte-identical between 6d08f41 and d89c8d3; VENDORED.md stays at 6d08f41.
- ACP-JSONRPC-005 ("errors are not fatal") is ADVISORY: no normative spec text, only SDK regression tests.
- Cascading failures (e.g. an agent that mis-echoes ids fails nearly every test) are the correct verdict
  shape; the report must simply attribute each FAIL to its requirement. No special cascade logic.
- Transcript/report format: our own JSON structure (slice 5). Conductor `.jsons` compatibility deferred;
  not a goal for v0.1.

## Open questions
- Vendored schema has no `additionalProperties: false` anywhere, so Req 41 (no custom root fields) needs a
  custom check (compare emitted object keys against the `$def`'s `properties` + `_meta`). Schedule in slice 7.
- `fs/write_text_file` etc. are client-authored; `validate_client_message` does not exist yet (needed for slice 6
  only if we validate our own mock client's output — optional).
- Unknown `sessionId` error code: unspecified in v1 → informational only (decided, no research needed).
- Is a second concurrent `session/prompt` per session legal in v1? Route to research before slice 4
  only if a test would depend on it (currently none planned).
