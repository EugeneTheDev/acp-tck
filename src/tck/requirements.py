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
            "returns a successful result carrying an integer protocolVersion that is not "
            "65535 and equals the version the same agent returns for a v1 request -- echoing "
            "the client's requested version verbatim is not conformant, even though it is a "
            "successful result with an integer protocolVersion (strengthened: both `testy` "
            "and `examples/echo_agent.py` echo 65535 verbatim and must FAIL this)."
        ),
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:94-98; testy-cross-check.md finding 1 "
            "(strengthening rationale)"
        ),
        source_report="acp-v1-protocol-surface.md; testy-cross-check.md",
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
    Requirement(
        id="ACP-LOAD-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.loadSession",
        text=(
            "`session/load` with a valid `sessionId`, `cwd`, and `mcpServers` succeeds with a "
            "schema-valid `LoadSessionResponse` object."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:104,108-186; "
            "schema/v1/schema.json:2419-2424,3215-3249,4944-4988 (C1, L1, L4)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-LOAD-002",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.loadSession",
        text=(
            "Every `session/update` belonging to the `session/load` replay arrives before the "
            "`session/load` response; none arrive after it. No claim is made about which "
            "`sessionUpdate` kinds, how many, or their fidelity -- L5 says that is unspecified."
        ),
        citation=_cite("docs/protocol/v1/session-setup.mdx:134,178 (L2, L3, L5)"),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-LOAD-003",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "The `session/load` empty result is `{}` (an object), not `null` -- the docs' "
            "historical `null` example was corrected upstream to `{}`. ADVISORY only: mandatory "
            "schema validation (ACP-LOAD-001) already treats `null` as equivalent for an "
            "all-optional object response (documented leniency, Discrepancy 2)."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:180-186; schema/v1/schema.json:3215-3249 "
            "(L4; Discrepancy 2)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-RESUME-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.resume",
        text=(
            "`session/resume` with `sessionId` and `cwd` (no `mcpServers`) succeeds with a "
            "schema-valid `ResumeSessionResponse` object."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:243; schema/v1/schema.json:5034-5078,3337-3371 "
            "(C2, R1, R3)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-RESUME-002",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.resume",
        text=(
            "No `session/update` carrying conversation history (`user_message_chunk`, "
            "`agent_message_chunk`, `agent_thought_chunk`) for the resumed session arrives "
            "before the `session/resume` response -- the prohibition is scoped to history "
            "updates in the pre-response window only, not to every update kind or to updates "
            "after the response."
        ),
        citation=_cite("docs/protocol/v1/session-setup.mdx:243 (R2)"),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-LIST-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.list",
        text=(
            "`session/list` with `params: {}` succeeds with a schema-valid "
            "`ListSessionsResponse` whose `sessions` field is present as an array."
        ),
        citation=_cite(
            "docs/protocol/v1/session-list.mdx:82,94; schema/v1/schema.json:4989-5010,3250-3322 "
            "(C2, S1, S3, S4)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-LIST-002",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.list",
        text=(
            "`session/list` filtered by a `cwd` that no session uses returns `sessions: []` "
            "(an empty array, never `null`, never an error)."
        ),
        citation=_cite(
            "docs/protocol/v1/session-list.mdx:84-87,166; schema/v1/schema.json:4993-4996 "
            "(S2, S5)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-DELETE-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.delete",
        text=(
            "`session/delete` for a session created earlier on the same connection succeeds "
            "with a schema-valid empty-object result."
        ),
        citation=_cite(
            "docs/protocol/v1/session-delete.mdx:69-81; "
            "schema/v1/schema.json:5011-5033,3323-3336 (C2, D1)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-DELETE-002",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Deleting an already-deleted or never-created `sessionId` SHOULD succeed silently, "
            "rather than erroring."
        ),
        citation=_cite("docs/protocol/v1/session-delete.mdx:86 (D2)"),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-CLOSE-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.close",
        text=(
            "`session/close` for an existing, idle session succeeds with a schema-valid "
            "empty-object result."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:295-308; "
            "schema/v1/schema.json:5079-5101,3372-3385 (C2, X1)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-CLOSE-002",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.close",
        text=(
            "`session/close` on a session with an in-flight `session/prompt` cancels the "
            "ongoing work as if `session/cancel` had been called, so the prompt resolves with "
            "`stopReason: \"cancelled\"`. Derived obligation, medium confidence -- the spec "
            "states the cancel-as-if via X2 and never says \"close\" explicitly next to "
            "`stopReason`; inferred by reference to the cancellation contract (X3)."
        ),
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:299 -> docs/protocol/v1/prompt-turn.mdx:332,339,343 "
            "(X2, X3)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-ADDDIRS-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.sessionCapabilities.additionalDirectories",
        text="`session/new` with an absolute `additionalDirectories` entry is accepted.",
        citation=_cite(
            "docs/protocol/v1/session-setup.mdx:315-344; schema/v1/schema.json:4757-4765 "
            "(C2, A1, A2)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-MODES-001",
        tier=Tier.CAPABILITY,
        capability="inferred:modes",
        text=(
            "When `session/new` returns a non-null `modes`, it validates against the schema "
            "and `currentModeId` refers to one of `availableModes`. Inferred support, not a "
            "boolean/object marker in `initialize` -- there is no `agentCapabilities` field for "
            "this; support is inferred from `session/new`'s own response (`capability` is a "
            "documentation-only string, not a real initialize-result path -- see module "
            "docstring of `test_session_config.py`). SKIPs with reason 'session/new returned no "
            "modes/configOptions' when absent."
        ),
        citation=_cite(
            "docs/protocol/v1/session-modes.mdx; schema/v1/schema.json:2911-2944,2945-2974 "
            "(SessionModeState, SessionMode) (§7, §0)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-MODES-002",
        tier=Tier.CAPABILITY,
        capability="inferred:modes",
        text=(
            "`session/set_mode` to a different `modeId` succeeds. No echo notification is "
            "required (§7: \"do not assert an echo notification\"), but if a "
            "`current_mode_update` (`session/update` with `sessionUpdate: "
            "\"current_mode_update\"`) for the session is observed, it MUST carry the schema "
            "field name `currentModeId` -- the docs' `modeId` example "
            "(`session-modes.mdx:117-119`) is a confirmed docs bug; the schema wins."
        ),
        citation=_cite(
            "docs/protocol/v1/session-modes.mdx:117-119 (docs bug); "
            "schema/v1/schema.json:5102-5132,4129-4160 (SetSessionModeRequest, "
            "CurrentModeUpdate) (§7)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-CONFIG-001",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "When `session/new` returns a non-null `configOptions`, every entry's "
            "`currentValue` is valid per its declared type: a `boolean` entry's `currentValue` "
            "is a bool; a `select` entry's `currentValue` is one of its `options` (flat or "
            "grouped shape). Inferred support, same encoding as ACP-MODES-001 -- "
            "`capability=\"inferred:configOptions\"` is documentation-only."
        ),
        citation=_cite(
            "schema/v1/schema.json:2975-3399 (SessionConfigOption and its select/boolean "
            "variants) (§7, §0)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-CONFIG-002",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "`session/set_config_option` responds with the *complete* list of every "
            "previously-advertised `configOptions` id (not only the changed one), with the new "
            "value applied to the option that was changed -- stated as a MUST twice in the "
            "docs."
        ),
        citation=_cite(
            "schema/v1/schema.json:5133-5169,3400-3423 (SetSessionConfigOptionRequest/"
            "Response) (§7 'complete list' rule)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-CONFIG-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "An agent MUST NOT include a `type: \"boolean\"` config option anywhere in "
            "`session/new`'s `configOptions` unless the client advertised "
            "`clientCapabilities.session.configOptions.boolean: {}` -- Req 33, a genuine client- "
            "controlled MUST NOT. Passes vacuously if the agent has no config options, or none "
            "of `type: \"boolean\"`, at all."
        ),
        citation=_cite(
            "schema/v1/schema.json:2975-3399 (SessionConfigOption boolean variant) "
            "(Req 33; §7 boolean gating)"
        ),
        source_report="acp-v1-session-capabilities.md; acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-001",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.promptCapabilities.image",
        text=(
            "When `agentCapabilities.promptCapabilities.image` is `true`, a `session/prompt` "
            "containing an `image` content block (`ImageContent`: `data`, `mimeType`) alongside "
            "text resolves with a successful result whose `stopReason` is a defined value."
        ),
        citation=_cite(
            "schema/v1/schema.json:2480-2523 (PromptCapabilities), 765-802 (ImageContent) "
            "(§8, Req 8)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-002",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.promptCapabilities.audio",
        text=(
            "When `agentCapabilities.promptCapabilities.audio` is `true`, a `session/prompt` "
            "containing an `audio` content block (`AudioContent`: `data`, `mimeType`) alongside "
            "text resolves with a successful result whose `stopReason` is a defined value."
        ),
        citation=_cite(
            "schema/v1/schema.json:2480-2523 (PromptCapabilities), 803-838 (AudioContent) "
            "(§8, Req 8)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-PROMPTCAP-003",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.promptCapabilities.embeddedContext",
        text=(
            "When `agentCapabilities.promptCapabilities.embeddedContext` is `true`, a "
            "`session/prompt` containing a `resource` content block (`EmbeddedResource` "
            "wrapping a text or blob resource) alongside text resolves with a successful result "
            "whose `stopReason` is a defined value."
        ),
        citation=_cite(
            "schema/v1/schema.json:2480-2523 (PromptCapabilities), 965-1010 (EmbeddedResource) "
            "(§8, Req 8)"
        ),
        source_report="acp-v1-session-capabilities.md",
    ),
    Requirement(
        id="ACP-AUTH-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "When `initialize`'s `authMethods` is present, it is an array of schema-valid "
            "`AuthMethod` objects with unique `id`s (AUTH-M1/M2 in the auth report's assertion "
            "table). Schema shape itself is already covered by ACP-SCHEMA-001's full-exchange "
            "validation; this test adds the id-uniqueness check that schema validation alone "
            "does not express."
        ),
        citation=_cite(
            "schema/v1/schema.json:2702-2735,2783-2810 (AuthMethod, AuthMethodAgent) "
            "(AUTH-M1, AUTH-M2)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-AUTH-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "No `authMethods[*].type == \"terminal\"` entry is advertised unless the client "
            "advertised `clientCapabilities.auth.terminal` (Req 23, AUTH-M4) -- a client- "
            "controlled MUST NOT, checked by connecting once without that capability."
        ),
        citation=_cite(
            "schema/v1/schema.json:2736-2782 (AuthMethodTerminal) (Req 23; AUTH-M4)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-AUTH-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Capability-conditional (AUTH-C3/C4): only exercised when `authMethods` is "
            "non-empty AND `--tck-auth-method <id>` was given -- SKIPs otherwise, since v1 "
            "never requires an agent to expose a testable auth flow and the TCK cannot guess a "
            "valid `methodId`. When exercised: `authenticate` with that `methodId` succeeds "
            "with an object result, and a subsequent `session/new` on the same connection "
            "succeeds (not `-32000`)."
        ),
        citation=_cite(
            "schema/v1/schema.json:4712-4734 (AuthenticateRequest/Response) (AUTH-C3, AUTH-C4)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-AUTH-004",
        tier=Tier.CAPABILITY,
        capability="agentCapabilities.auth.logout",
        text=(
            "When `agentCapabilities.auth.logout` is advertised (object marker), `logout` "
            "succeeds with an object result (AUTH-C1/C2). Nothing is asserted about sessions "
            "after logout (must-NOT list) -- if `--tck-auth-method` was given, `logout` is "
            "called after a successful `authenticate`; otherwise it is called standalone and "
            "only its own success is checked."
        ),
        citation=_cite(
            "schema/v1/schema.json:2666-2701,4735-4756 (AgentAuthCapabilities, LogoutRequest) "
            "(AUTH-C1, AUTH-C2)"
        ),
        source_report="acp-v1-authentication.md",
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
