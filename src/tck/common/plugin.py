"""The version-agnostic core of the ACP TCK's pytest plugin: CLI options, fixtures, markers,
the requirement result collector, and the JSON report / verdict-based exit code -- shared by
every protocol version's conformance suite.

Not a `pytest11` entry point itself and not usable alone: it reads the active protocol
version's `tck.common.version.VersionSpec` from `config.stash[VERSION_SPEC_KEY]`, which only a
thin per-version shim plugin (e.g. `tck.v1.plugin`) stashes, in its own `pytest_configure`,
before delegating to this module's hooks. Load the version's shim (`-p tck.v1.plugin`), never
this module directly.

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
from .report import (
    Report,
    Status,
    TestOutcome,
    Verdict,
    build_requirement_results,
    compute_verdict,
    current_tck_version,
    worse_status,
)
from .requirements import Tier
from .version import VersionSpec

VERSION_SPEC_KEY = pytest.StashKey[VersionSpec]()
"""Stashed by the active version's plugin shim (`tck.v1.plugin`, ...) in its own
`pytest_configure`, before it delegates to this module's `pytest_configure` -- every hook below
that needs a protocol_version/schema_revision/registry reads it from here rather than importing
a specific version's module."""

# --- options ---

_DEFAULT_CANCEL_PROMPT = (
    "Write a very long, detailed step-by-step explanation of how a compiler works, at least "
    "2000 words."
)
"""Default `--tck-cancel-prompt` text: long enough that a real agent is likely still generating
it when `session/cancel` arrives, so cancellation is actually exercised rather than raced.
Deliberately not special-cased by any fixture agent -- only the harness/tests may know it."""


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
        "--tck-auth-method",
        action="store",
        default=None,
        metavar="ID",
        help="An `authMethods[*].id` advertised by the agent under test. When given, "
        "`connected_agent`'s handshake calls `authenticate` with this methodId right after "
        "`initialize`, before anything else -- required to exercise session-dependent "
        "requirements against an agent that gates `session/new` behind authentication "
        "(ACP-AUTH-003 and every test that otherwise relies on `new_session()`/`connected_agent`).",
    )
    group.addoption(
        "--tck-allow-logout",
        action="store_true",
        default=False,
        help="Opt in to actually calling v2's `auth/logout` against the agent under test. Off "
        "by default because it may revoke the operator's own credentials for whatever account "
        "the agent is authenticated as -- without this flag, the logout test SKIPs instead of "
        "exercising it. v1 has no equivalent option: its logout test is gated purely by the "
        "`agentCapabilities.auth.logout` marker and is unaffected by this flag.",
    )
    group.addoption(
        "--tck-close-grace",
        action="store",
        type=float,
        default=2.0,
        metavar="S",
        help="Grace period in seconds budgeted at each stage of the agent-process shutdown "
        "ladder (stdin-close wait, post-SIGTERM wait, post-SIGKILL wait) on teardown "
        "(default: 2.0). Lower it to speed up tests/fixtures that deliberately never exit on "
        "their own -- a real agent under test should not normally need this changed.",
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
        close_grace=config.getoption("tck_close_grace"),
    )


# --- markers, collection ---


