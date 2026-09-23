# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP).
It launches an agent implementation as a stdio subprocess and drives it through the protocol to
check conformance -- initialize, session lifecycle, prompt turns, cancellation, error handling,
and transport hygiene -- reporting which requirements pass, fail, are not applicable, or were
never exercised.

## Architecture

The codebase is split into a version-agnostic core and one package per protocol version:

- `src/tck/common/` -- harness, report model, requirement-tier vocabulary, and the pytest
  plugin's version-agnostic core, plus the `VersionSpec` glue that connects a version package to
  that core.
- `src/tck/v1/` -- ACP v1's protocol constants, vendored schema, requirement registry, schema
  validation, pytest plugin shim, and full conformance suite. v1 is the default and complete.
- `src/tck/v2/` -- the same shape for ACP v2 (Draft). Nothing under `v2/` imports from `v1/` or
  vice versa -- each version package is a self-contained, honestly-duplicated implementation
  sharing only `common/`. v2 is behind `--protocol-version 2` and still growing.

This split lets a new protocol version be added without duplicating or forking the harness,
report model, or plugin machinery. For the precise, current set of requirements each version
covers, read `src/tck/v{1,2}/requirements.py` (the registry, with citations) rather than this
file -- it's the source of truth and won't drift the way a prose summary would.

