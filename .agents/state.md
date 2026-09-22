# State

**Last updated:** 2026-09-22 (comment trimming + stderr fix landed; V2-8 resumed)
**Last commit pushed:** `70d9669` on `v2-support` (comment trimming `52a7bd1`/`2337d1c`/`176a056` + stderr fix; 246 passed). V2-8 branch `v2-review-fixes`
pushed at WIP tip `a517657` (based on `f030d71`).

## Standing user decisions (2026-09-22, this session)
- **Spawn ONLY ONE programmer at a time** from now on, regardless of what `prompt.md` allows.
- Adhere to subagent definitions: `programmer` = Sonnet, `researcher` = Opus. Never override the model.
- `Requirement(...).text=`/`citation=` literals that mention slices / review docs / D-decisions stay as they are
  (part of the ongoing plan); comments/docstrings are now slice-free everywhere.
- Programmers on mechanical passes: comments only, no behaviour analysis, no whole-file reads, never fix
  out-of-scope failures (report them).

## Done (2026-09-22): comment-trimming pass
Comments/docstrings across `src/`, `tests/`, `scripts/` are concise and free of slice numbers, review-report
bookkeeping and history narration; research citations, footguns, maintenance notes kept. One rename:
`tests/v2/test_registry.py::test_registry_has_exactly_the_v2_6_requirements` →
`test_registry_has_exactly_the_expected_requirements`. No logic change.

## Done (2026-09-22): `fix-stderr-assert` (`70d9669`)
`tests/v1/test_cli.py` stderr byte-count assertion parses the count instead of a substring check that matched
`350`. Suite fully green (246 passed) at `70d9669`.

## In flight — slice V2-8 `v2-review-fixes` (RESUMED 2026-09-22, one programmer, existing worktree)
Programmer was told to `git merge origin/v2-support` (`70d9669`) into the branch first (comment-vs-code
conflicts expected), then finish the WIP (NIT 26 + `test_cli.py` AUTH-201/206 SKIP fallout incl.
`test_terminal_env_duplicate_names_fails_auth_207_only`), then the remaining list below. Orchestrator decisions
handed down: NIT 29 = keep both `ACP-CANCEL-208`/`ACP-CLOSE-202`, add a "counted twice by design" clause to
CANCEL-208's text; NIT 36 = leave deferred; NIT 37 = attempt, drop with a note if fallout exceeds
INFO-UNKNOWNSESSION-001 expectations; NIT 41 already done by the trim pass. New comments must follow the
trimmed style (no slice numbers). On report: run the merge checklist below, squash-merge, suite, push, remove
worktree + branch (local + remote).

## How to resume (fresh orchestrator)
1. Read `prompt.md` (the mission brief — v2 support, `common`/`v1`/`v2` layout, orchestrator-only role,
   per-slice git worktree workflow), this file, `plan.md`. Research reports in `research/` are the only
   protocol truth the code may encode.
2. `.agents/skills/*/.repo` are gitignored pointers to the upstream checkouts; if missing in this worktree,
   copy them from `/Users/eugene/Documents/JetBrains/projects/acp-tck/.agents/skills/*/.repo` (spec →
   `../agent-client-protocol`, rust → `../acp-rust-sdk`, python → `../acp-python-sdk`, a2a → `../a2a-tck`).
3. Verify the tree on `v2-support`: `uv run pytest -q` (≈360 s; expect 246 passed) and
   `uv run acp-tck --protocol-version 2 --cancel-prompt __hang__ --auth-method tck --allow-logout -- python
   tests/fixtures/agents/v2/conforming_full.py` (exit 0, CONFORMANT). Layout: `src/tck/common/` + `src/tck/v1/`
   + `src/tck/v2/`; tests in `tests/common/`, `tests/v1/`, `tests/v2/`; fixtures in `tests/fixtures/agents/v{1,2}/`
   (see `AGENTS.md`).
4. **Resume slice V2-8** — see "In flight" below. The worktree `../acp-tck-2-v2-review-fixes` (branch
   `v2-review-fixes`, 14 commits off `f030d71`, tip `a517657` = WIP, pushed to origin) still exists on disk;
   do NOT remove it. Spawn a fresh `programmer` and hand it that existing worktree/branch (tell it not to
   `git worktree add`), with the "V2-8 remaining work" list below as its task. Then follow the merge checklist.

## In flight — slice V2-8 `v2-review-fixes` (PAUSED, programmer stopped)
Source of truth for the item list: plan.md "Review decisions from research/review-v2-slices-1b-6.md → slice V2-8".
Programmer's hand-off (2026-09-22):

