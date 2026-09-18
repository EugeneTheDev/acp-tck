# How is the A2A TCK structured and operated, and which design choices could translate to a Python/uv/pytest TCK for ACP agents launched as stdio subprocesses?

**Sources checked:** `a2a-tck` @ `263b9cfaf16a554bdfb166a7ba5b67716e946349` (2026-09-01, "fix: probe-and-route CARD-EXT precondition"), checkout at `/Users/eugene/Documents/JetBrains/projects/a2a-tck`, `git pull --ff-only` → already up to date.
**Confidence:** high — for *what the A2A TCK does* (read directly from source). Everything about ACP fit is my design judgement, not evidence.

> **Scope warning.** This report contains **zero ACP protocol truth**. Every "could translate" statement is a design idea derived from A2A prior art, per `.agents/skills/check-a2a-tck/SKILL.md:10-15`. The A2A TCK is a *different protocol* (HTTP-based, multi-transport, server-SUT). Nothing here is a requirement for the ACP TCK.
>
> The `## Requirements` section of the `researcher` output template is intentionally omitted: this question has no ACP protocol requirements to tier. The equivalent table below tiers *design choices by transferability*.

## Answer

The A2A TCK is **a pytest suite with a thin argparse CLI wrapper on top** (`run_tck.py` shells out to `python -m pytest tests/compatibility/ --sut-host=…`), plus a reusable library package (`tck/`) holding a declarative requirement registry, transport clients, validators and reporting. Tiering is **RFC 2119 (MUST/SHOULD/MAY)** expressed as pytest markers, with MUST = hard fail, SHOULD/MAY = `pytest.xfail`, and capability-conditional cases = `pytest.skip` **plus an explicit `skipped=True` record** in a side-channel collector so the report can distinguish "not applicable" from "passed" and from "never ran". The verdict is not the pytest exit code but a separate compatibility percentage per level, computed by an aggregator that deliberately counts `NOT TESTED` requirements as failures and excludes only `SKIPPED` ones. Its most transferable ideas for an ACP TCK are: the declarative `RequirementSpec` registry with stable IDs + spec URLs, requirement IDs embedded in test docstrings and recovered by a `pytest_runtest_makereport` safety-net hook, the three-way PASS/SKIPPED/NOT-TESTED verdict model, and the **in-band SUT steering convention** (message-ID prefixes mapped to Gherkin scenarios, with a code generator that emits reference SUTs). Least transferable: everything keyed on the HTTP agent card, `supportedInterfaces`/`protocolBinding` transport matrix, SSE/gRPC streaming plumbing, the webhook receiver, and the `--sut-host` URL model — an ACP agent is a stdio subprocess the TCK *spawns*, so process lifecycle, stderr capture and initialize-handshake-derived capabilities replace all of it.

## Design choices by transferability

| # | A2A design choice | Citation (`a2a-tck`) | Transferability to an ACP stdio TCK (my judgement) |
|---|---|---|---|
| 1 | Deliverable = pytest suite + argparse wrapper, not a pytest plugin | `run_tck.py:34-72`, `pyproject.toml:42-43` | **High** — same shape works; consider a real console-script entry point instead of a repo-root script |
| 2 | CLI options registered via `pytest_addoption` in the test-dir conftest | `tests/compatibility/conftest.py:46-78` | **High** — direct analogue: `--agent-cmd`, `--agent-cwd`, `--agent-env` |
| 3 | Declarative `RequirementSpec` registry with IDs, spec URL, level, tags | `tck/requirements/base.py:85-104`, `tck/requirements/registry.py:29-49` | **High** — the single best idea to port |
| 4 | Tier = RFC 2119 level, expressed as pytest markers | `pyproject.toml:52-62`, `tests/compatibility/markers.py:17-25` | **High**, if ACP requirements can be classified this way |
| 5 | MUST→fail, SHOULD/MAY→`xfail` | `tests/compatibility/core_operations/test_requirements.py:238-239`, `287-288` | **Medium** — see caveat below; `xfail` on MAY hides real bugs |
| 6 | Requirement ID in docstring + regex recovery in a makereport hook | `tests/compatibility/conftest.py:38`, `236-247`, `289-349` | **High** — cheap, robust; but see "Discrepancies" |
| 7 | Side-channel result collector separate from pytest's own results | `tck/reporting/collector.py:27-65` | **High** |
| 8 | Three-way status: PASS / FAIL / SKIPPED / NOT TESTED, with NOT TESTED counting against you | `tck/reporting/aggregator.py:61-78`, `164-180`, `199-214` | **High** — prevents a dead SUT scoring 100% |
| 9 | Reports: console + JSON + HTML + pytest-html + JUnit XML, always written | `run_tck.py:62-66`, `tests/compatibility/conftest.py:357-388` | **Medium-high** — console + JSON + markdown is probably enough |
| 10 | Abstract transport client ABC with one method per protocol operation | `tck/transport/base.py:72-161` | **Medium** — ACP has one transport; a single typed client is enough, but the ABC-per-operation shape is still useful |
| 11 | Operation dispatcher mapping requirement → client method + `sample_input` keys | `tck/transport/dispatch.py:36-70` | **Medium** — enables the fully generic parametrized runner |
| 12 | In-band SUT steering: `messageId` prefix selects SUT behaviour, no side channel | `scenarios/core_operations.feature:9-11`, `tck/requirements/base.py:22-31` | **High** — ACP analogue: prompt text / session-id conventions |
| 13 | Gherkin scenarios + code generator emitting reference SUTs in 3 languages | `scenarios/*.feature`, `codegen/generator.py:29-80` | **Low-medium** — large investment; a hand-written reference ACP agent is likely enough at first |
| 14 | Session-unique ID suffix so reruns never collide with stale SUT state | `tck/requirements/base.py:20-31` | **High** for any stateful SUT; **low** if each ACP run spawns a fresh process |
| 15 | Registry-invariant unit tests (meta-tests over the requirement table) | `tests/unit/requirements/test_expected_error_declared.py:21-34` | **High** — very cheap, very high value |
| 16 | Unit tests spin up a real `http.server` as a fake SUT for client regressions | `tests/unit/transport/test_http_json_client.py:31-45` | **High** — ACP analogue: a fake agent subprocess script |
| 17 | Probe-and-route classifier for preconditions not observable from capabilities | `tck/validators/extended_card.py:25-54` | **High** — directly relevant wherever ACP capability advertisement is ambiguous |
| 18 | Agent-card-driven transport/capability discovery | `tests/compatibility/conftest.py:92-167` | **Not transferable** — replace with the initialize response |
| 19 | Webhook receiver for push notifications | `tck/webhook/server.py`, `tests/compatibility/conftest.py:187-194` | **Not transferable** |
| 20 | SSE / gRPC streaming event collection with wall-clock timeout in a daemon thread | `tests/compatibility/_test_helpers.py:90-125` | **Idea transferable, code not** — the "hard deadline enforced from outside the blocking read" pattern maps well to reading an agent's stdout |

