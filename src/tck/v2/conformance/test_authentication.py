"""The v2 authentication surface: `authMethods` shape, the terminal-method client-capability
gate, the `auth/login`/`auth/logout`/`session/new` flow, and the open-enum `type` rule
(ACP-AUTH-201..207).

v2 renames v1's `authenticate`/`logout` to `auth/login`/`auth/logout` and drops the separate
`agentCapabilities.auth.logout` marker -- see `tck.v2.requirements`'s "Authentication" section
for the id-namespacing rationale (which ids are re-cited from v1, which are genuinely new).

Deliberately not asserted: that non-empty `authMethods` implies `session/new` fails with
`-32000` before authentication (a MAY, not a MUST); session state after `auth/logout`; that
`auth/login`/`auth/logout` themselves succeed (a real agent may legitimately reject
bad/expired credentials -- that SKIPs with a diagnosable reason instead of FAILing).
"""

from __future__ import annotations

import contextlib

import pytest

from tck.common.plugin import current_allow_logout, current_auth_method_id

from .. import SPEC
from ..protocol import is_valid_open_enum_value
from ._helpers import connected_agent, new_session, skip_if_version_mismatch, validate_login_method_id


@contextlib.asynccontextmanager
async def _initialized_agent(agent_launch, *, capabilities=None):
    """A fresh connection with a manual `initialize` (optional `capabilities` override), SKIPping
    with `VERSION-MISMATCH:` unless the agent negotiated v2. Kept local rather than shared,
    since these tests need `handshake=False` to control `auth/login` timing relative to their
    own SKIP checks. Yields `(agent, init_result)`.
    """
    async with connected_agent(agent_launch, handshake=False) as agent:
        params = SPEC.initialize_params()
        if capabilities is not None:
            params = {**params, "capabilities": capabilities}
        req_id = await agent.send_request("initialize", params)
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.startup_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not succeed: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        yield agent, msg["result"]


@pytest.mark.requirement("ACP-AUTH-201")
async def test_auth_methods_have_unique_method_ids(agent_initialize_result):
    """ACP-AUTH-201 (ADVISORY; re-cites v1's ACP-AUTH-001, field renamed `id` -> `methodId`).
    Schema-shape validation of `authMethods` is already covered by ACP-SCHEMA-001; this adds the
    id-uniqueness check schema validation alone can't express. Uses the cached
    `agent_initialize_result` rather than a second connection -- v2 never requires a testable
    second `initialize`."""
    outcome = agent_initialize_result
    assert outcome.result is not None, f"initialize did not succeed: {outcome.error_message}"
    skip_if_version_mismatch(outcome.result)
    auth_methods = outcome.result.get("authMethods")
    if not auth_methods:
        # Nothing to check here -- record it as a SKIP, not a vacuous PASS.
        pytest.skip("agent advertises no authMethods")
    assert isinstance(auth_methods, list)
    method_ids = [method.get("methodId") for method in auth_methods if isinstance(method, dict)]
    assert len(method_ids) == len(set(method_ids)), f"authMethods methodIds are not unique: {method_ids!r}"


@pytest.mark.requirement("ACP-AUTH-206")
async def test_auth_method_type_is_a_defined_or_prefixed_value(agent_initialize_result):
    """ACP-AUTH-206 (MANDATORY, new in v2). Every `authMethods[*].type` is `"agent"`,
    `"terminal"`, or begins with `_` -- the general open-enum extensibility rule applied to this
    field (`docs/protocol/v2/authentication.mdx:120-122`)."""
    outcome = agent_initialize_result
    assert outcome.result is not None, f"initialize did not succeed: {outcome.error_message}"
    skip_if_version_mismatch(outcome.result)
    auth_methods = outcome.result.get("authMethods") or []
    if not auth_methods:
        # A vacuous PASS is more misleading than a SKIP for a MANDATORY row (SKIPPED doesn't
        # block conformance; FAIL/NOT_TESTED do).
        pytest.skip("agent advertises no authMethods")
    defined = frozenset({"agent", "terminal"})
    for method in auth_methods:
        if not isinstance(method, dict):
            continue
        type_value = method.get("type")
        assert is_valid_open_enum_value(type_value, defined), (
            f"authMethods entry has an unrecognized, non-`_`-prefixed type: {method!r}"
        )


