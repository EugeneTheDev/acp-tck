"""Tests for `tck.v2.validation` -- the three v2-specific behaviors called out in its module
docstring: batch root dispatch, no `null` special case for responses, and the open-fallback
carve-out in `find_unknown_root_keys`. Fixtures here are hand-built JSON-RPC messages, not
fixture agents -- unit tests of the validator itself.
"""

from __future__ import annotations

from tck.v2 import protocol
from tck.v2.validation import find_unknown_root_keys, validate_agent_message, validate_agent_response


# --- root dispatch: object / non-empty batch / empty batch ---


def test_valid_initialize_response_passes():
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": 2,
            "capabilities": {},
            "info": {"name": "fixture", "version": "0.0.0"},
        },
    }
    assert validate_agent_response("initialize", msg) == []


def test_empty_batch_array_is_an_issue():
    assert len(validate_agent_message([])) == 1
    assert len(validate_agent_response("initialize", [])) == 1


def test_non_empty_batch_validates_each_element_and_prefixes_the_path():
    good = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": 2,
            "capabilities": {},
            "info": {"name": "fixture", "version": "0.0.0"},
        },
    }
    bad = {"jsonrpc": "2.0", "id": 2, "result": {"capabilities": {}}}  # missing protocolVersion, info
    issues = validate_agent_response("initialize", [good, bad])
    assert len(issues) == 2  # missing protocolVersion, missing info
    assert all(issue.path.startswith("/1") for issue in issues)


# --- no null special case (unlike v1's session/load) ---


def test_null_result_fails_for_an_object_response_schema():
    msg = {"jsonrpc": "2.0", "id": 1, "result": None}
    issues = validate_agent_response("initialize", msg)
    assert issues, "a null result must fail validation against InitializeResponse's object schema"


# --- open-enum discriminator: is_valid_open_enum_value ---


def test_underscore_prefixed_stop_reason_is_a_valid_extension():
    assert protocol.is_valid_open_enum_value("_custom_stop", protocol.STOP_REASONS)


def test_unknown_non_underscore_stop_reason_is_rejected():
    assert not protocol.is_valid_open_enum_value("something_new", protocol.STOP_REASONS)


def test_defined_stop_reason_is_valid():
    assert protocol.is_valid_open_enum_value("end_turn", protocol.STOP_REASONS)


# --- find_unknown_root_keys: named branch vs. open "other" fallback carve-out ---


def test_unknown_key_on_a_named_branch_is_flagged():
    named = {"type": "terminal", "methodId": "m1", "bogus": True}
    assert find_unknown_root_keys("AuthMethod", named) == ["bogus"]


def test_extra_fields_on_the_open_fallback_branch_are_not_flagged():
    """`AuthMethod`'s `"other"` branch is the open, custom/future-method fallback: an object
    whose `type` doesn't match any named branch's `const` is presumed to be legitimately using
    it, so its extra fields (which the schema deliberately does not enumerate for that case) are
    not flagged as unknown."""
    other = {"type": "_custom_method", "methodId": "m1", "customField": "abc"}
    assert find_unknown_root_keys("AuthMethod", other) == []


def test_unknown_key_on_a_plain_object_def_is_still_flagged():
    assert find_unknown_root_keys("InitializeResponse", {"protocolVersion": 2, "bogus": True}) == [
        "bogus"
    ]
