"""Tests for `tck.v1.protocol` method inventories and `tck.v1.validation` schema checks.

Fixtures used here are hand-built JSON-RPC messages, not fixture *agents* -- these are unit
tests of the validator itself, not conformance tests of an agent under test.
"""

from __future__ import annotations

import asyncio

from tck.common.harness import AgentProcess
from tck.v1 import protocol, validation
from tck.v1.validation import validate_agent_message, validate_agent_response

from conftest import agent_launch

# --- initialize response ---


def test_valid_initialize_response_passes() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": 1,
            "agentCapabilities": {},
            "agentInfo": {"name": "fixture", "version": "0.0.0"},
        },
    }
    assert validate_agent_response("initialize", msg) == []


def test_initialize_response_missing_protocol_version_fails_with_pointed_issue() -> None:
    msg = {"jsonrpc": "2.0", "id": 1, "result": {"agentCapabilities": {}}}
    issues = validate_agent_response("initialize", msg)
    assert len(issues) == 1
    assert "protocolVersion" in issues[0].message


def test_response_with_both_result_and_error_fails() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": 1},
        "error": {"code": -32603, "message": "boom"},
    }
    issues = validate_agent_response("initialize", msg)
    assert any("both" in issue.message for issue in issues)


def test_response_with_neither_result_nor_error_fails() -> None:
    msg = {"jsonrpc": "2.0", "id": 1}
    issues = validate_agent_response("initialize", msg)
    assert any("exactly one of" in issue.message for issue in issues)


def test_error_response_with_string_code_fails() -> None:
    msg = {"jsonrpc": "2.0", "id": 1, "error": {"code": "-32700", "message": "bad json"}}
    issues = validate_agent_response("initialize", msg)
    assert any("code" in issue.path and "integer" in issue.message for issue in issues)


# --- session/update notifications ---


def test_session_update_agent_message_chunk_passes() -> None:
    msg = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hi"},
            },
        },
    }
    assert validate_agent_message(msg) == []


def test_session_update_unknown_kind_fails() -> None:
    msg = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": "sess-1", "update": {"sessionUpdate": "not_a_real_kind"}},
    }
    issues = validate_agent_message(msg)
    assert issues


def test_current_mode_update_with_current_mode_id_passes() -> None:
    """Locks in the schema-wins decision for Discrepancy 1: the schema requires
    `currentModeId`, even though some docs pages say `modeId`."""
    msg = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {"sessionUpdate": "current_mode_update", "currentModeId": "mode-a"},
        },
    }
    assert validate_agent_message(msg) == []


def test_current_mode_update_with_mode_id_fails() -> None:
    msg = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {"sessionUpdate": "current_mode_update", "modeId": "mode-a"},
        },
    }
    issues = validate_agent_message(msg)
    assert issues


# --- agent -> client requests ---


def test_request_permission_params_valid() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session/request_permission",
        "params": {
            "sessionId": "sess-1",
            "toolCall": {"toolCallId": "tc-1"},
            "options": [{"optionId": "opt-1", "name": "Allow", "kind": "allow_once"}],
        },
    }
    assert validate_agent_message(msg) == []


def test_request_permission_params_invalid() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session/request_permission",
        "params": {"sessionId": "sess-1"},
    }
    issues = validate_agent_message(msg)
    assert issues
    missing = {issue.message for issue in issues}
    assert any("toolCall" in message for message in missing)
    assert any("options" in message for message in missing)


def test_read_text_file_params_valid() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "fs/read_text_file",
        "params": {"sessionId": "sess-1", "path": "/tmp/a.txt"},
    }
    assert validate_agent_message(msg) == []


# --- documented quirks (Discrepancy 3: null vs {} responses) ---


def test_session_load_response_null_is_tolerated() -> None:
    msg = {"jsonrpc": "2.0", "id": 1, "result": None}
    assert validate_agent_response("session/load", msg) == []


def test_session_load_response_empty_object_is_tolerated() -> None:
    msg = {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert validate_agent_response("session/load", msg) == []


# --- _meta and unknown root fields ---


def test_meta_field_round_trip_passes() -> None:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": 1, "_meta": {"traceparent": "00-abc-def-01"}},
    }
    assert validate_agent_response("initialize", msg) == []