## Details

### 1. Deliverable shape

**Combination: library (`tck/`) + pytest suite (`tests/compatibility/`) + CLI wrapper (`run_tck.py`).** Not a pytest plugin — the CLI options are registered in the suite's own conftest, so they only exist when that directory is collected.

- `run_tck.py:34-72` builds an argv and `subprocess.run`s pytest; `run_tck.py:152-153` propagates pytest's exit code verbatim. There is no verdict logic in the CLI.
- Fixed arguments it always injects: `tests/compatibility/`, `--sut-host=…`, `--tb=short`, `--compatibility-report=reports/compatibility`, `--html=reports/tck_report.html --self-contained-html`, `--junitxml=reports/junitreport.xml` (`run_tck.py:36-66`).
- `--level {must,should,may}` becomes `-m <level>` (`run_tck.py:27-31`, `50-52`). `--transport` is passed through as a pytest option, not a marker filter (`run_tck.py:46-48`).
- Trailing `pytest_args` are appended, documented as usable after `--` (`run_tck.py:69-70`, `README.md:51`).
- Console script: `[project.scripts] run-tck = "run_tck:main"` (`pyproject.toml:42-43`), but all docs invoke `uv run ./run_tck.py …` instead (`README.md:27`, `AGENTS.md:97-99`).
- Pytest-level options, all with defaults so pytest can be driven directly: `--sut-host` (default `http://localhost`), `--transport` (default `all`), `--compatibility-report`, `--webhook-host` (`tests/compatibility/conftest.py:46-78`).
- **No config file.** No env-var configuration in the current code path either: `docs/SUT_REQUIREMENTS.md:19-45` documents `TCK_STREAMING_TIMEOUT` and a `.env` file, but the streaming timeout is now a hardcoded module constant (`tests/compatibility/_test_helpers.py:90`) and the documented `--sut-url`/`--category` flags no longer exist. That doc is stale — a warning about doc drift, not a design to copy.
- `pyproject.toml:48-62` sets `testpaths = ["tests"]`, `asyncio_mode = "auto"`, and declares all markers.

### 2. Test organization

Layout (`AGENTS.md:9-39` documents it; verified against the tree):

```
tck/                    # library: requirements/, transport/, validators/, reporting/, webhook/
tests/unit/             # harness self-tests, no SUT needed
tests/compatibility/    # conformance tests, need a live SUT
  conftest.py           # options, fixtures, hooks, report emission
  markers.py            # marker aliases
  _test_helpers.py      # record/assert/skip helpers
  _task_helpers.py      # precondition factories (create_completed_task, …)
  core_operations/      # cross-transport, parametrized
  agent_card/ grpc/ jsonrpc/ http_json/
scenarios/*.feature     # Gherkin describing required SUT behaviours
codegen/                # emits SUT projects from those scenarios
specification/          # vendored spec + JSON schema + generated proto stubs
```

Grouping is **two-dimensional and expressed redundantly**:

