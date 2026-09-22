"""ACP v2 (Draft) protocol-level constants and method inventories.

Everything here is derived from the vendored spec artifacts in `tck/v2/schema/` (see
`tck/v2/schema/VENDORED.md` for provenance) rather than hand-copied from documentation, so a
schema refresh re-derives these automatically. Deliberately duplicated from `tck.v1.protocol`
rather than imported -- each version's schema-derivation code is honest duplication, not shared
machinery that would couple the two versions' schema shapes together, since the two will drift
as v2 (still Draft) evolves.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 2
"""The ACP protocol version `tck.v2` speaks. Wire encoding is a bare JSON integer, not a version
string, same as v1 (`.agents/research/acp-v2-version-negotiation.md`)."""

SCHEMA_DIR = Path(__file__).parent / "schema"

SCHEMA_REVISION = "8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e"
"""The spec commit the vendored `schema/{schema,meta}.json` -- and every requirement citation in
`tck.v2.requirements` -- are pinned to (see `schema/VENDORED.md`). v2 is Draft (schema version
`2.0.0-alpha.5` at this commit); expect this to change more often than v1's pin."""

# JSON-RPC / ACP error codes (schema/v2/schema.json `ErrorCode`). Unchanged from v1
# (`.agents/research/acp-v2-status-and-delta-inventory.md`).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
REQUEST_CANCELLED = -32800
AUTHENTICATION_REQUIRED = -32000
RESOURCE_NOT_FOUND = -32002

# `StopReason` values (schema/v2/schema.json `StopReason`). Same five defined constants as v1,
# but v2 additionally has an open `"other"` fallback branch (`type: "string"`, no defined
# `const`) with no schema-level exclusion of unknown values -- see `is_valid_open_enum_value`
# below, which is the hand-written check that enforces the `_`-prefix extensibility rule the
# schema itself cannot express (`.agents/research/acp-v2-patches-enums-extensibility.md` B1).
STOP_REASON_END_TURN = "end_turn"
STOP_REASON_MAX_TOKENS = "max_tokens"
STOP_REASON_MAX_TURN_REQUESTS = "max_turn_requests"
STOP_REASON_REFUSAL = "refusal"
STOP_REASON_CANCELLED = "cancelled"
STOP_REASONS = frozenset(
    {
        STOP_REASON_END_TURN,
        STOP_REASON_MAX_TOKENS,
        STOP_REASON_MAX_TURN_REQUESTS,
        STOP_REASON_REFUSAL,
        STOP_REASON_CANCELLED,
    }
)

# Open-enum value sets for the `ACP-ENUM-201`/`ACP-ENUM-202` families (schema/v2/schema.json's
# `ToolKind`, `ToolCallStatus`, `PlanEntryPriority`, `PlanEntryStatus`,
# `SessionUpdate.sessionUpdate`, `StateUpdate.state`, `ToolCallContent.type`). Hand-copied
# constants, same as `STOP_REASONS` above; promoted here from `test_enums.py`'s own former
# module-local copies (review-v2-slices-1b-6 finding 20). `tests/v2/test_validation.py`'s
# `test_enum_sets_match_the_schema` independently re-derives each of these from `schema.json`'s
# own `anyOf`/`const` branches and asserts equality, so a schema refresh that adds, removes, or
# renames a branch is caught as a test failure rather than silently drifting out of sync.
TOOL_KIND = frozenset(
    {"read", "edit", "delete", "move", "search", "execute", "think", "fetch", "switch_mode", "other"}
)
TOOL_CALL_STATUS = frozenset({"pending", "in_progress", "completed", "failed", "cancelled"})
PLAN_ENTRY_PRIORITY = frozenset({"high", "medium", "low"})
PLAN_ENTRY_STATUS = frozenset({"pending", "in_progress", "completed", "cancelled"})
SESSION_UPDATE_KIND = frozenset(
    {
        "user_message_chunk",
        "user_message",
        "agent_message_chunk",
        "agent_message",
        "agent_thought_chunk",
        "agent_thought",
        "state_update",
        "tool_call_content_chunk",
        "tool_call_update",
        "terminal_update",
        "terminal_output_chunk",
        "plan_update",
        "available_commands_update",
        "config_option_update",
        "session_info_update",
        "usage_update",
    }
)
STATE_UPDATE_STATE = frozenset({"running", "idle", "requires_action"})
TOOL_CALL_CONTENT_TYPE = frozenset({"content", "diff", "terminal"})


