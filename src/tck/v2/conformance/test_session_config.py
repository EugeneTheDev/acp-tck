"""V2-4 session `configOptions` (ACP-CONFIG-201..204, ACP-CONFIG-206).

`configOptions` has no `capabilities` marker of its own -- support is *inferred* from whether
`session/new`'s response carries a non-empty `configOptions` list at all (C12,
`.agents/research/acp-v2-session-management.md`). `Requirement.capability` is therefore the
documentation-only `"inferred:configOptions"` string (mirrors v1's `ACP-MODES-001`/
`ACP-CONFIG-001/002` pattern exactly -- see `tck.v1.requirements`/`tck.v2.requirements` module
docstrings); it is *not* looked up by `@pytest.mark.capability(...)`. Each test instead performs
its own `session/new` and manually `pytest.skip`s with the reason "session/new returned no
configOptions" when the field is absent/empty.

Must NOT assert (per the source report): that a `configId`'s value scheme means anything beyond
schema validity, or that `session/set_config_option`'s *new* value is reflected anywhere besides
its own response/an observed `config_option_update` (`ACP-CONFIG-205`, ADVISORY, is not
registered this slice).

None of these tests carries a `@pytest.mark.capability(...)` marker (there is nothing for the
autouse `_tck_capability_gate` to look up -- `capability="inferred:configOptions"` is
documentation-only), so each connects via the local `_v2_only_agent` helper below -- `test_batch.
py`'s "manual initialize + skip on VERSION-MISMATCH" pattern, kept local for the same reason
`test_batch.py` keeps its own copy rather than promoting it to `_helpers.py` -- instead of
`connected_agent(agent_launch)` directly, so a v1-only agent forced under `--protocol-version 2`
SKIPs with the `VERSION-MISMATCH:` marker instead of just "session/new returned no
configOptions" (`tests/v2/test_cli.py`'s `test_v1_conforming_agent_under_protocol_version_2_is_
blocked_by_version_mismatch` invariant).
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from tck.v2.protocol import PROTOCOL_VERSION
from tck.v2.validation import validate_agent_response

from ._helpers import (
    connected_agent,
    drain_quiet,
    login_if_needed,
    quiet_period,
    resume_session,
    set_config_option,
    skip_if_auth_gated,
    skip_if_version_mismatch,
)


@contextlib.asynccontextmanager
async def _v2_only_agent(agent_launch):
    """A fresh connection, one manual `initialize`, and a `VERSION-MISMATCH:` skip unless the
    agent actually negotiated v2 -- see the module docstring. Also logs in (`login_if_needed`)
    when `--auth-method` was given, since every caller goes on to call `session/new` and this
    manual `initialize` bypasses `connected_agent`'s own auto-login step."""
    async with connected_agent(agent_launch, handshake=False) as agent:
        req_id = await agent.send_request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "info": {"name": "acp-tck", "version": "0"}},
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"initialize did not return a result object: {entry.text!r}"
        )
        skip_if_version_mismatch(msg["result"])
        await login_if_needed(agent, timeout=agent_launch.default_timeout)
        yield agent


async def _new_session_full_result(agent, cwd, *, timeout):
    """Like `_helpers.new_session`, but returns the whole result dict (not just `sessionId`) so
    callers can inspect `configOptions`.

    SKIPs (via `skip_if_auth_gated`, same as `_helpers.new_session()`) rather than failing when
    the agent requires authentication and no `--auth-method` was configured -- `_v2_only_agent`
    now also performs `login_if_needed` itself, so this remaining `skip_if_auth_gated` call only
    matters when no `--auth-method` was given at all (the ordinary auth-gate SKIP)."""
    req_id = await agent.send_request("session/new", {"cwd": str(cwd)})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    skip_if_auth_gated(entry)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    issues = validate_agent_response("session/new", msg)
    assert not issues, f"session/new result failed schema validation: {issues!r}"
    return msg["result"]


