# acp-tck

[![CI](https://github.com/EugeneTheDev/acp-tck/actions/workflows/ci.yml/badge.svg)](https://github.com/EugeneTheDev/acp-tck/actions/workflows/ci.yml)

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP).
Targets **v1** by default, with an opt-in, still-skeleton **v2** (Draft) suite via
`--protocol-version 2`. It launches an agent implementation as a stdio subprocess, drives it through the protocol
-- initialize, session lifecycle, prompt turns, cancellation, error handling, transport hygiene --
and reports which requirements pass, fail, don't apply, or were never exercised.

## Install & run
```
uv run acp-tck -- <agent command> [agent args...]
```

For example, against the bundled self-test fixture:

```
uv run acp-tck -- python tests/fixtures/agents/conforming.py
```

Everything after `--` is the agent's own command line, launched as a stdio subprocess -- a fresh
process per test, so one crash can't cascade into unrelated failures.

## Options

- `--protocol-version {1,2}` -- which protocol version's conformance suite to run (default 1).
  `2` runs the ACP v2 (Draft) suite, which is currently a skeleton covering only `initialize`
  (`ACP-INIT-001`, `ACP-INIT-201`) -- see `AGENTS.md`'s `src/tck/v2/` layout entry.
- `--agent-cwd DIR` -- working directory for the agent (default: inherit).
- `--agent-env KEY=VAL` -- environment variable overlaid on the agent's process; repeatable.
- `--timeout S` -- per-response deadline in seconds (default 30).
- `--startup-timeout S` -- deadline for the agent's first response (default 30).
- `--test-timeout S` -- wall-clock deadline for a single test, regardless of its own internal
  timeouts (default 120). Guards against a test that would otherwise hang indefinitely (e.g. an
  agent that stops responding partway through a multi-step exchange); on expiry the test fails
  with a message identifying the watchdog, and the agent process is still shut down normally.
- `--cancel-prompt TEXT` -- prompt text the cancellation tests send, instead of the short text
  every other prompt test uses. Pick something that keeps a real agent busy long enough for
  `session/cancel` to land while the turn is still in flight -- otherwise those tests report
  `SKIPPED` ("cancellation not exercised"), which means exactly that, not a conformance failure.
- `--auth-method ID` -- authenticate with this method id (one advertised in `initialize`'s
  `authMethods`) right after `initialize`, before any session-dependent test runs. Needed for
  any agent that gates `session/new` behind authentication -- without it, session-dependent
  tests report `SKIPPED` with an "AUTH-GATED" hint and the run is forced `NOT CONFORMANT`, since
  those requirements were never actually exercised.
- `--close-grace S` -- grace period in seconds budgeted at each stage of the shutdown ladder
  (close stdin, then SIGTERM, then SIGKILL) when tearing down the agent process after a test
  (default 2.0). Each stage stops early as soon as the agent actually exits, rather than always
  waiting out the full grace period, so raising this only matters for a slow-to-exit agent.
- `--report-json PATH` -- write the full JSON report (see below).
- `-k EXPR` -- run only tests matching a pytest `-k` expression.
- `-v` -- verbose pytest output.
- `--version`, `--help`.

## Reading the report

The terminal output groups every requirement by tier and prints its aggregated status, followed
by per-tier counts and a `VERDICT: CONFORMANT` / `VERDICT: NOT CONFORMANT (...)` line.
`--report-json PATH` writes the same information as JSON, plus failure diagnostics:

- `agent_command`, `agent_info`, `agent_capabilities`, `protocol_version`, `schema_revision`,
  `tck_version`, `started_at`/`finished_at`.
- `requirements`: one entry per requirement, always -- including ones no test ever ran
  (`status: "NOT_TESTED"`) -- with its tier, spec citation, aggregated status, and every bound
  test's outcome (`nodeid`, `status`, `message`, `duration_s`, `properties`). A `FAIL` outcome
  additionally carries `transcript` (the full wire traffic for that test) and `stderr`
  (truncated to the last 20 kB), so a failure is diagnosable from the JSON alone.
- `verdict`: `{"conformant": bool, "blocked_by_auth": bool, "tier_counts": {...}}`.

## The tier / status / verdict model

Every requirement has a **tier**:

- `MANDATORY` -- a spec MUST. A failure or an untested `MANDATORY` requirement makes the run
  non-conformant.
- `CAPABILITY` -- only applies if the agent advertised the relevant capability in `initialize`;
  otherwise it's reported `SKIPPED` ("not applicable"), which does **not** affect conformance.
  If the agent *did* advertise it, though, a failure does count against conformance -- advertised
  capabilities must work.
- `ADVISORY` -- a spec SHOULD. Always reported, never affects the verdict.
- `INFORMATIONAL` -- spec silent, or reference implementations disagree. The test never asserts on
  the probed behaviour itself; it records what was observed via `record_property`, and that note
  is surfaced alongside the status in both the terminal table (e.g.
  `ACP-INFO-PARSE-001   PASS  (silent; conn after: usable (sessionId=...))`) and the JSON report's
  `properties` field. It can still `FAIL` if the prerequisite handshake it rides on top of (e.g.
  `initialize`, or `session/new` for the unknown-`sessionId` probe) itself fails -- that is a real
  conformance problem the probe correctly surfaces, not a probe bug. Never affects the verdict
  either way.

Each test produces one of `PASS` / `FAIL` / `SKIPPED`; a setup/teardown error (including a
harness-level agent timeout or crash) is reported as `FAIL`. A requirement's status is the worst
across every test bound to it (`FAIL` > `PASS` > `SKIPPED`); a requirement no test ever ran is
`NOT_TESTED` -- deliberately counted as a failure for the `MANDATORY` tier (see "Verdict" below),
so a dead agent that never gets past `initialize` can't score 100% by starving every other check
of a record.

**Verdict:** `conformant` is `true` iff there is no `MANDATORY` `FAIL`, no `MANDATORY`
`NOT_TESTED`, no `CAPABILITY` `FAIL`, and the run was not `blocked_by_auth` (i.e. no
session-dependent test was skipped because the agent requires authentication and no
`--auth-method` was given -- see "Options" above).

**Exit code:** `0` iff `conformant`, `1` otherwise (including "the agent never responded to
anything" -- every `MANDATORY` requirement ends up `FAIL`/`NOT_TESTED`, but the run still
completes and still writes a report). No agent command after `--` is a usage error (`2`).

## Protocol scope

ACP **v1** (`PROTOCOL_VERSION = 1`, pinned in `tck.v1.protocol`) is the default and by far the
more complete suite -- the codebase is structured as a version-agnostic core plus one package
per protocol version (`src/tck/common/` + `src/tck/v1/` + `src/tck/v2/`, see `AGENTS.md`) so
each version's suite does not require forking the harness, report model, or pytest plugin.
Capability-conditional coverage now includes `session/load`, `session/resume`, `session/list`,
`session/delete`, `session/close`, `additionalDirectories`, session `modes`/`configOptions`,
`promptCapabilities` (`image`/`audio`/`embeddedContext`), and the authentication surface
(`authMethods`, `authenticate`, `logout`); MCP/terminal/fs capabilities are still to come -- see
`AGENTS.md` for the current requirement registry and what's implemented so far.

ACP **v2** (Draft, schema version `2.0.0-alpha.5` at the vendored pin) is available via
`--protocol-version 2`, but is currently only a skeleton: `initialize` and version negotiation
(`ACP-INIT-001`, `ACP-INIT-201`). Batch JSON-RPC arrays and v2's other prompt-lifecycle changes
are validated at the schema level (`tck.v2.validation`) but have no dedicated conformance tests
yet -- see `src/tck/v2/`'s entry in `AGENTS.md`'s "Layout" for exactly what's covered.

Also covered: `MANDATORY` negative tests asserting the agent never calls `fs/*`, `terminal/*`, or
`elicitation/create` during a prompt turn when the client didn't advertise the matching capability
(`ACP-CLIENTCAP-001`/`002`/`003`); a custom-methods-and-hygiene family -- `ACP-EXT-001`
(`MANDATORY`: a `_`-prefixed custom method must get *some* response, result or error; distinct
from `ACP-JSONRPC-004`'s `ADVISORY` concern about the specific `-32601` code for an unrecognised
method in general) plus `ADVISORY` `_meta` passthrough, unknown top-level response keys, error
message shape, and shutdown promptness; and the `INFORMATIONAL` family above covering malformed
JSON, structurally-invalid requests, unknown session ids, and stderr volume -- areas where the
spec is silent or reference agents disagree.

## Cross-checking against upstream agents

`scripts/cross-check.sh` runs this TCK against two independently implemented agents -- the Rust
SDK's `testy` fixture and the Python SDK's `examples/echo_agent.py` -- as a sanity check that the
TCK's own plumbing isn't systematically wrong. It needs a Rust toolchain and local checkouts of
both SDKs, so it's a manual/CI step rather than part of `uv run pytest`; see `AGENTS.md`
"Cross-checking against upstream agents" for prerequisites and usage, and `docs/cross-check.md`
for the latest result table with explanations of every non-`PASS`.

## Contributing

See [`AGENTS.md`](AGENTS.md) for the package layout, the harness/validation/plugin internals,
how to add a new requirement + test, and the conventions this repo follows (`uv`-only dependency
management, exact pins, `.agents/` as the project's own planning workbench).

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