- **Tier (MUST/SHOULD/MAY)** lives on the `RequirementSpec` as `level` (`tck/requirements/base.py:34-39`, `92`) *and* on tests as markers (`tests/compatibility/markers.py:17-19`). For the generic runner the two agree by construction because the tests are parametrized straight off `get_must_requirements()` / `get_should_requirements()` / `get_may_requirements()` (`tests/compatibility/core_operations/test_requirements.py:149-157`, `197-205`, `246-254`). For hand-written tests the marker is applied manually (`tests/compatibility/agent_card/test_agent_card.py:183-185` — `@must @core class TestBindingFieldDeclaration`).
- **Category/subsystem** is expressed by directory *and* by free-form `tags` on the requirement, all tags centralised as constants in `tck/requirements/tags.py` (including test-strategy tags `NOT_AUTOMATABLE` and `MULTI_OPERATION`, `tck/requirements/tags.py:70-72`).
- **Transport** is either a `@pytest.mark.parametrize("transport", ALL_TRANSPORTS)` axis or a transport marker (`tests/compatibility/conftest.py:34-35`, `217-234`).

**How a test declares which requirement it checks** — three mechanisms, in order of authority:

1. Direct reference to the requirement constant: `req = CARD_PROTO_001` then `record(..., req=req, ...)` (`tests/compatibility/agent_card/test_agent_card.py:152`, `158-159`).
2. Requirement ID as the **first token of the docstring**: `"""CARD-PROTO-001: supportedInterfaces must be a non-empty list."""` (`tests/compatibility/agent_card/test_agent_card.py:151`), parsed by `_REQUIREMENT_ID_RE = r"([A-Z][A-Z0-9_]+-[A-Z]+-\d+)"` (`tests/compatibility/conftest.py:38`, `240-243`).
3. Last-resort recovery from the crashed frame's locals — the hook walks the traceback for the test's own frame and reads `req`/`transport` out of `f_locals`, relying on the convention that every test assigns `req = <CONST>` before any I/O (`tests/compatibility/conftest.py:250-286`).

Spec linkage is a `spec_url` on the requirement, pointing into the vendored spec with an anchor: `SPEC_BASE = "specification/specification.md#"` + e.g. `311-send-message` (`tck/requirements/base.py:108`, `tck/requirements/core_operations.py:69`). Failure messages embed it: `"{req.id} [{req.title}] failed on {transport}: {detail} (see {req.spec_url})"` (`tests/compatibility/_test_helpers.py:34-39`).

IDs are namespaced by area and uniqueness is enforced at import time — a duplicate ID raises `ValueError` when the registry module loads (`tck/requirements/registry.py:43-49`). ID prefixes are documented in `AGENTS.md:48-52`.

### 3. Capability-conditional tests

Three distinct mechanisms, and the reporting distinction is the important part.

**(a) Tag → capability-key table, in the generic runner.** `_CAPABILITY_TAG_TO_CARD_KEY = {"streaming": "streaming", "push-notification": "pushNotifications", "agent-card": "extendedAgentCard"}` (`tests/compatibility/core_operations/test_requirements.py:29-33`). If any of the requirement's tags maps to a capability the agent card does not declare, the test records a skip and calls `pytest.skip` (`:36-60`):

```python
compatibility_collector.record(
    requirement_id=requirement.id, transport=transport,
    level=requirement.level.value, passed=False, skipped=True,
)
pytest.skip(f"Agent card does not declare capabilities for: {missing}")
```

The **paired `record(skipped=True)` + `pytest.skip()`** is the load-bearing idiom: pytest reports a skip, and the compatibility report separately learns "this requirement is not applicable to this SUT".

**(b) Ad-hoc guards in hand-written tests.** `_skip_if_no_streaming` reads `agent_card["capabilities"]["streaming"]` (`tests/compatibility/grpc/test_streaming.py:77-81`). Note many of these call bare `pytest.skip` *without* recording, e.g. `tests/compatibility/grpc/test_streaming.py:80` — so the requirement falls through to `NOT TESTED` rather than `SKIPPED`. The conftest documents that this is deliberate: a bare skip is "a deliberate, untracked skip" and must not be auto-recorded as a failure (`tests/compatibility/conftest.py:310-318`).

**(c) Inverse guards — capability present makes a negative test impossible.** To assert "returns `PushNotificationNotSupportedError` when unsupported", the test must skip when the SUT *does* support push (`tests/compatibility/jsonrpc/test_error_codes.py:148-149`, `176-177`; same in `tests/compatibility/http_json/test_http_status.py:117-118`, `171-172`).

**(d) Probe-and-route, when the precondition is not observable from advertised capabilities.** For the extended agent card, whether the server has one *configured* cannot be read off the public card, so the tests probe the endpoint and route on a pure classifier returning `CONFIGURED` / `NOT_CONFIGURED` / `AUTH_REQUIRED` / `WRONG_ERROR`, where `WRONG_ERROR` is a conformance violation rather than a skip (`tck/validators/extended_card.py:25-54`). This is the newest commit in the repo and, in my view, the most sophisticated capability-handling idea in it.

**Status semantics in the report** (`tck/reporting/collector.py:88-103`, mirrored in `tck/reporting/aggregator.py:128-135`):

| Condition | Requirement status |
|---|---|
| any non-skipped result failed | `FAIL` |
| all results skipped | `SKIPPED` |
| otherwise | `PASS` |
| in registry, never recorded at all | `NOT TESTED` (`tck/reporting/aggregator.py:164-180`) |

`SKIPPED` is excluded from the compatibility denominator; `NOT TESTED` is **not**, and the docstring explains exactly why: otherwise "an unreachable SUT that answers zero requests can report 100% compatibility" (`tck/reporting/aggregator.py:69-78`, enforced at `:210`).

