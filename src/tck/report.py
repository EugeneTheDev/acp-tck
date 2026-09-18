"""The report model: per-test outcomes aggregated into per-requirement status, plus the
overall verdict, serialized as a plain JSON-serializable dict.

`tck.plugin` is the only producer (it collects `TestOutcome`s from pytest hooks and builds a
`Report` at `pytest_sessionfinish`); this module has no pytest dependency so it can be unit
tested with synthetic data (`tests/test_report.py`).

Model (`.agents/plan.md` "Decided deliverable shape", four-status verdict model):

- `Status`: `PASS` / `FAIL` / `SKIPPED` / `NOT_TESTED`. Only `PASS`/`FAIL`/`SKIPPED` are ever
  recorded for an individual test; `NOT_TESTED` only ever appears as the *aggregated* status of
  a registered requirement id that no test bound to during the run.
- Aggregating a requirement's bound `TestOutcome`s into one `Status`: any `FAIL` wins; else any
  `PASS` wins; else any `SKIPPED` wins; zero records -> `NOT_TESTED`.
- A test that errors -- a setup/teardown exception, or a harness `AgentExited`/`AgentTimeout`
  propagating out of the test body -- counts as `FAIL` for every requirement it is bound to, with
  the exception text as the outcome's `message`. There is no separate "ERROR" status; it folds
  into `FAIL` (pytest itself already reports these as `failed` results at the `setup`/`call`/
  `teardown` phase, which is where `tck.plugin` reads them from).
- `Verdict.conformant` is computed from `MANDATORY`- and `CAPABILITY`-tier requirements only:
  `True` iff there is no `MANDATORY` `FAIL`, no `MANDATORY` `NOT_TESTED`, and no `CAPABILITY`
  `FAIL`. `CAPABILITY` `SKIPPED`/`NOT_TESTED` (capability not advertised, or simply never
  exercised) do not affect it -- only a *failed* capability check does, since the agent
  advertised the capability and it must then work. `ADVISORY`/`INFORMATIONAL` never affect it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Any

from .requirements import REGISTRY, Tier


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    NOT_TESTED = "NOT_TESTED"


STATUS_PRIORITY: dict[Status, int] = {
    Status.FAIL: 0,
    Status.PASS: 1,
    Status.SKIPPED: 2,
    Status.NOT_TESTED: 3,
}
"""Lower wins when aggregating several statuses into one (`FAIL` > `PASS` > `SKIPPED` >
`NOT_TESTED`). Shared with `tck.plugin`, which uses it to fold multiple pytest phases (setup /
call / teardown) for the same test into a single `TestOutcome`."""


def worse_status(a: Status, b: Status) -> Status:
    """The more severe of two statuses, by `STATUS_PRIORITY`."""
    return a if STATUS_PRIORITY[a] <= STATUS_PRIORITY[b] else b


@dataclass(frozen=True)
class TestOutcome:
    """One test's contribution to whatever requirement(s) it is bound to."""

    __test__ = False  # not a pytest test class despite the name -- silence collection warnings

    nodeid: str
    status: Status
    message: str
    duration_s: float
    properties: dict[str, str] = field(default_factory=dict)
    """`record_property(...)` values recorded during the test (e.g.
    `acp_tck_cancel_race_ms`)."""
    transcript: list[dict[str, Any]] | None = None
    """`[{"dir": "sent"|"received", "t": <monotonic timestamp>, "raw": <text>}, ...]` for the
    agent process(es) active during the test -- only populated for `FAIL` outcomes."""
    stderr: str | None = None
    """The agent's captured stderr, truncated to the last 20 kB -- only populated for `FAIL`
    outcomes."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeid": self.nodeid,
            "status": self.status.value,
            "message": self.message,
            "duration_s": self.duration_s,
            "properties": dict(self.properties),
            "transcript": self.transcript,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class RequirementResult:
    """One registry requirement, its aggregated status, and every test bound to it."""

    id: str
    tier: Tier
    capability: str | None
    text: str
    citation: str
    status: Status
    tests: list[TestOutcome]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "capability": self.capability,
            "text": self.text,
            "citation": self.citation,
            "status": self.status.value,
            "tests": [test.to_dict() for test in self.tests],
        }


def aggregate_status(tests: list[TestOutcome]) -> Status:
    """A requirement's status from the tests bound to it: worst-of, or `NOT_TESTED` if empty."""
    if not tests:
        return Status.NOT_TESTED
    result = tests[0].status
    for test in tests[1:]:
        result = worse_status(result, test.status)
    return result


