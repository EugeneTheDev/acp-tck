# State

**Last updated:** 2026-09-21 (v2 effort, session 1 — V2-0…V2-1c merged+pushed; V2-2a prompt driver in flight)
**Last commit pushed:** `75bc188` on `v2-support` (V2-1c; 186 tests) — plus workbench commits on top

## How to resume (fresh orchestrator)
1. Read `prompt.md` (the mission brief — v2 support, `common`/`v1`/`v2` layout, orchestrator-only role,
   per-slice git worktree workflow), this file, `plan.md`. Research reports in `research/` are the only
   protocol truth the code may encode.
2. `.agents/skills/*/.repo` are gitignored pointers to the upstream checkouts; if missing in this worktree,
   copy them from `/Users/eugene/Documents/JetBrains/projects/acp-tck/.agents/skills/*/.repo` (spec →
   `../agent-client-protocol`, rust → `../acp-rust-sdk`, python → `../acp-python-sdk`, a2a → `../a2a-tck`).
3. Verify the tree: `uv run pytest -q` (≈100 s; expect 135 passed) and
   `uv run acp-tck --cancel-prompt __hang__ --auth-method tck -- python tests/fixtures/agents/v1/conforming_full.py`
   (exit 0, CONFORMANT, only ACP-AUTH-005 SKIPPED). Layout is now `src/tck/common/` + `src/tck/v1/`,
   tests in `tests/common/`, `tests/v1/`, fixtures in `tests/fixtures/agents/v1/` (see `AGENTS.md`).
4. Check whether the four research reports listed under "In flight" exist; if they do, judge them and
   proceed to "Next actions". If not, re-spawn the missing researcher(s) with the same question.

## Mission (this effort)
Add ACP **v2** support to the TCK side by side with v1, without regressing v1. Integration branch is
`v2-support` (treat as upstream; `main` untouched until the user explicitly decides to merge back).
Target layout: `src/tck/common/` (version-agnostic), `src/tck/v1/` (existing code migrated),
`src/tck/v2/` (new). CLI routing between v1 and v2 (auto-detect vs flag vs sub-commands) is NOT decided —
it is an output of the first research round. Every protocol-touching slice starts from a researcher's
report on the v2 delta for that slice; never assume v1 carries over or diverges.

## v1 baseline (complete, on `main` and `v2-support`)
Installable `acp-tck` package; conformance suite in `src/tck/conformance/`; CLI `acp-tck [opts] -- <agent
cmd>` runs pytest with `-p tck.plugin`; one fresh stdio subprocess per test; hand-rolled asyncio NDJSON
harness (`src/tck/harness/`); vendored v1 schema (`src/tck/schema/v1/` @ 6d08f412) validated via
`jsonschema`; registry of **56 requirements** (`src/tck/requirements.py`) tiered MANDATORY / CAPABILITY /
ADVISORY / INFORMATIONAL; four-status verdict; console + JSON report; verdict exit code; self-tests in
`tests/` with ~35 pure-Python fixture agents; `scripts/cross-check.sh` against Rust `testy` and Python
`echo_agent.py`; CI in `.github/workflows/ci.yml`. Full catalogue in `AGENTS.md`. Real-agent reports
against `claude-agent-acp` and `codex-acp` in `.agents/reports/` (notes: `claude-wrapper.md`,
`codex-wrapper.md`). v1 research: `research/acp-v1-*.md`, `review-slices-*.md`, `spec-drift-check.md`,
`testy-cross-check.md`, `upstream-issues.md` (internal drafts only, do not file).

## In flight
- **V2-2a `v2-prompt-driver`** (worktree `../acp-tck-2-v2-prompt-driver`, off `75bc188`+): v2 `run_prompt`
  mock-client driver + core prompt-turn rows (PROMPT-20x response `{messageId}`, MSG-201 echo under same id,
  STATE-201..203 running/idle/stopReason per plan.md "v2 prompt lifecycle — decisions" and "v2 patches /
  open enums" (stopReason MANDATORY scoped to turn-ending idle; non-`_` unknown values FAIL), PROMPT-002
  re-cited (update `sessionId`), schema validity of every update), fixtures (conforming prompt behaviour
  already in `_base.py`; defect fixtures per id), `tests/v2/test_cli.py`. On report: verify, merge, push,
  cleanup. Then **V2-2b**: PROMPTCAP-001..003 re-gated on `capabilities.session.prompt.*`, PROMPT-003
  (ADVISORY resource_link), PERM-201, CLIENTCAP-201 (elicitation unadvertised) + CLIENTCAP-202 (no undefined
  non-`_`/non-`$/` client methods), informational probes. Then V2-3 … V2-7 per plan.md.