Skipped results are stored with `passed=False, skipped=True` (`tck/reporting/collector.py:40-65`) — the skip flag, not the pass flag, is what the reporting layer reads.

### 4. Harness

- **Connection model.** `--sut-host` → fetch `{host}/.well-known/agent-card.json` → build one client per declared `supportedInterfaces` entry, keyed by internal transport name (`tests/compatibility/conftest.py:92-167`). `_PROTOCOL_BINDING_MAP` maps `"JSONRPC"|"GRPC"|"HTTP+JSON"` to `(name, client_class)` (`:28-32`). First interface per binding wins (`:151-153`). If the card declares no interfaces, or the `--transport` filter leaves nothing, the fixture calls `pytest.fail` with a diagnostic listing what the card declared (`:123-127`, `:155-161`).
- **Fixture scoping.** Everything expensive is `scope="session"`: `sut_host`, `agent_card`, `transport_clients`, `validators`, `webhook_host`, `webhook_receiver`, `compatibility_collector` (`tests/compatibility/conftest.py:86-205`). Cleanup is a `yield` + loop calling `client.close()` (`:163-166`) and `receiver.stop()` (`:192-193`).
- **Cross-fixture/hook data sharing** uses `pytest.StashKey` on `config`, explicitly to avoid private attribute access (`tests/compatibility/conftest.py:41-43`, `104`, `204`; rationale in the docstring at `:198-201` and the ruff SLF001 rule in `AGENTS.md:63`).
- **Transport abstraction.** `BaseTransportClient(ABC)` declares one abstract method per protocol operation with schema-shaped signatures (`tck/transport/base.py:72-158`) and a no-op `close()` for subclasses to override (`:160-161`). Responses are `TransportResponse`/`StreamingResponse` dataclasses whose `error`, `error_code`, `task_id`, `context_id` are **abstract properties derived from `raw_response`** (`tck/transport/base.py:15-69`) — i.e. the harness normalises transport-specific error shapes behind one interface rather than in the tests.
- **Dispatch.** `OPERATION_DESCRIPTORS` maps each `OperationType` to a client method name plus required/optional `sample_input` keys (`tck/transport/dispatch.py:36-70`); the dispatcher deep-copies the sample input and makes `messageId`/`taskId` transport-unique "to prevent cross-transport state contamination on the SUT" (`tck/transport/dispatch.py:32-34`).
- **Precondition helpers instead of fixtures.** `create_completed_task`, `create_working_task`, `create_multiturn_task`, `create_multiturn_task_with_history` each send a message whose `messageId` prefix selects a SUT behaviour, validate the resulting state, and **`pytest.skip` on any setup failure** so a broken precondition is not reported as a conformance failure (`tests/compatibility/_task_helpers.py:42-63`, `70-101`, `104-133`, `138-183`).
- **Timeouts.** One constant, `_DEFAULT_STREAM_TIMEOUT_S = 10` (`tests/compatibility/_test_helpers.py:90`). `collect_events_with_timeout` drains the event iterator in a **daemon thread** and `join(timeout=…)`, precisely because `next(events_iter)` can block forever — it returns `(events, timed_out)` rather than raising (`tests/compatibility/_test_helpers.py:93-125`).
- **Retries: none.** There is no retry/backoff anywhere in the harness; flakiness is handled by skipping, not retrying.
- **Isolation.** A per-run `uuid4().hex[:8]` suffix on every generated ID, so stale SUT state from earlier runs cannot be mistaken for this run's (`tck/requirements/base.py:20-31`).
- **Safety net.** `pytest_runtest_makereport` (hookwrapper) snapshots `collector.record_count` at setup, and on a non-passing, non-skipped `call` phase with an unchanged count, synthesises a `record(passed=False, errors=[longreprtext])` for the requirement — so a crashed test still lands in the report as a failure rather than vanishing (`tests/compatibility/conftest.py:289-349`). Unknown requirement IDs default to level `MUST` (`:337-340`).

### 5. Reporting

- **Verdict computation.** `CompatibilityAggregator.aggregate()` produces `overall/must/should/may_compatibility` as percentages of requirements at that level with status `PASS`, after dropping `SKIPPED`; empty level ⇒ 100.0 (`tck/reporting/aggregator.py:89-103`, `199-214`). A requirement passes only if it passed on *every* transport where it ran (`:128-135`, documented `:66-68`).
- **There is no named conformance level** ("Bronze/Silver/Gold" etc.) and **no verdict-derived exit code**. The console formatter colours the overall number green at 100%, yellow at ≥80%, red below (`tck/reporting/console_formatter.py:27-28`, `73-82`) — thresholds live only in the formatter, not in the model. Exit code is pytest's own (`run_tck.py:152-153`).
- **Outputs.** Console summary is *always* printed at `pytest_sessionfinish` (header, SUT/timestamp metadata, overall %, per-level box table, per-transport line, failed-requirement list) (`tests/compatibility/conftest.py:357-377`; sections at `tck/reporting/console_formatter.py:47-137`). HTML and JSON are written only when `--compatibility-report` is given, derived from one path stem via `with_suffix` (`tests/compatibility/conftest.py:379-388`) — and `run_tck.py` always passes it, which is how the README can claim reports are always generated (`README.md:96-105`). JSON shape: `summary` / `per_requirement` / `per_transport` (+ `agent_card` when known), with percentages pre-formatted as `"93.3%"` **strings** (`tck/reporting/json_formatter.py:38-74`). pytest-html and JUnit XML come from off-the-shelf plugins (`run_tck.py:65-66`).
- **No markdown report and no spec-coverage matrix artifact.** The closest thing is the registry itself plus `NOT TESTED` rows in the report.

