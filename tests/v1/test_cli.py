"""End-to-end CLI tests: run `python -m tck -- <fixture agent>` as a real subprocess and check
the exit code plus the terminal requirement-summary table.

A subprocess (not in-process `pytest.main`) is used deliberately: this file itself runs under
pytest, and pytest does not support a clean re-entrant `pytest.main()` call from within a
running session.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "agents" / "v1"
CLI_SUBPROCESS_TIMEOUT = 60
"""Wall-clock cap on one `_run_cli` subprocess. Against `wrong_id_echo.py`, every
`--timeout`-bounded MANDATORY/ADVISORY/INFORMATIONAL id fails/errors via a real timeout (since
id-correlated waits never resolve), which adds up across the full registry; 60s leaves headroom
without materially changing the overall suite's runtime budget, since every other self-test
finishes in a small fraction of this."""

_MANDATORY_IDS = {
    "ACP-TRANSPORT-001",
    "ACP-TRANSPORT-002",
    "ACP-JSONRPC-001",
    "ACP-JSONRPC-002",
    "ACP-JSONRPC-003",
    "ACP-INIT-001",
    "ACP-INIT-002",
    "ACP-INIT-003",
    "ACP-SCHEMA-001",
    "ACP-SESSION-001",
    "ACP-SESSION-002",
    "ACP-PROMPT-001",
    "ACP-PROMPT-002",
    "ACP-CANCEL-001",
    "ACP-CANCEL-002",
    "ACP-CONFIG-003",
    "ACP-AUTH-002",
    "ACP-CLIENTCAP-001",
    "ACP-CLIENTCAP-002",
    "ACP-CLIENTCAP-003",
    "ACP-EXT-001",
}
_ADVISORY_IDS = {
    "ACP-JSONRPC-004",
    "ACP-JSONRPC-005",
    "ACP-INIT-004",
    "ACP-PROMPT-003",
    "ACP-LOAD-003",
    "ACP-DELETE-002",
    "ACP-META-001",
    "ACP-ERROR-001",
    "ACP-SHUTDOWN-001",
    "ACP-SCHEMA-002",
    "ACP-AUTH-005",
    # ACP-AUTH-001: its only assertion, AUTH-A5 (auth method ids are unique), is advisory in
    # the auth research -- not in _MANDATORY_IDS.
    "ACP-AUTH-001",
}
_INFORMATIONAL_IDS = {
    "ACP-STDERR-001",
    "ACP-INFO-PARSE-001",
    "ACP-INFO-INVALIDREQ-001",
    "ACP-INFO-UNKNOWNSESSION-001",
}
_CAPABILITY_IDS = {
    "ACP-LOAD-001",
    "ACP-LOAD-002",
    "ACP-RESUME-001",
    "ACP-RESUME-002",
    "ACP-LIST-001",
    "ACP-LIST-002",
    "ACP-DELETE-001",
    "ACP-CLOSE-001",
    "ACP-CLOSE-002",
    "ACP-ADDDIRS-001",
    "ACP-MODES-001",
    "ACP-MODES-002",
    "ACP-CONFIG-001",
    "ACP-CONFIG-002",
    "ACP-PROMPTCAP-001",
    "ACP-PROMPTCAP-002",
    "ACP-PROMPTCAP-003",
    "ACP-AUTH-004",
    # ACP-AUTH-003: CAPABILITY with capability="inferred:authMethods" -- runs only when
    # `authMethods` is non-empty and `--tck-auth-method` was given, otherwise SKIPPED.
    "ACP-AUTH-003",
}
_ALL_IDS = _MANDATORY_IDS | _ADVISORY_IDS | _CAPABILITY_IDS

_CANCEL_IDS = {"ACP-CANCEL-001", "ACP-CANCEL-002"}
"""None of the fixtures below `hangs_until_cancel.py`, `cancel_returns_error.py`,
`cancel_wrong_stop_reason.py`, and `update_after_response.py` deliberately withhold their
response until `session/cancel` arrives for arbitrary prompt text -- they resolve the turn
immediately, same as `conforming.py`. So for all of them, `session/cancel` always loses the
race and the cancel tests SKIP with "cancellation not exercised" rather than PASS or FAIL."""

_CAPABILITY_GATED_IDS = _CAPABILITY_IDS | {"ACP-LOAD-003", "ACP-DELETE-002"}
"""Every id that SKIPs (rather than PASSes) against `conforming.py`, which advertises
`agentCapabilities: {}` and no modes/configOptions/authMethods -- every CAPABILITY-tier id
(including `ACP-AUTH-003`, `capability="inferred:authMethods"`), plus the two ADVISORY ids
(`ACP-LOAD-003`, `ACP-DELETE-002`) that are still gated behind a `@pytest.mark.capability(...)`
marker on their test function even though their `Requirement.tier` itself is ADVISORY, not
CAPABILITY (see `test_session_capabilities.py` module docstring)."""


def _run_cli(
    fixture: str,
    *,
    k: str | None = None,
    timeout: str = "1",
    report_json: str | None = None,
    test_timeout: str | None = None,
    startup_timeout: str = "1",
    cancel_prompt: str | None = None,
    auth_method: str | None = None,
    close_grace: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "tck",
        "--timeout",
        timeout,
        "--startup-timeout",
        startup_timeout,
    ]
    if test_timeout is not None:
        cmd += ["--test-timeout", test_timeout]
    if k is not None:
        cmd += ["-k", k]
    if report_json is not None:
        cmd += ["--report-json", report_json]
    if cancel_prompt is not None:
        cmd += ["--cancel-prompt", cancel_prompt]
    if auth_method is not None:
        cmd += ["--auth-method", auth_method]
    if close_grace is not None:
        cmd += ["--close-grace", close_grace]
    cmd += [
        "--",
        sys.executable,
        str(FIXTURES_DIR / fixture),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_SUBPROCESS_TIMEOUT)


_TABLE_ROW_RE = re.compile(r"^\s*(ACP-\S+)\s+(PASS|FAIL|SKIPPED|NOT TESTED)\b")


def _table_statuses(output: str) -> dict[str, str]:
    """Parse `<id> <STATUS>` pairs out of the terminal summary table. The status label is not
    always one token -- `NOT TESTED` is two words (`plugin.py:675`) -- and a row can carry a
    trailing `  (note)` suffix (`_informational_note`), so match the known status labels by
    regex instead of assuming exactly two whitespace-split tokens; without this, `NOT TESTED`
    rows silently vanish from the parsed dict instead of being recorded, and every
    `statuses.get(x) == "PASS"` check elsewhere only works by accident (`None != "PASS"`)."""
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        match = _TABLE_ROW_RE.match(line)
        if match:
            statuses[match.group(1)] = match.group(2).replace("NOT TESTED", "NOT_TESTED")
    return statuses


def test_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--help"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "acp-tck" in result.stdout


def test_version_works():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--version"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "acp-tck" in result.stdout


def test_missing_agent_command_is_an_error():
    result = subprocess.run(
        [sys.executable, "-m", "tck"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0


def test_conforming_agent_passes_everything():
    """`conforming.py` only withholds a response for the literal `__hang__` prompt text (see
    its docstring), which the cancel tests deliberately do not send -- the TCK must not rely on
    a fixture's own sentinel, and a real agent doesn't know it either. So `session/cancel`
    always loses the race against this fixture's immediate reply, and ACP-CANCEL-001/002 SKIP
    ("cancellation not exercised") rather than PASS. `conforming.py` also advertises
    `agentCapabilities: {}` (no `loadSession`, no `sessionCapabilities`), so every
    CAPABILITY-tier id -- plus the two ADVISORY ids gated behind a capability marker
    (`ACP-LOAD-003`, `ACP-DELETE-002`) -- SKIPs too, rather than PASSing or being NOT_TESTED.
    Everything else still PASSes."""
    result = _run_cli("conforming.py")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    # N13's regex-based `_table_statuses` fix now actually parses INFORMATIONAL-tier rows too
    # (they carry a trailing `(note)` suffix that used to make them silently vanish, coincidentally
    # matching `_ALL_IDS`, which was never meant to include them) -- so compare against the union
    # explicitly rather than let that omission look intentional.
    assert set(statuses) == _ALL_IDS | _INFORMATIONAL_IDS, (
        f"requirement table missing/extra ids: {result.stdout}"
    )
    skip_ids = _CANCEL_IDS | _CAPABILITY_GATED_IDS
    for req_id in skip_ids:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised/unadvertised):\n{result.stdout}"
    for req_id, status in statuses.items():
        if req_id in skip_ids:
            continue
        assert status == "PASS", f"{req_id} is {status}, expected PASS for the conforming fixture:\n{result.stdout}"
    assert "NOT TESTED" not in result.stdout
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_exits_immediately_fails_gracefully():
    result = _run_cli("exits_immediately.py")
    assert result.returncode != 0
    assert "INTERNALERROR" not in result.stdout
    assert "INTERNALERROR" not in result.stderr
    statuses = _table_statuses(result.stdout)
    for req_id in _MANDATORY_IDS:
        assert statuses.get(req_id) == "FAIL", f"{req_id} should FAIL when the agent never responds"
    # ACP-AUTH-003 is CAPABILITY-tier, not MANDATORY, so it is not covered by the loop above --
    # assert its SKIP explicitly instead: it is
    # conditional on --tck-auth-method regardless of the agent's own behavior, and SKIPs even
    # against a dead agent, since the TCK never even attempts to connect for it without a
    # configured auth method (see test_authentication.py).
    assert statuses.get("ACP-AUTH-003") == "SKIPPED", "ACP-AUTH-003 should SKIP without --auth-method"


def test_scoped_k_run_prints_deselection_hint_not_no_mandatory_passed_hint():
    """The `-k`/deselection hint must print whenever any requirement is NOT_TESTED because its
    tests were deselected, independent of whether any MANDATORY
    requirement PASSed -- `conforming.py -k initialize` PASSes several MANDATORY requirements
    (ACP-INIT-*, ACP-TRANSPORT-*, ...) yet is still NOT CONFORMANT overall (every other
    MANDATORY id is NOT_TESTED, which counts as a failure), so this exercises the scoped-run
    branch, not the older "no MANDATORY requirement passed at all" branch, and checks the
    wording distinguishes deselection from an agent that never started."""
    result = _run_cli("conforming.py", k="initialize")
    assert result.returncode != 0
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout
    assert "NOT TESTED" in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-001") == "PASS", result.stdout

    assert "hint: this run was scoped" in result.stdout, result.stdout
    assert "-k 'initialize'" in result.stdout, result.stdout
    assert "no MANDATORY requirement passed" not in result.stdout, result.stdout


def test_banner_on_stdout_fails_transport_001_but_passes_transport_002():
    """The banner is plain ASCII -- valid UTF-8 -- so it must FAIL ACP-TRANSPORT-001 (framing)
    but PASS ACP-TRANSPORT-002 (UTF-8), not be misreported as a UTF-8 violation."""
    result = _run_cli("banner_on_stdout.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-TRANSPORT-001") == "FAIL", result.stdout
    assert statuses.get("ACP-TRANSPORT-002") == "PASS", result.stdout
    assert statuses.get("ACP-SCHEMA-001") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-TRANSPORT-001", "ACP-SCHEMA-001"} - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_invalid_utf8_fails_transport_002():
    """`invalid_utf8.py` is ACP-TRANSPORT-002's real negative control: a lone undecodable line
    makes ACP-TRANSPORT-002 FAIL."""
    result = _run_cli("invalid_utf8.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-TRANSPORT-002") == "FAIL", result.stdout


def test_garbage_after_response_fails_transport_001():
    """`garbage_after_response.py` writes non-JSON to stdout only after stdin closes -- strictly
    after the last response any test awaits. `close()` must drain and record that line so
    ACP-TRANSPORT-001 catches it instead of reporting a false PASS."""
    result = _run_cli("garbage_after_response.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-TRANSPORT-001") == "FAIL", result.stdout


def test_asks_permission_agent_passes_everything():
    """`asks_permission.py` sends `session/request_permission` before resolving every prompt --
    the mock client (`run_prompt`) must answer it for any prompt/transport/schema test to ever
    resolve at all."""
    result = _run_cli("asks_permission.py")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} is {statuses.get(req_id)}, expected PASS:\n{result.stdout}"


def test_asks_permission_closable_agent_passes_close_002():
    """`asks_permission_closable.py` combines `asks_permission.py`'s mid-turn
    `session/request_permission` with `sessionCapabilities.close` support: `session/close` on
    an in-flight, permission-pending prompt must resolve it as cancelled. `run_prompt`'s
    dispatcher (which answers any agent -> client request while waiting for the prompt's own
    response) is what makes this PASS deterministically, instead of deadlocking on the
    unanswered permission request.

    Uses a longer `--timeout` than this module's default (`_run_cli`'s `timeout="1"`) because the
    fixture deliberately delays its permission request past `run_prompt`'s short post-update peek
    window to keep the close-vs-permission race deterministic (see the fixture's docstring).
    Scoped to `close`: every prompt turn against this fixture pays that same deliberate delay,
    so an unscoped run against the full suite costs 30+s just from that, for no attribution
    benefit over the `session_capabilities`-only subset."""
    result = _run_cli(
        "asks_permission_closable.py", timeout="5", k="close", cancel_prompt="__hang__"
    )
    assert result.returncode != 0  # `-k`-scoped: MANDATORY ids are NOT_TESTED, verdict non-zero

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CLOSE-002") == "PASS", f"expected PASS:\n{result.stdout}"
    assert statuses.get("ACP-CLOSE-001") == "PASS", f"expected PASS:\n{result.stdout}"


def test_asks_permission_closable_agent_also_exercises_cancelled_outcome():
    """Same fixture as above, driven through `test_cancel.py` instead: its permission request
    also arrives after `session/cancel` fires (same post-update-peek delay), so `run_prompt`
    answers it `{"outcome": {"outcome": "cancelled"}}` -- the one branch of `run_prompt`'s
    permission-answering logic that `asks_permission.py` alone never exercises."""
    result = _run_cli(
        "asks_permission_closable.py", timeout="5", k="cancel", cancel_prompt="__hang__"
    )
    # Exit code not asserted: a `-k`-scoped run necessarily leaves every MANDATORY requirement
    # NOT_TESTED, which by itself forces a non-conformant (nonzero) verdict regardless of these
    # two ids' own status (see `test_load_returns_null_fails_load_003_advisory_only`).
    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "PASS", f"expected PASS:\n{result.stdout}"
    assert statuses.get("ACP-CANCEL-002") == "PASS", f"expected PASS:\n{result.stdout}"


def test_wrong_id_echo_fails_id_dependent_requirements():
    """`wrong_id_echo.py` mangles every response id, which breaks id-correlated waits (used by
    almost every test's setup, not only the id-echo test itself) -- so nearly everything times
    out and fails. This is expected: a broken id-echo genuinely makes the agent unusable.

    Scoped to `jsonrpc`: an unscoped run against this fixture means *every* test in the suite
    times out waiting for an id-correlated response before failing, which costs far longer for
    a fact this one id already demonstrates -- narrowing to the id-echo tests themselves keeps
    the same assertion true in a fraction of the time."""
    result = _run_cli("wrong_id_echo.py", k="jsonrpc")
    assert result.returncode != 0
    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-001") == "FAIL", result.stdout


def test_version_mismatch_errors_fails_init_003_only():
    result = _run_cli("version_mismatch_errors.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-003") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-INIT-003"} - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_router_requires_info_passes_everything():
    """`router_requires_info.py` models a dual-version protocol *router*: it selects v2 for any
    requested version >= 2, including the ACP-INIT-003 probe's 65535, and
    validates the params as a v2 `InitializeRequest`, whose `info` is REQUIRED. Before the
    probe in `test_initialize.py` carried `info`, this fixture reproduced the spurious
    `-32602` a real dual-version router agent would give (see the fixture's own docstring) --
    ACP-INIT-003 FAILed and the run was NOT CONFORMANT. With the fix, it PASSes: the fixture is
    otherwise identical to `conforming.py` (advertises `agentCapabilities: {}`, no
    modes/configOptions/authMethods), so the same SKIP/PASS split applies."""
    result = _run_cli("router_requires_info.py")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS | _INFORMATIONAL_IDS, (
        f"requirement table missing/extra ids: {result.stdout}"
    )
    skip_ids = _CANCEL_IDS | _CAPABILITY_GATED_IDS
    for req_id in skip_ids:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised/unadvertised):\n{result.stdout}"
    for req_id, status in statuses.items():
        if req_id in skip_ids:
            continue
        assert status == "PASS", f"{req_id} is {status}, expected PASS for router_requires_info.py:\n{result.stdout}"
    assert "NOT TESTED" not in result.stdout
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_echoes_any_version_fails_init_003_only():
    """`echoes_any_version.py` echoes the client's requested `protocolVersion` verbatim for
    *every* request, including the unsupported 65535 one -- exactly the false-negative pattern
    (`testy`, `examples/echo_agent.py`) the strengthened ACP-INIT-003 exists to catch (see
    `test_initialize.py`). ACP-INIT-002 still PASSes (a v1 request is correctly echoed 1)."""
    result = _run_cli("echoes_any_version.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-003") == "FAIL", result.stdout
    assert statuses.get("ACP-INIT-002") == "PASS", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-INIT-003"} - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_result_and_error_fails_init_001_and_schema_001():
    """`result_and_error.py`'s `initialize` response carries both `result` and `error`, which
    also fails ACP-JSONRPC-002 (that requirement's evidence includes the `initialize` response
    itself, not just a probe reply) in addition to ACP-INIT-001 and ACP-SCHEMA-001."""
    result = _run_cli("result_and_error.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-001") == "FAIL", result.stdout
    assert statuses.get("ACP-SCHEMA-001") == "FAIL", result.stdout
    assert statuses.get("ACP-JSONRPC-002") == "FAIL", result.stdout
    _failing = {"ACP-INIT-001", "ACP-SCHEMA-001", "ACP-JSONRPC-002"}
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - _failing - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_answers_notifications_fails_jsonrpc_003_only():
    result = _run_cli("answers_notifications.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-003") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-JSONRPC-003"} - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_unknown_method_no_error_only_fails_the_advisory_requirement():
    """An ADVISORY-only failure must not affect the verdict: exit code 0, `VERDICT: CONFORMANT`,
    even though ACP-JSONRPC-004 itself FAILs."""
    result = _run_cli("unknown_method_no_error.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-004") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_duplicate_session_id_fails_session_002_only():
    result = _run_cli("duplicate_session_id.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-SESSION-002") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-SESSION-002"} - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_bad_stop_reason_fails_prompt_001_and_schema_001_only():
    """`bad_stop_reason.py` replies `stopReason: "done"` for any non-`__hang__` prompt, which
    directly breaks ACP-PROMPT-001 and ACP-SCHEMA-001. It does *not* hang for the cancel tests'
    prompt text either (only `__hang__` triggers that), so `session/cancel` always loses the
    race against its immediate (if invalid) reply -- ACP-CANCEL-001/002 SKIP as "cancellation
    not exercised" rather than cascading into a FAIL."""
    result = _run_cli("bad_stop_reason.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    expected_fails = {"ACP-PROMPT-001", "ACP-SCHEMA-001"}
    for req_id in expected_fails:
        assert statuses.get(req_id) == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - expected_fails - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_update_wrong_session_fails_prompt_002_only():
    """`update_wrong_session.py` always attributes `session/update` to `sessionId: "other"`.
    ACP-PROMPT-001/PROMPT-003 only check the response, not update attribution, so they still
    PASS; ACP-PROMPT-002 (which does check it) FAILs. It doesn't hang for the cancel tests'
    prompt text, so `session/cancel` always loses the race and ACP-CANCEL-001/002 SKIP as
    "cancellation not exercised" -- an unexercised cancel can't exercise ACP-CANCEL-002's
    ordering check either, so the wrong-sessionId update it would otherwise have caught there
    goes unreported by that particular test (ACP-PROMPT-002 still reports it)."""
    result = _run_cli("update_wrong_session.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    expected_fails = {"ACP-PROMPT-002"}
    for req_id in expected_fails:
        assert statuses.get(req_id) == "FAIL", result.stdout
    for req_id in _CANCEL_IDS | {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - expected_fails - _CANCEL_IDS - {"ACP-AUTH-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_hangs_until_cancel_agent_passes_cancel_requirements():
    """`hangs_until_cancel.py` withholds its response on *every* prompt until `session/cancel`
    arrives, which is deliberately incompatible with the non-cancelling prompt tests
    (ACP-PROMPT-*, ACP-SCHEMA-001, ACP-TRANSPORT-*) -- those would time out waiting for a
    response the fixture never sends unprompted. This self-test scopes the run to the cancel
    tests with `-k`, which is the only way to exercise this fixture meaningfully.

    The overall exit code is *not* asserted here: the exit code reflects the four-status
    verdict over the whole registry, and a `-k`-scoped run necessarily leaves every
    other MANDATORY requirement NOT_TESTED (counted as a verdict failure by design) -- that says
    nothing about whether *this* fixture's cancel handling is correct, which is what this test
    checks via the per-requirement table."""
    result = _run_cli("hangs_until_cancel.py", k="cancel")

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "PASS", result.stdout + result.stderr
    assert statuses.get("ACP-CANCEL-002") == "PASS", result.stdout + result.stderr


def test_cancel_returns_error_fails_cancel_001():
    """`cancel_returns_error.py` resolves a cancelled turn with a JSON-RPC error instead of a
    successful `cancelled` result. Scoped with `-k "cancel"` for the same reason as the
    `hangs_until_cancel.py` self-test above (the fixture hangs on every prompt)."""
    result = _run_cli("cancel_returns_error.py", k="cancel")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "FAIL", result.stdout


def test_cancel_wrong_stop_reason_fails_cancel_001_only():
    """`cancel_wrong_stop_reason.py` resolves a cancelled turn successfully but with
    `stopReason: "end_turn"` instead of `"cancelled"` -- ACP-CANCEL-001 FAILs, but ACP-CANCEL-002
    (no update after the response) is unaffected and still PASSes. Scoped with `-k "cancel"` for
    the same reason as the `hangs_until_cancel.py` self-test above. Uses a longer `--timeout`
    since the fixture deliberately sleeps 1.2s after `session/cancel` before answering, to stay
    outside the TCK's 1.0s "was this actually exercised" race window (see the fixture's
    docstring)."""
    result = _run_cli("cancel_wrong_stop_reason.py", k="cancel", timeout="5")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "FAIL", result.stdout
    assert statuses.get("ACP-CANCEL-002") == "PASS", result.stdout


def test_update_after_response_fails_cancel_002_only():
    """`update_after_response.py` correctly resolves a cancelled turn with `stopReason:
    "cancelled"` (ACP-CANCEL-001 PASSes) but then sends one more `session/update` afterwards,
    which ACP-CANCEL-002 catches. Scoped with `-k "cancel"` for the same reason as the
    `hangs_until_cancel.py` self-test above."""
    result = _run_cli("update_after_response.py", k="cancel")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "PASS", result.stdout
    assert statuses.get("ACP-CANCEL-002") == "FAIL", result.stdout


def test_per_test_watchdog_fails_a_hung_test_fast():
    """A tiny `--test-timeout` must fail a test whose own per-operation deadlines are much
    larger, well before any individual read/write deadline would ever fire on its own --
    proving the watchdog itself is what caught it, not the ordinary per-response timeout.
    Scoped to one fast, id-echo-only test node so this stays quick even though
    `--timeout`/`--startup-timeout` are deliberately large. `--close-grace` is also lowered:
    `never_responds.py` never exits on its own, so teardown would otherwise pay the full
    default 2s stdin-close wait every run just to prove the watchdog fired; this self-test only
    cares that it fired, not about giving a real agent a generous shutdown window."""
    result = _run_cli(
        "never_responds.py",
        k="test_id_is_echoed_for_integer_and_string_ids",
        timeout="10",
        startup_timeout="1",
        test_timeout="0.3",
        close_grace="0.2",
    )
    assert result.returncode != 0
    assert "per-test watchdog" in result.stdout, result.stdout + result.stderr
    assert "--tck-test-timeout" in result.stdout, result.stdout + result.stderr


# --- session-capability tests ---


def test_conforming_full_agent_passes_everything_with_cancel_prompt_hang():
    """`conforming_full.py` advertises `loadSession: true`, every `sessionCapabilities` marker,
    modes, config options, every `promptCapabilities`, and the auth surface -- so every
    CAPABILITY-tier id (plus the two capability-gated ADVISORY ids) should PASS instead of
    SKIPPING. `--cancel-prompt __hang__` is required: it's the only prompt text `_base.py`'s
    `_handle_prompt` withholds a response for, so it's what lets ACP-CANCEL-001/002 and
    ACP-CLOSE-002 actually exercise their cancellation/close-race logic instead of SKIPPING as
    "not exercised". `--auth-method tck` is required for ACP-AUTH-003 to PASS instead of SKIP,
    since `conforming_full.py` advertises an `authMethods` entry with that id.

    `ACP-AUTH-005` (AUTH-A1) is the one ADVISORY id that legitimately SKIPs here rather than
    PASSing: it only concerns an agent that advertises *no* `authMethods`, and
    `conforming_full.py` deliberately advertises one -- that is inapplicability, not a
    conformance gap, exactly like `ACP-AUTH-003` SKIPping without `--auth-method`."""
    result = _run_cli("conforming_full.py", cancel_prompt="__hang__", auth_method="tck")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS | _INFORMATIONAL_IDS, (
        f"requirement table missing/extra ids: {result.stdout}"
    )
    for req_id, status in statuses.items():
        if req_id == "ACP-AUTH-005":
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED (not applicable):\n{result.stdout}"
            continue
        assert status == "PASS", f"{req_id} is {status}, expected PASS for conforming_full.py:\n{result.stdout}"
    assert "NOT TESTED" not in result.stdout
    assert all(
        status != "SKIPPED" for req_id, status in statuses.items() if req_id != "ACP-AUTH-005"
    ), result.stdout


def test_load_replays_after_response_fails_load_002_only():
    """`load_replays_after_response.py` advertises `loadSession` but answers `session/load`
    before replaying stored history instead of after -- ACP-LOAD-001 still PASSes (the response
    itself is valid), only the ordering requirement ACP-LOAD-002 FAILs."""
    result = _run_cli("load_replays_after_response.py", k="load")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-LOAD-001") == "PASS", result.stdout
    assert statuses.get("ACP-LOAD-002") == "FAIL", result.stdout


def test_resume_replays_history_fails_resume_002_only():
    """`resume_replays_history.py` advertises `sessionCapabilities.resume` but replays stored
    history before answering `session/resume`, which resume MUST NOT do -- ACP-RESUME-001 still
    PASSes, only ACP-RESUME-002 FAILs."""
    result = _run_cli("resume_replays_history.py", k="resume")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-RESUME-001") == "PASS", result.stdout
    assert statuses.get("ACP-RESUME-002") == "FAIL", result.stdout


def test_load_returns_null_fails_load_003_advisory_only():
    """`load_returns_null.py` replays history correctly and advertises `loadSession`, but
    answers `session/load` with a literal `null` instead of `{}`. Mandatory schema validation
    tolerates `null` for this all-optional response, so ACP-LOAD-001/002 PASS; only the
    stricter ADVISORY ACP-LOAD-003 FAILs. The overall exit code is *not* asserted here (see
    `test_hangs_until_cancel_agent_passes_cancel_requirements` for why): a `-k`-scoped run
    necessarily leaves every MANDATORY requirement NOT_TESTED, which by itself forces a
    non-conformant verdict regardless of ACP-LOAD-003's own (ADVISORY, verdict-inert) status."""
    result = _run_cli("load_returns_null.py", k="load")

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-LOAD-001") == "PASS", result.stdout
    assert statuses.get("ACP-LOAD-002") == "PASS", result.stdout
    assert statuses.get("ACP-LOAD-003") == "FAIL", result.stdout


def test_mode_update_uses_modeId_fails_modes_002_only():
    """`mode_update_uses_modeId.py` advertises `modes` and emits a `current_mode_update` with
    the docs-bug field name `modeId` instead of the schema-true `currentModeId` --
    ACP-MODES-001 (which never inspects a mode-update notification) still PASSes."""
    result = _run_cli("mode_update_uses_modeId.py", k="mode")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-MODES-001") == "PASS", result.stdout
    assert statuses.get("ACP-MODES-002") == "FAIL", result.stdout


def test_config_partial_list_fails_config_002_only():
    """`config_partial_list.py` advertises `configOptions` and answers `session/set_config_option`
    with only the changed option, not the complete list -- ACP-CONFIG-001 (which only checks
    `session/new`'s own configOptions) still PASSes."""
    result = _run_cli("config_partial_list.py", k="config")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CONFIG-001") == "PASS", result.stdout
    assert statuses.get("ACP-CONFIG-002") == "FAIL", result.stdout


def test_boolean_option_unadvertised_fails_config_003():
    """`boolean_option_unadvertised.py` advertises a `type: "boolean"` config option even to a
    client that never advertised `clientCapabilities.session.configOptions.boolean` -- a
    MANDATORY (Req 33) FAIL, which must flip the overall verdict."""
    result = _run_cli("boolean_option_unadvertised.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CONFIG-003") == "FAIL", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_terminal_auth_unadvertised_fails_auth_002():
    """`terminal_auth_unadvertised.py` advertises `authMethods[*].type == "terminal"` even to a
    client that never advertised `clientCapabilities.auth.terminal` -- a MANDATORY (Req 23) FAIL."""
    result = _run_cli("terminal_auth_unadvertised.py", k="auth")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-AUTH-002") == "FAIL", result.stdout


def test_gated_by_auth_without_auth_method_skips_with_hint_and_is_not_conformant():
    """`gated_by_auth.py` requires `authenticate` before `session/new` succeeds. Without
    `--auth-method`, every session-dependent test SKIPs (not FAILs) with a message pointing at
    the flag, and the run is scored NOT CONFORMANT via `Verdict.blocked_by_auth` even though no
    MANDATORY test actually FAILed."""
    result = _run_cli("gated_by_auth.py", k="session")
    assert result.returncode != 0
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout
    assert "blocked by authentication" in result.stdout, result.stdout
    assert "--auth-method" in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-SESSION-001") == "SKIPPED", result.stdout
    assert statuses.get("ACP-SESSION-002") == "SKIPPED", result.stdout


def test_gated_by_auth_with_auth_method_succeeds():
    """The same fixture, scoped the same way, but with `--auth-method tck` -- the auto-
    authenticate step in `connected_agent` makes it behave like a normal conforming agent for
    every session-dependent test in scope. The overall exit code is *not* asserted here (see
    `test_hangs_until_cancel_agent_passes_cancel_requirements` for why): a `-k`-scoped run
    necessarily leaves every out-of-scope MANDATORY requirement NOT_TESTED, which by itself
    forces a non-conformant verdict regardless of whether authentication itself worked -- what
    this test checks is that the in-scope session tests PASS instead of SKIPPING."""
    result = _run_cli("gated_by_auth.py", k="session", auth_method="tck")

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-002") == "PASS", result.stdout
    assert "blocked by authentication" not in result.stdout, result.stdout


def test_gated_by_auth_full_run_without_auth_method_is_not_conformant_and_blocked_by_auth(
    tmp_path,
):
    """A full (unscoped) run against `gated_by_auth.py` without `--auth-method`: every
    session-dependent test SKIPs with the auth hint, no MANDATORY requirement actually FAILs
    (everything reachable without a session -- `initialize`, JSON-RPC envelope/id echo, the
    schema-less parts of ACP-AUTH-001/002 -- still PASSes), and the run is scored NOT CONFORMANT
    solely via `Verdict.blocked_by_auth`. The JSON report's `verdict.blocked_by_auth` must be
    `true` and `verdict.conformant` `false`."""
    report_path = tmp_path / "report.json"
    result = _run_cli(
        "gated_by_auth.py",
        cancel_prompt="__hang__",
        report_json=str(report_path),
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout
    assert "blocked by authentication" in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    mandatory_fails = {
        req_id for req_id in _MANDATORY_IDS if statuses.get(req_id) == "FAIL"
    }
    assert not mandatory_fails, f"unexpected MANDATORY FAILs: {mandatory_fails}\n{result.stdout}"

    report = json.loads(report_path.read_text())
    assert report["verdict"]["blocked_by_auth"] is True, report["verdict"]
    assert report["verdict"]["conformant"] is False, report["verdict"]


def test_gated_by_auth_full_run_with_auth_method_is_fully_conformant():
    """The same full (unscoped) run, but with `--auth-method tck`: the auto-authenticate step
    in `connected_agent` makes `gated_by_auth.py` behave exactly like `conforming_full.py` minus
    the extra capabilities it doesn't advertise (`loadSession`, `sessionCapabilities`,
    `promptCapabilities`, `auth.logout`, `modes`/`configOptions`) -- every one of those SKIPs as
    "not advertised", every other MANDATORY/ADVISORY requirement PASSes, and the overall exit
    code is 0/CONFORMANT. `--cancel-prompt __hang__` is needed for the same reason
    `conforming_full.py`'s own self-test needs it: `_base.py`'s hang-on-`__hang__` behavior is
    unconditional, so ACP-CANCEL-001/002 need that exact prompt text to exercise the race
    instead of SKIPping as "cancellation not exercised"."""
    result = _run_cli("gated_by_auth.py", cancel_prompt="__hang__", auth_method="tck")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout
    assert "NOT TESTED" not in result.stdout, result.stdout

    statuses = _table_statuses(result.stdout)
    # ACP-AUTH-005 (AUTH-A1) legitimately SKIPs too: it only concerns an agent advertising no
    # authMethods, and `gated_by_auth.py` advertises one -- inapplicability, not a gap.
    capability_gated = _CAPABILITY_GATED_IDS - {"ACP-AUTH-003"} | {"ACP-AUTH-005"}
    for req_id in capability_gated:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (not advertised):\n{result.stdout}"
    for req_id, status in statuses.items():
        if req_id in capability_gated:
            continue
        assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"


def test_advertises_load_but_errors_fails_load_001_and_verdict():
    """`advertises_load_but_errors.py` advertises `loadSession: true` but always errors on
    `session/load` -- a CAPABILITY-tier FAIL, which must flip the overall verdict to NOT
    CONFORMANT (unlike an ADVISORY-only failure)."""
    result = _run_cli("advertises_load_but_errors.py", k="load")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-LOAD-001") == "FAIL", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- --report-json ---


def test_report_json_for_conforming_agent_is_conformant_with_cancel_skipped(tmp_path):
    report_path = tmp_path / "report.json"
    result = _run_cli("conforming.py", report_json=str(report_path))
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(report_path.read_text())
    assert report["verdict"]["conformant"] is True
    by_id = {r["id"]: r for r in report["requirements"]}
    skip_ids = _CANCEL_IDS | _CAPABILITY_GATED_IDS
    for req_id in skip_ids:
        assert by_id[req_id]["status"] == "SKIPPED", report
    for req_id in _ALL_IDS - skip_ids:
        assert by_id[req_id]["status"] == "PASS", (req_id, report)
    assert report["protocol_version"] == 1
    assert report["agent_info"] is not None
    assert set(report) == {
        "tck_version",
        "protocol_version",
        "schema_revision",
        "agent_command",
        "agent_info",
        "agent_capabilities",
        "started_at",
        "finished_at",
        "requirements",
        "verdict",
    }


def test_report_json_for_advisory_only_failure_is_still_conformant(tmp_path):
    report_path = tmp_path / "report.json"
    result = _run_cli("unknown_method_no_error.py", report_json=str(report_path))
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(report_path.read_text())
    assert report["verdict"]["conformant"] is True
    by_id = {r["id"]: r for r in report["requirements"]}
    assert by_id["ACP-JSONRPC-004"]["status"] == "FAIL"


def test_report_json_for_banner_on_stdout_includes_a_nonempty_transcript_on_failure(tmp_path):
    report_path = tmp_path / "report.json"
    result = _run_cli("banner_on_stdout.py", report_json=str(report_path))
    assert result.returncode != 0

    report = json.loads(report_path.read_text())
    assert report["verdict"]["conformant"] is False
    by_id = {r["id"]: r for r in report["requirements"]}
    failing = by_id["ACP-TRANSPORT-001"]
    assert failing["status"] == "FAIL"
    test_outcome = failing["tests"][0]
    assert test_outcome["status"] == "FAIL"
    assert test_outcome["transcript"], "expected a non-empty transcript on a FAIL outcome"
    assert isinstance(test_outcome["transcript"], list)
    assert {"dir", "t", "raw"} <= set(test_outcome["transcript"][0])


def test_calls_fs_unadvertised_fails_clientcap_001():
    """`calls_fs_unadvertised.py` calls `fs/read_text_file` on every prompt turn even though the
    TCK's mock client never advertised `fs` -- a MANDATORY (Req 29) FAIL that must flip the
    exit code. Scoped to `clientcap` since this fixture's `_handle_prompt` override only ever
    resolves a turn once the client has answered its one client-request, which is exactly what
    the clientcap tests' `run_prompt` calls do; other prompt tests would work too, but scoping
    keeps this self-test fast and focused.

    Also asserts ACP-CLIENTCAP-002/003 still PASS: the three ids are three separate tests
    specifically so that a single-capability violation like this one isn't mis-attributed to
    the other two."""
    result = _run_cli("calls_fs_unadvertised.py", k="clientcap")
    assert result.returncode != 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CLIENTCAP-001") == "FAIL", result.stdout
    assert statuses.get("ACP-CLIENTCAP-002") == "PASS", result.stdout
    assert statuses.get("ACP-CLIENTCAP-003") == "PASS", result.stdout


def test_calls_terminal_unadvertised_fails_clientcap_002():
    """Same as above, for `terminal/create` (Req 30); asserts -001/-003 still PASS."""
    result = _run_cli("calls_terminal_unadvertised.py", k="clientcap")
    assert result.returncode != 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CLIENTCAP-001") == "PASS", result.stdout
    assert statuses.get("ACP-CLIENTCAP-002") == "FAIL", result.stdout
    assert statuses.get("ACP-CLIENTCAP-003") == "PASS", result.stdout


def test_calls_elicitation_unadvertised_fails_clientcap_003():
    """Same as above, for `elicitation/create` (Req 32); asserts -001/-002 still PASS."""
    result = _run_cli("calls_elicitation_unadvertised.py", k="clientcap")
    assert result.returncode != 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CLIENTCAP-001") == "PASS", result.stdout
    assert statuses.get("ACP-CLIENTCAP-002") == "PASS", result.stdout
    assert statuses.get("ACP-CLIENTCAP-003") == "FAIL", result.stdout


def test_noisy_stderr_and_parse_error_reply_agent_informational_notes():
    """`noisy_stderr_and_parse_error_reply.py` deterministically exercises two INFORMATIONAL
    probes' non-default branches: it logs every line to stderr (ACP-STDERR-001's byte count
    must be > 0) and replies `-32700`/`id: null` to malformed JSON instead of staying silent
    (ACP-INFO-PARSE-001's recorded behaviour must say so) -- proving the terminal table actually
    surfaces a recorded property as a note, not just that the always-PASS scaffolding runs."""
    result = _run_cli("noisy_stderr_and_parse_error_reply.py")
    assert result.returncode == 0, result.stdout + result.stderr

    assert "ACP-STDERR-001" in result.stdout
    assert "ACP-INFO-PARSE-001" in result.stdout
    assert "replied -32700 with id:null" in result.stdout, result.stdout
    assert "stderr byte(s)" in result.stdout, result.stdout
    for line in result.stdout.splitlines():
        if "ACP-STDERR-001" in line:
            match = re.search(r"(\d+) stderr byte\(s\)", line)
            assert match and int(match.group(1)) > 0, result.stdout


def test_report_json_for_exits_immediately_has_no_crash_and_all_mandatory_fail_or_not_tested(
    tmp_path,
):
    report_path = tmp_path / "report.json"
    result = _run_cli("exits_immediately.py", report_json=str(report_path))
    assert result.returncode != 0
    assert "INTERNALERROR" not in result.stdout + result.stderr

    assert report_path.exists(), "report must still be written even when every test fails"
    report = json.loads(report_path.read_text())
    assert report["verdict"]["conformant"] is False
    for requirement in report["requirements"]:
        if requirement["id"] == "ACP-AUTH-003":
            # Conditional on --tck-auth-method regardless of the agent's own behavior -- see
            # test_exits_immediately_fails_gracefully.
            assert requirement["status"] == "SKIPPED", requirement
        elif requirement["tier"] == "MANDATORY":
            assert requirement["status"] in ("FAIL", "NOT_TESTED"), requirement
