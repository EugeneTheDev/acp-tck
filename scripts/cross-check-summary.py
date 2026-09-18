#!/usr/bin/env python3
"""Render a compact requirement-by-requirement comparison table from two `acp-tck
--report-json` reports (see `scripts/cross-check.sh`). Stdlib only -- no project dependency.

Usage:
  cross-check-summary.py <left.json> <left-label> <right.json> <right-label>
                          [--expect-only-mandatory-fail ID [ID ...]]

`--expect-only-mandatory-fail` checks, for *each* report, that the set of MANDATORY-tier
requirements with status FAIL is exactly the given id set (order-independent) -- e.g.
`--expect-only-mandatory-fail ACP-INIT-003` asserts that the only MANDATORY FAIL in each
report is ACP-INIT-003, and exits 1 (after printing the table) if either report has a
different set of MANDATORY FAILs. Passing no ids after the flag asserts zero MANDATORY FAILs.
"""

from __future__ import annotations

import argparse
import json
import sys


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"_error": str(exc)}


def _requirements_by_id(report: dict) -> dict[str, dict]:
    return {r["id"]: r for r in report.get("requirements", [])}


def mandatory_fail_ids(report: dict) -> set[str]:
    """The set of MANDATORY-tier requirement ids with aggregated status FAIL."""
    return {
        r["id"]
        for r in report.get("requirements", [])
        if r.get("tier") == "MANDATORY" and r.get("status") == "FAIL"
    }


def check_only_mandatory_fail(report: dict, label: str, expected_ids: set[str]) -> bool:
    """Print a one-line verdict for `label` and return whether its MANDATORY FAILs are
    exactly `expected_ids`. A report that failed to load (`_error`) always fails the check.
    """
    if "_error" in report:
        print(f"{label}: FAIL -- could not read report ({report['_error']})", file=sys.stderr)
        return False

    actual_ids = mandatory_fail_ids(report)
    if actual_ids != expected_ids:
        print(
            f"{label}: FAIL -- expected MANDATORY FAIL(s) {sorted(expected_ids) or '(none)'}, "
            f"got {sorted(actual_ids) or '(none)'}",
            file=sys.stderr,
        )
        return False

    print(f"{label}: OK -- only MANDATORY FAIL(s): {sorted(expected_ids) or '(none)'}")
    return True


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=argv[0] if argv else "cross-check-summary.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("left_path")
    parser.add_argument("left_label")
    parser.add_argument("right_path")
    parser.add_argument("right_label")
    parser.add_argument(
        "--expect-only-mandatory-fail",
        nargs="*",
        default=None,
        metavar="ID",
        help="assert the only MANDATORY-tier FAIL(s) in each report are exactly these ids",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 2)

    left = _load(args.left_path)
    right = _load(args.right_path)

    left_reqs = _requirements_by_id(left)
    right_reqs = _requirements_by_id(right)
    all_ids = sorted(set(left_reqs) | set(right_reqs))

    id_width = max((len(i) for i in all_ids), default=len("requirement id"))
    id_width = max(id_width, len("requirement id"))
    col_width = max(len(args.left_label), len(args.right_label), len("status"))

    header = (
        f"{'requirement id'.ljust(id_width)}  "
        f"{args.left_label.ljust(col_width)}  {args.right_label.ljust(col_width)}"
    )
    print(header)
    print("-" * len(header))
    for req_id in all_ids:
        left_status = left_reqs.get(req_id, {}).get("status", "MISSING")
        right_status = right_reqs.get(req_id, {}).get("status", "MISSING")
        print(f"{req_id.ljust(id_width)}  {left_status.ljust(col_width)}  {right_status.ljust(col_width)}")

    print()
    for label, report in ((args.left_label, left), (args.right_label, right)):
        if "_error" in report:
            print(f"{label}: could not read report ({report['_error']})")
            continue
        verdict = report.get("verdict", {})
        conformant = verdict.get("conformant")
        blocked = verdict.get("blocked_by_auth")
        tier_counts = verdict.get("tier_counts", {})
        verdict_text = "CONFORMANT" if conformant else "NOT CONFORMANT"
        print(
            f"{label}: VERDICT: {verdict_text} (blocked_by_auth={blocked}) "
            f"tier_counts={tier_counts}"
        )

    if args.expect_only_mandatory_fail is not None:
        expected = set(args.expect_only_mandatory_fail)
        print()
        left_ok = check_only_mandatory_fail(left, args.left_label, expected)
        right_ok = check_only_mandatory_fail(right, args.right_label, expected)
        if not (left_ok and right_ok):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
