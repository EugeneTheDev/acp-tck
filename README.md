# acp-tck

[![CI](https://github.com/EugeneTheDev/acp-tck/actions/workflows/ci.yml/badge.svg)](https://github.com/EugeneTheDev/acp-tck/actions/workflows/ci.yml)

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP).
It launches an agent implementation as a stdio subprocess, drives it through the protocol --
initialize, session lifecycle, prompt turns, cancellation, error handling, transport hygiene --
and reports which requirements pass, fail, don't apply, or were never exercised.

Targets **v1** by default, with an opt-in **v2** (Draft) suite via `--protocol-version 2`. 
See ["What is covered"](#what-is-covered) below for the exact per-version breakdown.

## Install & run
```
uv run acp-tck [args] -- <agent command> [agent args...]
```

For example, against the bundled self-test fixture:

```
uv run acp-tck -- python tests/fixtures/agents/v1/conforming.py
```

Everything after `--` is the agent's own command line, launched as a stdio subprocess -- a fresh
process per test, so one crash can't cascade into unrelated failures.

## Options

- `--protocol-version {1,2}` -- which protocol version's conformance suite to run (default 1);
  see ["What is covered"](#what-is-covered) for what each suite checks. If the agent under test
  never actually negotiates the requested version, version-dependent tests are `SKIPPED` with a
  `VERSION-MISMATCH` hint and the run is forced `NOT CONFORMANT` -- symmetrically for both
  directions (a v1-only agent run under `--protocol-version 2`, or a v2-only agent run under
  `--protocol-version 1`).
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
- `--allow-logout` -- (v2 only) opt in to actually calling `auth/logout` against the agent under
  test. Off by default because it may revoke the operator's own credentials for whatever account
  the agent is authenticated as; without it, the logout requirement (`ACP-AUTH-203`) reports
  `SKIPPED` instead of exercising the method. A SKIPPED `CAPABILITY`-tier requirement doesn't
  affect conformance -- only a *failed* one does -- so omitting `--allow-logout` never by itself
  makes a run NOT CONFORMANT.
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
- `verdict`: `{"conformant": bool, "blocked_by_auth": bool, "blocked_by_version_mismatch": bool,
  "tier_counts": {...}}`.

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
`NOT_TESTED`, no `CAPABILITY` `FAIL`, the run was not `blocked_by_auth` (i.e. no
session-dependent test was skipped because the agent requires authentication and no
`--auth-method` was given -- see "Options" above), and not `blocked_by_version_mismatch` (i.e. no
version-dependent test was skipped because the agent under test never actually negotiated the
`--protocol-version` this run targets -- checked for both v1 and v2 runs).

**Exit code:** `0` iff `conformant`, `1` otherwise (including "the agent never responded to
anything" -- every `MANDATORY` requirement ends up `FAIL`/`NOT_TESTED`, but the run still
completes and still writes a report). No agent command after `--` is a usage error (`2`).

## Protocol scope

The codebase is structured as a version-agnostic core plus one package per protocol version
(`src/tck/common/` + `src/tck/v1/` + `src/tck/v2/`, see `AGENTS.md`), so each version's suite does
not require forking the harness, report model, or pytest plugin. ACP **v1**
(`PROTOCOL_VERSION = 1`, pinned in `tck.v1.protocol`) is the default and the smaller, mature suite
(56 requirements: 21 `MANDATORY` / 19 `CAPABILITY` / 12 `ADVISORY` / 4 `INFORMATIONAL`). ACP **v2**
(Draft, schema version `2.0.0-alpha.5` at the vendored pin) is available via `--protocol-version 2`
and is actually the larger suite (106 requirements: 19 `MANDATORY` / 51 `CAPABILITY` / 20
`ADVISORY` / 16 `INFORMATIONAL`) -- not because it's ahead of v1, but because most of its
session-lifecycle/prompt/cancel methods are tiered `CAPABILITY` (gated on `capabilities.session`)
where v1 tiers the same methods `MANDATORY`. The one genuine coverage gap is MCP/terminal/
filesystem capability surfaces, which is v1's own backlog item, not a v2 shortfall (v2's protocol
removed `fs/*`/`terminal/*` entirely). For the precise, current requirement set,
`src/tck/v{1,2}/requirements.py` is the source of truth; the summary below won't drift the way
prose does, but treat it as a snapshot rather than a guarantee.

## What is covered

### v1

- `initialize` handshake and version negotiation, including the strengthened unsupported-version
  probe (`ACP-INIT-003`)
- Session lifecycle: `session/new`, `session/load`, `session/resume`, `session/list`,
  `session/delete`, `session/close`, `additionalDirectories`
- `session/prompt` turns and `session/cancel`, including the cancellation race handling described
  above
- Session `modes` and `configOptions`
- Prompt content capabilities (`image`/`audio`/`embeddedContext`)
- Authentication surface: `authMethods`, `authenticate`, `logout`
- Client-capability negatives: the agent must never call `fs/*`, `terminal/*`, or
  `elicitation/create` when the client didn't advertise the matching capability
  (`ACP-CLIENTCAP-001`/`002`/`003`)
- Extensibility and hygiene: `_`-prefixed custom methods must get a response (`ACP-EXT-001`),
  `_meta` passthrough, unknown top-level response keys, error message shape, shutdown promptness
- Transport/JSON-RPC hygiene: stdio framing, envelope validation, unrecognised-method handling
- `INFORMATIONAL` probes (reported only, spec silent or reference agents disagree): malformed
  JSON, structurally-invalid requests, unknown session ids, stderr volume
- Not yet covered: MCP/terminal/filesystem capability surfaces

### v2

- `initialize`/version-negotiation baseline, including a v2-only agent's required behavior when
  asked for `1`
- `session/new` baseline
- Core `session/prompt` turn/`state_update` lifecycle (turn completion via `state_update`, not the
  prompt response) and `session/cancel` (confirmed via a terminating `cancelled` idle
  `state_update`)
- Prompt content capabilities (`image`/`audio`/`embeddedContext`)
- `session/request_permission` flow
- Agent -> client method rules (including the `_`/`$/`-prefix extensibility rule)
- stdio transport, the JSON-RPC envelope, and batching
- Session management: `session/resume` (including replay ordering), `session/list`,
  `session/close`/`delete`, `additionalDirectories`, MCP server config,
  `session/set_config_option`/`configOptions`
- Authentication: `authMethods`, `auth/login`/`auth/logout`
- Keyed upsert/patch semantics (messages, tool calls, terminals), open-enum emitter rules
  (custom values must be `_`-prefixed)
- Extensibility/`_meta`/schema-hygiene, error shape, shutdown promptness
- `INFORMATIONAL` probes: malformed JSON, structurally-invalid requests, unknown session ids,
  stderr volume, MCP connection details