@pytest.mark.requirement("ACP-AUTH-202")
async def test_no_terminal_auth_method_without_client_capability(agent_launch):
    """ACP-AUTH-202 (MANDATORY, new id -- not a reuse of v1's `ACP-AUTH-002`; see the module
    docstring). Connects with no `capabilities.auth.terminal` (the default v2 handshake omits
    it entirely) and asserts no `authMethods[*].type == "terminal"` is advertised."""
    async with _initialized_agent(agent_launch) as (agent, init_result):
        auth_methods = init_result.get("authMethods") or []
        terminal_methods = [
            method for method in auth_methods if isinstance(method, dict) and method.get("type") == "terminal"
        ]
        assert not terminal_methods, (
            "agent advertised authMethods[*].type == 'terminal' without the client advertising "
            f"capabilities.auth.terminal: {terminal_methods!r}"
        )


@pytest.mark.requirement("ACP-AUTH-207")
async def test_terminal_auth_method_descriptor_shape(agent_launch):
    """ACP-AUTH-207 (MANDATORY, new in v2 -- no v1 analogue). On a dedicated connection that
    *does* advertise `capabilities.auth.terminal: {}`, every `type: "terminal"` entry's `args`
    (if present) is an array of strings, `env` (if present) is an array of well-formed
    `EnvVariable` objects, and `env` names are unique within that descriptor ("Names MUST be
    unique", `schema/v2/schema.json` `$defs/AuthMethodTerminal`). Conditional on at least one
    terminal entry actually appearing -- SKIPs otherwise, since there is nothing to check."""
    async with _initialized_agent(agent_launch, capabilities={"auth": {"terminal": {}}}) as (agent, init_result):
        auth_methods = init_result.get("authMethods") or []
        terminal_methods = [
            method for method in auth_methods if isinstance(method, dict) and method.get("type") == "terminal"
        ]
        if not terminal_methods:
            pytest.skip("agent advertises no type=='terminal' authMethods entry; nothing to check")
        for method in terminal_methods:
            args = method.get("args")
            if args is not None:
                assert isinstance(args, list) and all(isinstance(a, str) for a in args), (
                    f"terminal authMethods entry's args must be an array of strings: {method!r}"
                )
            env = method.get("env")
            if env is not None:
                assert isinstance(env, list), f"terminal authMethods entry's env must be an array: {method!r}"
                names = []
                for var in env:
                    assert (
                        isinstance(var, dict)
                        and isinstance(var.get("name"), str)
                        and isinstance(var.get("value"), str)
                    ), f"env entry is not a well-formed EnvVariable (name/value both required strings): {var!r}"
                    names.append(var["name"])
                assert len(names) == len(set(names)), f"terminal authMethods entry's env names are not unique: {names!r}"


