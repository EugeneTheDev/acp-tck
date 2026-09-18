"""The authentication surface: `authMethods` shape, the terminal-method client-capability
gate, the `authenticate`/`session/new` flow, and `logout`
(ACP-AUTH-001/002/003/004).

See `.agents/research/acp-v1-authentication.md` for the full tiered assertion list this module
draws from. Deliberately not asserted here (the report's "must NOT" list): that a non-empty
`authMethods` implies `session/new` fails with `-32000` before authentication (v1: MAY, not
MUST -- `testy` itself does not enforce it), and nothing about session state after `logout`.
"""

from __future__ import annotations

import pytest

from tck.plugin import current_auth_method_id

from ._helpers import connected_agent


@pytest.mark.requirement("ACP-AUTH-001")
async def test_auth_methods_have_unique_ids(agent_launch):
    """ACP-AUTH-001. Schema-shape validation of the whole `initialize` result (including
    `authMethods`) is already covered by ACP-SCHEMA-001; this test adds the id-uniqueness check
    that schema validation alone cannot express."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not succeed: {entry.text!r}"
        )
        auth_methods = msg["result"].get("authMethods")
        if not auth_methods:
            return  # nothing to check -- vacuously true, per "authMethods (if present)"
        assert isinstance(auth_methods, list)
        ids = [method.get("id") for method in auth_methods if isinstance(method, dict)]
        assert len(ids) == len(set(ids)), f"authMethods ids are not unique: {ids!r}"


@pytest.mark.requirement("ACP-AUTH-002")
async def test_no_terminal_auth_method_without_client_capability(agent_launch):
    """ACP-AUTH-002 (Req 23). Connects with `clientCapabilities: {}` explicitly (no
    `auth.terminal`) and asserts no `authMethods[*].type == "terminal"` is advertised."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not succeed: {entry.text!r}"
        )
        auth_methods = msg["result"].get("authMethods") or []
        terminal_methods = [
            method for method in auth_methods if isinstance(method, dict) and method.get("type") == "terminal"
        ]
        assert not terminal_methods, (
            "agent advertised authMethods[*].type == 'terminal' without the client advertising "
            f"clientCapabilities.auth.terminal: {terminal_methods!r}"
        )


@pytest.mark.requirement("ACP-AUTH-003")
async def test_authenticate_then_session_new_succeeds(agent_launch, tmp_path):
    """ACP-AUTH-003. Only exercised when `authMethods` is non-empty AND `--tck-auth-method` was
    given -- SKIPs otherwise, since the TCK cannot guess a valid `methodId` and v1 never
    requires a testable auth flow to exist."""
    method_id = current_auth_method_id()
    if method_id is None:
        pytest.skip("no --tck-auth-method given; cannot exercise the authenticate flow")

    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        init_entry = await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)
        init_msg = init_entry.parsed
        assert isinstance(init_msg, dict) and isinstance(init_msg.get("result"), dict), (
            f"initialize did not succeed: {init_entry.text!r}"
        )
        auth_methods = init_msg["result"].get("authMethods") or []
        if not auth_methods:
            pytest.skip("agent advertises no authMethods; nothing to authenticate against")

        auth_id = await agent.send_request("authenticate", {"methodId": method_id})
        auth_entry = await agent.wait_for_response(auth_id, timeout=agent_launch.default_timeout)
        auth_msg = auth_entry.parsed
        assert isinstance(auth_msg, dict) and isinstance(auth_msg.get("result"), dict), (
            f"authenticate with methodId={method_id!r} did not succeed: {auth_entry.text!r}"
        )

        session_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        session_entry = await agent.wait_for_response(session_id, timeout=agent_launch.default_timeout)
        session_msg = session_entry.parsed
        assert isinstance(session_msg, dict) and "error" not in session_msg, (
            f"session/new failed after a successful authenticate: {session_entry.text!r}"
        )
        assert isinstance(session_msg.get("result"), dict), (
            f"session/new did not return a result object after authenticate: {session_entry.text!r}"
        )


@pytest.mark.requirement("ACP-AUTH-004")
@pytest.mark.capability("agentCapabilities.auth.logout")
async def test_logout_succeeds(agent_launch):
    """ACP-AUTH-004. If `--tck-auth-method` was given, `connected_agent`'s handshake has
    already authenticated -- `logout` is then called on that authenticated connection.
    Otherwise it's called standalone; only its own success is checked (nothing about session
    state after logout, per the must-NOT list)."""
    async with connected_agent(agent_launch) as agent:
        req_id = await agent.send_request("logout", {})
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"logout did not succeed with an object result: {entry.text!r}"
        )
