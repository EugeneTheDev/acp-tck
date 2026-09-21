"""Permission-request shape: ACP-PERM-201 (new id -- no v1 counterpart at all: v1's own
`session/request_permission` params shape differs and has no `title`).

`Tier.CAPABILITY`, `capability="capabilities.session"` per the "v2 tiering rule for
session-baseline rows" -- see `tck.v2.requirements`'s module docstring (the source research
report's own table suggests MANDATORY "vacuous when unseen"; superseded). SKIPs "no permission
request observed" whenever the agent's turn never sends `session/request_permission` at all --
sending one is only MAY (research row C1), so there is then nothing to validate.
"""

from __future__ import annotations

import pytest

from tck.v2.validation import validate_agent_message

from ._helpers import connected_agent, new_session, run_prompt

_PROMPT_TEXT = "hi"


@pytest.mark.requirement("ACP-PERM-201")
@pytest.mark.capability("capabilities.session")
async def test_request_permission_shape_and_turn_completes(agent_launch, tmp_path):
    """ACP-PERM-201. Any `session/request_permission` request observed during the turn
    validates against the v2 schema, and specifically carries a non-empty string `title` (new in
    v2 -- research row C2) and a non-empty `options` array, each option carrying
    `optionId`/`name`/`kind` (row C3). Once the mock client answers with a `selected` outcome
    (`run_prompt`'s default), the turn still reaches a terminating idle.
    """
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        turn = await run_prompt(
            agent,
            session_id,
            [{"type": "text", "text": _PROMPT_TEXT}],
            timeout=agent_launch.default_timeout,
        )

        permission_requests = [
            entry
            for entry in turn.client_requests_seen
            if isinstance(entry.parsed, dict)
            and entry.parsed.get("method") == "session/request_permission"
        ]
        if not permission_requests:
            pytest.skip("no permission request observed during this turn")

        for entry in permission_requests:
            msg = entry.parsed
            issues = validate_agent_message(msg)
            assert not issues, f"session/request_permission failed schema validation: {issues!r}"

            params = msg.get("params") or {}
            title = params.get("title")
            assert isinstance(title, str) and title, (
                f"session/request_permission.title must be a non-empty string, got {title!r}"
            )
            options = params.get("options")
            assert isinstance(options, list) and options, (
                f"session/request_permission.options must be a non-empty array, got {options!r}"
            )
            for option in options:
                assert isinstance(option, dict), f"permission option is not an object: {option!r}"
                for field in ("optionId", "name", "kind"):
                    assert field in option and option[field], (
                        f"permission option missing/empty {field!r}: {option!r}"
                    )

        assert turn.idle_update is not None, (
            "a session/request_permission was answered with a selected outcome, but the turn "
            "never reached a terminating idle state_update"
        )
