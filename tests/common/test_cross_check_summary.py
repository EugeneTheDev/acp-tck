"""Unit tests for `scripts/cross-check-summary.py`'s `--expect-only-mandatory-fail` check.

`scripts/` is not a package (it holds standalone, stdlib-only CLI scripts run via `python3`,
not `uv run pytest` -- see `AGENTS.md` "Cross-checking against upstream agents"), so the module
is loaded directly from its file path via `importlib`, keyed off this test file's own location
so it works regardless of the current working directory.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "cross-check-summary.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("cross_check_summary", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ccs = _load_module()


def _report(requirements: list[dict]) -> dict:
    return {
        "requirements": requirements,
        "verdict": {"conformant": False, "blocked_by_auth": False, "tier_counts": {}},
    }


def _req(req_id: str, tier: str, status: str) -> dict:
    return {"id": req_id, "tier": tier, "status": status}


def test_mandatory_fail_ids_only_counts_mandatory_fail():
    report = _report(
        [
            _req("ACP-INIT-003", "MANDATORY", "FAIL"),
            _req("ACP-INIT-004", "ADVISORY", "FAIL"),
            _req("ACP-SESSION-001", "MANDATORY", "PASS"),
            _req("ACP-CANCEL-001", "MANDATORY", "SKIPPED"),
        ]
    )
    assert ccs.mandatory_fail_ids(report) == {"ACP-INIT-003"}


def test_check_only_mandatory_fail_matches_expected_set(capsys):
    report = _report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])
    ok = ccs.check_only_mandatory_fail(report, "testy", {"ACP-INIT-003"})
    assert ok is True
    assert "OK" in capsys.readouterr().out


def test_check_only_mandatory_fail_flags_unexpected_extra_fail(capsys):
    report = _report(
        [
            _req("ACP-INIT-003", "MANDATORY", "FAIL"),
            _req("ACP-SESSION-001", "MANDATORY", "FAIL"),
        ]
    )
    ok = ccs.check_only_mandatory_fail(report, "echo_agent", {"ACP-INIT-003"})
    assert ok is False
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "ACP-SESSION-001" in err


def test_check_only_mandatory_fail_flags_missing_expected_fail(capsys):
    # Expected ACP-INIT-003 to fail, but this synthetic agent passed it -- also a deviation
    # worth flagging (the whole point is to catch drift in either direction).
    report = _report([_req("ACP-INIT-003", "MANDATORY", "PASS")])
    ok = ccs.check_only_mandatory_fail(report, "some_agent", {"ACP-INIT-003"})
    assert ok is False


def test_main_end_to_end_exits_nonzero_on_unexpected_mandatory_fail(tmp_path: Path, capsys):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(
        json.dumps(
            _report(
                [
                    _req("ACP-INIT-003", "MANDATORY", "FAIL"),
                    _req("ACP-JSONRPC-001", "MANDATORY", "FAIL"),
                ]
            )
        )
    )

    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--expect-only-mandatory-fail",
            "ACP-INIT-003",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "right" in err and "ACP-JSONRPC-001" in err


def test_main_end_to_end_exits_zero_when_expectation_holds(tmp_path: Path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))

    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--expect-only-mandatory-fail",
            "ACP-INIT-003",
        ]
    )
    assert exit_code == 0


def test_main_without_the_flag_still_exits_zero_regardless_of_fails(tmp_path: Path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([])))

    exit_code = ccs.main(["cross-check-summary.py", str(left), "left", str(right), "right"])
    assert exit_code == 0


def test_parse_expect_splits_label_and_id_set():
    label, ids = ccs._parse_expect("python_v2_agent=ACP-BATCH-201,ACP-BATCH-202")
    assert label == "python_v2_agent"
    assert ids == {"ACP-BATCH-201", "ACP-BATCH-202"}


def test_parse_expect_empty_ids_means_zero_expected_fails():
    label, ids = ccs._parse_expect("testy_v2=")
    assert label == "testy_v2"
    assert ids == set()


def test_parse_expect_rejects_missing_equals():
    with pytest.raises(Exception):
        ccs._parse_expect("no-equals-sign")


def test_main_accepts_extra_reports_via_report_flag(tmp_path: Path, capsys):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    extra = tmp_path / "extra.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    extra.write_text(json.dumps(_report([_req("ACP-BATCH-201", "MANDATORY", "FAIL")])))

    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--report",
            str(extra),
            "extra",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "extra" in out
    assert "ACP-BATCH-201" in out


def test_main_per_report_expect_overrides_the_global_default(tmp_path: Path, capsys):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    extra = tmp_path / "extra.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    extra.write_text(json.dumps(_report([_req("ACP-BATCH-201", "MANDATORY", "FAIL")])))

    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--report",
            str(extra),
            "extra",
            "--expect-only-mandatory-fail",
            "ACP-INIT-003",
            "--expect",
            "extra=ACP-BATCH-201",
        ]
    )
    assert exit_code == 0


def test_main_per_report_expect_still_flags_a_genuine_deviation(tmp_path: Path, capsys):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    extra = tmp_path / "extra.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    # "extra" fails something the --expect override doesn't mention -- must still be caught.
    extra.write_text(
        json.dumps(
            _report(
                [
                    _req("ACP-BATCH-201", "MANDATORY", "FAIL"),
                    _req("ACP-SESSION-001", "MANDATORY", "FAIL"),
                ]
            )
        )
    )

    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--report",
            str(extra),
            "extra",
            "--expect-only-mandatory-fail",
            "ACP-INIT-003",
            "--expect",
            "extra=ACP-BATCH-201",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "extra" in err and "ACP-SESSION-001" in err


def test_main_expect_without_the_mandatory_fail_flag_still_checks_named_reports(tmp_path: Path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(_report([_req("ACP-INIT-003", "MANDATORY", "FAIL")])))
    right.write_text(json.dumps(_report([])))

    # No --expect-only-mandatory-fail at all, but "right" gets an explicit --expect: it should
    # still be checked (and pass, since it has no MANDATORY FAILs), while "left" -- which has a
    # real MANDATORY FAIL and no override -- is simply not checked at all.
    exit_code = ccs.main(
        [
            "cross-check-summary.py",
            str(left),
            "left",
            str(right),
            "right",
            "--expect",
            "right=",
        ]
    )
    assert exit_code == 0