Each version's `plugin.py` is a thin shim: it copies every hook/fixture from `tck.common.plugin`
into its own module namespace (via `vars()`, not `import *`, so underscore-named autouse
fixtures aren't skipped), then overrides `pytest_configure` to stash that version's `SPEC` before
delegating to `tck.common.plugin.pytest_configure`. **Footgun:** the copied functions keep
`__globals__` pointing at `tck.common.plugin`'s own namespace, so only a function pytest resolves
*by name as a hook* (like `pytest_configure`) can actually be overridden in a shim -- redefining
a plain helper (e.g. `_build_report`) in `tck.v1.plugin` would silently do nothing, since every
copied hook still calls `tck.common.plugin`'s original.

Mirroring this split, `tests/common/`, `tests/v1/`, `tests/v2/` hold unit/registry/CLI tests, and
`tests/fixtures/agents/v{1,2}/` hold pure-stdlib, deterministic, offline fixture agents: a
conforming baseline plus one fixture per defect, each designed to trip exactly the requirement(s)
named in its filename/docstring. Read a conformance test's own `@pytest.mark.requirement(...)`/
`@pytest.mark.capability(...)` markers, and a fixture's own docstring, for ground truth --
`tests/v{1,2}/test_cli.py` asserts each fixture's exact FAIL/PASS set.

## Running the TCK against an agent

```
uv run acp-tck -- python tests/fixtures/agents/v1/conforming.py
uv run acp-tck --protocol-version 2 -- python tests/fixtures/agents/v2/conforming.py
```

Key options: `--agent-cwd DIR`, `--agent-env KEY=VAL` (repeatable), `--timeout S` (per-response
deadline, default 30), `--startup-timeout S`, `--test-timeout S` (per-test watchdog),
`--cancel-prompt TEXT` (prompt text for cancellation tests -- needs to keep a real agent busy
long enough for `session/cancel` to land; SKIP with "cancellation not exercised" means the race
was inconclusive, not that the agent failed), `--report-json PATH`, `--close-grace S`, `-k EXPR`,
`--protocol-version {1,2}` (default 1), `--auth-method ID` (drives `authenticate`/`auth/login`
before session-dependent tests; without it, auth-gated agents SKIP those tests and the run is
forced NOT CONFORMANT via `Verdict.blocked_by_auth`), `--allow-logout` (opt-in to actually
calling `logout`/`auth/logout`, since it may revoke the operator's own credentials).

If an agent negotiates down to a different protocol version than requested (e.g. a v1-only
agent run under `--protocol-version 2`), every requirement that judges the *result's shape*
against that version's rules SKIPs with a `"VERSION-MISMATCH:"`-prefixed message rather than
failing, and the run is forced NOT CONFORMANT (`Verdict.blocked_by_version_mismatch`) even with
zero FAILs. Requirements that judge only the negotiation *outcome* are judged normally and PASS
on an honest downgrade.

**Exit code** is the four-status verdict, not pytest's own: `0` iff `verdict.conformant` (no
MANDATORY FAIL/NOT_TESTED, no CAPABILITY FAIL, no auth/version-mismatch block), `1` otherwise.

You can also run the suite directly with plain pytest to add pytest's own flags, e.g.:

```
uv run pytest src/tck/v1/conformance -p tck.v1.plugin --tck-agent-cmd 'python tests/fixtures/agents/v1/conforming.py'
```

The plugin shims are deliberately not auto-registered via `pytest11` entry points -- always pass
`-p tck.v1.plugin` / `-p tck.v2.plugin` explicitly.

## Running the repo's own tests

```
uv run pytest
```

Runs harness unit tests, registry meta-tests, and end-to-end CLI tests against every fixture for
both v1 and v2 (a few minutes -- most of it is v2's end-to-end subprocess runs). Some self-tests
scope themselves with `-k` to just the module(s) owning the id(s) they assert on, which flips the
printed verdict to NOT CONFORMANT for that run (expected -- they're checking specific per-id
statuses, not the overall verdict).

## CI

`.github/workflows/ci.yml`: a required `test` job (`uv sync --locked && uv run pytest -q`) and an
informational `cross-check` job (`continue-on-error: true`) that runs the suite against
independently-built upstream agents (Rust SDK's `testy`, Python SDK's example/experimental v2
agents) via `scripts/cross-check.sh` and diffs the result against the documented baseline in
`docs/cross-check.md`. Both upstream v1 agents are expected to fail only the deliberately
strengthened `ACP-INIT-003`; v2's `testy` is expected fully conformant; the Python v2 example
agent is expected to fail a small, documented set tied to known upstream limitations. Any other
deviation is worth investigating as either a TCK bug or a genuine new upstream behavior.

## How to add a requirement + test

(Describes v1; a future version's suite follows the same shape under its own package.)

1. Add a `Requirement(...)` entry to `_DECLARATIONS` in `src/tck/v1/requirements.py`: pick an id
   (`ACP-<AREA>-<NNN>`), a `Tier` (from `tck.common.requirements`), and cite the exact
   `.agents/research/*.md` line(s) that back it -- those reports are the specification, not
   memory of the protocol.
2. Write a test under `src/tck/v1/conformance/`, marked `@pytest.mark.requirement("ACP-…")` with
   a docstring starting with the id(s). Use `connected_agent()` from `_helpers.py` to spawn the
   agent; `async def` tests work without extra setup.
3. If the requirement only applies when the agent advertises a capability, add
   `@pytest.mark.capability("agentCapabilities.some.path")` -- the test SKIPs with a
   "capability not advertised" reason otherwise. This checks for an *object marker* by default
   (present + non-null counts, even `{}`); pass `boolean=True` for a plain boolean gate. See
   `capability_is_supported()` in `src/tck/common/plugin.py`.
4. If the test needs to send a custom/probe method the agent isn't expected to recognize, prefix
   it with `_` (`_tck/does_not_exist`, ...) -- the extensibility rule requires custom methods to
   be `_`-prefixed, and the TCK holds its own probe traffic to the same rule.
5. Run `uv run pytest` -- `tests/v1/test_registry.py` fails if the new id isn't referenced by a
   test, or if a test references an unregistered id.
6. Consider adding a non-conforming fixture under `tests/fixtures/agents/v1/` that trips only the
   new requirement, and assert on it in `tests/v1/test_cli.py`.

## Tiers, statuses, reporting

Tiers (`tck.common.requirements.Tier`, shared across versions): `MANDATORY` (MUST), `CAPABILITY`
(only applies when advertised), `ADVISORY` (SHOULD -- reported, never the sole cause of a failing
verdict), `INFORMATIONAL` (spec silent / SDKs disagree -- reported only, never affects verdict).

Statuses (`tck.common.report.Status`): `PASS`, `FAIL`, `SKIPPED`, `NOT_TESTED` (a registered id no
test bound to during the run). A test that errors (setup/teardown exception, or an
`AgentExited`/`AgentTimeout` propagating out) is `FAIL`, not a separate status. Aggregating
several tests bound to the same requirement: any FAIL wins; else any PASS; else any SKIPPED; no
records -> NOT_TESTED.

`--report-json PATH` writes the full run as JSON: `tck_version`, `protocol_version`,
`schema_revision`, `agent_command`, `agent_info`/`agent_capabilities`, timestamps, `requirements`
(one entry per registry id with tier/capability/text/citation and every bound test's outcome --
FAIL outcomes carry a capped transcript), and `verdict` (`{conformant, blocked_by_auth,
blocked_by_version_mismatch, tier_counts}`). `conformant` is `true` iff no MANDATORY FAIL/
NOT_TESTED, no CAPABILITY FAIL, and neither block flag is set -- ADVISORY/INFORMATIONAL never
affect it, and a SKIPPED/NOT_TESTED CAPABILITY doesn't either. See `src/tck/common/report.py` and
`tests/common/test_report.py` for the exact aggregation rules.

## Harness API (`tck.common.harness`)

A raw, hand-rolled asyncio NDJSON stdio client -- deliberately not built on the ACP Python SDK,
whose typed layer cannot emit malformed traffic and whose transport silently drops
non-conforming lines. It never drops or crashes on anything the agent sends; it records it.

- `AgentLaunch(command, cwd=None, env_overrides={}, startup_timeout=5.0, default_timeout=5.0,
  max_line_bytes=64*1024*1024)`.
- `AgentProcess(launch)` -- async context manager, its own process group (POSIX).
  - `send_raw` / `send_message` / `send_request(method, params=None, *, id=None) -> id` /
    `send_notification`.
  - `read_line(timeout=None) -> TranscriptEntry` -- byte-lossless even past `max_line_bytes`
    (flags `oversize` rather than truncating). Raises `AgentTimeout` or `AgentExited` (both carry
    the transcript so far; the latter also stderr and exit code).
  - `wait_for_response(id, timeout=None)` / `wait_for_message(predicate, timeout=None)`.
  - `transcript` (everything sent/received, both directions, malformed lines included),
    `stderr_text()`, `close(grace=2.0)` (stdin-close -> SIGTERM -> SIGKILL ladder, draining
    stdout at each stage so late-written output is still captured).
- `TranscriptEntry` -- `direction`, `raw`, `timestamp`, `text`/`text_error`, `parsed`/
  `parse_error`, `oversize`. Decode/parse failures are recorded as fields, never raised.

## Mock-client prompt driver (`_helpers.run_prompt`)

Each version's conformance suite drives `session/prompt` through its own `run_prompt` helper,
which acts as a minimal ACP client: answers `session/request_permission`, records/rejects other
agent -> client requests, records `session/update` notifications in order, and supports
`on_cancel`/`on_action` to send `session/cancel`/another action mid-turn with a race-aware peek so
an agent that resolves before the driver acts isn't misreported.

v1 and v2 have genuinely different turn-end contracts and so have separate, non-shared
implementations: in v1 the `session/prompt` response itself carries `stopReason` and *is* the
turn's result; in v2 the response is only an acceptance receipt (`{messageId}`), and the turn's
outcome is learned from a later `state_update{state:"idle", stopReason}` notification. Read
`src/tck/v{1,2}/conformance/_helpers.py` directly for the exact turn-end predicate and
cancel-race handling before writing a new prompt test.

Cancellation tests never turn an unavoidable race into a false PASS/FAIL: they SKIP with
"cancellation not exercised" when the response was read before cancel could be sent, or when a
valid non-cancelled stop reason arrives within a short race window after cancel was sent.
`--cancel-prompt` exists specifically to make that race less likely against a real agent.

## Vendored schema

`src/tck/v{1,2}/schema/schema.json` and `meta.json` are verbatim copies of the ACP JSON Schema
from the spec repo; commit hash, vendor date, and refresh procedure live in each `schema/
VENDORED.md`. Do not hand-edit either JSON file. `tck.v{1,2}.protocol` and `tck.v{1,2}.validation`
derive their method-name tables and validation rules from these files at import time, so a schema
refresh mostly self-updates them -- but check each version's `validation.py` docstring for
hand-written carve-outs a refresh could invalidate (e.g. v1's `session/load` null-response quirk,
v2's batch dispatch and open-enum discriminator carve-out).

`tck.v{1,2}.validation` only validates messages the *agent under test* authors (its requests/
notifications to the client, and its responses to methods it implements) -- never a message the
TCK's own mock client writes. There is no `validate_client_message`; add one only if a future
requirement needs to assert on the harness's own outgoing traffic.

## Conventions

- Keep comments and docstrings concise and straightforward. Use plain language. Note non-obvious
  rationale, gotchas, and spec citations; skip narrating what the code already says, restating
  history slice-by-slice, or listing exhaustive cascades/examples that belong in tests, not prose.
  **Never mention intermediate research artifacts** (e.g., notes from researcher agents, work-in-progress
  findings in `.agents/research/`) in final code comments. Research documents are temporary and will be
  deleted once features are implemented. Only reference a research document in a comment if it is explicitly
  work-in-progress and you or the next agent plan to return to that part in this or the next iteration.
  After implementation, clean up or replace all research references with proper, permanent comments.
- Dependency management is `uv` only, with exact pins (`==`), never bare `pip` or hand-edited
  `pyproject.toml` dependency entries.
- `.agents/` is the orchestrator's workbench. `.agents/research/*.md` are read-only inputs --
  they are the specification this code implements; do not edit them.
- Licensed under Apache-2.0 (`LICENSE`); `pyproject.toml`'s `license`/`license-files` (PEP 639)
  are the source of truth -- do not add a `License ::` classifier alongside them.
