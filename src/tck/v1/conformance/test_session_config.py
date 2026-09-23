"""Session modes and config options (ACP-MODES-001/002, ACP-CONFIG-001/002/003).

`modes` and `configOptions` have no `agentCapabilities` marker of their own -- support is
*inferred* from whether `session/new`'s response carries a non-null value for either field.
`ACP-MODES-*`/`ACP-CONFIG-001/002`'s `Requirement.capability` is therefore a documentation-only
`"inferred:modes"` / `"inferred:configOptions"` string (see `tck.v1.requirements` module
docstring for why this is the smallest change that satisfies `Requirement.__post_init__`'s
invariant) -- it is *not* looked up by `tck.common.plugin`'s `@pytest.mark.capability(...)`
marker/`_tck_capability_gate` fixture, since that machinery only understands real
`initialize`-result paths. Instead, each test below performs its own `session/new` and manually
`pytest.skip`s with the reason "session/new returned no modes/configOptions" when the relevant
field is absent.

Note: `current_mode_update` emission itself is optional; only the field name, if it is emitted,
is a MUST.
"""

from __future__ import annotations

from typing import Any

import pytest

from tck.common.harness import AgentExited, AgentTimeout
from tck.v1.validation import validate_agent_response

from ._helpers import connected_agent, quiet_period, skip_if_auth_gated


async def _new_session_full_result(agent, cwd, *, timeout):
    """Like `_helpers.new_session`, but returns the whole result dict (not just `sessionId`) so
    callers can inspect `modes`/`configOptions`."""
    req_id = await agent.send_request("session/new", {"cwd": str(cwd), "mcpServers": []})
    entry = await agent.wait_for_response(req_id, timeout=timeout)
    skip_if_auth_gated(entry)
    msg = entry.parsed
    assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
        f"session/new did not return a result object: {entry.text!r}"
    )
    issues = validate_agent_response("session/new", msg)
    assert not issues, f"session/new result failed schema validation: {issues!r}"
    return msg["result"]


def _flatten_select_values(options) -> list[Any]:
    """`SessionConfigSelectOptions` is `anyOf` a flat array of `{value, name, ...}` or a grouped
    array of `{group, name, options: [{value, ...}]}` -- flatten either shape down to the set of
    legal `value`s."""
    values = []
    for entry in options:
        if not isinstance(entry, dict):
            continue
        if "value" in entry:
            values.append(entry["value"])
        elif "options" in entry:
            for sub in entry["options"]:
                if isinstance(sub, dict) and "value" in sub:
                    values.append(sub["value"])
    return values


# --- modes ---


@pytest.mark.requirement("ACP-MODES-001")
async def test_modes_validate_and_current_mode_is_available(agent_launch, tmp_path):
    """ACP-MODES-001."""
    async with connected_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        modes = result.get("modes")
        if modes is None:
            pytest.skip("session/new returned no modes/configOptions")
        assert isinstance(modes, dict), f"modes must be an object, got {modes!r}"
        current_mode_id = modes.get("currentModeId")
        available = modes.get("availableModes")
        assert isinstance(available, list) and available, (
            f"modes.availableModes must be a non-empty array, got {available!r}"
        )
        ids = [mode.get("id") for mode in available if isinstance(mode, dict)]
        assert current_mode_id in ids, (
            f"modes.currentModeId {current_mode_id!r} is not one of availableModes' ids {ids!r}"
        )


@pytest.mark.requirement("ACP-MODES-002")
async def test_set_mode_succeeds_and_update_uses_currentModeId(agent_launch, tmp_path, record_property):
    """ACP-MODES-002. Do not assert an echo `current_mode_update` is emitted at all -- only that
    *if* one is observed, it carries the schema field name `currentModeId`, not the docs-bug
    `modeId`."""
    async with connected_agent(agent_launch) as agent:
        session_id_result = await _new_session_full_result(
            agent, tmp_path, timeout=agent_launch.default_timeout
        )
        modes = session_id_result.get("modes")
        if modes is None:
            pytest.skip("session/new returned no modes/configOptions")
        session_id = session_id_result["sessionId"]
        available = modes.get("availableModes") or []
        ids = [mode.get("id") for mode in available if isinstance(mode, dict)]
        current = modes.get("currentModeId")
        candidates = [mode_id for mode_id in ids if mode_id != current]
        if not candidates:
            pytest.skip("agent only advertises a single mode; nothing to switch to")
        target_mode_id = candidates[0]

        req_id = await agent.send_request(
            "session/set_mode", {"sessionId": session_id, "modeId": target_mode_id}
        )
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and "result" in msg, (
            f"session/set_mode did not succeed: {entry.text!r}"
        )

        def _is_mode_update(candidate_entry) -> bool:
            candidate = candidate_entry.parsed
            if not isinstance(candidate, dict) or candidate.get("method") != "session/update":
                return False
            params = candidate.get("params") or {}
            update = params.get("update") or {}
            return (
                params.get("sessionId") == session_id
                and update.get("sessionUpdate") == "current_mode_update"
            )

        update_entry = None
        for pending_entry in agent.pending():
            if _is_mode_update(pending_entry):
                update_entry = pending_entry
                break
        if update_entry is None:
            try:
                update_entry = await agent.wait_for_message(
                    _is_mode_update, timeout=quiet_period(agent_launch.default_timeout)
                )
            except (AgentTimeout, AgentExited):
                # Exiting promptly instead of waiting out the quiet period also counts as
                # "no update observed" -- not a defect.
                update_entry = None

        if update_entry is not None:
            update = update_entry.parsed["params"]["update"]
            assert "currentModeId" in update, (
                "current_mode_update must carry the schema field name 'currentModeId' (the "
                f"docs' 'modeId' is a confirmed docs bug); got {update!r}"
            )
            # Only the field name is pinned by the spec, not the echoed value -- an agent may
            # autonomously switch again inside the quiet period. Record it for a human reader
            # instead of asserting it.
            record_property("acp_tck_mode_update_current_mode_id", update["currentModeId"])


