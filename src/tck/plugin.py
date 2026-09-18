"""The `tck.plugin` pytest plugin: CLI options, fixtures, markers, and the requirement result
collector for the ACP conformance suite (`tck/conformance/`).

Not auto-registered via a `pytest11` entry point (see `.agents/plan.md` "Decided deliverable
shape") -- it is always loaded explicitly with `-p tck.plugin`, either by the `acp-tck` CLI
(`tck.__init__.main`) or by hand when running `pytest src/tck/conformance -p tck.plugin ...`.

Full JSON reporting and a verdict-based exit code are slice 5 (see the TODOs in
`pytest_terminal_summary`); this slice only prints a compact console table.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from .harness import AgentExited, AgentLaunch, AgentProcess, AgentTimeout, Direction, TranscriptEntry
from .protocol import PROTOCOL_VERSION
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
        "capability(path): skip this test unless the cached `initialize` result has a "
        "non-null value at this JSON path (dotted, e.g. 'agentCapabilities.loadSession').",
    )
    config.stash[REQUIREMENT_RECORDS_KEY] = []


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
    asyncio.run(testfunction(**kwargs))
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


@pytest.fixture(scope="session")
def agent_initialize_result(request: pytest.FixtureRequest) -> InitializeOutcome:
    """One real `initialize` handshake against a fresh agent process, performed once per
    session and cached for `capability`-marked tests to gate on."""
    launch = _build_launch(request.config)
    if launch is None:
        return InitializeOutcome(None, "no --tck-agent-cmd given")

    async def _run() -> InitializeOutcome:
        try:
            async with AgentProcess(launch) as agent:
                req_id = await agent.send_request(
                    "initialize",
                    {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}},
                )
                entry = await agent.wait_for_response(req_id, timeout=launch.startup_timeout)
        except (AgentTimeout, AgentExited) as exc:
            return InitializeOutcome(None, str(exc))
        msg = entry.parsed
        if not isinstance(msg, dict) or "result" not in msg:
            return InitializeOutcome(None, f"initialize did not return a result: {entry.text!r}")
        return InitializeOutcome(msg["result"], None)

    return asyncio.run(_run())


@pytest.fixture(autouse=True)
def _tck_capability_gate(request: pytest.FixtureRequest) -> None:
    marker = request.node.get_closest_marker("capability")
    if marker is None:
        return
    path = marker.args[0]
    outcome: InitializeOutcome = request.getfixturevalue("agent_initialize_result")
    if outcome.result is None:
        pytest.skip(f"initialize failed: {outcome.error_message}")
    value: Any = outcome.result
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            value = None
            break
        value = value[part]
    if value is None:
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


# --- requirement result collection ---


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class RequirementRecord:
    id: str
    status: Status
    test_nodeid: str
    message: str


REQUIREMENT_RECORDS_KEY = pytest.StashKey[list[RequirementRecord]]()


def _requirement_ids(item: pytest.Item) -> list[str]:
    ids: list[str] = []
    for marker in item.iter_markers("requirement"):
        ids.extend(marker.args)
    return ids


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    outcome = yield
    report = outcome.get_result()

    ids = _requirement_ids(item)
    if ids:
        status: Status | None = None
        message = ""
        if report.when == "setup":
            if report.skipped:
                status, message = Status.SKIPPED, str(report.longrepr)
            elif report.failed:
                status, message = Status.FAIL, str(report.longrepr)
        elif report.when == "call":
            if report.passed:
                status, message = Status.PASS, ""
            elif report.failed:
                status, message = Status.FAIL, str(report.longrepr)
            elif report.skipped:
                status, message = Status.SKIPPED, str(report.longrepr)
        if status is not None:
            records = item.config.stash[REQUIREMENT_RECORDS_KEY]
            for req_id in ids:
                records.append(RequirementRecord(req_id, status, item.nodeid, message))

    if report.failed:
        processes = item.stash.get(_PROCESSES_STASH_KEY, [])
        for index, process in enumerate(processes):
            report.sections.append(
                (f"ACP transcript (process {index})", _format_transcript(process.transcript))
            )
            report.sections.append((f"ACP stderr (process {index})", process.stderr_text() or "(empty)"))


# --- terminal summary ---

_TIER_ORDER = [Tier.MANDATORY, Tier.CAPABILITY, Tier.ADVISORY, Tier.INFORMATIONAL]
_STATUS_PRIORITY = {Status.FAIL: 0, Status.PASS: 1, Status.SKIPPED: 2}


def _aggregate(records: list[RequirementRecord]) -> dict[str, Status]:
    aggregated: dict[str, Status] = {}
    for record in records:
        current = aggregated.get(record.id)
        if current is None or _STATUS_PRIORITY[record.status] < _STATUS_PRIORITY[current]:
            aggregated[record.id] = record.status
    return aggregated


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    records = config.stash.get(REQUIREMENT_RECORDS_KEY, [])
    aggregated = _aggregate(records)

    terminalreporter.section("ACP TCK requirement summary")
    for tier in _TIER_ORDER:
        ids = sorted(req_id for req_id, req in REGISTRY.items() if req.tier is tier)
        if not ids:
            continue
        terminalreporter.write_line(f"[{tier.value}]")
        for req_id in ids:
            status = aggregated.get(req_id)
            label = status.value if status is not None else "NOT TESTED"
            terminalreporter.write_line(f"  {req_id:<20} {label}")

    # TODO (slice 5): also emit a full JSON report (--report-json PATH) and compute a
    # four-status verdict (PASS/FAIL/SKIPPED/NOT TESTED) that drives the process exit code
    # (0 iff no MANDATORY FAIL or NOT TESTED). Today's exit code is whatever pytest itself
    # returns based on individual test outcomes.