def build_requirement_results(tests_by_id: dict[str, list[TestOutcome]]) -> list[RequirementResult]:
    """One `RequirementResult` per `REGISTRY` entry (including ids no test ever ran), sorted by
    id, aggregating `tests_by_id.get(id, [])`."""
    results = []
    for req_id in sorted(REGISTRY):
        requirement = REGISTRY[req_id]
        tests = tests_by_id.get(req_id, [])
        results.append(
            RequirementResult(
                id=req_id,
                tier=requirement.tier,
                capability=requirement.capability,
                text=requirement.text,
                citation=requirement.citation,
                status=aggregate_status(tests),
                tests=tests,
            )
        )
    return results


@dataclass(frozen=True)
class Verdict:
    conformant: bool
    tier_counts: dict[str, dict[str, int]]
    """`tier.value -> status.value -> count`, over every `RequirementResult` (not test)."""
    blocked_by_auth: bool = False
    """`True` if at least one test was SKIPPED because the agent requires authentication before
    `session/new` and no `--auth-method` was configured (see
    `tck.conformance._helpers.skip_if_auth_gated`). Such a run cannot claim conformance --
    mandatory/capability requirements that depend on a session were never actually exercised,
    even though they show up as an ordinary SKIPPED rather than FAIL/NOT_TESTED -- so
    `conformant` is forced `False` whenever this is set, regardless of the tier counts."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conformant": self.conformant,
            "tier_counts": {tier: dict(counts) for tier, counts in self.tier_counts.items()},
            "blocked_by_auth": self.blocked_by_auth,
        }


def compute_verdict(results: list[RequirementResult], *, blocked_by_auth: bool = False) -> Verdict:
    tier_counts: dict[str, dict[str, int]] = {
        tier.value: {status.value: 0 for status in Status} for tier in Tier
    }
    for result in results:
        tier_counts[result.tier.value][result.status.value] += 1

    mandatory = tier_counts[Tier.MANDATORY.value]
    capability = tier_counts[Tier.CAPABILITY.value]
    conformant = (
        mandatory[Status.FAIL.value] == 0
        and mandatory[Status.NOT_TESTED.value] == 0
        and capability[Status.FAIL.value] == 0
        and not blocked_by_auth
    )
    return Verdict(conformant=conformant, tier_counts=tier_counts, blocked_by_auth=blocked_by_auth)


def current_tck_version() -> str:
    try:
        return _pkg_version("acp-tck")
    except PackageNotFoundError:
        return "0.0.0+unknown"


@dataclass(frozen=True)
class Report:
    tck_version: str
    protocol_version: int
    schema_revision: str
    agent_command: list[str]
    agent_info: dict[str, Any] | None
    agent_capabilities: dict[str, Any] | None
    started_at: str
    finished_at: str
    requirements: list[RequirementResult]
    verdict: Verdict

    def to_dict(self) -> dict[str, Any]:
        return {
            "tck_version": self.tck_version,
            "protocol_version": self.protocol_version,
            "schema_revision": self.schema_revision,
            "agent_command": list(self.agent_command),
            "agent_info": self.agent_info,
            "agent_capabilities": self.agent_capabilities,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "requirements": [result.to_dict() for result in self.requirements],
            "verdict": self.verdict.to_dict(),
        }