def is_valid_open_enum_value(value: Any, defined: frozenset[str]) -> bool:
    """Req B1: a value for an open enum / tagged-union discriminator (e.g. `StopReason`) is
    legal iff it is one of `defined`'s fixed constants, OR it is a string beginning with `_`
    (reserved for implementation-specific extensions). Any other value -- including a
    non-`_`-prefixed string the schema's own open `"other"` fallback branch would otherwise
    accept -- is reserved for future ACP variants and is not legal for *this* agent to emit.

    Never raises, even for an unhashable agent-supplied `value` (a `list`/`dict`): the
    `isinstance` check runs before any membership test against `defined`, which would otherwise
    raise `TypeError` for `value in defined` on an unhashable `value`.
    """
    if not isinstance(value, str):
        return False
    return value in defined or value.startswith("_")


@lru_cache(maxsize=1)
def load_meta() -> dict[str, Any]:
    """Parse `schema/meta.json`: a `version` int, plus three flat `{internal_name: "wire/
    method"}` dicts -- `agentMethods`, `clientMethods`, `protocolMethods` (just
    `cancel_request` -> `$/cancel_request`, same as v1). Does not itself distinguish requests
    from notifications -- that split is derived from `schema.json` below."""
    return json.loads((SCHEMA_DIR / "meta.json").read_text())


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Parse `schema/schema.json`."""
    return json.loads((SCHEMA_DIR / "schema.json").read_text())


def _collect_ref_names(node: Any) -> list[str]:
    """Recursively collect every local `$ref` target name (`#/$defs/X` -> `X`) under `node`."""
    names: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            names.append(ref.removeprefix("#/$defs/"))
        for value in node.values():
            names.extend(_collect_ref_names(value))
    elif isinstance(node, list):
        for item in node:
            names.extend(_collect_ref_names(item))
    return names


def _notification_methods(notification_def_name: str) -> frozenset[str]:
    """Wire methods of every non-extension variant listed under a top-level notification
    envelope $def (`AgentNotification` or `ClientNotification`).

    Each variant $def carries its own `x-method` annotation (e.g. `UpdateSessionNotification` ->
    `session/update`); `Ext*` defs carry no `x-side`/`x-method` annotation and are skipped since
    their method name is dynamic (`_`-prefixed, caller-chosen).
    """
    defs = load_schema()["$defs"]
    envelope = defs[notification_def_name]
    methods = set()
    for ref_name in _collect_ref_names(envelope.get("properties", {}).get("params", {})):
        method = defs.get(ref_name, {}).get("x-method")
        if method:
            methods.add(method)
    return frozenset(methods)


AGENT_METHODS: frozenset[str] = frozenset(load_meta()["agentMethods"].values())
"""Wire methods the agent must be able to handle (client -> agent), requests and notifications
alike."""

CLIENT_METHODS: frozenset[str] = frozenset(load_meta()["clientMethods"].values())
"""Wire methods the client must be able to handle (agent -> client), requests and notifications
alike."""

PROTOCOL_METHODS: frozenset[str] = frozenset(load_meta()["protocolMethods"].values())
"""Bidirectional protocol-level notifications (`$/cancel_request`)."""

AGENT_NOTIFICATIONS: frozenset[str] = _notification_methods("ClientNotification") & AGENT_METHODS
"""Subset of `AGENT_METHODS` that are notifications, not requests (`session/cancel`)."""

CLIENT_NOTIFICATIONS: frozenset[str] = _notification_methods("AgentNotification") & CLIENT_METHODS
"""Subset of `CLIENT_METHODS` that are notifications, not requests (`session/update`,
`elicitation/complete`)."""

KNOWN_METHODS: frozenset[str] = AGENT_METHODS | CLIENT_METHODS | PROTOCOL_METHODS
"""The full "known method" union across all three inventories. v1's schema has the same three
top-level branches (`Agent`/`Client`/`ProtocolLevel`) and `tck.v1.protocol` already defines its
own `PROTOCOL_METHODS`; `KNOWN_METHODS` itself is simply a new convenience union v1 never
needed, not a consequence of v2 having a branch v1 lacks."""
