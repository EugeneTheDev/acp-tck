"""Schema validation for JSON-RPC messages the agent under test writes to stdout, against the
vendored ACP v2 (Draft) schema (`tck/v2/schema/schema.json`, see `VENDORED.md`).

Mirrors `tck.v1.validation`'s API (`validate_agent_message`, `validate_agent_response`,
`find_unknown_root_keys`) but is its own module, not shared code -- v2 differs from v1 in three
ways this module encodes:

1. **Batching.** v2's top-level schema adds four batch-call/-response branches alongside the
   three v1-style single-message branches (`Agent`/`Client`/`ProtocolLevel`) -- a bare JSON
   array is a valid top-level line, but an *empty* array is not. `validate_agent_message`/
   `validate_agent_response` dispatch on shape: a `dict` is one message; a non-empty `list` is a
   batch, validated element-by-element (each issue's `path` prefixed with `/<index>`); an empty
   `list` is itself one issue.
2. **No `null` response special case.** v1 special-cased `result: null` for method responses
   whose schema is an all-optional object (a documented docs/schema mismatch, Discrepancy 3).
   No v2 `*Response` `$def` is nullable (checked directly against the vendored schema), so this
   module does not carry that special case over -- a `null` result is validated as-is and fails
   against any `type: "object"` response schema, as it structurally should.
3. **Open-enum discriminator carve-out for `find_unknown_root_keys`.** Several v2 discriminated
   unions (`ContentBlock`, `AuthMethod`, `SessionUpdate`, ...) have an `"other"`-titled fallback
   branch for custom/future variants -- the same "custom values MUST begin with `_`" rule
   `tck.v2.protocol.is_valid_open_enum_value` enforces for plain open enums, but for whole
   objects. When `find_unknown_root_keys` sees such a union and the object's discriminator is a
   `_`-prefixed string not matching any named branch's const, it legitimately uses the open
   fallback and the check is skipped (`[]`) instead of flagging extra fields. A missing/`null`/
   non-`_`-prefixed discriminator does not count, so a malformed discriminator can't dodge the
   check.
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
    message root. For a batch element, prefixed with `/<index>`."""
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


