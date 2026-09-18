# State

**Last updated:** 2026-09-18 (session 1, after slice 3)
**Last commit pushed:** see `git log -1` (each slice commits this file)

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

- **Slice 2 — schema + validation** (32 tests green total): `src/tck/schema/v1/{schema.json,meta.json,VENDORED.md}`
  vendored verbatim from spec @ 6d08f41; `src/tck/protocol.py` (`PROTOCOL_VERSION = 1`, error-code constants,
  `STOP_REASONS`, `AGENT_METHODS`/`CLIENT_METHODS`/`*_NOTIFICATIONS` derived from meta.json + x-method annotations);
  `src/tck/validation.py` (`ValidationIssue`, `validate_agent_message`, `validate_agent_response`; Draft 2020-12;
  `null` accepted for all-optional object responses like `session/load`; `_`-prefixed methods skipped). Runtime dep
  `jsonschema==4.26.0`. Schema root has three branches: Agent, Client, ProtocolLevel (`$/cancel_request`).

- **Slice 3 — registry, plugin, CLI, first conformance tests** (49 tests green): `src/tck/requirements.py`
  (`Tier`, `Requirement`, `REGISTRY`, 12 requirements ACP-TRANSPORT-001/002, ACP-JSONRPC-001..005,
  ACP-INIT-001..004, ACP-SCHEMA-001); `src/tck/plugin.py` (`--tck-agent-cmd/-cwd/-env/-timeout/-startup-timeout`,
  `requirement`/`capability` markers, async tests via `pytest_pyfunc_call`, `agent_launch` + session-scoped
  `agent_initialize_result` fixtures, transcript+stderr attached to failure reports, `RequirementRecord`
  collector, tier-grouped terminal table with NOT TESTED; JSON report + verdict exit code are TODO slice 5);
  `src/tck/conformance/{_helpers.py,test_transport.py,test_jsonrpc.py,test_initialize.py}`;
  CLI `acp-tck [--agent-cwd] [--agent-env K=V] [--timeout] [--startup-timeout] [-k] [-v] -- <cmd>` plus
  `python -m tck`; defect fixtures `wrong_id_echo.py`, `version_mismatch_errors.py`, `result_and_error.py`,
  `answers_notifications.py`, `unknown_method_no_error.py`; `tests/test_registry.py`, `tests/test_cli.py`
  (subprocess end-to-end). Verified: conforming → exit 0, 12 PASS; banner → exit 1, TRANSPORT-001/002 +
  SCHEMA-001 FAIL.

## In flight
- **Programmer — Slice 4** (session/new, prompt, cancel mandatory tests + defect fixtures).


## Open questions / blockers
- (none blocking) Auth research landed: see plan.md "Decisions from follow-up research".
- Transcript format choice (conductor `.jsons` compatibility) before slice 5.

## Next actions
1. On slice 4 return: verify (`uv run pytest`, CLI against conforming + new defect fixtures), commit + push.
2. Spawn slice 5 (JSON report, verdict-based exit code, meta-tests).
