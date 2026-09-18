"""The ACP TCK requirement registry.

Every conformance assertion the TCK makes is backed by exactly one `Requirement` here, keyed
by a stable id (`ACP-<AREA>-<NNN>`). Requirements are *declared*, not derived from code, because
they encode a judgment call about spec text (tier, capability gating) that the schema itself
does not carry. `text`/`citation` are taken from `.agents/research/*.md`, the reports that are
this package's specification -- see each entry's `source_report` and `citation` before changing
wording, not memory of the spec.

Conformance tests bind to a requirement via `@pytest.mark.requirement("ACP-…")` (see
`tck.plugin`). Two meta-tests (`tests/test_registry.py`) keep this registry and the test suite
in sync: every marker id must exist here, and every id here must be referenced by at least one
test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .protocol import SCHEMA_REVISION

SPEC_REVISION = SCHEMA_REVISION
"""The spec commit every citation below is relative to (see `AGENTS.md` "Vendored schema" and
`.agents/research/*.md` headers). Single source of truth is `tck.protocol.SCHEMA_REVISION`."""


class Tier(Enum):
    MANDATORY = "MANDATORY"
    CAPABILITY = "CAPABILITY"
    ADVISORY = "ADVISORY"
    INFORMATIONAL = "INFORMATIONAL"


@dataclass(frozen=True)
class Requirement:
    """One conformance requirement the TCK can test for.

    `capability` is a JSON path under the `initialize` result (e.g.
    `agentCapabilities.loadSession`) that gates whether the requirement even applies; it is
    required iff `tier is Tier.CAPABILITY` and must be `None` otherwise.
    """

    id: str
    tier: Tier
    capability: str | None
    text: str
    citation: str
    source_report: str

    def __post_init__(self) -> None:
        if self.tier is Tier.CAPABILITY and not self.capability:
            raise ValueError(f"{self.id}: tier is CAPABILITY but no capability path was given")
        if self.tier is not Tier.CAPABILITY and self.capability is not None:
            raise ValueError(f"{self.id}: tier is {self.tier.value}, not CAPABILITY, but capability={self.capability!r}")


def _cite(path_and_lines: str) -> str:
    return f"{path_and_lines} @ {SPEC_REVISION}"


_DECLARATIONS: tuple[Requirement, ...] = (
    Requirement(
        id="ACP-TRANSPORT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text="Every line the agent writes to stdout is a single valid JSON-RPC 2.0 message.",
        citation=_cite("docs/protocol/v1/transports.mdx:24,26"),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-TRANSPORT-002",
        tier=Tier.MANDATORY,
        capability=None,
        text="The agent's stdout is valid UTF-8.",
        citation=_cite("docs/protocol/v1/transports.mdx:6"),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-JSONRPC-001",
        tier=Tier.MANDATORY,
        capability=None,
        text="A response's `id` echoes the request `id` exactly, for both integer and string ids.",
        citation=_cite("agent-client-protocol-schema/src/rpc.rs:12-39,245-289"),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-JSONRPC-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A response carries exactly one of `result`/`error`; an error object has an "
            "integer `code` and a string `message`."
        ),
        citation=_cite(
            "docs/protocol/v1/overview.mdx:219-223; agent-client-protocol-schema/src/v1/error.rs:149-224"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-JSONRPC-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Notifications never receive a response, success or error. Concluding \"no "
            "response arrived\" is inherently a heuristic wait (a quiet period derived from "
            "--tck-timeout, not an infinite one) -- see tck.conformance._helpers.quiet_period."
        ),
        citation=_cite(
            "docs/protocol/v1/overview.mdx:223; agent-client-protocol-schema/src/v1/error.rs:9"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-JSONRPC-004",
        tier=Tier.ADVISORY,
        capability=None,
        text="An unknown method yields error `-32601` (spec wording is \"should\").",
        citation=_cite("docs/protocol/v1/extensibility.mdx:80-92"),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-JSONRPC-005",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "After an erroneous request, the connection remains usable (subsequent requests "
            "still succeed)."
        ),
        citation=_cite(
            "docs/protocol/v1/overview.mdx:219-223 (J1), docs/protocol/v1/extensibility.mdx:80-92 (J6); "
            "de-facto rule inferred from reference-SDK regression tests, not normative spec text -- "
            "rust-sdk src/agent-client-protocol/tests/jsonrpc_error_handling.rs:634-708,824-911, "
            "python-sdk tests/test_rpc.py:480-526 (Testability note 7)"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-INIT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text="`initialize` succeeds and the result validates against the schema, with an integer `protocolVersion`.",
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:54; schema/v1/schema.json:2340-2407"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-INIT-002",
        tier=Tier.MANDATORY,
        capability=None,
        text="When the client requests protocol version 1, the agent returns 1.",
        citation=_cite("docs/protocol/v1/initialization.mdx:96"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-INIT-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "When the client requests an unsupported protocol version (65535), the agent "
            "returns a successful result carrying its latest supported version, not an error."
        ),
        citation=_cite("docs/protocol/v1/initialization.mdx:94-98"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-INIT-004",
        tier=Tier.ADVISORY,
        capability=None,
        text="`agentInfo` with `name` and `version` is present in the `initialize` result.",
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:54,271; schema/v1/schema.json:2813-2838"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-SCHEMA-001",
        tier=Tier.MANDATORY,
        capability=None,
        text="Every message the agent emits during a basic exchange validates against the vendored v1 schema.",
        citation=_cite("schema/v1/schema.json:5-42 (Testability notes)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-SESSION-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "`session/new` with an absolute `cwd` and `mcpServers: []` succeeds with a "
            "non-empty string `sessionId`, and the response validates against the schema."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:71; schema/v1/schema.json:2867-2910 "
            "(Req 9; Testability notes 'session/new with an absolute cwd...')"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-SESSION-002",
        tier=Tier.MANDATORY,
        capability=None,
        text="Two `session/new` calls on the same connection return distinct `sessionId`s.",
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:71; schema/v1/schema.json:2867-2910 (Req 9 'unique')"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-PROMPT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A text-only `session/prompt` resolves with a successful result whose `stopReason` "
            "is one of the defined `StopReason` values."
        ),
        citation=_cite(
            "docs/protocol/v1/prompt-turn.mdx:217; schema/v1/schema.json:3424-3476 (Req 24); "
            "docs/protocol/v1/initialization.mdx:204, docs/protocol/v1/content.mdx:31 (baseline "
            "text support, Req 7)"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-PROMPT-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every `session/update` notification emitted during a prompt turn validates "
            "against the schema and carries the `sessionId` of the session being prompted. "
            "An agent that emits no updates during the turn is allowed (Req 1 places no MUST "
            "on emitting them, only on being *able* to send them); this test passes vacuously "
            "in that case."
        ),
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:245 (Req 1); schema/v1/schema.json:3622 "
            "(SessionNotification); Testability notes 'Weakly assertable' first bullet"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-PROMPT-003",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A prompt containing a `resource_link` content block alongside text is accepted. "
            "Advisory, not mandatory: `initialization.mdx:204` lists `resource_link` as baseline "
            "MUST-accept alongside text, but `content.mdx:31` says only text is MUST -- treated "
            "as advisory until upstream resolves the discrepancy."
        ),
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:204 vs docs/protocol/v1/content.mdx:31 "
            "(Req 7; Discrepancy 2)"
        ),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-CANCEL-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "After `session/cancel` during an in-flight `session/prompt`, the prompt request "
            "resolves with a successful result whose `stopReason` is `cancelled`, not an error."
        ),
        citation=_cite("docs/protocol/v1/prompt-turn.mdx:332,339 (Reqs 25, 26)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-CANCEL-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every `session/update` for the cancelled session arrives before the `session/prompt` "
            "response; none arrive after it. \"None arrive after it\" is checked with a quiet "
            "period derived from --tck-timeout (tck.conformance._helpers.quiet_period), not an "
            "infinite wait."
        ),
        citation=_cite("docs/protocol/v1/prompt-turn.mdx:343 (Req 28)"),
        source_report="acp-v1-protocol-surface.md",
    ),
)

REGISTRY: dict[str, Requirement] = {requirement.id: requirement for requirement in _DECLARATIONS}


def get(requirement_id: str) -> Requirement:
    """Look up a requirement by id, raising a helpful `KeyError` if it is not registered."""
    try:
        return REGISTRY[requirement_id]
    except KeyError:
        raise KeyError(
            f"{requirement_id!r} is not a registered requirement id; known ids: "
            f"{sorted(REGISTRY)}"
        ) from None
