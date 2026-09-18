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

from ._helpers import connected_agent, new_session


@pytest.mark.requirement("ACP-AUTH-001")
async def test_auth_methods_have_unique_ids(agent_initialize_result):
    """ACP-AUTH-001. Schema-shape validation of the whole `initialize` result (including
    `authMethods`) is already covered by ACP-SCHEMA-001; this test adds the id-uniqueness check
    that schema validation alone cannot express.

    Reads the cached `agent_initialize_result` (one real handshake per session) instead of
    connecting and sending a second `initialize` on a fresh/already-initialized connection --
    the latter is unspecified in v1 and a strict agent may legitimately reject a repeat
    `initialize` with `-32600` (review-slices-5-6.md B1)."""
    outcome = agent_initialize_result
    assert outcome.result is not None, f"initialize did not succeed: {outcome.error_message}"
    auth_methods = outcome.result.get("authMethods")
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
    """ACP-AUTH-003 (AUTH-C3/AUTH-C4). Only exercised when `authMethods` is non-empty AND
    `--tck-auth-method` was given -- SKIPs otherwise, since the TCK cannot guess a valid
    `methodId` and v1 never requires a testable auth flow to exist.

    `authenticate` succeeding is never asserted (must-NOT list #10: a real agent may
    legitimately reject bad/expired/cancelled credentials) -- an `authenticate` error SKIPs
    with a distinct, diagnosable reason. When it does return a result: AUTH-C3 (shape-only) the
    result is a JSON object; AUTH-C4 (the one hard assertion here) a subsequent `session/new`
    on the same connection does not fail with `-32000`."""
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
        if not (isinstance(auth_msg, dict) and isinstance(auth_msg.get("result"), dict)):
            detail = (auth_msg.get("error") if isinstance(auth_msg, dict) else None) or auth_entry.text
            pytest.skip(f"authenticate with methodId={method_id!r} failed: {detail!r}")
        # AUTH-C3: already established by the branch above -- reaching here means the result
        # was a dict.

        session_id = await agent.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}
        )
        session_entry = await agent.wait_for_response(session_id, timeout=agent_launch.default_timeout)
        session_msg = session_entry.parsed
        # AUTH-C4: only "not -32000" is assertable -- not full success shape, which is already
        # covered elsewhere (ACP-SESSION-001 etc.) for the non-auth-gated path.
        error = session_msg.get("error") if isinstance(session_msg, dict) else None
        assert not (isinstance(error, dict) and error.get("code") == -32000), (
            f"session/new failed with -32000 (authentication required) after a successful "
            f"authenticate: {session_entry.text!r}"
        )


@pytest.mark.requirement("ACP-AUTH-005")
async def test_session_new_not_gated_when_no_auth_methods_advertised(agent_launch, tmp_path):
    """ACP-AUTH-005 (AUTH-A1, ADVISORY). If `initialize` advertises no `authMethods` at all,
    `session/new` must not fail with `-32000` -- there would be no defined remedy. SKIPs when
    the agent does advertise auth methods (that case is ACP-AUTH-003's territory)."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        init_id = await agent.send_request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        init_entry = await agent.wait_for_response(init_id, timeout=agent_launch.default_timeout)
        init_msg = init_entry.parsed
        assert isinstance(init_msg, dict) and isinstance(init_msg.get("result"), dict), (
            f"initialize did not succeed: {init_entry.text!r}"
        )
        auth_methods = init_msg["result"].get("authMethods") or []
        if auth_methods:
            pytest.skip("agent advertises authMethods; AUTH-A1 only concerns the empty case")

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert isinstance(session_id, str)


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
