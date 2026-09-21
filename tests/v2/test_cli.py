"""End-to-end CLI tests for `--protocol-version 2`: run `python -m tck --protocol-version 2 --
<fixture agent>` as a real subprocess and check the exit code plus the terminal
requirement-summary table. Mirrors `tests/v1/test_cli.py`.

Slice V2-1b expanded this from the skeleton's two routing checks to the full `initialize`/
`session/new` baseline: the conforming fixture PASSing everything, one test per defect fixture
asserting its exact FAIL set, and the version-mismatch scenario (a v1 fixture run under
`--protocol-version 2`). Slice V2-2a adds the mock-client prompt driver's own defect fixtures
(`bad_stop_reason.py`, `vendor_stop_reason.py`, `no_running_update.py`,
`no_idle_after_running.py`, `idle_before_running.py`, `echo_wrong_message_id.py`,
`missing_message_id.py`, `update_wrong_session.py`).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR_V2 = Path(__file__).parent.parent / "fixtures" / "agents" / "v2"
FIXTURES_DIR_V1 = Path(__file__).parent.parent / "fixtures" / "agents" / "v1"
CLI_SUBPROCESS_TIMEOUT = 60

_MANDATORY_IDS = {
    "ACP-INIT-001",
    "ACP-INIT-003",
    "ACP-INIT-201",
    "ACP-INIT-202",
    "ACP-INIT-203",
    "ACP-INIT-204",
    "ACP-SCHEMA-001",
}
_CAPABILITY_IDS = {
    "ACP-SESSION-001",
    "ACP-SESSION-002",
    "ACP-PROMPT-205",
    "ACP-PROMPT-201",
    "ACP-PROMPT-203",
    "ACP-STATE-201",
    "ACP-STATE-202",
    "ACP-STATE-203",
}
_ALL_IDS = _MANDATORY_IDS | _CAPABILITY_IDS

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
    report_json: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "tck", "--timeout", timeout, "--startup-timeout", startup_timeout]
    if protocol_version is not None:
        cmd += ["--protocol-version", str(protocol_version)]
    if report_json is not None:
        cmd += ["--report-json", report_json]
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
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id, status in statuses.items():
        assert status == "PASS", f"{req_id} is {status}, expected PASS for the v2 conforming fixture:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_v2_report_json_reads_the_v2_shaped_initialize_result(tmp_path):
    """review-v2-slices-0-1a.md finding 7: `--report-json` for a real v2 run must carry
    `protocol_version == 2` and read `agent_info`/`agent_capabilities` from the v2-renamed
    `info`/`capabilities` keys (`tck.common.version.VersionSpec.agent_info_field`/
    `agent_capabilities_field` -- see `tests/common/test_version.py` for the mechanism itself in
    isolation)."""
    report_path = tmp_path / "report.json"
    result = _run_cli(
        FIXTURES_DIR_V2, "conforming.py", protocol_version=2, report_json=str(report_path)
    )
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(report_path.read_text())
    assert report["protocol_version"] == 2
    assert report["agent_info"] == {"name": "tck-fixture-conforming-v2", "version": "0.0.0"}
    assert report["agent_capabilities"] == {"session": {}}
    assert report["verdict"]["conformant"] is True


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


# --- defect fixtures: each must FAIL exactly its intended requirement id(s) ---


def test_echoes_any_version_fails_init_003_and_201_only():
    """`echoes_any_version.py` echoes the client's requested `protocolVersion` verbatim,
    including the unsupported `65535` probe -- fails the strengthened `ACP-INIT-003` (must not
    echo `65535`) and `ACP-INIT-201` (the two-branch negotiation rule). It advertises
    `capabilities: {"session": {}}` like `conforming.py` (review-v2-slices-0-1a.md finding/item
    3), so `ACP-SESSION-001/002` PASS -- `session/new` itself is unmodified and correct."""
    result = _run_cli(FIXTURES_DIR_V2, "echoes_any_version.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-INIT-003", "ACP-INIT-201"}, result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_only_errors_on_v1_fails_init_202_only():
    """`v2_only_errors_on_v1.py` errors instead of answering `2` when asked for `1` -- fails only
    `ACP-INIT-202` (the `N < min(S)` downgrade-must-still-succeed rule). It advertises
    `capabilities: {"session": {}}` like `conforming.py`, so `ACP-SESSION-001/002` PASS."""
    result = _run_cli(FIXTURES_DIR_V2, "v2_only_errors_on_v1.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-INIT-202"}, result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_missing_info_fails_init_203_and_schema_001_only():
    """`missing_info.py` omits the required `info` field entirely -- fails `ACP-INIT-203` (`info`
    is REQUIRED in v2) and `ACP-SCHEMA-001` (the same missing-required-property schema
    violation). `ACP-INIT-001` still PASSes: it only asserts `initialize` returned a non-error
    result (this fixture still does), never the result's shape. It advertises
    `capabilities: {"session": {}}` like `conforming.py`, so `ACP-SESSION-001/002` PASS."""
    result = _run_cli(FIXTURES_DIR_V2, "missing_info.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-INIT-203", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-INIT-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_boolean_session_capability_fails_init_204_and_schema_001_only():
    """`boolean_session_capability.py` advertises `capabilities.session: true` (a boolean, not an
    object marker) -- fails `ACP-SCHEMA-001` (schema violation) and `ACP-INIT-204` (capability
    markers must be objects). `ACP-INIT-001` still PASSes (non-error result only), and
    `ACP-SESSION-001`/`002` still PASS: the underlying `session/new` handler works fine and
    `capability_is_supported` treats `true` as advertised."""
    result = _run_cli(FIXTURES_DIR_V2, "boolean_session_capability.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-INIT-204", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-INIT-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert statuses.get("ACP-SESSION-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_duplicate_session_id_fails_session_002_only():
    """`duplicate_session_id.py` always returns the same `sessionId` -- fails only the CAPABILITY
    `ACP-SESSION-002`, which alone must still flip the verdict to NOT CONFORMANT."""
    result = _run_cli(FIXTURES_DIR_V2, "duplicate_session_id.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-SESSION-002"}, result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- V2-2a: the prompt-turn defect fixtures ---


def test_bad_stop_reason_fails_state_203_only():
    result = _run_cli(FIXTURES_DIR_V2, "bad_stop_reason.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-STATE-203"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_vendor_stop_reason_passes_everything():
    """Positive control for the `_`-prefix open-enum extensibility rule."""
    result = _run_cli(FIXTURES_DIR_V2, "vendor_stop_reason.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    for req_id, status in statuses.items():
        assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_no_running_update_fails_state_201_only():
    result = _run_cli(FIXTURES_DIR_V2, "no_running_update.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-STATE-201"}, result.stdout
    assert statuses.get("ACP-STATE-202") == "SKIPPED", result.stdout
    assert statuses.get("ACP-STATE-203") == "SKIPPED", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_no_idle_after_running_fails_every_run_prompt_dependent_id():
    """`no_idle_after_running.py` never sends a terminating idle: every test that drives a turn
    through `run_prompt` independently hits `AgentTimeout` and FAILs. Uses a larger
    `--timeout` than the other CLI self-tests (still small) so the cascade is deterministic and
    the observed wall-clock time stays well within budget."""
    result = _run_cli(
        FIXTURES_DIR_V2, "no_idle_after_running.py", protocol_version=2, timeout="2"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-PROMPT-205",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-SCHEMA-001",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_idle_before_running_passes_everything():
    """`idle_before_running.py` sends a legal, unsolicited "session-ready" idle before any
    `session/prompt` is ever issued -- must not be mistaken for a turn terminator."""
    result = _run_cli(FIXTURES_DIR_V2, "idle_before_running.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    for req_id, status in statuses.items():
        assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_echo_wrong_message_id_fails_prompt_203_only():
    result = _run_cli(FIXTURES_DIR_V2, "echo_wrong_message_id.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPT-203"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_missing_message_id_fails_prompt_201_and_schema_001_and_skips_prompt_203():
    result = _run_cli(FIXTURES_DIR_V2, "missing_message_id.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPT-201", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-PROMPT-203") == "SKIPPED", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_update_wrong_session_fails_every_run_prompt_dependent_id():
    """`update_wrong_session.py` misattributes every `session/update` to `sessionId: "other"`:
    the same cascade shape as `no_idle_after_running.py`, since `run_prompt` never recognizes a
    matching terminating idle either."""
    result = _run_cli(
        FIXTURES_DIR_V2, "update_wrong_session.py", protocol_version=2, timeout="2"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-PROMPT-205",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-SCHEMA-001",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- version mismatch: a v1 agent run under --protocol-version 2 ---

# The negotiation rows (`ACP-INIT-001`/`003`/`201`/`202`) assert only on the negotiation
# *outcome*, never on the result's shape, so an agent that honestly negotiates down to 1 still
# PASSes them. The v2-only *shape* rows (`info` required, object-only capability markers, v2
# schema validity, plus the CAPABILITY-tier session rows) cannot be meaningfully judged against
# a result the agent never claimed was v2-shaped, so they SKIP with the `VERSION-MISMATCH:`
# marker instead of FAILing (see `tck.v2.requirements`'s "Version-mismatch-aware v2-shape rows"
# section).
_NEGOTIATION_IDS = {"ACP-INIT-001", "ACP-INIT-003", "ACP-INIT-201", "ACP-INIT-202"}
_VERSION_MISMATCH_SKIP_IDS = (_MANDATORY_IDS | _CAPABILITY_IDS) - _NEGOTIATION_IDS
assert _NEGOTIATION_IDS | _VERSION_MISMATCH_SKIP_IDS == _ALL_IDS


def test_v1_conforming_agent_under_protocol_version_2_is_blocked_by_version_mismatch(tmp_path):
    """The v1 conforming fixture speaks only protocol version 1, so under `--protocol-version 2`
    it honestly negotiates down to `1` for every fresh handshake (per `ACP-INIT-201`'s two-branch
    rule). The negotiation rows (`ACP-INIT-001`/`003`/`201`/`202`) are judged normally against
    that honest negotiation and PASS -- an agent that does not yet speak v2 is not thereby
    "broken". Every v2-only shape row (`ACP-INIT-203`/`204`/`ACP-SCHEMA-001`,
    `ACP-SESSION-001`/`002`) SKIPs with the `VERSION-MISMATCH:` marker instead of FAILing, since
    a v1-shaped result cannot be judged against v2 shape rules. Zero FAILs anywhere, yet the run
    as a whole is still NOT CONFORMANT with `verdict.blocked_by_version_mismatch == true`, exit
    code 1, and a terminal hint -- the version-dependent requirements were never actually
    exercised against v2."""
    report_path = tmp_path / "report.json"
    result = _run_cli(
        FIXTURES_DIR_V1,
        "conforming.py",
        protocol_version=2,
        report_json=str(report_path),
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout
    assert "blocked by version mismatch" in result.stdout, result.stdout
    assert "negotiated protocol version" in result.stdout.lower() or "did not negotiate" in result.stdout.lower(), result.stdout

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), f"expected zero FAILs (honest downgrade, not a defect): {result.stdout}"
    for req_id in _NEGOTIATION_IDS:
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    for req_id in _VERSION_MISMATCH_SKIP_IDS:
        assert statuses.get(req_id) == "SKIPPED", f"{req_id}: {result.stdout}"

    report = json.loads(report_path.read_text())
    assert report["verdict"]["blocked_by_version_mismatch"] is True, report["verdict"]
    assert report["verdict"]["conformant"] is False, report["verdict"]

    skip_results = [r for r in report["requirements"] if r["id"] in _VERSION_MISMATCH_SKIP_IDS]
    assert len(skip_results) == len(_VERSION_MISMATCH_SKIP_IDS)
    for r in skip_results:
        assert r["status"] == "SKIPPED", r
        assert any("VERSION-MISMATCH:" in t["message"] for t in r["tests"]), r["tests"]

    pass_results = [r for r in report["requirements"] if r["id"] in _NEGOTIATION_IDS]
    assert len(pass_results) == len(_NEGOTIATION_IDS)
    for r in pass_results:
        assert r["status"] == "PASS", r