**Done (2026-09-21): slice V2-1c** (`75bc188`) — review fixes (README quick-start, docs accuracy, never-raise
validators, tightened `other`-branch carve-out, `UsageError` guard when `tck.common.plugin` is loaded
without a shim, `tests/common/test_version.py`, v2 tier-set cross-check, defect fixtures advertise
`capabilities.session`). 186 passed. Deferred nits recorded in plan.md "Deferred nits".

**Done (2026-09-21): slice V2-1b** (`cec6aea`) — v2 registry now 9 ids (INIT-001/003/201/202/203/204,
SCHEMA-001, SESSION-001/002 gated on `capabilities.session`); v2 `_base.py` implements the 7-method baseline
minimally (list/resume/close/prompt/cancel untested until V2-2/V2-4); 5 defect fixtures; `new_session()` +
`skip_if_version_mismatch()` helpers; `Verdict.blocked_by_version_mismatch` + `VERSION-MISMATCH:` marker
(decision in plan.md "Version mismatch handling"); 170 passed.

**Review landed:** `research/review-v2-slices-0-1a.md` — 0 BLOCKER / 8 SHOULD-FIX / 10 NIT; v1 behavior
preserved, `common/` version-agnostic, vendored v2 schema byte-identical to spec @ 8f76d6c, both v2
requirements falsifiable. Fix slice **V2-1c** scheduled after V2-1b (plan.md "v2 effort — slices").

**Done (2026-09-21): slice V2-1a** (`1d795cc`) — `src/tck/v2/` skeleton: vendored schema @ 8f76d6c,
`protocol.py` (incl. `protocolMethods`, `_`-prefix enum helper), batch-aware `validation.py`, registry
(ACP-INIT-001 reused, ACP-INIT-201 new), `SPEC`, plugin shim, `conformance/{_helpers,test_initialize}.py`,
CLI `--protocol-version {1,2}`, fixtures `tests/fixtures/agents/v2/{_base,conforming}.py` (advertises
`capabilities: {}` for now), `tests/v2/*`. `VersionSpec` gained `agent_info_field`/`agent_capabilities_field`
(v1 defaults). 160 passed. Note: `scratch/` is gitignored and absent in fresh worktrees — `mkdir -p scratch`
before `--report-json scratch/...`.
**Done (2026-09-21): slice V2-0b** (`42d5587`) — v1 INIT-003 probe carries `info`; `router_requires_info.py`.

**Done (2026-09-21): slice V2-0** — `src/tck/common/` (harness, requirements base, report, plugin core,
`version.py::VersionSpec`) + `src/tck/v1/` (protocol, schema, requirements, validation, conformance,
plugin shim, `SPEC`); tests reorganised; docs synced. 135 passed; v1 report identical except module paths in
prose/skip message. Programmer tip: clear `__pycache__` after `git mv` of directories (stale `co_filename`).

**Landed research (2026-09-21):**
- `research/acp-v2-patches-enums-extensibility.md` — keyed upserts, 30 open enums with emitter `_` MUST
  (invalid values stay MANDATORY FAILs), extensibility byte-identical to v1, `$/` reserved prefix, v2
  validator checklist; decisions in plan.md "v2 patches / open enums / extensibility — decisions" (incl.
  stopReason-on-idle resolved MANDATORY scoped to turn-ending idle).
- `research/acp-v2-session-management.md` — 7-method baseline; resume `replayFrom` MUSTs; no guaranteed
  resumable id (try-three-routes-then-SKIP); close observable via idle cancelled; list/delete/mcp/config
  rows; 14 v1 ids to retire; decisions in plan.md "v2 session management — decisions".
- `research/acp-v2-authentication.md` — `auth/login`/`auth/logout`, `methodId`, derived gate (non-empty
  authMethods ⇒ both MUST), `-32000` still MAY, terminal gate stays; decisions in plan.md "v2 authentication
  — decisions" incl. opt-in `--allow-logout`.