**Done, committed on the branch (verified green when committed):** BLOCKER finding 1 (RESUME-202..205 via
`obtain_resumable_session`, self-test `resume_always_errors.py`); SHOULD-FIX findings 2–21 (incl. BATCH-206/207/208
+ CANCEL-204 → INFORMATIONAL, CONFIG-202/BATCH-203/204 over-assertions, batch-array unwrapping in all scans,
`conforming_full.py` terminal auth method + terminal updates, self-test cascade widening, enum constant sets moved
to `tck.v2.protocol` with a schema meta-test, aggregate read-loop deadlines); NITs 22, 23, 24, 31, 32; NIT 25 was
already fixed. NIT 23 intentionally changed ACP-AUTH-201/206 from vacuous PASS to SKIP when no `authMethods` is
advertised — this is a correct behaviour change, and is the cause of the self-test fallout below.

**Partial (in WIP commit `a517657`, NOT verified green):**
- NIT 26 (`test_batch.py` ACP-BATCH-201 reads until a response-shaped line) — code-complete, verified in isolation.
- `tests/v2/test_cli.py` self-test expectations after NIT 23: `_NO_AUTH_SKIP_IDS` and the inline `expected_skips`
  in `test_v2_conforming_agent_passes_everything` now include ACP-AUTH-201/206 (likely fixed; not re-run).
- **Next thing to do:** `test_terminal_env_duplicate_names_fails_auth_207_only` (`tests/v2/test_cli.py` ~line 1923)
  still asserts ACP-AUTH-201/202/206 PASS. Check whether AUTH-201/206's tests in `test_authentication.py`
  (`_initialized_agent(..., capabilities=None)`, lines ~57/79) connect with `capabilities.auth.terminal` advertised —
  the only connection on which `terminal_env_duplicate_names.py` shows its one `authMethods` entry. If not, those
  two ids now SKIP for that fixture and the assertion needs the same correction. Then re-run
  `uv run pytest -q tests/v2/test_cli.py` (last run before the two edits: 2 failed / 65 passed, 309 s — exactly the
  two sites above) and the full suite.

**V2-8 remaining work (not started):**
- NITs 27, 28 (citation lines ENUM-201/JSONRPC-001), 29 (double-count judgment call), 30 (PATCH-209 SKIP on
  refusal/cancelled), 33 (record_property counts + sessionId filter), 34 (vacuous assertions), 35
  (`--tck-allow-logout` help text), 36 (deferred-nits judgment call), 37 (v1 session/prompt guard port to v2 —
  moderate risk, programmer may skip with a note), 38 (5 fixture docstrings citing wrong id), 39
  (`vendor_stop_reason.py` stale docstring), 40, 41, 42 (comments/rename in `tests/v2/test_cli.py`).
- New fixture `tests/fixtures/agents/v2/v2_only_honest.py` + `tests/v1/test_cli.py` self-test proving
  `blocked_by_version_mismatch` is symmetric (a v2-only agent under `--protocol-version 1`); docs wording that it
  is "always false for v1" must go.
- `docs/cross-check.md` "spurious PASS" wording → a dual-router's `2` answer to the 65535 probe is a legitimate PASS.
- Re-run `scripts/cross-check.sh`; refresh `docs/cross-check.md` tables and `.github/workflows/ci.yml` `--expect`
  baselines (re-tiering and the new SKIPs may move rows).
- `AGENTS.md`/`README.md` drift: unscoped-cascade claims, id count 106, D3 rationale text, `conforming_full.py`
  PASS count (target 101/106).
- Rebase onto current `origin/v2-support` (still `f030d71` at pause — no rebase needed unless it moves), full
  `uv run pytest -q` (expect ≈250 passed, ≈400 s), push branch, report.

