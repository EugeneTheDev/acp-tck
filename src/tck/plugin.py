"""The `tck.plugin` pytest plugin: CLI options, fixtures, markers, the requirement result
collector, and the JSON report / verdict-based exit code for the ACP conformance suite
(`tck/conformance/`).

Not auto-registered via a `pytest11` entry point (see `.agents/plan.md` "Decided deliverable
shape") -- it is always loaded explicitly with `-p tck.plugin`, either by the `acp-tck` CLI
(`tck.__init__.main`) or by hand when running `pytest src/tck/conformance -p tck.plugin ...`.

Exit code mechanism: `pytest_sessionfinish` overwrites `session.exitstatus` (a documented
pytest extension point) to `0`/`1` from `Verdict.conformant`, but only when pytest itself
finished a normal run (`exitstatus` was `OK` or `TESTS_FAILED`) -- `--collect-only`, usage
errors, and interrupted runs keep pytest's own exit code untouched.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from .harness import AgentExited, AgentLaunch, AgentProcess, AgentTimeout, Direction, TranscriptEntry
from .protocol import PROTOCOL_VERSION, SCHEMA_REVISION
from .report import (
    Report,
    Status,
    TestOutcome,
    build_requirement_results,
    compute_verdict,
    current_tck_version,
    worse_status,
)
from .requirements import REGISTRY, Tier

# --- options ---

_DEFAULT_CANCEL_PROMPT = (
    "Write a very long, detailed step-by-step explanation of how a compiler works, at least "
    "2000 words."
)
"""Default `--tck-cancel-prompt` text: long enough that a real, working agent is likely still
generating it when `session/cancel` arrives, so the cancel tests actually get to exercise
cancellation instead of racing a near-instant response (see `.agents/plan.md` 'Cancel tests and
the race'). Deliberately not special-cased by any fixture agent -- fixtures must not know the
TCK's default prompt text, only the harness/tests do."""


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("acp-tck")
    group.addoption(
        "--tck-agent-cmd",
        action="store",
        default=None,
        help="Shell-quoted command that launches the agent under test, e.g. 'python agent.py'.",
    )
    group.addoption(
        "--tck-agent-cwd",
        action="store",
        default=None,
        help="Working directory to launch the agent in (default: inherit).",
    )
    group.addoption(
        "--tck-agent-env",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="Environment variable to overlay on the agent's process; repeatable.",
    )
    group.addoption(
        "--tck-timeout",
        action="store",
        type=float,
        default=30.0,
        help="Per-response deadline in seconds (default: 30).",
    )
    group.addoption(
        "--tck-startup-timeout",
        action="store",
        type=float,
        default=30.0,
        help="Deadline for the agent's first response (e.g. initialize) in seconds (default: 30).",
    )
    group.addoption(
        "--tck-cancel-prompt",
        action="store",
        default=_DEFAULT_CANCEL_PROMPT,
        metavar="TEXT",
        help="Prompt text sent by the cancellation tests (ACP-CANCEL-001/002) instead of the "
        "short deterministic text every other prompt test uses -- pick something that keeps a "
        "real agent busy long enough for `session/cancel` to land while the turn is still in "
        "flight (default: %(default)r). A SKIPPED cancel test means cancellation was not "
        "exercised (the turn finished before or shortly after cancel was sent), not that the "
        "agent failed conformance.",
    )
    group.addoption(
        "--tck-test-timeout",
        action="store",
        type=float,
        default=120.0,
        help="Per-test wall-clock watchdog in seconds (default: 120). Guards against an agent "
        "that hangs in a way no single read/write deadline catches (e.g. a `session/prompt` "
        "that keeps streaming `session/update`s forever) -- the test fails clearly instead of "
        "hanging the whole run, and the agent process is still closed and its transcript/stderr "
        "still attached to the failure.",
    )
    group.addoption(
        "--tck-report-json",
        action="store",
        default=None,
        metavar="PATH",
        help="Write the full JSON report (per-requirement status, verdict, failure diagnostics) "
        "to this path.",
    )


def _build_launch(config: pytest.Config) -> AgentLaunch | None:
    cmd = config.getoption("tck_agent_cmd")
    if not cmd:
        return None
    command = shlex.split(cmd)
    cwd = config.getoption("tck_agent_cwd")
    env_overrides: dict[str, str] = {}
    for entry in config.getoption("tck_agent_env") or []:
        key, _, value = entry.partition("=")
        env_overrides[key] = value
    return AgentLaunch(
        command=command,
        cwd=Path(cwd) if cwd else None,
        env_overrides=env_overrides,
        startup_timeout=config.getoption("tck_startup_timeout"),
        default_timeout=config.getoption("tck_timeout"),
    )


# --- markers, collection ---


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requirement(*ids): bind this test to one or more tck.requirements.REGISTRY ids.",
    )
    config.addinivalue_line(
        "markers",
        "capability(path, boolean=False): skip this test unless the cached `initialize` "
        "result advertises the capability at this dotted JSON path. By default (object-marker "
        "semantics) any present, non-null value counts; pass boolean=True for capabilities that "
        "are gated by `=== true` rather than by presence (e.g. 'agentCapabilities.loadSession').",
    )
    config.stash[TEST_STATES_KEY] = {}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    errors = []
    for item in items:
        for marker in item.iter_markers("requirement"):
            for req_id in marker.args:
                if req_id not in REGISTRY:
                    errors.append(f"{item.nodeid}: unknown requirement id {req_id!r}")
    if errors:
        raise pytest.UsageError("Unknown requirement id(s) in @pytest.mark.requirement:\n" + "\n".join(errors))


