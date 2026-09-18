# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
v1. It launches an agent implementation as a stdio subprocess and drives it through the
protocol to check conformance -- initialize, session lifecycle, prompt turns, cancellation,
error handling, and transport hygiene -- reporting which requirements pass, fail, are not
applicable, or were never exercised.

This slice adds an installable CLI (`acp-tck`), a requirement registry, a pytest plugin, and
the first conformance tests (transport hygiene + `initialize`). Session/prompt/cancel tests,
capability-conditional tests, and full reporting/verdict/exit-code land in later slices.

## Layout

```
src/tck/
  __init__.py            `acp-tck` console-script entry point (`main()`); argparse CLI, runs
                          the packaged conformance suite via `pytest.main(...)`
  __main__.py            `python -m tck` -- same as the console script (used by the self-tests
                          so they don't depend on the console script being on PATH)
  requirements.py        the requirement registry: `Tier`, `Requirement`, `REGISTRY`, `get()`
  plugin.py               the `tck.plugin` pytest plugin: `--tck-*` options, `requirement`/
                          `capability` markers, async test support, fixtures, the requirement
                          result collector, and the terminal summary table
  protocol.py            PROTOCOL_VERSION, error codes, StopReason values, method inventories
  validation.py          schema validation for agent-authored JSON-RPC messages
  harness/
    __init__.py           public API re-exports
    process.py            AgentProcess, AgentLaunch, AgentTimeout, AgentExited
    transcript.py          TranscriptEntry, Direction
  schema/v1/
    schema.json            vendored ACP v1 JSON Schema (verbatim, do not hand-edit)
    meta.json               vendored method-name tables (verbatim, do not hand-edit)
    VENDORED.md             source repo, commit hash, date, refresh procedure
  conformance/            the conformance suite itself, shipped inside the wheel
    __init__.py
    conftest.py            intentionally empty: `-p tck.plugin` is always passed explicitly
    _helpers.py             `connected_agent()` -- spawn + optional initialize + auto-close
    test_transport.py       ACP-TRANSPORT-001/002 (framing, UTF-8)
    test_jsonrpc.py         ACP-JSONRPC-001..005 (id echo, result-xor-error, notifications, ...)
    test_initialize.py      ACP-INIT-001..004, ACP-SCHEMA-001 (handshake + full-exchange schema)

tests/
  conftest.py              agent_launch() helper for spawning fixture agents (harness unit tests)
  test_harness.py          unit tests for the harness, run against the fixtures below
  test_validation.py       unit tests for tck.protocol / tck.validation
  test_registry.py          registry invariants + two-way check against conformance markers
  test_cli.py               end-to-end: run `python -m tck -- <fixture>` as a subprocess
  fixtures/agents/
    _base.py               shared ConformingAgent core (not a standalone script)
    conforming.py          deterministic, offline, conforming ACP v1 agent
    banner_on_stdout.py     conforming + prints a non-ACP banner line to stdout first
    stderr_chatter.py      conforming + logs every received message to stderr
    never_responds.py      reads stdin forever, never writes anything
    exits_immediately.py   exits 0 without reading stdin
    wrong_id_echo.py       mangles every response id (violates ACP-JSONRPC-001)
    version_mismatch_errors.py  errors instead of succeeding on a version mismatch (ACP-INIT-003)
    result_and_error.py    initialize response carries both result and error (ACP-JSONRPC-002)
    answers_notifications.py  replies to the session/cancel notification (ACP-JSONRPC-003)
    unknown_method_no_error.py  unknown methods succeed instead of -32601 (ACP-JSONRPC-004 only)
```

## Running the TCK against an agent

```
uv run acp-tck -- python tests/fixtures/agents/conforming.py
```

Options: `--agent-cwd DIR`, `--agent-env KEY=VAL` (repeatable), `--timeout S` (per-response
deadline, default 30), `--startup-timeout S` (default 30), `-k EXPR`, `-v`, `--version`,
`--help`. Everything after `--` is the agent's own command line. Exit code is whatever pytest
itself returns for the individual test outcomes (a verdict-based exit code driven by the
four-status model is slice 5).

You can also run the suite directly with plain pytest, e.g. to add pytest's own flags:

```
uv run pytest src/tck/conformance -p tck.plugin --tck-agent-cmd 'python tests/fixtures/agents/conforming.py'
```

`tck.plugin` is deliberately **not** auto-registered via a `pytest11` entry point (see
`.agents/plan.md` "Decided deliverable shape") -- it must always be loaded with `-p tck.plugin`,
which both invocations above do.