### 6. Self-testing

Yes, and this is a well-developed part of the repo. `tests/unit/` (27 files, ~3.2k lines) needs no SUT and is the only thing CI runs.

- **Reporting layer** is unit-tested end to end: `tests/unit/reporting/test_collector.py`, `test_aggregator.py` (346 lines), `test_console_formatter.py`, `test_html_formatter.py`, `test_json_formatter.py`.
- **The pytest hook itself** is unit-tested by importing private helpers out of the conftest (`from tests.compatibility.conftest import _extract_from_crashed_frame, _extract_requirement_and_transport`) and feeding them `MagicMock(spec=pytest.Item)` fakes with synthetic docstrings/callspecs/markers (`tests/unit/reporting/test_safety_net_hook.py:12-46`, `49-80`).
- **Registry invariants as meta-tests.** `test_named_error_requirements_declare_expected_error` regex-scans every requirement description for `MUST return <Name>Error` and asserts the requirement declares that exact `expected_error`; the docstring explains the failure mode it prevents — "tests fall back to accepting *any* error and a server returning the wrong code passes a MUST it should fail" (`tests/unit/requirements/test_expected_error_declared.py:1-34`). `expected_error_of()` then treats a missing binding as a registry bug, not a runtime condition (`tests/compatibility/_test_helpers.py:22-31`).
- **Fake SUTs.** Not a full fake agent, but real localhost servers for transport-client regressions: `tests/unit/transport/test_http_json_client.py` stands up a `http.server.HTTPServer` returning a 400 + JSON error body to reproduce an `httpx.ResponseNotRead` crash (`:31-45`, rationale `:1-10`). `tests/unit/webhook/test_server.py` exercises the webhook receiver.
- **Validators and codegen** are unit-tested too (`tests/unit/validators/*`, `tests/unit/codegen/*`).
- **Gap:** CI never runs the conformance suite against any SUT — the whole pipeline is `uv sync --extra dev` then `make lint unit-test` (`.github/workflows/ci.yml:10-17`, `Makefile:15-19`). The generated reference SUTs exist and are documented (`README.md:107-160`) but are driven manually.

### 7. Packaging / dev workflow

- Hatchling build; `name = "a2a-tck"`, `version = "1.0.0"` hardcoded; `requires-python = ">=3.11"` (`pyproject.toml:1-22`). Wheel packages are `["tck", "specification", "codegen"]` — note `tests/` is *not* shipped, so an installed wheel cannot run the conformance suite; the documented workflow is a git clone + `uv pip install -e .` (`pyproject.toml:45-46`, `README.md:12-20`).
- Runtime deps include pytest itself: `pytest`, `pytest-asyncio`, `pytest-html`, `httpx`, `grpcio`, `protobuf`, `googleapis-common-protos`, `jsonschema`, `gherkin-official`, `Jinja2` (`pyproject.toml:23-34`). Dev extra is just `ruff` + `mypy` (`:36-40`).
- `Makefile` is the task runner with a self-documenting `help` target: `proto`, `jsonschema`, `spec`, `unit-test`, `lint`, and three `codegen-*-sut` targets (`Makefile:1-29`).
- **The spec is vendored and regenerated**: `make spec` runs `scripts/update_spec.sh`, `make proto` regenerates Python gRPC stubs into `specification/generated/`, `make jsonschema` derives `specification/a2a.json` from `a2a.proto` (`Makefile:6-13`). The JSON schema is then loaded by the session-scoped `validators` fixture from `specification/a2a.json` (`tests/compatibility/conftest.py:170-178`).
- **No release automation.** No publish workflow, no tags-based release, no CHANGELOG; CI is lint + unit tests only (`.github/workflows/ci.yml`).
- **Documentation structure.** `README.md` sections: Requirements → Installation → Quick Start → CLI Reference (flag table) → Examples → Compatibility Levels (level/meaning/test-behaviour table, `README.md:66-82`) → Transports → Reports (report/file/description table) → SUT Code Generation (per-target) → Development (command table) → License. `AGENTS.md` carries the architecture tree, ID conventions and code style. `docs/` holds `SUT_REQUIREMENTS.md`, `SDK_VALIDATION_GUIDE.md`, `SPEC_UPDATE_WORKFLOW.md`, `DOCUMENTATION_STANDARDS.md` and **ADRs** (`docs/adrs/ADR-001..003`). `PRD/` holds the original PRD plus mermaid diagrams (`PRD/architecture.mmd`, `validation-flow.mmd`, `compatibility-report.mmd`, `test-parametrization.mmd`). `backlog/` is a file-per-task backlog with `tasks/` and `completed/`.
- **Agent skills as the user-facing runbook**: `run-tck`, `learn-requirement`, `diagnose-failure`, `update-a2a-spec`, plus per-SUT skills (`AGENTS.md:79-87`); `.agents/skills/run-tck/SKILL.md:15-70` is a step-by-step "verify prereqs → confirm SUT reachable → run MUST first" script.