def pytest_configure(config: pytest.Config) -> None:
    if VERSION_SPEC_KEY not in config.stash:
        raise pytest.UsageError(
            "tck.common.plugin is not usable alone; load a version's shim instead "
            "(e.g. -p tck.v1.plugin or -p tck.v2.plugin), which stashes "
            "config.stash[VERSION_SPEC_KEY] before delegating to this module's hooks."
        )
    config.addinivalue_line(
        "markers",
        "requirement(*ids): bind this test to one or more ids in the active protocol "
        "version's requirement registry (see the version's plugin shim, e.g. tck.v1.plugin).",
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
    registry = config.stash[VERSION_SPEC_KEY].registry
    errors = []
    for item in items:
        for marker in item.iter_markers("requirement"):
            for req_id in marker.args:
                if req_id not in registry:
                    errors.append(f"{item.nodeid}: unknown requirement id {req_id!r}")
        # `_phase_status` folds xpass into PASS and xfail into SKIPPED, which misreads as the
        # test having genuinely run; a conformance suite has no legitimate use for "expected
        # failure", so forbid the marker outright.
        if item.get_closest_marker("xfail") is not None:
            errors.append(
                f"{item.nodeid}: @pytest.mark.xfail is not allowed in the conformance suite -- "
                "it is remapped to PASS/SKIPPED by _phase_status, not reported as-is; use "
                "pytest.skip with a reason instead"
            )
    if errors:
        raise pytest.UsageError(
            "Invalid test(s) in the conformance suite:\n" + "\n".join(errors)
        )


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


# --- auth-method context, for _helpers.connected_agent's auto-authenticate step ---

_AUTH_METHOD: contextvars.ContextVar[str | None] = contextvars.ContextVar("_AUTH_METHOD", default=None)


def current_auth_method_id() -> str | None:
    """The `--tck-auth-method` id configured for the current test, or `None` if none was given.
    Read by `tck.v1.conformance._helpers.connected_agent`/`skip_if_auth_gated`, which are plain
    functions with no fixture access of their own -- mirrors the `_ACTIVE_PROCESSES` contextvar
    pattern used for process registration."""
    return _AUTH_METHOD.get()


_INIT_AUTH_METHODS: contextvars.ContextVar[list[Any] | None] = contextvars.ContextVar(
    "_INIT_AUTH_METHODS", default=None
)


def current_initialize_auth_methods() -> list[Any] | None:
    """The cached `initialize` result's `authMethods` for the current test (`None` if
    `initialize` failed or the field is absent/not a list) -- read by
    `tck.v1.conformance._helpers.skip_if_auth_gated`: a `-32000` from `session/new` is only
    excusable as "needs --auth-method" when the agent actually advertised at least one auth
    method; an agent with none advertised has no defined remedy and the `-32000` is an ordinary
    failure, not something to skip."""
    return _INIT_AUTH_METHODS.get()


_ALLOW_LOGOUT: contextvars.ContextVar[bool] = contextvars.ContextVar("_ALLOW_LOGOUT", default=False)


def current_allow_logout() -> bool:
    """Whether `--tck-allow-logout` was given for this run. Read by both versions' logout
    requirements -- v1's `ACP-AUTH-004` (`logout`) and v2's `ACP-AUTH-203` (`auth/logout`) --
    to decide whether to actually call the destructive logout method; mirrors the
    `current_auth_method_id()` contextvar pattern above."""
    return _ALLOW_LOGOUT.get()


@pytest.fixture(autouse=True)
def _tck_auth_method_context(request: pytest.FixtureRequest) -> Any:
    token = _AUTH_METHOD.set(request.config.getoption("tck_auth_method"))
    allow_logout_token = _ALLOW_LOGOUT.set(bool(request.config.getoption("tck_allow_logout")))
    init_outcome: InitializeOutcome = request.getfixturevalue("agent_initialize_result")
    auth_methods = None
    if init_outcome.result is not None:
        # "authMethods" is a v1-derived literal, but it is unchanged in v2's
        # InitializeResponse too (root `authMethods`, schema.json @ 8f76d6c) -- safe to keep
        # here rather than adding it to VersionSpec.
        candidate = init_outcome.result.get("authMethods")
        if isinstance(candidate, list):
            auth_methods = candidate
    methods_token = _INIT_AUTH_METHODS.set(auth_methods)
    yield
    _AUTH_METHOD.reset(token)
    _INIT_AUTH_METHODS.reset(methods_token)
    _ALLOW_LOGOUT.reset(allow_logout_token)


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
    `agent_info`/`agent_capabilities` fields (`pytest_sessionfinish`). Autouse so it runs even
    when no test in the run carries a `capability` marker. The request `params` come from the
    active version's `VersionSpec.initialize_params()` -- the one place a version's own
    handshake shape enters this module."""
    launch = _build_launch(request.config)
    if launch is None:
        outcome = InitializeOutcome(None, "no --tck-agent-cmd given")
        request.config.stash[AGENT_INIT_KEY] = outcome
        return outcome

    spec = request.config.stash[VERSION_SPEC_KEY]

    async def _run() -> InitializeOutcome:
        try:
            async with AgentProcess(launch) as agent:
                # "initialize" is a v1-derived literal too, but the method name is unchanged
                # in v2 as well (meta.json keeps "initialize") -- safe to keep here.
                req_id = await agent.send_request("initialize", spec.initialize_params())
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
    """Whether the capability at `path` is advertised:

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
        # `initialize` is mandatory: if it failed, a capability-gated test is a real failure,
        # not "not applicable" -- SKIPPED would let a broken agent score falsely well.
        pytest.fail(f"cannot evaluate capability {path!r}: initialize failed: {outcome.error_message}", pytrace=False)
    spec = request.config.stash[VERSION_SPEC_KEY]
    negotiated = outcome.result.get("protocolVersion")
    if negotiated != spec.protocol_version:
        # The agent never negotiated this run's protocol version (e.g. a v1 agent run with
        # --protocol-version 2), so a capability path defined by that version's own
        # initialize-result shape can't be meaningfully evaluated -- the generic "not
        # advertised" message would misleadingly read as a missing feature rather than a
        # version mismatch. `_VERSION_MISMATCH_MARKER` flags the run as
        # `blocked_by_version_mismatch` instead of scoring it conformant on requirements that
        # were never actually exercised.
        pytest.skip(
            f"{_VERSION_MISMATCH_MARKER} negotiated protocolVersion={negotiated!r}, expected "
            f"{spec.protocol_version!r} -- capability {path!r} cannot be evaluated"
        )
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


_TRANSCRIPT_ENTRY_RAW_BYTES = 4 * 1024
"""Per-entry cap on the JSON report's `raw` field -- a single oversize line (an embedded image
block, a huge diff) must not blow up the report."""

_TRANSCRIPT_MAX_ENTRIES = 400
"""Cap on entries kept per failing test's JSON transcript: first/last half each, with a gap
marker between -- the start (handshake) and end (failure) matter most; a chatty middle (many
`session/update`s) is safest to elide."""


def _truncate_raw(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= _TRANSCRIPT_ENTRY_RAW_BYTES:
        return text
    head = encoded[:_TRANSCRIPT_ENTRY_RAW_BYTES].decode("utf-8", errors="replace")
    return f"{head}...[truncated {len(encoded) - _TRANSCRIPT_ENTRY_RAW_BYTES} byte(s)]..."


def _transcript_entries_dict(transcript: list[TranscriptEntry]) -> list[dict[str, Any]]:
    entries = [
        {
            "dir": entry.direction.value,
            "t": entry.timestamp,
            "raw": _truncate_raw(
                entry.text if entry.text is not None else f"<undecodable: {entry.text_error}>"
            ),
        }
        for entry in transcript
    ]
    if len(entries) <= _TRANSCRIPT_MAX_ENTRIES:
        return entries
    half = _TRANSCRIPT_MAX_ENTRIES // 2
    gap = len(entries) - 2 * half
    marker = {"dir": "gap", "t": 0.0, "raw": f"...[{gap} entry(ies) omitted]..."}
    return entries[:half] + [marker] + entries[-half:]


# --- requirement result collection ---
#
# One accumulator dict per test nodeid, built up across the setup/call/teardown phases pytest
# reports separately, then turned into a `tck.common.report.TestOutcome` at `pytest_sessionfinish` and
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
        # `record_property` accepts any scalar, but properties must be `dict[str, str]` (the
        # JSON report requires it) -- coerce here rather than trust every call site.
        state.properties[key] = str(value)

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

_STATUS_MARKUP: dict[Status, str] = {
    Status.PASS: "green",
    Status.FAIL: "red",
    Status.SKIPPED: "yellow",
    Status.NOT_TESTED: "light",
}
"""`TerminalWriter._esctable` keyword for each status's colour -- `light` is pytest's own name
for ANSI code 2 (faint/dim), used here as NOT_TESTED's own colour so "never ran" reads visually
distinct from a SKIPPED yellow."""


def _status_markup(status: Status, *, count: int | None = None) -> dict[str, bool]:
    """Markup kwargs for one status token. For the tier-count summary lines, pass the token's
    `count`: a zero count gets no markup at all, so it recedes instead of competing for
    attention -- that leaves `light` (dim) meaning only "NOT_TESTED", not also "zero of
    something". Non-zero counts (and per-requirement rows, which don't pass `count`) get the
    status's own colour."""
    if count == 0:
        return {}
    return {_STATUS_MARKUP[status]: True}


def _verdict_reason(verdict: Verdict) -> str:
    """The `VERDICT: NOT CONFORMANT (...)` reason: every actual cause, comma-joined, omitting
    zero-valued terms -- so a capability-only failure reads as "1 capability failure" rather
    than a misleading "0 mandatory failures".

    Per `compute_verdict`'s rules (`report.py`), at least one of the five conditions below is
    always true when not conformant; the `"no cause recorded"` fallback is unreachable, kept
    only so this never renders empty parentheses if that invariant changes.
    """
    mandatory = verdict.tier_counts[Tier.MANDATORY.value]
    capability = verdict.tier_counts[Tier.CAPABILITY.value]
    n_fail = mandatory[Status.FAIL.value]
    n_not_tested = mandatory[Status.NOT_TESTED.value]
    n_cap_fail = capability[Status.FAIL.value]

    parts: list[str] = []
    if n_fail:
        parts.append(f"{n_fail} mandatory failure{'s' if n_fail != 1 else ''}")
    if n_not_tested:
        parts.append(f"{n_not_tested} mandatory not tested")
    if n_cap_fail:
        parts.append(f"{n_cap_fail} capability failure{'s' if n_cap_fail != 1 else ''}")
    if verdict.blocked_by_auth:
        parts.append("blocked by authentication")
    if verdict.blocked_by_version_mismatch:
        parts.append("blocked by version mismatch")
    return ", ".join(parts) if parts else "no cause recorded"

STARTED_AT_KEY = pytest.StashKey[str]()
REPORT_KEY = pytest.StashKey[Report]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[STARTED_AT_KEY] = datetime.now(timezone.utc).isoformat()


def _agent_command(config: pytest.Config) -> list[str]:
    cmd = config.getoption("tck_agent_cmd")
    return shlex.split(cmd) if cmd else []


_AUTH_GATED_MARKER = "AUTH-GATED:"
_VERSION_MISMATCH_MARKER = "VERSION-MISMATCH:"


def _build_report(config: pytest.Config) -> Report:
    spec = config.stash[VERSION_SPEC_KEY]
    states = config.stash.get(TEST_STATES_KEY, {})
    tests_by_req: dict[str, list[TestOutcome]] = {}
    blocked_by_auth = False
    blocked_by_version_mismatch = False
    for nodeid, state in states.items():
        if state.status is None:
            continue  # no phase produced a verdict for this test (shouldn't normally happen)
        if state.status is Status.SKIPPED and _AUTH_GATED_MARKER in state.message:
            blocked_by_auth = True
        if state.status is Status.SKIPPED and _VERSION_MISMATCH_MARKER in state.message:
            blocked_by_version_mismatch = True
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

    results = build_requirement_results(tests_by_req, spec.registry)
    verdict = compute_verdict(
        results,
        blocked_by_auth=blocked_by_auth,
        blocked_by_version_mismatch=blocked_by_version_mismatch,
    )

    init_outcome: InitializeOutcome | None = config.stash.get(AGENT_INIT_KEY, None)
    agent_info = None
    agent_capabilities = None
    if init_outcome is not None and init_outcome.result is not None:
        agent_info = init_outcome.result.get(spec.agent_info_field)
        agent_capabilities = init_outcome.result.get(spec.agent_capabilities_field)

    return Report(
        tck_version=current_tck_version(),
        protocol_version=spec.protocol_version,
        schema_revision=spec.schema_revision,
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

    # Only override pytest's exit code for a normal completed run -- leave --collect-only,
    # usage errors, and interrupted runs alone. `exitstatus in (OK, TESTS_FAILED)` alone isn't
    # enough since --collect-only (or an empty -k match) also reports OK, so also require that
    # some test actually produced a verdict.
    states = config.stash.get(TEST_STATES_KEY, {})
    ran_any_test = any(state.status is not None for state in states.values())
    if exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED) and ran_any_test:
        session.exitstatus = pytest.ExitCode.OK if report.verdict.conformant else pytest.ExitCode.TESTS_FAILED


def _informational_note(result: Any) -> str:
    """A short, one-line note for an INFORMATIONAL-tier result, drawn from whatever
    `record_property(...)` values its test(s) recorded (`behaviour`, `acp_tck_stderr_bytes`,
    `connection_usable_after`) -- e.g. `ACP-INFO-PARSE-001  PASS  (silent)`. `""` for any other
    tier, or if no test bound to this id recorded anything recognized."""
    if result.tier is not Tier.INFORMATIONAL:
        return ""
    parts: list[str] = []
    for test in result.tests:
        behaviour = test.properties.get("behaviour")
        if behaviour:
            parts.append(behaviour)
        stderr_bytes = test.properties.get("acp_tck_stderr_bytes")
        if stderr_bytes is not None:
            parts.append(f"{stderr_bytes} stderr byte(s)")
        usable = test.properties.get("connection_usable_after")
        if usable:
            parts.append(f"conn after: {usable}")
    return "; ".join(parts)


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    report = config.stash.get(REPORT_KEY, None)
    if report is None:
        return  # e.g. --collect-only: sessionfinish still ran, but nothing was ever executed

    states = config.stash.get(TEST_STATES_KEY, {})
    if not any(state.status is not None for state in states.values()):
        # Nothing actually ran (e.g. --collect-only, or a -k/-m that matched zero tests) --
        # every requirement would read NOT_TESTED, which would print a misleading verdict for a
        # run that never intended to produce one at all.
        terminalreporter.write_line(
            "ACP TCK: no test executed in this run (collection-only, or the selection matched "
            "nothing) -- no requirement verdict to report.",
        )
        return

    registry = config.stash[VERSION_SPEC_KEY].registry
    results_by_id = {result.id: result for result in report.requirements}

    terminalreporter.section("ACP TCK requirement summary")
    for tier in _TIER_ORDER:
        ids = sorted(req_id for req_id, req in registry.items() if req.tier is tier)
        if not ids:
            continue
        terminalreporter.write_line(f"[{tier.value}]")
        for req_id in ids:
            result = results_by_id[req_id]
            status = result.status
            label = "NOT TESTED" if status is Status.NOT_TESTED else status.value
            note = _informational_note(result)
            suffix = f"  ({note})" if note else ""
            terminalreporter.write(f"  {req_id:<28} ")
            terminalreporter.write(label, **_status_markup(status))
            terminalreporter.write_line(suffix)

    verdict = report.verdict
    mandatory = verdict.tier_counts[Tier.MANDATORY.value]
    n_fail = mandatory[Status.FAIL.value]
    n_not_tested = mandatory[Status.NOT_TESTED.value]
    terminalreporter.write_line("")
    for tier in _TIER_ORDER:
        counts = verdict.tier_counts[tier.value]
        terminalreporter.write(f"  {tier.value:<14} ")
        statuses = list(Status)
        for i, status in enumerate(statuses):
            n = counts[status.value]
            token = f"{status.value}={n}"
            if i < len(statuses) - 1:
                terminalreporter.write(token, **_status_markup(status, count=n))
                terminalreporter.write(", ")
            else:
                terminalreporter.write_line(token, **_status_markup(status, count=n))

    if verdict.conformant:
        terminalreporter.write_line("VERDICT: CONFORMANT", bold=True, green=True)
    else:
        terminalreporter.write_line(
            f"VERDICT: NOT CONFORMANT ({_verdict_reason(verdict)})",
            bold=True,
            red=True,
        )
        keyword = config.getoption("keyword", "") or ""
        markexpr = config.getoption("markexpr", "") or ""
        selected = bool(keyword or markexpr)
        if selected and n_not_tested > 0:
            # A `-k`/`-m`-scoped run that did exercise some requirements is the case most
            # likely to be mistaken for a real verdict, so flag it regardless of pass count.
            selector = f"-k {keyword!r}" if keyword else f"-m {markexpr!r}"
            terminalreporter.write_line(
                f"hint: this run was scoped ({selector}), so some requirements were deselected "
                "(NOT TESTED) rather than exercised at all -- this reflects the selection, not a "
                "failure of the agent under test; run the full suite (no -k/-m) for a real "
                "conformance verdict.",
            )
        elif mandatory[Status.PASS.value] == 0 and (n_fail + n_not_tested) > 0:
            # Unscoped and nothing MANDATORY passed -- points at the agent under test, not at
            # test selection.
            terminalreporter.write_line(
                "hint: no MANDATORY requirement passed -- the agent may have failed to start or "
                "never responded; check --agent-cwd/--timeout/--startup-timeout and the stderr "
                "captured in the JSON report (--report-json).",
            )
        if verdict.blocked_by_auth:
            terminalreporter.write_line(
                "hint: one or more session-dependent tests were SKIPPED because the agent "
                "requires authentication before session/new and no --auth-method was given -- "
                "pass --auth-method <id> (an id from initialize's authMethods) to test this "
                "agent fully; the run cannot be scored CONFORMANT without it.",
                bold=True,
                yellow=True,
            )
        if verdict.blocked_by_version_mismatch:
            terminalreporter.write_line(
                "hint: one or more version-dependent tests were SKIPPED because this connection "
                "did not negotiate the protocol version this run targets (initialize negotiated "
                "a different protocolVersion than --protocol-version requested, in either "
                "direction) -- the agent under test may simply not support this version; the "
                "run cannot be scored CONFORMANT without a successful negotiation.",
                bold=True,
                yellow=True,
            )