# --- async test support (no pytest-asyncio dependency) ---


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None
    argnames = pyfuncitem._fixtureinfo.argnames
    kwargs = {name: pyfuncitem.funcargs[name] for name in argnames if name in pyfuncitem.funcargs}
    timeout = pyfuncitem.config.getoption("tck_test_timeout")

    async def _run_with_watchdog() -> None:
        try:
            await asyncio.wait_for(testfunction(**kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            pytest.fail(
                f"test exceeded the {timeout}s per-test watchdog (--tck-test-timeout) -- the "
                "agent process has been closed; see the attached transcript/stderr",
                pytrace=False,
            )

    asyncio.run(_run_with_watchdog())
    return True


# --- fixtures ---


@pytest.fixture
def agent_launch(request: pytest.FixtureRequest) -> AgentLaunch:
    """A fresh `AgentLaunch` built from the `--tck-*` options, one per test."""
    launch = _build_launch(request.config)
    if launch is None:
        pytest.fail(
            "--tck-agent-cmd is required to run ACP TCK conformance tests "
            "(e.g. `acp-tck -- python agent.py`, or pass --tck-agent-cmd directly to pytest)",
            pytrace=False,
        )
    return launch


@pytest.fixture
def cancel_prompt_text(request: pytest.FixtureRequest) -> str:
    """The `--tck-cancel-prompt` text, used only by the cancellation tests (`test_cancel.py`) --
    every other prompt test keeps its own short, deterministic text."""
    return request.config.getoption("tck_cancel_prompt")


@dataclass(frozen=True)
class InitializeOutcome:
    """The cached result of one real `initialize` handshake, or why it failed."""

    result: dict[str, Any] | None
    error_message: str | None


AGENT_INIT_KEY = pytest.StashKey[InitializeOutcome]()


@pytest.fixture(scope="session", autouse=True)
def agent_initialize_result(request: pytest.FixtureRequest) -> InitializeOutcome:
    """One real `initialize` handshake against a fresh agent process, performed once per
    session -- cached for `capability`-marked tests to gate on, and for the JSON report's
    `agent_info`/`agent_capabilities` fields (`pytest_sessionfinish`). Autouse so it always
    runs once per session even when no test in the run happens to carry a `capability`
    marker."""
    launch = _build_launch(request.config)
    if launch is None:
        outcome = InitializeOutcome(None, "no --tck-agent-cmd given")
        request.config.stash[AGENT_INIT_KEY] = outcome
        return outcome

    async def _run() -> InitializeOutcome:
        try:
            async with AgentProcess(launch) as agent:
                req_id = await agent.send_request(
                    "initialize",
                    {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}},
                )
                entry = await agent.wait_for_response(req_id, timeout=launch.startup_timeout)
        except (AgentTimeout, AgentExited, OSError) as exc:
            return InitializeOutcome(None, str(exc))
        msg = entry.parsed
        if not isinstance(msg, dict) or "result" not in msg:
            return InitializeOutcome(None, f"initialize did not return a result: {entry.text!r}")
        return InitializeOutcome(msg["result"], None)

    outcome = asyncio.run(_run())
    request.config.stash[AGENT_INIT_KEY] = outcome
    return outcome


def _lookup_capability(result: dict[str, Any], path: str) -> Any:
    """Walk a dotted JSON path (e.g. `agentCapabilities.loadSession`) into `result`, returning
    `None` if any segment is missing or not an object -- the same "absent" outcome as an
    explicit `null`."""
    value: Any = result
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def capability_is_supported(result: dict[str, Any], path: str, *, boolean: bool = False) -> bool:
    """Whether the capability at `path` is advertised, per
    `.agents/plan.md` "Decisions (orchestrator)" / "Capability detection":

    - `boolean=True` gates (e.g. `promptCapabilities.image`, `agentCapabilities.loadSession`)
      are supported iff the value is `=== true` -- anything else (missing, `false`, `null`, an
      object) does not count.
    - Object markers (e.g. `agentCapabilities.mcpCapabilities`, `auth.logout`) are supported iff
      the value is present and non-null -- `{}` counts as supported, `false`/missing/`null`
      does not.
    """
    value = _lookup_capability(result, path)
    if boolean:
        return value is True
    return value is not None


@pytest.fixture(autouse=True)
def _tck_capability_gate(request: pytest.FixtureRequest) -> None:
    marker = request.node.get_closest_marker("capability")
    if marker is None:
        return
    path = marker.args[0]
    boolean = marker.kwargs.get("boolean", False)
    outcome: InitializeOutcome = request.getfixturevalue("agent_initialize_result")
    if outcome.result is None:
        # `initialize` is mandatory: if it failed, every capability-gated test is a real
        # failure of the requirement chain, not "not applicable" -- SKIPPED would let a broken
        # agent score falsely well on everything gated behind a capability.
        pytest.fail(f"cannot evaluate capability {path!r}: initialize failed: {outcome.error_message}", pytrace=False)
    if not capability_is_supported(outcome.result, path, boolean=boolean):
        pytest.skip(f"capability {path!r} not advertised by the agent under test")


# --- process registration, for failure diagnostics ---

_ACTIVE_PROCESSES: contextvars.ContextVar[list[AgentProcess] | None] = contextvars.ContextVar(
    "_ACTIVE_PROCESSES", default=None
)


def register_active_process(process: AgentProcess) -> None:
    """Register `process` so a failure in the currently running test attaches its transcript
    and stderr as report sections. No-op outside of `_tck_track_processes`'s scope (e.g. when
    `connected_agent` is used from a unit test, not a conformance test)."""
    processes = _ACTIVE_PROCESSES.get()
    if processes is not None:
        processes.append(process)


_PROCESSES_STASH_KEY = pytest.StashKey[list[AgentProcess]]()


@pytest.fixture(autouse=True)
def _tck_track_processes(request: pytest.FixtureRequest) -> Any:
    processes: list[AgentProcess] = []
    request.node.stash[_PROCESSES_STASH_KEY] = processes
    token = _ACTIVE_PROCESSES.set(processes)
    yield
    _ACTIVE_PROCESSES.reset(token)


def _format_transcript(transcript: list[TranscriptEntry]) -> str:
    lines = []
    for entry in transcript:
        arrow = "-->" if entry.direction is Direction.SENT else "<--"
        text = entry.text if entry.text is not None else f"<undecodable: {entry.text_error}>"
        lines.append(f"{arrow} {text}")
    return "\n".join(lines) if lines else "(empty)"


_STDERR_TRUNCATE_BYTES = 20 * 1024
_STDERR_TRUNCATE_MARKER = "...[truncated; showing last 20 kB]...\n"


def _truncate_stderr(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= _STDERR_TRUNCATE_BYTES:
        return text
    tail = encoded[-_STDERR_TRUNCATE_BYTES:].decode("utf-8", errors="replace")
    return _STDERR_TRUNCATE_MARKER + tail


def _transcript_entries_dict(transcript: list[TranscriptEntry]) -> list[dict[str, Any]]:
    return [
        {
            "dir": entry.direction.value,
            "t": entry.timestamp,
            "raw": entry.text if entry.text is not None else f"<undecodable: {entry.text_error}>",
        }
        for entry in transcript
    ]


# --- requirement result collection ---
#
# One accumulator dict per test nodeid, built up across the setup/call/teardown phases pytest
# reports separately, then turned into a `tck.report.TestOutcome` at `pytest_sessionfinish` and
# attached to every requirement id the test is bound to.


@dataclass
class _TestState:
    req_ids: list[str]
    status: Status | None = None
    message: str = ""
    duration_s: float = 0.0
    properties: dict[str, str] = field(default_factory=dict)
    transcript: list[dict[str, Any]] | None = None
    stderr: str | None = None


TEST_STATES_KEY = pytest.StashKey[dict[str, _TestState]]()


def _requirement_ids(item: pytest.Item) -> list[str]:
    ids: list[str] = []
    for marker in item.iter_markers("requirement"):
        ids.extend(marker.args)
    return ids


def _phase_status(report: pytest.TestReport) -> tuple[Status, str] | None:
    """The `(status, message)` this report phase implies, or `None` if the phase doesn't settle
    anything (e.g. a passing `setup`/`teardown`, which carries no verdict of its own)."""
    if report.passed:
        return (Status.PASS, "") if report.when == "call" else None
    if report.failed:
        return Status.FAIL, str(report.longrepr)
    if report.skipped:
        return Status.SKIPPED, str(report.longrepr)
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    outcome = yield
    report = outcome.get_result()

    states = item.config.stash[TEST_STATES_KEY]
    state = states.setdefault(item.nodeid, _TestState(req_ids=_requirement_ids(item)))
    state.duration_s += report.duration
    for key, value in report.user_properties:
        state.properties[key] = value

    settled = _phase_status(report)
    if settled is not None:
        phase_status, phase_message = settled
        if state.status is None or worse_status(phase_status, state.status) is phase_status:
            state.status = phase_status
            state.message = phase_message
        elif phase_status is state.status is Status.FAIL:
            # Rare (e.g. call *and* teardown both fail): keep both messages, not just the first.
            state.message = f"{state.message}\n{phase_message}"

    if report.failed:
        processes = item.stash.get(_PROCESSES_STASH_KEY, [])
        for index, process in enumerate(processes):
            report.sections.append(
                (f"ACP transcript (process {index})", _format_transcript(process.transcript))
            )
            report.sections.append((f"ACP stderr (process {index})", process.stderr_text() or "(empty)"))
        if processes:
            last = processes[-1]
            state.transcript = _transcript_entries_dict(last.transcript)
            state.stderr = _truncate_stderr(last.stderr_text())


# --- terminal summary + JSON report + verdict-based exit code ---

_TIER_ORDER = [Tier.MANDATORY, Tier.CAPABILITY, Tier.ADVISORY, Tier.INFORMATIONAL]

STARTED_AT_KEY = pytest.StashKey[str]()
REPORT_KEY = pytest.StashKey[Report]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[STARTED_AT_KEY] = datetime.now(timezone.utc).isoformat()


def _agent_command(config: pytest.Config) -> list[str]:
    cmd = config.getoption("tck_agent_cmd")
    return shlex.split(cmd) if cmd else []


def _build_report(config: pytest.Config) -> Report:
    states = config.stash.get(TEST_STATES_KEY, {})
    tests_by_req: dict[str, list[TestOutcome]] = {}
    for nodeid, state in states.items():
        if state.status is None:
            continue  # no phase produced a verdict for this test (shouldn't normally happen)
        outcome = TestOutcome(
            nodeid=nodeid,
            status=state.status,
            message=state.message,
            duration_s=state.duration_s,
            properties=dict(state.properties),
            transcript=state.transcript,
            stderr=state.stderr,
        )
        for req_id in state.req_ids:
            tests_by_req.setdefault(req_id, []).append(outcome)

    results = build_requirement_results(tests_by_req)
    verdict = compute_verdict(results)

    init_outcome: InitializeOutcome | None = config.stash.get(AGENT_INIT_KEY, None)
    agent_info = None
    agent_capabilities = None
    if init_outcome is not None and init_outcome.result is not None:
        agent_info = init_outcome.result.get("agentInfo")
        agent_capabilities = init_outcome.result.get("agentCapabilities")

    return Report(
        tck_version=current_tck_version(),
        protocol_version=PROTOCOL_VERSION,
        schema_revision=SCHEMA_REVISION,
        agent_command=_agent_command(config),
        agent_info=agent_info,
        agent_capabilities=agent_capabilities,
        started_at=config.stash.get(STARTED_AT_KEY, ""),
        finished_at=datetime.now(timezone.utc).isoformat(),
        requirements=results,
        verdict=verdict,
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    report = _build_report(config)
    config.stash[REPORT_KEY] = report

    path = config.getoption("tck_report_json")
    if path:
        Path(path).write_text(json.dumps(report.to_dict(), indent=2) + "\n")

    # Only override pytest's own exit code for a normal completed run (whether it passed or had
    # test failures) -- leave --collect-only, usage errors, and interrupted runs alone, since
    # every requirement would otherwise read NOT_TESTED and falsely force a non-conformant exit.
    if exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED):
        session.exitstatus = pytest.ExitCode.OK if report.verdict.conformant else pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    report = config.stash.get(REPORT_KEY, None)
    if report is None:
        return  # e.g. --collect-only: sessionfinish still ran, but nothing was ever executed

    aggregated = {result.id: result.status for result in report.requirements}

    terminalreporter.section("ACP TCK requirement summary")
    for tier in _TIER_ORDER:
        ids = sorted(req_id for req_id, req in REGISTRY.items() if req.tier is tier)
        if not ids:
            continue
        terminalreporter.write_line(f"[{tier.value}]")
        for req_id in ids:
            status = aggregated[req_id]
            label = "NOT TESTED" if status is Status.NOT_TESTED else status.value
            terminalreporter.write_line(f"  {req_id:<20} {label}")

    verdict = report.verdict
    mandatory = verdict.tier_counts[Tier.MANDATORY.value]
    terminalreporter.write_line("")
    for tier in _TIER_ORDER:
        counts = verdict.tier_counts[tier.value]
        summary = ", ".join(f"{status.value}={counts[status.value]}" for status in Status)
        terminalreporter.write_line(f"  {tier.value:<14} {summary}")

    if verdict.conformant:
        terminalreporter.write_line("VERDICT: CONFORMANT", bold=True, green=True)
    else:
        n_fail = mandatory[Status.FAIL.value]
        n_not_tested = mandatory[Status.NOT_TESTED.value]
        terminalreporter.write_line(
            f"VERDICT: NOT CONFORMANT ({n_fail} mandatory failures, {n_not_tested} not tested)",
            bold=True,
            red=True,
        )
        if mandatory[Status.PASS.value] == 0 and (n_fail + n_not_tested) > 0:
            terminalreporter.write_line(
                "hint: no MANDATORY requirement passed -- the agent may have failed to start or "
                "never responded; check --agent-cwd/--timeout/--startup-timeout and the stderr "
                "captured in the JSON report (--report-json).",
            )