### 8. Clearly *not* transferable to an ACP stdio TCK (my judgement — do not port)

1. **`--sut-host` URL as the SUT handle.** An ACP agent is a command to spawn, not a URL to poll. The whole `sut_host` → HTTP-GET → card chain (`tests/compatibility/conftest.py:86-105`) has no analogue.
2. **Agent card discovery at `/.well-known/agent-card.json`** and everything derived from it — `supportedInterfaces`, `protocolBinding`, per-interface URLs, first-interface-wins preference (`tests/compatibility/conftest.py:92-167`), the whole `agent_card/` test directory, `CARD-*` requirements, card caching and card signing.
3. **The transport matrix.** Three transports × every requirement is A2A's defining structural axis: `ALL_TRANSPORTS` parametrization, `@grpc`/`@jsonrpc`/`@http_json` markers, `transport_clients` dict, per-transport clients/validators/error bindings, per-transport report columns, `--transport` filtering (`tck/transport/base.py`, `tck/requirements/binding_*.py`, `tck/validators/{grpc,jsonrpc,http_json}/`, `tck/reporting/aggregator.py:182-197`). A single-transport ACP TCK should collapse this axis entirely — otherwise you inherit a dimension of complexity (dicts keyed by transport, "passes only if it passes on every transport") for no benefit.
4. **`ErrorBinding.expected_code(transport)` three-way error mapping** — JSON-RPC code / HTTP status / gRPC status name per error (`tck/requirements/base.py:233-257`, `260-391`). ACP over stdio needs one code space.
5. **HTTP-specific conformance surface**: status-code tests, `Content-Type` negotiation, AIP-193 error bodies, caching headers, TLS, `google.rpc.ErrorInfo` reasons (`tests/compatibility/http_json/test_http_status.py`, `tck/validators/error_info.py`, `tck/requirements/tags.py:73-96`).
6. **SSE / gRPC streaming plumbing** — `tests/compatibility/jsonrpc/test_sse_streaming.py`, `tests/compatibility/grpc/test_streaming.py`, `tck/validators/streaming.py`, the multi-stream and resubscribe machinery. The *pattern* of bounding a blocking read (`_test_helpers.py:93-125`) transfers; the SSE/gRPC code does not.
7. **Webhook receiver** — a local HTTP server the SUT calls back into, for push notifications (`tck/webhook/server.py`, fixture at `tests/compatibility/conftest.py:187-194`). ACP has no inbound-HTTP model here.
8. **proto/protobuf toolchain** — `buf`, `a2a.proto`, generated `_pb2` stubs, `ProtoSchemaValidator`, `scripts/install_buf.sh`, `make proto` (`specification/`, `tck/validators/proto_schema.py`).
9. **Long-lived shared SUT state as a correctness hazard** — transport-unique `messageId`/`taskId` and session-unique suffixes exist because one server instance serves all transports and survives across runs (`tck/transport/dispatch.py:32-34`, `tck/requirements/base.py:20-31`). A per-test freshly spawned ACP subprocess makes most of this unnecessary; keep it only if you reuse one process across tests.
10. **Multi-language SUT code generation** (`codegen/`, `sut/a2a-java`, `sut/a2a-jakarta`, Jinja templates, Maven/Quarkus/WildFly instructions). Only worth it when you must prove several independent SDKs conform. Note it is also *not* CI-verified.
11. **Also do not copy, for quality reasons rather than protocol reasons:** (a) `docs/SUT_REQUIREMENTS.md` documents flags and env vars that no longer exist (`--sut-url`, `--category`, `TCK_STREAMING_TIMEOUT`) — the drift comes from having behaviour documented in prose instead of generated from the registry; (b) the three near-identical MUST/SHOULD/MAY runner functions in `tests/compatibility/core_operations/test_requirements.py:158-288` are copy-paste triplicates differing only in the final `assert` vs `xfail`; (c) `_extract_from_crashed_frame` reading `f_locals` (`tests/compatibility/conftest.py:250-286`) is clever but fragile — an explicit marker or decorator carrying the requirement ID would be more robust.

## Testability notes

Translating the A2A mechanics to an ACP stdio SUT, mechanism by mechanism (all my design inference):