# --- config options ---


@pytest.mark.requirement("ACP-CONFIG-001")
async def test_config_options_current_values_are_valid(agent_launch, tmp_path):
    """ACP-CONFIG-001."""
    async with connected_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if config_options is None:
            pytest.skip("session/new returned no modes/configOptions")
        assert isinstance(config_options, list), (
            f"configOptions must be an array, got {config_options!r}"
        )
        for option in config_options:
            assert isinstance(option, dict) and "id" in option and "name" in option, (
                f"each configOptions entry needs at least id/name: {option!r}"
            )
            option_type = option.get("type")
            current_value = option.get("currentValue")
            if option_type == "boolean":
                assert isinstance(current_value, bool), (
                    f"config option {option['id']!r} is type=boolean but currentValue is "
                    f"{current_value!r}"
                )
            else:
                # Default/select variant: currentValue must be one of the declared options.
                legal_values = _flatten_select_values(option.get("options") or [])
                assert current_value in legal_values, (
                    f"config option {option['id']!r} currentValue {current_value!r} is not "
                    f"among its declared options {legal_values!r}"
                )


@pytest.mark.requirement("ACP-CONFIG-002")
async def test_set_config_option_returns_the_complete_list(agent_launch, tmp_path):
    """ACP-CONFIG-002."""
    async with connected_agent(agent_launch) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions")
        if not config_options:
            pytest.skip("session/new returned no modes/configOptions")
        session_id = result["sessionId"]
        # Guard against a non-dict/missing-"id" entry the same way CONFIG-001 does at its own
        # set-comprehension -- this test runs independently of CONFIG-001, so it must not rely
        # on that guard having already caught a malformed entry.
        original_ids = {
            option["id"] for option in config_options if isinstance(option, dict) and "id" in option
        }

        target = config_options[0]
        if target.get("type") == "boolean":
            new_value: Any = not target.get("currentValue")
            params: dict[str, Any] = {
                "sessionId": session_id,
                "configId": target["id"],
                "type": "boolean",
                "value": new_value,
            }
        else:
            legal_values = _flatten_select_values(target.get("options") or [])
            remaining = [value for value in legal_values if value != target.get("currentValue")]
            if not remaining:
                pytest.skip(f"config option {target['id']!r} has no alternative value to switch to")
            new_value = remaining[0]
            params = {"sessionId": session_id, "configId": target["id"], "value": new_value}

        req_id = await agent.send_request("session/set_config_option", params)
        entry = await agent.wait_for_response(req_id, timeout=agent_launch.default_timeout)
        msg = entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/set_config_option did not succeed: {entry.text!r}"
        )
        returned = msg["result"].get("configOptions")
        assert isinstance(returned, list), (
            f"session/set_config_option result.configOptions must be an array, got {returned!r}"
        )
        returned_ids = {option.get("id") for option in returned if isinstance(option, dict)}
        # Subset, not set-equality: the complete-list requirement exists so agents can reflect
        # dependent changes, which may *add* options a stricter `==` check would wrongly reject.
        # Do not "fix" this into `==`.
        assert original_ids <= returned_ids, (
            "session/set_config_option must return the *complete* configOptions list -- missing "
            f"ids {original_ids - returned_ids!r}"
        )
        changed = next(
            (opt for opt in returned if isinstance(opt, dict) and opt.get("id") == target["id"]),
            None,
        )
        assert changed is not None and changed.get("currentValue") == new_value, (
            f"session/set_config_option's returned list does not reflect the new value for "
            f"{target['id']!r}: {changed!r}"
        )


@pytest.mark.requirement("ACP-CONFIG-003")
async def test_no_boolean_config_option_without_client_capability(agent_launch, tmp_path):
    """ACP-CONFIG-003 (MANDATORY, Req 33). Connects with `clientCapabilities: {}` explicitly
    (no `session.configOptions.boolean`) and asserts no `type: "boolean"` option is present.
    Passes vacuously if the agent has no config options at all, or none of type boolean."""
    # `client_capabilities={}` is already the default; passed explicitly so this reads as a
    # deliberate no-capability connection, not an accident of today's default.
    async with connected_agent(agent_launch, client_capabilities={}) as agent:
        result = await _new_session_full_result(agent, tmp_path, timeout=agent_launch.default_timeout)
        config_options = result.get("configOptions") or []
        boolean_options = [opt for opt in config_options if isinstance(opt, dict) and opt.get("type") == "boolean"]
        assert not boolean_options, (
            "agent advertised type='boolean' configOptions without the client advertising "
            f"clientCapabilities.session.configOptions.boolean: {boolean_options!r}"
        )
