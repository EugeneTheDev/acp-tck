"""Unit tests for pure helpers in `tck.common.plugin` that don't need a live agent process."""

from __future__ import annotations

from tck.common.plugin import _verdict_reason, capability_is_supported
from tck.common.report import Status, Verdict
from tck.common.requirements import Tier


def _tier_counts(*, mandatory_fail=0, mandatory_not_tested=0, capability_fail=0) -> dict:
    """A minimal `Verdict.tier_counts` shape -- only the MANDATORY/CAPABILITY entries
    `_verdict_reason` reads -- for the given non-zero counts."""
    zero = {status.value: 0 for status in Status}
    return {
        Tier.MANDATORY.value: {
            **zero,
            Status.FAIL.value: mandatory_fail,
            Status.NOT_TESTED.value: mandatory_not_tested,
        },
        Tier.CAPABILITY.value: {**zero, Status.FAIL.value: capability_fail},
    }


# --- object-marker semantics (default: present & non-null) ---


def test_object_marker_present_and_non_null_is_supported() -> None:
    result = {"agentCapabilities": {"mcpCapabilities": {"http": True}}}
    assert capability_is_supported(result, "agentCapabilities.mcpCapabilities") is True


def test_object_marker_empty_object_still_counts_as_supported() -> None:
    result = {"agentCapabilities": {"mcpCapabilities": {}}}
    assert capability_is_supported(result, "agentCapabilities.mcpCapabilities") is True


def test_object_marker_missing_is_not_supported() -> None:
    result = {"agentCapabilities": {}}
    assert capability_is_supported(result, "agentCapabilities.mcpCapabilities") is False


def test_object_marker_explicit_null_is_not_supported() -> None:
    result = {"agentCapabilities": {"mcpCapabilities": None}}
    assert capability_is_supported(result, "agentCapabilities.mcpCapabilities") is False


# --- boolean-gate semantics (boolean=True: only `=== true` counts) ---


def test_boolean_gate_true_is_supported() -> None:
    result = {"agentCapabilities": {"loadSession": True}}
    assert capability_is_supported(result, "agentCapabilities.loadSession", boolean=True) is True


def test_boolean_gate_false_is_not_supported() -> None:
    result = {"agentCapabilities": {"loadSession": False}}
    assert capability_is_supported(result, "agentCapabilities.loadSession", boolean=True) is False


def test_boolean_gate_missing_is_not_supported() -> None:
    result = {"agentCapabilities": {}}
    assert capability_is_supported(result, "agentCapabilities.loadSession", boolean=True) is False


def test_boolean_gate_non_boolean_truthy_value_is_not_supported() -> None:
    # A boolean gate is `=== true`, not merely truthy -- an object or a string there does not count.
    result = {"promptCapabilities": {"image": "yes"}}
    assert capability_is_supported(result, "promptCapabilities.image", boolean=True) is False


def test_nested_path_through_missing_intermediate_object() -> None:
    result = {}
    assert capability_is_supported(result, "agentCapabilities.loadSession", boolean=True) is False
    assert capability_is_supported(result, "agentCapabilities.mcpCapabilities") is False


# --- _verdict_reason: the NOT CONFORMANT reason string ---


def test_verdict_reason_mandatory_failures_only() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(mandatory_fail=3))
    assert _verdict_reason(verdict) == "3 mandatory failures"


def test_verdict_reason_singular_failure() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(mandatory_fail=1))
    assert _verdict_reason(verdict) == "1 mandatory failure"


def test_verdict_reason_mandatory_not_tested_only() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(mandatory_not_tested=21))
    assert _verdict_reason(verdict) == "21 mandatory not tested"


def test_verdict_reason_capability_failure_only() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(capability_fail=1))
    assert _verdict_reason(verdict) == "1 capability failure"


def test_verdict_reason_capability_failures_plural() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(capability_fail=2))
    assert _verdict_reason(verdict) == "2 capability failures"


def test_verdict_reason_mandatory_and_capability_failures_both_listed() -> None:
    verdict = Verdict(
        conformant=False,
        tier_counts=_tier_counts(mandatory_fail=3, mandatory_not_tested=21, capability_fail=1),
    )
    assert (
        _verdict_reason(verdict)
        == "3 mandatory failures, 21 mandatory not tested, 1 capability failure"
    )


def test_verdict_reason_blocked_by_auth() -> None:
    verdict = Verdict(conformant=False, tier_counts=_tier_counts(), blocked_by_auth=True)
    assert _verdict_reason(verdict) == "blocked by authentication"


def test_verdict_reason_blocked_by_version_mismatch() -> None:
    verdict = Verdict(
        conformant=False, tier_counts=_tier_counts(), blocked_by_version_mismatch=True
    )
    assert _verdict_reason(verdict) == "blocked by version mismatch"


def test_verdict_reason_failures_and_version_mismatch_combined() -> None:
    verdict = Verdict(
        conformant=False,
        tier_counts=_tier_counts(mandatory_fail=3, capability_fail=1),
        blocked_by_version_mismatch=True,
    )
    assert (
        _verdict_reason(verdict)
        == "3 mandatory failures, 1 capability failure, blocked by version mismatch"
    )


def test_verdict_reason_degenerate_no_cause_is_honest_not_empty() -> None:
    # Unreachable through `compute_verdict` (non-conformant always implies at least one of these
    # counts/flags is set), but `_verdict_reason` is a pure function of `Verdict` and must not
    # render empty parentheses if ever called with an inconsistent one.
    verdict = Verdict(conformant=False, tier_counts=_tier_counts())
    assert _verdict_reason(verdict) == "no cause recorded"