def _flatten_select_values(options: Any) -> list[Any]:
    """`SessionConfigSelectOptions` is `anyOf` a flat array of `{value, name, ...}` or a grouped
    array of `{groupId, name, options: [{value, ...}]}` -- flatten either shape down to the set
    of legal `value`s."""
    values: list[Any] = []
    for entry in options or []:
        if not isinstance(entry, dict):
            continue
        if "value" in entry:
            values.append(entry["value"])
        elif "options" in entry:
            for sub in entry["options"]:
                if isinstance(sub, dict) and "value" in sub:
                    values.append(sub["value"])
    return values


def _assert_config_options_shape_valid(config_options: list[Any]) -> None:
    """ACP-CONFIG-201's shape checks, factored out so ACP-CONFIG-203 (the `session/resume`
    carrier) can reuse them verbatim."""
    assert isinstance(config_options, list), f"configOptions must be an array, got {config_options!r}"
    for option in config_options:
        assert isinstance(option, dict) and "configId" in option and "name" in option, (
            f"each configOptions entry needs at least configId/name: {option!r}"
        )
        option_type = option.get("type")
        if option_type == "boolean":
            assert isinstance(option.get("currentValue"), bool), (
                f"config option {option['configId']!r} is type=boolean but currentValue is "
                f"{option.get('currentValue')!r}"
            )
        elif option_type == "select":
            assert "currentValue" in option, (
                f"select config option {option['configId']!r} has no currentValue"
            )
            opts = option.get("options") or []
            assert isinstance(opts, list) and opts, (
                f"select config option {option['configId']!r} has no options: {opts!r}"
            )
            is_flat = all(isinstance(o, dict) and "value" in o for o in opts)
            is_grouped = all(isinstance(o, dict) and "groupId" in o for o in opts)
            assert is_flat or is_grouped, (
                f"select config option {option['configId']!r} mixes flat and grouped option "
                f"shapes, never allowed: {opts!r}"
            )
        # any other `type` is a custom/`_`-prefixed variant -- nothing further to check here.


def _update_of(entry: Any) -> dict[str, Any] | None:
    msg = entry.parsed
    if not isinstance(msg, dict) or msg.get("method") != "session/update":
        return None
    params = msg.get("params")
    if not isinstance(params, dict):
        return None
    update = params.get("update")
    return update if isinstance(update, dict) else None


@pytest.mark.requirement("ACP-CONFIG-201")
async def test_config_options_shape_is_valid(agent_launch, tmp_path):
    """ACP-CONFIG-201."""
    async with _v2_only_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if not config_options:
            pytest.skip("session/new returned no configOptions")
        _assert_config_options_shape_valid(config_options)


async def _pick_settable_option(config_options: list[Any]) -> tuple[dict[str, Any], str, Any]:
    """Pick the first configOptions entry this suite knows how to `session/set_config_option`,
    returning `(option, set_type, new_value)`. Skips if `config_options[0]` is a custom type this
    suite has no wire encoding for."""
    target = config_options[0]
    if target.get("type") == "boolean":
        return target, "boolean", not target.get("currentValue")
    if target.get("type") == "select":
        legal_values = _flatten_select_values(target.get("options"))
        remaining = [value for value in legal_values if value != target.get("currentValue")]
        if not remaining:
            pytest.skip(f"config option {target['configId']!r} has no alternative value to switch to")
        return target, "id", remaining[0]
    pytest.skip(f"config option {target['configId']!r} has an unrecognized/custom type {target.get('type')!r}")
    raise AssertionError("unreachable")  # pytest.skip always raises


@pytest.mark.requirement("ACP-CONFIG-202")
async def test_set_config_option_returns_the_complete_list(agent_launch, tmp_path):
    """ACP-CONFIG-202. Gate is genuinely unstated upstream (C12): SKIPs rather than ever
    speculatively calling `session/set_config_option` when `session/new` advertised no
    `configOptions` at all -- there would be nothing legitimate to set."""
    async with _v2_only_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if not config_options:
            pytest.skip("session/new returned no configOptions")
        session_id = result["sessionId"]
        original_ids = {
            option["configId"]
            for option in config_options
            if isinstance(option, dict) and "configId" in option
        }
        target, set_type, new_value = await _pick_settable_option(config_options)

        entry = await set_config_option(
            agent,
            session_id,
            target["configId"],
            type=set_type,
            value=new_value,
            timeout=agent_launch.default_timeout,
        )
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/set_config_option did not succeed: {entry.text!r}"
        )
        returned = msg["result"].get("configOptions")
        assert isinstance(returned, list), (
            f"session/set_config_option result.configOptions must be an array, got {returned!r}"
        )
        returned_ids = {option.get("configId") for option in returned if isinstance(option, dict)}
        assert original_ids <= returned_ids, (
            "session/set_config_option must return the *complete* configOptions list -- "
            f"missing ids {original_ids - returned_ids!r}"
        )
        changed = next(
            (o for o in returned if isinstance(o, dict) and o.get("configId") == target["configId"]),
            None,
        )
        assert changed is not None and changed.get("currentValue") == new_value, (
            f"session/set_config_option's returned list does not reflect the new value for "
            f"{target['configId']!r}: {changed!r}"
        )


