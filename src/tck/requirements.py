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

SPEC_REVISION = "6d08f412a7a1370d3cc9a124e3be3d6acf92641e"
"""The spec commit every citation below is relative to (see `AGENTS.md` "Vendored schema" and
`.agents/research/*.md` headers)."""


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
        text="Notifications never receive a response, success or error.",
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
