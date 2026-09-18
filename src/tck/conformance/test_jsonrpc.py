"""JSON-RPC envelope conformance: ACP-JSONRPC-001..005.

Not listed by name in the slice-3 task's conformance-tests file list (which named only
`test_transport.py` / `test_initialize.py`), but the task's own bullet points describe a
distinct "jsonrpc:" group of assertions; splitting them into their own module keeps each file
focused on one requirement family. See `AGENTS.md` "How to add a requirement + test".
"""

from __future__ import annotations

import pytest

from tck.harness import AgentTimeout
from tck.protocol import METHOD_NOT_FOUND, PROTOCOL_VERSION

from ._helpers import connected_agent


@pytest.mark.requirement("ACP-JSONRPC-001")
async def test_id_is_echoed_for_integer_and_string_ids(agent_launch):
    """ACP-JSONRPC-001."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        params = {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}

        int_id = await agent.send_request("initialize", params, id=424242)
        int_entry = await agent.wait_for_response(int_id, timeout=agent_launch.default_timeout)
        assert int_entry.parsed["id"] == 424242, f"integer id not echoed: {int_entry.parsed!r}"

        str_id = await agent.send_request("initialize", params, id="tck-string-id")
        str_entry = await agent.wait_for_response(str_id, timeout=agent_launch.default_timeout)
        assert str_entry.parsed["id"] == "tck-string-id", f"string id not echoed: {str_entry.parsed!r}"


@pytest.mark.requirement("ACP-JSONRPC-002")
async def test_unknown_method_response_is_result_xor_error_with_valid_shape(agent_launch):
    """ACP-JSONRPC-002."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("tck/does_not_exist")
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict), f"response did not parse to a JSON object: {entry.raw!r}"

        has_result = "result" in msg
        has_error = "error" in msg
        assert has_result != has_error, f"response must have exactly one of result/error: {msg!r}"

        if has_error:
            error = msg["error"]
            assert isinstance(error, dict), f"error must be an object: {error!r}"
            code = error.get("code")
            assert isinstance(code, int) and not isinstance(code, bool), f"error.code must be an integer: {code!r}"
            message = error.get("message")
            assert isinstance(message, str), f"error.message must be a string: {message!r}"


@pytest.mark.requirement("ACP-JSONRPC-004")
async def test_unknown_method_yields_method_not_found(agent_launch):
    """ACP-JSONRPC-004 (ADVISORY -- spec wording is "should")."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("tck/does_not_exist")
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        error = entry.parsed.get("error") if isinstance(entry.parsed, dict) else None
        assert error is not None, f"expected an error response, got {entry.parsed!r}"
        assert error.get("code") == METHOD_NOT_FOUND, f"expected -32601, got {error.get('code')!r}"


@pytest.mark.requirement("ACP-JSONRPC-003")
async def test_notification_receives_no_response(agent_launch, tmp_path):
    """ACP-JSONRPC-003. `session/cancel` with no prompt in flight is a pure notification.

    This also stands in for a would-be `ACP-CANCEL-003` ("`session/cancel` itself is a
    notification and receives no response", J2 applied to cancel): the slice-4 task considered
    a dedicated requirement id for that, but it is exactly what this test already asserts, so no
    separate id was registered -- see `.agents/plan.md` slice 4 notes."""
    async with connected_agent(agent_launch) as agent:
        session_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        session_entry = await agent.wait_for_response(session_req, timeout=agent_launch.default_timeout)
        session_id = session_entry.parsed["result"]["sessionId"]

        await agent.send_notification("session/cancel", {"sessionId": session_id})

        def _is_a_response(entry) -> bool:
            return isinstance(entry.parsed, dict) and "id" in entry.parsed and (
                "result" in entry.parsed or "error" in entry.parsed
            )

        with pytest.raises(AgentTimeout):
            await agent.wait_for_message(_is_a_response, timeout=1.0)


@pytest.mark.requirement("ACP-JSONRPC-005")
async def test_connection_survives_an_erroneous_request(agent_launch, tmp_path):
    """ACP-JSONRPC-005 (ADVISORY -- see `tck.requirements` for why this isn't MANDATORY)."""
    async with connected_agent(agent_launch) as agent:
        bad_id = await agent.send_request("tck/does_not_exist")
        await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)

        session_req = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        entry = await agent.wait_for_response(session_req, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert "result" in msg, f"request after an error must still succeed: {msg!r}"
        assert isinstance(msg["result"].get("sessionId"), str)