## Running the repo's own tests

```
uv run pytest
```

The whole suite (harness unit tests + registry meta-tests + end-to-end CLI tests against every
fixture) runs in well under a minute. Harness unit tests use short (≤2s) per-call timeouts and
`asyncio.run(...)` directly -- there is no `pytest-asyncio` dependency. The conformance suite's
own async tests are run the same way, via `tck.plugin`'s `pytest_pyfunc_call` hook.

## How to add a requirement + test

1. Add a `Requirement(...)` entry to `_DECLARATIONS` in `src/tck/requirements.py`: pick an id
   (`ACP-<AREA>-<NNN>`), a `Tier`, and cite the exact `research/*.md` line(s) that back it --
   these reports are the specification, not memory of the protocol.
2. Write a test under `src/tck/conformance/`, marked `@pytest.mark.requirement("ACP-…")` with a
   docstring starting with the id(s). Use `connected_agent()` from `_helpers.py` to spawn the
   agent; `async def` tests work without any extra setup.
3. If the requirement only applies when the agent advertises a capability, add
   `@pytest.mark.capability("agentCapabilities.some.path")` too -- the test is skipped with
   reason "capability ... not advertised" (or "initialize failed") otherwise.
4. Run `uv run pytest` -- `tests/test_registry.py` fails if the new id isn't referenced by a
   test, or if a test references an id that isn't registered.
5. Consider adding a non-conforming fixture under `tests/fixtures/agents/` that trips only the
   new requirement, and assert on it in `tests/test_cli.py`.

## Tiers and statuses

Tiers (`tck.requirements.Tier`): `MANDATORY` (MUST), `CAPABILITY` (only applies when the agent
advertises the capability), `ADVISORY` (SHOULD; reported, never the sole cause of a failing
verdict once slice 5 lands), `INFORMATIONAL` (spec silent / SDKs disagree; reported only).

Per-test statuses the plugin's result collector records (`tck.plugin.Status`): `PASS`, `FAIL`,
`SKIPPED`. The terminal summary aggregates across every test bound to a given id (worst of
FAIL > PASS > SKIPPED wins) and reports `NOT TESTED` for any registered id no test ever ran.

## Harness API (`tck.harness`)

Raw, hand-rolled asyncio NDJSON stdio client -- deliberately not built on the ACP Python SDK,
whose typed layer cannot emit malformed traffic and whose transport silently drops
non-conforming lines. This harness never drops or crashes on anything the agent sends; it
records it.

- `AgentLaunch(command, cwd=None, env_overrides={}, startup_timeout=5.0, default_timeout=5.0)`
  -- launch configuration. `env_overrides` is applied on top of the inherited `os.environ`.
- `AgentProcess(launch)` -- async context manager; spawns the subprocess in its own process
  group (POSIX) so the whole group can be terminated.
  - `send_raw(bytes | str)` -- writes exactly the given bytes plus `\n`; use this for
    deliberately malformed traffic.
  - `send_message(dict)` -- compact `json.dumps` plus `\n`.
  - `send_request(method, params=None, *, id=None) -> id` -- auto-increments an int id unless
    one is given (string ids allowed).
  - `send_notification(method, params=None)`.
  - `read_line(timeout=None) -> TranscriptEntry` -- next stdout line, raw bytes plus best-effort
    UTF-8/JSON decoding. Raises `AgentTimeout` (carries the transcript so far) or `AgentExited`
    (carries exit code, `stderr_text()`, and the transcript).
  - `wait_for_response(id, timeout=None)` / `wait_for_message(predicate, timeout=None)` -- read
    until a match; every other line read along the way stays in `transcript` and is available
    via `pending()`.
  - `transcript: list[TranscriptEntry]` -- everything sent and received, in order, both
    directions, malformed lines included.
  - `stderr_text()` -- everything captured from stderr so far (drained continuously in the
    background so the child never blocks on it).
  - `close(grace=2.0)` -- close stdin, wait; SIGTERM the process group, wait; SIGKILL. Sets
    `exit_code` and `exited_on_stdin_close`.
- `TranscriptEntry` -- `direction`, `raw`, `timestamp`, `text`/`text_error`,
  `parsed`/`parse_error`. Decode/parse failures are recorded as fields, never raised.

## Fixture agent catalogue

All fixtures are pure Python, stdlib only, deterministic, offline, ~50 lines:

