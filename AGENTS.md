# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
v1. It launches an agent implementation as a stdio subprocess and drives it through the
protocol to check conformance -- initialize, session lifecycle, prompt turns, cancellation,
error handling, and transport hygiene -- reporting which requirements pass, fail, are not
applicable, or were never exercised.

This slice ships only the harness core and the fixture agents/tests it will be verified
against; the conformance suite itself lands in a later slice.

## Layout

```
src/tck/
  __init__.py            console-script entry point (`main()`); stub for now
  harness/
    __init__.py           public API re-exports
    process.py            AgentProcess, AgentLaunch, AgentTimeout, AgentExited
    transcript.py          TranscriptEntry, Direction

tests/
  conftest.py              agent_launch() helper for spawning fixture agents
  test_harness.py          unit tests for the harness, run against the fixtures below
  fixtures/agents/
    _base.py               shared ConformingAgent core (not a standalone script)
    conforming.py          deterministic, offline, conforming ACP v1 agent
    banner_on_stdout.py     conforming + prints a non-ACP banner line to stdout first
    stderr_chatter.py      conforming + logs every received message to stderr
    never_responds.py      reads stdin forever, never writes anything
    exits_immediately.py   exits 0 without reading stdin
```

## Running tests

```
uv run pytest
```

The whole suite runs in a few seconds. Every test uses short (≤2s) per-call timeouts and
`asyncio.run(...)` directly -- there is no `pytest-asyncio` dependency; with only the harness
itself exercising async code, a bare `asyncio.run` per test was simpler than adding a plugin.

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

## Conventions

- Dependency management is `uv` only, with exact pins (`==`), never bare `pip` or hand-edited
  `pyproject.toml` dependency entries.
- Protocol scope is ACP **v1 only**; v2/draft surfaces are out of scope.
- `.agents/` is the orchestrator's workbench. `.agents/research/*.md` are read-only inputs --
  they are the specification this code implements; do not edit them.