**Orchestrator merge checklist on report:** run suite from the worktree; smoke-run `conforming_full.py` under
`--protocol-version 2 --auth-method tck --allow-logout --cancel-prompt __hang__` and check tier counts; check a few
defect fixtures' FAIL sets; `scripts/cross-check-summary.py` OK against the refreshed baseline; `git diff --stat
v2-support...v2-review-fixes`; squash-merge into `v2-support`; suite on `v2-support`; push; remove worktree and
branch (local + remote). Then final rewrite of this file and `plan.md` to "done", and the user summary.

**User decisions still open (surface in the final summary):** merge `v2-support` → `main`; make v1's ACP-AUTH-004
`logout` opt-in like v2's `--allow-logout`; accept MANDATORY tier for "v2-only agent asked for 1 must answer 2"
(reference SDKs violate it); accept that v2 is Draft/alpha and will churn (re-vendor before any release); whether
to file `research/upstream-issues-v2.md` drafts.

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

## Done log (newest first)

**Done (2026-09-22): slice V2-7** (`9151515`) — cross-check v2 legs (`testy` dual build in separate
`--target-dir`; repo-authored `scripts/cross-check/python_v2_agent.py` on rc2), N-report summary with
per-report `--expect`, CI baselines, `docs/cross-check.md` v2 section. Baseline: testy_v2 CONFORMANT;
python_v2_agent FAILs BATCH-201/202 (SDK crash on arrays) + INIT-003/201/202 (native v2 rejects other
versions with -32602). 246 passed.

**Done (2026-09-22): slice V2-6** (`26bf0f2`) — PATCH-201..209, ENUM-201..203, META-201, EXT-201..203, re-cited
EXT-001/META-001/ERROR-001/SHUTDOWN-001/SCHEMA-002/STDERR-001/INFO-PARSE-001/INFO-INVALIDREQ-001; rich turn in
`conforming_full.py`; 10 fixtures; enum scan batch-unwrap fix. 239 passed (≈360 s). Registry 106 ids.
Notes: PATCH-206/207 never PASS (no terminal-update fixture); `custom_method_no_response.py` cascades into
BATCH-203/204/205 + ERROR-001 in an unscoped run (batch probes use `_tck/...` methods).

**Done (2026-09-22): slice V2-5** (`fac2649`) — AUTH-201..207, `--allow-logout`/`--tck-allow-logout`
(opt-in logout probe), `login_if_needed` helper fixing an auth-gate bypass in self-initializing v2 tests,
6 fixtures incl. v2 `gated_by_auth.py`. 229 passed (≈310 s).

**Done (2026-09-22): slice V2-4b** (`7183441`) — `-k` scoping in `tests/v2/test_cli.py`; suite 540 s → 293 s
(3 consecutive runs), no `src/tck/**` change, no xdist needed. Per-test subprocess spawn (~90 ms × ~73 tests)
is the inherent cost floor of an unscoped run.

**Done (2026-09-22): slice V2-4** (`8679393`) — RESUME-201..205, LIST-201..204, CLOSE-201/202, DELETE-201..203,
ADDDIRS-201/202, MCP-201/202 (INFORMATIONAL: use unobservable), CONFIG-201..206 (`inferred:configOptions`),
SESSION-203; `_session_with_history` try-three-routes helper; 7 fixtures; `conforming_full.py` extended.
220 passed (540 s). Review-pass item: confirm MCP rows' INFORMATIONAL tier vs plan's CAPABILITY intent.

**Done (2026-09-22): slice V2-3** (`150e8a5`) — CANCEL-201..208, TRANSPORT-201/203 + re-cited TRANSPORT-002,
JSONRPC-001..005 re-cited, BATCH-201..208, INFO-BATCH/CANCEL-20x; 13 fixtures incl. `emits_batch_updates.py`
(exposed + fixed two TCK bugs: dict-only SCHEMA-001 scan, `transcript.index` on synthetic batch entries);
`INFO-CONCURRENT-001`→`201`. 213 passed. Review-pass item: record-only ADVISORY rows (BATCH-206/207/208,
CANCEL-204) should probably be INFORMATIONAL.

**Done (2026-09-21): slice V2-2b** (`0da54fb`) — PROMPTCAP-001..003 re-gated, PROMPT-003 ADVISORY, PERM-201,
CLIENTCAP-201/202, INFO-CONCURRENT-001 (id to be renamed 201 in V2-3), INFO-UNKNOWNSESSION-001; fixtures incl.
`conforming_full.py` (v2 all-PASS), `asks_permission`, `calls_*`, `rejects_image_when_advertised`. 200 passed,
suite ≈210 s. Registry: 24 ids.

**Done (2026-09-21): slice V2-2a** (`01d48de`) — v2 `run_prompt`/`PromptTurn` driver (turn-end = idle with
stopReason or after observed running; bounded waits; trailing-update peek), rows PROMPT-201/203/205,
STATE-201/202/203 (all CAPABILITY on `capabilities.session` per plan.md tiering rule), 8 fixtures, SCHEMA-001
validates a full turn. 194 passed. Registry: 15 ids.

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
1. Resume V2-8 per "In flight" (fresh programmer on the existing worktree/branch), verify, squash-merge, push, cleanup.
2. Final `state.md`/`plan.md` rewrite to "done"; user summary with the open decisions above.
3. Merging `v2-support` → `main` only on the user's explicit decision.
