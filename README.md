# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP). It launches an agent
implementation as a stdio subprocess, drives it through the protocol - initialize, session lifecycle, prompt turns,
cancellation, error handling, transport hygiene - and reports which requirements pass, fail, don't apply, or were never
exercised.

Targets **v1** by default, with an opt-in **v2** (Draft) suite via `--protocol-version 2`.
See ["What is covered"](#what-is-covered) below for the exact per-version breakdown.

## Run

```
uv run acp-tck [args] -- <agent command> [agent args...]
```

For example, against the bundled self-test fixture:

```
uv run acp-tck -- python tests/fixtures/agents/v1/conforming.py
```

Everything after `--` is the agent's own command line, launched as a stdio subprocess - a fresh process per test, so one
crash can't cascade into unrelated failures.

### Examples

Run the v1 suite against the bundled conforming fixture agent, using defaults for everything else:

```bash
uv run acp-tck -- python tests/fixtures/agents/v1/conforming.py
```

Run against a real agent binary, with a scratch working directory for it to run in, longer per-response and per-test
timeouts (real agents are slower than fixtures), and write the full JSON report for later inspection:

```bash
uv run acp-tck \
  --agent-cwd /tmp/acp-tck-wd \
  --timeout 90 --test-timeout 300 \
  --report-json .agents/reports/report.json \
  -- node /path/to/some-agent/dist/index.js
```

Run the v2 suite from inside the agent's own project directory, without a separate acp-tck checkout on PATH - uv's
--project points at wherever acp-tck actually lives, so `uv run acp-tck` resolves and runs from there while the agent
command still runs relative to the current directory:

```bash
uv --project ../acp-tck run acp-tck \
  --timeout 90 --test-timeout 300 --protocol-version 2 \
  -- node ./dist/index.js
```

## Options

### `--protocol-version {1,2}`

Selects which protocol version's conformance suite to run (default `1`); see ["What is covered"](#what-is-covered) for
what each suite checks. If the agent under test never actually negotiates the requested version, version-dependent tests
are `SKIPPED` with a `VERSION-MISMATCH` hint and the run is forced `NOT CONFORMANT` - symmetrically for both directions
(a v1-only agent run under `--protocol-version 2`, or a v2-only agent run under `--protocol-version 1`).

### `--agent-cwd DIR`

Working directory for the agent process (default: inherit from the `acp-tck` process itself). Useful when the agent
expects to be launched from within a particular project or workspace directory.

### `--agent-env KEY=VAL`

An environment variable overlaid on the agent's process environment. Repeatable - pass the flag once per variable to set
several.

### `--timeout S`

Per-response deadline in seconds (default `30`). Bounds how long the harness waits for any single response from the
agent before treating it as unresponsive.

### `--startup-timeout S`

Deadline in seconds for the agent's very first response (default `30`), kept separate from `--timeout` so a
slow-starting agent (e.g. one doing heavyweight initialization work) doesn't force every later response deadline to be
raised too.

### `--test-timeout S`

Wall-clock deadline in seconds for a single test, regardless of its own internal timeouts (default `120`). Guards
against a test that would otherwise hang indefinitely - e.g. an agent that stops responding partway through a multi-step
exchange. On expiry the test fails with a message identifying the watchdog, and the agent process is still shut down
normally.

### `--cancel-prompt TEXT`

Prompt text the cancellation tests send, instead of the short text every other prompt test uses. Pick something that
keeps a real agent busy long enough for `session/cancel` to land while the turn is still in flight - otherwise those
tests report `SKIPPED` ("cancellation not exercised"), which means exactly that, not a conformance failure.

### `--auth-method ID`

Authenticates with this method id (one advertised in `initialize`'s `authMethods`) right after `initialize`, before any
session-dependent test runs. Needed for any agent that gates `session/new` behind authentication - without it,
session-dependent tests report `SKIPPED` with an "AUTH-GATED" hint and the run is forced `NOT CONFORMANT`, since those
requirements were never actually exercised.

### `--allow-logout`

v2 only. Opts in to actually calling `auth/logout` against the agent under test. Off by default because it may revoke
the operator's own credentials for whatever account the agent is authenticated as; without it, the logout requirement
(`ACP-AUTH-203`) reports `SKIPPED` instead of exercising the method. A `SKIPPED` `CAPABILITY`-tier requirement doesn't
affect conformance - only a *failed* one does - so omitting `--allow-logout` never by itself makes a run
`NOT CONFORMANT`.

### `--close-grace S`

Grace period in seconds budgeted at each stage of the shutdown ladder (close stdin, then `SIGTERM`, then `SIGKILL`) when
tearing down the agent process after a test (default `2.0`). Each stage stops early as soon as the agent actually exits,
rather than always waiting out the full grace period, so raising this only matters for a slow-to-exit agent.

### `--report-json PATH`

Writes the full JSON report to `PATH` - see ["Reading the report"](#reading-the-report) below for its shape.

### `-k EXPR`

Runs only tests matching a pytest `-k` expression.

### `-v`

Verbose pytest output.

### `--version`, `--help`

Print the installed `acp-tck` version, or usage help, and exit.

## Reading the report

The terminal output groups every requirement by tier and prints its aggregated status, followed by per-tier counts and a
`VERDICT: CONFORMANT` / `VERDICT: NOT CONFORMANT (...)` line. `--report-json PATH` writes the same information as JSON,
plus failure diagnostics:

- `agent_command`, `agent_info`, `agent_capabilities`, `protocol_version`, `schema_revision`, `tck_version`,
  `started_at`/`finished_at`.
- `requirements`: one entry per requirement, always - including ones no test ever ran (`status: "NOT_TESTED"`) - with
  its tier, spec citation, aggregated status, and every bound test's outcome (`nodeid`, `status`, `message`,
  `duration_s`, `properties`). A `FAIL` outcome additionally carries `transcript` (the full wire traffic for that test)
  and `stderr` (truncated to the last 20 kB), so a failure is diagnosable from the JSON alone.
- `verdict`: `{"conformant": bool, "blocked_by_auth": bool, "blocked_by_version_mismatch": bool, "tier_counts": {...}}`.

## The tier / status / verdict model

### Tier

Every requirement has a **tier**

#### MANDATORY

A spec MUST. A failure or an untested `MANDATORY` requirement makes the run non-conformant.

#### CAPABILITY

Only applies if the agent advertised the relevant capability in `initialize`; otherwise it's reported
`SKIPPED` ("not applicable"), which does **not** affect conformance. If the agent *did* advertise it, though, a failure
does count against conformance - advertised capabilities must work.

#### ADVISORY

A spec SHOULD. Always reported, never affects the verdict.

#### INFORMATIONAL

Spec silent, or reference implementations disagree. The test never asserts on the probed behaviour itself; it records
what was observed via `record_property`, and that note is surfaced alongside the status in both the terminal table (e.g.
`ACP-INFO-PARSE-001   PASS  (silent; conn after: usable (sessionId=...))`) and the JSON report's
`properties` field. It can still `FAIL` if the prerequisite handshake it rides on top of (e.g. `initialize`, or
`session/new` for the unknown-`sessionId` probe) itself fails - that is a real conformance problem the probe correctly
surfaces, not a probe bug. Never affects the verdict either way.

### Status

Each test produces one of `PASS` / `FAIL` / `SKIPPED`; a setup/teardown error (including a harness-level agent timeout
or crash) is reported as `FAIL`. A requirement's status is the worst across every test bound to it (`FAIL` > `PASS` >
`SKIPPED`); a requirement no test ever ran is `NOT_TESTED` - deliberately counted as a failure for the `MANDATORY` tier
(see "Verdict" below), so a dead agent that never gets past `initialize` can't score 100% by starving every other check
of a record.

### Verdict

`conformant` is `true` iff there is no `MANDATORY` `FAIL`, no `MANDATORY` `NOT_TESTED`, no `CAPABILITY`
`FAIL`, the run was not `blocked_by_auth` (i.e. no session-dependent test was skipped because the agent requires
authentication and no `--auth-method` was given - see ["Options"](#options) above), and not
`blocked_by_version_mismatch` (i.e. no version-dependent test was skipped because the agent under test never actually
negotiated the `--protocol-version` this run targets - checked for both v1 and v2 runs).

### Exit code

`0` iff `conformant`, `1` otherwise (including "the agent never responded to anything" - every
`MANDATORY` requirement ends up `FAIL`/`NOT_TESTED`, but the run still completes and still writes a report). No agent
command after `--` is a usage error (`2`).

## Protocol scope

The codebase is structured as a version-agnostic core plus one package per protocol version (`src/tck/common/` +
`src/tck/v1/` + `src/tck/v2/`, see `AGENTS.md`), so each version's suite does not require forking the harness, report
model, or pytest plugin. ACP **v1** is the default. ACP **v2** is available via `--protocol-version 2`. For the precise,
current requirement set, `src/tck/v{1,2}/requirements.py` is the source of truth.

## What is covered

### v1

- `initialize` handshake and version negotiation, including the strengthened unsupported-version probe (`ACP-INIT-003`)
- Session lifecycle: `session/new`, `session/load`, `session/resume`, `session/list`, `session/delete`, `session/close`,
  `additionalDirectories`
- `session/prompt` turns and `session/cancel`, including the cancellation race handling described above
- Session `modes` and `configOptions`
- Prompt content capabilities (`image`/`audio`/`embeddedContext`)
- Authentication surface: `authMethods`, `authenticate`, `logout`
- Client-capability negatives: the agent must never call `fs/*`, `terminal/*`, or `elicitation/create` when the client
  didn't advertise the matching capability (`ACP-CLIENTCAP-001`/`002`/`003`)
- Extensibility and hygiene: `_`-prefixed custom methods must get a response (`ACP-EXT-001`), `_meta` passthrough,
  unknown top-level response keys, error message shape, shutdown promptness
- Transport/JSON-RPC hygiene: stdio framing, envelope validation, unrecognised-method handling
- `INFORMATIONAL` probes (reported only, spec silent or reference agents disagree): malformed JSON, structurally-invalid
  requests, unknown session ids, stderr volume
- Not yet covered: MCP/terminal/filesystem capability surfaces

### v2

- `initialize`/version-negotiation baseline, including a v2-only agent's required behavior when asked for `1`
- `session/new` baseline
- Core `session/prompt` turn/`state_update` lifecycle (turn completion via `state_update`, not the prompt response) and
  `session/cancel` (confirmed via a terminating `cancelled` idle `state_update`)
- Prompt content capabilities (`image`/`audio`/`embeddedContext`)
- `session/request_permission` flow
- Agent -> client method rules (including the `_`/`$/`-prefix extensibility rule)
- stdio transport, the JSON-RPC envelope, and batching
- Session management: `session/resume` (including replay ordering), `session/list`, `session/close`/`delete`,
  `additionalDirectories`, MCP server config, `session/set_config_option`/`configOptions`
- Authentication: `authMethods`, `auth/login`/`auth/logout`
- Keyed upsert/patch semantics (messages, tool calls, terminals), open-enum emitter rules (custom values must be `_`
  -prefixed)
- Extensibility/`_meta`/schema-hygiene, error shape, shutdown promptness
- `INFORMATIONAL` probes: malformed JSON, structurally-invalid requests, unknown session ids, stderr volume, MCP
  connection details
