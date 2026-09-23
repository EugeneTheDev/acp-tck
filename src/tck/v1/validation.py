"""Schema validation for JSON-RPC messages the agent under test writes to stdout.

Backed by the vendored `tck/v1/schema/schema.json` (see `tck/v1/schema/VENDORED.md`). The
schema's top-level shape is `anyOf` of three side-annotated envelopes -- `Agent`, `Client`,
`ProtocolLevel` (`schema/v1/schema.json:4-119`) -- each further split into `Request` /
`Response` / `Notification` branches. Every method-specific params/response `$def` carries
`x-side` (which side implements the method) and `x-method` (its wire name); those annotations
are what let us look up "the schema for `session/prompt`'s response" instead of hand-copying
tables from the spec.

This module only validates messages the *agent* authors: agent -> client requests/notifications
(`x-side: "client"` methods, e.g. `fs/read_text_file`) and agent -> client
requests/notifications the agent itself implements ... i.e. responses to methods the agent
handles (`x-side: "agent"`, e.g. `initialize`), plus the bidirectional `$/cancel_request`
notification. It never validates a message the *client* authored (e.g. a `fs/write_text_file`
*response*, which the TCK's own mock client writes) -- there is no `validate_client_message`;
add one only if a future requirement needs to assert on the harness's own outgoing traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from .protocol import load_schema

_DRAFT_VALIDATORS: dict[str, type[jsonschema.protocols.Validator]] = {
    "https://json-schema.org/draft/2020-12/schema": Draft202012Validator,
}


@dataclass(frozen=True)
class ValidationIssue:
    """One schema (or envelope) violation found in a message."""

    path: str
    """JSON pointer (e.g. `/result/protocolVersion`) to the offending value, `""` for the
    message root."""
    message: str
    """Human-readable description of the violation."""
    schema_path: str
    """JSON pointer into the schema (or a fixed literal for hand-written envelope checks) that
    the value failed to satisfy."""


def _validator_class() -> type[jsonschema.protocols.Validator]:
    dialect = load_schema()["$schema"]
    validator_class = _DRAFT_VALIDATORS.get(dialect)
    if validator_class is None:
        raise RuntimeError(
            f"vendored schema.json declares $schema={dialect!r}, which this module does not "
            "have a jsonschema Draft validator mapped for -- add one to _DRAFT_VALIDATORS"
        )
    return validator_class


def _pointer(path_parts: Any) -> str:
    return "/" + "/".join(str(p) for p in path_parts) if path_parts else ""


@lru_cache(maxsize=None)
def _def_validator(def_name: str) -> jsonschema.protocols.Validator:
    """A `Validator` for `#/$defs/{def_name}`, self-contained (the wrapper schema carries the
    full `$defs` map alongside the `$ref`), so every internal `$ref` resolves without a
    separate `Registry`.
    """
    full = load_schema()
    wrapper = {
        "$schema": full["$schema"],
        "$ref": f"#/$defs/{def_name}",
        "$defs": full["$defs"],
    }
    validator_class = _validator_class()
    validator_class.check_schema(wrapper)
    return validator_class(wrapper)


def _issues_from_errors(errors: Any) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            path=_pointer(list(error.absolute_path)),
            message=error.message,
            schema_path=_pointer(list(error.absolute_schema_path)),
        )
        for error in errors
    ]


@lru_cache(maxsize=1)
def _request_and_notification_method_defs() -> dict[str, str]:
    """`{wire_method: def_name}` for every params `$def` an agent-authored message can carry:
    agent -> client requests (`AgentRequest`), agent -> client notifications
    (`AgentNotification`), and the bidirectional `$/cancel_request` notification
    (`ProtocolLevel`). Extension (`_*`) methods are excluded -- their schema (`ExtRequest` /
    `ExtNotification`) carries no fixed shape by design.
    """
    defs = load_schema()["$defs"]
    mapping: dict[str, str] = {}
    for envelope_name in ("AgentRequest", "AgentNotification"):
        envelope = defs[envelope_name]
        for ref_name in _ref_names_under(envelope.get("properties", {}).get("params", {})):
            method = defs.get(ref_name, {}).get("x-method")
            if method:
                mapping[method] = ref_name
    # `$/cancel_request` lives under the third top-level branch, `ProtocolLevel`.
    cancel_request_method = defs.get("CancelRequestNotification", {}).get("x-method")
    if cancel_request_method:
        mapping[cancel_request_method] = "CancelRequestNotification"
    return mapping


@lru_cache(maxsize=1)
def _response_method_defs() -> dict[str, str]:
    """`{wire_method: def_name}` for every method the agent implements, mapping to the
    `$def` of its *successful* response (`AgentResponse`'s `Result` branch).
    """
    defs = load_schema()["$defs"]
    # Select the branch by content (`properties` containing `result`), not position -- a schema
    # refresh reordering `AgentResponse`'s `anyOf` must not silently empty this mapping out.
    result_branch = next(
        branch for branch in defs["AgentResponse"]["anyOf"] if "result" in branch.get("properties", {})
    )
    result_variants = result_branch["properties"]["result"]["anyOf"]
    mapping: dict[str, str] = {}
    for variant in result_variants:
        for ref_name in _ref_names_under(variant):
            method = defs.get(ref_name, {}).get("x-method")
            if method:
                mapping[method] = ref_name
    return mapping


def _ref_names_under(node: Any) -> list[str]:
    names: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            names.append(ref.removeprefix("#/$defs/"))
        for value in node.values():
            names.extend(_ref_names_under(value))
    elif isinstance(node, list):
        for item in node:
            names.extend(_ref_names_under(item))
    return names


def _response_schema_permits_null(def_name: str) -> bool:
    """True if `#/$defs/{def_name}` is an object type with no required properties, in which
    case `null` and `{}` are equivalent in practice even though the schema only spells out
    `{}`. Quirk: `session/load`'s and `fs/write_text_file`'s docs show `"result": null`, but
    their schema `$def`s are `type: "object"` with no required fields, which literally rejects
    `null`.
    """
    definition = load_schema()["$defs"].get(def_name, {})
    return definition.get("type") == "object" and not definition.get("required")


def _validate_error_envelope(error: Any, base_path: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(error, dict):
        return [
            ValidationIssue(
                path=_pointer(base_path),
                message=f"error must be an object, got {type(error).__name__}",
                schema_path="#/$defs/Error/type",
            )
        ]
    code = error.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        issues.append(
            ValidationIssue(
                path=_pointer(base_path + ["code"]),
                message=f"error.code must be an integer, got {code!r}",
                schema_path="#/$defs/Error/properties/code",
            )
        )
    message = error.get("message")
    if not isinstance(message, str):
        issues.append(
            ValidationIssue(
                path=_pointer(base_path + ["message"]),
                message=f"error.message must be a string, got {message!r}",
                schema_path="#/$defs/Error/properties/message",
            )
        )
    return issues


def _is_valid_request_id(value: Any) -> bool:
    """`RequestId` (`schema/v1/schema.json:245-264`) is `null | integer | string`."""
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_jsonrpc_field(msg: dict[str, Any]) -> list[ValidationIssue]:
    if msg.get("jsonrpc") != "2.0":
        return [
            ValidationIssue(
                path="/jsonrpc",
                message=f'jsonrpc must be the literal string "2.0", got {msg.get("jsonrpc")!r}',
                schema_path="#/properties/jsonrpc",
            )
        ]
    return []


def validate_agent_message(msg: dict[str, Any]) -> list[ValidationIssue]:
    """Validate one parsed JSON-RPC message the agent wrote to stdout.

    Dispatches on shape, never on caller-supplied context:

    - has `method` and `id` -> agent -> client (or `$/cancel_request`) *request*: validate
      `params` against that method's params schema.
    - has `method`, no `id` -> notification: same, against the notification's params schema.
    - no `method` -> *response*: only the JSON-RPC envelope is checked here (`result` XOR
      `error`, `id` present, error shape) -- validating `result` against a method-specific
      response schema requires knowing which request it answers, so use
      `validate_agent_response(method, msg)` for that.

    Never raises on malformed input; unrecognized shapes come back as issues.
    """
    if not isinstance(msg, dict):
        return [
            ValidationIssue(
                path="", message=f"message must be a JSON object, got {type(msg).__name__}", schema_path=""
            )
        ]

    issues = _validate_jsonrpc_field(msg)

    if "method" not in msg:
        return issues + validate_response_envelope(msg)

    method = msg.get("method")
    if not isinstance(method, str):
        issues.append(
            ValidationIssue(
                path="/method",
                message=f"method must be a string, got {method!r}",
                schema_path="#/properties/method",
            )
        )
        return issues

    if method.startswith("_"):
        # Extension methods carry no fixed shape by design (extensibility.mdx).
        return issues

    method_defs = _request_and_notification_method_defs()
    def_name = method_defs.get(method)
    if def_name is None:
        issues.append(
            ValidationIssue(
                path="/method",
                message=f"{method!r} is not a known agent-authored request/notification method",
                schema_path="",
            )
        )
        return issues

    params = msg.get("params")
    validator = _def_validator(def_name)
    issues.extend(_issues_from_errors(validator.iter_errors(params if params is not None else {})))
    return issues


def validate_response_envelope(msg: dict[str, Any]) -> list[ValidationIssue]:
    """Validate the JSON-RPC response envelope only: `id` present and a valid `RequestId`,
    exactly one of `result`/`error`, and (for an error) the shared `Error` shape. This is the
    mandatory-path evidence for ACP-JSONRPC-002 -- it applies to *any* response, so callers can
    run it over `initialize`'s response or any other response that MUST exist, rather than
    relying on a reply to an unrecognised method (which is only SHOULD)."""
    issues: list[ValidationIssue] = []
    if "id" not in msg:
        issues.append(
            ValidationIssue(path="/id", message="response is missing required field 'id'", schema_path="")
        )
    elif not _is_valid_request_id(msg["id"]):
        issues.append(
            ValidationIssue(
                path="/id",
                message=f"id must be a string, integer, or null (RequestId), got {msg['id']!r}",
                schema_path="#/$defs/RequestId",
            )
        )
    has_result = "result" in msg
    has_error = "error" in msg
    if has_result and has_error:
        issues.append(
            ValidationIssue(
                path="",
                message="response must not have both 'result' and 'error'",
                schema_path="",
            )
        )
    elif not has_result and not has_error:
        issues.append(
            ValidationIssue(
                path="",
                message="response must have exactly one of 'result' or 'error'",
                schema_path="",
            )
        )
    if has_error:
        issues.extend(_validate_error_envelope(msg.get("error"), ["error"]))
    return issues


@lru_cache(maxsize=None)
def _allowed_root_properties(def_name: str) -> set[str] | None:
    """The set of property names permitted at the root of `#/$defs/{def_name}`, resolved by
    walking `allOf`/`anyOf`/`oneOf`/`$ref` (needed for ACP-SCHEMA-002: the vendored schema has
    no `additionalProperties: false` anywhere, so this comparison has to be built by hand
    instead of relying on jsonschema to reject extras).

    Returns `None` if no branch in the composition ever declares a non-empty `properties` map
    (e.g. `def_name` is a bare scalar/array `$def` like `RequestId`) -- there is nothing
    meaningful to compare an object's keys against in that case, and the caller should skip the
    check rather than flag every key as unknown.
    """
    defs = load_schema()["$defs"]
    seen: set[str] = set()
    allowed: set[str] = set()
    found_any_properties = False

    def _walk(node: Any) -> None:
        nonlocal found_any_properties
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.removeprefix("#/$defs/")
            if name not in seen:
                seen.add(name)
                _walk(defs.get(name, {}))
            # JSON Schema 2020-12 allows keywords alongside `$ref` on the same node -- fall
            # through to the sibling handling below instead of returning, so a `properties`/
            # `allOf`/etc. next to a `$ref` isn't silently dropped.
        props = node.get("properties")
        if isinstance(props, dict) and props:
            found_any_properties = True
            allowed.update(props.keys())
        for key in ("allOf", "anyOf", "oneOf"):
            branches = node.get(key)
            if isinstance(branches, list):
                for branch in branches:
                    _walk(branch)

    _walk(defs.get(def_name, {}))
    if not found_any_properties:
        return None
    allowed.add("_meta")
    return allowed


def find_unknown_root_keys(def_name: str, obj: Any) -> list[str]:
    """ACP-SCHEMA-002 (ADVISORY): the root-level keys of an emitted spec object (`obj`, e.g. a
    request/notification `params`, or a successful response `result`) that are not part of
    `#/$defs/{def_name}`'s resolved `properties` union (`_meta` is always allowed, per Req 41's
    "custom data goes in `_meta`" carve-out). Returns `[]` -- nothing to flag -- when `obj` is
    not a dict, or when `def_name`'s schema has no resolvable `properties` at all.
    """
    if not isinstance(obj, dict):
        return []
    allowed = _allowed_root_properties(def_name)
    if allowed is None:
        return []
    return sorted(key for key in obj if key not in allowed)


def validate_agent_response(method: str, msg: dict[str, Any]) -> list[ValidationIssue]:
    """Validate a response the agent wrote to stdout, in reply to a `method` request it
    implements (e.g. `"initialize"`, `"session/prompt"`).

    Validates the JSON-RPC envelope (`validate_response_envelope`) plus, for a successful
    response, `result` against `method`'s specific response schema. For an error response,
    `error` is checked against the hand-written envelope only (`code` an integer, `message` a
    string) -- not the full `Error` schema; `data` is never inspected, since it may be absent
    or `null` without asserting its shape.
    """
    if not isinstance(msg, dict):
        return [
            ValidationIssue(
                path="", message=f"message must be a JSON object, got {type(msg).__name__}", schema_path=""
            )
        ]

    issues = _validate_jsonrpc_field(msg) + validate_response_envelope(msg)

    if "error" in msg and "result" not in msg:
        return issues

    if "result" not in msg:
        return issues

    response_defs = _response_method_defs()
    def_name = response_defs.get(method)
    if def_name is None:
        issues.append(
            ValidationIssue(
                path="/result",
                message=f"{method!r} is not a known method the agent implements a response for",
                schema_path="",
            )
        )
        return issues

    result = msg["result"]
    if result is None and _response_schema_permits_null(def_name):
        # Quirk: docs show `null` for all-optional object responses; treat as equivalent to `{}`.
        return issues

    validator = _def_validator(def_name)
    issues.extend(_issues_from_errors(validator.iter_errors(result)))
    return issues