- `conforming.py` -- handles `initialize`, `session/new`, `session/prompt`, `session/cancel`,
  and a harness-only `_tck/env` method (echoes an env var, for testing env-override
  propagation). A prompt whose text is exactly `__hang__` withholds its response until
  `session/cancel` arrives, to make the cancel flow testable. Unknown methods get `-32601`.
- `banner_on_stdout.py` -- conforming, but prints a human banner to stdout first (violates the
  "stdout is ACP-only" transport rule).
- `stderr_chatter.py` -- conforming, logs to stderr on every message received.
- `never_responds.py` -- reads stdin forever, never writes; does not exit on stdin EOF.
- `exits_immediately.py` -- exits 0 without reading anything.

## Vendored schema (`tck/schema/v1/`)

`schema.json` and `meta.json` are verbatim copies of the ACP v1 JSON Schema from the spec
repo (`https://github.com/zed-industries/agent-client-protocol`); the commit hash, vendor
date, and exact copy commands live in `src/tck/schema/v1/VENDORED.md`. Refresh procedure is
documented there. Do not hand-edit either JSON file.

The vendored schema's top level (`schema.json:4-119`) is `anyOf` of three side-annotated
envelopes -- `Agent`, `Client`, `ProtocolLevel` -- each split into `Request` / `Response` /
`Notification` branches. Every method-specific params/response `$def` carries `x-side`
(which side implements the method) and `x-method` (its wire name); `tck.protocol` and
`tck.validation` derive their method-name tables from these annotations plus `meta.json`
rather than hand-copying a table from docs, so a schema refresh mostly self-updates them.

## `tck.protocol`

`PROTOCOL_VERSION = 1` (v1-only; a future v2 effort starts here). JSON-RPC/ACP error code
constants (`PARSE_ERROR`, `INVALID_REQUEST`, `METHOD_NOT_FOUND`, `INVALID_PARAMS`,
`INTERNAL_ERROR`, `REQUEST_CANCELLED`, `AUTHENTICATION_REQUIRED`, `RESOURCE_NOT_FOUND`).
`StopReason` constants and the `STOP_REASONS` frozenset. Method inventories, all derived from
`meta.json`/`schema.json` at import time: `AGENT_METHODS` (client -> agent, requests and
notifications), `CLIENT_METHODS` (agent -> client), `AGENT_NOTIFICATIONS` /
`CLIENT_NOTIFICATIONS` (the notification-only subsets of each, cross-derived from
`schema.json`'s `AgentNotification`/`ClientNotification` `$def`s since `meta.json` itself does
not separate requests from notifications).

## `tck.validation`

Validates JSON-RPC messages the **agent under test** writes to stdout against the vendored
schema (never messages the TCK's own mock client writes -- there is no `validate_client_*`
yet). `ValidationIssue(path, message, schema_path)` -- `path`/`schema_path` are JSON pointers;
never raises, always returns issues.

- `validate_agent_message(msg: dict) -> list[ValidationIssue]` -- dispatches on shape: a
  request/notification (`method` present) is checked against that method's params schema; a
  response (`method` absent) only gets the JSON-RPC envelope check (`jsonrpc`, `id` type,
  `result` XOR `error`, error object shape) -- use `validate_agent_response` for the `result`
  payload, since picking the right response schema requires knowing which request it answers.
- `validate_agent_response(method: str, msg: dict) -> list[ValidationIssue]` -- envelope check
  plus `result` validated against `method`'s response schema (or `error` against the shared
  `Error` schema).
- Documented spec quirk (protocol-surface report, Discrepancy 3): `session/load`'s response
  docs show `null` where the schema types an all-optional object. The vendored schema does
  **not** itself accept `null` there (checked: `LoadSessionResponse` is `type: "object"`, no
  `"null"` in an outer `anyOf`), so `validate_agent_response` special-cases it -- `null` is
  accepted whenever the target response schema is an object type with zero required fields.
- The vendored schema never sets `additionalProperties: false` anywhere (checked: zero
  occurrences), so it cannot reject an unknown root field on a spec type even though the
  spec's prose (`extensibility.mdx`) says implementations MUST NOT add one; `validate_*` does
  not flag this today (see `tests/test_validation.py::test_unknown_root_field_is_permitted_by_the_vendored_schema`).

## Conventions

- Dependency management is `uv` only, with exact pins (`==`), never bare `pip` or hand-edited
  `pyproject.toml` dependency entries.
- Protocol scope is ACP **v1 only**; v2/draft surfaces are out of scope.
- `.agents/` is the orchestrator's workbench. `.agents/research/*.md` are read-only inputs --
  they are the specification this code implements; do not edit them.
