"""Unit tests for `tck.report`: aggregation rules over synthetic `TestOutcome`s, the verdict
rule, and `Report.to_dict()`'s JSON round-trip -- no pytest-plugin machinery involved (that is
covered end-to-end by `tests/test_cli.py`).
"""

from __future__ import annotations

import json

import pytest

from tck.report import (
    Report,
    RequirementResult,
    Status,
    TestOutcome,
    Verdict,
    aggregate_status,
    build_requirement_results,
    compute_verdict,
    current_tck_version,
    worse_status,
)
from tck.requirements import REGISTRY, Tier


def _outcome(status: Status, nodeid: str = "mod.py::test") -> TestOutcome:
    return TestOutcome(nodeid=nodeid, status=status, message="", duration_s=0.01)


# --- aggregation ---


def test_aggregate_status_no_records_is_not_tested():
    assert aggregate_status([]) is Status.NOT_TESTED


def test_aggregate_status_all_pass():
    assert aggregate_status([_outcome(Status.PASS), _outcome(Status.PASS)]) is Status.PASS


def test_aggregate_status_all_skipped():
    assert aggregate_status([_outcome(Status.SKIPPED), _outcome(Status.SKIPPED)]) is Status.SKIPPED


def test_aggregate_status_any_fail_wins_over_pass_and_skipped():
    assert (
        aggregate_status([_outcome(Status.PASS), _outcome(Status.SKIPPED), _outcome(Status.FAIL)])
        is Status.FAIL
    )


def test_aggregate_status_pass_wins_over_skipped():
    assert aggregate_status([_outcome(Status.SKIPPED), _outcome(Status.PASS)]) is Status.PASS


def test_worse_status_orders_fail_over_everything():
    assert worse_status(Status.FAIL, Status.PASS) is Status.FAIL
    assert worse_status(Status.PASS, Status.SKIPPED) is Status.PASS
    assert worse_status(Status.SKIPPED, Status.NOT_TESTED) is Status.SKIPPED


def test_a_setup_or_teardown_error_is_reported_as_fail_with_the_exception_text():
    """The report model has no separate ERROR status -- a setup/teardown exception (or a
    harness AgentExited/AgentTimeout propagating out of a test) is folded into FAIL by
    `tck.plugin` before it ever reaches `TestOutcome`; this test locks in that FAIL carries the
    exception text as `message`, which is what a JSON report consumer actually needs to see."""
    outcome = TestOutcome(
        nodeid="mod.py::test_x",
        status=Status.FAIL,
        message="AgentExited: agent process exited while waiting for a line (exit_code=1)",
        duration_s=0.1,
    )
    assert outcome.status is Status.FAIL
    assert "AgentExited" in outcome.message


# --- build_requirement_results ---


def test_build_requirement_results_covers_every_registry_id_including_untested_ones():
    any_id = next(iter(REGISTRY))
    results = build_requirement_results({any_id: [_outcome(Status.PASS)]})
    ids = {result.id for result in results}
    assert ids == set(REGISTRY)
    by_id = {result.id: result for result in results}
    assert by_id[any_id].status is Status.PASS
    other_id = next(i for i in REGISTRY if i != any_id)
    assert by_id[other_id].status is Status.NOT_TESTED
    assert by_id[other_id].tests == []


# --- verdict ---


def _fake_results(overrides: dict[str, Status]) -> list[RequirementResult]:
    """One `RequirementResult` per registry entry, with `overrides` supplying a status for the
    given ids and everything else defaulting to PASS (or NOT_TESTED for CAPABILITY, so tests
    stay independent of which real ids happen to be CAPABILITY-tier)."""
    results = []
    for req_id, requirement in REGISTRY.items():
        status = overrides.get(req_id)
        if status is None:
            status = Status.NOT_TESTED if requirement.tier is Tier.CAPABILITY else Status.PASS
        results.append(
            RequirementResult(
                id=req_id,
                tier=requirement.tier,
                capability=requirement.capability,
                text=requirement.text,
                citation=requirement.citation,
                status=status,
                tests=[],
            )
        )
    return results


def _first_id_of_tier(tier: Tier) -> str | None:
    """`None` if no registry entry has this tier yet (CAPABILITY/INFORMATIONAL land in a later
    slice) -- callers `pytest.skip(...)` in that case rather than asserting on a tier that
    cannot yet occur."""
    return next((req_id for req_id, req in REGISTRY.items() if req.tier is tier), None)


