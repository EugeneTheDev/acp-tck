"""End-to-end CLI tests for `--protocol-version 2`: run `python -m tck --protocol-version 2 --
<fixture agent>` as a real subprocess and check the exit code plus the terminal
requirement-summary table. Mirrors `tests/v1/test_cli.py`, scaled down to this skeleton slice's
two-requirement registry, plus a couple of routing checks (`--help`, and that the default/
`--protocol-version 1` path still runs the v1 suite unchanged).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR_V2 = Path(__file__).parent.parent / "fixtures" / "agents" / "v2"
FIXTURES_DIR_V1 = Path(__file__).parent.parent / "fixtures" / "agents" / "v1"
CLI_SUBPROCESS_TIMEOUT = 60

_MANDATORY_IDS = {"ACP-INIT-001", "ACP-INIT-201"}

_TABLE_ROW_RE = re.compile(r"^\s*(ACP-\S+)\s+(PASS|FAIL|SKIPPED|NOT TESTED)\b")


def _table_statuses(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        match = _TABLE_ROW_RE.match(line)
        if match:
            statuses[match.group(1)] = match.group(2).replace("NOT TESTED", "NOT_TESTED")
    return statuses


def _run_cli(
    fixture_dir: Path,
    fixture: str,
    *,
    protocol_version: int | None,
    timeout: str = "1",
    startup_timeout: str = "1",
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "tck", "--timeout", timeout, "--startup-timeout", startup_timeout]
    if protocol_version is not None:
        cmd += ["--protocol-version", str(protocol_version)]
    cmd += ["--", sys.executable, str(fixture_dir / fixture)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_SUBPROCESS_TIMEOUT)


def test_help_mentions_protocol_version_option():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--help"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "--protocol-version" in result.stdout


def test_v2_conforming_agent_passes_everything():
    result = _run_cli(FIXTURES_DIR_V2, "conforming.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _MANDATORY_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id, status in statuses.items():
        assert status == "PASS", f"{req_id} is {status}, expected PASS for the v2 conforming fixture:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_v2_missing_agent_command_is_an_error():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--protocol-version", "2"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0


def test_default_protocol_version_still_runs_the_v1_suite_unchanged():
    """No `--protocol-version` given at all -- must behave exactly as before this slice: the v1
    suite, against the v1 conforming fixture."""
    result = _run_cli(FIXTURES_DIR_V1, "conforming.py", protocol_version=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout
    assert "ACP-INIT-002" in result.stdout, "expected the v1 registry's ids, not v2's"


def test_explicit_protocol_version_1_matches_the_default():
    result = _run_cli(FIXTURES_DIR_V1, "conforming.py", protocol_version=1)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout
