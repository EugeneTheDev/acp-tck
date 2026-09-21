# ACP v2: patch/upsert `session/update` semantics, open enums, and extensibility/`_meta`/error hygiene

**Sources checked:**
- `agentclientprotocol/agent-client-protocol` (spec) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`,
  2026-09-21, `docs: update registry agents (#2190)`. `git pull --ff-only` → "Already up to date"
  (an earlier attempt in this session failed with a transient `no such ref was fetched`; the retry
  succeeded, so the checkout *is* current).
- `agentclientprotocol/rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5`, 2026-09-18 —
  `git pull --ff-only` clean.
- `agentclientprotocol/python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64`, 2026-09-21 —
  `git pull --ff-only` clean.

All `path:line` citations below are **spec-repo** relative unless prefixed `[rust]` / `[python]`.

**Confidence:** high for A and C (prose + schema agree and are mutually corroborating), high for B
(the enum inventory is mechanically derived from `schema/v2/schema.json` and cross-checked against
per-enum prose), medium for the SDK observations (both SDKs' v2 surfaces are thin/experimental and
neither emits a tool call).

## Answer

v2 turns three families of `session/update` into **keyed upserts with three-state patch fields**:
messages keyed by `messageId` (`user_message`/`agent_message`/`agent_thought`), tool calls keyed by
`toolCallId` (`tool_call_update`), and display terminals keyed by `terminalId` (`terminal_update`) —
in each, an *omitted* field means unchanged, `null` means clear/unset, and a concrete value replaces;
the paired `*_chunk` variants append instead. An update **may** reference an id the client has never
seen: that *is* the create ("For a new `toolCallId`, omitted fields use Client defaults",
`docs/protocol/v2/tool-calls.mdx:101-110`), so there is no "create must precede update" MUST and no
error path for an unknown key. Almost all of the patch text is *client application* guidance; the
agent-bound, client-observable MUSTs reduce to id presence/uniqueness/stability, absolute `cwd`,
`planId` on every plan variant, and the state/stop-reason ordering rules. On enums: **every**
string enum and tagged-union discriminator in v2 is open except `ElicitationSchemaType` and the
JSON-RPC `jsonrpc: "2.0"` literal — 12 scalar open enums (`anyOf: [const…, {type:"string"}]`) and 18
tagged unions carrying a `title: "other"` fallback branch guarded by a `not` clause. Crucially this
does **not** soften the TCK: nine separate prose passages put a **MUST on the emitter** ("Custom X
**MUST** begin with `_`"), so the v1-style "invalid value" FAIL survives in v2, merely restated as
*defined constant **or** `_`-prefixed*. Extensibility, `_meta`, custom-method naming, the
unknown-root-field MUST NOT, `-32601`'s weak lowercase "should", and the `Error` object are all
**byte-identical to v1** (verified by diff and by `$def` equality), with one addition: the new
"Enum and Tagged-Union Variants" section, which is the only new normative extensibility content in
v2 (`docs/protocol/v2/extensibility.mdx:111-122`).

## Requirements

Tier column uses the TCK's own tiers where the mapping is unambiguous. "MANDATORY(obs)" means the
requirement is mandatory but only assertable when the agent happens to emit the construct — a TCK
should PASS vacuously, never FAIL, when it never appears.

### A. Patch / upsert semantics — agent-bound

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| A1 | Agent **MUST** include an opaque `messageId` on every message update and message chunk | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:246`; schema required: `schema/v2/schema.json:4767-4796` (`UserMessage`), `:4797-4826` (`AgentMessage`), `:4827-4856` (`AgentThought`), `:4738-4766` (`ContentChunk`) |
| A2 | `session/prompt` response carries a required, non-null string `messageId`; omission and explicit `null` are invalid | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:124-127`; `schema/v2/schema.json:4097-4123` (`PromptResponse`, `required: ["messageId"]`) |
| A3 | All updates for the inserted user message **MUST** use the `messageId` returned by that `session/prompt` response | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:129` |
| A4 | Agent **MUST** report the inserted user message via a `user_message` update with full `content`, or via streamed `user_message_chunk` updates | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:129` |
| A5 | Agents **MUST** assign distinct message IDs to distinct inserted submissions, even if content is identical | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:151` |
| A6 | If a message is retained and replayed, the Agent **MUST** use the same ID | MANDATORY, conditional on replay | `docs/protocol/v2/prompt-lifecycle.mdx:153` |
| A7 | Agent **MUST NOT** answer `session/prompt` successfully merely on receipt / ID assignment; success means insertion. Pre-insertion rejection uses a JSON-RPC error | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:110` |
| A8 | Agent **MUST** send `state_update` with `state: "running"` when foreground work starts or resumes | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:159` |
| A9 | Agent **MUST** report `idle` via `state_update` when ready for a new prompt, and **MUST** include the corresponding `StopReason` when that transition ends foreground work | MANDATORY *(schema says SHOULD — see Discrepancy D1)* | `docs/protocol/v2/prompt-lifecycle.mdx:348`; vs `schema/v2/schema.json:4904-4917` |
| A10 | After `session/cancel`, once aborts and pending updates are done, Agent **MUST** send an idle `state_update` with `stopReason: "cancelled"`, and **MUST** catch abort exceptions rather than surfacing a generic failure | MANDATORY | `docs/protocol/v2/prompt-lifecycle.mdx:519`, `:526` |
| A11 | Agent **MAY** send content/tool-call updates after `session/cancel`, but **MUST** send them before the idle cancelled `state_update` | MANDATORY (ordering) | `docs/protocol/v2/prompt-lifecycle.mdx:530` |
| A12 | Every `tool_call_update` carries `toolCallId`; every `tool_call_content_chunk` carries `toolCallId` **and** `content` | MANDATORY(obs) | `schema/v2/schema.json:674-758` (`required: ["toolCallId"]`), `:5040-5110` (`required: ["toolCallId","content"]`); `docs/protocol/v2/tool-calls.mdx:37-39`, `:174-181` |
| A13 | `terminalId` is unique within the session, stable for the terminal's lifetime, and **MUST NOT** be reused for a different terminal | MANDATORY(obs) | `docs/protocol/v2/tool-calls.mdx:405-411` |
| A14 | A supplied `terminal_update.cwd` **MUST** be absolute | MANDATORY(obs) | `docs/protocol/v2/tool-calls.mdx:439-440`; general rule `docs/protocol/v2/overview.mdx:176` |
| A15 | Every plan content variant, **including custom/future ones**, **MUST** carry a `planId` | MANDATORY(obs) | `docs/protocol/v2/agent-plan.mdx:71`; schema: `PlanItems.required=["planId","entries"]` `schema/v2/schema.json:5367-5396`, and even the `other` fallback requires `planId` `:5199-5278` |
| A16 | For item-based plans the Agent **MUST** send the complete entry list in every update | MANDATORY but **unobservable** (see Testability) | `docs/protocol/v2/agent-plan.mdx:108`; `schema/v2/schema.json:5367-5396` |
| A17 | `session/set_config_option` **MUST** respond with the complete list of all config options and current values | CAPABILITY / MANDATORY(obs) | `docs/protocol/v2/session-config-options.mdx:262`, `:307-311`; `SetSessionConfigOptionResponse.required=["configOptions"]` `schema/v2/schema.json:4073-4096` |
| A18 | Agents **MUST** always provide a default value for every configuration option | MANDATORY(obs) | `docs/protocol/v2/session-config-options.mdx:197` |
| A19 | Agent **SHOULD** report a requested tool invocation with a `tool_call_update`; **SHOULD** include `name` in the first report when available and **SHOULD NOT** change it later except to correct metadata; **SHOULD** include `title` the first time it reports a `toolCallId` | ADVISORY | `docs/protocol/v2/tool-calls.mdx:18`, `:44-47`, `:51-52` |
| A20 | Agent **SHOULD** provide `terminal_update.command` on the first update when applicable | ADVISORY | `docs/protocol/v2/tool-calls.mdx:437-438` |
| A21 | While blocked on a permission response or other user action the Agent **SHOULD** report `requires_action`, and `running` when work resumes | ADVISORY | `docs/protocol/v2/prompt-lifecycle.mdx:371` |
| A22 | Agent **SHOULD** report plans with `plan_update`, and **SHOULD** report progress with further `plan_update`s carrying the same `planId` | ADVISORY | `docs/protocol/v2/agent-plan.mdx:16`, `:106` |
| A23 | Agents **SHOULD** place higher-priority config options first in `configOptions` | ADVISORY | `docs/protocol/v2/session-config-options.mdx:187` |
| A24 | Terminal `output` snapshots and `terminal_output_chunk` `data` are RFC 4648 base64 (`contentEncoding: "base64"`); each chunk is *independently* encoded | MANDATORY(obs) | `docs/protocol/v2/tool-calls.mdx:441-446`, `:466-474` |

### B. Open enums

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| B1 | Any custom value an *agent emits* in an open enum / tagged-union discriminator **MUST** begin with `_`; unknown non-underscore values are reserved for future ACP variants, and extensions **MUST NOT** define them | MANDATORY | `docs/protocol/v2/extensibility.mdx:111-118`; `docs/protocol/v2/overview.mdx:191`; `docs/protocol/v2/migration.mdx:716` |
| B2 | Per-site restatements of B1 (each an explicit **MUST**): `StopReason`, `ToolKind`, `ToolCallStatus`, `PermissionOptionKind`, `ContentBlock.type`, plan content `type`, `PlanEntryPriority`, `PlanEntryStatus`, `SessionConfigOption.type`, `AuthMethod.type`, `McpServer.type`, `AvailableCommandInput.type` | MANDATORY | `prompt-lifecycle.mdx:481`; `tool-calls.mdx:75`, `:346`, `:373`; `content.mdx:20`; `agent-plan.mdx:69`, `:88`, `:100`; `session-config-options.mdx:203`; `authentication.mdx:121`; `session-setup.mdx:334`; `slash-commands.mdx:73` |
| B3 | `SessionConfigOptionCategory` names not beginning with `_` are reserved for the ACP spec; `_`-prefixed category names are free for custom use | MANDATORY | `docs/protocol/v2/session-config-options.mdx:172`; `docs/protocol/v2/schema.mdx:5106-5107` |
| B4 | Implementations **MUST NOT** treat unknown non-underscore values as custom extensions | MANDATORY, **receiver-side / not observable** from a client TCK | `docs/protocol/v2/extensibility.mdx:118` |
| B5 | An Agent that receives a `RequestPermissionOutcome` it does not understand **MUST NOT** treat it as approval | MANDATORY, receiver-side (testable only by an adversarial client — see Testability) | `docs/protocol/v2/migration.mdx:528` |
| B6 | When storing/replaying/proxying/forwarding, implementations **SHOULD** preserve unknown values and raw tagged-union payloads; when displaying, fall back to generic UI | SHOULD → ADVISORY/untestable | `docs/protocol/v2/extensibility.mdx:122`; `docs/protocol/v2/migration.mdx:716` |
| B7 | Clients **MUST** handle missing or unknown config-option categories gracefully; categories **MUST NOT** be required for correctness | MANDATORY, client-side (context only) | `docs/protocol/v2/session-config-options.mdx:168-169` |

### C. Extensibility, `_meta`, custom methods, unknown fields, errors

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| C1 | Implementations **MUST NOT** add any custom field at the root of a type that is part of the specification; all names are reserved for future protocol versions | MANDATORY (check is soft — see Testability) | `docs/protocol/v2/extensibility.mdx:39` |
| C2 | `_meta` may be carried only by object types that define it; primitives and types without `_meta` cannot carry it. `Error` does **not** define `_meta` | MANDATORY | `docs/protocol/v2/extensibility.mdx:10`; `schema/v2/schema.json:4127-4149` (`Error` has no `_meta`) |
| C3 | Every `_meta` in v2 is typed `["object","null"]` with `additionalProperties: true` — 106 `$def`s, uniformly | MANDATORY (schema-level) | mechanically verified across `schema/v2/schema.json`; e.g. `:4289-4295` (`UpdateSessionNotification._meta`) |
| C4 | `traceparent` / `tracestate` / `baggage` **SHOULD** be reserved as root keys of `_meta` (W3C trace context) | SHOULD → ADVISORY | `docs/protocol/v2/extensibility.mdx:33-37` |
| C5 | Custom methods **MUST** be `_`-prefixed; the protocol reserves that namespace. Implementations **MAY** expose/call them | MANDATORY (naming) / MAY (existence) | `docs/protocol/v2/extensibility.mdx:43`, `:52` |
| C6 | On receiving a custom request, implementations **MUST** respond with the provided `id` | MANDATORY | `docs/protocol/v2/extensibility.mdx:65` |
| C7 | An unrecognized custom method *should* get `-32601` "Method not found" — lowercase, unbolded prose | SHOULD → ADVISORY (see Discrepancy D2) | `docs/protocol/v2/extensibility.mdx:80-91` |
| C8 | Implementations **SHOULD** ignore unrecognized notifications | SHOULD → ADVISORY | `docs/protocol/v2/extensibility.mdx:109` |
| C9 | Extensions **SHOULD** advertise custom capabilities via `_meta` in capability objects | SHOULD → ADVISORY | `docs/protocol/v2/extensibility.mdx:93`, `:126-149` |
| C10 | Error objects carry `code` (integer) and `message` (string), both required; `message` "should be limited to a concise single sentence"; `data` is any JSON value | MANDATORY (shape) / SHOULD (message brevity) | `schema/v2/schema.json:4127-4149` — **identical to `schema/v1`'s `Error`** |
| C11 | ACP error codes: `-32700`, `-32600`, `-32601`, `-32602`, `-32603`, `-32800` (Request cancelled), `-32000` (Authentication required), `-32002` (Resource not found), plus an open "Other" integer. **Unchanged from v1** | MANDATORY (values) | `schema/v2/schema.json:4150-4216`; v1 equivalent verified identical |
| C12 | Agent **MUST NOT** write anything to stdout that is not a valid ACP message; messages are `\n`-delimited, UTF-8, and **MUST NOT** contain embedded newlines; agent **MAY** write UTF-8 to stderr | MANDATORY | `docs/protocol/v2/transports.mdx:6`, `:25-28` |
| C13 | Shutdown: the spec still defines **no** shutdown method — only the diagram's "Close stdin, terminate subprocess" | (no requirement) | `docs/protocol/v2/transports.mdx:41` — same as v1 |
| C14 | ACP-defined property keys are `camelCase`; discriminator string values are `snake_case`; JSON-RPC envelope fields follow JSON-RPC 2.0 | convention (unbolded) → ADVISORY | `docs/protocol/v2/overview.mdx:189` |
| C15 | All file paths **MUST** be absolute; line numbers are 1-based | MANDATORY | `docs/protocol/v2/overview.mdx:176-177` |

## Details

### A. The three patch/upsert families, field by field

**A.1 Message upserts — `user_message` / `agent_message` / `agent_thought`**

Normative prose: `docs/protocol/v2/prompt-lifecycle.mdx:248-258`. Schema: `UserMessage`
`schema/v2/schema.json:4767-4796`, `AgentMessage` `:4797-4826`, `AgentThought` `:4827-4856`. All
three are structurally identical.

| field | required | type | patch rule |
|---|---|---|---|
| `messageId` | **yes** | `MessageId` = `string` (`schema/v2/schema.json:4120-4123`) | the upsert key |
| `content` | no | `["array","null"]` of `ContentBlock` | **omitted → unchanged**; `null` → clear; `[]` → clear; concrete array → **replaces everything accumulated so far, including earlier chunks** |
| `_meta` | no | `["object","null"]` | omitted → no metadata update; `null` → explicit clear |

Chunks: `ContentChunk` `schema/v2/schema.json:4738-4766`, used by `user_message_chunk`,
`agent_message_chunk`, `agent_thought_chunk` (`SessionUpdate` branches, `:4300-4560`).
`required: ["messageId","content"]`; `content` here is a **single `ContentBlock` object**, not an
array — a validator must not conflate the two shapes. A chunk appends; a changed `messageId`
starts a new message; a chunk's `_meta` is chunk-scoped
(`schema/v2/schema.json:4755-4760`, `docs/protocol/v2/prompt-lifecycle.mdx:256`).

Worked example the spec gives (`docs/protocol/v2/prompt-lifecycle.mdx:258`):
`agent_message content:[A]` → `agent_message_chunk B` ⇒ `[A,B]`; then `agent_message content:[C]`
⇒ `[C]`; subsequent chunks append to `[C]`.

Ordering: clients apply per-`messageId` in **receive order** (`:250`). There is no MUST that a
"create" precede an "update" — `content` omitted on a first-seen `messageId` simply means "omitted
fields use client defaults" (`schema/v2/schema.json:4769`, in the `UserMessage` description).
Idempotency: replaying an identical full-`content` update is idempotent; replaying a chunk is
**not** (it appends again).

**A.2 Tool-call upsert — `tool_call_update` + `tool_call_content_chunk`**

`ToolCallUpdate` `schema/v2/schema.json:674-758`; prose `docs/protocol/v2/tool-calls.mdx:37-118`,
`:146-186`.

| field | required | patch rule |
|---|---|---|
| `toolCallId` | **yes** | the upsert key |
| `name` | no, nullable | omit → unchanged; `null` → clear; string → set/replace. On a new id, omission and `null` both mean "no name" (`docs/protocol/v2/tool-calls.mdx:110-114`) |
| `title` | no, nullable | same |
| `kind` | no, nullable | `ToolKind` (open enum) |
| `status` | no, nullable | `ToolCallStatus` (open enum), defaults to `pending` (`docs/protocol/v2/tool-calls.mdx:79`) |
| `content` | no, nullable array | whole-array replace; `[]` or `null` clears |
| `locations` | no, nullable array | whole-array replace; `[]` or `null` clears |
| `rawInput` / `rawOutput` | no, untyped | same patch rule — **the representation cannot distinguish storing a literal JSON `null` from clearing** (`docs/protocol/v2/tool-calls.mdx:115-119`) |
| `_meta` | no, nullable | omit → unchanged; `null` → clear |

`ToolCallContentChunk` `schema/v2/schema.json:5040-5110`: `required: ["toolCallId","content"]`,
`content` is a single `ToolCallContent`. Append semantics, per-`toolCallId` receive order; a later
`tool_call_update` carrying `content` replaces the accumulation; later chunks append to that
replacement (`docs/protocol/v2/tool-calls.mdx:185-193`, `docs/protocol/v2/prompt-lifecycle.mdx:415`).

**Unknown key rule:** "For a new `toolCallId`, omitted fields use Client defaults"
(`docs/protocol/v2/tool-calls.mdx:104-105`) — an update for an unseen id **creates**. v2 removed
v1's separate `tool_call` create variant entirely (`docs/protocol/v2/migration.mdx:733`: "Stop
sending `tool_call`. Send `tool_call_update` for creation and patches."). Likewise a `terminal`
content item and that terminal's own updates "may arrive in either order, so Clients retain state
for a first-seen `terminalId`" (`docs/protocol/v2/tool-calls.mdx:411-412`).

**A.3 Terminal upsert — `terminal_update` + `terminal_output_chunk`**

`TerminalUpdate` `schema/v2/schema.json:5111-5172`; prose `docs/protocol/v2/tool-calls.mdx:412-476`.
Key `terminalId` (required); `command`, `cwd`, `output`, `exitStatus`, `_meta` are patch fields
(omit/`null`/value). `output` is an **authoritative replacement snapshot**: clients **MUST NOT**
merge or splice previous bytes into it (`:445`). `TerminalOutputChunk`
`schema/v2/schema.json:5173-5198` requires `terminalId` + `data`; each `data` is *independently*
base64-encoded and clients **MUST NOT** concatenate encoded strings before decoding (`:472`).
Nested `_meta` (on `output`, on `exitStatus`, on a chunk) is scoped to that object and there
omission and `null` are **equivalent** — unlike top-level `_meta`
(`docs/protocol/v2/migration.mdx:717`).

**A.4 Non-patch update variants (important negative knowledge)**

- `plan_update` (`schema/v2/schema.json:5397-5424`) is **not** a field patch: each update for a
  given `planId` **replaces that plan's entries completely** (`docs/protocol/v2/agent-plan.mdx:108`,
  `docs/protocol/v2/migration.mdx:570`). `planId` scopes multiple plans per session.
- `config_option_update` (`schema/v2/schema.json:5538-5559`) carries the **complete** configuration
  state, not a delta (`docs/protocol/v2/session-config-options.mdx:307-311`, `:360`).
- `available_commands_update` (`:5516-5537`) carries the full list.
- `session_info_update` (`:5560-5582`) *is* patch-shaped: all fields optional, omit → unchanged,
  `null` → clear.
- `usage_update` (`:5606-5638`): `used` and `size` required non-null integers; `cost` optional
  nullable, and when present `amount` + `currency` (ISO 4217) are required
  (`docs/protocol/v2/prompt-lifecycle.mdx:344`).
- `state_update` (`:4940-5039`) is a state report, not an upsert.

**A.5 What `testy` v2 and the Python v2 surface actually emit**

- `[rust] src/agent-client-protocol-test/src/testy/v2.rs:307-385` — per prompt, `V2Testy` sends,
  in order: the `user_message` update (`:314`), `state_update: running` (`:316-321`), then exactly
  **one** `agent_message_chunk` carrying the whole response text (`:370-378`), then an idle
  `state_update` with a stop reason (`:191-196`). It records an `AgentMessage` with full `content`
  into history for *replay* (`:379-382`) but never sends it live. So **no multi-chunk message and
  no tool call are emitted at all**: `TestyCommand::CallTool`/`ListTools` answer
  "Testy v2 does not advertise MCP support yet" and `RunScenario` answers "not implemented yet"
  with `StopReason::Refusal` (`:355-365`).
- v2 in the Rust SDK is behind the `unstable_protocol_v2` cargo feature
  (`[rust] src/agent-client-protocol-test/Cargo.toml:15`,
  `[rust] src/agent-client-protocol/Cargo.toml:53`). The `testy` binary serves **both** v1 and v2
  through `Testy::new().protocol_router()` when built with that feature, and v1-only otherwise
  (`[rust] src/agent-client-protocol-test/src/bin/testy.rs:10-19`). That is how a v2 cross-check
  would be wired.
- `[rust] src/agent-client-protocol/examples/simple_agent_v2.rs` is the richer v2 example and still
  emits no tool calls: `state_update: running` (`:285`), one `agent_message_chunk` (`:313`), an
  `AgentMessage` for history (`:320-321`), idle with stop reason (`:150-151`). Notably at
  `:363-368` it sends an **idle `state_update` with no `stopReason` immediately after
  `session/new`** — a legal non-turn-ending idle. A v2 TCK must not assume the first idle it sees
  belongs to a prompt turn.
- Python: v2 lives in `[python] src/acp/experimental/v2/` and its schema is pinned to
  `schema-v2.0.0-alpha.5` (`[python] schema/v2/VERSION`), while `[python] src/acp/meta.py:50` still
  reads `PROTOCOL_VERSION = 1`. **No example agent uses v2** (`[python] examples/*.py` all import
  the v1 `acp.schema`); the only v2 exercises are `[python] tests/test_v2_runtime.py`,
  `test_v2_routing.py`, `test_v2_schema.py`. So there is no Python v2 cross-check target today.
  The generated models do match the spec: `[python] src/acp/experimental/v2/schema.py:4568-4569`
  (`AgentMessage.message_id` required), `:5456-5486` (`ToolCallUpdate`, open `kind` ending in a
  bare `str`), and serialization uses `model_dump(..., exclude_unset=True)`
  (`[python] src/acp/experimental/v2/agent.py:27`), which correctly preserves the
  omitted-vs-explicit-`null` distinction that `docs/protocol/v2/migration.mdx:765` warns about.

### B. The complete open-enum inventory

**B.1 Scalar open enums** — `anyOf: [ {const …}, …, {title: "other", type: "string"} ]`. Twelve,
mechanically extracted from `schema/v2/schema.json`:

| `$def` | line | defined values |
|---|---|---|
| `ToolKind` | 759 | `read`, `edit`, `delete`, `move`, `search`, `execute`, `think`, `fetch`, `switch_mode`, `other` |
| `ToolCallStatus` | 819 | `pending`, `in_progress`, `completed`, `failed`, `cancelled` |
| `Role` | 1141 | `assistant`, `user` |
| `IconTheme` | 1321 | `light`, `dark` |
| `DiffFileType` | 1743 | `text`, `binary`, `directory`, `symlink` |
| `DiffPatchFormat` | 1834 | `git_patch` |
| `PermissionOptionKind` | 2036 | `allow_once`, `allow_always`, `reject_once`, `reject_always` |
| `StringFormat` | 2427 | `email`, `uri`, `date`, `date-time` |
| `SessionConfigOptionCategory` | 3776 | `mode`, `model`, `model_config`, `thought_level` |
| `StopReason` | 4869 (fallback branch at 4898) | `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled` |
| `PlanEntryPriority` | 5312 | `high`, `medium`, `low` |
| `PlanEntryStatus` | 5337 | `pending`, `in_progress`, `completed`, `cancelled` |

Note `ToolKind` has a *defined* value literally named `other` **and** an untitled open fallback —
a validator/tier author must not confuse `kind: "other"` (defined, the documented default) with the
open-variant branch.

**B.2 Open tagged unions** — each carries a `title: "other"` branch whose discriminator is a bare
`{type: "string"}`, guarded by a `not: {anyOf: [ …each known const… ]}` so the fallback matches
*only* genuinely unknown values. Eighteen:

| `$def` | line | discriminator | defined values |
|---|---|---|---|
| `RequestPermissionSubject` | 600 | `type` | `tool_call`, `command` |
| `ToolCallContent` | 854 | `type` | `content`, `diff`, `terminal` |
| `ContentBlock` | 954 (fallback at 1038) | `type` | `text`, `image`, `audio`, `resource_link`, `resource` |
| `DiffChange` | 1558 | `operation` | `add`, `delete`, `modify`, `move`, `copy` |
| `CreateElicitationRequest` | 2066 | `mode` | `form`, `url` |
| `ElicitationPropertySchema` | 2275 | `type` | `string`, `number`, `integer`, `boolean`, `array` |
| `MultiSelectItems` | 2657 | `type` | `string` (plus a `titled` branch) |
| `AuthMethod` | 3399 | `type` | `terminal`, `agent` (fallback also requires `methodId`, `name`) |
| `SessionConfigOption` | 3659 | `type` | `select`, `boolean` |
| `SessionUpdate` | 4300 (fallback at 4560) | `sessionUpdate` | `user_message_chunk`, `user_message`, `agent_message_chunk`, `agent_message`, `agent_thought_chunk`, `agent_thought`, `state_update`, `tool_call_content_chunk`, `tool_call_update`, `terminal_update`, `terminal_output_chunk`, `plan_update`, `available_commands_update`, `config_option_update`, `session_info_update`, `usage_update` |
| `StateUpdate` | 4940 | `state` | `running`, `idle`, `requires_action` |
| `PlanUpdateContent` | 5199 | `type` | `items` (fallback also requires `planId`) |
| `AvailableCommandInput` | 5451 | `type` | `text` |
| `McpServer` | 6052 | `type` | `http`, `stdio` |
| `ReplayFrom` | 6335 | `type` | `start` |
| `SetSessionConfigOptionRequest` | 6424 | `type` | `id`, `boolean` |
| `RequestPermissionOutcome` | 6662 | `outcome` | `cancelled`, `selected` |
| `CreateElicitationResponse` | 6752 | `action` | `accept`, `decline`, `cancel` |

**B.3 Open numeric enum:** `ErrorCode` `schema/v2/schema.json:4150-4216` — eight named `const`
integers plus a `title: "Other"` bare `{type: "integer"}`. Identical to v1.

**B.4 What is still CLOSED.** Only two string enums in the whole v2 schema reject unknown values:
`ElicitationSchemaType` (`schema/v2/schema.json:2265-2274`, `oneOf` with the single const
`"object"`, no fallback) and the JSON-RPC literal `jsonrpc: {"enum": ["2.0"]}` at each of the seven
root branches (`:6`, `:44`, `:82`, `:125`, `:289`, `:332`, `:424`). Structural (untagged) unions —
`AgentResponse` / `ClientResponse` (Result|Error), `RequestId` (Null|Number|Str),
`EmbeddedResourceResource`, `ElicitationContentValue`, `SessionConfigSelectOptions`,
`ElicitationFormMode`, `ElicitationUrlMode` — are closed but have no discriminator to extend.

This means `docs/protocol/v2/migration.mdx:716`'s "Every enum-like string accepts unknown values"
is very nearly, but not literally, true.

**B.5 The consequence for TCK tiering — the single most important finding.**

The instinct "the schema is open, so unknown values can't FAIL" is **wrong for v2**. Nine separate
prose passages bind the *emitter*:

> "Custom stop reasons **MUST** begin with `_`; unknown non-underscore stop reasons are reserved
> for future ACP variants." — `docs/protocol/v2/prompt-lifecycle.mdx:481`

plus the generic rule "Extensions **MUST NOT** define custom non-underscore values"
(`docs/protocol/v2/extensibility.mdx:117`). So the v1 check *survives*, restated:

> **defined constant OR starts with `_`** — anything else is a MUST violation by the emitting agent.

Concretely, for the v1 `ACP-PROMPT-001` stop-reason check: `"end_turn"` PASSes,
`"_vendor.example/throttled"` PASSes, `"done"` **FAILs** (MANDATORY). Nothing becomes
INFORMATIONAL. The same restatement applies verbatim at every site in B.1/B.2 that has explicit
prose (B2 in the requirements table); for the handful of open enums with **no** prose MUST
(`Role`, `IconTheme`, `DiffFileType`, `DiffPatchFormat`, `StringFormat`, `DiffChange.operation`,
`SessionUpdate.sessionUpdate`, `StateUpdate.state`, `RequestPermissionOutcome.outcome`,
`RequestPermissionSubject.type`, `ReplayFrom.type`, `ElicitationPropertySchema.type`,
`CreateElicitation*`, `SetSessionConfigOptionRequest.type`, `MultiSelectItems.type`,
`ToolCallContent.type`) the generic `extensibility.mdx:117` MUST still applies, and the schema's
own `other`-branch descriptions repeat it verbatim (e.g. `schema/v2/schema.json:4560-4575` for
`SessionUpdate`, `:1038-1053` for `ContentBlock`, `:4898-4902` for `StopReason`). I would
nonetheless tier those **without** dedicated prose one notch lower (ADVISORY) than the twelve with
it, because the generic rule's own scope clause ("This rule applies only where the schema defines a
fallback path", `docs/protocol/v2/extensibility.mdx:120`) makes the per-site prose the safer ground.

### C. Extensibility, `_meta`, methods, unknown fields, errors

**C.1 v1 → v2 delta, verified by diff.** `diff docs/protocol/v1/extensibility.mdx
docs/protocol/v2/extensibility.mdx` yields exactly three hunks:

1. The `_meta` intro paragraph reworded. v1's explicit `{ [key: string]: unknown }` typing and its
   "for example, the `Error` object does not [define `_meta`]" were dropped; v2 says "Primitive
   types and object types that do not define `_meta` cannot carry it"
   (`docs/protocol/v2/extensibility.mdx:10`). **Substance unchanged** — the schema still types
   `_meta` as `["object","null"]` everywhere and `Error` still has none.
2. The **new** "Enum and Tagged-Union Variants" section (`:111-122`) — the only new normative
   extensibility content in v2.
3. The capability example updated to v2's `capabilities`/`info` initialize shape (`:130-148`).

Everything else is byte-identical: `:39` (MUST NOT add custom root fields), `:43`/`:52`
(`_`-prefixed custom methods), `:65` (MUST respond with the provided `id`), `:80-91` (`-32601`),
`:93`/`:126` (SHOULD advertise custom capabilities), `:109` (SHOULD ignore unrecognized
notifications). `docs/protocol/v2/draft/extensibility.mdx` is **identical** to the stable page
(diff exit 0) — no pending divergence.

**C.2 The scope clause is new and matters.** `docs/protocol/v2/extensibility.mdx:120`:
"This rule applies only where the schema defines a fallback path. Closed discriminators can still
reject unknown values when the receiver cannot safely continue without understanding the variant."
Per B.4 the only such closed discriminator is `ElicitationSchemaType`.

**C.3 `_meta` mechanics.** 106 of 175 `$def`s define a root `_meta`, always
`{"type": ["object","null"], "additionalProperties": true, "x-deserialize-default-on-error": true}`.
Object-shaped `$def`s **without** root `_meta`: `AgentNotification`, `AgentRequest`,
`ClientNotification`, `ClientRequest`, `DiffPatch`, `DiffPathChange`, `DiffPathPairChange`,
`ElicitationAcceptAction`, `ElicitationFormMode`, `ElicitationRequestScope`,
`ElicitationSessionScope`, `ElicitationUrlMode`, `Error`, `Icon`, `ProtocolLevelNotification`,
`SessionConfigBoolean`, `SessionConfigSelect`, `ToolCallPermissionSubject`. Top-level `_meta` on an
upsert-shaped update follows patch semantics (omit → unchanged, `null` → clear); nested/scoped
`_meta` treats omission and `null` as equivalent (`docs/protocol/v2/migration.mdx:717`).

**C.4 Error object.** `schema/v2/schema.json:4127-4149` is byte-identical to `schema/v1`'s `Error`
(verified by Python dict equality). `required: ["code","message"]`; `message` is a plain
`type: "string"` whose description says it "should be limited to a concise single sentence";
`data` is an untyped any-JSON field with `x-deserialize-default-on-error`. No `_meta`.
`docs/protocol/v2/error.mdx:1-6` is a "_Documentation coming soon_" stub — exactly as
`docs/protocol/v1/error.mdx` is — so the only v2 error prose is
`docs/protocol/v2/overview.mdx:181-185`.

**C.5 Custom-method modelling in the schema.** `ExtRequest` (`schema/v2/schema.json:2887-2889`),
`ExtResponse` (`:4124-4126`) and `ExtNotification` (`:5666-5668`) are **description-only** `$def`s
with no `type` and no `properties` — they impose no constraints. A v2 validator therefore cannot
schema-check custom-method traffic at all; the `_`-prefix rule and the MUST-respond-with-`id` rule
are hand-written checks, as in v1.

**C.6 New/renamed protocol-level surface relevant to hygiene.** `meta.json` (`schema/v2/meta.json`)
adds `protocolMethods: { "cancel_request": "$/cancel_request" }`; `ProtocolLevelNotification`
(`schema/v2/schema.json:6967-7000`) documents that `$/`-prefixed notifications "may not be
implementable in all clients or agents. If an agent or client receives notifications starting with
`$/` it is free to ignore the notification." `CancelRequestNotification`
(`:7001-7024`) requires `requestId` and the receiver **MUST** answer the original request with
either a valid response or `-32800`. This is a **second reserved method-name prefix** alongside
`_` — new relative to v1's hygiene surface, and something the TCK's "custom methods must be
`_`-prefixed" self-discipline rule must now also respect (`$/` is spec-reserved, not free).

**C.7 Vendor prefixes / versioned extensions.** There is **no** `x-`/vendor-prefix mechanism in
the v2 protocol. The `x-side`, `x-method`, `x-docs-ignore`, `x-deserialize-default-on-error`
(222×) and `x-deserialize-skip-invalid-items` (26×) keys are *schema-generation annotations*, not
wire features, and all five already exist in `schema/v1/schema.json` (251/27/7/46/46). Extension
negotiation remains `_meta` in capability objects (`docs/protocol/v2/extensibility.mdx:124-151`) —
a **SHOULD**, with no structural support.

**C.8 Shutdown.** Unchanged: `docs/protocol/v2/transports.mdx` differs from v1 only by the batch
section and the "or batch arrays" phrase (`:23-24`). There is still no shutdown method and no
stdin-EOF MUST — only the mermaid step "Close stdin, terminate subprocess" (`:41`).

## Candidate v2 requirement rows

Reusing a v1 id **only** where the identical requirement re-cites to a v2 source; otherwise a
2xx id in the area.

### Patch/upsert — new family

| id | tier | requirement | v2 citation | conforming | non-conforming fixture line |
|---|---|---|---|---|---|
| `ACP-PATCH-201` | MANDATORY | Every agent-emitted message update/chunk carries a non-empty string `messageId` | `prompt-lifecycle.mdx:246`; `schema.json:4738-4856` | every `*_message*` update has `messageId` | emits `agent_message_chunk` with no `messageId` |
| `ACP-PATCH-202` | MANDATORY | The `session/prompt` result is `{messageId: <non-null string>}` and the agent's `user_message`/`user_message_chunk` updates for that submission carry that same id | `prompt-lifecycle.mdx:124-129`; `schema.json:4097-4123` | ids match | responds `{"messageId": null}`, or acks with a different id |
| `ACP-PATCH-203` | MANDATORY | Two `session/prompt`s with identical content receive two **distinct** `messageId`s | `prompt-lifecycle.mdx:151` | distinct | returns a constant `messageId` (v2 analogue of `duplicate_session_id.py`) |
| `ACP-PATCH-204` | MANDATORY(obs) | Every `tool_call_update` carries `toolCallId`; every `tool_call_content_chunk` carries `toolCallId` + `content` | `schema.json:674-758`, `:5040-5110` | present | omits `toolCallId` on a follow-up status patch |
| `ACP-PATCH-205` | MANDATORY(obs) | Every `plan_update.plan`, including an unknown/`_` variant, carries `planId` | `agent-plan.mdx:71`; `schema.json:5199-5278` | present | sends `{"type":"items","entries":[…]}` with no `planId` |
| `ACP-PATCH-206` | MANDATORY(obs) | A supplied `terminal_update.cwd` is absolute; a `terminalId` is never reused for a different terminal within a session | `tool-calls.mdx:405-411`, `:439-440` | absolute, unique | relative `cwd` |
| `ACP-PATCH-207` | MANDATORY(obs) | `terminal_output_chunk.data` and `terminal_update.output.data` each decode as standalone RFC 4648 base64 | `tool-calls.mdx:441-446`, `:466-474` | decodes | emits a chunk that only decodes when concatenated with the previous one |
| `ACP-PATCH-208` | ADVISORY | The first `tool_call_update` for a new `toolCallId` includes `title`, and `name` when available; `name` does not change afterwards | `tool-calls.mdx:44-52` | included | first report has neither |
| `ACP-PATCH-209` | ADVISORY | While blocked on a permission response the agent reports `requires_action`, and `running` when it resumes | `prompt-lifecycle.mdx:371` | both seen | stays `running` throughout |

### Open enums — new family

| id | tier | requirement | v2 citation | conforming | non-conforming fixture line |
|---|---|---|---|---|---|
| `ACP-ENUM-201` | MANDATORY | Every value the agent emits at an open-enum site **with per-site prose** (the twelve in B2) is a defined constant or begins with `_` | `extensibility.mdx:111-118` + the twelve per-site cites | `kind: "read"`, `kind: "_zed.dev/scry"` | `kind: "sorcery"` |
| `ACP-ENUM-202` | ADVISORY | Same rule at open-enum sites the prose does not individually restate (`sessionUpdate`, `state`, `outcome`, `operation`, `Role`, `IconTheme`, `DiffFileType`, `DiffPatchFormat`, `StringFormat`, …) | `extensibility.mdx:117`, scope clause `:120`; schema `other`-branch descriptions, e.g. `schema.json:4560-4575` | defined or `_`-prefixed | `"sessionUpdate": "surprise"` |
| `ACP-ENUM-203` | ADVISORY | A `_`-prefixed value at any open-enum site is accepted by the *agent* when the client sends one (e.g. a `_`-prefixed `SetSessionConfigOptionRequest.type` or permission outcome) without a crash or a `-32602` | `extensibility.mdx:115`, `:122` | tolerated | errors on an unknown-but-`_`-prefixed variant |
| `ACP-PROMPT-001` (**re-cited, re-worded**) | MANDATORY | The turn's idle `state_update` carries a `stopReason` that is a defined `StopReason` **or** begins with `_` | `prompt-lifecycle.mdx:464-481`; `schema.json:4869-4903` | `end_turn` / `_vendor/x` | `"done"` |

### Extensibility / hygiene — v1 ids re-cited against v2

| id | tier | change | v2 citation |
|---|---|---|---|
| `ACP-EXT-001` | MANDATORY, **unchanged** | re-cite only | `docs/protocol/v2/extensibility.mdx:43,52,65,109` |
| `ACP-JSONRPC-004` | ADVISORY, **unchanged** | re-cite only; keep ADVISORY (D2) | `docs/protocol/v2/extensibility.mdx:80-91` |
| `ACP-META-001` | ADVISORY, **unchanged** | re-cite; note `_meta` on `session/prompt` params still exists (`PromptRequest._meta`) | `docs/protocol/v2/extensibility.mdx:10,33-37,39` |
| `ACP-ERROR-001` | ADVISORY, **unchanged** | re-cite; `Error` `$def` is byte-identical to v1 | `schema/v2/schema.json:4127-4149`; `docs/protocol/v2/overview.mdx:181-185` |
| `ACP-SHUTDOWN-001` | ADVISORY, **unchanged** | re-cite; still no shutdown method in v2 | `docs/protocol/v2/transports.mdx:41` |
| `ACP-SCHEMA-001` | MANDATORY, **unchanged in spirit** | must now validate against `schema/v2/schema.json`, including the batch root branches | `schema/v2/schema.json:1-462` (root `anyOf`), `:463-7024` (`$defs`) |
| `ACP-SCHEMA-002` | ADVISORY, **needs a v2 carve-out** | unknown-root-key detection must be **skipped** for any object matched by an `other` fallback branch (an unknown/`_` variant is not "a type that's part of the specification", so `:39` does not bind it) | `docs/protocol/v2/extensibility.mdx:39` + `:113-120` |

### New hygiene rows

| id | tier | requirement | v2 citation | non-conforming fixture line |
|---|---|---|---|---|
| `ACP-META-201` | ADVISORY | Every `_meta` the agent emits is a JSON object or `null` (never a string/array/number) | `schema.json` — all 106 `_meta` sites typed `["object","null"]`, e.g. `:4289-4295` | emits `"_meta": "trace=1"` |
| `ACP-EXT-201` | ADVISORY | An unrecognized `_`-prefixed **notification** sent to the agent produces no response line and no crash (SHOULD-ignore) | `docs/protocol/v2/extensibility.mdx:109` | replies to `_tck/ping` notification (v2 analogue of `answers_notifications.py`) |
| `ACP-EXT-202` | ADVISORY | The agent advertises its extensions under `initialize` → `result.capabilities._meta` rather than as new root capability keys | `docs/protocol/v2/extensibility.mdx:93`, `:126-149` | adds `capabilities.myVendorThing: true` (also trips `ACP-SCHEMA-002`) |
| `ACP-EXT-203` | INFORMATIONAL | Behaviour on a `$/`-prefixed protocol-level notification the agent does not implement (spec explicitly says it "is free to ignore") — record only | `schema/v2/schema.json:6967-6990` | n/a — never assert |

### v1 ids to retire or re-tier for v2

| v1 id | v2 disposition | evidence |
|---|---|---|
| `ACP-CONFIG-003` (no `type:"boolean"` option without `clientCapabilities.session.configOptions.boolean`) | **RETIRE** — v2 `ClientCapabilities` has only `auth`, `elicitation`, `_meta`; the boolean gate does not exist | `schema/v2/schema.json` `ClientCapabilities` |
| `ACP-CLIENTCAP-001` (`fs/*` never called unadvertised) | **RETIRE** — the whole `fs/*` surface is gone from v2 | `docs/protocol/v2/migration.mdx:740`; `schema/v2/meta.json` `clientMethods` |
| `ACP-CLIENTCAP-002` (`terminal/*`) | **RETIRE** — same; terminals are agent-owned display state in v2 | `docs/protocol/v2/migration.mdx:740`, `:752` |
| `ACP-CLIENTCAP-003` (`elicitation/create`) | **KEEP**, still capability-gated on `clientCapabilities.elicitation` | `schema/v2/schema.json` `ClientCapabilities.elicitation`; `docs/protocol/v2/overview.mdx:142-148` |
| `ACP-MODES-001/002` | **RETIRE** — `session/set_mode`, `modes`, `current_mode_update` are removed; the same state is a config option with `category: "mode"` | `docs/protocol/v2/migration.mdx:738` |
| `ACP-LOAD-001/002/003` | **RETIRE** — `session/load` is removed in favour of `session/resume` + `replayFrom` | `docs/protocol/v2/migration.mdx:739`; `schema/v2/meta.json` has no `session_load` |
| `ACP-PROMPT-001` | **KEEP but re-word** — stop reason moves from the `session/prompt` *response* to the idle `state_update`, and the assertion becomes "defined **or** `_`-prefixed" | `docs/protocol/v2/prompt-lifecycle.mdx:348`, `:481` |
| `ACP-CONFIG-002` | **KEEP** — the complete-list MUST survives verbatim | `docs/protocol/v2/session-config-options.mdx:262` |

(The `ACP-CLIENTCAP-*` / `ACP-MODES-*` / `ACP-LOAD-*` rows overlap the initialize-capabilities and
prompt-lifecycle reports; listed here only because the orchestrator asked for a retire list in this
report. Defer to those owners if they disagree.)

## v2 validator checklist

1. **Root dispatch.** `schema/v2/schema.json` root is `anyOf` of **seven** branches (v1 had three):
   `Agent` (`:6`), `Client` (`:44`), `AgentBatchCall` (`:82`), `AgentBatchResponse` (`:125`),
   `ClientBatchCall` (`:289`), `ClientBatchResponse` (`:332`), `ProtocolLevel` (`:424`). Dispatch on
   the *JSON type* first: an **object** → the `Agent`/`Client`/`ProtocolLevel` envelopes; a
   **non-empty array** → the four batch branches (`"type": "array"`, `"minItems": 1` at `:122`,
   `:286`, `:329`, `:421`). An **empty array is invalid** and per
   `docs/protocol/v2/transports.mdx:57-59` earns `-32600` with `id: null`. Batch items are the same
   envelope, but `AgentBatchCall` items admit only `Request` / `Notification` /
   `ProtocolLevelNotification` (`:95-119`) — **not** responses — while `AgentBatchResponse` items
   admit only `Result` / `Error`.
2. **Side/method tables.** Keep deriving them from `x-side` / `x-method` (28 occurrences each in v2,
   was 46 in v1 — the surface shrank) plus `schema/v2/meta.json`. v2's `meta.json` adds a third
   bucket, `protocolMethods` (`$/cancel_request`), on top of `agentMethods` / `clientMethods`.
3. **Unknown-root-key detection stays hand-written.** `additionalProperties: false` appears
   **zero** times in `schema/v2/schema.json` (and `additionalProperties: true` 125 times, all on
   `_meta`). Port `_allowed_root_properties` / `find_unknown_root_keys` unchanged in mechanism:
   resolve the property-name union through `allOf` / `anyOf` / `oneOf` / `$ref`, always allowing
   `_meta`.
4. **…but add a v2-only carve-out for open variants.** When the object's discriminator value is
   *not* one of the union's defined constants (i.e. it matched the `title: "other"` branch), **skip**
   unknown-root-key detection entirely. `docs/protocol/v2/extensibility.mdx:39` reserves root names
   on "a type that's part of the specification"; an unknown or `_`-prefixed variant is by
   construction not one. Concretely: `{"sessionUpdate": "_zed.dev/x", "foo": 1}` must **not** be
   flagged; `{"sessionUpdate": "agent_message", "messageId": "m", "foo": 1}` **must** be.
   The `other` branches list only their discriminator (plus, for `AuthMethod`, `methodId`/`name`/
   `description`, and for `PlanUpdateContent`, `planId`) and notably do **not** list `_meta`.
5. **Two different `content` shapes.** In `UserMessage`/`AgentMessage`/`AgentThought`, `content` is
   `["array","null"]` of `ContentBlock`. In `ContentChunk` it is a single required `ContentBlock`.
   In `ToolCallUpdate` it is `["array","null"]` of `ToolCallContent`; in `ToolCallContentChunk` a
   single required `ToolCallContent`. Do not share one validator path.
6. **Where `null` must NOT be accepted.** Every `*Response` `$def` is `"type": "object"` — **none**
   is nullable, and there is no v2 analogue of v1's `LoadSessionResponse`. Therefore the v1
   `validate_agent_response` special case ("accept a literal `null` when the target response schema
   is an all-optional object") **must not be carried into v2**. Verified across all 13 concrete
   response defs: `CloseSessionResponse` `:4059`, `CreateElicitationResponse` `:6752`,
   `DeleteSessionResponse` `:4022`, `InitializeResponse` `:3040`, `ListSessionsResponse` `:3933`,
   `LoginAuthResponse` `:3599`, `LogoutAuthResponse` `:3613`, `NewSessionResponse` `:3627`,
   `PromptResponse` `:4097`, `RequestPermissionResponse` `:6639`, `ResumeSessionResponse` `:4036`,
   `SetSessionConfigOptionResponse` `:4073` — all `type: "object"`, none with a `"null"` in an outer
   union. Also non-nullable and required: `PromptResponse.messageId`,
   `NewSessionResponse.sessionId`, `ListSessionsResponse.sessions`,
   `SetSessionConfigOptionResponse.configOptions`, `RequestPermissionResponse.outcome`,
   `InitializeResponse.protocolVersion` + `.info`, and all the upsert keys
   (`messageId`, `toolCallId`, `terminalId`, `planId`).
7. **`null` that IS legal** (do not over-reject): every `_meta`; `IdleStateUpdate.stopReason`
   (`:4904-4917`); all `ToolCallUpdate` patch fields; all `TerminalUpdate` patch fields;
   `SessionInfoUpdate.title`/`.updatedAt`; `UsageUpdate.cost`; `UserMessage`/`AgentMessage`/
   `AgentThought` `.content`; `ListSessionsResponse.nextCursor`; `Implementation.title`;
   `ClientCapabilities.auth`/`.elicitation`; `AgentNotification.params`.
8. **Annotations are not constraints.** Ignore `x-deserialize-default-on-error` (222),
   `x-deserialize-skip-invalid-items` (26), `x-docs-ignore` (10) when validating — they describe
   *lenient deserialization* in the generated SDKs, not wire legality. A TCK that honoured
   `x-deserialize-default-on-error` would silently forgive exactly the defects it is meant to catch.
9. **Open enums and the validator are orthogonal.** The schema will happily accept
   `stopReason: "done"` via the `other` branch. The defined-constant-or-`_` check is therefore a
   **separate hand-written pass over agent-emitted values**, keyed by (`$def`, discriminator/field),
   using the B.1/B.2 tables. Do not try to express it as schema strictness — that would also reject
   legitimate `_`-prefixed extensions and legitimate future ACP values.
10. **`Ext*` defs are empty.** `ExtRequest` (`:2887`), `ExtResponse` (`:4124`), `ExtNotification`
    (`:5666`) carry only a `description`. Custom-method traffic is unvalidatable; assert only the
    `_` prefix and the `id` echo.

## Testability notes

**Directly assertable from a client-side TCK:**
- A1–A3, A5 (message-id discipline): drive two prompts with identical text; assert both results
  carry distinct non-null string `messageId`s, and that every `user_message*` update's `messageId`
  appears in a prompt response. A non-conforming agent reuses one id or acks with an id nobody
  returned.
- A8–A11 (state/stop-reason ordering): the whole prompt turn is observable. Note the
  `simple_agent_v2` finding above — **an idle `state_update` can legitimately arrive right after
  `session/new`**, before any prompt, and it legitimately carries no `stopReason`. Bind the
  assertion to the idle that follows a `running` for the turn, not to "the first idle".
- A12–A15, A24, `ACP-PATCH-204/205/206/207`: pure shape checks on whatever the agent emits;
  vacuous-PASS when the construct never appears.
- `ACP-ENUM-201/202` and the re-worded `ACP-PROMPT-001`: scan every agent-emitted value at the
  B.1/B.2 sites. This is the cheapest high-value v2 check and it is MANDATORY-tierable.
- `ACP-EXT-001` / `ACP-JSONRPC-004` / `ACP-META-001` / `ACP-ERROR-001` / `ACP-SCHEMA-002`: port the
  v1 tests verbatim; only the citations change.
- `ACP-META-201`: a type check over every `_meta` seen in the transcript.
- B5 (agent must not treat an unknown permission outcome as approval) **is** testable by an
  adversarial mock client: answer `session/request_permission` with
  `{"outcome": {"outcome": "_tck/unknown"}}` and assert the agent does not proceed to execute.
  I would file this INFORMATIONAL rather than MANDATORY for a first v2 slice — "did not proceed" is
  hard to observe reliably and the failure mode is a false FAIL.

**Unobservable / must NOT assert:**
- **A16 ("complete list of plan entries")** — a client cannot distinguish "the agent sent every
  entry" from "the agent has only these entries". Never FAIL on it.
- **The upsert application rules themselves.** omitted-vs-`null`-vs-array is a *client rendering*
  contract. An agent that always sends full `content` and never a chunk is fully conforming; so is
  one that only ever chunks. Never FAIL an agent for its choice of chunking granularity, for
  re-sending `content` it could have omitted, or for never using `null` to clear.
- **B4 / B6** (receivers must not treat unknown non-`_` values as extensions; SHOULD preserve
  unknown values when storing/proxying) — both bind the receiver's *internal state*, invisible over
  the wire from a driving client. Untestable.
- **B7, and every "Clients **MUST/SHOULD** …" line** in `tool-calls.mdx`, `agent-plan.mdx`,
  `session-config-options.mdx`, `prompt-lifecycle.mdx` — those bind the TCK itself as a client, not
  the agent under test. In particular `prompt-lifecycle.mdx:513` ("Client SHOULD preemptively mark
  tool calls cancelled") and `:515` ("Client MUST respond to pending permission requests with
  `cancelled`") are obligations the TCK's own mock client must honour, not assertions.
- **C1's underlying MUST NOT is strong but the check is weak** — with zero
  `additionalProperties: false` in the schema, `ACP-SCHEMA-002` remains a hand-written heuristic,
  and the new open-variant carve-out (checklist item 4) makes it weaker still. Keep it ADVISORY,
  exactly as in v1, and for the same reason.
- **C7/`ACP-JSONRPC-004`**: do not raise to MANDATORY. See D2.
- **`ACP-EXT-203`** (`$/`-prefixed notifications): the spec explicitly permits ignoring them, so
  there is no conforming/non-conforming distinction — record only.
- **Cross-check reality check:** neither reference implementation currently emits a tool call, a
  multi-chunk message, a plan, a terminal update, or a config-option update over v2. Any v2
  patch/upsert test will be **SKIPPED (vacuous)** against both `testy` v2 and the Python SDK today.
  A v2 defect-fixture suite of the repo's own is the only way to exercise these rows.

## Discrepancies

**D1 — `stopReason` on the idle transition: prose says MUST, schema says SHOULD.**
`docs/protocol/v2/prompt-lifecycle.mdx:348`: "When the transition ends foreground work, the Agent
**MUST** include the corresponding `StopReason`." `schema/v2/schema.json:4904-4917`
(`IdleStateUpdate.stopReason`): "Optional. Omitted or `null` both mean the agent is not reporting a
stop reason. Agents SHOULD include this when the idle transition ends foreground work." Same scope,
different strength. The reference implementation sides with *optional*: it sends a bare
`IdleStateUpdate::new()` after `session/new`
(`[rust] src/agent-client-protocol/examples/simple_agent_v2.rs:363-368`) and only attaches a stop
reason on the turn-ending idle (`:150-151`). **Tier impact:** the turn-ending stop-reason check is
MANDATORY on the prose, but the TCK must scope it precisely to the idle that terminates an
observed `running` turn — an unscoped "every idle carries a stopReason" check would FAIL the
reference agent. If the orchestrator wants to be conservative, ADVISORY is defensible on the
schema's wording; I recommend MANDATORY-but-scoped and recording the discrepancy in the
requirement's citation.

**D2 — `-32601` for unknown methods is still prose-weak in v2.** `docs/protocol/v2/extensibility.mdx:80`
reads "it *should* respond with the standard 'Method not found' error" — lowercase, unbolded,
unlike every surrounding bolded **MUST**/**SHOULD**/**MAY**. The adjacent **MUST** at `:65` covers
only "respond … with the provided `id`", i.e. correlation, not the code. Identical to v1.
**Tier impact:** do **not** promote `ACP-JSONRPC-004` to MANDATORY in v2; keep the v1 split
(`ACP-EXT-001` MANDATORY for "responds at all", `ACP-JSONRPC-004` ADVISORY for "with `-32601`").

**D3 — "Every enum-like string accepts unknown values" is not literally true.**
`docs/protocol/v2/migration.mdx:716` and `:16` say every enum is open; `docs/protocol/v2/extensibility.mdx:120`
correctly qualifies it ("only where the schema defines a fallback path. Closed discriminators can
still reject unknown values"). The schema has exactly one closed string discriminator,
`ElicitationSchemaType` (`schema/v2/schema.json:2265-2274`). Minor, but a validator written from
`migration.mdx` alone would wrongly accept `{"type": "_vendor"}` on an elicitation schema.

**D4 — `error.mdx` is a stub in both v1 and v2.** `docs/protocol/v2/error.mdx:1-6` is
"_Documentation coming soon_". Everything the TCK asserts about error objects rests on the `Error`
`$def` (`schema/v2/schema.json:4127-4149`) and one paragraph of
`docs/protocol/v2/overview.mdx:181-185`. **Tier impact:** `ACP-ERROR-001` gains no new footing in
v2 and must stay ADVISORY.

**D5 — Reference implementations under-exercise v2.** `testy` v2 implements no tool calls
(`[rust] src/agent-client-protocol-test/src/testy/v2.rs:355-365` returns `StopReason::Refusal` for
both `CallTool` and `RunScenario`) and emits only single-chunk messages (`:370-382`); the Python
SDK's v2 surface is `experimental`, pinned to schema `v2.0.0-alpha.5`
(`[python] schema/v2/VERSION`) rather than the spec's current v2, with `PROTOCOL_VERSION = 1` in
the shipping package (`[python] src/acp/meta.py:50`) and **no v2 example agent**. This is not a
spec/impl conflict, but it does mean the v2 patch/upsert rows cannot be validated against any
independent implementation yet — a material change to the cross-check story in
`docs/cross-check.md`.

**D6 — `$/` is a second reserved method prefix, not documented in `extensibility.mdx`.** The
extensibility page discusses only `_` (`:43`), but `schema/v2/meta.json` defines
`protocolMethods.cancel_request = "$/cancel_request"` and `ProtocolLevelNotification`
(`schema/v2/schema.json:6967-6990`) reserves the whole `$/` namespace. The TCK's own probe-naming
rule ("prefix TCK probe methods with `_`") is unaffected, but a v2 method-inventory derived only
from `agentMethods`/`clientMethods` would mis-classify `$/cancel_request` as unknown.

## Open questions

- **Batch framing vs. the validator.** I settled the *root dispatch* (checklist item 1), but the
  behavioural batch requirements (`docs/protocol/v2/transports.mdx:45-80`: per-entry `-32600`,
  never reply to a notification in a batch, never return an empty array, don't batch
  lifecycle-sensitive messages) belong to the cancellation-and-batching report. Someone must own
  whether the TCK *sends* batches at all.
- **`$/cancel_request` request-level cancellation** (`schema/v2/schema.json:7001-7024`, MUST answer
  with a valid response or `-32800`) is a new MANDATORY surface. Almost certainly the
  cancellation report's; flagging so it is not dropped.
- **Is the v1 `--auth-method` / `blocked_by_auth` machinery still needed?** v2 renames
  `authenticate` → `auth/login` and adds a MUST tying `authMethods` to implementing both
  `auth/login` and `auth/logout` (`docs/protocol/v2/overview.mdx:54`,
  `docs/protocol/v2/migration.mdx:730`). Authentication owner's call.
- **Does v2 keep any notion of a required first `initialize`?** Not examined; the
  initialize-capabilities baseline report owns it.
- **`ElicitationSchemaType` being the sole closed discriminator** looks like an oversight rather
  than a decision. Worth an upstream question, not a TCK decision.