- `research/acp-v2-prompt-lifecycle.md` — prompt response = `{messageId}` receipt; turn via `state_update`
  running→idle; updates after idle legal; 22 candidate rows; driver design; decisions in plan.md
  "v2 prompt lifecycle — decisions".
- `research/acp-v2-cancellation-and-batching.md` — cancel wire-identical; confirmation = idle
  `state_update{stopReason: cancelled}`; v1 race persists in v2 (supersedes SDK report item 9); batching per
  JSON-RPC §6; 22 candidate rows; decisions in plan.md "v2 cancellation and batching — decisions".
- `research/acp-v2-initialize-capabilities-baseline.md` — v2 `initialize` field tables (`info` REQUIRED both
  sides), all capabilities object markers, `capabilities.session` ⟹ 7-method baseline, minimal
  `session/new`, validator facts (7 anyOf branches, no `null` responses), candidate requirement rows with
  2xx ids; decisions recorded in plan.md "v2 initialize / capabilities / baseline — decisions".
- `research/reference-sdks-v2-status.md` — both SDKs implement draft v2; `testy` dual build
  (`--features unstable_protocol_v2`) is the v2 cross-check target; Python needs a repo-authored v2 fixture
  on rc2; wire constraints (no pipelining behind initialize, deterministic v2 cancel, idle-before-running,
  `info` required) recorded in plan.md "Reference SDKs and v2".
- `research/acp-v2-version-negotiation.md` — negotiation algorithm verbatim v1; `info` REQUIRED both sides;
  second `initialize` rejected by both SDKs; dual v1/v2 support non-normative; routing decision recorded
  as plan.md part 2 (`--protocol-version {1,2}`, default 1; `auto` deferred); v1 INIT-003 probe needs
  `info` (slice V2-0b); v2-only-agent-asked-for-1 MUST answer 2 → MANDATORY (SDKs violate by design).
- `research/common-v1-v2-split-analysis.md` — module classification, coupling points P1–P10, decisions
  D1–D8, migration steps §5.1 (implemented by slice V2-0), A2A TCK has no multi-version support.
- `research/acp-v2-status-and-delta-inventory.md` — v2 is a **Draft** (2.0.0-alpha.5, 2026-09-18);
  vendorable `schema/v2/{schema,meta}.json` @ spec 8f76d6c with `x-side`/`x-method`; large delta (see
  plan.md "v2 upstream status"); 8 follow-up research slices named; flags: migration.mdx stale on client
  capabilities, `session/set_config_option` availability unstated, StopReason open enum, batch arrays are
  valid stdout lines (v2 ACP-TRANSPORT-001 must relax).

## Open questions / known blockers
- Upstream checkouts: `git pull --ff-only` now fails with "Cannot fast-forward to multiple branches"
  (local tracking config in all three checkouts). Workaround researchers used: `git fetch origin` then
  verify `git rev-list --left-right --count HEAD...origin/main` is `0 0`. Consider having a programmer
  update the `check-*` SKILL.md refresh step; do not "repair" the checkouts without the user.
- Deliverable shape parts 1 (layout, D1–D8, one suite per run) and 2 (CLI routing) are decided in `plan.md`.
- v2 upstream is a Draft (alpha); pin every citation and the vendored schema to a commit; expect churn.
- Deferred v1 nits (not scheduled): N12/N20 from `review-slices-5-6.md`, N9 from `review-slices-7.md`.

## Next actions
1. Merge slice V2-0 when the programmer reports (see "In flight" for the checklist).
2. After V2-0 merges: spawn slice V2-0b (v1 INIT-003 probe carries `info` + router fixture; plan.md part 2).
3. Spawn slice V2-1 (v2 skeleton + initialize, plan.md "v2 effort — slices") in parallel with V2-0b, both
   off the post-V2-0 tip; merge in the order they report. Then V2-2 … V2-7 serially (each touches
   `v2/requirements.py`, `_helpers.py`, `_base.py`), per the fixed order in plan.md.
4. Tell the user: v2 upstream is Draft/alpha; requirements will churn with upstream; confirm they want to
   proceed against a moving target (proceeding meanwhile, per the mission brief).