def test_verdict_conformant_when_nothing_mandatory_fails_or_is_untested():
    results = _fake_results({})
    verdict = compute_verdict(results)
    assert verdict.conformant is True


def test_verdict_not_conformant_on_a_mandatory_fail():
    mandatory_id = _first_id_of_tier(Tier.MANDATORY)
    results = _fake_results({mandatory_id: Status.FAIL})
    assert compute_verdict(results).conformant is False


def test_verdict_not_conformant_on_a_mandatory_not_tested():
    mandatory_id = _first_id_of_tier(Tier.MANDATORY)
    results = _fake_results({mandatory_id: Status.NOT_TESTED})
    assert compute_verdict(results).conformant is False


def test_verdict_not_conformant_on_a_capability_fail():
    """A CAPABILITY requirement FAILing *does* break conformance: the agent advertised the
    capability, so it must work."""
    capability_id = _first_id_of_tier(Tier.CAPABILITY)
    if capability_id is None:
        pytest.skip("no CAPABILITY-tier requirement registered yet")
    results = _fake_results({capability_id: Status.FAIL})
    assert compute_verdict(results).conformant is False


def test_verdict_conformant_despite_capability_skipped_or_not_tested():
    """A capability the agent never advertised (SKIPPED) or that simply never ran
    (NOT_TESTED) must not affect the verdict."""
    capability_id = _first_id_of_tier(Tier.CAPABILITY)
    if capability_id is None:
        pytest.skip("no CAPABILITY-tier requirement registered yet")
    for status in (Status.SKIPPED, Status.NOT_TESTED):
        results = _fake_results({capability_id: status})
        assert compute_verdict(results).conformant is True, status


def test_verdict_conformant_despite_advisory_fail():
    advisory_id = _first_id_of_tier(Tier.ADVISORY)
    results = _fake_results({advisory_id: Status.FAIL})
    assert compute_verdict(results).conformant is True


def test_verdict_conformant_despite_informational_fail():
    informational_id = _first_id_of_tier(Tier.INFORMATIONAL)
    if not any(req.tier is Tier.INFORMATIONAL for req in REGISTRY.values()):
        pytest.skip("no INFORMATIONAL-tier requirement registered yet")
    results = _fake_results({informational_id: Status.FAIL})
    assert compute_verdict(results).conformant is True


def test_verdict_tier_counts_add_up_to_the_registry_size_per_tier():
    results = _fake_results({})
    verdict = compute_verdict(results)
    for tier in Tier:
        expected = sum(1 for req in REGISTRY.values() if req.tier is tier)
        assert sum(verdict.tier_counts[tier.value].values()) == expected


# --- Report.to_dict() ---


def _sample_report() -> Report:
    results = _fake_results({})  # all-PASS/NOT_TESTED(capability-only) -> a conformant sample
    return Report(
        tck_version=current_tck_version(),
        protocol_version=1,
        schema_revision="deadbeef",
        agent_command=["python", "agent.py"],
        agent_info={"name": "x", "version": "1"},
        agent_capabilities={},
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        requirements=results,
        verdict=compute_verdict(results),
    )


def test_report_to_dict_has_the_documented_top_level_keys():
    report = _sample_report()
    d = report.to_dict()
    assert set(d) == {
        "tck_version",
        "protocol_version",
        "schema_revision",
        "agent_command",
        "agent_info",
        "agent_capabilities",
        "started_at",
        "finished_at",
        "requirements",
        "verdict",
    }


def test_report_to_dict_round_trips_through_json_dumps():
    report = _sample_report()
    encoded = json.dumps(report.to_dict())
    decoded = json.loads(encoded)
    assert decoded["protocol_version"] == 1
    assert decoded["verdict"]["conformant"] is True
    assert len(decoded["requirements"]) == len(REGISTRY)


def test_every_requirement_in_the_json_report_has_a_valid_status():
    report = _sample_report()
    valid = {status.value for status in Status}
    for requirement in report.to_dict()["requirements"]:
        assert requirement["status"] in valid


def test_report_verdict_is_not_conformant_when_a_registry_id_is_missing_a_record():
    """A registered but never-run requirement (NOT_TESTED, since `build_requirement_results`
    covers the whole registry) counts as a verdict failure -- a dead agent that never gets past
    `initialize` cannot score 100% by starving every other test of a record."""
    results = build_requirement_results({})  # nothing ran at all
    verdict = compute_verdict(results)
    assert verdict.conformant is False
