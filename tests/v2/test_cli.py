"""End-to-end CLI tests for `--protocol-version 2`: run `python -m tck --protocol-version 2 --
<fixture agent>` as a real subprocess and check the exit code plus the terminal
requirement-summary table. Mirrors `tests/v1/test_cli.py`.

Covers the conforming fixture PASSing everything, one test per defect fixture asserting its
exact FAIL set, and the version-mismatch scenario (a v1 fixture run under
`--protocol-version 2`). `_VERSION_TOLERANT_IDS`, a strict superset of `_NEGOTIATION_IDS`: the
eight connection-level `ACP-JSONRPC-*`/`ACP-TRANSPORT-*` rows are judged identically for an
honestly-negotiating v1 agent forced under `--protocol-version 2`, since their own tests never
drive a v2-shaped `session/prompt` turn (see
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
    "ACP-AUTH-202",
    "ACP-AUTH-206",
    "ACP-AUTH-207",
    "ACP-EXT-001",
}
_CAPABILITY_IDS = {
    "ACP-ENUM-201",
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
    "ACP-AUTH-203",
    "ACP-AUTH-204",
    "ACP-PATCH-201",
    "ACP-PATCH-203",
    "ACP-PATCH-204",
    "ACP-PATCH-205",
    "ACP-PATCH-206",
    "ACP-PATCH-207",
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
    "ACP-AUTH-201",
    "ACP-AUTH-205",
    "ACP-PATCH-208",
    "ACP-PATCH-209",
    "ACP-ENUM-202",
    "ACP-ENUM-203",
    "ACP-META-001",
    "ACP-META-201",
    "ACP-EXT-201",
    "ACP-EXT-202",
    "ACP-ERROR-001",
    "ACP-SHUTDOWN-001",
    "ACP-SCHEMA-002",
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
    "ACP-EXT-203",
    "ACP-STDERR-001",
    "ACP-INFO-PARSE-001",
    "ACP-INFO-INVALIDREQ-001",
}
_ALL_IDS = _MANDATORY_IDS | _CAPABILITY_IDS | _ADVISORY_IDS | _INFORMATIONAL_IDS

# `ACP-BATCH-206`/`207`/`208` (unconditional record-only ADVISORY probes -- see `test_batch.py`)
# and `ACP-CANCEL-204` (ditto for cancellation) never PASS for *any* fixture; they always SKIP --
# except that `ACP-CANCEL-204` (and, not in this set, `ACP-INFO-CANCEL-202`) FAILs instead of
# SKIPping against a fixture that hangs forever on `session/cancel` (`cancel_no_idle.py` and its
# siblings): an uncaught `AgentTimeout` in shared setup is a FAIL, not a SKIP, so "always" here
# means "for any fixture that lets the turn reach a terminating idle", not literally always.
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
# FAILs) for a fixture that neither advertises nor exercises them.
#
# A fixture that never opts into `_base.py`'s `_send_rich_turn_updates` (`emit_rich_turn_updates`
# defaults to `False`) never emits a tool_call_update/plan_update/terminal_update/
# terminal_output_chunk at all, and never asks for permission either -- so these all legitimately
# SKIP ("no <variant> observed") rather than PASS, exactly as they do for `conforming.py` itself
# (see `test_v2_conforming_agent_passes_everything` above).
_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS = {
    "ACP-PROMPTCAP-001",
    "ACP-PROMPTCAP-002",
    "ACP-PROMPTCAP-003",
    "ACP-PERM-201",
    "ACP-ENUM-201",
    "ACP-ENUM-203",
    "ACP-PATCH-204",
    "ACP-PATCH-205",
    "ACP-PATCH-206",
    "ACP-PATCH-207",
    "ACP-PATCH-208",
    "ACP-PATCH-209",
}

# A fixture that advertises only the bare `capabilities: {"session": {}}}` baseline (or nothing
# session-related at all) legitimately SKIPs the session-management extras below -- `delete`,
# `additionalDirectories`, `mcp`, and `configOptions` (inferred from `session/new`'s own result,
# not a capability marker) -- exactly as it does for `conforming.py` itself (see
# `test_v2_conforming_agent_passes_everything` above). `ACP-SESSION-203`/`ACP-RESUME-*`/
# `ACP-LIST-*`/`ACP-CLOSE-201` are NOT in this set: they are gated on the baseline
# `capabilities.session` marker alone, present even as `{}`.
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

# A fixture that advertises no `authMethods` at all, run with no `--auth-method`/
# `--allow-logout`, legitimately SKIPs these five: `ACP-AUTH-203`/`204` both need `authMethods`
# non-empty (`203` additionally needs `--allow-logout`); `ACP-AUTH-207` needs a `type: "terminal"`
# entry to appear on a dedicated connection advertising `capabilities.auth.terminal`.
# `ACP-AUTH-201`/`206` also SKIP here: with no `authMethods` advertised at all there is nothing
# to check uniqueness/type-shape of, and a MANDATORY/ADVISORY row SKIPping on "nothing to check"
# is more honest than a vacuous PASS. `ACP-AUTH-202`/`205` are NOT in this set: each is judged
# against the empty-`authMethods` case itself and PASSes.
_NO_AUTH_SKIP_IDS = {
    "ACP-AUTH-201",
    "ACP-AUTH-203",
    "ACP-AUTH-204",
    "ACP-AUTH-206",
    "ACP-AUTH-207",
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
    auth_method: str | None = None,
    allow_logout: bool = False,
    close_grace: str | None = None,
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
    if auth_method is not None:
        cmd += ["--auth-method", auth_method]
    if allow_logout:
        cmd += ["--allow-logout"]
    if close_grace is not None:
        cmd += ["--close-grace", close_grace]
    cmd += ["--", sys.executable, str(fixture_dir / fixture)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_SUBPROCESS_TIMEOUT)


def test_help_mentions_protocol_version_option():
    result = subprocess.run(
        [sys.executable, "-m", "tck", "--help"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "--protocol-version" in result.stdout


_CONFORMING_EXPECTED_SKIPS = {
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
    "ACP-AUTH-201",
    "ACP-AUTH-203",
    "ACP-AUTH-204",
    "ACP-AUTH-206",
    "ACP-AUTH-207",
    "ACP-ENUM-201",
    "ACP-ENUM-203",
    "ACP-PATCH-204",
    "ACP-PATCH-205",
    "ACP-PATCH-206",
    "ACP-PATCH-207",
    "ACP-PATCH-208",
    "ACP-PATCH-209",
} | _CANCEL_RACE_SKIP_IDS | _ALWAYS_SKIPPED_IDS


def _assert_conforming_baseline(result: subprocess.CompletedProcess[str], fixture: str) -> None:
    """Assert `result` matches `conforming.py`'s own full-run outcome (see its test below):
    every id in `_CONFORMING_EXPECTED_SKIPS` SKIPs, every other id PASSes."""
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    for req_id, status in statuses.items():
        if req_id in _CONFORMING_EXPECTED_SKIPS:
            assert status == "SKIPPED", (
                f"{req_id} is {status}, expected SKIPPED (not advertised / no permission "
                f"request observed):\n{result.stdout}"
            )
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS for {fixture}:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_v2_conforming_agent_passes_everything():
    """`conforming.py` advertises only the plain `session: {}` baseline -- no prompt-content
    capabilities, no `delete`/`additionalDirectories`/`mcp` marker, no `configOptions`, no
    `authMethods`, and it never asks for permission or opts into `_send_rich_turn_updates`. So
    every capability row that needs more than that SKIPs rather than PASSes:
    `ACP-PROMPTCAP-001/002/003` ("not advertised"), `ACP-PERM-201` ("no permission request
    observed"), `ACP-DELETE-201/202/203`/`ACP-ADDDIRS-201/202`/`ACP-MCP-201/202`/
    `ACP-CONFIG-201..204,206` (session-management extras absent), `ACP-AUTH-203/204/207` (no
    `authMethods`, no `--auth-method`/`--allow-logout`), and `ACP-ENUM-201/203`/
    `ACP-PATCH-204..209` (no rich turn updates, no permission request). `ACP-PATCH-201/203` and
    `ACP-ENUM-202` still PASS: the ordinary message-chunk/state-update traffic every turn already
    emits is enough to exercise them. `ACP-SESSION-203`/`ACP-RESUME-201..205`/
    `ACP-LIST-201..204`/`ACP-CLOSE-201` are gated on the baseline `capabilities.session` marker
    alone (present even as `{}`), so they PASS. `ACP-AUTH-202`/`205` PASS too -- each is judged
    against the absence of `authMethods`; `ACP-AUTH-201`/`206` SKIP instead of vacuously passing,
    since there is nothing to check uniqueness/type-shape of.

    Without a `--cancel-prompt` override, `conforming.py`'s short deterministic turns routinely
    resolve before the TCK can act on `session/cancel` at all, so `_CANCEL_RACE_SKIP_IDS`
    (including `ACP-CLOSE-202`, which shares `ACP-CANCEL-208`'s exact race-prone test)
    legitimately SKIP too ("cancellation not exercised") -- `ACP-CANCEL-205` (no direct response
    to the cancel notification itself) still PASSes regardless of that race, and
    `_ALWAYS_SKIPPED_IDS` SKIP unconditionally for any fixture. Every other id PASSes. See
    `conforming_full.py`'s own self-test below (with `--cancel-prompt __hang__`) for the "every
    exercisable id PASSes" fixture."""
    result = _run_cli(FIXTURES_DIR_V2, "conforming.py", protocol_version=2)
    _assert_conforming_baseline(result, "conforming.py")


def test_v2_conforming_full_agent_passes_everything():
    """`conforming_full.py` advertises `capabilities.session.prompt.{image,audio,
    embeddedContext}`, asks for permission on every turn (`AsksPermissionAgent`), opts into
    `_send_rich_turn_updates` (two message chunks sharing one `messageId`, one tool_call
    create+patch sharing one `toolCallId`, one plan_update with one `planId`), and advertises one
    `type: "agent"` authMethods entry (`methodId: "tck"`). Run with `--cancel-prompt __hang__
    --auth-method tck --allow-logout`, this exercises essentially every capability: every
    prompt-content/permission/client-capability id, `ACP-PATCH-201/203/204/205/208/209` and
    `ACP-ENUM-201/202/203`, `ACP-AUTH-203/204`, and every CAPABILITY-tier `ACP-CANCEL-*` id all
    PASS. Both INFORMATIONAL probes PASS too (an INFORMATIONAL test PASSes as long as it never
    hits an assertion failure or setup/teardown error -- it never asserts on the behaviour it
    probes, only records it).

    `conforming_full.py` also advertises a `type: "terminal"` auth method on any connection that
    advertises `capabilities.auth.terminal` (`ACP-AUTH-202` still PASSes since that descriptor
    never appears on the default connection this fixture also answers), and emits one
    `terminal_update` + one `terminal_output_chunk` per turn under the same
    `emit_rich_turn_updates` flag -- so `ACP-AUTH-207`/`ACP-PATCH-206`/`ACP-PATCH-207` all PASS
    too, instead of SKIPping "nothing to check"/"no <variant> observed".

    One id still legitimately SKIPs even for this otherwise all-PASS fixture: `ACP-AUTH-205`
    only concerns the empty-`authMethods` case, the mirror image of `ACP-AUTH-204` PASSing
    precisely because `authMethods` is non-empty. `_ALWAYS_SKIPPED_IDS` (permanently
    unobservable ADVISORY record-only probes) SKIP regardless."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "conforming_full.py",
        protocol_version=2,
        cancel_prompt="__hang__",
        auth_method="tck",
        allow_logout=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    expected_skips = _ALWAYS_SKIPPED_IDS | {
        "ACP-AUTH-205",
    }
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS for conforming_full.py:\n{result.stdout}"
    assert statuses["ACP-INFO-CONCURRENT-201"] == "PASS", result.stdout
    assert statuses["ACP-INFO-UNKNOWNSESSION-001"] == "PASS", result.stdout
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_v2_conforming_full_agent_without_allow_logout_only_skips_auth_203():
    """Acceptance criterion: the same `conforming_full.py --auth-method tck` run, but WITHOUT
    `--allow-logout`, must SKIP ONLY `ACP-AUTH-203` in addition to the baseline's own SKIPs
    (`_ALWAYS_SKIPPED_IDS` plus `ACP-AUTH-205`, per
    `test_v2_conforming_full_agent_passes_everything` above) -- every other id keeps the exact
    same status. `ACP-AUTH-204` still PASSes here since `--auth-method tck` alone is enough to
    exercise `auth/login`; only `auth/logout` (`ACP-AUTH-203`) requires the separate
    `--allow-logout` opt-in."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "conforming_full.py",
        protocol_version=2,
        cancel_prompt="__hang__",
        auth_method="tck",
        allow_logout=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    expected_skips = _ALWAYS_SKIPPED_IDS | {
        "ACP-AUTH-205",
        "ACP-AUTH-203",
    }
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS without --allow-logout:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_asks_permission_fixture_passes_perm_201_but_skips_promptcap():
    """`asks_permission.py` isolates `ACP-PERM-201` from `conforming_full.py`'s broader
    capability set: it asks for permission on every turn but advertises no prompt-content
    capabilities at all, so `ACP-PERM-201` PASSes while `ACP-PROMPTCAP-001/002/003` still SKIP
    ("not advertised").

    Perf note: scoped with `-k` to `test_permission.py` (owns `ACP-PERM-201`) plus
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


# --- prompt content capabilities, the permission flow, and the agent->client method rules --
# defect fixtures ---


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


def test_sends_undefined_client_notification_fails_clientcap_202_only():
    """`run_prompt`'s driver records agent -> client *requests and notifications* alike on
    `PromptTurn.client_requests_seen`, so a notification using an undefined method name cannot
    silently escape `ACP-CLIENTCAP-202`'s check -- its own text claims "request/notification"
    coverage. `sends_undefined_client_notification.py` fires
    exactly that -- a notification, no `id`, method name `made_up/notify` -- and nothing else."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "sends_undefined_client_notification.py",
        protocol_version=2,
        k="client_capabilities",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-CLIENTCAP-202"}, result.stdout
    assert statuses.get("ACP-CLIENTCAP-201") == "PASS", result.stdout
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
    `-k`-scoped, which necessarily leaves every other MANDATORY id NOT_TESTED, and NOT_TESTED
    MANDATORY ids do flip the verdict to NOT CONFORMANT by design (see
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
    """`--report-json` for a real v2 run must carry `protocol_version == 2` and read
    `agent_info`/`agent_capabilities` from the v2-renamed `info`/`capabilities` keys
    (`tck.common.version.VersionSpec.agent_info_field`/`agent_capabilities_field` -- see
    `tests/common/test_version.py` for the mechanism itself in isolation)."""
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
    """No `--protocol-version` given at all -- must run the v1 suite, against the v1 conforming
    fixture."""
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
    `capabilities: {"session": {}}` like `conforming.py`, so `ACP-SESSION-001/002` PASS --
    `session/new` itself is unmodified and correct."""
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


# --- prompt-turn defect fixtures ---


def test_bad_stop_reason_fails_state_203_only():
    """`bad_stop_reason.py`'s defect (every non-`__hang__` prompt -- including the dedicated
    cancel-test prompt -- resolves immediately with an invalid `stopReason: "done"`) cascades
    into every `run_prompt`-driven cancel check: the terminating idle never says `"cancelled"`,
    and `"done"` is not a recognised `StopReason` the TCK's race heuristic would excuse as "the
    agent simply finished on its own" (mirrors v1's `bad_stop_reason.py` cascading into
    `ACP-CANCEL-001`). `ACP-CLOSE-202` shares `ACP-CANCEL-208`'s exact test, so it FAILs
    alongside it too."""
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
    """Positive control for the `_`-prefix open-enum extensibility rule. Advertises only the
    bare `session: {}` baseline and never opts into `_send_rich_turn_updates` or asks for
    permission, so `_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS` (prompt-content capabilities,
    permission, and the tool_call/plan/terminal/permission-dependent PATCH-2xx/ENUM-201/203
    ids), `_SESSION_MGMT_EXTRAS_SKIP_IDS`, and `_NO_AUTH_SKIP_IDS` all legitimately SKIP.

    Every prompt (including the dedicated cancel-test prompt) resolves immediately with its own
    vendor-prefixed stop reason, so the terminating idle after `session/cancel` never says
    `"cancelled"` -- and a `_`-prefixed vendor value is not a recognised `StopReason` the TCK's
    race heuristic excuses as "finished on its own", so this is a genuine FAIL cascade for
    `ACP-CANCEL-201`/`206`/`207`/`208` (same shape as `bad_stop_reason.py`'s own documented
    cascade above), and `ACP-CLOSE-202` FAILs alongside it too (shares `ACP-CANCEL-208`'s exact
    test). `ACP-CANCEL-202` additionally SKIPs rather than FAILs or PASSes: its own test
    requires the prerequisite `stopReason: "cancelled"` from `ACP-CANCEL-201` to have actually
    happened before it can check "no further update after it" -- which never occurs here -- so
    it correctly records "prerequisite not met" instead of judging anything.
    `_ALWAYS_SKIPPED_IDS` (`ACP-CANCEL-204`, `ACP-BATCH-206/207/208`) SKIP unconditionally for
    any fixture."""
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
        | _NO_AUTH_SKIP_IDS
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
    through `run_prompt` independently hits `AgentTimeout` and FAILs. This includes
    `ACP-CLIENTCAP-201/202` (both observe a turn via `run_prompt`), `ACP-PERM-201` (never gets
    the chance to legitimately SKIP "no permission observed" -- it times out instead), the
    ADVISORY `ACP-PROMPT-003`, every `ACP-CANCEL-*` row (all seven drive `run_prompt` and never
    see a terminating idle either) plus `ACP-CLOSE-202` (shares `ACP-CANCEL-208`'s test),
    `ACP-INFO-CANCEL-202` (INFORMATIONAL, but an uncaught `AgentTimeout` is a FAIL, not a SKIP),
    `ACP-TRANSPORT-201/002/203` (`test_transport.py`'s own `_drive_full_exchange` drives one
    ordinary `run_prompt` turn to gather evidence, which times out here too), `ACP-RESUME-
    202..205` (their own tests drive a `run_prompt` turn via `_session_with_history` to have
    something to replay, which also never resolves -- `ACP-RESUME-201` is unaffected, no prompt
    turn needed, and `ACP-CLOSE-202` FAILs alongside `ACP-CANCEL-208` since they share the same
    test), and `ACP-PATCH-209` (its test drives a `run_prompt` turn expecting a permission
    request mid-turn, incidentally selected by this fixture's `-k` pattern via
    `test_permission.py`). Every other `run_prompt`-driven id in `test_enums.py`
    (`ACP-ENUM-201/202`) and `test_extensibility.py` (`ACP-META-001/201`/`ACP-SCHEMA-002`) FAILs
    too, for the same reason -- so `-k` is widened to also select those two modules.
    `ACP-PROMPTCAP-001/002/003` are unaffected -- they SKIP on the capability-marker check before
    ever calling `run_prompt`, since this fixture advertises `capabilities: {"session": {}}}`
    only.

    Uses an even smaller `--timeout` (`0.5`) than the other CLI self-tests -- this fixture never
    responds at all, so the cascade is deterministic regardless of how short the wait is; a
    shorter wait just means the TCK gives up sooner. Scoped with `-k` to the modules that
    actually contribute a FAIL (plus `test_initialize.py` for the shared `ACP-SCHEMA-001`
    check) -- everything else is deselected (`NOT_TESTED`) rather than re-verified here."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "no_idle_after_running.py",
        protocol_version=2,
        timeout="0.5",
        k=(
            "(test_prompt and not capabilities) or initialize or client_capabilities or "
            "permission or cancel or session_capabilities or transport or enums or "
            "extensibility or patches"
        ),
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
        "ACP-SCHEMA-002",
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
        "ACP-PATCH-201",
        "ACP-PATCH-203",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
        "ACP-PATCH-209",
        "ACP-ENUM-201",
        "ACP-ENUM-202",
        "ACP-META-001",
        "ACP-META-201",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_idle_before_running_passes_everything():
    """`idle_before_running.py` sends a legal, unsolicited "session-ready" idle before any
    `session/prompt` is ever issued -- must not be mistaken for a turn terminator. Advertises
    only the bare `session: {}` baseline and never exercises the permission flow, so
    `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201` legitimately SKIP rather than PASS -- see
    `_NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS`. Like `conforming.py`, its ordinary turns resolve
    fast with no `--cancel-prompt` override, so `_CANCEL_RACE_SKIP_IDS` legitimately SKIP too
    (cancellation not exercised), and `_ALWAYS_SKIPPED_IDS` SKIP unconditionally.

    It does NOT cascade into the batching machinery: `ACP-BATCH-204`/`205`/`ACP-JSONRPC-001`'s
    shared test batches two side-effect-free `session/list` calls, which this fixture's
    `_handle_new_session` override never touches, so all three legitimately PASS.
    `_SESSION_MGMT_EXTRAS_SKIP_IDS` SKIP too, since this fixture predates them and advertises
    only the bare `session: {}}` baseline. `_NO_AUTH_SKIP_IDS` SKIP too, since this fixture
    advertises no `authMethods` and the run passes no `--auth-method`."""
    result = _run_cli(FIXTURES_DIR_V2, "idle_before_running.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    expected_skips = (
        _NOT_ADVERTISED_OR_EXERCISED_SKIP_IDS
        | _CANCEL_RACE_SKIP_IDS
        | _ALWAYS_SKIPPED_IDS
        | _SESSION_MGMT_EXTRAS_SKIP_IDS
        | _NO_AUTH_SKIP_IDS
    )
    statuses = _table_statuses(result.stdout)
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", f"{req_id} is {status}, expected PASS:\n{result.stdout}"
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_echo_wrong_message_id_fails_prompt_203_and_resume_204():
    """`echo_wrong_message_id.py` echoes a `"wrong-" + messageId` on the live `user_message`
    update -- FAILs `ACP-PROMPT-203` directly (the echoed `messageId` must match the response's).
    The same mismatched id is what gets stored and later replayed on `session/resume`, so
    `ACP-RESUME-204`'s own check (the replayed `user_message`'s `messageId` must include the
    original prompt response's `messageId`) also FAILs -- a second, independent manifestation of
    the same underlying defect, not a new bug."""
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
    """Perf note: scoped with `-k` to `test_prompt.py` (owns `ACP-PROMPT-201/203`) plus
    `test_initialize.py` (owns the shared `ACP-SCHEMA-001` full-exchange schema scan). Also
    genuinely cascades into `ACP-META-001` (`test_extensibility.py`: its own first assertion,
    `turn.message_id` truthy, fails outright since the acceptance receipt carries none) and
    `ACP-PATCH-203` (`test_patches.py`: two prompts both get `messageId: ""`, so they are not
    *distinct* ids) -- confirmed via an unscoped run; `-k` widened to select those two modules
    too. Everything else is deselected (`NOT_TESTED`) rather than re-verified here."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "missing_message_id.py",
        protocol_version=2,
        k="(test_prompt and not capabilities) or initialize or extensibility or patches",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PROMPT-201", "ACP-SCHEMA-001", "ACP-META-001", "ACP-PATCH-203"}, result.stdout
    assert statuses.get("ACP-PROMPT-203") == "SKIPPED", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_update_wrong_session_fails_every_run_prompt_dependent_id():
    """`update_wrong_session.py` misattributes every `session/update` to `sessionId: "other"`:
    the same cascade shape as `no_idle_after_running.py` (see that test's docstring for why
    `ACP-CLIENTCAP-201/202`/`ACP-PERM-201`/`ACP-PROMPT-003`/every `ACP-CANCEL-*` row (plus
    `ACP-CLOSE-202`, sharing `ACP-CANCEL-208`'s test)/`ACP-INFO-CANCEL-202`/
    `ACP-TRANSPORT-201/002/203` are included here too), since `run_prompt` never recognizes a
    matching terminating idle either. Also FAILs `ACP-RESUME-202..205` (their own tests drive a
    `run_prompt` turn via `_session_with_history` first, which never resolves either) and
    `ACP-PATCH-209` (same "permission" `-k` substring incidence explained on
    `no_idle_after_running.py`'s test above) -- and, for the same reason, every other
    `run_prompt`-driven id: `ACP-ENUM-201/202`, `ACP-META-001/201`, `ACP-SCHEMA-002`, and the
    rest of the `ACP-PATCH-2xx` family -- confirmed identical to `no_idle_after_running.py`'s own
    FAIL set via an unscoped run, since both fixtures never send a terminating idle at all. `-k`
    widened to match."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "update_wrong_session.py",
        protocol_version=2,
        timeout="0.5",
        k=(
            "(test_prompt and not capabilities) or initialize or client_capabilities or "
            "permission or cancel or session_capabilities or transport or enums or "
            "extensibility or patches"
        ),
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
        "ACP-SCHEMA-002",
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
        "ACP-PATCH-201",
        "ACP-PATCH-203",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
        "ACP-PATCH-209",
        "ACP-ENUM-201",
        "ACP-ENUM-202",
        "ACP-META-001",
        "ACP-META-201",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- cancellation, transport, JSON-RPC envelope, and batching defect fixtures ---


def test_cancel_no_idle_fails_every_cancel_dependent_id():
    """`cancel_no_idle.py` hangs on *every* prompt (not just the dedicated cancel-test one) and
    silently ignores `session/cancel` -- so every test that drives a turn through `run_prompt` at
    all times out with an uncaught `AgentTimeout`, a FAIL (not a SKIP -- see `AGENTS.md`
    "Statuses"), the same broad cascade shape as `no_idle_after_running.py`/
    `update_wrong_session.py` above. `ACP-CANCEL-208`/`ACP-CLOSE-202` are the one exception (both
    bound to the same test): `session/close` still rescues the hanging turn via
    `ConformingAgent`'s inherited default handler, so they PASS. Also FAILs `ACP-RESUME-202..205`
    (their own tests drive a `run_prompt` turn via `_session_with_history` first, which never
    resolves either since this fixture hangs on *every* prompt) and `ACP-PATCH-209` (same
    "permission" `-k` substring incidence explained on `no_idle_after_running.py`'s test above)
    -- and, for the same reason, so does every other `run_prompt`-driven id: `ACP-ENUM-201/202`,
    `ACP-META-001/201`, `ACP-SCHEMA-002`, and the rest of the `ACP-PATCH-2xx` family. `-k`
    widened to match."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "cancel_no_idle.py",
        protocol_version=2,
        timeout="0.5",
        k=(
            "(test_prompt and not capabilities) or initialize or client_capabilities or "
            "permission or cancel or session_capabilities or transport or enums or "
            "extensibility or patches"
        ),
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-SCHEMA-001",
        "ACP-SCHEMA-002",
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
        "ACP-PATCH-201",
        "ACP-PATCH-203",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
        "ACP-PATCH-209",
        "ACP-ENUM-201",
        "ACP-ENUM-202",
        "ACP-META-001",
        "ACP-META-201",
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
    deferring to `ACP-CANCEL-203` -- the turn never reaches a terminating idle at all. Also FAILs
    `ACP-RESUME-202..205` (their own tests drive a `run_prompt` turn via `_session_with_history`
    first, which never resolves either since this fixture withholds its acceptance receipt on
    every turn). The same cascade also catches every other `run_prompt`-driven id -- `ACP-
    ENUM-201/202` (`test_enums.py`), `ACP-META-001/201`/`ACP-SCHEMA-002` (`test_extensibility.py`),
    and the whole `ACP-PATCH-2xx` family (`test_patches.py`) -- `-k` widened to select those
    three modules too.

    Perf note: split into two `_run_cli` invocations instead of one broad-`-k` run.
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
        k=(
            "(test_prompt and not capabilities) or initialize or client_capabilities or "
            "test_permission or session_capabilities or transport or enums or extensibility or "
            "patches"
        ),
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
        "ACP-SCHEMA-002",
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
        "ACP-ENUM-201",
        "ACP-ENUM-202",
        "ACP-META-001",
        "ACP-META-201",
        "ACP-PATCH-201",
        "ACP-PATCH-203",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
        "ACP-PATCH-209",
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
    above. Also FAILs `ACP-RESUME-202..205` (their own tests drive a `run_prompt` turn via
    `_session_with_history` first, which hangs the same way). The same cascade also catches
    every other `run_prompt`-driven id -- `ACP-ENUM-201/202`, `ACP-META-001/201`/
    `ACP-SCHEMA-002`, and the whole `ACP-PATCH-2xx` family -- `-k` widened to select those three
    modules too.

    Perf note: split into two `_run_cli` invocations instead of one broad-`-k` run
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
        k=(
            "(test_prompt and not capabilities) or initialize or client_capabilities or "
            "test_permission or session_capabilities or transport or enums or extensibility or "
            "patches"
        ),
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
        "ACP-SCHEMA-002",
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
        "ACP-ENUM-201",
        "ACP-ENUM-202",
        "ACP-META-001",
        "ACP-META-201",
        "ACP-PATCH-201",
        "ACP-PATCH-203",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
        "ACP-PATCH-209",
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
    and the shared `ACP-BATCH-204`/`205` test (no matching response array is ever produced) --
    plus, cascading from the same three tests (each is also the sole batch-delivered evidence
    for one `ACP-JSONRPC-*` id via a second `@pytest.mark.requirement(...)` marker),
    `ACP-JSONRPC-003`/`005`/`001` respectively."""
    result = _run_cli(FIXTURES_DIR_V2, "rejects_batch.py", protocol_version=2, k="batch")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {
        "ACP-BATCH-202",
        "ACP-BATCH-203",
        "ACP-BATCH-204",
        "ACP-BATCH-205",
        "ACP-JSONRPC-001",
        "ACP-JSONRPC-003",
        "ACP-JSONRPC-005",
    }, result.stdout
    assert statuses.get("ACP-BATCH-201") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_crashes_on_batch_fails_only_batch_rows():
    """`crashes_on_batch.py` exits the moment it sees any batch-shaped line -- otherwise fully
    conforming. FAILs every row whose own test actually sends a batch line
    (`ACP-BATCH-201`/`202`/`203`/`204`/`205`), plus -- cascading from the same tests
    (`202`/`203`/`204`+`205`'s tests are also the sole batch-delivered evidence for
    `ACP-JSONRPC-003`/`005`/`001` respectively, via a second `@pytest.mark.requirement(...)`
    marker on each) -- those three ids too. Despite the name,
    "only batch rows" now means "only rows whose evidence is gathered by sending a batch line",
    not literally every failing id's own name starting with `ACP-BATCH-`."""
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
        "ACP-JSONRPC-001",
        "ACP-JSONRPC-003",
        "ACP-JSONRPC-005",
    }, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- transport/JSON-RPC negative-control fixtures (mirror the v1 fixtures of the same name, on
# top of v2's own `_base.py` -- honest duplication, not shared machinery) ---


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
    at all, and either FAILs via a mismatched-shape assertion or hits `AgentTimeout`) --
    unscoped, this fixture FAILs all 106 ids, which is the intended, correct verdict shape for
    an agent this broken, not a TCK bug -- so this self-test scopes the run to `-k jsonrpc`
    (mirroring v1's own precedent for the identical problem) rather than paying the cost of an
    unscoped run across the whole suite. Scoped, the only requirements actually exercised are
    the five `ACP-JSONRPC-*` ids plus `ACP-TRANSPORT-201` (`test_transport.py`'s own
    full-exchange test matches the `-k jsonrpc` substring via its function name) -- everything
    else is deselected (`NOT_TESTED`)."""
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


def test_v2_pushes_status_notifications_passes_everything():
    """`pushes_status_notifications.py` pushes an unsolicited `_`-prefixed notification after
    every notification it receives, so one lands in the quiet period of `ACP-JSONRPC-003`/
    `ACP-BATCH-202`/`ACP-EXT-201`. A notification is not a reply, so the outcome must match
    `conforming.py`'s exactly."""
    result = _run_cli(FIXTURES_DIR_V2, "pushes_status_notifications.py", protocol_version=2)
    _assert_conforming_baseline(result, "pushes_status_notifications.py")


def test_v2_pushes_status_and_answers_notifications_fails_no_reply_rows_only():
    """`pushes_status_and_answers_notifications.py` pushes the same status notification, then
    also replies to the notification. The leading notification must not hide the reply behind
    it: every "a notification gets no response" row still FAILs."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "pushes_status_and_answers_notifications.py",
        protocol_version=2,
        k="test_batch or test_jsonrpc or test_extensibility",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-JSONRPC-003", "ACP-BATCH-202", "ACP-EXT-201"}, result.stdout


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
    CAPABILITY requirement. `ACP-BATCH-204`/`205`'s own probe batches two `session/list` calls,
    never an unknown method, so this fixture does not fail them. ADVISORY failures never flip
    the verdict on their own -- but the exit code/overall verdict text are not asserted here:
    this run is `-k`-scoped, which necessarily leaves every other MANDATORY id NOT_TESTED, and
    NOT_TESTED MANDATORY ids do flip the verdict to NOT CONFORMANT by design (see
    `tests/v1/test_cli.py`'s
    `test_hangs_until_cancel_agent_passes_cancel_requirements` for the same precedent) -- that
    says nothing about whether *this* fixture's behaviour for the ids actually exercised is
    conforming, which is what the per-id statuses below check."""
    result = _run_cli(
        FIXTURES_DIR_V2, "unknown_method_no_error.py", protocol_version=2, k="jsonrpc or batch"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-JSONRPC-004"}, result.stdout
    assert statuses.get("ACP-BATCH-204") == "PASS", result.stdout
    assert statuses.get("ACP-BATCH-205") == "PASS", result.stdout
    assert all(req_id in _ADVISORY_IDS for req_id in fails), result.stdout


def test_v2_emits_batch_updates_passes_everything():
    """Positive control: batching every pair of a turn's own spontaneous `session/update`
    notifications into single JSON-RPC batch array lines (`ACP-BATCH-207`, ADVISORY, permits
    this) must not, by itself, break anything the TCK checks. Same "every exercisable id PASSes"
    shape as `conforming_full.py`'s own self-test above -- run with `--cancel-prompt __hang__`
    so every CAPABILITY-tier `ACP-CANCEL-*` id is actually exercised, not just skipped by a race.
    This fixture advertises only the bare `capabilities.session.prompt.*` baseline (no
    session-management extras, no `authMethods`), so `_SESSION_MGMT_EXTRAS_SKIP_IDS`/
    `_NO_AUTH_SKIP_IDS` legitimately SKIP too, exactly as they do for `conforming.py` itself.
    """
    result = _run_cli(
        FIXTURES_DIR_V2, "emits_batch_updates.py", protocol_version=2, cancel_prompt="__hang__"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    assert set(statuses) == _ALL_IDS, f"requirement table missing/extra ids: {result.stdout}"
    # This fixture never opts into `_send_rich_turn_updates` either, so the tool_call/plan/
    # terminal-dependent ids legitimately SKIP as they do for `conforming.py`/
    # `vendor_stop_reason.py`/`idle_before_running.py` above. Unlike those three, though, this
    # fixture is built on `AsksPermissionAgent` (it asks for permission mid-turn, same as
    # `conforming_full.py`), so the permission-dependent `ACP-ENUM-203`/`ACP-PATCH-209` PASS
    # here rather than SKIP -- only `ACP-PATCH-208` (needs a *tool_call_update*, not a
    # permission request) still SKIPs.
    _RICH_TURN_SKIP_IDS = {
        "ACP-ENUM-201",
        "ACP-PATCH-204",
        "ACP-PATCH-205",
        "ACP-PATCH-206",
        "ACP-PATCH-207",
        "ACP-PATCH-208",
    }
    expected_skips = (
        _ALWAYS_SKIPPED_IDS | _SESSION_MGMT_EXTRAS_SKIP_IDS | _NO_AUTH_SKIP_IDS | _RICH_TURN_SKIP_IDS
    )
    for req_id, status in statuses.items():
        if req_id in expected_skips:
            assert status == "SKIPPED", f"{req_id} is {status}, expected SKIPPED:\n{result.stdout}"
        else:
            assert status == "PASS", (
                f"{req_id} is {status}, expected PASS for emits_batch_updates.py:\n{result.stdout}"
            )
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


# --- session management -- defect fixtures ---


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


def test_resume_always_errors_all_resume_rows_skip_together():
    """`resume_always_errors.py` advertises `capabilities.session: {}` but always errors on
    `session/resume` with a plain `-32603`, never `-32601` (Method not found, which
    `obtain_resumable_session` treats as a hard FAIL). All three of
    `obtain_resumable_session`'s routes (create-then-resume, list-then-resume, close-then-resume)
    end in the same `session/resume` call, so all three are exhausted identically here, and
    every test that routes through it -- `ACP-RESUME-201..205` and `ACP-ADDDIRS-202` -- must
    SKIP together with the same "no resumable session obtainable" reason, never hard-FAIL:
    `ACP-RESUME-202..205` must call `obtain_resumable_session` first rather than building their
    own session directly (`_session_with_history`), or they would hard-FAIL on this fixture's
    `session/resume` error, producing a false NOT CONFORMANT for an agent the TCK itself admits
    it could not obtain a resumable session from."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "resume_always_errors.py",
        protocol_version=2,
        k="session_capabilities",
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), f"expected no FAILs, got {fails}: {result.stdout}"
    for req_id in (
        "ACP-RESUME-201",
        "ACP-RESUME-202",
        "ACP-RESUME-203",
        "ACP-RESUME-204",
        "ACP-RESUME-205",
        "ACP-ADDDIRS-202",
    ):
        assert statuses.get(req_id) == "SKIPPED", f"{req_id}: {result.stdout}"


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


# --- authentication (`ACP-AUTH-201..207`) -- self-tests ---


def test_gated_by_auth_without_auth_method_is_blocked_by_auth():
    """`gated_by_auth.py` always errors `session/new` with `-32000` unless `auth/login` with
    methodId `"tck"` has already succeeded on the connection. Without `--auth-method`, every
    session-dependent test SKIPs with the `AUTH-GATED:` marker (via `skip_if_auth_gated()`),
    which forces `verdict.blocked_by_auth == true` and exit code 1 -- even though zero
    requirements actually FAILed; they were simply never exercised. Mirrors v1's
    `gated_by_auth.py` self-test."""
    result = _run_cli(FIXTURES_DIR_V2, "gated_by_auth.py", protocol_version=2)
    assert result.returncode != 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), f"expected zero FAILs (the agent is merely never exercised): {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout
    assert "blocked by auth" in result.stdout.lower() or "auth-gated" in result.stdout.lower(), result.stdout


def test_gated_by_auth_with_auth_method_is_conformant():
    """The same `gated_by_auth.py` fixture, run with `--auth-method tck`: `connected_agent`'s
    auto-login step (`_helpers.py`) authenticates before any session-dependent test ever calls
    `session/new`, so the gate never fires and the run is fully CONFORMANT."""
    result = _run_cli(FIXTURES_DIR_V2, "gated_by_auth.py", protocol_version=2, auth_method="tck")
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert "VERDICT: CONFORMANT" in result.stdout, result.stdout


def test_terminal_auth_unadvertised_fails_auth_202_only():
    """`terminal_auth_unadvertised.py` advertises a `type: "terminal"` authMethods entry on every
    connection, including the default one that never advertises `capabilities.auth.terminal` --
    FAILs exactly `ACP-AUTH-202`. It has no `args`/`env` fields at all, so it cannot also trip
    `ACP-AUTH-207` (which only runs when a terminal entry actually appears on the dedicated
    terminal-capable connection -- and this fixture happens to also advertise it there, but with
    a well-formed descriptor)."""
    result = _run_cli(FIXTURES_DIR_V2, "terminal_auth_unadvertised.py", protocol_version=2, k="authentication")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-AUTH-202"}, result.stdout
    for req_id in ("ACP-AUTH-201", "ACP-AUTH-206", "ACP-AUTH-207"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_duplicate_method_id_fails_auth_201_only_and_stays_conformant():
    """`duplicate_method_id.py` advertises two `authMethods` entries sharing the same
    `methodId` -- FAILs exactly `ACP-AUTH-201`, which is ADVISORY (re-cites v1's `ACP-AUTH-001`).
    An ADVISORY FAIL never affects `verdict.conformant` on its own -- unlike every other defect
    fixture in this section, all of which trip a MANDATORY id. Scoped with `-k authentication`
    (`tests/v2/test_cli.py`'s own `-k` convention, see `test_asks_permission_fixture_passes_
    perm_201_but_skips_promptcap` above), so the exit code/overall verdict text are not asserted:
    scoping necessarily leaves every other MANDATORY id `NOT_TESTED`, which flips the verdict to
    NOT CONFORMANT by design regardless of how the exercised ids actually behave -- the "stays
    conformant" claim in this test's name is about `ACP-AUTH-201`'s own tier, not the scoped
    run's own verdict line."""
    result = _run_cli(FIXTURES_DIR_V2, "duplicate_method_id.py", protocol_version=2, k="authentication")

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-AUTH-201"}, result.stdout
    for req_id in ("ACP-AUTH-202", "ACP-AUTH-206"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"


def test_custom_auth_type_unprefixed_fails_auth_206_only():
    """`custom_auth_type_unprefixed.py` advertises an authMethods entry whose `type` is
    `"sso"` -- neither a defined value nor `_`-prefixed -- FAILs exactly `ACP-AUTH-206`
    (MANDATORY, new in v2)."""
    result = _run_cli(FIXTURES_DIR_V2, "custom_auth_type_unprefixed.py", protocol_version=2, k="authentication")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-AUTH-206"}, result.stdout
    for req_id in ("ACP-AUTH-201", "ACP-AUTH-202"):
        assert statuses.get(req_id) == "PASS", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_advertises_auth_but_logout_errors_fails_auth_203_only_with_allow_logout():
    """`advertises_auth_but_logout_errors.py` implements `auth/login` normally but always errors
    on `auth/logout`. Run with `--auth-method tck --allow-logout` (both required to actually
    exercise `auth/logout` at all) -- FAILs exactly `ACP-AUTH-203`."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "advertises_auth_but_logout_errors.py",
        protocol_version=2,
        k="authentication",
        auth_method="tck",
        allow_logout=True,
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-AUTH-203"}, result.stdout
    assert statuses.get("ACP-AUTH-204") == "PASS", result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_advertises_auth_but_logout_errors_skips_auth_203_without_allow_logout():
    """The same fixture, without `--allow-logout`: `auth/logout` is never called at all, so
    `ACP-AUTH-203` SKIPs (its documented, diagnosable reason) rather than FAILing. Scoped with
    `-k authentication`, so the exit code/overall verdict text are not asserted -- see
    `test_duplicate_method_id_fails_auth_201_only_and_stays_conformant` above for why; the
    "fully CONFORMANT" claim is about `ACP-AUTH-203` no longer being a FAIL, not the scoped run's
    own verdict line."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "advertises_auth_but_logout_errors.py",
        protocol_version=2,
        k="authentication",
        auth_method="tck",
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert statuses.get("ACP-AUTH-203") == "SKIPPED", result.stdout


def test_terminal_env_duplicate_names_fails_auth_207_only():
    """`terminal_env_duplicate_names.py` only advertises its `type: "terminal"` authMethods entry
    to a connection that itself advertises `capabilities.auth.terminal` -- so it never trips
    `ACP-AUTH-202` (the default connection sees no `authMethods` at all) -- but that entry's
    `env` array has two entries sharing the same `name`, FAILing exactly `ACP-AUTH-207`
    (MANDATORY, new in v2). `ACP-AUTH-201`/`206` bind to `agent_initialize_result`, which
    connects with the default (no `auth.terminal`) capabilities, so they see no `authMethods` at
    all and SKIP rather than PASS."""
    result = _run_cli(FIXTURES_DIR_V2, "terminal_env_duplicate_names.py", protocol_version=2, k="authentication")
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-AUTH-207"}, result.stdout
    assert statuses.get("ACP-AUTH-202") == "PASS", result.stdout
    for req_id in ("ACP-AUTH-201", "ACP-AUTH-206"):
        assert statuses.get(req_id) == "SKIPPED", f"{req_id}: {result.stdout}"
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


# --- patch/upsert semantics, open enums, extensibility/hygiene -- defect fixtures ---


def test_tool_call_update_missing_id_fails_patch_204_and_schema_001():
    """`tool_call_update_missing_id.py` emits one `tool_call_update` with no `toolCallId` --
    FAILs `ACP-PATCH-204` directly, and cascades into `ACP-SCHEMA-001` since `ToolCallUpdate`
    schema-requires `toolCallId` (`schema/v2/schema.json`'s `$defs/ToolCallUpdate`). It overrides
    `_send_rich_turn_updates`, which `_base.py` calls on *every* turn, so it also cascades into
    `ACP-PROMPT-205` (CAPABILITY -- schema-validates every `session/update` a driven turn
    observes) -- confirmed via an unscoped run; `-k` is widened to `test_prompt` too so this
    self-test's own asserted FAIL set matches an unscoped run's."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "tool_call_update_missing_id.py",
        protocol_version=2,
        k="test_patches or initialize or (test_prompt and not capabilities)",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PATCH-204", "ACP-SCHEMA-001", "ACP-PROMPT-205"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_plan_missing_plan_id_fails_patch_205_and_schema_001():
    """`plan_missing_plan_id.py` emits one `plan_update` whose `plan` object has no `planId` --
    FAILs `ACP-PATCH-205` directly, and cascades into `ACP-SCHEMA-001` since `PlanItems`
    schema-requires `planId` (`schema/v2/schema.json`'s `$defs/PlanItems`). Same
    `_send_rich_turn_updates`-on-every-turn cascade as the sibling test above also FAILs
    `ACP-PROMPT-205` unscoped; `-k` widened to match."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "plan_missing_plan_id.py",
        protocol_version=2,
        k="test_patches or initialize or (test_prompt and not capabilities)",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PATCH-205", "ACP-SCHEMA-001", "ACP-PROMPT-205"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_message_chunk_missing_message_id_fails_patch_201_and_schema_001():
    """`message_chunk_missing_message_id.py` emits one `agent_message_chunk` with no
    `messageId` -- FAILs `ACP-PATCH-201` directly, and cascades into `ACP-SCHEMA-001` since
    `ContentChunk` schema-requires `messageId` (`schema/v2/schema.json`'s `$defs/ContentChunk`).
    Same `_send_rich_turn_updates`-on-every-turn cascade as the two sibling tests above also
    FAILs `ACP-PROMPT-205` unscoped; `-k` widened to match."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "message_chunk_missing_message_id.py",
        protocol_version=2,
        k="test_patches or initialize or (test_prompt and not capabilities)",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-PATCH-201", "ACP-SCHEMA-001", "ACP-PROMPT-205"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_unprefixed_custom_session_update_fails_enum_202_only():
    """`unprefixed_custom_session_update.py` sends one `session/update` with
    `sessionUpdate: "surprise"` (neither a defined constant nor `_`-prefixed) -- FAILs
    `ACP-ENUM-202` only. The `SessionUpdate` `$def`'s own `"other"`-titled fallback branch only
    requires `sessionUpdate` to be a string, so this does NOT cascade into `ACP-SCHEMA-001`."""
    result = _run_cli(
        FIXTURES_DIR_V2, "unprefixed_custom_session_update.py", protocol_version=2, k="test_enums"
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-ENUM-202"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_prefixed_custom_session_update_passes_enum_202():
    """Positive control for the rule above: `_tck_custom_update` is `_`-prefixed, so
    `ACP-ENUM-202` PASSes."""
    result = _run_cli(
        FIXTURES_DIR_V2, "prefixed_custom_session_update.py", protocol_version=2, k="test_enums"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert statuses.get("ACP-ENUM-202") == "PASS", result.stdout


def test_custom_method_no_response_fails_ext_001_and_error_001():
    """`custom_method_no_response.py` silently swallows every `_`-prefixed custom method
    request instead of responding at all -- FAILs `ACP-EXT-001` (MANDATORY) directly. It also
    cascades into the ADVISORY `ACP-ERROR-001` (`test_diagnostics.py`): that probe sends its own
    `_`-prefixed unknown method and, getting no reply at all instead of a `-32601` with a
    non-empty one-line `message`, FAILs the "error message is well-formed" check outright
    (confirmed via an unscoped run; the batch tests use a different unknown-method probe now, so
    `ACP-BATCH-203/204/205` are unaffected here). `-k` widened to `test_diagnostics` to match."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "custom_method_no_response.py",
        protocol_version=2,
        k="test_extensibility or test_diagnostics",
    )
    assert result.returncode != 0

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-EXT-001", "ACP-ERROR-001"}, result.stdout
    assert "VERDICT: NOT CONFORMANT" in result.stdout, result.stdout


def test_error_message_with_newline_fails_error_001_only():
    """`error_message_with_newline.py` appends an embedded newline to the `-32601` error
    message only -- FAILs `ACP-ERROR-001` (ADVISORY) only."""
    result = _run_cli(
        FIXTURES_DIR_V2, "error_message_with_newline.py", protocol_version=2, k="test_diagnostics"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-ERROR-001"}, result.stdout


def test_never_exits_on_stdin_close_fails_shutdown_001_only():
    """`never_exits_on_stdin_close.py` needs SIGTERM/SIGKILL to actually terminate -- FAILs
    `ACP-SHUTDOWN-001` (ADVISORY) only. `--close-grace` is kept small so this self-test doesn't
    pay the default grace period at every rung of the shutdown ladder."""
    result = _run_cli(
        FIXTURES_DIR_V2,
        "never_exits_on_stdin_close.py",
        protocol_version=2,
        k="test_diagnostics",
        close_grace="0.2",
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-SHUTDOWN-001"}, result.stdout


def test_unknown_root_key_fails_schema_002_only():
    """`unknown_root_key.py` adds `unknownRootKey` to the `initialize` result's root -- FAILs
    `ACP-SCHEMA-002` (ADVISORY) only; the vendored schema itself never sets
    `additionalProperties: false`, so this is not caught by `ACP-SCHEMA-001`/`ACP-INIT-001`."""
    result = _run_cli(
        FIXTURES_DIR_V2, "unknown_root_key.py", protocol_version=2, k="test_extensibility or initialize"
    )

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == {"ACP-SCHEMA-002"}, result.stdout


def test_noisy_stderr_and_parse_error_reply_fails_nothing():
    """`noisy_stderr_and_parse_error_reply.py` logs every raw line to stderr and replies with an
    explicit `-32700` to malformed JSON instead of staying silent -- self-test only, exercising
    the non-default branches of `ACP-STDERR-001`/`ACP-INFO-PARSE-001` (both INFORMATIONAL,
    never asserted on the probed behaviour itself, so this fixture FAILs nothing)."""
    result = _run_cli(FIXTURES_DIR_V2, "noisy_stderr_and_parse_error_reply.py", protocol_version=2)
    assert result.returncode == 0, result.stdout + result.stderr

    statuses = _table_statuses(result.stdout)
    fails = {req_id for req_id, status in statuses.items() if status == "FAIL"}
    assert fails == set(), result.stdout
    assert statuses.get("ACP-STDERR-001") == "PASS", result.stdout
    assert statuses.get("ACP-INFO-PARSE-001") == "PASS", result.stdout


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
# A second, disjoint category: `ACP-JSONRPC-001..005` are connection-level rows whose own tests
# never drive a full v2-shaped `session/prompt` turn at all (`test_jsonrpc.py`'s tests only use
# `initialize`/`session/new`/bare notifications). A v1 agent's ordinary handshake/session/
# notification traffic satisfies all five of these unchanged, so -- like the negotiation rows --
# they PASS rather than SKIP here. `ACP-TRANSPORT-002`/`201`/`203`, despite also being
# connection-level, do NOT belong in this set: `test_transport.py`'s own `_drive_full_exchange`
# calls `skip_if_version_mismatch` itself before ever gathering evidence (see that module's
# docstring), specifically so it never has to drive v2-only `run_prompt` machinery against a
# mismatched agent -- so they SKIP, not PASS. Confirmed empirically: a full run of
# `test_transport.py`/`test_jsonrpc.py`/`test_batch.py` against
# `tests/fixtures/agents/v1/conforming.py` under `--protocol-version 2` produces zero FAILs,
# exactly the five JSONRPC ids PASS, and every other new id (all of
# `ACP-TRANSPORT-*`/`ACP-BATCH-*`/`ACP-INFO-BATCH-*`) SKIPs with `VERSION-MISMATCH:`.
_NEGOTIATION_IDS = {"ACP-INIT-001", "ACP-INIT-003", "ACP-INIT-201", "ACP-INIT-202"}
# ACP-EXT-001/201/203 probe an ordinary `_`-/`$/`-prefixed custom method or notification
# exchange -- they never inspect `initialize`'s negotiated version or its `capabilities` shape at
# all, so they PASS regardless of which protocolVersion was negotiated.
# ACP-EXT-202 is NOT included here: it reads `result.capabilities` (the v2 field name) directly,
# which a v1-negotiated result simply doesn't have (v1 uses `agentCapabilities` instead), so it
# correctly `pytest.skip("initialize result has no capabilities object to check")`s on its own --
# a genuine skip, not the VERSION-MISMATCH marker, but still a skip either way (see
# `test_extensibility.py`'s module docstring for the full breakdown).
_VERSION_TOLERANT_IDS = _NEGOTIATION_IDS | {
    "ACP-JSONRPC-001",
    "ACP-JSONRPC-002",
    "ACP-JSONRPC-003",
    "ACP-JSONRPC-004",
    "ACP-JSONRPC-005",
    "ACP-EXT-001",
    "ACP-EXT-201",
    "ACP-EXT-203",
    # ACP-INFO-PARSE-001/ACP-INFO-INVALIDREQ-001 (re-cited from v1, unchanged) carry no
    # `@pytest.mark.capability(...)` marker at all (test_informational.py's module docstring),
    # and their shared `_probe_connection_usable_after` helper swallows a `session/new` failure
    # -- including a version-mismatched/capability-unsupporting one -- into an "unusable"
    # behaviour string rather than letting it propagate, then only ever `record_property(...)`s
    # it, never asserts. So both PASS unconditionally, the same as the five JSONRPC ids above.
    "ACP-INFO-PARSE-001",
    "ACP-INFO-INVALIDREQ-001",
    # ACP-STDERR-001 (re-cited from v1, unchanged): also connection-level/no capability marker,
    # and its own `new_session(...)` call succeeds even against a v1-negotiated agent -- v1's
    # `conforming.py` implements `session/new` unconditionally at the wire level, with no
    # capability check of its own -- so this always PASSes regardless of negotiated version too.
    "ACP-STDERR-001",
    # ACP-ERROR-001/ACP-SHUTDOWN-001 (re-cited from v1, unchanged, `test_diagnostics.py`): same
    # story -- connection-level, no capability marker, and their own `session/new` (missing
    # `cwd`, or ordinary) calls succeed at the wire level against a v1-negotiated agent too.
    "ACP-ERROR-001",
    "ACP-SHUTDOWN-001",
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
        if r["id"] == "ACP-EXT-202":
            # ACP-EXT-202 carries no `@pytest.mark.capability(...)` marker either (it reads
            # `result.capabilities` -- the v2 field name -- directly, rather than going through
            # the autouse capability gate), so it never produces the VERSION-MISMATCH: marker
            # text; it still genuinely SKIPs here, just via its own plain
            # `pytest.skip("initialize result has no capabilities object to check")`, since a
            # v1-negotiated result has no `capabilities` key at all (v1 uses `agentCapabilities`
            # instead) -- see `test_extensibility.py`'s module docstring.
            continue
        assert any("VERSION-MISMATCH:" in t["message"] for t in r["tests"]), r["tests"]

    pass_results = [r for r in report["requirements"] if r["id"] in _VERSION_TOLERANT_IDS]
    assert len(pass_results) == len(_VERSION_TOLERANT_IDS)
    for r in pass_results:
        assert r["status"] == "PASS", r
