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
- Slice 1 — harness core + fixture agents + 13 unit tests (`src/tck/harness/`, `tests/`).
- Research round 1: `research/acp-v1-protocol-surface.md`, `research/acp-v1-transport-and-jsonrpc.md`,
  `research/a2a-tck-structure.md`, `research/reference-sdks-as-harness.md`.

## In progress
- **Slice 2 — vendored schema + validation** (programmer). See "Next slices" item 2.
- **Research: authentication semantics** → `research/acp-v1-authentication.md` (does an agent
  advertising `authMethods` have to return `-32000` before `authenticate`?).

## Next slices (in order)
2. Vendored v1 JSON schema + `tck/protocol.py` constants + `validate_agent_message()` + tests.
3. Requirement registry + pytest plugin (options, per-test agent fixture, `@requirement` marker,
   result collector) + CLI wiring + first conformance tests: transport hygiene (T1/T5/T7/J1–J4)
   and `initialize` (Reqs 3, 5, 6; version mismatch → success with agent's latest).
4. Session/prompt/cancel mandatory tests (Reqs 9, 24, 25, 26, 28) + non-conforming fixtures for each.
5. Reporting (console + JSON, four-status verdict, exit code) + meta-tests over the registry.
6. Capability-conditional tests (`loadSession` replay ordering, `session/resume`, `session/list`,
   `session/delete`, `session/close`, prompt content caps) + client-capability negative tests
   (fs/terminal/elicitation/boolean config never called when not advertised).
7. Advisory/informational tier (unknown method −32601, error shape, stdin-EOF exit, `_meta` round-trip,
   `_ext` method response).

## Open questions
- Authentication `-32000` semantics (research in flight).
- Unknown `sessionId` error code: unspecified in v1 → informational only (decided, no research needed).
- Is a second concurrent `session/prompt` per session legal in v1? Route to research before slice 4
  only if a test would depend on it (currently none planned).
- Whether to emit transcripts in the conductor `.jsons` trace format (cheap to decide before slice 5).
