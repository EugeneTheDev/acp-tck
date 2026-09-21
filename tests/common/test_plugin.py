"""Unit tests for pure helpers in `tck.common.plugin` that don't need a live agent process."""

from __future__ import annotations

from tck.common.plugin import capability_is_supported


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
