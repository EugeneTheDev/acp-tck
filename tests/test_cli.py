"""End-to-end CLI tests: run `python -m tck -- <fixture agent>` as a real subprocess and check
the exit code plus the terminal requirement-summary table.

A subprocess (not in-process `pytest.main`) is used deliberately: this file itself runs under
pytest, and pytest does not support a clean re-entrant `pytest.main()` call from within a
running session.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "agents"
CLI_SUBPROCESS_TIMEOUT = 30

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
}
_ADVISORY_IDS = {"ACP-JSONRPC-004", "ACP-JSONRPC-005", "ACP-INIT-004", "ACP-PROMPT-003"}
_ALL_IDS = _MANDATORY_IDS | _ADVISORY_IDS

_CANCEL_IDS = {"ACP-CANCEL-001", "ACP-CANCEL-002"}
"""None of the fixtures below `hangs_until_cancel.py`, `cancel_returns_error.py`,
`cancel_wrong_stop_reason.py`, and `update_after_response.py` deliberately withhold their
response until `session/cancel` arrives for arbitrary prompt text -- they resolve the turn
immediately, same as `conforming.py`. So for all of them, `session/cancel` always loses the
race and the cancel tests SKIP with "cancellation not exercised" rather than PASS or FAIL (see
`.agents/plan.md` "Cancel tests and the race")."""


def _run_cli(
    fixture: str, *, k: str | None = None, timeout: str = "1"
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "tck",
        "--timeout",
        timeout,
        "--startup-timeout",
        "1",
    ]
    if k is not None:
        cmd += ["-k", k]
    cmd += [
        "--",
        sys.executable,
        str(FIXTURES_DIR / fixture),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_SUBPROCESS_TIMEOUT)


def _table_statuses(output: str) -> dict[str, str]:
    """Parse `<id> <STATUS>` pairs out of the terminal summary table."""
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("ACP-"):
            statuses[parts[0]] = parts[1]
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
    ("cancellation not exercised") rather than PASS -- everything else still PASSes."""
    result = _run_cli("conforming.py")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id, status in statuses.items():
        if req_id in _CANCEL_IDS:
            continue
        assert status == "PASS", f"{req_id} is {status}, expected PASS for the conforming fixture:\n{result.stdout}"
    assert "NOT TESTED" not in result.stdout


def test_exits_immediately_fails_gracefully():
    result = _run_cli("exits_immediately.py")
    assert result.returncode != 0
    assert "INTERNALERROR" not in result.stdout
    assert "INTERNALERROR" not in result.stderr
    statuses = _table_statuses(result.stdout)
    for req_id in _MANDATORY_IDS:
        assert statuses.get(req_id) == "FAIL", f"{req_id} should FAIL when the agent never responds"


def test_banner_on_stdout_fails_transport_requirements_only():
    result = _run_cli("banner_on_stdout.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-TRANSPORT-001") == "FAIL", result.stdout
    assert statuses.get("ACP-TRANSPORT-002") == "FAIL", result.stdout
    assert statuses.get("ACP-SCHEMA-001") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-TRANSPORT-001", "ACP-TRANSPORT-002", "ACP-SCHEMA-001"} - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_wrong_id_echo_fails_id_dependent_requirements():
    """`wrong_id_echo.py` mangles every response id, which breaks id-correlated waits (used by
    almost every test's setup, not only the id-echo test itself) -- so nearly everything times
    out and fails. This is expected: a broken id-echo genuinely makes the agent unusable."""
    result = _run_cli("wrong_id_echo.py")
    assert result.returncode != 0
    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-001") == "FAIL", result.stdout


def test_version_mismatch_errors_fails_init_003_only():
    result = _run_cli("version_mismatch_errors.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-003") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-INIT-003"} - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_result_and_error_fails_init_001_and_schema_001():
    result = _run_cli("result_and_error.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-001") == "FAIL", result.stdout
    assert statuses.get("ACP-SCHEMA-001") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-INIT-001", "ACP-SCHEMA-001"} - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_answers_notifications_fails_jsonrpc_003_only():
    result = _run_cli("answers_notifications.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-003") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-JSONRPC-003"} - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_unknown_method_no_error_only_fails_the_advisory_requirement():
    result = _run_cli("unknown_method_no_error.py")

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-004") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_duplicate_session_id_fails_session_002_only():
    result = _run_cli("duplicate_session_id.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-SESSION-002") == "FAIL", result.stdout
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - {"ACP-SESSION-002"} - _CANCEL_IDS:
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
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - expected_fails - _CANCEL_IDS:
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
    for req_id in _CANCEL_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id} should SKIP (unexercised):\n{result.stdout}"
    for req_id in _MANDATORY_IDS - expected_fails - _CANCEL_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_hangs_until_cancel_agent_passes_cancel_requirements():
    """`hangs_until_cancel.py` withholds its response on *every* prompt until `session/cancel`
    arrives, which is deliberately incompatible with the non-cancelling prompt tests
    (ACP-PROMPT-*, ACP-SCHEMA-001, ACP-TRANSPORT-*) -- those would time out waiting for a
    response the fixture never sends unprompted. This self-test scopes the run to the cancel
    tests with `-k`, which is the only way to exercise this fixture meaningfully; see
    `.agents/plan.md` slice 4 notes for why an unscoped run is not a meaningful check here."""
    result = _run_cli("hangs_until_cancel.py", k="cancel")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-CANCEL-001") == "PASS", result.stdout
    assert statuses.get("ACP-CANCEL-002") == "PASS", result.stdout


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
