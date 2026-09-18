# State

**Last updated:** 2026-09-18 (session 2, slice 8 + review of slices 7–7b in flight)
**Last commit pushed:** see `git log -1` (each slice commits this file)

## How to resume (fresh orchestrator)
1. Read `prompt.md`, this file, `plan.md`. Research reports in `research/` are the only protocol truth
   the code may encode. Reviews are in `research/review-*.md`.
2. Verify the tree: `uv run pytest -q` (≈118 s, run in background; expect 125 passed) and
   `uv run acp-tck --cancel-prompt __hang__ --auth-method tck -- python tests/fixtures/agents/conforming_full.py`
   (expect exit 0, VERDICT: CONFORMANT, only ACP-AUTH-005 SKIPPED).
3. Continue with **Slice 8** (see "Next actions").

## Deliverable shape (decided)
See `plan.md` § "Decided deliverable shape". Summary: installable `acp-tck` package with the
conformance suite shipped inside `src/tck/conformance/`; CLI `acp-tck [opts] -- <agent cmd>` runs
pytest programmatically with `-p tck.plugin`; agent under test is a stdio subprocess, one fresh
process per test; hand-rolled asyncio NDJSON raw harness (no Python-SDK runtime dependency);
vendored spec JSON schema v1 validated via `jsonschema`; requirement registry with tiers
mandatory / capability:<path> / advisory / informational; four-status verdict PASS/FAIL/SKIPPED/NOT
TESTED; console + JSON report; verdict-based exit code; self-tests in repo-only `tests/` against
pure-Python fixture agents. Protocol scope v1 only (`PROTOCOL_VERSION = 1`).

## Research completed (all in `.agents/research/`)
- `acp-v1-protocol-surface.md` — 46 requirements with tiers; baseline MUST set; version negotiation;
  docs bugs (`currentModeId`; `error.mdx` stub).
- `acp-v1-transport-and-jsonrpc.md` — framing MUSTs, error codes, batch = v2 only, SDK divergence on
  malformed input (informational), no shutdown method.
- `a2a-tck-structure.md` — design inspiration (registry, four-status verdict, ship tests in wheel).
- `reference-sdks-as-harness.md` — why raw harness; `testy`/`echo_agent.py` as fixtures.
- `acp-v1-authentication.md` — v1 never requires `-32000` gating; auth is surface checks + `--auth-method`.
- `acp-v1-session-capabilities.md` — per-method shapes/orderings for load/resume/list/delete/close/
  additionalDirectories/modes/configOptions/prompt caps; capability encodings (boolean `=== true` vs
  object marker non-null); 20 must-NOT-assert items.
- `testy-cross-check.md` — how to build/run Rust `testy` (17 s build, no CLI, scenarios by prompt text,
  `--cancel-prompt wait_for_cancel`); measured CONFORMANT; found INIT-003 false negative (fixed 6a/7b).
- `spec-drift-check.md` — upstream HEAD d3c1dd7: `schema/v1/` byte-identical to vendored 6d08f41 → no
  re-vendor; citations stay pinned at 6d08f412; three citation text fixes pending (slice 8).
- `review-slices-1-4.md`, `review-slices-5-6.md` — code reviews; all blockers/should-fix addressed in
  slices 5b and 7b (deferred nits N12, N20 listed below).

## Implemented and verified (all on `main`, suite green: 125 passed ≈118 s)
Registry: **56 requirements** in `src/tck/requirements.py` (see `AGENTS.md` for the catalogue).
- Harness `src/tck/harness/` — `AgentLaunch` (command, cwd, env overrides, timeouts, `max_line_bytes`
  64 MiB, `close_grace`), `AgentProcess` (process-group spawn, raw/JSON send with drain deadline,
  lossless oversize reads, deadline reads, two-way transcript incl. malformed lines, stderr capture,
  `close()` drains stdout then close-stdin→SIGTERM→SIGKILL).
- `src/tck/protocol.py` (`PROTOCOL_VERSION`, `SCHEMA_REVISION`, error codes, `STOP_REASONS`, method sets
  from meta.json), `src/tck/validation.py` (schema validation; `find_unknown_root_keys`),
  `src/tck/schema/v1/` vendored @ 6d08f412.
