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
}
_ADVISORY_IDS = {"ACP-JSONRPC-004", "ACP-JSONRPC-005", "ACP-INIT-004"}
_ALL_IDS = _MANDATORY_IDS | _ADVISORY_IDS


def _run_cli(fixture: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "tck",
        "--timeout",
        "1",
        "--startup-timeout",
        "1",
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
    result = _run_cli("conforming.py")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id, status in statuses.items():
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
    for req_id in _MANDATORY_IDS - {"ACP-TRANSPORT-001", "ACP-TRANSPORT-002", "ACP-SCHEMA-001"}:
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
    for req_id in _MANDATORY_IDS - {"ACP-INIT-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_result_and_error_fails_init_001_and_schema_001():
    result = _run_cli("result_and_error.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-INIT-001") == "FAIL", result.stdout
    assert statuses.get("ACP-SCHEMA-001") == "FAIL", result.stdout
    for req_id in _MANDATORY_IDS - {"ACP-INIT-001", "ACP-SCHEMA-001"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_answers_notifications_fails_jsonrpc_003_only():
    result = _run_cli("answers_notifications.py")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-003") == "FAIL", result.stdout
    for req_id in _MANDATORY_IDS - {"ACP-JSONRPC-003"}:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"


def test_unknown_method_no_error_only_fails_the_advisory_requirement():
    result = _run_cli("unknown_method_no_error.py")

    statuses = _table_statuses(result.stdout)
    assert statuses.get("ACP-JSONRPC-004") == "FAIL", result.stdout
    for req_id in _MANDATORY_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id} should still PASS:\n{result.stdout}"
