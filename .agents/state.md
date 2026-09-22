# State

**Last updated:** 2026-09-22 — v2 effort COMPLETE on `v2-support`; awaiting user decisions.
**Last commit pushed:** `0d373fa` on `v2-support`. No programmer worktrees or feature branches remain
(`git worktree list` = main checkout at `../acp-tck` [main] + this checkout [v2-support]).

## How to resume (fresh orchestrator)
1. Read `prompt.md` (mission: v2 side by side with v1, `common`/`v1`/`v2` layout, orchestrator-only role,
   per-slice worktree workflow), this file, `plan.md` (decision record + deferred nits). `research/*.md` is the
   only protocol truth the code may encode.
2. `.agents/skills/*/.repo` are gitignored pointers to upstream checkouts; if missing, copy from
   `/Users/eugene/Documents/JetBrains/projects/acp-tck/.agents/skills/*/.repo` (spec → `../agent-client-protocol`,
   rust → `../acp-rust-sdk`, python → `../acp-python-sdk`, a2a → `../a2a-tck`). `git pull --ff-only` in those
   checkouts fails ("multiple branches"); use `git fetch origin` and compare against `origin/main`.
3. Verify: `uv run pytest -q` → **252 passed** (≈7 min) and
   `uv run acp-tck --protocol-version 2 --cancel-prompt __hang__ --auth-method tck --allow-logout -- python
   tests/fixtures/agents/v2/conforming_full.py` → exit 0, CONFORMANT, 101/106 PASS
   (MANDATORY 19/19, CAPABILITY 51/51, ADVISORY 19 PASS + 1 SKIP, INFORMATIONAL 12 PASS + 4 SKIP).
4. There is no in-flight work. Next actions are all user decisions (below).

## Standing user decisions (2026-09-22)
- Spawn **ONLY ONE programmer at a time** (overrides `prompt.md`'s parallelism allowance).
- Subagent models per definition: `programmer` = Sonnet, `researcher` = Opus; never override.
- `Requirement(...).text=`/`citation=` literals that mention slices / review docs / D-decisions stay as-is.
- Comments/docstrings everywhere: concise; no slice numbers, review-report references or history narration.
  Mechanical passes are briefed shallow (grep/AST-locate, no whole-file reads, never fix out-of-scope failures).

## What is implemented and verified
- Layout: `src/tck/common/` (harness, report, requirement tiers, plugin core, `VersionSpec`), `src/tck/v1/`
  (56 ids, complete), `src/tck/v2/` (106 ids, ACP v2 Draft 2.0.0-alpha.5 @ spec 8f76d6c). CLI
  `--protocol-version {1,2}` (default 1), `--auth-method`, `--allow-logout` (v2). Tests: `tests/common`,
  `tests/v1`, `tests/v2`; fixtures `tests/fixtures/agents/v{1,2}/` (v2: conforming, conforming_full,
  one-defect fixtures incl. `v2_only_honest.py`, `resume_always_errors.py`). See `AGENTS.md` for usage.
- Cross-check (`scripts/cross-check.sh`, `docs/cross-check.md`, CI `--expect` baselines refreshed in V2-8):
  testy v1/echo_agent fail only the strengthened ACP-INIT-003; testy_v2 CONFORMANT; python_v2_agent fails
  BATCH-201/202 + JSONRPC-001/003/005 (SDK crash on batch arrays) + INIT-003/201/202 (rejects other
  versions with -32602); AUTH-201/206 SKIP for both v2 agents (no authMethods). `cross-check-summary.py` OK.
- Slice history (all squash-merged, newest first): `0d373fa` final comment trim; `e855bdb` V2-8 review fixes
  (see commit body); `70d9669` v1 self-test stderr-count fix; `176a056`/`2337d1c`/`52a7bd1` comment trimming;
  `9151515` V2-7 cross-check; V2-6 patches/enums (`26bf0f2`); V2-5 auth (`fac2649`); V2-4b perf (`7183441`);
  V2-4 session mgmt (`8679393`); V2-3 cancel/batch (`150e8a5`); V2-2a/2b prompt driver (`01d48de`,
  `0da54fb`); V2-1/1b/1c skeleton + init (`75bc188`…); V2-0/0b common/v1 split (`42d5587`).
- Research inputs: `research/acp-v2-*.md` (7 reports), `reference-sdks-v2-status.md`,
  `common-v1-v2-split-analysis.md`, reviews `review-v2-slices-0-1a.md`, `review-v2-slices-1b-6.md` (all
  findings resolved or recorded as deferred in `plan.md`), `upstream-issues-v2.md` (internal drafts, unfiled).

## Open user decisions (surface these)
1. Merge `v2-support` → `main` (explicit user decision per `prompt.md`; `main` untouched so far).
2. v1 suite has no `VERSION-MISMATCH` SKIP guard: a v2-only agent under `--protocol-version 1` hard-FAILs six
   non-capability v1 ids (INIT-002/004, META-001, PROMPT-001, SCHEMA-001/002) instead of SKIPping as `AGENTS.md`
   describes. `tests/v1/test_cli.py::test_v2_only_agent_under_protocol_version_1_is_blocked_by_version_mismatch`
   pins the current behaviour. Port the v2 guard to v1 (small slice) or document the asymmetry.
3. Make v1 `ACP-AUTH-004` `logout` opt-in like v2's `--allow-logout`.
4. Accept MANDATORY tier for "v2-only agent asked for 1 must answer 2" (both reference SDKs violate it by design).
5. v2 is Draft/alpha — re-vendor `src/tck/v2/schema/` and re-check citations before any release.
6. Whether to file the `research/upstream-issues*.md` drafts upstream.
7. Deferred nits in `plan.md` ("Deferred nits — refreshed 2026-09-22"): unused `VersionSpec` fields, test
   package `__init__.py`, CANCEL-208/CLOSE-202 double count, v1 nits N12/N20/N9.

## Known blockers
None. Suite green; no worktrees; nothing unpushed.
