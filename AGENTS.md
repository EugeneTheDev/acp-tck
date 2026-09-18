# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
v1. It launches an agent implementation as a stdio subprocess and drives it through the
protocol to check conformance -- initialize, session lifecycle, prompt turns, cancellation,
error handling, and transport hygiene -- reporting which requirements pass, fail, are not
applicable, or were never exercised.

Slices so far add an installable CLI (`acp-tck`), a requirement registry, a pytest plugin,
transport/`initialize` conformance tests, mandatory session/prompt/cancel conformance tests, full
reporting (a JSON report via `--report-json`, the four-status verdict, and a verdict-based exit
code), capability-conditional session-method tests: `session/load`, `session/resume`,
`session/list`, `session/delete`, `session/close`, and `additionalDirectories`, each gated on the
`initialize` result advertising the relevant capability, and (slice 6b) session modes/config
options (support *inferred* from `session/new`'s own response, not an `initialize` marker),
prompt content capabilities (`image`/`audio`/`embeddedContext`), and the authentication surface
(`authMethods`, `authenticate`, `logout`, plus a `--auth-method` option so the TCK can drive a
real authenticate handshake before `session/new`), and (slice 7) MANDATORY client-capability
negative tests (`fs`/`terminal`/`elicitation` MUST NOT be called unadvertised), the extensibility/
`_meta`/schema-hygiene ADVISORY family (`ACP-EXT-001` MANDATORY, `ACP-META-001`/`ACP-ERROR-001`/
`ACP-SHUTDOWN-001`/`ACP-SCHEMA-002` ADVISORY), and an INFORMATIONAL tier of report-only probes
(`ACP-STDERR-001`, `ACP-INFO-PARSE-001`, `ACP-INFO-INVALIDREQ-001`, `ACP-INFO-UNKNOWNSESSION-001`)
that never assert on the probed behaviour itself -- but still FAIL if the prerequisite handshake
they ride on top of fails -- for behaviour the spec is silent on or SDKs disagree about.

## Layout

```
src/tck/
  __init__.py            `acp-tck` console-script entry point (`main()`); argparse CLI, runs
                          the packaged conformance suite via `pytest.main(...)`
  __main__.py            `python -m tck` -- same as the console script (used by the self-tests
                          so they don't depend on the console script being on PATH)
  requirements.py        the requirement registry: `Tier`, `Requirement`, `REGISTRY`, `get()`.
                          Requirements gated by *inferred* support (no `initialize`-result
                          marker -- e.g. `modes`/`configOptions`, only observable in
                          `session/new`'s own response) use a documentation-only
                          `capability="inferred:modes"`/`"inferred:configOptions"` string that
                          satisfies `Requirement.__post_init__`'s invariant but is not looked up
                          by `@pytest.mark.capability(...)`/`_tck_capability_gate` -- those tests
                          instead `pytest.skip(...)` manually when the field is absent.
  plugin.py               the `tck.plugin` pytest plugin: `--tck-*` options (including
                          `--tck-report-json`, `--tck-auth-method`), `requirement`/`capability`
                          markers, async test support, fixtures, the per-test result collector,
                          the terminal summary table, JSON report writing, and the verdict-based
                          exit code. Also holds the `_AUTH_METHOD` contextvar and
                          `current_auth_method_id()` accessor (mirrors `_ACTIVE_PROCESSES`),
                          set per-test by the autouse `_tck_auth_method_context` fixture from
                          `--tck-auth-method`; `_build_report()` scans skip messages for the
                          literal `"AUTH-GATED:"` marker to compute `Verdict.blocked_by_auth`.
  report.py              the report model: `Status`, `TestOutcome`, `RequirementResult`,
                          `Verdict` (including `blocked_by_auth: bool`), `Report` -- pure data +
                          aggregation, no pytest dependency
  protocol.py            PROTOCOL_VERSION, SCHEMA_REVISION, error codes, StopReason values,
                          method inventories
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
    _helpers.py             `connected_agent()`, `new_session()`, `run_prompt()`/`PromptTurn` --
                            spawn + optional initialize + auto-close, plus the mock-client prompt
                            driver used by every session/prompt/cancel test
    test_transport.py       ACP-TRANSPORT-001/002 (framing, UTF-8)
    test_jsonrpc.py         ACP-JSONRPC-001..005 (id echo, result-xor-error, notifications, ...)
    test_initialize.py      ACP-INIT-001..004, ACP-SCHEMA-001 (handshake + full-exchange schema)
    test_session.py         ACP-SESSION-001/002 (session/new sessionId, uniqueness)
    test_prompt.py          ACP-PROMPT-001..003 (stop reason, update validity, resource_link)
    test_cancel.py           ACP-CANCEL-001/002 (cancelled stop reason, no update after response)
    test_session_capabilities.py  ACP-LOAD-001..003, ACP-RESUME-001/002, ACP-LIST-001/002,
                            ACP-DELETE-001/002, ACP-CLOSE-001/002, ACP-ADDDIRS-001 --
                            capability-conditional `session/load`/`resume`/`list`/`delete`/`close`
                            and `additionalDirectories`, each gated by
                            `@pytest.mark.capability(...)` on the corresponding
                            `agentCapabilities`/`sessionCapabilities` path
    test_session_config.py  ACP-MODES-001/002, ACP-CONFIG-001/002/003 -- session `modes`/
                            `configOptions` (support inferred from `session/new`'s own response,
                            manually skipped when absent -- see `requirements.py` note above) and
                            the Req 33 negative control (no `type: "boolean"` config option
                            without `clientCapabilities.session.configOptions.boolean`)
    test_prompt_capabilities.py  ACP-PROMPTCAP-001/002/003 -- `image`/`audio`/`embeddedContext`
                            prompt content blocks, each a boolean
                            `agentCapabilities.promptCapabilities.*` gate
    test_authentication.py  ACP-AUTH-001..005 -- `authMethods` shape/uniqueness, the Req 23
                            terminal-method client-capability gate, the `authenticate` ->
                            `session/new` flow (only when `--tck-auth-method` was given; narrowed
                            to AUTH-C4's "no -32000", not full success -- ACP-SESSION-001 owns
                            general `session/new` health), `logout` (gated on the
                            `agentCapabilities.auth.logout` object marker), and AUTH-A1/
                            ACP-AUTH-005 (ADVISORY): with no `authMethods` advertised,
                            `session/new` must not fail with `-32000` -- enforced via
                            `skip_if_auth_gated` only excusing that error when `authMethods` is
                            non-empty
    test_client_capabilities.py  ACP-CLIENTCAP-001..003 (MANDATORY) -- three separate tests
                            (one per id, sharing a helper) each asserting one of
                            `fs/*`/`terminal/*`/`elicitation/create` is never observed during a
                            prompt turn run against a mock client that advertises
                            `clientCapabilities: {}` (Reqs 29, 30, 32); split from a single
                            combined test so a fixture that only calls one unadvertised surface
                            fails only that id, not all three (review-slices-5-6.md item 9)
    test_extensibility.py  ACP-EXT-001 (MANDATORY -- Req 42's MUST-respond-to-custom-methods,
                            distinct from ACP-JSONRPC-004's general SHOULD about the `-32601`
                            code), ACP-META-001 (ADVISORY -- `_meta` on `session/prompt` is
                            accepted), ACP-SCHEMA-002 (ADVISORY -- no unknown root-level keys on
                            any agent-authored request/notification `params` or response
                            `result`, via `validation.find_unknown_root_keys`)
    test_diagnostics.py    ACP-ERROR-001 (ADVISORY -- error `message` non-empty, no embedded
                            newline), ACP-SHUTDOWN-001 (ADVISORY -- `exited_on_stdin_close` after
                            an ordinary close), ACP-STDERR-001 (INFORMATIONAL -- records stderr
                            byte count; never asserts on the count itself)
    test_informational.py  ACP-INFO-PARSE-001/INVALIDREQ-001/UNKNOWNSESSION-001 (INFORMATIONAL --
                            malformed-JSON-line, structurally-invalid-request, and
                            unknown-`sessionId` behaviour, each recorded via `record_property`
                            and never asserted on directly; still FAILs if the prerequisite
                            handshake itself fails; the probed behaviour is silent in the spec
                            and real SDKs disagree; "silent" is concluded via a short
                            `quiet_period()`, never the full `--tck-timeout`)

tests/
  conftest.py              agent_launch() helper for spawning fixture agents (harness unit tests)
  test_harness.py          unit tests for the harness, run against the fixtures below
  test_validation.py       unit tests for tck.protocol / tck.validation
  test_registry.py          registry invariants + two-way check against conformance markers
  test_report.py            `tck.report` unit tests: aggregation, verdict rule, JSON round-trip
  test_cli.py               end-to-end: run `python -m tck -- <fixture>` as a subprocess,
                            including `--report-json` output and exit codes
  fixtures/agents/
    _base.py               shared ConformingAgent core (not a standalone script); optionally
                          takes a `capabilities` dict merged into `agentCapabilities`, and
                          implements `session/load` (replays stored history before responding),
                          `session/resume` (no replay), `session/list` (filtered by `cwd`),
                          `session/delete`/`session/close` (remove the session; close also
                          resolves an in-flight prompt as `cancelled`). Also (slice 6b) accepts
                          `modes`, `config_options`, `auth_methods`, `require_auth`,
                          `emit_mode_update`, `mode_update_field` (default `"currentModeId"`,
                          overridable by defect fixtures), and implements
                          `session/set_mode`/`session/set_config_option`/`authenticate`/
                          `logout`, plus filters `type: "boolean"` config options out of
                          `session/new`'s result unless the client advertised
                          `clientCapabilities.session.configOptions.boolean` (Req 33).
    conforming.py          deterministic, offline, conforming ACP v1 agent; advertises
                          `agentCapabilities: {}`, so every capability-conditional test SKIPs
    conforming_full.py     conforming.py plus `loadSession: true`, every `sessionCapabilities`
                          marker (`list`/`delete`/`resume`/`close`/`additionalDirectories`),
                          `promptCapabilities: {image, audio, embeddedContext}`, two `modes`, a
                          select and a boolean `configOptions` entry, an `authMethods` entry
                          (id `"tck"`), and `auth: {logout: {}}` -- all correctly implemented via
                          `_base.py` -- drives every CAPABILITY-tier requirement in this slice to
                          PASS when run with `--auth-method tck` (see "Running" below)
    banner_on_stdout.py     conforming + prints a non-ACP banner line to stdout first
    stderr_chatter.py      conforming + logs every received message to stderr
    never_responds.py      reads stdin forever, never writes anything
    exits_immediately.py   exits 0 without reading stdin
    wrong_id_echo.py       mangles every response id (violates ACP-JSONRPC-001)
    version_mismatch_errors.py  errors instead of succeeding on a version mismatch (ACP-INIT-003)
    echoes_any_version.py  echoes the client's requested `protocolVersion` verbatim, including
                          for the unsupported 65535 request -- the strengthened ACP-INIT-003
                          false-negative pattern also present in `testy`/`examples/echo_agent.py`
    result_and_error.py    initialize response carries both result and error (ACP-JSONRPC-002)
    answers_notifications.py  replies to the session/cancel notification (ACP-JSONRPC-003)
    unknown_method_no_error.py  unknown methods succeed instead of -32601 (ACP-JSONRPC-004 only)
    hangs_until_cancel.py  conforming, but every prompt (any text) withholds its response until
                          `session/cancel`; self-test-only, drives ACP-CANCEL-001/002
                          deterministically since the conformance suite itself must not rely on
                          `conforming.py`'s `__hang__` sentinel
    cancel_returns_error.py  cancelled turn resolves with a JSON-RPC error, not `cancelled`
                          (ACP-CANCEL-001)
    cancel_wrong_stop_reason.py  cancelled turn resolves with `stopReason: "end_turn"` instead of
                          `"cancelled"` (ACP-CANCEL-001)
    update_after_response.py  cancelled turn resolves correctly, then sends one more
                          `session/update` afterwards (ACP-CANCEL-002)
    bad_stop_reason.py     non-`__hang__` prompts resolve with `stopReason: "done"`, not a valid
                          StopReason (ACP-PROMPT-001, ACP-SCHEMA-001, cascades into ACP-CANCEL-001)
    duplicate_session_id.py  `session/new` always returns the same sessionId (ACP-SESSION-002)
    update_wrong_session.py  every `session/update` carries `sessionId: "other"`
                          (ACP-PROMPT-002, cascades into ACP-CANCEL-002)
    asks_permission.py    conforming, but sends `session/request_permission` mid-turn and only
                          resolves once the client answers -- the only self-test fixture that
                          exercises `_helpers.run_prompt`'s permission-answering path
    garbage_after_response.py  conforming for the whole exchange, then -- after stdin closes --
                          writes one line of non-JSON garbage to stdout before exiting
                          (ACP-TRANSPORT-001; only catchable via `AgentProcess.close()`'s
                          post-close stdout drain)
    invalid_utf8.py       writes one line of invalid UTF-8 bytes to stdout, otherwise conforming;
                          the dedicated negative control for ACP-TRANSPORT-002 (it also FAILs
                          ACP-TRANSPORT-001, since a line that isn't decodable text isn't valid
                          JSON either -- see `banner_on_stdout.py` below for the complementary
                          fixture that FAILs 001 but PASSes 002)
    load_replays_after_response.py  advertises `loadSession`; answers `session/load` before
                          replaying stored history instead of after (ACP-LOAD-002 only --
                          ACP-LOAD-001 still PASSes)
    resume_replays_history.py  advertises `sessionCapabilities.resume`; replays stored history
                          before answering `session/resume`, which resume MUST NOT do
                          (ACP-RESUME-002 only -- ACP-RESUME-001 still PASSes)
    load_returns_null.py  advertises `loadSession`, replays correctly, but answers
                          `session/load` with a literal `null` instead of `{}` -- fails only the
                          ADVISORY ACP-LOAD-003 (ACP-LOAD-001/002 still PASS: mandatory schema
                          validation tolerates `null` here)
    advertises_load_but_errors.py  advertises `loadSession: true` but always errors on
                          `session/load` -- a CAPABILITY-tier FAIL (ACP-LOAD-001), which flips
                          the overall verdict to NOT CONFORMANT
    mode_update_uses_modeId.py  conforming_full.py, but its `current_mode_update` carries the
                          docs-bug field name `modeId` instead of the schema's `currentModeId`
                          (ACP-MODES-002 only)
    config_partial_list.py  conforming_full.py, but `session/set_config_option` returns only the
                          changed entry instead of the complete `configOptions` list
                          (ACP-CONFIG-002 only)
    boolean_option_unadvertised.py  conforming_full.py, but always includes its `type: "boolean"`
                          config option in `session/new`'s result even when the client didn't
                          advertise `clientCapabilities.session.configOptions.boolean` (ACP-CONFIG-003,
                          MANDATORY -- flips the verdict to NOT CONFORMANT)
    terminal_auth_unadvertised.py  conforming_full.py, but advertises an
                          `authMethods[*].type == "terminal"` entry regardless of whether the
                          client advertised `clientCapabilities.auth.terminal` (ACP-AUTH-002,
                          MANDATORY -- flips the verdict to NOT CONFORMANT)
    gated_by_auth.py       conforming_full.py, but `session/new` always errors with
                          `-32000` (`AUTHENTICATION_REQUIRED`) unless the client has
                          successfully called `authenticate` first with the advertised
                          `"tck"` method id -- self-test-only fixture for
                          `--auth-method`/`Verdict.blocked_by_auth`
    calls_fs_unadvertised.py  `SendsClientRequestAgent` subclass (shared base added to `_base.py`
                          for slice 7): sends `fs/read_text_file` mid-turn regardless of
                          advertised client capabilities (ACP-CLIENTCAP-001, MANDATORY)
    calls_terminal_unadvertised.py  same shape, `terminal/create` (ACP-CLIENTCAP-002, MANDATORY)
    calls_elicitation_unadvertised.py  same shape, `elicitation/create` (ACP-CLIENTCAP-003,
                          MANDATORY)
    noisy_stderr_and_parse_error_reply.py  conforming, but logs every raw line to stderr and
                          replies `{"id": null, "error": {"code": -32700, ...}}` to malformed
                          JSON instead of silently swallowing it -- self-test-only fixture that
                          deterministically exercises ACP-STDERR-001's/ACP-INFO-PARSE-001's
                          non-default branches (see `tests/test_cli.py`)
```

## Running the TCK against an agent

```
uv run acp-tck -- python tests/fixtures/agents/conforming.py
```

Options: `--agent-cwd DIR`, `--agent-env KEY=VAL` (repeatable), `--timeout S` (per-response
deadline, default 30), `--startup-timeout S` (default 30), `--test-timeout S` (per-test
wall-clock watchdog, default 120 -- plugin: `--tck-test-timeout`; wraps the whole async test
body in `asyncio.wait_for(...)`, so a test hangs for at most this long even if every individual
read/write inside it uses a much larger `--timeout`; on expiry the test `FAIL`s with a message
naming the watchdog, and the agent process is still closed normally so transcript/stderr
diagnostics are still attached), `--cancel-prompt TEXT` (see below), `--report-json PATH` (see
"Reporting" below), `--close-grace S` (plugin: `--tck-close-grace`, default 2.0 -- grace period
budgeted at each stage of the agent-process shutdown ladder on teardown: stdin-close wait,
post-SIGTERM wait, post-SIGKILL wait; lower it only to speed up a fixture/test that deliberately
never exits on its own, a real agent under test should not normally need this changed), `-k EXPR`,
`-v`, `--version`, `--help`. Everything after `--` is the agent's own command line.

**Exit code** is the four-status verdict, not pytest's own per-test exit code: `0` iff
`verdict.conformant` (no `MANDATORY` `FAIL`/`NOT_TESTED`, no `CAPABILITY` `FAIL` -- see
"Reporting" below), `1` otherwise (this includes an agent that fails to start or never responds
at all: every `MANDATORY` requirement ends up `FAIL` or `NOT_TESTED`, the run still completes and
still writes a report, and the terminal summary prints a hint to check `--agent-cwd`/timeouts/
stderr). `acp-tck` with no command after `--` is a usage error (exit `2`, from `argparse`), not a
verdict. Mechanism: `tck.plugin`'s `pytest_sessionfinish` overwrites `session.exitstatus`, but
only when pytest itself completed a normal run (`ExitCode.OK`/`TESTS_FAILED`) -- `--collect-only`,
usage errors, and interrupted runs keep pytest's own exit code.

`--cancel-prompt TEXT` (plugin: `--tck-cancel-prompt`) sets the prompt text the cancellation
tests (ACP-CANCEL-001/002) send -- every other prompt test keeps its own short, deterministic
text. Default is a long free-form writing prompt, chosen to keep a real agent busy long enough
for `session/cancel` to land while the turn is still in flight. If ACP-CANCEL-001/002 report
SKIPPED with reason "cancellation not exercised", it means exactly that -- the turn finished
before, or too soon after, `session/cancel` was sent for the TCK to tell whether the agent
actually reacted to it -- not that the agent failed conformance. Passing a longer or slower
`--cancel-prompt` (and, if needed, a larger `--timeout`) may let a fast agent's turn stay in
flight long enough to exercise the requirement for real.

`--auth-method ID` (plugin: `--tck-auth-method`) tells the harness to send an `authenticate`
request with this `methodId` right after a successful `initialize`, before any session-dependent
test runs (`connected_agent(..., handshake=True)`, the default). Needed for any agent whose
`session/new` gates behind authentication: without it, session-dependent tests SKIP with a
message prefixed `"AUTH-GATED:"`, and the run is forced NOT CONFORMANT
(`Verdict.blocked_by_auth`) even if no MANDATORY/CAPABILITY requirement otherwise failed --
because those requirements were never actually exercised. `ACP-AUTH-003` itself additionally
SKIPs outright whenever `--auth-method` is omitted (it can't guess a valid method id) or the
agent advertises no `authMethods` at all.

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

## CI

`.github/workflows/ci.yml` runs on every push to `main`, every pull request, and on manual
`workflow_dispatch`. Two jobs:

- **`test`** -- `astral-sh/setup-uv` (cached), `uv python install 3.14`, `uv sync --locked`,
  `uv run pytest -q`. This is the required, blocking job.
- **`cross-check`** -- `needs: test`, `continue-on-error: true` (informational only). Clones
  `rust-sdk`/`python-sdk` as sibling checkouts pinned to the SHAs recorded in
  `docs/cross-check.md`, builds `testy` with `Swatinem/rust-cache` caching cargo, runs
  `scripts/cross-check.sh`, uploads the two `--report-json` reports as an artifact, then runs
  `scripts/cross-check-summary.py --expect-only-mandatory-fail ACP-INIT-003` to assert the
  scorecard hasn't drifted from the documented baseline (both upstream agents are expected to
  FAIL only `ACP-INIT-003`, per "Cross-checking against upstream agents" below). Its own
  exit code does not fail the workflow -- read the uploaded reports and the summary step's
  output when it goes red.

## Cross-checking against upstream agents

`scripts/cross-check.sh` runs the packaged conformance suite against two independently
implemented agents -- the Rust SDK's `testy` fixture and the Python SDK's
`examples/echo_agent.py` -- to sanity-check the TCK's own plumbing (framing, id correlation,
schema wiring, timeouts) against implementations this repo did not write. It is **not** part of
`uv run pytest`: it needs a Rust toolchain and local checkouts of both SDKs, so it is a manual/CI
step, run on demand.

**Prerequisites:**

- A Rust toolchain (`cargo`, `rustc >= 1.88`) on `PATH`.
- Local checkouts of `agentclientprotocol/rust-sdk` and `agentclientprotocol/python-sdk` --
  by default the paths recorded in `.agents/skills/check-rust-sdk/.repo` and
  `.agents/skills/check-python-sdk/.repo`; override with the `ACP_RUST_SDK` / `ACP_PYTHON_SDK`
  environment variables to point at any other checkout.
- `uv` (already required for everything else in this repo).

**Running:**

```
scripts/cross-check.sh
```

`OUT_DIR` (default `scratch/cross-check/`, gitignored) controls where the two
`--report-json` reports land. The script:

1. builds `testy` with `cargo build -p agent-client-protocol-test --bin testy
   --no-default-features` (strict-v1 build; the default `unstable` feature adds a non-v1
   `mcpCapabilities.acp` field) inside `$ACP_RUST_SDK` -- this is the only write the script
   makes outside `$OUT_DIR`, and it only ever touches that checkout's own `target/`;
2. runs `acp-tck --cancel-prompt wait_for_cancel --report-json "$OUT_DIR/testy.json" --
   target/debug/testy` (the `wait_for_cancel` prompt is required for `testy`'s cancel scenario
   to actually hang long enough for `session/cancel` to land -- see
   `.agents/research/testy-cross-check.md` §2.1);
3. runs the same against `uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python
   "$ACP_PYTHON_SDK/examples/echo_agent.py"` -- pinned explicitly, because `echo_agent.py`'s own
   unpinned PEP 723 header would otherwise resolve the latest *stable* release, which has a
   known prompt-deserialization bug (fixed on `main`/`1.0.0rc1`; see
   `.agents/research/testy-cross-check.md` §3.3);
4. prints a compact per-requirement comparison table (via `scripts/cross-check-summary.py`,
   stdlib only) plus both verdict lines and exit codes.

The script itself always exits `0` if it ran to completion -- the two agents' own verdicts are
data to read, not the script's success/failure. **Expected result** (see `docs/cross-check.md`
for the full table, explanations, and date of the last run): both agents are NOT CONFORMANT,
solely because of the deliberately strengthened `ACP-INIT-003` (both echo the client's
unsupported requested version verbatim) and the ADVISORY `ACP-INIT-004` (neither sets
`agentInfo`); `echo_agent`'s cancel tests are permanently SKIPPED (it has no cancellation
handling at all). Any *other* deviation from that baseline is worth investigating -- it means
either a TCK bug or a genuine, newly-observed upstream behaviour; `docs/cross-check.md` is where
that investigation is recorded.

## How to add a requirement + test

1. Add a `Requirement(...)` entry to `_DECLARATIONS` in `src/tck/requirements.py`: pick an id
   (`ACP-<AREA>-<NNN>`), a `Tier`, and cite the exact `research/*.md` line(s) that back it --
   these reports are the specification, not memory of the protocol.
2. Write a test under `src/tck/conformance/`, marked `@pytest.mark.requirement("ACP-…")` with a
   docstring starting with the id(s). Use `connected_agent()` from `_helpers.py` to spawn the
   agent; `async def` tests work without any extra setup.
3. If the requirement only applies when the agent advertises a capability, add
   `@pytest.mark.capability("agentCapabilities.some.path")` too -- the test is skipped with
   reason "capability ... not advertised" (or "initialize failed") otherwise. By default this
   checks for an *object marker*: supported iff the path resolves to a present, non-`null`
   value (an empty object still counts -- e.g. `"loadSession": {}`). For a plain boolean gate
   (supported iff the value is exactly `true`, e.g. `"loadSession": false` must NOT count as
   advertised), pass `boolean=True`: `@pytest.mark.capability("agentCapabilities.loadSession",
   boolean=True)`. See `capability_is_supported()` in `src/tck/plugin.py` and its unit tests in
   `tests/test_plugin.py` for both encodings.
4. If the test needs to send a custom/probe method the agent isn't expected to recognize (e.g.
   an "unknown method" negative control), prefix it with `_` (`_tck/does_not_exist`, `_tck/big`,
   ...) -- Req 42 / the extensibility rule requires custom methods to be `_`-prefixed, and the
   TCK holds itself to the same rule so its own probe traffic can never collide with a real,
   spec-defined method name.
5. Run `uv run pytest` -- `tests/test_registry.py` fails if the new id isn't referenced by a
   test, or if a test references an id that isn't registered.
6. Consider adding a non-conforming fixture under `tests/fixtures/agents/` that trips only the
   new requirement, and assert on it in `tests/test_cli.py`.

## Tiers and statuses

Tiers (`tck.requirements.Tier`): `MANDATORY` (MUST), `CAPABILITY` (only applies when the agent
advertises the capability), `ADVISORY` (SHOULD; reported, never the sole cause of a failing
verdict), `INFORMATIONAL` (spec silent / SDKs disagree; reported only, never affects the verdict).

Statuses (`tck.report.Status`): `PASS`, `FAIL`, `SKIPPED`, `NOT_TESTED`. A test only ever produces
the first three; `NOT_TESTED` is the aggregated status of a registered id that no test bound to
during the run (a dead agent that never gets past `initialize` cannot score 100% by starving
every other requirement of a record). A test that *errors* -- a setup/teardown exception, or a
harness `AgentExited`/`AgentTimeout` propagating out of the test body -- is `FAIL`, not a separate
status; the exception text becomes the outcome's `message`. Aggregating several tests bound to
the same requirement: any `FAIL` wins; else any `PASS`; else any `SKIPPED`; no records at all ->
`NOT_TESTED`. The terminal summary prints this aggregated status per id, grouped by tier.

## Reporting (`tck.report`, `--report-json`)

`--report-json PATH` (plugin: `--tck-report-json`) writes the full run as JSON at
`pytest_sessionfinish`, in addition to the terminal summary. Top-level keys: `tck_version`,
`protocol_version` (`tck.protocol.PROTOCOL_VERSION`), `schema_revision`
(`tck.protocol.SCHEMA_REVISION` -- the single source of truth; `tck.requirements.SPEC_REVISION`
reads from it too), `agent_command` (the launched command, as a list), `agent_info` /
`agent_capabilities` (from the cached `initialize` result, or `null` if it never succeeded),
`started_at` / `finished_at` (ISO 8601 UTC), `requirements`, `verdict`.

`requirements` has one entry per `tck.requirements.REGISTRY` id -- including ids no test ever
ran (`status: "NOT_TESTED"`, `tests: []`) -- each carrying its `tier`/`capability`/`text`/
`citation` plus every bound test's outcome (`nodeid`, `status`, `message`, `duration_s`,
`properties` -- `record_property(...)` values such as `acp_tck_cancel_race_ms` -- and, for `FAIL`
outcomes only, `transcript` (`[{"dir": "sent"|"received", "t": <monotonic ts>, "raw": <line>},
...]`, each entry's own `raw` capped at 4 kB with a `"...[truncated N byte(s)]..."` marker, and
the whole list capped at 400 entries -- first/last 200 with a gap marker in between, since the
handshake/setup and the failure itself are almost always what matters and a chatty middle is
safest to elide; review-slices-5-6.md S8) and `stderr` (truncated to the last 20 kB).

`verdict` is `{"conformant": bool, "blocked_by_auth": bool, "tier_counts": {tier: {status:
count}}}`. `conformant` is computed from `MANDATORY`- and `CAPABILITY`-tier requirements, plus
`blocked_by_auth`: `true` iff no `MANDATORY` `FAIL`, no `MANDATORY` `NOT_TESTED`, no `CAPABILITY`
`FAIL`, and not `blocked_by_auth`. A `CAPABILITY` `SKIPPED`/`NOT_TESTED` (not advertised, or
simply never exercised) does not affect it -- only a *failed* capability check does, since the
agent advertised it and it must then work. `ADVISORY`/`INFORMATIONAL` never affect it.
`blocked_by_auth` is `true` whenever any test was `SKIPPED` with a message containing the
literal marker `"AUTH-GATED:"` (a substring match, not a prefix -- the recorded message is
`str(report.longrepr)`, which for a skip wraps the reason in a `(path, lineno, "Skipped: ...")`
repr, so a prefix check would never match; see `plugin.py`'s `_AUTH_GATED_MARKER` and
review-slices-5-6.md N18) -- i.e. the agent requires authentication before `session/new` and no
`--auth-method` was given, so session-dependent requirements were never actually exercised and
the run cannot be honestly scored conformant regardless of how many other checks passed. See
`src/tck/report.py` for the full model (`Status`, `TestOutcome`, `RequirementResult`, `Verdict`,
`Report`) and `tests/test_report.py` for the aggregation rules exercised against synthetic data.

## Harness API (`tck.harness`)

Raw, hand-rolled asyncio NDJSON stdio client -- deliberately not built on the ACP Python SDK,
whose typed layer cannot emit malformed traffic and whose transport silently drops
non-conforming lines. This harness never drops or crashes on anything the agent sends; it
records it.

- `AgentLaunch(command, cwd=None, env_overrides={}, startup_timeout=5.0, default_timeout=5.0,
  max_line_bytes=64*1024*1024)` -- launch configuration. `env_overrides` is applied on top of
  the inherited `os.environ`. `max_line_bytes` is passed as `create_subprocess_exec(limit=...)`
  (the `StreamReader` buffer size) *and* is the line-reassembly threshold below: a single
  oversized stdout line is never truncated or dropped, only flagged (see `read_line` below).
- `AgentProcess(launch)` -- async context manager; spawns the subprocess in its own process
  group (POSIX) so the whole group can be terminated.
  - `send_raw(bytes | str)` -- writes exactly the given bytes plus `\n`; use this for
    deliberately malformed traffic. `drain()` is bounded by `launch.default_timeout`; a stuck
    write (e.g. an agent that never reads stdin, filling the pipe buffer) raises `AgentTimeout`
    instead of hanging the test forever.
  - `send_message(dict)` -- compact `json.dumps` plus `\n`.
  - `send_request(method, params=None, *, id=None) -> id` -- auto-increments an int id unless
    one is given (string ids allowed).
  - `send_notification(method, params=None)`.
  - `read_line(timeout=None) -> TranscriptEntry` -- next stdout line, raw bytes plus best-effort
    UTF-8/JSON decoding. Byte-lossless even past `max_line_bytes`: internally loops
    `StreamReader.readuntil(b"\n")`, and on `LimitOverrunError` consumes exactly the buffered
    bytes via `readexactly` and keeps looping rather than following `readline()`'s own behavior
    of silently discarding them -- the resulting `TranscriptEntry.oversize` is `True` whenever
    this happened, `False` otherwise. Raises `AgentTimeout` (carries the transcript so far) or
    `AgentExited` (carries exit code, `stderr_text()`, and the transcript).
  - `wait_for_response(id, timeout=None)` / `wait_for_message(predicate, timeout=None)` -- read
    until a match; every other line read along the way stays in `transcript` and is available
    via `pending()`.
  - `transcript: list[TranscriptEntry]` -- everything sent and received, in order, both
    directions, malformed lines included.
  - `stderr_text()` -- everything captured from stderr so far (drained continuously in the
    background so the child never blocks on it, bounded to the last 64 kB with a "truncated N
    earlier byte(s)" prefix once exceeded).
  - `close(grace=2.0)` -- close stdin, wait; SIGTERM the process group, wait; SIGKILL. Sets
    `exit_code` and `exited_on_stdin_close`. At each stage of that ladder, drains and records
    whatever the agent has already written to stdout since the last line any test read --
    including a partial final line with no trailing newline -- so output written after the last
    `read_line`/`wait_for_*` call (e.g. garbage flushed only once stdin hits EOF) still lands in
    `transcript` and is still checked by ACP-TRANSPORT-001/002. Never raises on lateness; each
    drain stage has its own short deadline carved out of `grace`.
- `TranscriptEntry` -- `direction`, `raw`, `timestamp`, `text`/`text_error`,
  `parsed`/`parse_error`, `oversize` (see `read_line` above). Decode/parse failures are recorded
  as fields, never raised.

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
- `rejects_second_initialize.py` -- conforming, but a second `initialize` on the same connection
  gets `-32600` instead of a normal handshake response; self-test proving no test in the suite
  itself ever sends a second `initialize`.
- `supports_v1_and_v2.py` -- advertises `protocolVersion: 2` support; correctly negotiates down
  to `1` for a client that only sends `protocolVersion: 1`. Self-test for ACP-INIT-003's
  `version != 65535 and version >= latest_supported` rule (PASS case, paired with
  `echoes_any_version.py`'s FAIL case).
- `asks_permission_closable.py` -- `asks_permission.py` plus `sessionCapabilities.close`;
  delays its permission request past `run_prompt`'s peek window so `session/close` deterministically
  wins the race, then replies to `session/close` before resolving the pending permission request
  as cancelled. Self-test for ACP-CLOSE-002 against a conforming, permission-asking agent, and
  (via `test_cancel.py`) for the otherwise-dead "cancelled" permission-outcome branch in
  `run_prompt` (review-slices-5-6.md S3, S10a).

See the layout listing above for the slice-4 defect fixtures (`hangs_until_cancel.py`,
`cancel_returns_error.py`, `cancel_wrong_stop_reason.py`, `update_after_response.py`,
`bad_stop_reason.py`, `duplicate_session_id.py`, `update_wrong_session.py`).

`cancel_wrong_stop_reason.py` sleeps 1.2s after receiving `session/cancel` before replying with
its (wrong) `stopReason: "end_turn"` -- an instant reply would land inside `test_cancel.py`'s
1.0s race window and, since `"end_turn"` is itself a valid `StopReason`, would make the cancel
test SKIP ("cancellation not exercised") instead of catching the defect. None of the other
fixtures need this: `cancel_returns_error.py`'s JSON-RPC error FAILs regardless of timing, and
`bad_stop_reason.py`/`update_wrong_session.py`/`conforming.py` etc. don't hang on the cancel
tests' prompt text at all (only the literal `__hang__` text triggers a hang in `conforming.py`
and `bad_stop_reason.py`), so `session/cancel` always loses the race against their immediate
reply and ACP-CANCEL-001/002 SKIP for them too -- see `tests/test_cli.py`'s `_CANCEL_IDS` note.

## Mock-client prompt driver (`_helpers.run_prompt`)

`test_session.py`/`test_prompt.py`/`test_cancel.py`/`test_session_capabilities.py` drive
`session/prompt` through `run_prompt(agent, session_id, blocks, *, on_cancel=False,
on_action=None, cancel_wait=0.5, timeout)` (`_helpers.py`), which acts as a minimal ACP client
for whatever the agent under test sends during the turn:

- `session/request_permission` is answered `{"outcome": {"outcome": "selected", "optionId":
  <first option's optionId>}}`, or `{"outcome": {"outcome": "cancelled"}}` once
  `session/cancel` has actually been sent for this turn.
- any other agent -> client request (`fs/*`, `terminal/*`, `elicitation/create`, ...) gets
  `-32601` (the mock client advertises `clientCapabilities: {}`), and is recorded on
  `PromptTurn.client_requests_seen` for later negative tests to use.
- `session/update` notifications are recorded, in order, as `(transcript_index, entry)` pairs.

It returns a `PromptTurn(response_entry, updates, client_requests_seen, cancelled_at_index,
action_response, action_sent_at_index)`. `cancelled_at_index` is `None` unless `on_cancel=True`
**and** `session/cancel` was actually sent before the prompt resolved -- see the race note below.

`on_action`, if given, is a zero-argument async callable fired at the same trigger point as
`on_cancel` (first update, or `cancel_wait` elapsed) instead of/alongside sending
`session/cancel` -- used by ACP-CLOSE-002 to send `session/close` mid-turn. Its response lands on
`PromptTurn.action_response`/`action_sent_at_index` (mirroring `cancelled_at_index`), both `None`
if `on_action` was not given or never fired. If the prompt's own response arrives before the
action's response -- a valid ordering the spec makes no claim against -- `run_prompt` does one
short peek read (the same window `cancel_race_peek` gives an update's immediate response) for the
action's response before returning, so an agent that replies to the action *after* resolving the
pending prompt doesn't lose that response to an early return (a real bug found and fixed via
`conforming_full.py`'s ACP-CLOSE-002 self-test, review-slices-5-6.md S3).

If `on_cancel=True`, `run_prompt` sends `session/cancel` for `session_id` as soon as either the
first `session/update` arrives or `cancel_wait` seconds elapse, whichever is first. This has an
inherent race for a real (or fixture) agent that replies immediately after its last update: by
the time the TCK has read that update, the agent may have *already* written its response to the
pipe, before the TCK ever decides to send cancel. `run_prompt` mitigates the most common case with
a short non-blocking-ish look for the response right after an update and before committing to
cancel -- if the response is already there, it is returned with `cancelled_at_index=None`, i.e.
as an honest race rather than a false "cancel preceded the response". This peek window and the
skip window below are not fixed constants: `_helpers.cancel_race_peek(timeout)` and
`_helpers.quiet_period(timeout)` derive both from whatever `--timeout` (`agent_launch.
default_timeout`) is in effect for the run, so a larger `--timeout` against a slower real agent
widens both windows instead of leaving them pinned to defaults tuned for the fast, offline
fixtures.

`test_cancel.py` (ACP-CANCEL-001/002) never turns an unavoidable race into a PASS or FAIL --
claiming a requirement was exercised when it was not is dishonest. It `pytest.skip("cancellation
not exercised: ...")` in two situations (`.agents/plan.md` "Cancel tests and the race"): (1)
`cancelled_at_index is None` -- the response was read before `session/cancel` could be sent at
all; (2) `session/cancel` was sent, but the response arrives with a valid, non-`cancelled` stop
reason within `quiet_period(agent_launch.default_timeout)` (measured off the transcript's
monotonic timestamps between the cancel notification and the response) -- the agent may simply
have finished on its own before reading the notification. The elapsed milliseconds are recorded
via `record_property("acp_tck_cancel_race_ms", ...)`. Outside those two situations the
requirement is judged normally: `stopReason: "cancelled"` PASSes; a JSON-RPC error, or a
non-`cancelled` stop reason arriving outside the race window, FAILs. The cancel tests use
`--cancel-prompt` text (see above) instead of the short text other prompt tests use, specifically
to make situations (1)/(2) less likely against a real agent.

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
  spec's prose (`extensibility.mdx`) says implementations MUST NOT add one; `validate_agent_message`/
  `validate_agent_response` do not flag this (see
  `tests/test_validation.py::test_unknown_root_field_is_permitted_by_the_vendored_schema`).
- `find_unknown_root_keys(def_name, obj) -> list[str]` (slice 7, backs ACP-SCHEMA-002) is the
  hand-written check that fills that gap: `_allowed_root_properties(def_name)` walks
  `allOf`/`anyOf`/`oneOf`/`$ref` to resolve the full property-name union a `$def`'s composition
  permits (always including `_meta`), and `find_unknown_root_keys` flags any root key of `obj`
  outside that set. Returns `[]` -- nothing to flag -- for a non-dict `obj`, or when the `$def`
  resolves no `properties` anywhere (e.g. a bare scalar/array union like `RequestId`) since
  there is nothing meaningful to compare keys against in that case.

## Conventions

- Dependency management is `uv` only, with exact pins (`==`), never bare `pip` or hand-edited
  `pyproject.toml` dependency entries.
- Protocol scope is ACP **v1 only**; v2/draft surfaces are out of scope.
- `.agents/` is the orchestrator's workbench. `.agents/research/*.md` are read-only inputs --
  they are the specification this code implements; do not edit them.