@pytest.mark.requirement("ACP-AUTH-204")
async def test_login_then_session_new_succeeds(agent_launch, tmp_path):
    """ACP-AUTH-204 (CAPABILITY, `capability="inferred:authMethods"` -- mirrors v1's
    `ACP-AUTH-003`, method renamed `authenticate` -> `auth/login`). SKIPs unless `authMethods`
    is non-empty and `--tck-auth-method` was given (the TCK cannot guess a `methodId`), or if
    `validate_login_method_id` rejects an unadvertised/terminal id.

    `auth/login` succeeding is not a hard requirement -- an agent may legitimately reject
    bad/expired credentials, which SKIPs with a diagnosable reason instead of failing. The one
    hard assertion: a subsequent `session/new` on the same connection does not fail with
    `-32000`.

    The `--tck-auth-method` check happens inside `_initialized_agent`, after the
    version-mismatch check has already had a chance to fire, so a version-mismatched agent
    SKIPs with `VERSION-MISMATCH:` rather than an unrelated reason."""
    async with _initialized_agent(agent_launch) as (agent, init_result):
        method_id = current_auth_method_id()
        if method_id is None:
            pytest.skip("no --tck-auth-method given; cannot exercise the auth/login flow")

        auth_methods = init_result.get("authMethods") or []
        if not auth_methods:
            pytest.skip("agent advertises no authMethods; nothing to authenticate against")
        validate_login_method_id(auth_methods, method_id)

        login_id = await agent.send_request("auth/login", {"methodId": method_id})
        login_entry = await agent.wait_for_response(login_id, timeout=agent_launch.default_timeout)
        login_msg = login_entry.parsed
        if not (isinstance(login_msg, dict) and isinstance(login_msg.get("result"), dict)):
            detail = (login_msg.get("error") if isinstance(login_msg, dict) else None) or login_entry.text
            pytest.skip(f"auth/login with methodId={method_id!r} failed: {detail!r}")

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert isinstance(session_id, str) and session_id


@pytest.mark.requirement("ACP-AUTH-205")
async def test_session_new_not_gated_when_no_auth_methods_advertised(agent_launch, tmp_path):
    """ACP-AUTH-205 (ADVISORY; re-cites v1's ACP-AUTH-005/AUTH-A1). If `initialize` advertises
    no `authMethods` at all, `session/new` must not fail with `-32000` -- there would be no
    defined remedy. SKIPs when the agent does advertise auth methods (that case is
    ACP-AUTH-204's territory)."""
    async with _initialized_agent(agent_launch) as (agent, init_result):
        auth_methods = init_result.get("authMethods") or []
        if auth_methods:
            pytest.skip("agent advertises authMethods; AUTH-205 only concerns the empty case")

        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        assert isinstance(session_id, str)


@pytest.mark.requirement("ACP-AUTH-203")
async def test_logout_succeeds(agent_launch):
    """ACP-AUTH-203 (CAPABILITY, `capability="inferred:authMethods"` -- replaces v1's
    `ACP-AUTH-004` outright, since v2 has no `agentCapabilities.auth.logout` marker). SKIPs when
    the agent advertises no `authMethods`, or unless `--allow-logout`/`--tck-allow-logout` was
    given, since a real `auth/logout` may revoke the operator's own credentials.

    If `--tck-auth-method` was given, logs in first (gated by the same `validate_login_method_id`
    check as ACP-AUTH-204, so an unadvertised/terminal id SKIPs rather than sending a
    spec-forbidden `auth/login`). Only `auth/logout`'s own success (a schema-valid object
    result) is checked -- nothing about session state after logout."""
    async with _initialized_agent(agent_launch) as (agent, init_result):
        auth_methods = init_result.get("authMethods") or []
        if not auth_methods:
            pytest.skip("agent advertises no authMethods; nothing to log out of")
        if not current_allow_logout():
            pytest.skip(
                "auth/logout not exercised: pass --allow-logout (it may revoke the operator's "
                "credentials)"
            )

        method_id = current_auth_method_id()
        if method_id is not None:
            validate_login_method_id(auth_methods, method_id)
            login_id = await agent.send_request("auth/login", {"methodId": method_id})
            login_entry = await agent.wait_for_response(login_id, timeout=agent_launch.default_timeout)
            login_msg = login_entry.parsed
            if not (isinstance(login_msg, dict) and isinstance(login_msg.get("result"), dict)):
                detail = (login_msg.get("error") if isinstance(login_msg, dict) else None) or login_entry.text
                pytest.skip(f"auth/login with methodId={method_id!r} failed: {detail!r}")

        logout_id = await agent.send_request("auth/logout", {})
        logout_entry = await agent.wait_for_response(logout_id, timeout=agent_launch.default_timeout)
        logout_msg = logout_entry.parsed
        assert isinstance(logout_msg, dict) and isinstance(logout_msg.get("result"), dict), (
            f"auth/logout did not succeed with an object result: {logout_entry.text!r}"
        )
