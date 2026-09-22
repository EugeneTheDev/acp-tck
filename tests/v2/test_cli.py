"""End-to-end CLI tests for `--protocol-version 2`: run `python -m tck --protocol-version 2 --
<fixture agent>` as a real subprocess and check the exit code plus the terminal
requirement-summary table. Mirrors `tests/v1/test_cli.py`.

Slice V2-1b expanded this from the skeleton's two routing checks to the full `initialize`/
`session/new` baseline: the conforming fixture PASSing everything, one test per defect fixture
asserting its exact FAIL set, and the version-mismatch scenario (a v1 fixture run under
`--protocol-version 2`). Slice V2-2a adds the mock-client prompt driver's own defect fixtures
(`bad_stop_reason.py`, `vendor_stop_reason.py`, `no_running_update.py`,
`no_idle_after_running.py`, `idle_before_running.py`, `echo_wrong_message_id.py`,
`missing_message_id.py`, `update_wrong_session.py`). Slice V2-2b adds prompt content
capabilities, the permission flow, and the agent->client method rules:
`conforming_full.py` (every id PASSes), `asks_permission.py` (isolates `ACP-PERM-201`), and the
defect/positive-control fixtures `rejects_image_when_advertised.py`,
`calls_elicitation_unadvertised.py`, `calls_fs_unadvertised.py`, `calls_custom_method.py`. Slice
V2-3 adds cancellation (`ACP-CANCEL-201..208`), stdio transport (`ACP-TRANSPORT-002` reused from
v1, plus new/widened `ACP-TRANSPORT-201`/`203`), the JSON-RPC envelope (`ACP-JSONRPC-001..005`,
all five reused from v1 -- D3: the wire assertion itself is unchanged, only the
evidence-gathering probe widens to cover batches), and batching (`ACP-BATCH-201..208`,
`ACP-INFO-BATCH-201/202`) requirements, plus their defect fixtures: `cancel_no_idle.py`,
`cancel_returns_error.py`, `cancel_wrong_stop_reason.py`, `rejects_batch.py`,
`crashes_on_batch.py`, and the transport/JSON-RPC negative controls mirrored from
`tests/fixtures/agents/v1/` on top of the v2 `_base.py`: `banner_on_stdout.py`,
`invalid_utf8.py`, `garbage_after_response.py`, `wrong_id_echo.py`,
`answers_notifications.py`, `result_and_error.py`, `unknown_method_no_error.py`, and the
positive control `emits_batch_updates.py`. It also introduces `_VERSION_TOLERANT_IDS`, a strict
superset of `_NEGOTIATION_IDS`: the eight connection-level `ACP-JSONRPC-*`/`ACP-TRANSPORT-*` rows
are judged identically for an honestly-negotiating v1 agent forced under `--protocol-version 2`,
since their own tests never drive a v2-shaped `session/prompt` turn (see
`test_v1_conforming_agent_under_protocol_version_2_is_blocked_by_version_mismatch` below).
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
    "ACP-TRANSPORT-201",
    "ACP-TRANSPORT-002",
    "ACP-TRANSPORT-203",
    "ACP-JSONRPC-001",
    "ACP-JSONRPC-002",
    "ACP-JSONRPC-003",
    "ACP-BATCH-201",
    "ACP-BATCH-202",
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
    "ACP-PROMPTCAP-001",
    "ACP-PROMPTCAP-002",
    "ACP-PROMPTCAP-003",
    "ACP-PERM-201",
    "ACP-CLIENTCAP-201",
    "ACP-CLIENTCAP-202",
    "ACP-CANCEL-201",
    "ACP-CANCEL-202",
    "ACP-CANCEL-203",
    "ACP-CANCEL-205",
    "ACP-CANCEL-206",
    "ACP-CANCEL-207",
    "ACP-CANCEL-208",
    "ACP-SESSION-203",
    "ACP-RESUME-201",
    "ACP-RESUME-202",
    "ACP-RESUME-203",
    "ACP-RESUME-204",
    "ACP-RESUME-205",
    "ACP-LIST-201",
    "ACP-LIST-202",
    "ACP-LIST-203",
    "ACP-LIST-204",
    "ACP-CLOSE-201",
    "ACP-CLOSE-202",
    "ACP-DELETE-201",
    "ACP-DELETE-202",
    "ACP-ADDDIRS-201",
    "ACP-ADDDIRS-202",
    "ACP-CONFIG-201",
    "ACP-CONFIG-202",
    "ACP-CONFIG-203",
    "ACP-CONFIG-204",
    "ACP-CONFIG-206",
}
_ADVISORY_IDS = {
    "ACP-PROMPT-003",
    "ACP-CANCEL-204",
    "ACP-JSONRPC-004",
    "ACP-JSONRPC-005",
    "ACP-BATCH-203",
    "ACP-BATCH-204",
    "ACP-BATCH-205",
    "ACP-BATCH-206",
    "ACP-BATCH-207",
    "ACP-BATCH-208",
    "ACP-DELETE-203",
}
_INFORMATIONAL_IDS = {
    "ACP-INFO-CONCURRENT-201",
    "ACP-INFO-UNKNOWNSESSION-001",
    "ACP-INFO-CANCEL-201",
    "ACP-INFO-CANCEL-202",
    "ACP-INFO-BATCH-201",
    "ACP-INFO-BATCH-202",
    "ACP-MCP-201",
    "ACP-MCP-202",
}
_ALL_IDS = _MANDATORY_IDS | _CAPABILITY_IDS | _ADVISORY_IDS | _INFORMATIONAL_IDS

# `ACP-BATCH-206`/`207`/`208` (unconditional record-only ADVISORY probes -- see `test_batch.py`)
# and `ACP-CANCEL-204` (ditto for cancellation) never PASS for *any* fixture; they always SKIP.
_ALWAYS_SKIPPED_IDS = {
    "ACP-CANCEL-204",
    "ACP-BATCH-206",
    "ACP-BATCH-207",
    "ACP-BATCH-208",
}

# CAPABILITY-tier cancel rows that need a turn to still be in flight when `session/cancel` is
# sent to be exercised at all -- against a fast fixture with no `--cancel-prompt` override the
# turn routinely resolves before the TCK can act, so these legitimately SKIP ("cancellation not
# exercised") rather than PASS. `ACP-CANCEL-205` (no direct response to the cancel notification
# itself) holds regardless of the race outcome, so it is not in this set. `ACP-CLOSE-202` shares
# `ACP-CANCEL-208`'s exact test (`test_close_cancels_foreground_work`), so it races the same way.
_CANCEL_RACE_SKIP_IDS = {
    "ACP-CANCEL-201",
    "ACP-CANCEL-202",
    "ACP-CANCEL-203",
    "ACP-CANCEL-206",
    "ACP-CANCEL-207",
    "ACP-CANCEL-208",
    "ACP-CLOSE-202",
}

# `ACP-PROMPTCAP-001/002/003` SKIP whenever the agent doesn't advertise the corresponding
# `capabilities.session.prompt.*` marker, and `ACP-PERM-201` SKIPs whenever a turn never
# actually triggers a `session/request_permission` -- both legitimate, expected SKIPs (not
# FAILs) for any V2-2a-era fixture that predates the V2-2b content-capability/permission
# machinery and therefore neither advertises nor exercises it.
_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS = {
    "ACP-PROMPTCAP-001",
    "ACP-PROMPTCAP-002",
    "ACP-PROMPTCAP-003",
    "ACP-PERM-201",
}

# Slice V2-4: every pre-V2-4 fixture advertises only the bare `capabilities: {"session": {}}}`
# baseline (or nothing session-related at all), so the four session-management extras added
# this slice -- `delete`, `additionalDirectories`, `mcp`, and `configOptions` (inferred from
# `session/new`'s own result, not a capability marker) -- all legitimately SKIP for any of them,
# exactly as they do for `conforming.py` itself (see `test_v2_conforming_agent_passes_everything`
# above). `ACP-SESSION-203`/`ACP-RESUME-*`/`ACP-LIST-*`/`ACP-CLOSE-201` are NOT in this set: they
# are gated on the baseline `capabilities.session` marker alone, present even as `{}`.
_SESSION_MGMT_EXTRAS_SKIP_IDS = {
    "ACP-DELETE-201",
    "ACP-DELETE-202",
    "ACP-DELETE-203",
    "ACP-ADDDIRS-201",
    "ACP-ADDDIRS-202",
    "ACP-MCP-201",
    "ACP-MCP-202",
    "ACP-CONFIG-201",
    "ACP-CONFIG-202",
    "ACP-CONFIG-203",
    "ACP-CONFIG-204",
    "ACP-CONFIG-206",
}

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
    k: str | None = None,
    timeout: str = "1",
    startup_timeout: str = "1",
    report_json: str | None = None,
    cancel_prompt: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "tck", "--timeout", timeout, "--startup-timeout", startup_timeout]
    if protocol_version is not None:
        cmd += ["--protocol-version", str(protocol_version)]
    if k is not None:
        cmd += ["-k", k]
    if report_json is not None:
        cmd += ["--report-json", report_json]
    if cancel_prompt is not None:
        cmd += ["--cancel-prompt", cancel_prompt]
    cmd += ["--", sys.executable, str(fixture_dir / fixture)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_SUBPROCESS_TIMEOUT)


def test_help_mentions_protocol_version_option():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--help"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "--protocol-version" in result.stdout


def test_v2_conforming_agent_passes_everything():
    """`conforming.py` advertises only the plain `session: {}` baseline -- no prompt-content
    capabilities, and it never asks for permission -- so the V2-2b capability rows that need
    more than that SKIP rather than PASS: `ACP-PROMPTCAP-001/002/003` ("not advertised") and
    `ACP-PERM-201` ("no permission request observed"). Without a `--cancel-prompt` override,
    `conforming.py`'s short deterministic turns routinely resolve before the TCK can act on
    `session/cancel` at all, so `_CANCEL_RACE_SKIP_IDS` legitimately SKIP too ("cancellation not
    exercised") -- `ACP-CANCEL-205` (no direct response to the cancel notification itself) still
    PASSes regardless of that race, and `_ALWAYS_SKIPPED_IDS` SKIP unconditionally for any
    fixture. Every other id PASSes. See `conforming_full.py`'s own self-test below (with
    `--cancel-prompt __hang__`) for the "every exercisable id PASSes" fixture.

    Slice V2-4: `conforming.py` advertises only the plain `session: {}` baseline, no `delete`/
    `additionalDirectories`/`mcp` marker and no `configOptions` at all -- so `ACP-DELETE-201/202`
    (`capabilities.session.delete` marker), `ACP-DELETE-203` (ADVISORY, but still gated by the
    same marker for its own SKIP), `ACP-ADDDIRS-201/202`, `ACP-MCP-201/202`, and
    `ACP-CONFIG-201..204,206` (`configOptions` absent from `session/new`'s own result -- inferred
    support, not an `initialize`-result marker) all SKIP too. `ACP-SESSION-203`/`ACP-RESUME-
    201..205`/`ACP-LIST-201..204`/`ACP-CLOSE-201`/`ACP-CLOSE-202` are gated on the baseline
    `capabilities.session` marker alone (present even as `{}`), so they PASS -- except
    `ACP-CLOSE-202`, which shares `ACP-CANCEL-208`'s exact race-prone test."""
    result = _run_cli(FIXTURES_DIR_V2, "conforming.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    expected_skips = {
        "ACP-PROMPTCAP-001",
        "ACP-PROMPTCAP-002",
        "ACP-PROMPTCAP-003",
        "ACP-PERM-201",
        "ACP-DELETE-201",
        "ACP-DELETE-202",
        "ACP-DELETE-203",
        "ACP-ADDDIRS-201",
        "ACP-ADDDIRS-202",
        "ACP-MCP-201",
        "ACP-MCP-202",
        "ACP-CONFIG-201",
        "ACP-CONFIG-202",
        "ACP-CONFIG-203",
        "ACP-CONFIG-204",
        "ACP-CONFIG-206",
    } | _CANCEL_RACE_SKIP_IDS | _ALWAYS_SKIPPED_IDS
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", (
                f"{req_id} is {status}, expected SKIPPED (not advertised / no permission "
                f"request observed):\n{result.stdout}"
            )
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS for the v2 conforming fixture:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_v2_conforming_full_agent_passes_everything():
    """`conforming_full.py` advertises `capabilities.session.prompt.{image,audio,
    embeddedContext}` and asks for permission on every turn (`AsksPermissionAgent`) -- every
    V2-2b id, including both INFORMATIONAL probes, PASSes (an INFORMATIONAL test PASSes as long
    as it never hits an assertion failure or a setup/teardown error -- it never asserts on the
    behaviour it probes, only records it). `--cancel-prompt __hang__` keeps every cancel-driven
    turn in flight long enough for `session/cancel` to be exercised for real, so every
    CAPABILITY-tier `ACP-CANCEL-*` id PASSes too -- only `_ALWAYS_SKIPPED_IDS` (permanently
    unobservable ADVISORY record-only probes, never a function of the fixture or timing) still
    SKIP."""
    result = _run_cli(
        FIXTURES_DIR_V2, "conforming_full.py", protocol_version=2, cancel_prompt="__hang__"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id, status in statuses.items():
        if req_id in _ALWAYS_SKIPPED_IDS:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS for conforming_full.py:\n{result.stdout}"
    assert statuses["ACP-INFO-CONCURRENT-201"] == "PASS", result.stdout
    assert statuses["ACP-INFO-UNKNOWNSESSION-001"] == "PASS", result.stdout
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_asks_permission_fixture_passes_perm_201_but_skips_promptcap():
    """`asks_permission.py` isolates `ACP-PERM-201` from `conforming_full.py`'s broader
    capability set: it asks for permission on every turn but advertises no prompt-content
    capabilities at all, so `ACP-PERM-201` PASSes while `ACP-PROMPTCAP-001/002/003` still SKIP
    ("not advertised").

    Perf note (slice V2-4b): scoped with `-k` to `test_permission.py` (owns `ACP-PERM-201`) plus
    `test_prompt_capabilities.py` (owns `ACP-PROMPTCAP-001/002/003`) -- everything else is
    deselected (`NOT_TESTED`) rather than re-verified here. The exit code/overall verdict text
    are not asserted for the same reason as `test_calls_custom_method_passes_everything_it_can`
    above: `-k` scoping necessarily leaves every other MANDATORY id `NOT_TESTED`, which flips the
    verdict to NOT CONFORMANT by design regardless of how the exercised ids actually behave."""
    result = _run_cli(
        FIXTURES_DIR_V2, "asks_permission.py", protocol_version=2, k="test_permission or prompt_capabilities"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert statuses.get("ACP-PERM-201") == "PASS", result.stdout
    for req_id in ("ACP-PROMPTCAP-001", "ACP-PROMPTCAP-002", "ACP-PROMPTCAP-003"):
        assert statuses.get(req_id) == "SKIPPED", result.stdout


# --- V2-2b: prompt content capabilities, the permission flow, and the agent->client method
# rules -- defect fixtures ---


def test_rejects_image_when_advertised_fails_promptcap_001_only():
    result = _run_cli(
        FIXTURES_DIR_V2, "rejects_image_when_advertised.py", protocol_version=2, k="prompt_capabilities"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPTCAP-001"}, result.stdout
    assert statuses.get("ACP-PROMPTCAP-002") == "PASS", result.stdout
    assert statuses.get("ACP-PROMPTCAP-003") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_calls_elicitation_unadvertised_fails_clientcap_201_only():
    result = _run_cli(
        FIXTURES_DIR_V2, "calls_elicitation_unadvertised.py", protocol_version=2, k="client_capabilities"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-CLIENTCAP-201"}, result.stdout
    assert statuses.get("ACP-CLIENTCAP-202") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_calls_fs_unadvertised_fails_clientcap_202_only():
    """`fs/read_text_file` is not a known v2 agent->client method at all (`fs/*`/`terminal/*`
    were removed from v2), so it also cascades into `ACP-SCHEMA-001`'s general "every agent
    message validates against the schema" check -- the same documented
    defect-cascades-into-schema-validation pattern as `ACP-INIT-204` (see
    `tck.v2.requirements`'s module docstring), not a separate bug."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "calls_fs_unadvertised.py",
        protocol_version=2,
        k="client_capabilities or initialize",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-CLIENTCAP-202", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-CLIENTCAP-201") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_calls_custom_method_passes_everything_it_can():
    """Positive control for the `_`-prefix open-enum rule on agent -> client methods, paired
    with `calls_fs_unadvertised.py`'s negative control. Advertises only the plain `session: {}}`
    baseline, so `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201` still SKIP -- this fixture is a
    control for `ACP-CLIENTCAP-201/202` specifically, not a full `conforming_full.py`-style
    all-PASS fixture. The exit code/overall verdict text are not asserted here: this run is
    `-k`-scoped (perf note, slice V2-4b), which necessarily leaves every other MANDATORY id
    NOT_TESTED, and NOT_TESTED MANDATORY ids do flip the verdict to NOT CONFORMANT by design (see
    `tests/v1/test_cli.py`'s `test_hangs_until_cancel_agent_passes_cancel_requirements` for the
    same precedent) -- that says nothing about whether *this* fixture's behaviour for the ids
    actually exercised is conforming, which is what the per-id statuses below check."""
    result = _run_cli(
        FIXTURES_DIR_V2, "calls_custom_method.py", protocol_version=2, k="client_capabilities"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert statuses.get("ACP-CLIENTCAP-201") == "PASS", result.stdout
    assert statuses.get("ACP-CLIENTCAP-202") == "PASS", result.stdout


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
    result = _run_cli(
        FIXTURES_DIR_V2,
        "echoes_any_version.py",
        protocol_version=2,
        k="initialize or (test_session and not capabilities and not config)",
    )
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
    result = _run_cli(
        FIXTURES_DIR_V2,
        "v2_only_errors_on_v1.py",
        protocol_version=2,
        k="initialize or (test_session and not capabilities and not config)",
    )
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
    result = _run_cli(
        FIXTURES_DIR_V2,
        "missing_info.py",
        protocol_version=2,
        k="initialize or (test_session and not capabilities and not config)",
    )
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
    result = _run_cli(
        FIXTURES_DIR_V2,
        "boolean_session_capability.py",
        protocol_version=2,
        k="initialize or (test_session and not capabilities and not config)",
    )
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
    result = _run_cli(
        FIXTURES_DIR_V2,
        "duplicate_session_id.py",
        protocol_version=2,
        k="test_session and not capabilities and not config",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-SESSION-002"}, result.stdout
    assert statuses.get("ACP-SESSION-001") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- V2-2a: the prompt-turn defect fixtures ---


def test_bad_stop_reason_fails_state_203_only():
    """`bad_stop_reason.py` predates the cancellation machinery (V2-3), but its defect (every
    non-`__hang__` prompt -- including the dedicated cancel-test prompt -- resolves immediately
    with an invalid `stopReason: "done"`) also cascades into every `run_prompt`-driven cancel
    check: the terminating idle never says `"cancelled"`, and `"done"` is not a recognised
    `StopReason` the TCK's race heuristic would excuse as "the agent simply finished on its own"
    (mirrors v1's `bad_stop_reason.py` cascading into `ACP-CANCEL-001`). Slice V2-4:
    `ACP-CLOSE-202` shares `ACP-CANCEL-208`'s exact test, so it FAILs alongside it too."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "bad_stop_reason.py",
        protocol_version=2,
        k="(test_prompt and not capabilities) or cancel",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-STATE-203",
        "ACP-CANCEL-201",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
        "ACP-CANCEL-208",
        "ACP-CLOSE-202",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_vendor_stop_reason_passes_everything():
    """Positive control for the `_`-prefix open-enum extensibility rule. Predates V2-2b's
    content-capability/permission machinery, so `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201`
    legitimately SKIP (not advertised / not exercised) rather than PASS -- see
    `_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS`. It also predates V2-3's cancellation machinery: every
    prompt (including the dedicated cancel-test prompt) resolves immediately with its own
    vendor-prefixed stop reason, so the terminating idle after `session/cancel` never says
    `"cancelled"` -- and a `_`-prefixed vendor value is not a recognised `StopReason` the TCK's
    race heuristic excuses as "finished on its own", so this is a genuine (if unintended by the
    original V2-2a fixture) FAIL cascade for `ACP-CANCEL-201`/`206`/`207`/`208`, not a bug in
    this slice -- same shape as `bad_stop_reason.py`'s own documented cascade above.
    `ACP-CANCEL-202` additionally SKIPs rather than FAILs or PASSes: its own test requires the
    prerequisite `stopReason: "cancelled"` from `ACP-CANCEL-201` to have actually happened before
    it can check "no further update after it" -- which never occurs here -- so it correctly
    records "prerequisite not met" instead of judging anything. `_ALWAYS_SKIPPED_IDS`
    (`ACP-CANCEL-204`, `ACP-BATCH-206/207/208`) SKIP unconditionally for any fixture. Slice
    V2-4: `ACP-CLOSE-202` shares `ACP-CANCEL-208`'s exact test, so it FAILs alongside it too, and
    `_SESSION_MGMT_EXTRAS_SKIP_IDS` SKIP ("not advertised") since this fixture predates them."""
    result = _run_cli(FIXTURES_DIR_V2, "vendor_stop_reason.py", protocol_version=2)
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    expected_fails = {
        "ACP-CANCEL-201",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
        "ACP-CANCEL-208",
        "ACP-CLOSE-202",
    }
    expected_skips = (
        _NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS
        | _ALWAYS_SKIPPED_IDS
        | _SESSION_MGMT_EXTRAS_SKIP_IDS
        | {"ACP-CANCEL-202"}
    )
    for req_id, status in statuses.items():
        if req_id in expected_fails:
            assert status == "FAIL", f"{req_id} is {status}, expected FAIL:\n{result.stdout}"
        elif req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_no_running_update_fails_state_201_only():
    result = _run_cli(
        FIXTURES_DIR_V2,
        "no_running_update.py",
        protocol_version=2,
        k="test_prompt and not capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-STATE-201"}, result.stdout
    assert statuses.get("ACP-STATE-202") == "SKIPPED", result.stdout
    assert statuses.get("ACP-STATE-203") == "SKIPPED", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_no_idle_after_running_fails_every_run_prompt_dependent_id():
    """`no_idle_after_running.py` never sends a terminating idle: every test that drives a turn
    through `run_prompt` independently hits `AgentTimeout` and FAILs -- as of V2-2b this
    includes `ACP-CLIENTCAP-201/202` (both observe a turn via `run_prompt`), `ACP-PERM-201`
    (never gets the chance to legitimately SKIP "no permission observed" -- it times out
    instead), and the ADVISORY `ACP-PROMPT-003` (also drives its own `run_prompt` turn).
    `ACP-PROMPTCAP-001/002/003` are unaffected -- they SKIP on the capability-marker check
    before ever calling `run_prompt`, since this fixture advertises `capabilities: {"session":
    {}}}` only. As of V2-3 the cascade additionally includes every `ACP-CANCEL-*` row (all seven
    drive `run_prompt` and never see a terminating idle either), `ACP-INFO-CANCEL-202`
    (INFORMATIONAL, but an uncaught `AgentTimeout` is a FAIL, not a SKIP), and
    `ACP-TRANSPORT-201/002/203` (`test_transport.py`'s own `_drive_full_exchange` drives one
    ordinary `run_prompt` turn to gather evidence, which times out here too). Uses an even
    smaller `--timeout` (`0.5`) than the other CLI self-tests -- this fixture never responds at
    all, so the cascade is deterministic regardless of how short the wait is; a shorter wait
    just means the TCK gives up sooner. Scoped with `-k` to the modules that actually
    contribute a FAIL (plus `test_initialize.py` for the shared `ACP-SCHEMA-001` check) --
    everything else is deselected (`NOT_TESTED`) rather than re-verified here; perf note (slice
    V2-4b). Slice V2-4: `ACP-RESUME-202..205` also FAIL -- their own tests drive a
    `run_prompt` turn via `_session_with_history` to have something to (optionally) replay, and
    that turn also never resolves. `ACP-RESUME-201` is unaffected (no prompt turn needed), and
    `ACP-CLOSE-202` FAILs alongside `ACP-CANCEL-208` since they share the same test."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "no_idle_after_running.py",
        protocol_version=2,
        timeout="0.5",
        k='(test_prompt and not capabilities) or initialize or client_capabilities or permission or cancel or session_capabilities or transport',
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-PROMPT-205",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-PROMPT-003",
        "ACP-SCHEMA-001",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
        "ACP-CLIENTCAP-201",
        "ACP-CLIENTCAP-202",
        "ACP-PERM-201",
        "ACP-CANCEL-201",
        "ACP-CANCEL-202",
        "ACP-CANCEL-203",
        "ACP-CANCEL-205",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
        "ACP-CANCEL-208",
        "ACP-CANCEL-204",
        "ACP-CLOSE-202",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
        "ACP-INFO-CANCEL-202",
        "ACP-TRANSPORT-201",
        "ACP-TRANSPORT-002",
        "ACP-TRANSPORT-203",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_idle_before_running_passes_everything():
    """`idle_before_running.py` sends a legal, unsolicited "session-ready" idle before any
    `session/prompt` is ever issued -- must not be mistaken for a turn terminator. Predates
    V2-2b's content-capability/permission machinery, so `ACP-PROMPTCAP-001/002/003`/
    `ACP-PERM-201` legitimately SKIP rather than PASS -- see
    `_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS`. Like `conforming.py`, its ordinary turns resolve
    fast with no `--cancel-prompt` override, so `_CANCEL_RACE_SKIP_IDS` legitimately SKIP too
    (cancellation not exercised), and `_ALWAYS_SKIPPED_IDS` SKIP unconditionally.

    It also predates V2-3's batching machinery, and cascades into it: `ACP-BATCH-204`/`205`'s
    shared test batches a `session/new` call together with an unknown-method call and expects
    the very next stdout line to be the combined response array. This fixture's
    `_handle_new_session` override fires its unsolicited ready-idle notification as an immediate
    side effect of handling `session/new` -- including when `session/new` arrives inside a batch
    -- so that notification line lands on stdout ahead of the batch's own response array, and the
    test's single `read_line()` sees the notification instead. Both ids FAIL as a result; since
    both are ADVISORY, this does not flip the overall verdict away from CONFORMANT (only a
    MANDATORY/CAPABILITY FAIL would). Slice V2-4: `_SESSION_MGMT_EXTRAS_SKIP_IDS` SKIP too, since
    this fixture predates them and advertises only the bare `session: {}}` baseline."""
    result = _run_cli(FIXTURES_DIR_V2, "idle_before_running.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    expected_fails = {"ACP-BATCH-204", "ACP-BATCH-205"}
    expected_skips = (
        _NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS
        | _CANCEL_RACE_SKIP_IDS
        | _ALWAYS_SKIPPED_IDS
        | _SESSION_MGMT_EXTRAS_SKIP_IDS
    )
    statuses = _table_statuses(result.stdout)
    for req_id, status in statuses.items():
        if req_id in expected_fails:
            assert status == "FAIL", f"{req_id} is {status}, expected FAIL:\n{result.stdout}"
        elif req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_echo_wrong_message_id_fails_prompt_203_and_resume_204():
    """`echo_wrong_message_id.py` echoes a `"wrong-" + messageId` on the live `user_message`
    update -- FAILs `ACP-PROMPT-203` directly (the echoed `messageId` must match the response's).
    Slice V2-4: the same mismatched id is what gets stored and later replayed on
    `session/resume`, so `ACP-RESUME-204`'s own check (the replayed `user_message`'s `messageId`
    must include the original prompt response's `messageId`) also FAILs -- a second,
    independent manifestation of the same underlying defect, not a new bug."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "echo_wrong_message_id.py",
        protocol_version=2,
        k="(test_prompt and not capabilities) or session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPT-203", "ACP-RESUME-204"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_missing_message_id_fails_prompt_201_and_schema_001_and_skips_prompt_203():
    """Perf note (slice V2-4b): scoped with `-k` to `test_prompt.py` (owns `ACP-PROMPT-201/203`)
    plus `test_initialize.py` (owns the shared `ACP-SCHEMA-001` full-exchange schema scan) --
    everything else is deselected (`NOT_TESTED`) rather than re-verified here."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "missing_message_id.py",
        protocol_version=2,
        k="(test_prompt and not capabilities) or initialize",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPT-201", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-PROMPT-203") == "SKIPPED", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_update_wrong_session_fails_every_run_prompt_dependent_id():
    """`update_wrong_session.py` misattributes every `session/update` to `sessionId: "other"`:
    the same cascade shape as `no_idle_after_running.py` (see that test's docstring for why
    `ACP-CLIENTCAP-201/202`/`ACP-PERM-201`/`ACP-PROMPT-003`/every `ACP-CANCEL-*` row/
    `ACP-INFO-CANCEL-202`/`ACP-TRANSPORT-201/002/203` are included here too), since `run_prompt`
    never recognizes a matching terminating idle either. Slice V2-4: also FAILs
    `ACP-RESUME-202..205` (their own tests drive a `run_prompt` turn via `_session_with_history`
    first, which never resolves either) and `ACP-CLOSE-202` (shares `ACP-CANCEL-208`'s exact
    test)."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "update_wrong_session.py",
        protocol_version=2,
        timeout="0.5",
        k='(test_prompt and not capabilities) or initialize or client_capabilities or permission or cancel or session_capabilities or transport',
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-PROMPT-205",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-PROMPT-003",
        "ACP-SCHEMA-001",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
        "ACP-CLIENTCAP-201",
        "ACP-CLIENTCAP-202",
        "ACP-PERM-201",
        "ACP-CANCEL-201",
        "ACP-CANCEL-202",
        "ACP-CANCEL-203",
        "ACP-CANCEL-205",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
        "ACP-CANCEL-208",
        "ACP-CANCEL-204",
        "ACP-CLOSE-202",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
        "ACP-INFO-CANCEL-202",
        "ACP-TRANSPORT-201",
        "ACP-TRANSPORT-002",
        "ACP-TRANSPORT-203",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- V2-3: cancellation, transport, JSON-RPC envelope, and batching defect fixtures ---


def test_cancel_no_idle_fails_every_cancel_dependent_id():
    """`cancel_no_idle.py` hangs on *every* prompt (not just the dedicated cancel-test one) and
    silently ignores `session/cancel` -- so every test that drives a turn through `run_prompt` at
    all times out with an uncaught `AgentTimeout`, a FAIL (not a SKIP -- see `AGENTS.md`
    "Statuses"), the same broad cascade shape as `no_idle_after_running.py`/
    `update_wrong_session.py` above. `ACP-CANCEL-208`/`ACP-CLOSE-202` are the one exception (both
    bound to the same test): `session/close` still rescues the hanging turn via
    `ConformingAgent`'s inherited default handler, so they PASS. Slice V2-4: also FAILs
    `ACP-RESUME-202..205` (their own tests drive a `run_prompt` turn via `_session_with_history`
    first, which never resolves either since this fixture hangs on *every* prompt)."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "cancel_no_idle.py",
        protocol_version=2,
        timeout="0.5",
        k='(test_prompt and not capabilities) or initialize or client_capabilities or permission or cancel or session_capabilities or transport',
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-SCHEMA-001",
        "ACP-TRANSPORT-201",
        "ACP-TRANSPORT-002",
        "ACP-TRANSPORT-203",
        "ACP-CANCEL-201",
        "ACP-CANCEL-202",
        "ACP-CANCEL-203",
        "ACP-CANCEL-205",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
        "ACP-CLIENTCAP-201",
        "ACP-CLIENTCAP-202",
        "ACP-PERM-201",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-PROMPT-205",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
        "ACP-CANCEL-204",
        "ACP-PROMPT-003",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
        "ACP-INFO-CANCEL-202",
    }, result.stdout
    assert statuses.get("ACP-CANCEL-208") == "PASS", result.stdout
    assert statuses.get("ACP-CLOSE-202") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_cancel_returns_error_fails_cancel_203_and_208_only():
    """`cancel_returns_error.py` withholds `session/prompt`'s own acceptance receipt entirely for
    *every* turn, not just the dedicated cancel-test one, until `session/cancel` arrives -- so
    every id whose own test drives an ordinary (non-cancelling) `run_prompt` turn never even gets
    that far and FAILs with a timeout: `ACP-SCHEMA-001`, `ACP-TRANSPORT-201/002/203`,
    `ACP-CLIENTCAP-201/202`, `ACP-PERM-201`, `ACP-PROMPT-201/203/205`, `ACP-STATE-201/202/203`,
    and the ADVISORY `ACP-PROMPT-003`. On top of that cascade, cancelling itself resolves the
    prompt with a JSON-RPC error instead of a terminating idle -- FAILs `ACP-CANCEL-203` (the
    error itself) and `ACP-CANCEL-208`/`ACP-CLOSE-202` (dual-bound to the same test: a
    `session/close` sent instead has nothing registered to rescue either, since `_handle_prompt`
    never adds the session to `_hanging_sessions`). `ACP-CANCEL-201`/`202`/`206`/`207` SKIP,
    deferring to `ACP-CANCEL-203` -- the turn never reaches a terminating idle at all. Slice
    V2-4: also FAILs `ACP-RESUME-202..205` (their own tests drive a `run_prompt` turn via
    `_session_with_history` first, which never resolves either since this fixture withholds its
    acceptance receipt on every turn).

    Perf note (slice V2-4b): split into two `_run_cli` invocations instead of one broad-`-k` run.
    `test_cancel.py` itself (`cancel_result`) needs `--tck-timeout 1` -- at `0.5` its own
    `run_prompt(on_cancel=True, cancel_wait=0.5)` races the fixed `cancel_wait` against the
    read-response deadline and spuriously FAILs `ACP-CANCEL-201/202/206/207` instead of SKIPping
    them (confirmed empirically). The rest of the cascade (`cascade_result`) never gets a response
    at all regardless of timeout, so it can run at a much smaller `--tck-timeout 0.5` safely."""
    cancel_result = _run_cli(
        FIXTURES_DIR_V2, "cancel_returns_error.py", protocol_version=2, k="cancel"
    )
    cascade_result = _run_cli(
        FIXTURES_DIR_V2,
        "cancel_returns_error.py",
        protocol_version=2,
        timeout="0.5",
        k="(test_prompt and not capabilities) or initialize or client_capabilities or test_permission or session_capabilities or transport",
    )
    assert cancel_result.returncode != 0
    assert cascade_result.returncode != 0

    cancel_statuses = _table_statuses(cancel_result.stdout)
    cascade_statuses = _table_statuses(cascade_result.stdout)
    cancel_fails = {req_id for req_id, status in cancel_statuses.items() if status == "FAIL"}
    cascade_fails = {req_id for req_id, status in cascade_statuses.items() if status == "FAIL"}
    assert cancel_fails == {"ACP-CANCEL-203", "ACP-CANCEL-208", "ACP-CLOSE-202"}, cancel_result.stdout
    assert cascade_fails == {
        "ACP-SCHEMA-001",
        "ACP-TRANSPORT-201",
        "ACP-TRANSPORT-002",
        "ACP-TRANSPORT-203",
        "ACP-CLIENTCAP-201",
        "ACP-CLIENTCAP-202",
        "ACP-PERM-201",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-PROMPT-205",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
        "ACP-PROMPT-003",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
    }, cascade_result.stdout
    for req_id in ("ACP-CANCEL-201", "ACP-CANCEL-202", "ACP-CANCEL-206", "ACP-CANCEL-207"):
        assert cancel_statuses.get(req_id) == "SKIPPED", f"{req_id}: {cancel_result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in cancel_result.stdout, cancel_result.stdout
    assert "VERDICT: NOT CONFORMANT" in cascade_result.stdout, cascade_result.stdout


def test_cancel_wrong_stop_reason_fails_201_203_206_207_only():
    """`cancel_wrong_stop_reason.py` hangs on *every* prompt (not just the dedicated cancel-test
    one), so every id whose own test drives an ordinary (non-cancelling) `run_prompt` turn times
    out too, the same broad cascade shape as `cancel_no_idle.py` above: `ACP-SCHEMA-001`,
    `ACP-TRANSPORT-201/002/203`, `ACP-CLIENTCAP-201/202`, `ACP-PERM-201`,
    `ACP-PROMPT-201/203/205`, `ACP-STATE-201/202/203`, and the ADVISORY `ACP-PROMPT-003`. For the
    cancel scenario itself -- a deliberate 1.2s delay clears the TCK's own race window (see the
    fixture's own module docstring; needs `--timeout 2` for that delay to fit comfortably inside
    the wait) before resolving with `stopReason: "end_turn"` instead of `"cancelled"` -- FAILs
    `ACP-CANCEL-201`/`203`/`207` and `ACP-CANCEL-206` (the `_meta`-carrying scenario hits the same
    overridden handler). `ACP-CANCEL-202`/`208` SKIP/PASS respectively, deferring to the rows
    above. Slice V2-4: also FAILs `ACP-RESUME-202..205` (their own tests drive a `run_prompt`
    turn via `_session_with_history` first, which hangs the same way).

    Perf note (slice V2-4b): split into two `_run_cli` invocations instead of one broad-`-k` run
    at `--tck-timeout 2` for everything. Only `test_cancel.py` itself (`cancel_result`) needs the
    full `2` to let the fixture's deliberate 1.2s post-cancel delay clear the TCK's own race
    window; the rest of the cascade (`cascade_result`) never gets a response at all regardless of
    timeout (this fixture hangs on every prompt), so it runs at a much smaller `--tck-timeout
    0.5` safely (confirmed empirically to reproduce the identical FAIL set)."""
    cancel_result = _run_cli(
        FIXTURES_DIR_V2, "cancel_wrong_stop_reason.py", protocol_version=2, timeout="2", k="cancel"
    )
    cascade_result = _run_cli(
        FIXTURES_DIR_V2,
        "cancel_wrong_stop_reason.py",
        protocol_version=2,
        timeout="0.5",
        k="(test_prompt and not capabilities) or initialize or client_capabilities or test_permission or session_capabilities or transport",
    )
    assert cancel_result.returncode != 0
    assert cascade_result.returncode != 0

    cancel_statuses = _table_statuses(cancel_result.stdout)
    cascade_statuses = _table_statuses(cascade_result.stdout)
    cancel_fails = {req_id for req_id, status in cancel_statuses.items() if status == "FAIL"}
    cascade_fails = {req_id for req_id, status in cascade_statuses.items() if status == "FAIL"}
    assert cancel_fails == {
        "ACP-CANCEL-201",
        "ACP-CANCEL-203",
        "ACP-CANCEL-206",
        "ACP-CANCEL-207",
    }, cancel_result.stdout
    assert cascade_fails == {
        "ACP-SCHEMA-001",
        "ACP-TRANSPORT-201",
        "ACP-TRANSPORT-002",
        "ACP-TRANSPORT-203",
        "ACP-CLIENTCAP-201",
        "ACP-CLIENTCAP-202",
        "ACP-PERM-201",
        "ACP-PROMPT-201",
        "ACP-PROMPT-203",
        "ACP-PROMPT-205",
        "ACP-STATE-201",
        "ACP-STATE-202",
        "ACP-STATE-203",
        "ACP-PROMPT-003",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
    }, cascade_result.stdout
    assert cancel_statuses.get("ACP-CANCEL-202") == "SKIPPED", cancel_result.stdout
    assert cancel_statuses.get("ACP-CANCEL-208") == "PASS", cancel_result.stdout
    assert "VERDICT: NOT CONFORMANT" in cancel_result.stdout, cancel_result.stdout
    assert "VERDICT: NOT CONFORMANT" in cascade_result.stdout, cascade_result.stdout


def test_rejects_batch_fails_batch_202_through_205_only():
    """`rejects_batch.py` treats every non-empty batch as if it were the empty-batch case -- a
    single top-level `-32600`/`id: null` object. This coincidentally still satisfies
    `ACP-BATCH-201` (the empty-array case itself). FAILs `ACP-BATCH-202` (a notification-only
    batch gets a bogus reply instead of silence), `ACP-BATCH-203` (no per-entry handling at all),
    and the shared `ACP-BATCH-204`/`205` test (no matching response array is ever produced)."""
    result = _run_cli(FIXTURES_DIR_V2, "rejects_batch.py", protocol_version=2, k="batch")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-BATCH-202", "ACP-BATCH-203", "ACP-BATCH-204", "ACP-BATCH-205"}, result.stdout
    assert statuses.get("ACP-BATCH-201") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_crashes_on_batch_fails_only_batch_rows():
    """`crashes_on_batch.py` exits the moment it sees any batch-shaped line -- otherwise fully
    conforming. FAILs every row whose own test actually sends a batch line
    (`ACP-BATCH-201`/`202`/`203`/`204`/`205`) and nothing else: the acceptance-criteria example of
    a fixture that must fail *only* batch rows."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "crashes_on_batch.py",
        protocol_version=2,
        timeout="2",
        cancel_prompt="__hang__",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-BATCH-201",
        "ACP-BATCH-202",
        "ACP-BATCH-203",
        "ACP-BATCH-204",
        "ACP-BATCH-205",
    }, result.stdout
    assert all(req_id.startswith("ACP-BATCH-") for req_id in fails), result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- V2-3: transport/JSON-RPC negative-control fixtures (mirror the v1 fixtures of the same
# name, on top of v2's own `_base.py` -- D6 "honest duplication, not shared machinery") ---


def test_v2_banner_on_stdout_fails_transport_201_and_schema_001_only():
    """`banner_on_stdout.py` prints a human banner line to stdout before behaving like a
    conforming agent -- violates `ACP-TRANSPORT-201` ("every stdout line is a valid ACP
    message"). The banner line also shows up in the full-exchange schema scan
    (`ACP-SCHEMA-001`), which fails the same way `test_initialize.py`'s scan does for any
    non-object line it can't attribute to a method/response. The banner is plain ASCII, so it
    does not additionally violate `ACP-TRANSPORT-002`."""
    result = _run_cli(
        FIXTURES_DIR_V2, "banner_on_stdout.py", protocol_version=2, k="transport or initialize"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-TRANSPORT-201", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-TRANSPORT-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_invalid_utf8_fails_transport_002_201_and_schema_001():
    """`invalid_utf8.py` writes one line of invalid UTF-8 bytes to stdout before behaving like a
    conforming agent -- the dedicated negative control for `ACP-TRANSPORT-002`. A line that
    isn't decodable text isn't valid JSON either, so it also fails `ACP-TRANSPORT-201` and the
    full-exchange schema scan (`ACP-SCHEMA-001`), same cascade shape as `banner_on_stdout.py`."""
    result = _run_cli(
        FIXTURES_DIR_V2, "invalid_utf8.py", protocol_version=2, k="transport or initialize"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-TRANSPORT-002", "ACP-TRANSPORT-201", "ACP-SCHEMA-001"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_garbage_after_response_fails_transport_201_and_schema_001_only():
    """`garbage_after_response.py` is conforming for the whole exchange, then -- after stdin
    closes -- writes one line of plain-text (ASCII) garbage to stdout before exiting. Only
    catchable via `AgentProcess.close()`'s post-close stdout drain. Fails `ACP-TRANSPORT-201`
    (the garbage line is not valid JSON) and `ACP-SCHEMA-001` (the drained garbage line is still
    on `agent.transcript` when the schema scan runs after `connected_agent`'s `__aexit__`).
    `ACP-TRANSPORT-002` still PASSes: the garbage is plain ASCII."""
    result = _run_cli(
        FIXTURES_DIR_V2, "garbage_after_response.py", protocol_version=2, k="transport or initialize"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-TRANSPORT-201", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-TRANSPORT-002") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_wrong_id_echo_fails_id_dependent_requirements():
    """`wrong_id_echo.py` mangles every response id -- violates `ACP-JSONRPC-001`. Breaking id
    correlation for literally every request/response pair in the connection cascades into
    almost every other requirement (each of whose own test can no longer find its own response
    at all, and either FAILs via a mismatched-shape assertion or hits `AgentTimeout`), so this
    self-test scopes the run to `-k jsonrpc` (mirroring v1's own precedent for the identical
    problem) rather than paying the cost of an unscoped run across the whole suite. Scoped, the
    only requirements actually exercised are the five `ACP-JSONRPC-*` ids plus
    `ACP-TRANSPORT-201` (`test_transport.py`'s own full-exchange test matches the `-k jsonrpc`
    substring via its function name) -- everything else is deselected (`NOT_TESTED`)."""
    result = _run_cli(FIXTURES_DIR_V2, "wrong_id_echo.py", protocol_version=2, k="jsonrpc")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-JSONRPC-001",
        "ACP-JSONRPC-002",
        "ACP-JSONRPC-003",
        "ACP-TRANSPORT-201",
        "ACP-JSONRPC-004",
        "ACP-JSONRPC-005",
    }, result.stdout
    assert statuses.get("ACP-JSONRPC-001") == "FAIL", result.stdout
    assert statuses.get("ACP-JSONRPC-002") == "FAIL", result.stdout
    assert statuses.get("ACP-JSONRPC-003") == "FAIL", result.stdout
    assert statuses.get("ACP-TRANSPORT-201") == "FAIL", result.stdout
    assert statuses.get("ACP-JSONRPC-004") == "FAIL", result.stdout
    assert statuses.get("ACP-JSONRPC-005") == "FAIL", result.stdout
    for req_id in _ALL_IDS - fails:
        assert statuses.get(req_id) == "NOT_TESTED", (
            f"{req_id} is {statuses.get(req_id)}, expected NOT_TESTED (deselected by -k "
            f"jsonrpc):\n{result.stdout}"
        )
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_answers_notifications_fails_jsonrpc_003_only():
    """`answers_notifications.py` unconditionally replies to the `session/cancel` notification
    with a bogus response (`{"id": null, "result": null}`) -- violates `ACP-JSONRPC-003`
    (notifications never receive a response). Nothing else about it is non-conforming."""
    result = _run_cli(FIXTURES_DIR_V2, "answers_notifications.py", protocol_version=2, k="jsonrpc")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-JSONRPC-003"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_result_and_error_fails_jsonrpc_002_and_schema_001_only():
    """`result_and_error.py`'s `initialize` response illegally carries both `result` and
    `error` -- violates `ACP-JSONRPC-002` (exactly one of `result`/`error`) and, via the same
    envelope check, `ACP-SCHEMA-001`. `ACP-INIT-001` still PASSes: that check only asserts
    `"result" in msg`, which remains true even though `error` is also illegally present."""
    result = _run_cli(
        FIXTURES_DIR_V2, "result_and_error.py", protocol_version=2, k="jsonrpc or initialize"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-JSONRPC-002", "ACP-SCHEMA-001"}, result.stdout
    assert statuses.get("ACP-INIT-001") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_v2_unknown_method_no_error_only_fails_the_advisory_requirement():
    """`unknown_method_no_error.py` replies to unknown methods with an empty success result
    instead of `-32601`. Should only trip the ADVISORY `ACP-JSONRPC-004`, never a MANDATORY/
    CAPABILITY requirement -- plus the two batched-unknown-method ADVISORY checks
    (`ACP-BATCH-204`/`205`), which also expect `-32601` for the unknown call inside a mixed
    batch. ADVISORY failures never flip the verdict on their own -- but the exit code/overall
    verdict text are not asserted here: this run is `-k`-scoped (perf note, slice V2-4b), which
    necessarily leaves every other MANDATORY id NOT_TESTED, and NOT_TESTED MANDATORY ids do flip
    the verdict to NOT CONFORMANT by design (see `tests/v1/test_cli.py`'s
    `test_hangs_until_cancel_agent_passes_cancel_requirements` for the same precedent) -- that
    says nothing about whether *this* fixture's behaviour for the ids actually exercised is
    conforming, which is what the per-id statuses below check."""
    result = _run_cli(
        FIXTURES_DIR_V2, "unknown_method_no_error.py", protocol_version=2, k="jsonrpc or batch"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-JSONRPC-004", "ACP-BATCH-204", "ACP-BATCH-205"}, result.stdout
    assert all(req_id in _ADVISORY_IDS for req_id in fails), result.stdout


def test_v2_emits_batch_updates_passes_everything():
    """Positive control: batching every pair of a turn's own spontaneous `session/update`
    notifications into single JSON-RPC batch array lines (`ACP-BATCH-207`, ADVISORY, permits
    this) must not, by itself, break anything the TCK checks. Same "every exercisable id PASSes"
    shape as `conforming_full.py`'s own self-test above -- run with `--cancel-prompt __hang__`
    so every CAPABILITY-tier `ACP-CANCEL-*` id is actually exercised, not just skipped by a race.
    Slice V2-4: this fixture predates the session-management extras and advertises only the bare
    `capabilities.session.prompt.*` baseline, so `_SESSION_MGMT_EXTRAS_SKIP_IDS` legitimately
    SKIP too, exactly as they do for `conforming.py` itself.
    """
    result = _run_cli(
        FIXTURES_DIR_V2, "emits_batch_updates.py", protocol_version=2, cancel_prompt="__hang__"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    expected_skips = _ALWAYS_SKIPPED_IDS | _SESSION_MGMT_EXTRAS_SKIP_IDS
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", (
                f"{req_id} is {status}, expected PASS for emits_batch_updates.py:\n{result.stdout}"
            )
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


# --- V2-4: session management -- defect fixtures ---


def test_resume_replays_when_not_asked_fails_resume_203_only():
    """`resume_replays_when_not_asked.py` replays the session's full retained history on every
    `session/resume`, even when `replayFrom` is omitted/`null` -- FAILs exactly `ACP-RESUME-203`
    (the "MUST NOT replay when not asked" rule). `ACP-RESUME-201` (resume itself still succeeds)
    and `ACP-RESUME-202`/`204`/`205` (the replay-`{"type": "start"}` scenarios, answered
    identically to `conforming_full.py` since this fixture always replays regardless of
    `replayFrom`) are unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "resume_replays_when_not_asked.py",
        protocol_version=2,
        k="session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-RESUME-203"}, result.stdout
    for req_id in ("ACP-RESUME-201", "ACP-RESUME-202", "ACP-RESUME-204", "ACP-RESUME-205"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_resume_responds_before_replay_fails_resume_202_only():
    """`resume_responds_before_replay.py` answers `session/resume` before replaying stored
    history (reversed order vs. the spec's requirement) -- FAILs exactly `ACP-RESUME-202`.
    `ACP-RESUME-204`'s own test reads only up to the response before checking replayed
    `messageId`s, so with the replay now arriving *after* the response it never observes any
    replayed update at all and legitimately SKIPs rather than PASSing or FAILing.
    `ACP-RESUME-201`/`203`/`205` are unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "resume_responds_before_replay.py",
        protocol_version=2,
        k="session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-RESUME-202"}, result.stdout
    assert statuses.get("ACP-RESUME-204") == "SKIPPED", result.stdout
    for req_id in ("ACP-RESUME-201", "ACP-RESUME-203", "ACP-RESUME-205"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_resume_replay_missing_message_id_fails_resume_204_only():
    """`resume_replay_missing_message_id.py` replays correctly (before responding, only when
    asked) but strips `messageId` from every replayed `session/update` -- FAILs exactly
    `ACP-RESUME-204`. `ACP-RESUME-201`/`202`/`203`/`205` are unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "resume_replay_missing_message_id.py",
        protocol_version=2,
        k="session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-RESUME-204"}, result.stdout
    for req_id in ("ACP-RESUME-201", "ACP-RESUME-202", "ACP-RESUME-203", "ACP-RESUME-205"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_list_errors_when_empty_fails_list_202_only():
    """`list_errors_when_empty.py` errors instead of returning `{"sessions": []}` whenever the
    (possibly `cwd`-filtered) result set would be empty -- FAILs exactly `ACP-LIST-202`.
    `ACP-LIST-201`/`203`/`204` are unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2, "list_errors_when_empty.py", protocol_version=2, k="session_capabilities"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-LIST-202"}, result.stdout
    for req_id in ("ACP-LIST-201", "ACP-LIST-203", "ACP-LIST-204"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_close_no_cancel_idle_fails_cancel_208_and_close_202_only():
    """`close_no_cancel_idle.py` keeps `ConformingAgent`'s default hang behaviour (hangs only on
    the literal `__hang__` sentinel), so the defect is bounded and only observable when driven
    with `--cancel-prompt __hang__`: `session/close` on a still-hanging prompt replies to the
    close normally but resolves the pending turn with `stopReason: "end_turn"` instead of
    `"cancelled"`, after a deliberate delay past the TCK's race window. FAILs exactly
    `ACP-CANCEL-208`/`ACP-CLOSE-202` (both dual-bound to `test_close_cancels_foreground_work`).
    Every other id, including plain `ACP-CANCEL-201..207` (which use `session/cancel`, not
    `session/close`) and `ACP-CLOSE-201` (closing an already-idle session), is unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "close_no_cancel_idle.py",
        protocol_version=2,
        cancel_prompt="__hang__",
        k="cancel or session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-CANCEL-208", "ACP-CLOSE-202"}, result.stdout
    assert statuses.get("ACP-CLOSE-201") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_advertises_delete_but_errors_fails_delete_201_202_and_203():
    """`advertises_delete_but_errors.py` advertises `capabilities.session.delete` but always
    errors on `session/delete` -- FAILs `ACP-DELETE-201` (delete itself must succeed) and
    `ACP-DELETE-202` (cascades: the deleted session can't be observed gone). The ADVISORY
    `ACP-DELETE-203` also FAILs (the same underlying probe)."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "advertises_delete_but_errors.py",
        protocol_version=2,
        k="session_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-DELETE-201", "ACP-DELETE-202", "ACP-DELETE-203"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_config_partial_list_fails_config_202_only():
    """`config_partial_list.py` advertises two independent `configOptions` entries but
    `session/set_config_option` replies with only the changed one instead of the complete list
    -- FAILs exactly `ACP-CONFIG-202`. `ACP-CONFIG-201`/`203`/`204`/`206` are unaffected."""
    result = _run_cli(
        FIXTURES_DIR_V2, "config_partial_list.py", protocol_version=2, k="session_config"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-CONFIG-202"}, result.stdout
    for req_id in ("ACP-CONFIG-201", "ACP-CONFIG-203", "ACP-CONFIG-204", "ACP-CONFIG-206"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- version mismatch: a v1 agent run under --protocol-version 2 ---

# The negotiation rows (`ACP-INIT-001`/`003`/`201`/`202`) assert only on the negotiation
# *outcome*, never on the result's shape, so an agent that honestly negotiates down to 1 still
# PASSes them. The v2-only *shape* rows (`info` required, object-only capability markers, v2
# schema validity, plus the CAPABILITY-tier session rows) cannot be meaningfully judged against
# a result the agent never claimed was v2-shaped, so they SKIP with the `VERSION-MISMATCH:`
# marker instead of FAILing (see `tck.v2.requirements`'s "Version-mismatch-aware v2-shape rows"
# section).
# `ACP-PROMPT-003` (ADVISORY) and the two INFORMATIONAL probes carry the same
# `@pytest.mark.capability("capabilities.session")` marker as every other row below, so the
# autouse version-mismatch gate (`tck.common.plugin`'s `_tck_capability_gate`) skips them with
# the same `VERSION-MISMATCH:` marker too -- include them here alongside the MANDATORY/
# CAPABILITY rows rather than carving out a separate, unchecked set.
#
# Slice V2-3 adds a second, disjoint category: `ACP-JSONRPC-001..005` are connection-level rows
# whose own tests never drive a full v2-shaped `session/prompt` turn at all
# (`test_jsonrpc.py`'s tests only use `initialize`/`session/new`/bare notifications). A v1 agent's
# ordinary handshake/session/notification traffic satisfies all five of these unchanged, so --
# like the negotiation rows -- they PASS rather than SKIP here. `ACP-TRANSPORT-002`/`201`/`203`,
# despite also being connection-level, do NOT belong in this set: `test_transport.py`'s own
# `_drive_full_exchange` calls `skip_if_version_mismatch` itself before ever gathering evidence
# (see that module's docstring), specifically so it never has to drive v2-only `run_prompt`
# machinery against a mismatched agent -- so they SKIP, not PASS. Confirmed empirically
# (`.agents/plan.md` D-notes for this slice): a full run of `test_transport.py`/`test_jsonrpc.py`/
# `test_batch.py` against `tests/fixtures/agents/v1/conforming.py` under `--protocol-version 2`
# produces zero FAILs, exactly the five JSONRPC ids PASS, and every other new id (all of
# `ACP-TRANSPORT-*`/`ACP-BATCH-*`/`ACP-INFO-BATCH-*`) SKIPs with `VERSION-MISMATCH:`.
_NEGOTIATION_IDS = {"ACP-INIT-001", "ACP-INIT-003", "ACP-INIT-201", "ACP-INIT-202"}
_VERSION_TOLERANT_IDS = _NEGOTIATION_IDS | {
    "ACP-JSONRPC-001",
    "ACP-JSONRPC-002",
    "ACP-JSONRPC-003",
    "ACP-JSONRPC-004",
    "ACP-JSONRPC-005",
}
_VERSION_MISMATCH_SKIP_IDS = (
    _MANDATORY_IDS | _CAPABILITY_IDS | _ADVISORY_IDS | _INFORMATIONAL_IDS
) - _VERSION_TOLERANT_IDS
assert _VERSION_TOLERANT_IDS | _VERSION_MISMATCH_SKIP_IDS == _ALL_IDS


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
    for req_id in _VERSION_TOLERANT_IDS:
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
        if r["id"] in _ALWAYS_SKIPPED_IDS:
            # ACP-CANCEL-204/ACP-BATCH-206..208 are unconditional record-only SKIPs (MAY,
            # never exercised regardless of version) -- they SKIP here for that reason, not
            # because of the version mismatch, so they carry no VERSION-MISMATCH: marker.
            continue
        assert any("VERSION-MISMATCH:" in t["message"] for t in r["tests"]), r["tests"]

    pass_results = [r for r in report["requirements"] if r["id"] in _VERSION_TOLERANT_IDS]
    assert len(pass_results) == len(_VERSION_TOLERANT_IDS)
    for r in pass_results:
        assert r["status"] == "PASS", r
