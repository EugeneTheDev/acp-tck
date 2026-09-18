#!/usr/bin/env python3
"""Render a compact requirement-by-requirement comparison table from two `acp-tck
--report-json` reports (see `scripts/cross-check.sh`). Stdlib only -- no project dependency.

Usage: cross-check-summary.py <left.json> <left-label> <right.json> <right-label>
"""

from __future__ import annotations

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


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(f"usage: {argv[0]} <left.json> <left-label> <right.json> <right-label>", file=sys.stderr)
        return 2

    left_path, left_label, right_path, right_label = argv[1:]
    left = _load(left_path)
    right = _load(right_path)

    left_reqs = _requirements_by_id(left)
    right_reqs = _requirements_by_id(right)
    all_ids = sorted(set(left_reqs) | set(right_reqs))

    id_width = max((len(i) for i in all_ids), default=len("requirement id"))
    id_width = max(id_width, len("requirement id"))
    col_width = max(len(left_label), len(right_label), len("status"))

    header = f"{'requirement id'.ljust(id_width)}  {left_label.ljust(col_width)}  {right_label.ljust(col_width)}"
    print(header)
    print("-" * len(header))
    for req_id in all_ids:
        left_status = left_reqs.get(req_id, {}).get("status", "MISSING")
        right_status = right_reqs.get(req_id, {}).get("status", "MISSING")
        print(f"{req_id.ljust(id_width)}  {left_status.ljust(col_width)}  {right_status.ljust(col_width)}")

    print()
    for label, report in ((left_label, left), (right_label, right)):
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
