#!/usr/bin/env python3
"""Render a compact requirement-by-requirement comparison table from two or more `acp-tck
--report-json` reports (see `scripts/cross-check.sh`). Stdlib only -- no project dependency.

Usage:
  cross-check-summary.py <left.json> <left-label> <right.json> <right-label>
                          [--report <path> <label> ...]
                          [--expect-only-mandatory-fail ID [ID ...]]
                          [--expect LABEL=ID,ID,...]

The two positional (path, label) pairs are always required (e.g. the v1 testy/echo_agent leg).
`--report PATH LABEL` may be repeated to add further reports to the same comparison table --
e.g. the v2 testy/python_v2_agent legs -- so a single invocation can print all four side by side.

`--expect-only-mandatory-fail` sets the *default* expected set of MANDATORY-tier FAIL ids
(order-independent) for every report that doesn't have a more specific `--expect` override --
e.g. `--expect-only-mandatory-fail ACP-INIT-003` asserts that the only MANDATORY FAIL in each
report is ACP-INIT-003. Passing no ids after the flag asserts zero MANDATORY FAILs by default.

`--expect LABEL=ID,ID,...` (repeatable) overrides that default for one specific report by
label -- needed because the v1 and v2 legs have different expected upstream baselines (e.g.
`echo_agent (1.0.0rc1)=ACP-INIT-003` vs `python_v2_agent=ACP-BATCH-201,ACP-BATCH-202,...`).
`LABEL=` (an empty id list) asserts zero MANDATORY FAILs for that report. A report with
neither a `--expect` override nor `--expect-only-mandatory-fail` given is not checked at all.

Checking is opt-in and per-report. For each report, its set of MANDATORY-tier requirement ids whose aggregated status is
FAIL is compared against one *expected* id set, and fails loudly if the two sets differ in either direction -- an
unexpected extra MANDATORY FAIL, or an expected one that didn't happen, both count as a deviation.
Which expected set (if any) applies to a given report is resolved like this:

Example:
`--expect-only-mandatory-fail ACP-INIT-003` means "every report without its own `--expect`
override must FAIL exactly `ACP-INIT-003` among MANDATORY requirements, and nothing else."
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


def _parse_expect(spec: str) -> tuple[str, set[str]]:
    """Parse one `--expect LABEL=ID,ID,...` argument. `LABEL=` (empty right-hand side) means
    "expect zero MANDATORY FAILs for this report"."""
    if "=" not in spec:
        raise argparse.ArgumentTypeError(f"--expect value must be LABEL=ID,ID,... (got {spec!r})")
    label, _, ids = spec.partition("=")
    if not label:
        raise argparse.ArgumentTypeError(f"--expect value must start with a non-empty LABEL= (got {spec!r})")
    return label, {i for i in ids.split(",") if i}


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
        "--report",
        nargs=2,
        metavar=("PATH", "LABEL"),
        action="append",
        default=[],
        help="add another report to the comparison table (repeatable)",
    )
    parser.add_argument(
        "--expect-only-mandatory-fail",
        nargs="*",
        default=None,
        metavar="ID",
        help="default expected MANDATORY-tier FAIL id set for any report without a more "
        "specific --expect override",
    )
    parser.add_argument(
        "--expect",
        metavar="LABEL=ID,ID,...",
        action="append",
        default=[],
        type=_parse_expect,
        help="expected MANDATORY-tier FAIL id set for one specific report, by label "
        "(repeatable; overrides --expect-only-mandatory-fail for that label)",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 2)

    reports: list[tuple[str, dict]] = [
        (args.left_label, _load(args.left_path)),
        (args.right_label, _load(args.right_path)),
    ]
    for path, label in args.report:
        reports.append((label, _load(path)))

    reqs_by_report = [(label, _requirements_by_id(report)) for label, report in reports]
    all_ids = sorted(set().union(*(set(reqs) for _, reqs in reqs_by_report)))

    id_width = max((len(i) for i in all_ids), default=len("requirement id"))
    id_width = max(id_width, len("requirement id"))
    col_width = max((len(label) for label, _ in reports), default=0)
    col_width = max(col_width, len("status"))

    header = f"{'requirement id'.ljust(id_width)}  " + "  ".join(
        label.ljust(col_width) for label, _ in reports
    )
    print(header)
    print("-" * len(header))
    for req_id in all_ids:
        cells = [reqs.get(req_id, {}).get("status", "MISSING") for _, reqs in reqs_by_report]
        print(f"{req_id.ljust(id_width)}  " + "  ".join(c.ljust(col_width) for c in cells))

    print()
    for label, report in reports:
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

    per_label_expect: dict[str, set[str]] = dict(args.expect)
    if args.expect_only_mandatory_fail is not None or per_label_expect:
        default_expected = set(args.expect_only_mandatory_fail or [])
        print()
        all_ok = True
        for label, report in reports:
            if label in per_label_expect:
                expected = per_label_expect[label]
            elif args.expect_only_mandatory_fail is not None:
                expected = default_expected
            else:
                continue
            all_ok = check_only_mandatory_fail(report, label, expected) and all_ok
        if not all_ok:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
