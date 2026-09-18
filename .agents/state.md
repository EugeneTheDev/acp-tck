# State

**Last updated:** 2026-09-18 (session 1, after research round 1)
**Last commit pushed:** see git log (slice 1 committed together with this file)

## Deliverable shape (decided)
See `plan.md` § "Decided deliverable shape". Summary: installable `acp-tck` package with the
conformance suite shipped inside `src/tck/conformance/`; CLI `acp-tck [opts] -- <agent cmd>` runs
pytest programmatically with `-p tck.plugin`; agent under test is a stdio subprocess, one fresh
process per test; hand-rolled asyncio NDJSON raw harness (no Python-SDK runtime dependency);
vendored spec JSON schema v1 validated via `jsonschema`; requirement registry with tiers
mandatory / capability:<path> / advisory / informational; four-status verdict PASS/FAIL/SKIPPED/NOT
TESTED; console + JSON report; self-tests in repo-only `tests/` against pure-Python fixture agents.
Protocol scope v1 only (`PROTOCOL_VERSION = 1`).

## Research completed (authoritative inputs; all cite spec @ 6d08f41, rust-sdk @ b28b8ad, python-sdk @ c1004f8)
- `.agents/research/acp-v1-protocol-surface.md` — 46 requirements with tiers; baseline MUST set is
  `initialize`, `session/new`, `session/prompt`, `session/cancel`, ability to send `session/update`.
  Version mismatch → success result carrying agent's latest version, never an error. Docs bug:
  `current_mode_update` uses `currentModeId` in schema (schema wins). `error.mdx` is a stub → no
  mandatory error-code tests for unknown session / unadvertised methods.
- `.agents/research/acp-v1-transport-and-jsonrpc.md` — framing MUSTs (UTF-8, one JSON-RPC message
  per line, no embedded newlines, nothing else on stdout, stderr free). Error codes from schema crate.
  Batch = v2 only. Malformed-JSON handling: Rust replies −32700, Python silently drops → informational.
  No shutdown method; stdin EOF exit is a warning-level check only.
- `.agents/research/a2a-tck-structure.md` — design ideas: requirement registry, four-status verdict,
  crash safety-net hook, meta-tests, ship tests in wheel.
- `.agents/research/reference-sdks-as-harness.md` — Python SDK typed layer unsuitable for edge cases;
  Rust `testy` and `examples/echo_agent.py` are conforming fixtures but echo protocolVersion (unsafe
  for negotiation tests); non-conforming fixtures must be hand-written raw-byte scripts.

## Implemented and verified
- **Slice 1 — harness core** (13 tests green, `uv run pytest -q`): `src/tck/harness/{process,transcript}.py`
  (`AgentLaunch`, `AgentProcess`, `TranscriptEntry`, `AgentTimeout`, `AgentExited`; process-group spawn,
  raw/JSON send, deadline reads, full two-way transcript, stderr capture, close-stdin→SIGTERM→SIGKILL
  ladder). Fixture agents in `tests/fixtures/agents/` (`_base.py`, `conforming.py`, `banner_on_stdout.py`,
  `stderr_chatter.py`, `never_responds.py`, `exits_immediately.py`; conforming agent supports a `__hang__`
  prompt for cancel tests and a `_tck/env` extension method). `AGENTS.md` documents layout/API/conventions.
  `pyproject.toml`: `pytest==9.1.1` runtime dep, `[tool.uv.build-backend] module-name = "tck"`. Tests use
  `asyncio.run` directly (no pytest-asyncio). `acp-tck` CLI is a stub exiting 2.

## In flight
- **Programmer — Slice 2** (vendored v1 JSON schema + `tck/protocol.py` + `validate_agent_message`).
- **Researcher — authentication semantics** → `.agents/research/acp-v1-authentication.md`.

## Open questions / blockers
- Auth `-32000` semantics (research in flight; blocks auth tests only, not slices 1–5).
- Transcript format choice (conductor `.jsons` compatibility) before slice 5.

## Next actions
1. On slice 2 return: verify (`uv run pytest`, `git diff --stat`), commit + push.
2. Spawn slice 3 (requirement registry + pytest plugin + CLI + transport/initialize conformance tests).
3. Read auth research; fold into registry when reached.
