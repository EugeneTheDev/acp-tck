"""Protocol-level constants and method inventories for ACP.

Everything here is derived from the vendored spec artifacts in `tck/schema/v1/` (see
`tck/schema/v1/VENDORED.md` for provenance) rather than hand-copied from documentation, so a
schema refresh re-derives these automatically.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
"""The only ACP protocol version this TCK speaks.

This is a v1-only assumption baked into the whole package (see `AGENTS.md` "Protocol
scope"). A future v2 effort must find and update every place that reads this constant --
start here. Wire encoding is a bare JSON integer, not a version string
(`.agents/research/acp-v1-protocol-surface.md` §2).
"""

SCHEMA_DIR = Path(__file__).parent / "schema" / "v1"

SCHEMA_REVISION = "6d08f412a7a1370d3cc9a124e3be3d6acf92641e"
"""The spec commit the vendored `schema/v1/{schema,meta}.json` -- and every requirement
citation in `tck.requirements` -- are pinned to (see `schema/v1/VENDORED.md`). This is the
single place that constant lives; `tck.requirements.SPEC_REVISION` and `tck.report.Report`'s
`schema_revision` field both read it from here."""

# JSON-RPC / ACP error codes (schema/v1/schema.json `ErrorCode`, :3503-3569). Names follow
# the schema's own `title` for each variant.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
REQUEST_CANCELLED = -32800
AUTHENTICATION_REQUIRED = -32000
RESOURCE_NOT_FOUND = -32002

# `StopReason` values (schema/v1/schema.json `StopReason`, :3447-3476). Closed enum in v1.
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


@lru_cache(maxsize=1)
def load_meta() -> dict[str, Any]:
    """Parse `schema/v1/meta.json`.

    Real structure (verified against the vendored file): a `version` int, plus three flat
    `{internal_name: "wire/method"}` dicts -- `agentMethods` (methods the agent handles,
    requests and notifications alike, e.g. `session_cancel` -> `session/cancel`),
    `clientMethods` (methods the client handles, e.g. `session_update` -> `session/update`),
    and `protocolMethods` (bidirectional protocol-level notifications, just
    `cancel_request` -> `$/cancel_request`). It does not itself distinguish requests from
    notifications -- that split is derived from `schema.json` below.
    """
    return json.loads((SCHEMA_DIR / "meta.json").read_text())


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Parse `schema/v1/schema.json`."""
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

    Each variant $def carries its own `x-method` annotation (e.g. `SessionNotification` ->
    `session/update`); `ExtNotification` has none and is skipped since its method name is
    dynamic (`_`-prefixed, caller-chosen).
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
"""Wire methods the agent must be able to handle (client -> agent), requests and
notifications alike."""

CLIENT_METHODS: frozenset[str] = frozenset(load_meta()["clientMethods"].values())
"""Wire methods the client must be able to handle (agent -> client), requests and
notifications alike."""

PROTOCOL_METHODS: frozenset[str] = frozenset(load_meta()["protocolMethods"].values())
"""Bidirectional protocol-level notifications (`$/cancel_request`)."""

AGENT_NOTIFICATIONS: frozenset[str] = _notification_methods("ClientNotification") & AGENT_METHODS
"""Subset of `AGENT_METHODS` that are notifications, not requests (`session/cancel`)."""

CLIENT_NOTIFICATIONS: frozenset[str] = _notification_methods("AgentNotification") & CLIENT_METHODS
"""Subset of `CLIENT_METHODS` that are notifications, not requests (`session/update`,
`elicitation/complete`)."""