- **SUT handle.** Replace `--sut-host` with `--agent-cmd` (argv to spawn), plus `--agent-cwd`, repeatable `--agent-env`, and `--startup-timeout`. Keep the A2A shape: register them with `pytest_addoption` and give every one a default so plain `pytest` still works (`tests/compatibility/conftest.py:46-78`).
- **Capability discovery.** A2A's `agent_card` session fixture becomes an `initialize`-response fixture: one session-scoped fixture that performs the handshake once and stashes the result on `config` for the report, exactly as `_agent_card_key` does (`tests/compatibility/conftest.py:92-105`, `369`). The tag → capability-key table (`test_requirements.py:29-33`) then keys off advertised ACP capabilities instead of `card["capabilities"]`.
- **Process lifecycle is the new transport layer.** Where A2A has `client.close()` in a session fixture teardown (`conftest.py:163-166`), an ACP harness needs terminate-then-kill, stderr drained to a buffer and attached to failures, and a decision about scope: session-scoped process (fast, but inherits A2A's stale-state problem and its `tck_id` workaround) vs. per-test process (slow, but each test starts clean and crashes cannot cascade). I'd default to per-test-module or per-test, and drop the session-unique-ID machinery.
- **Timeouts become mandatory everywhere.** A hung stdio child is indistinguishable from a slow one, so every read needs a deadline; A2A's "drain in a daemon thread, `join(timeout)`, return `(events, timed_out)`" (`_test_helpers.py:93-125`) is the right shape — a timeout is data, not an exception.
- **A crashed agent must be attributable.** A2A's safety-net hook exists so a mid-test crash still produces a recorded failure (`conftest.py:289-349`). For stdio this matters more: process death during a test should record a FAIL against the requirement under test, with exit code and captured stderr as the error string.
- **Verdict model.** Port the four-status model verbatim (PASS / FAIL / SKIPPED / NOT TESTED) and the rule that only SKIPPED leaves the denominator (`tck/reporting/aggregator.py:69-78`, `:210`). For a stdio SUT this is even more valuable: an agent that fails to start yields zero records, and without the NOT-TESTED-counts-against-you rule it would score 100%.
- **What is *more* observable over stdio than over HTTP:** stderr, exit code, exit timing, whether the process closed stdout, whether it wrote non-JSON to stdout, whether it exited on stdin EOF. None of these have A2A analogues, so expect a whole requirement family with no prior art here.
- **What is *less* observable:** nothing that A2A tests via out-of-band HTTP (webhooks, card caching, TLS) has an ACP equivalent; conversely there is no "second client connects to the same server" scenario, so A2A's multi-stream/cross-transport-contamination tests have no counterpart.
- **Meta-tests are the cheapest win.** `test_expected_error_declared.py` shows the pattern: assert invariants over the requirement registry (every requirement has a spec URL; every declared ID is exercised by at least one test; no requirement is both MUST and capability-conditional). These run in CI with no SUT.
- **Self-test with a fake agent.** A2A's fake HTTP server (`tests/unit/transport/test_http_json_client.py:31-45`) becomes a set of tiny Python scripts under `tests/fixtures/agents/` — a conforming agent, a silent agent, an agent that emits malformed JSON, one that exits immediately, one that hangs. Run the real conformance suite against each and assert the *report* comes out as expected. A2A does **not** do this (its CI never runs the conformance suite at all, `.github/workflows/ci.yml:10-17`), so this would be an improvement on the prior art, not a port of it.

## Options for ACP TCK

**These three options are my design suggestions, derived from A2A prior art. They are not A2A facts and not ACP requirements.** All assume Python/uv/pytest and an SUT launched as a stdio subprocess.

### Option A — "A2A shape": pytest suite in-repo + argparse CLI wrapper

Mirror `run_tck.py` + `tests/conformance/` + `acp_tck/` library, with `--agent-cmd` replacing `--sut-host`.

- **Pros:** proven; the wrapper can force report flags on so users cannot forget them (`run_tck.py:62-66`); tests are plain pytest so contributors need no plugin knowledge; easiest path to a rich HTML/JSON report.
- **Cons:** the suite lives in `tests/`, which is **not** packaged (`pyproject.toml:45-46`) — users must clone the repo, and A2A's own `[project.scripts] run-tck` entry point is therefore near-useless (`pyproject.toml:42-43` vs `README.md:27`). Implementors cannot add their own tests alongside. Two layers of argument parsing (CLI → pytest) that must be kept in sync, and A2A shows the docs drifting out of sync first (`docs/SUT_REQUIREMENTS.md:19-45`).
- **Best if:** the ACP TCK is primarily run by the protocol maintainers against a handful of SDKs, from a clone.

### Option B — installable pytest plugin (+ a thin console script)

Ship `acp-tck` as a wheel whose package *includes* the conformance tests, register a pytest plugin via `[project.entry-points.pytest11]` for the options/fixtures/hooks, and expose the tests via `--acp-tck` / `pytest --pyargs acp_tck.conformance`.

- **Pros:** `uvx acp-tck --agent-cmd "…"` with no clone — a much better story for third-party agent authors than A2A's clone-and-edit flow; options/fixtures are available in *the user's own* test suite, so implementors can write ACP tests reusing the harness (something A2A cannot offer, since its options are defined in a non-shipped conftest at `tests/compatibility/conftest.py:46-78`); versioned conformance ("we pass acp-tck 0.4") becomes meaningful.
- **Cons:** more packaging discipline (test data, JSON schemas, fixture agent scripts must all be package data); plugin-scoped options are global, so care is needed not to collide with a host project's pytest config; harder to hack on for casual contributors; A2A gives no prior art here, so you would be designing it fresh.
- **Best if:** the goal is for external ACP agent authors to self-certify in their own CI.

### Option C — library-first: `acp_tck` as a scenario/assertion toolkit, conformance suite as one consumer

Invest primarily in the harness (`AgentProcess` driver, requirement registry, validators, collector/reporter) as a clean public API; the shipped conformance suite is one consumer of it, and users can build others.

- **Pros:** the parts of A2A that aged best are exactly its library parts — `RequirementSpec` (`tck/requirements/base.py:85-104`), the collector/aggregator (`tck/reporting/`), the validators — while the parts that aged worst are the hand-written per-transport test modules; a library boundary makes the registry-invariant meta-tests natural (`tests/unit/requirements/test_expected_error_declared.py`) and makes fake-agent self-testing trivial; it keeps the door open to a non-pytest runner later.
- **Cons:** slowest to a usable verdict for a real agent; risks over-engineering the framework before enough requirements exist to reveal what the abstractions should be (A2A's generic dispatcher at `tck/transport/dispatch.py:36-70` had to be escape-hatched for "multi-operation" requirements, which are excluded from the generic runner and re-implemented by hand, `tests/compatibility/core_operations/test_requirements.py:69-86`); a public API means compatibility obligations.
- **Best if:** you expect the ACP requirement set to keep moving and want the registry to be the single source of truth for tests, docs and coverage matrix.

**My leaning (a suggestion, not a finding):** start as Option A for the first 20–30 requirements so the abstractions are discovered rather than guessed, but make two decisions up-front that are expensive to retrofit — (1) put the conformance tests *inside* the installed package from day one, so Option B is a packaging change rather than a rewrite; (2) adopt the four-status verdict model and the declarative requirement registry immediately, since A2A's report quality rests entirely on those two (`tck/reporting/aggregator.py:69-78`, `tck/requirements/base.py:85-104`). Collapse the transport axis to nothing, and spend the saved complexity budget on process lifecycle, stderr capture and timeouts instead.

## Discrepancies

Internal inconsistencies *within the A2A TCK* worth knowing before porting (no ACP spec conflicts are in scope here):

1. **MAY requirements `xfail` rather than skip.** `README.md:74` and `run_tck.py:100` both say MAY is "skipped if the agent doesn't declare the capability", but `test_may_requirement` only skips on an undeclared capability and otherwise `xfail`s on any validation error (`tests/compatibility/core_operations/test_requirements.py:287-288`). So a declared-but-broken optional feature silently xfails instead of failing. The report is unaffected (the collector records `passed=False`, `tck/reporting/aggregator.py:128`), but the pytest run looks green.
2. **Two sources of truth for tier.** `RequirementSpec.level` and the pytest marker are independent; they agree in the generic runner by construction but are hand-maintained in the dedicated test modules (`tests/compatibility/agent_card/test_agent_card.py:183-185`). Nothing checks them for consistency.
3. **Bare-skip vs recorded-skip is inconsistent** across hand-written tests: some record `skipped=True` then skip (`tests/compatibility/http_json/test_http_status.py:117-118`), others just skip (`tests/compatibility/grpc/test_streaming.py:80`). The first yields `SKIPPED` (excluded from the score); the second yields `NOT TESTED` (counted as a failure). The conftest documents this as intentional (`tests/compatibility/conftest.py:310-318`), but the difference is invisible at the call site and easy to get wrong.
4. **Stale docs.** `docs/SUT_REQUIREMENTS.md:19-45` documents `--sut-url`, `--category` and `TCK_STREAMING_TIMEOUT`; none exist in the current code (`run_tck.py:104-137`, `tests/compatibility/_test_helpers.py:90`).
5. **Wheel does not contain the tests** (`pyproject.toml:45-46`) yet a `run-tck` console script is declared (`:42-43`), so `pip install a2a-tck && run-tck` cannot work — it exits on the missing `tests/compatibility` check (`run_tck.py:142-145`).
6. **Percentages are strings in JSON** (`"93.3%"`, `tck/reporting/json_formatter.py:73-74`) while floats in the model (`tck/reporting/aggregator.py:51`) — awkward for machine consumers.

## Open questions

Adjacent to my scope; for the orchestrator to route elsewhere:

- **What ACP requirements actually exist, and are they classifiable as MUST/SHOULD/MAY?** A2A's whole tiering rests on the spec using RFC 2119 language consistently. Whether ACP's spec does is a `check-specification` question, and it determines whether design choice #4 above is even available.
- **How does an ACP agent advertise capabilities, and is the advertisement complete enough to gate tests on?** A2A needed the probe-and-route escape hatch (`tck/validators/extended_card.py`) exactly where its card was not expressive enough. Owner: whoever holds the initialize/capabilities question.
- **Is there a published ACP JSON Schema the TCK can vendor and validate against**, mirroring `specification/a2a.json` + `JSONSchemaValidator`? A2A derives it from `.proto` via `make jsonschema`; ACP's equivalent pipeline is a spec question.
- **Process-lifecycle conformance requirements** (exit on stdin EOF, shutdown ordering, stderr expectations) have no A2A prior art at all. Needs an ACP-spec/reference-SDK researcher.
- **Should the TCK reuse one agent process across tests or spawn per test?** This is partly a protocol-semantics question (does ACP define session isolation within one process?) and partly performance; I flagged the tradeoff but cannot settle it from A2A.
- **Does ACP have a "reference agent" the TCK can self-test against**, or must the TCK ship its own fake agents? A2A generates SUTs from Gherkin (`codegen/`); whether the ACP Python SDK already offers an equivalent is a `check-python-sdk` question.
