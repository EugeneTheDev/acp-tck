# Plan

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
- **Slice 7b — hardening from review-slices-5-6** (programmer).

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