def _prefix_issues(prefix: str, issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [
        ValidationIssue(path=f"{prefix}{issue.path}", message=issue.message, schema_path=issue.schema_path)
        for issue in issues
    ]


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
    (`ProtocolLevel`). Extension (`_*`) methods are excluded -- their schema (`Ext*` defs)
    carries no fixed shape by design.
    """
    defs = load_schema()["$defs"]
    mapping: dict[str, str] = {}
    for envelope_name in ("AgentRequest", "AgentNotification"):
        envelope = defs[envelope_name]
        for ref_name in _ref_names_under(envelope.get("properties", {}).get("params", {})):
            method = defs.get(ref_name, {}).get("x-method")
            if method:
                mapping[method] = ref_name
    # `$/cancel_request` lives under the third top-level single-message branch, `ProtocolLevel`.
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
    # refresh that reorders `AgentResponse`'s `anyOf` must not silently map every method to the
    # error branch and empty this mapping out.
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
    """`RequestId` is `null | integer | string`, same as v1."""
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


def _empty_batch_issue() -> ValidationIssue:
    return ValidationIssue(
        path="",
        message="a batch array must not be empty",
        schema_path="#/anyOf (AgentBatchCall/AgentBatchResponse/ClientBatchCall/ClientBatchResponse)",
    )


def validate_agent_message(msg: Any) -> list[ValidationIssue]:
    """Validate one parsed line the agent wrote to stdout -- a single message (`dict`) or a
    non-empty JSON-RPC batch (`list`); an empty `list` is itself an issue.

    For a single message, dispatches on shape, never on caller-supplied context:

    - has `method` and `id` -> agent -> client (or `$/cancel_request`) *request*: validate
      `params` against that method's params schema.
    - has `method`, no `id` -> notification: same, against the notification's params schema.
    - no `method` -> *response*: only the JSON-RPC envelope is checked here (`result` XOR
      `error`, `id` present, error shape) -- validating `result` against a method-specific
      response schema requires knowing which request it answers, so use
      `validate_agent_response(method, msg)` for that.

    Never raises on malformed input; unrecognized shapes come back as issues.
    """
    if isinstance(msg, list):
        if not msg:
            return [_empty_batch_issue()]
        issues: list[ValidationIssue] = []
        for index, item in enumerate(msg):
            issues.extend(_prefix_issues(f"/{index}", validate_agent_message(item)))
        return issues

    if not isinstance(msg, dict):
        return [
            ValidationIssue(
                path="",
                message=f"message must be a JSON object or a non-empty batch array, got {type(msg).__name__}",
                schema_path="",
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
    exactly one of `result`/`error`, and (for an error) the shared `Error` shape. Applies to any
    single response message (not a batch -- see `validate_agent_response` for batch dispatch)."""
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
    walking `allOf`/`anyOf`/`oneOf`/`$ref` (needed because the vendored schema has no
    `additionalProperties: false` anywhere, same as v1).

    Returns `None` if no branch in the composition ever declares a non-empty `properties` map
    (e.g. `def_name` is a bare scalar/array `$def`) -- there is nothing meaningful to compare an
    object's keys against in that case, and the caller should skip the check rather than flag
    every key as unknown.
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


def _discriminator_property(named_branches: list[dict[str, Any]]) -> str | None:
    """If every branch in `named_branches` (i.e. every branch of a union *except* its `"other"`
    fallback) declares exactly one property with a `const` value, and they all agree on the
    same property *name*, return that name -- the discriminator field the union is keyed on.
    `None` if the branches don't agree on a single such property (the union isn't a simple
    single-field discriminated union, so the open-fallback carve-out below does not apply)."""
    discriminator: str | None = None
    for branch in named_branches:
        const_props = [
            name
            for name, sub in branch.get("properties", {}).items()
            if isinstance(sub, dict) and "const" in sub
        ]
        if len(const_props) != 1:
            return None
        if discriminator is None:
            discriminator = const_props[0]
        elif discriminator != const_props[0]:
            return None
    return discriminator


def _matches_open_fallback_branch(def_name: str, obj: dict[str, Any]) -> bool:
    """True iff `#/$defs/{def_name}` is a discriminated union with an `"other"`-titled fallback
    branch, and `obj` legitimately uses it: the discriminator is present, a `_`-prefixed string,
    and doesn't match any named branch's const (module docstring point 3). Anything else --
    missing/`null`/non-string/unknown-without-`_`-prefix -- is not the fallback.
    """
    branches = load_schema()["$defs"].get(def_name, {}).get("anyOf")
    if not isinstance(branches, list):
        return False
    named_branches = [b for b in branches if b.get("title") != "other"]
    if len(named_branches) == len(branches):
        return False  # no "other" branch at all
    discriminator = _discriminator_property(named_branches)
    if discriminator is None:
        return False
    named_consts = {
        branch["properties"][discriminator]["const"]
        for branch in named_branches
        if "const" in branch.get("properties", {}).get(discriminator, {})
    }
    value = obj.get(discriminator)
    return isinstance(value, str) and value.startswith("_") and value not in named_consts


def find_unknown_root_keys(def_name: str, obj: Any) -> list[str]:
    """The root-level keys of an emitted spec object (`obj`, e.g. a request/notification
    `params`, or a successful response `result`) that are not part of `#/$defs/{def_name}`'s
    resolved `properties` union (`_meta` is always allowed). Returns `[]` -- nothing to flag --
    when `obj` is not a dict, when `def_name`'s schema has no resolvable `properties` at all, or
    when `obj` matches `def_name`'s open `"other"` fallback branch (module docstring point 3).
    """
    if not isinstance(obj, dict):
        return []
    if _matches_open_fallback_branch(def_name, obj):
        return []
    allowed = _allowed_root_properties(def_name)
    if allowed is None:
        return []
    return sorted(key for key in obj if key not in allowed)


def validate_agent_response(method: str, msg: Any) -> list[ValidationIssue]:
    """Validate a response (or non-empty batch of responses) the agent wrote to stdout, in
    reply to a `method` request it implements (e.g. `"initialize"`, `"session/prompt"`).

    Validates the JSON-RPC envelope (`validate_response_envelope`) plus, for a successful
    response, `result` against `method`'s specific response schema. For an error response,
    `error` is checked against the hand-written envelope only (`code` an integer, `message` a
    string) -- not the full `Error` schema, and `data` is never inspected.

    Unlike `tck.v1.validation`, a `result` of `null` is never special-cased: no v2 `*Response`
    `$def` is nullable, so `null` is validated as-is and fails against any `type: "object"`
    response schema, as it structurally should (module docstring point 2).
    """
    if isinstance(msg, list):
        if not msg:
            return [_empty_batch_issue()]
        issues: list[ValidationIssue] = []
        for index, item in enumerate(msg):
            issues.extend(_prefix_issues(f"/{index}", validate_agent_response(method, item)))
        return issues

    if not isinstance(msg, dict):
        return [
            ValidationIssue(
                path="",
                message=f"message must be a JSON object or a non-empty batch array, got {type(msg).__name__}",
                schema_path="",
            )
        ]

    issues = _validate_jsonrpc_field(msg) + validate_response_envelope(msg)

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
    validator = _def_validator(def_name)
    issues.extend(_issues_from_errors(validator.iter_errors(result)))
    return issues
