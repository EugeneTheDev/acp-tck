# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
**v1**. It launches an agent implementation as a stdio subprocess, drives it through the protocol
-- initialize, session lifecycle, prompt turns, cancellation, error handling, transport hygiene --
and reports which requirements pass, fail, don't apply, or were never exercised.

## Install & run

No install needed, via `uvx`:

```
uvx acp-tck -- <agent command> [agent args...]
```

Or from a checkout of this repo:

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
- `INFORMATIONAL` -- spec silent, or reference implementations disagree. Reported only.

Each test produces one of `PASS` / `FAIL` / `SKIPPED`; a setup/teardown error (including a
harness-level agent timeout or crash) is reported as `FAIL`. A requirement's status is the worst
across every test bound to it (`FAIL` > `PASS` > `SKIPPED`); a requirement no test ever ran is
`NOT_TESTED` -- deliberately counted as a failure for `MANDATORY`/`CAPABILITY` tiers, so a dead
agent that never gets past `initialize` can't score 100% by starving every other check of a
record.

**Verdict:** `conformant` is `true` iff there is no `MANDATORY` `FAIL`, no `MANDATORY`
`NOT_TESTED`, no `CAPABILITY` `FAIL`, and the run was not `blocked_by_auth` (i.e. no
session-dependent test was skipped because the agent requires authentication and no
`--auth-method` was given -- see "Options" above).

**Exit code:** `0` iff `conformant`, `1` otherwise (including "the agent never responded to
anything" -- every `MANDATORY` requirement ends up `FAIL`/`NOT_TESTED`, but the run still
completes and still writes a report). No agent command after `--` is a usage error (`2`).

## Protocol scope

ACP **v1 only** (`PROTOCOL_VERSION = 1`, pinned in `tck.protocol`). Batch JSON-RPC arrays,
pre-`initialize` request gating, and v2 prompt-lifecycle changes are all out of scope.
Capability-conditional coverage now includes `session/load`, `session/resume`, `session/list`,
`session/delete`, `session/close`, `additionalDirectories`, session `modes`/`configOptions`,
`promptCapabilities` (`image`/`audio`/`embeddedContext`), and the authentication surface
(`authMethods`, `authenticate`, `logout`); MCP/terminal/fs capabilities are still to come -- see
`AGENTS.md` for the current requirement registry and what's implemented so far.

## Contributing

See [`AGENTS.md`](AGENTS.md) for the package layout, the harness/validation/plugin internals,
how to add a new requirement + test, and the conventions this repo follows (`uv`-only dependency
management, exact pins, `.agents/` as the project's own planning workbench).
