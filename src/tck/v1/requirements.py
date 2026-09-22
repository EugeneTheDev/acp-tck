"""The ACP TCK requirement registry.

Every conformance assertion the TCK makes is backed by exactly one `Requirement` here, keyed
by a stable id (`ACP-<AREA>-<NNN>`). Requirements are *declared*, not derived from code, because
they encode a judgment call about spec text (tier, capability gating) that the schema itself
does not carry. `text`/`citation` are taken from `.agents/research/*.md`, the reports that are
this package's specification -- see each entry's `source_report` and `citation` before changing
wording, not memory of the spec.

Conformance tests bind to a requirement via `@pytest.mark.requirement("ACP-…")` (see
`tck.common.plugin`). Two meta-tests (`tests/v1/test_registry.py`) keep this registry and the test suite
in sync: every marker id must exist here, and every id here must be referenced by at least one
test.
"""

from __future__ import annotations

from ..common.requirements import Requirement, Tier, make_cite
from .protocol import SCHEMA_REVISION

SPEC_REVISION = SCHEMA_REVISION
"""The spec commit every citation below is relative to (see `AGENTS.md` "Vendored schema" and
`.agents/research/*.md` headers). Single source of truth is `tck.v1.protocol.SCHEMA_REVISION`."""

_cite = make_cite(SPEC_REVISION)


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
            "--tck-timeout, not an infinite one) -- see tck.v1.conformance._helpers.quiet_period."
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
            "returns a successful result carrying an integer protocolVersion that (a) is not "
            "65535 -- echoing the client's requested version verbatim is not conformant, even "
            "though it is a successful result with an integer protocolVersion -- and (b) is at "
            "least the version the same agent returns for a v1 request. Equality is NOT "
            "required: an agent that legitimately supports multiple versions (e.g. answers 1 "
            "for a v1 request and 2 for anything >= 2) may correctly answer higher than its "
            "v1-request answer; only echoing 65535 verbatim, or answering something lower than "
            "its own v1 answer, is a violation (review-slices-5-6.md B2 -- the prior equality "
            "rule produced a false FAIL against dual-version agents). The 65535 probe's params "
            "also carry a v2-shaped info object alongside the v1 fields, since the probe "
            "represents a future-version client and a dual-version router agent selects v2 for "
            "any requested version >= 2 (including 65535) and validates the params as a v2 "
            "InitializeRequest, whose info is REQUIRED -- omitting it would produce a spurious "
            "-32602 for a params-shape reason unrelated to version negotiation."
        ),
        citation=_cite(
            "docs/protocol/v1/initialization.mdx:94-98; testy-cross-check.md finding 1 "
            "(strengthening rationale); review-slices-5-6.md B2 (weakened to >=); "
            "acp-v2-version-negotiation.md:137,185 (router selects v2 for >=2 and requires "
            "info, spurious -32602 without it)"
        ),
        source_report="acp-v1-protocol-surface.md; testy-cross-check.md; acp-v2-version-negotiation.md",
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
            "period derived from --tck-timeout (tck.v1.conformance._helpers.quiet_period), not an "
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
            "all-optional object response (documented leniency, Discrepancy 2), and upstream "
            "`ac82df6` (`agent-client-protocol-schema/src/serde_util.rs`) made the Rust reference "
            "itself accept `null` for defaultable payloads, which is why `null` stays tolerated "
            "rather than becoming a FAIL."
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
            "field name `currentModeId` -- the docs' `modeId` example at "
            "`session-modes.mdx:117-119` was a confirmed docs bug at the vendored revision "
            "(`6d08f412`), since fixed upstream in `b96b439` (docs now show `currentModeId` "
            "too); the schema was always the source of truth here."
        ),
        citation=_cite(
            "docs/protocol/v1/session-modes.mdx:117-119 (docs bug at 6d08f412, fixed upstream "
            "in b96b439); schema/v1/schema.json:5102-5132,4129-4160 (SetSessionModeRequest, "
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
            "schema/v1/schema.json:2975-3399 (SessionConfigOption boolean variant); "
            "docs/protocol/v1/session-config-options.mdx:119-121 (normative MUST NOT text) "
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
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "When `initialize`'s `authMethods` is present, its entries' `id`s are unique "
            "(AUTH-A5). Schema shape itself (array-ness, `id`/`name` being present) is already "
            "covered by ACP-SCHEMA-001's full-exchange validation, and the test itself defers "
            "shape to it -- so the only thing this requirement actually asserts is uniqueness. "
            "ADVISORY, not MANDATORY: the schema only *describes* `id` as \"Unique identifier\" "
            "(a description, not a MUST), so AUTH-A5 is itself filed Advisory in the auth "
            "report's assertion table (review-slices-7.md S5 -- retiered from MANDATORY, where "
            "an agent with duplicate ids was forced NOT CONFORMANT on the strength of a schema "
            "description alone)."
        ),
        citation=_cite("schema/v1/schema.json:2740 (AuthMethod.id description) (AUTH-A5)"),
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
            "schema/v1/schema.json:2736-2782 (AuthMethodTerminal); "
            "docs/protocol/v1/authentication.mdx:126-128 (normative MUST NOT text) "
            "(Req 23; AUTH-M4)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-AUTH-003",
        tier=Tier.CAPABILITY,
        capability="inferred:authMethods",
        text=(
            "Capability-conditional (AUTH-C4), same documentation-only encoding as "
            "ACP-MODES-001/ACP-CONFIG-001 -- `capability=\"inferred:authMethods\"` is not a real "
            "`initialize`-result path; support is inferred from `authMethods` being non-empty "
            "AND `--tck-auth-method <id>` being given (review-slices-7.md S9: the entry's own "
            "text already said \"capability-conditional\" while the tier field said MANDATORY). "
            "SKIPs otherwise, since v1 never requires an agent to expose a testable auth flow "
            "and the TCK cannot guess a valid `methodId`. `authenticate` succeeding is NOT "
            "itself assertable (must-NOT list #10: a real agent may legitimately reject bad/"
            "expired/cancelled credentials) -- an `authenticate` error SKIPs with a distinct "
            "reason instead of failing. Only when `authenticate` returns a result is anything "
            "asserted, and only two things: (AUTH-C3, shape-only) the result is a JSON object; "
            "(AUTH-C4, the one hard assertion this requirement makes) a subsequent `session/new` "
            "on the same connection does not fail with `-32000`."
        ),
        citation=_cite(
            "schema/v1/schema.json:4712-4734 (AuthenticateRequest/Response) (AUTH-C3, AUTH-C4); "
            "acp-v1-authentication.md must-NOT list #10"
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
            "only its own success is checked. Only actually exercised when "
            "`--allow-logout`/`--tck-allow-logout` is given (destructive: may revoke the "
            "operator's own credentials); SKIPs otherwise."
        ),
        citation=_cite(
            "schema/v1/schema.json:2666-2701,4735-4756 (AgentAuthCapabilities, LogoutRequest) "
            "(AUTH-C1, AUTH-C2)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-AUTH-005",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "AUTH-A1: if `initialize`'s `authMethods` is empty or absent, `session/new` does "
            "not fail with `-32000`. Nothing in v1 requires an agent to gate anything behind "
            "`authenticate`, and `authMethods` is not required in `InitializeResponse`; an "
            "agent that advertises none and then returns -32000 has made the connection "
            "unusable with no defined remedy (v2 makes this rule explicit; v1 leaves it "
            "advisory). `skip_if_auth_gated` only excuses `-32000` when `authMethods` is "
            "non-empty -- with it empty/absent, the ordinary `session/new` assertion is left to "
            "fail on its own terms, which is deliberate (a broken agent legitimately fails "
            "whatever MANDATORY requirement needed that session, not just this one)."
        ),
        citation=_cite(
            "docs/protocol/v1/schema.mdx (InitializeResponse.authMethods optional) "
            "(AUTH-A1)"
        ),
        source_report="acp-v1-authentication.md",
    ),
    Requirement(
        id="ACP-CLIENTCAP-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The agent MUST NOT call `fs/read_text_file` or `fs/write_text_file` during a "
            "session/prompt turn when the client did not advertise `fs` support -- the mock "
            "client always advertises `clientCapabilities: {}`, so no `fs/*` request may ever "
            "be observed. PASS is vacuous for an agent that never needs file access."
        ),
        citation=_cite("docs/protocol/v1/file-system.mdx:10,28; schema/v1/schema.json:4550-4573 (Req 29)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-CLIENTCAP-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The agent MUST NOT call any `terminal/*` method during a session/prompt turn when "
            "the client did not advertise `clientCapabilities.terminal === true`. PASS is "
            "vacuous for an agent that never needs a terminal."
        ),
        citation=_cite("docs/protocol/v1/terminals.mdx:10,25 (Req 30)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-CLIENTCAP-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The agent MUST NOT call `elicitation/create` during a session/prompt turn when "
            "the client did not advertise any elicitation mode. PASS is vacuous for an agent "
            "that never elicits."
        ),
        citation=_cite("docs/protocol/v1/elicitation.mdx:54,107-108 (Req 32)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-EXT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A request to an unknown, `_`-prefixed custom method receives *some* response -- "
            "a result or any error, not necessarily `-32601`. Judgment call, resolved by the "
            "orchestrator (`.agents/plan.md` \"Decisions (orchestrator) -- from "
            "review-slices-7.md\"): Req 42's \"recipients must respond to custom requests\" "
            "(extensibility.mdx:43,52,65,109) is phrased as a MUST and covers custom requests in "
            "general, distinct from `acp-v1-transport-and-jsonrpc.md`'s J6, which tiers the "
            "*specific* `-32601` error code an unrecognised method gets as SHOULD -- so "
            "\"responds at all\" stays MANDATORY here (this is the one place the two research "
            "reports look like they disagree; they do not, they cover different observables: "
            "\"a response exists\" vs. \"which code it carries\"), while the specific code "
            "remains ACP-JSONRPC-004's ADVISORY concern under J6 (not duplicated here)."
        ),
        citation=_cite(
            "docs/protocol/v1/extensibility.mdx:43,52,65,109 (Req 42); cross-ref "
            "acp-v1-transport-and-jsonrpc.md J6 (the `-32601` code, not \"responds at all\", "
            "is what J6 tiers SHOULD)"
        ),
        source_report="acp-v1-protocol-surface.md; acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-META-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A `session/prompt` carrying `_meta` (e.g. a `traceparent` key, SHOULD-reserved by "
            "Req 43) is accepted and resolves with a normal, defined `stopReason`."
        ),
        citation=_cite("docs/protocol/v1/extensibility.mdx:10,33-37,39 (Reqs 41, 43)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-ERROR-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Every error object's `message` is non-empty and free of embedded newlines (E3: "
            "\"should be limited to a concise single sentence\" -- checked leniently, exact "
            "wording is never asserted); `data`, if present, needs no further shape check "
            "beyond already being valid JSON. Evidence comes from errors already provoked "
            "elsewhere in the suite (an unrecognised method, an invalid-params request); "
            "passes vacuously if the agent returns none."
        ),
        citation=_cite(
            "agent-client-protocol-schema/src/v1/error.rs:149-224 (E3)"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-SHUTDOWN-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "After the client closes stdin, the agent process exits on its own within a "
            "lenient window, without needing SIGTERM/SIGKILL. Warning-level only (Testability "
            "note 11): the spec defines no shutdown method, only that the client closes stdin "
            "then kills the process if needed."
        ),
        citation=_cite(
            "docs/protocol/v1/overview.mdx (no shutdown method defined; Testability note 11)"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-SCHEMA-002",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "No agent-emitted spec object (a request/notification `params`, or a successful "
            "response `result`) carries a root-level key outside its `$def`'s resolved "
            "`properties` union (following `allOf`/`anyOf`/`oneOf`/`$ref`), other than `_meta` "
            "-- Req 41 says implementations MUST NOT add custom root fields, a genuine MUST NOT. "
            "Downgraded to ADVISORY not because the underlying rule is soft, but because the "
            "check itself is: the vendored schema has no `additionalProperties: false` anywhere, "
            "so this is a hand-written approximation of the allowed-keys union (see "
            "`tck.v1.validation.find_unknown_root_keys`), and a false positive against a genuinely "
            "conforming agent would be an unrecoverable, unfair FAIL -- a testability-driven "
            "downgrade (review-slices-7.md N4), not a claim that Req 41 is itself only SHOULD/MAY."
        ),
        citation=_cite("docs/protocol/v1/extensibility.mdx:39 (Req 41)"),
        source_report="acp-v1-protocol-surface.md",
    ),
    Requirement(
        id="ACP-STDERR-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "The byte count of stderr output observed during a full exchange is reported for "
            "informational purposes; never asserted on itself (Testability note T6: the spec "
            "places no MUST on stderr content) -- but still FAILs if the prerequisite handshake "
            "(`initialize`, `session/new`) itself fails, since that is a real conformance problem "
            "the probe correctly surfaces (review-slices-7.md N2)."
        ),
        citation=_cite("docs/protocol/v1/transports.mdx (Testability note T6)"),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-INFO-PARSE-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Behaviour on a malformed (non-JSON) stdin line is recorded -- reply `-32700` with "
            "`id: null`, reply otherwise, or stay silent -- along with whether the connection "
            "remains usable afterwards (a subsequent `session/new` still succeeds). Spec "
            "silent; reference SDKs disagree (rust-sdk replies -32700, python-sdk silently "
            "drops the line). Never asserts on the probed behaviour itself, but still FAILs if "
            "the prerequisite `initialize` handshake fails (review-slices-7.md N2)."
        ),
        citation=_cite(
            "agent-client-protocol-schema (spec silent); rust-sdk vs python-sdk divergence "
            "(Assertable only as warnings/informational)"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-INFO-INVALIDREQ-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Behaviour on a syntactically-valid JSON value that is not a JSON-RPC envelope "
            "(`{\"foo\": \"bar\"}`) is recorded, same shape as ACP-INFO-PARSE-001. Spec silent; "
            "reference SDKs disagree (rust-sdk replies -32600, python-sdk silently drops it). "
            "Never asserts on the probed behaviour itself, but still FAILs if the prerequisite "
            "`initialize` handshake fails (review-slices-7.md N2)."
        ),
        citation=_cite(
            "agent-client-protocol-schema (spec silent); rust-sdk vs python-sdk divergence "
            "(Assertable only as warnings/informational)"
        ),
        source_report="acp-v1-transport-and-jsonrpc.md",
    ),
    Requirement(
        id="ACP-INFO-UNKNOWNSESSION-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "The error code (if any) returned for `session/prompt` against a `sessionId` the "
            "agent never created is recorded, never asserted -- v1 does not specify one "
            "(Discrepancy 6). Even a successful result is only recorded. Never asserts on the "
            "probed behaviour itself, but still FAILs if the prerequisite `initialize`/"
            "`session/new` handshake fails (review-slices-7.md N2)."
        ),
        citation=_cite("docs/protocol/v1/error.mdx (stub; Discrepancy 6)"),
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