@pytest.mark.requirement("ACP-CONFIG-203")
async def test_resume_config_options_shape_is_valid_when_present(agent_launch, tmp_path):
    """ACP-CONFIG-203. A new carrier in v2 -- v1's `session/load` had no analogous field."""
    async with _v2_only_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        if not result.get("configOptions"):
            pytest.skip("session/new returned no configOptions")
        session_id = result["sessionId"]
        response_entry, _updates = await resume_session(
            agent, session_id, tmp_path, timeout=agent_launch.default_timeout
        )
        msg = response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/resume did not succeed: {response_entry.text!r}"
        )
        config_options = msg["result"].get("configOptions")
        if config_options is None:
            pytest.skip("session/resume result carried no configOptions to validate")
        _assert_config_options_shape_valid(config_options)


@pytest.mark.requirement("ACP-CONFIG-204")
async def test_select_config_option_current_value_is_declared(agent_launch, tmp_path):
    """ACP-CONFIG-204."""
    async with _v2_only_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if not config_options:
            pytest.skip("session/new returned no configOptions")
        select_options = [
            option for option in config_options if isinstance(option, dict) and option.get("type") == "select"
        ]
        if not select_options:
            pytest.skip("no select-type configOptions to check")
        for option in select_options:
            legal_values = _flatten_select_values(option.get("options"))
            assert option.get("currentValue") in legal_values, (
                f"config option {option['configId']!r} currentValue {option.get('currentValue')!r} "
                f"is not among its declared options {legal_values!r}"
            )


@pytest.mark.requirement("ACP-CONFIG-206")
async def test_config_option_update_is_complete_if_observed(agent_launch, tmp_path, record_property):
    """ACP-CONFIG-206. Conditional and vacuous (recorded, never FAILed) when no
    `config_option_update` is ever observed during the run."""
    async with _v2_only_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if not config_options:
            pytest.skip("session/new returned no configOptions")
        session_id = result["sessionId"]
        original_ids = {
            option["configId"]
            for option in config_options
            if isinstance(option, dict) and "configId" in option
        }
        target, set_type, new_value = await _pick_settable_option(config_options)

        entry = await set_config_option(
            agent,
            session_id,
            target["configId"],
            type=set_type,
            value=new_value,
            timeout=agent_launch.default_timeout,
        )
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/set_config_option did not succeed: {entry.text!r}"
        )

        # `wait_for_response` (inside `set_config_option`) may already have buffered a
        # same-timing `config_option_update` into `agent.pending()`; a short quiet drain then
        # catches one sent just after the response too.
        observed = agent.pending() + await drain_quiet(agent, quiet_period(agent_launch.default_timeout))
        update_entries = [
            update
            for entry in observed
            if (update := _update_of(entry)) is not None and update.get("sessionUpdate") == "config_option_update"
        ]
        record_property("acp_tck_config_option_update_observed", bool(update_entries))
        if not update_entries:
            return  # vacuous -- conforming, nothing further to check
        for update in update_entries:
            returned = update.get("configOptions")
            assert isinstance(returned, list), (
                f"config_option_update.configOptions must be an array, got {returned!r}"
            )
            returned_ids = {o.get("configId") for o in returned if isinstance(o, dict)}
            assert original_ids <= returned_ids, (
                "config_option_update must carry the *complete* configuration state -- missing "
                f"ids {original_ids - returned_ids!r}"
            )