def test_unknown_root_field_is_permitted_by_the_vendored_schema() -> None:
    """The spec's docs (extensibility.mdx) say implementations MUST NOT add custom root
    fields to a spec type, but the vendored JSON Schema itself never sets
    `additionalProperties: false` anywhere (checked: zero occurrences in schema.json), so it
    cannot enforce this. Document the gap rather than assert a rejection the schema does not
    actually produce.
    """
    msg = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": 1, "bogusRootField": True}}
    assert validate_agent_response("initialize", msg) == []


# --- ACP-SCHEMA-002: hand-written unknown-root-key comparison ---


def test_find_unknown_root_keys_flags_a_bogus_field_the_schema_cannot_reject() -> None:
    """Direct counterpart to `test_unknown_root_field_is_permitted_by_the_vendored_schema`
    above: `find_unknown_root_keys` catches exactly what plain jsonschema validation cannot,
    since the vendored schema has no `additionalProperties: false` anywhere."""
    obj = {"protocolVersion": 1, "bogusRootField": True}
    assert validation.find_unknown_root_keys("InitializeResponse", obj) == ["bogusRootField"]


def test_find_unknown_root_keys_permits_known_fields_and_meta() -> None:
    obj = {"protocolVersion": 1, "agentCapabilities": {}, "_meta": {"tck": True}}
    assert validation.find_unknown_root_keys("InitializeResponse", obj) == []


def test_find_unknown_root_keys_on_a_union_type_permits_each_variants_own_fields() -> None:
    """`ContentBlock` is a `oneOf` union of variants (`TextContent`, `ImageContent`, ...), each
    carrying its own `type` const plus its own detail fields (e.g. `TextContent`'s `text`,
    `annotations`) via an `allOf` `$ref` -- `_allowed_root_properties` must walk `oneOf`/`allOf`
    and union every variant's properties, not just the first branch it finds."""
    valid = {"type": "text", "text": "hi"}
    assert validation.find_unknown_root_keys("ContentBlock", valid) == []

    invalid = {"type": "text", "text": "hi", "extraKey": "nope"}
    assert validation.find_unknown_root_keys("ContentBlock", invalid) == ["extraKey"]


def test_find_unknown_root_keys_on_a_scalar_union_skips_the_check() -> None:
    """`RequestId` (`null | integer | string`) has no `properties` anywhere in its `anyOf`
    branches -- there is nothing meaningful to compare an object's keys against, so the check
    must skip (return `[]`) rather than flag every key as unknown."""
    assert validation._allowed_root_properties("RequestId") is None
    assert validation.find_unknown_root_keys("RequestId", {"anything": 1}) == []


def test_find_unknown_root_keys_on_a_non_dict_object_returns_empty() -> None:
    assert validation.find_unknown_root_keys("InitializeResponse", None) == []
    assert validation.find_unknown_root_keys("InitializeResponse", "not a dict") == []


# --- registry completeness ---


def test_every_agent_method_has_a_resolvable_schema() -> None:
    """Every method the agent must handle (`AGENT_METHODS`) either has a response schema
    (it's a request) or is a known notification (`AGENT_NOTIFICATIONS`) -- either way the
    validator must be able to resolve it."""
    response_defs = validation._response_method_defs()
    for method in protocol.AGENT_METHODS:
        assert method in response_defs or method in protocol.AGENT_NOTIFICATIONS, method


def test_every_client_method_has_a_resolvable_schema() -> None:
    """Every method the client must handle (`CLIENT_METHODS`) has a params schema resolvable
    via the x-method annotations (it's something the agent can legitimately send)."""
    request_and_notification_defs = validation._request_and_notification_method_defs()
    for method in protocol.CLIENT_METHODS:
        assert method in request_and_notification_defs, method


# --- harness integration ---


def test_conforming_fixture_initialize_response_validates_clean() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            req_id = await agent.send_request(
                "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
            )
            entry = await agent.wait_for_response(req_id)
            assert validate_agent_response("initialize", entry.parsed) == []

    asyncio.run(scenario())