- `src/tck/plugin.py` — options `--tck-agent-cmd/-cwd/-env/-timeout/-startup-timeout/-test-timeout/
  -cancel-prompt/-auth-method/-close-grace/-report-json`; markers `requirement`, `capability(path,
  boolean=)`; async tests via `pytest_pyfunc_call` + watchdog; autouse session-scoped
  `agent_initialize_result`; per-test outcome collector; tier-grouped table with INFORMATIONAL notes;
  JSON report; verdict → `session.exitstatus` (not for `--collect-only`); xfail forbidden.
- `src/tck/report.py` — `Status`, `TestOutcome`, `RequirementResult`, `Verdict` (`conformant`,
  `blocked_by_auth`, tier counts), `Report.to_dict()`; transcript cap 400 entries / 4 kB per line.
- `src/tck/conformance/` — `_helpers.py` (`connected_agent` with auto-authenticate, `new_session`,
  `run_prompt` mock client with `on_action` hook, `skip_if_auth_gated`), tests: transport, jsonrpc,
  initialize, session, prompt, cancel, session_capabilities, session_config, prompt_capabilities,
  authentication, client_capabilities, extensibility, diagnostics, informational.
- CLI `src/tck/__init__.py` (`acp-tck [options] -- <cmd>`, `--version`, `--help`), `src/tck/__main__.py`.
- Fixtures `tests/fixtures/agents/` (~35 scripts; `_base.py` conforming core; `conforming.py`,
  `conforming_full.py`, `gated_by_auth.py`, plus single-defect agents). Self-tests `tests/`
  (`test_harness`, `test_validation`, `test_registry`, `test_plugin`, `test_report`, `test_cli`).
- Docs: `AGENTS.md` (contributor guide, catalogue), `README.md` (user guide).

## In flight
- **Programmer — Slice 8b** (fixes from `review-slices-7.md`: send_raw OSError→AgentExited, informational probes use quiet_period, close() checks exit per stage, -k hint, AUTH-001 advisory, AUTH-003 inferred capability, EXT-001 assertion scope, nits).

Slice 8 done and committed: `scripts/cross-check.sh` (builds testy `--no-default-features`, runs TCK with
`--cancel-prompt wait_for_cancel`; runs echo_agent via `uv run --no-project --with agent-client-protocol==1.0.0rc1`),
`scripts/cross-check-summary.py` (`--expect-only-mandatory-fail`), `docs/cross-check.md` (table + explanations).
CI: `.github/workflows/ci.yml` — `test` job (uv, Python 3.14) + informational `cross-check` job (clones upstream at
pinned SHAs, cargo cache). pyproject has description + urls; license deliberately not set (user decision). Result: both upstream agents
NOT CONFORMANT only because of INIT-003 (they echo 65535) and advisory INIT-004; echo_agent also fails advisory
JSONRPC-004 (SDK returns `result: null` for unknown `_` methods). No TCK bug found. Spot checks that completed before the
pause: full suite 125 passed; `conforming_full.py` and `conforming.py` full runs CONFORMANT. Orchestrator also
re-ran: `gated_by_auth.py --auth-method wrong` → exit 1 blocked by authentication; `supports_v1_and_v2.py`
INIT-003 PASS. Programmer-reported only: `echoes_any_version.py` INIT-003 FAIL; `rejects_second_initialize.py`
CONFORMANT; `--collect-only` exit 0.

## Open questions / deferred
- Deferred nits from review-slices-5-6: N12 (pytester-based plugin test), N20 (O(n²) `transcript.index`).
- Citation text fixes from `spec-drift-check.md` (MODES-002 wording, LOAD-003 cite `ac82df6`,
  INFO-UNKNOWNSESSION-001 path) → slice 8.
- Req 10 (stdio MCP MUST) deliberately untested (not client-observable).
- v0.1 release/tag: decide after slice 8 and a final review pass.

## Next actions
1. Read `review-slices-7.md` when it lands; spawn slice 8b (fix blockers/should-fix + release readiness:
   pyproject metadata, license decision needs the user).
2. Decide v0.1 tag; optional GitHub Actions workflow (pytest on 3.14; cross-check job with cached cargo).
3. Consider filing upstream: INIT-003 echo behaviour in testy/echo_agent; `error.mdx` stub; baseline
   content-type discrepancy (initialization.mdx vs content.mdx).
