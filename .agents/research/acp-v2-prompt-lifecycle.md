# What is the complete v2 prompt-turn contract — from `session/prompt` request through every notification the agent may send, to whatever signals the turn is finished?

**Sources checked:**
- `agent-client-protocol` (spec, source of truth) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`, 2026-09-21 10:46 UTC, branch `main` (`git pull --ff-only` → "Already up to date"). Schema artifact version `2.0.0-alpha.5`.
- `acp-rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5`, 2026-09-18 ("Already up to date"). **Ran** its `testy` v2 agent live (built at `/tmp/acp-v2-testy-target/debug/testy` from `cargo build -p agent-client-protocol-test --bin testy --no-default-features --features unstable_protocol_v2`; no write outside that scratch target dir).
- `acp-python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64`, 2026-09-21 ("Already up to date"). Read only — its v2 runtime has no runnable example agent.
- Read-for-orientation (not re-derived): `.agents/research/acp-v2-status-and-delta-inventory.md`, `.agents/research/acp-v2-initialize-capabilities-baseline.md`, `.agents/research/reference-sdks-v2-status.md`.

**Confidence:** high for wire shapes, field tables and the observed reference sequence (read directly from `schema/v2/schema.json` and a live transcript); **medium** for the state machine, because the spec states obligations per-transition and never draws the machine — "is `idle` before `running` legal", "must `running` precede `idle`", and "may updates follow the turn-ending `idle`" are answered by inference from three separate normative sentences, not by one statement. One genuine prose-vs-schema tier conflict on `stopReason` (§Discrepancies 1).

---

## Answer

In v2 the `session/prompt` request is unchanged from v1 (`sessionId` + `prompt: ContentBlock[]` + optional `_meta`), but the response is now an **acceptance receipt**, not a turn result: it carries a required, non-null string `messageId` identifying the inserted user message and **MUST** be sent as soon as the message is inserted, without waiting for foreground work (`docs/protocol/v2/prompt-lifecycle.mdx:110,124-127`). Everything else moved into `session/update` notifications: the agent **MUST** echo the inserted user message under the same `messageId` (`:129`), **MUST** send `state_update {state:"running"}` when foreground work starts (`:159`), and **MUST** report `state_update {state:"idle"}` when it is ready for a new prompt, carrying the `StopReason` when that transition ends foreground work (`:348`). The turn's end is therefore learned only from an idle `state_update` — never from the prompt response — and `stopReason` lives only there (`schema/v2/schema.json:4904` `IdleStateUpdate`). There are 16 known `sessionUpdate` discriminators in stable v2 plus an open "other" fallback, all agent→client, all carried on `session/update` with a required `sessionId`; seven of them (`user_message`, `agent_message`, `agent_thought`, `state_update`, `tool_call_content_chunk`, `terminal_update`, `terminal_output_chunk`) are new relative to v1. The spec deliberately does **not** define whether a second `session/prompt` may be sent while a turn is running (`docs/rfds/v2/prompt.mdx:86`) — both reference agents reject it with `-32602` — so a TCK driver must serialize prompts per session and treat concurrency as an informational probe.

---

## Requirements

Tier column: MUST/SHOULD/MAY as stated upstream; `capability:<path>` where the requirement only applies when the agent advertises it. **Every row below is additionally conditional on `protocolVersion: 2` having been negotiated** (see `.agents/research/acp-v2-status-and-delta-inventory.md` S4) and, for everything session-scoped, on the agent advertising `capabilities.session` (`schema/v2/schema.json:3159` — advertising `session: {}` commits the agent to `session/new|list|resume|close|prompt|cancel|update`).

| # | Requirement | Tier | Citation (repo `agent-client-protocol` unless noted) |
|---|-------------|------|------------------------------------------------------|
| P1 | Clients MUST complete initialization and session setup before prompting. | MUST (client-side) | `docs/protocol/v2/prompt-lifecycle.mdx:10` |
| P2 | `session/prompt` params: `sessionId` and `prompt` are required; `_meta` optional/nullable. | MUST | `schema/v2/schema.json:6531` (`required: ["sessionId","prompt"]`) |
| P3 | An agent advertising `session` MUST support `text` and `resource_link` content blocks in prompts. (Contradicted by `content.mdx:33`, see Discrepancy 2.) | MUST (prose A) / text-only MUST (prose B) | `docs/protocol/v2/initialization.mdx:203`; `schema/v2/schema.json:6531` (`prompt` description); vs `docs/protocol/v2/content.mdx:33` |
| P4 | `image` / `audio` / `resource` (embedded context) blocks are allowed only when the agent advertises the matching capability. Clients MUST restrict content accordingly. | capability:`capabilities.session.prompt.image` / `.audio` / `.embeddedContext` (object markers) | `docs/protocol/v2/prompt-lifecycle.mdx:100`; `docs/protocol/v2/initialization.mdx:201-226`; `schema/v2/schema.json:3219` |
| P5 | The agent MUST respond successfully once the user message is inserted, **without waiting for foreground work to finish**. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:110`; `docs/protocol/v2/migration.mdx:251` |
| P6 | The agent MUST NOT respond successfully merely on receipt, queueing, or ID assignment. Rejection before insertion uses a JSON-RPC error. | MUST / MUST NOT | `docs/protocol/v2/prompt-lifecycle.mdx:110`; `docs/rfds/v2/prompt.mdx:43` (RFD, same wording) |
| P7 | The success result MUST contain `messageId`: a required, non-null string. Omission and explicit `null` are invalid. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:124-127`; `schema/v2/schema.json:4097` (`required: ["messageId"]`), `:4120` (`MessageId` = `type: "string"`) |
| P8 | The agent MUST also report the inserted user message via a `user_message` update (full `content` array) or streamed `user_message_chunk` updates, using **the same `messageId`** as the response. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:129`; `docs/protocol/v2/migration.mdx:261` |
| P9 | Clients MUST tolerate the user-message update arriving **before or after** the prompt response. | MUST (client-side; constrains the TCK driver, not the agent) | `docs/protocol/v2/prompt-lifecycle.mdx:129` |
| P10 | Agents MUST assign **distinct** `messageId`s to distinct inserted submissions, even with identical content. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:151` |
| P11 | If a retained message is replayed, the agent MUST reuse the original `messageId`. | MUST (conditional on retention; retention itself is not required) | `docs/protocol/v2/prompt-lifecycle.mdx:153`; `docs/rfds/v2/prompt.mdx:159` |
| P12 | A successful prompt response is **not** an `idle` signal; clients must not treat it as one. | MUST (client-side) | `docs/protocol/v2/prompt-lifecycle.mdx:155`; `docs/protocol/v2/migration.mdx:299` |
| U1 | Every `session/update` notification carries required `sessionId` and `update`. | MUST | `schema/v2/schema.json:4269` (`required: ["sessionId","update"]`, `x-side: client`, `x-method: session/update`) |
| U2 | `session/update` is agent→client only; there is no client→agent session notification in v2. | MUST | `schema/v2/meta.json:18` (under `clientMethods`); `docs/protocol/v2/overview.mdx:154-172` |
| U3 | The agent MUST include a `messageId` on every message update and message chunk. | MUST (schema-enforced) | `docs/protocol/v2/prompt-lifecycle.mdx:246`; `schema/v2/schema.json:4738,4767,4797,4827` |
| U4 | Clients apply message updates and chunks **in received order per `messageId`**; chunks append, a concrete `content` array replaces, `content: null`/`[]` clears, omitted `content` leaves unchanged. | MUST (ordering) / patch semantics deferred | `docs/protocol/v2/prompt-lifecycle.mdx:248-258`; `docs/protocol/v2/migration.mdx:329-339` |
| U5 | Unknown `sessionUpdate` discriminators are schema-valid (open union). Custom values MUST begin with `_`; unknown non-underscore values are reserved for future ACP and MUST NOT be treated as extensions. | MUST | `schema/v2/schema.json:4300` (last `anyOf` branch, `title: "other"`, with a `not` over the 16 known consts); `docs/protocol/v2/extensibility.mdx:113-118` |
| S1 | When foreground work **starts or resumes**, the agent MUST send `state_update` with `state: "running"`. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:159`; `docs/protocol/v2/migration.mdx:278` |
| S2 | When the agent is ready to process a new prompt, it MUST report `state_update` with `state: "idle"`. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:348`; `docs/protocol/v2/migration.mdx:282` |
| S3 | When the idle transition **ends foreground work**, the agent MUST include the corresponding `StopReason`. | **MUST in prose, SHOULD in schema** — see Discrepancy 1 | `docs/protocol/v2/prompt-lifecycle.mdx:348`, `:462`; `docs/protocol/v2/migration.mdx:282` vs `schema/v2/schema.json:4904` (`IdleStateUpdate` has no `required`; description says "Agents SHOULD include this…") |
| S4 | `stopReason` is one of `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`, **or** a custom value beginning with `_`. Unknown non-underscore values are reserved. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:464-481`; `schema/v2/schema.json:4869` |
| S5 | `state` is one of `running`, `idle`, `requires_action`, or a custom value beginning with `_`. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:487-495`; `schema/v2/schema.json:4940`; `docs/protocol/v2/extensibility.mdx:113-118` |
| S6 | While foreground work is blocked on a permission response or other user action, the agent SHOULD report `requires_action`; when work resumes, SHOULD report `running`. | SHOULD | `docs/protocol/v2/prompt-lifecycle.mdx:371`; `docs/protocol/v2/migration.mdx:309` |
| S7 | Background activity MAY continue and emit other `session/update` notifications while the agent reports `idle`; those do not change the state. | MAY | `docs/protocol/v2/prompt-lifecycle.mdx:497`; `schema/v2/schema.json:4940` (`StateUpdate` description) |
| S8 | Agents MAY stop foreground work at any point by sending an idle `state_update` with the corresponding stop reason. | MAY | `docs/protocol/v2/prompt-lifecycle.mdx:365` |
| S9 | After the agent reports `idle`, the client may send another `session/prompt`. | MAY (client-side) | `docs/protocol/v2/prompt-lifecycle.mdx:536` |
| C1 | Before proceeding with execution the agent MAY request permission via `session/request_permission`. | MAY | `docs/protocol/v2/prompt-lifecycle.mdx:369` |
| C2 | `session/request_permission` params require `sessionId`, `title`, and a non-empty `options` array; `description` and `subject` are optional/nullable. | MUST (when sent) | `schema/v2/schema.json:545` (`required: ["sessionId","title","options"]`, `options.minItems: 1`); `docs/protocol/v2/tool-calls.mdx:194,233,253` |
| C3 | Each `PermissionOption` requires `optionId`, `name`, `kind`. | MUST | `schema/v2/schema.json:1999` |
| C4 | Agents receiving an outcome they do not understand MUST NOT treat it as approval. | MUST (unobservable from a client harness) | `schema/v2/schema.json:6662` ("other" branch description); `docs/protocol/v2/tool-calls.mdx:318-322` |
| C5 | Agents MUST NOT request an elicitation mode the client has not advertised; a request using an unadvertised mode produces `-32602`. | MUST / capability:`capabilities.elicitation.{form,url}` | `docs/protocol/v2/elicitation.mdx:54`, `:166` |
| C6 | Agents MUST NOT assume an elicitation succeeds; they MUST handle `decline`, `cancel`, and failures. | MUST (partly observable) | `docs/protocol/v2/elicitation.mdx:151-153` |
| C7 | In v2 the only agent→client methods that exist are `session/request_permission`, `session/update`, `elicitation/create`, `elicitation/complete` (+ `$/cancel_request`). `fs/*` and `terminal/*` are gone. | MUST (by construction) | `schema/v2/meta.json:16-21`; `docs/protocol/v2/migration.mdx:53-54,628-637` |
| X1 | Concurrency: whether an agent accepts, queues, or rejects a `session/prompt` while a turn is running is **explicitly out of scope** of the v2 design. | *Unspecified* | `docs/rfds/v2/prompt.mdx:86` ("This RFD does not specify queueing, steering, or whether agents insert new prompts while busy") |
| X2 | The error code for an unknown `sessionId` on `session/prompt` is **not specified** (`docs/protocol/v2/error.mdx` is "Documentation coming soon"). | *Unspecified* | `docs/protocol/v2/error.mdx`; both reference agents use `-32602` (§6) |

Cross-reference (owned by the cancellation researcher, stated once for completeness): after `session/cancel`, the agent MAY keep sending updates but MUST send them **before** the idle `state_update` that reports `stopReason: "cancelled"` (`docs/protocol/v2/prompt-lifecycle.mdx:519,530`).

---

## Details

### 1. `session/prompt` request

`$def` `PromptRequest`, `schema/v2/schema.json:6531`, `x-side: "agent"`, `x-method: "session/prompt"`.

| Field | Type | Req? | Notes |
|---|---|---|---|
| `sessionId` | `SessionId` (`string`, `:596`) | **required** | |
| `prompt` | `ContentBlock[]` (`:954`) | **required** | May be empty (`[]`); no `minItems`. `testy` accepts `[]`. |
| `_meta` | `object \| null` | optional | `additionalProperties: true`; `x-deserialize-default-on-error`. Accepted by `testy` v2 without echo. |

Unchanged from v1 (`docs/protocol/v2/migration.mdx:257` — "The request is unchanged").

**Content blocks** (`ContentBlock`, `:954`) — five known `type` values plus an open `other` branch:

| `type` | `$def` | Required fields | Gate |
|---|---|---|---|
| `text` | `TextContent` `:1161` | `text` | baseline MUST (`content.mdx:33`) |
| `resource_link` | `ResourceLink` `:1341` | `name`, `uri` | baseline MUST per `initialization.mdx:203` (Discrepancy 2). New optional `icons`. |
| `image` | `ImageContent` `:1194` | `data`, `mimeType` | capability `capabilities.session.prompt.image` |
| `audio` | `AudioContent` `:1238` | `data`, `mimeType` | capability `capabilities.session.prompt.audio` |
| `resource` | `EmbeddedResource` `:1504` | `resource` | capability `capabilities.session.prompt.embeddedContext` |
| `_…` | open fallback | `type` | custom types MUST begin with `_` (`content.mdx:20`) |

The three prompt capabilities are **object markers**, not booleans (v1 used booleans): `PromptCapabilities` `:3219`, sub-objects `PromptImageCapabilities` `:3267`, `PromptAudioCapabilities` `:3279`, `PromptEmbeddedContextCapabilities` `:3291`. "Omitted or `null` both mean the agent does not advertise support. Supplying `{}` means the agent supports …". They live at `capabilities.session.prompt.*` in the `initialize` result (`SessionCapabilities` `:3159`), i.e. `agentCapabilities.promptCapabilities.*` → `capabilities.session.prompt.*`.

### 2. `session/prompt` response

`$def` `PromptResponse`, `schema/v2/schema.json:4097`.

| Field | Type | Req? | Notes |
|---|---|---|---|
| `messageId` | `MessageId` = `string` (`:4120`) | **required, non-null** | "Omission and explicit `null` are both invalid" (`prompt-lifecycle.mdx:126-127`) |
| `_meta` | `object \| null` | optional | |

There is **no `stopReason` in the response** — the single biggest v1→v2 break. The schema description is explicit: "This response does not indicate that the prompt was merely received or queued, nor that the agent has finished processing it. Processing and completion are reported through `state_update` session updates" (`:4097`).

**Timing.** The response is an *acceptance*, sent at insertion time (`prompt-lifecycle.mdx:110`), not at turn end. "Acceptance means insertion, not receipt, queueing, or processing completion." Insertion is a logical conversation event, not durable storage (`:153`, `docs/rfds/v2/prompt.mdx:45`).

**`messageId` semantics.** Opaque, agent-generated, `string`. Distinct submissions get distinct IDs even for identical content (`:151`). RFD adds "IDs are unique within the session and MUST NOT be reused for a different submission" (`docs/rfds/v2/prompt.mdx:70`) — the docs state only the distinctness half, so treat session-wide non-reuse as RFD-level design intent. Format is unconstrained: no pattern, no length, no `minLength` in the schema.

**Error cases.**
- Rejection before insertion → a JSON-RPC error response (`:110`). No code is specified.
- Unknown `sessionId` → unspecified upstream (X2). Observed: `-32602` with `data: "unknown session \`nope\`"` in both Rust reference agents.
- Closed session → unspecified. Observed `-32602` in `testy` v2.
- Concurrent prompt while a turn is running → **explicitly unspecified** (X1). Observed `-32602 … "already has foreground work"` in `testy` v2 (`acp-rust-sdk:src/agent-client-protocol-test/src/testy/v2.rs:157-161`) and in the Rust `simple_agent_v2` example (`src/agent-client-protocol/examples/simple_agent_v2.rs:122-126`). Neither queues. A TCK must therefore **never** overlap prompts on one session, and must classify concurrency behaviour as INFORMATIONAL.

### 3. `session/update` notification

Envelope `$def` `UpdateSessionNotification`, `schema/v2/schema.json:4269`: `required: ["sessionId","update"]`, plus optional `_meta`. `x-side: "client"` / `x-method: "session/update"` — i.e. implemented by the client, sent by the agent. **All 17 variants are agent→client only**; there is no client→agent session notification in v2 (`schema/v2/meta.json:16-21`).

`update` is the `SessionUpdate` union (`:4300`), discriminated by `sessionUpdate`. Each branch is `{sessionUpdate: <const>}` ∧ the referenced `$def`, so the branch's required set is `["sessionUpdate"] ∪ <def>.required`. Full table:

| `sessionUpdate` | `$def` (line) | Required (besides `sessionUpdate`) | Optional | New in v2? |
|---|---|---|---|---|
| `user_message_chunk` | `ContentChunk` `:4738` | `messageId`, `content` (a **single** `ContentBlock`) | `_meta` | kept; `messageId` now required |
| `user_message` | `UserMessage` `:4767` | `messageId` | `content` (`array \| null`), `_meta` | **new** |
| `agent_message_chunk` | `ContentChunk` `:4738` | `messageId`, `content` | `_meta` | kept; `messageId` now required |
| `agent_message` | `AgentMessage` `:4797` | `messageId` | `content`, `_meta` | **new** |
| `agent_thought_chunk` | `ContentChunk` `:4738` | `messageId`, `content` | `_meta` | kept; `messageId` now required |
| `agent_thought` | `AgentThought` `:4827` | `messageId` | `content`, `_meta` | **new** |
| `state_update` | `StateUpdate` `:4940` | `state` | per-state (below) | **new** |
| `tool_call_content_chunk` | `ToolCallContentChunk` `:5040` | `toolCallId`, `content` (single `ToolCallContent`) | `_meta` | **new** |
| `tool_call_update` | `ToolCallUpdate` `:674` | `toolCallId` | `name`, `title`, `kind`, `status`, `content`, `locations`, `rawInput`, `rawOutput`, `_meta` | kept; now the only tool-call variant (v1's `tool_call` create is gone) |
| `terminal_update` | `TerminalUpdate` `:5111` | `terminalId` | `command`, `cwd`, `output`, `exitStatus`, `_meta` | **new** |
| `terminal_output_chunk` | `TerminalOutputChunk` `:5173` | `terminalId`, `data` (base64) | `_meta` | **new** |
| `plan_update` | `PlanUpdate` `:5397` | `plan` (`PlanUpdateContent`) | `_meta` | replaces v1 `plan` |
| `available_commands_update` | `AvailableCommandsUpdate` `:5516` | `availableCommands` | `_meta` | kept |
| `config_option_update` | `ConfigOptionUpdate` `:5538` | `configOptions` (full set) | `_meta` | kept |
| `session_info_update` | `SessionInfoUpdate` `:5560` | — | `title`, `updatedAt`, `_meta` | kept |
| `usage_update` | `UsageUpdate` `:5606` | `used`, `size` | `cost`, `_meta` | kept |
| *(any other string)* | open branch, `:4300` last | `sessionUpdate` | anything | **new** open fallback with a `not` over the 16 known consts |

Removed relative to v1: `tool_call` (create), `current_mode_update`, `plan` (flat). Draft-only (**not** in stable v2): `notice`, `plan_removed`, `compaction_update`, `compaction_summary_chunk` — present only in `schema/v2/schema.unstable.json` and `docs/protocol/v2/draft/prompt-lifecycle.mdx:319-401`. This matters: the Python SDK generates its v2 models from the **unstable** artifact (§6).

**Ordering constraints actually stated:**
- Per-`messageId` order is significant: "Clients apply message updates and chunks in the order they are received for each `messageId`" (`prompt-lifecycle.mdx:250`). Nothing constrains ordering *across* different `messageId`s.
- `running` must precede the work it describes ("when foreground work starts or resumes", `:159`); the idle that ends work comes after (`:348`).
- Cancellation only: pending updates MUST be flushed before the idle-cancelled (`:530`) — cancel researcher's territory.
- Tool-call content: `tool_call_content_chunk` appends; a later `tool_call_update` with `content` replaces the accumulated content (`:415`).
- Terminal: `terminal_output_chunk` bytes are decoded per chunk and appended in received order; a `terminal_update.output` snapshot **replaces** all stored bytes and MUST NOT be spliced (`docs/protocol/v2/tool-calls.mdx:441-476`).
- A tool-call `terminal` content item and the terminal's own updates "may arrive in either order" (`tool-calls.mdx:411`).
- **No global ordering rule** exists between the prompt response and any update (`:129` explicitly permits either order).

**Upsert / patch variants — wire shape and ordering only** (deep-merge semantics deferred to the upsert-patch-semantics slice, per the delta report §4.5 and my brief):
- `user_message` / `agent_message` / `agent_thought` are upserts keyed by `messageId`. Three-state `content`: omitted → unchanged; `null` or `[]` → cleared; concrete array → replaces everything including chunk-accumulated content (`:248-258`, `migration.mdx:329-339`).
- `tool_call_update` is an upsert keyed by `toolCallId`; the first update for an unseen id creates the call, and `title` SHOULD be on the first report (`migration.mdx:345`). Every non-key field is a patch (omit / `null` / value).
- `terminal_update` is an upsert keyed by `terminalId` with the same three-state patch rule (`tool-calls.mdx:432-435`).
- `_meta` follows the same three-state rule at the top level of these upserts (`migration.mdx:717`).
- **Consequence for a TCK**: the *distinction* between "omitted" and "`null`" is not observable in Python unless the driver keeps the raw JSON. `tck.harness`'s `TranscriptEntry.parsed` already preserves it (`null` → `None` present in the dict vs key absent), so a v2 driver must compare on key presence, never on `.get(...) is None`.

### 4. `state_update` and turn completion

`$def` `StateUpdate` (`schema/v2/schema.json:4940`) is a union discriminated by `state`:

| `state` | `$def` | Fields |
|---|---|---|
| `running` | `RunningStateUpdate` `:4857` | only `_meta` |
| `idle` | `IdleStateUpdate` `:4904` | `stopReason` (`StopReason \| null`, **optional**), `_meta` |
| `requires_action` | `RequiresActionStateUpdate` `:4928` | only `_meta` |
| *(other)* | inline `:4940` last branch | `state` + `additionalProperties: true`, guarded by `not` over the three known consts |

None of the three known state objects has a `required` list, so `state` is the only structurally required key.

**Stop reason value set** (`StopReason` `:4869`): `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`, plus an **open** final branch that is a bare `{"type": "string"}` with **no `not` exclusion**. Semantics (`prompt-lifecycle.mdx:464-481`) are unchanged from v1; only the carrier moved. Custom values MUST begin with `_`; unknown non-underscore values are reserved for future ACP (`:481`, `extensibility.mdx:113-118`).
→ **JSON-Schema validation alone cannot reject an invalid stop reason in v2.** A v2 TCK must compare the value in Python.

**State machine, as far as upstream defines it.** The spec never draws a machine; it states four obligations and one permission. Reading them together:

1. *Initial state is unstated.* There is no "a new session starts idle" sentence anywhere in `session-setup.mdx` or `prompt-lifecycle.mdx`. Nothing requires a `state_update` before the first prompt.
2. *`idle` before `running` is legal.* `idle` is defined purely as "The Agent is ready to process a new prompt" (`:489-491`), not as "work ended". An agent may announce readiness at session creation. The Python SDK's own test agent does exactly this (§6). Such an idle carries **no** `stopReason`, because it does not end foreground work (`:348`).
3. *`running` MUST precede the idle that ends foreground work.* Not stated as an ordering rule, but entailed: `running` MUST be sent "when foreground work starts or resumes" (`:159`), and a `stopReason` is required precisely "when the transition ends foreground work" (`:348`). Work that ends must have started. So: **an idle carrying a `stopReason`, with no preceding `running` in the same session, is non-conformant.** (Labelled as inference, not a quoted rule.)
4. *An accepted prompt does not by itself oblige `running`.* A prompt "starts **or contributes to**" foreground work (`:6`), and a locally handled command may insert a live-only user message with no model work at all (`:153`, `docs/rfds/v2/prompt.mdx:308`). An agent that was already `running` when the prompt arrived need not re-announce `running`. This is the main honesty caveat for an `ACP-STATE-201`-style test.
5. *Completion signal.* The client learns the turn ended **only** from an idle `state_update` for that `sessionId`; the `stopReason` on it says why (`:348`, `:462`). The prompt response tells you nothing about completion (`:155`).
6. *Timing relative to the response.* Unconstrained in both directions. `user_message` and `running` may precede the response (`:129` is explicit for the user message; nothing forbids the rest). The Rust `simple_agent_v2` example inserts a `tokio::task::yield_now()` specifically so the response usually wins the race (`acp-rust-sdk:src/agent-client-protocol/examples/simple_agent_v2.rs:287-289`) — a deliberate courtesy, not a requirement.
7. *Updates after the turn-ending signal are legal.* "Background activity **MAY** continue and emit other `session/update` notifications while the Agent reports `idle`. These notifications do not change the state." (`:497`). There is **no** v2 analogue of v1's "no update after the response" rule for the normal end-of-turn case; the only ordering guarantee of that flavour is the cancellation one (`:530`).

Canonical happy-path sequence (`prompt-lifecycle.mdx:18-63`):

```
C→A  session/prompt {sessionId, prompt}
A→C  result {messageId}                      # insertion receipt
A→C  session/update user_message {messageId, content}   # may precede the result
A→C  session/update state_update {state:"running"}
     … plan_update / agent_message(_chunk) / agent_thought(_chunk) /
       tool_call_update / tool_call_content_chunk / terminal_* / usage_update …
     [ A→C session/request_permission ; A→C state_update requires_action ;
       C→A outcome ; A→C state_update running ]
A→C  session/update state_update {state:"idle", stopReason:"end_turn"}
```

### 5. Client requests during a turn

The complete v2 agent→client surface is four methods (`schema/v2/meta.json:16-21`): `session/request_permission`, `session/update`, `elicitation/create`, `elicitation/complete`. `fs/*` and `terminal/*` were removed entirely (`migration.mdx:53-54,628-637`), so on a v2 connection they are simply unknown methods.

**`session/request_permission`** — `RequestPermissionRequest` `:545`, `x-side: "client"`.

| Field | Type | Req? |
|---|---|---|
| `sessionId` | `SessionId` | **required** |
| `title` | `string` | **required** (new in v2) |
| `description` | `string \| null` | optional |
| `subject` | `RequestPermissionSubject \| null` (`:600`) | optional (new in v2) |
| `options` | `PermissionOption[]`, `minItems: 1` | **required** |
| `_meta` | `object \| null` | optional |

`RequestPermissionSubject` is a tagged union: `tool_call` → `{toolCall: ToolCallUpdate}` (`:1935`); `command` → `{command, cwd}` required, `toolCallId`/`terminalId`/`_meta` optional (`:1950`); plus an open `other` branch. `PermissionOption` (`:1999`) requires `optionId`, `name`, `kind`; `PermissionOptionKind` (`:2036`) is `allow_once | allow_always | reject_once | reject_always` + open fallback.

Response `RequestPermissionResponse` `:6639`: `required: ["outcome"]`. `RequestPermissionOutcome` `:6662` is a union on `outcome`:
- `{"outcome": "cancelled"}` — the client MUST send this for every pending permission request once it has sent `session/cancel` (`:6662` description; `prompt-lifecycle.mdx:515`; `tool-calls.mdx:304`).
- `{"outcome": "selected", "optionId": <PermissionOptionId>}` (`SelectedPermissionOutcome` `:6731`, `required: ["optionId"]`).
- open `other` branch — "Agents that do not understand this outcome **MUST NOT** treat it as approval."

There is no upstream statement forbidding a permission request after the turn's idle. Since tool execution is foreground work and background activity is explicitly allowed while idle (`:497`), a permission request arriving after idle is **not** a violation the TCK can assert on.

**`elicitation/create`** — `CreateElicitationRequest` `:2066`, a union on `mode` (`form` / `url` / open `other`), with `message` required at the top level. Response `CreateElicitationResponse` `:6752` is a union on `action`: `accept` (`ElicitationAcceptAction` `:6888`, optional `content`), `decline`, `cancel`, plus open fallback. Client capability path is `capabilities.elicitation.{form,url}` (`ClientCapabilities` `:5842` → `ElicitationCapabilities` `:5914`); `{}` advertises **no** modes (`elicitation.mdx:38-51`). Agents MUST NOT request an unadvertised mode (`:54`), and a client receiving one answers `-32602` (`:166`). Agents MUST handle `decline`/`cancel`/failure gracefully (`:151-153`).

**How the agent must react to a declined/cancelled outcome.** For elicitation, explicitly: "fall back safely, retry, or fail the originating operation" (`elicitation.mdx:152`). For permission, the only normative statements are (a) MUST NOT treat an unknown outcome as approval (`:6662`), and (b) for cancellation the agent MUST end with idle + `cancelled` (`:519`). There is **no** statement that a `reject_once` selection MUST fail the tool call — from a client harness, a rejected permission followed by the agent running the tool anyway is not detectable at all (the TCK cannot see the agent's side effects).

### 6. Reference behaviour

#### 6.1 Rust `testy` v2 — live transcript

Built at `2a78849` with `--no-default-features --features unstable_protocol_v2`; implementation at `acp-rust-sdk:src/agent-client-protocol-test/src/testy/v2.rs`. Observed, verbatim (elided `jsonrpc` fields for width):

```
→ initialize {protocolVersion:2, info:{…}}
← {"id":1,"result":{"protocolVersion":2,"info":{"name":"test-agent","version":"0.11.0"},"capabilities":{"session":{}}}}
→ session/new {cwd:"/tmp"}
← {"id":2,"result":{"sessionId":"testy-v2-session-1"}}
→ session/prompt {sessionId:"testy-v2-session-1", prompt:[{type:"text",text:"greet"}]}
← {"id":3,"result":{"messageId":"testy-v2-user-message-0"}}
← session/update {sessionId:…, update:{sessionUpdate:"user_message",messageId:"testy-v2-user-message-0",content:[{type:"text",text:"greet"}]}}
← session/update {… update:{sessionUpdate:"state_update",state:"running"}}
← session/update {… update:{sessionUpdate:"agent_message_chunk",messageId:"testy-v2-agent-message-1",content:{type:"text",text:"Hello, world!"}}}
← session/update {… update:{sessionUpdate:"state_update",state:"idle",stopReason:"end_turn"}}
```

Notes and deviations:
- Order is deterministically **response → `user_message` → `running` → content → `idle(stopReason)`** (`v2.rs:498` responds, then `:500` spawns `process_prompt`, which sends the user message at `:314` and `running` at `:316-322`). The Rust integration test asserts exactly this order (`src/agent-client-protocol-test/tests/testy_v2.rs:106-145`).
- `messageId`s come from one connection-wide counter shared by user and agent messages (`v2.rs:80-85`), so they are distinct across submissions — P10 holds. Second prompt returned `testy-v2-user-message-2`.
- **Never emits `requires_action`** (no permission requests at all) and never emits a full `agent_message` live — it only records one into replay history (`v2.rs:378-383`). Both legal.
- **Concurrent prompt rejected**: second prompt while `wait_for_cancel` was running → `{"code":-32602,"message":"Invalid params","data":"session \`testy-v2-session-1\` already has foreground work"}` (`v2.rs:157-161`). *Informational*, not a bug — X1 says the spec is silent.
- **Unknown session** → `-32602 … "unknown session \`nope\`"` (`v2.rs:153`). *Informational*, spec silent (X2).
- **Accepts an `image` content block although it advertises no `capabilities.session.prompt.image`** — verified live. *Not a bug*: P4 is a **client**-side MUST (`prompt-lifecycle.mdx:100`); nothing obliges an agent to reject over-rich content.
- `capabilities: {"session": {}}` only — so every prompt-capability test against `testy` v2 SKIPs, and it is **not** a useful positive fixture for `ACP-PROMPTCAP-*`.
- Cancel path (one line, cross-referenced only): after `session/cancel`, it emitted exactly `state_update {state:"idle", stopReason:"cancelled"}` with no intervening content.

The Rust `simple_agent_v2` example (`src/agent-client-protocol/examples/simple_agent_v2.rs:273-324`) is the same shape, plus it emits an `agent_message` full snapshot after the chunk with the same `messageId` — a deliberate demonstration of replace-after-append that the comment flags as "clients must not render it a second time" (`:319-321`).

#### 6.2 Python SDK v2

No runnable v2 example agent exists (`examples/` has only v1 scripts). The v2 runtime (`src/acp/experimental/v2/`) is transport plumbing: it validates request/response models and routes, but imposes **no lifecycle ordering** — the agent author decides when to send `state_update`s. `docs/experimental-v2.md:99-105` restates the contract correctly ("`session/prompt` returns after the agent inserts the user message … The response requires a non-null `message_id` … That update may arrive before or after the response").

Two findings a TCK must absorb:

1. **`idle` as an initial ready state.** The SDK's own reference agent in `tests/test_v2_runtime.py:92` sends `IdleSessionStateUpdate()` (no `stopReason`) immediately after `session/new`, then `RunningSessionStateUpdate()` on prompt, and the test asserts the client observes `idle, running, user_message, idle(stop_reason="end_turn")` in that order (`tests/test_v2_runtime.py:277-291`). This is **spec-legal** (§4 point 2) and is exactly the pattern that breaks a naive "first idle after the prompt ends the turn" detector. *Informational, not a bug.*
2. **The Python SDK's vendored v2 schema is the *unstable* artifact.** `acp-python-sdk:schema/v2/schema.json` has 267 `$defs` and is byte-for-byte the spec's `schema/v2/schema.unstable.json` (verified by `$defs` set diff: empty both ways), not the 175-`$def` stable `schema/v2/schema.json`. Consequently `v2.schema.SessionNotice` exists (`src/acp/experimental/v2/schema.py:3818`) and `docs/experimental-v2.md:107-110` advertises sending `sessionUpdate: "notice"`, which is **not** in stable v2. An agent built on this SDK can emit `notice`, `plan_removed`, or `compaction_*` updates on a plain `protocolVersion: 2` connection. Per `extensibility.mdx:115-117` those are unknown non-underscore values reserved for future ACP. **Likely bug / at minimum a gating gap** — but it is an SDK packaging issue, so a v2 TCK should record unknown `sessionUpdate` discriminators as INFORMATIONAL rather than FAIL them, or it will red-flag every Python-SDK-based agent.

---

## Testability notes

### Candidate v2 requirement rows

Id scheme per the brief: reuse a v1 id only when it is literally the same requirement re-cited against v2; otherwise a 2xx number in the area.

| Id | Tier | Requirement | Citation | Conforming vs non-conforming agent |
|---|---|---|---|---|
| `ACP-PROMPT-201` | MANDATORY | The `session/prompt` result is an object with a `messageId` key whose value is a non-empty string. No `stopReason` (that key is an unknown root field for `PromptResponse`). | `prompt-lifecycle.mdx:124-127`; `schema/v2/schema.json:4097` | Conforming: `{"messageId":"m1"}`. Non-conforming: `{}`, `{"messageId":null}`, `{"messageId":123}`, or the v1-shaped `{"stopReason":"end_turn"}`. |
| `ACP-PROMPT-202` | ADVISORY (race-skipped) | The prompt response is an acceptance: it arrives before the turn-ending idle `state_update`. | `prompt-lifecycle.mdx:110`; `migration.mdx:251` | Conforming: response, then idle. Non-conforming: idle observed before the response (agent still blocks the RPC for the whole turn). SKIP if the whole turn completes inside `cancel_race_peek(timeout)` — a fast agent's ordering is not provable. |
| `ACP-PROMPT-203` | MANDATORY | A `user_message` (with `content`) or ≥1 `user_message_chunk` carrying **the response's `messageId`** is observed for the prompted session, before or after the response, no later than the turn-ending idle. | `prompt-lifecycle.mdx:129`; `migration.mdx:261` | Conforming: either form, same id. Non-conforming: no user-message update at all, or one with a different `messageId`. |
| `ACP-PROMPT-204` | MANDATORY | Two sequential prompts with identical content on one session return **different** `messageId`s. | `prompt-lifecycle.mdx:151` | Conforming: `m1` then `m2`. Non-conforming: the same id twice. Must run the second prompt only after the first turn's idle (X1). |
| `ACP-PROMPT-002` *(reused)* | MANDATORY | Every `session/update` the agent emits during the turn validates against the v2 schema and carries the prompted `sessionId`. Vacuous pass if the agent emits none. | `schema/v2/schema.json:4269,4300` | Non-conforming: `sessionId: "other"`, or a malformed known-discriminator payload. |
| `ACP-PROMPT-003` *(reused, still ADVISORY)* | ADVISORY | A prompt of text + `resource_link` is accepted. The v1 doc conflict survives verbatim into v2 (Discrepancy 2), so keep it advisory. | `initialization.mdx:203` vs `content.mdx:33` | Conforming: accepted, turn reaches idle. Non-conforming: JSON-RPC error. |
| `ACP-STATE-201` | MANDATORY | If a turn-ending idle `state_update` (one carrying a `stopReason`) is observed, a `state_update {state:"running"}` for that session MUST have been observed earlier in the run. | `prompt-lifecycle.mdx:159,348` (inference, §4 point 3) | Conforming: `running` … `idle{stopReason}`. Non-conforming: straight to `idle{stopReason:"end_turn"}` with no `running` ever. Vacuous if no stop-reason-bearing idle was seen (then `ACP-STATE-203` reports it). |
| `ACP-STATE-202` | MANDATORY | After an accepted prompt, an idle `state_update` for that session arrives within the per-turn deadline. | `prompt-lifecycle.mdx:348`; `migration.mdx:282` | Conforming: idle arrives. Non-conforming: agent streams content forever, or goes quiet after `running`, and never reports idle. |
| `ACP-STATE-203` | **ADVISORY (recommended)** — MUST in prose, SHOULD in schema | The idle that ends the prompt-initiated turn carries a `stopReason`. | `prompt-lifecycle.mdx:348` vs `schema/v2/schema.json:4904` — Discrepancy 1 | Conforming: `{"state":"idle","stopReason":"end_turn"}`. Non-conforming (advisory): bare `{"state":"idle"}`. Recommend ADVISORY until upstream reconciles; MANDATORY is defensible and would be the stricter read. |
| `ACP-STATE-204` | MANDATORY | Any `stopReason` the agent emits is one of the five known values or begins with `_`. Not schema-checkable (`StopReason`'s fallback is a bare string). | `prompt-lifecycle.mdx:481`; `schema/v2/schema.json:4869`; `extensibility.mdx:113-118` | Conforming: `end_turn`. Non-conforming: `"done"`, `"finished"`. Conforming-but-custom: `"_vendor/timeout"`. |
| `ACP-STATE-205` | MANDATORY | Any `state` value is `running`/`idle`/`requires_action` or begins with `_`. | `prompt-lifecycle.mdx:487-495`; `extensibility.mdx:113-118` | Non-conforming: `{"state":"working"}`. |
| `ACP-STATE-206` | ADVISORY | If the agent sends `session/request_permission` during the turn, it reports `requires_action` while blocked and `running` when work resumes. SKIP when no permission request was seen. | `prompt-lifecycle.mdx:371` | Conforming: `running → requires_action → (answer) → running → idle`. Non-conforming (advisory): stays `running` across the block. |
| `ACP-STATE-207` | INFORMATIONAL | Record whether any `session/update` arrives **after** the turn-ending idle. Never assert: `prompt-lifecycle.mdx:497` explicitly allows it. | `prompt-lifecycle.mdx:497` | There is no non-conforming agent here — this is the v2 replacement for v1's `ACP-CANCEL-002`-style "nothing after the end" intuition, and it must not become a test. |
| `ACP-MSG-201` | MANDATORY (schema-covered) | Every message update / chunk carries a `messageId`. Already enforced by `ACP-PROMPT-002`'s schema validation; keep a separate id only for report legibility. | `prompt-lifecycle.mdx:246`; `schema/v2/schema.json:4738,4767,4797,4827` | Non-conforming: `agent_message_chunk` with no `messageId`. |
| `ACP-PROMPTCAP-001/002/003` *(reused ids, new gate)* | capability:`capabilities.session.prompt.image` / `.audio` / `.embeddedContext` — **object markers**, so `capability_is_supported(..., boolean=False)` | A prompt containing the gated block alongside text is accepted (`messageId` returned) and the turn reaches idle without a JSON-RPC error. | `initialization.mdx:201-226`; `schema/v2/schema.json:3219`; block shapes `:1194`, `:1238`, `:1504` | Conforming: accepted. Non-conforming: `-32602` on a block type it advertised. The assertion target changes from v1's "valid `stopReason` in the response" to "accepted + reaches idle". |
| `ACP-CLIENTCAP-201` | MANDATORY | With a mock client advertising `capabilities: {}`, no `elicitation/create` is observed during a prompt turn. | `elicitation.mdx:54`; `schema/v2/schema.json:5842` | Non-conforming: sends `elicitation/create` mid-turn. |
| `ACP-CLIENTCAP-202` | MANDATORY | No `fs/*` or `terminal/*` request is observed on a v2 connection — those methods do not exist in v2. | `schema/v2/meta.json:16-21`; `migration.mdx:628-637` | Non-conforming: any `fs/read_text_file`, `terminal/create`, … (This is the v2 collapse of v1's `ACP-CLIENTCAP-001/002`; coordinate with the initialize/capabilities slice so it is not double-owned.) |
| `ACP-PERM-201` | MANDATORY (vacuous when unseen) | Any `session/request_permission` the agent sends validates: `sessionId`, non-empty `title`, `options` with ≥1 entry, each option carrying `optionId`/`name`/`kind`. | `schema/v2/schema.json:545,1999`; `tool-calls.mdx:233,253` | Non-conforming: omits `title` (new in v2), or sends `options: []`. |
| `ACP-INFO-V2CONCURRENT-001` | INFORMATIONAL | Record what the agent does with a second `session/prompt` while a turn is running (accept / error code / silence). Never assert. | `docs/rfds/v2/prompt.mdx:86` | No conforming/non-conforming distinction exists. Both Rust reference agents answer `-32602`. |
| `ACP-INFO-UNKNOWNSESSION-001` *(reused)* | INFORMATIONAL | Record the response to `session/prompt` with an unknown `sessionId`. | `docs/protocol/v2/error.mdx` is empty | Observed `-32602` in Rust; v1 SDKs disagreed too. |
| `ACP-INFO-V2UNKNOWNUPDATE-001` | INFORMATIONAL | Record any `sessionUpdate` discriminator outside the 16 stable values (e.g. `notice` from an unstable-schema Python agent). | `schema/v2/schema.json:4300`; `extensibility.mdx:115-117`; §6.2 | Would otherwise red-flag every Python-SDK v2 agent. |

**v1 prompt-area ids with no v2 counterpart (retire for v2):**

| v1 id | Why it has no v2 counterpart |
|---|---|
| `ACP-PROMPT-001` | Its whole content — "the `session/prompt` result's `stopReason` is a defined value" — is gone: `PromptResponse` has no `stopReason` (`schema/v2/schema.json:4097`). Its *intent* splits into `ACP-PROMPT-201` (response shape) and `ACP-STATE-203/204` (stop reason on idle). |
| `ACP-MODES-001` | `modes` was removed from the `session/new`/`session/resume` response (`migration.mdx:598`; `NewSessionResponse` `schema/v2/schema.json:3627` has no `modes`). |
| `ACP-MODES-002` | `session/set_mode` and the `current_mode_update` notification were both removed; replaced by `session/set_config_option` / `config_option_update` (`migration.mdx:49,72,606-608`; no `SetSessionModeRequest` `$def` in v2). |
| `ACP-CONFIG-003` | Its gate, `clientCapabilities.session.configOptions.boolean`, no longer exists — v2 `ClientCapabilities` is `{auth, elicitation, _meta}` only (`schema/v2/schema.json:5842`), and `BooleanConfigOptionCapabilities` is absent from the v2 `$defs`. |
| `ACP-CONFIG-001/002` | **Not** retired — `session/set_config_option` and `config_option_update` survive (with `id`→`configId`, `group`→`groupId`; `migration.mdx:705-706`). They are out of the prompt-turn scope; route them to a session-config slice. |

### Mock-client prompt driver design note

The v1 `run_prompt` contract inverts: the prompt response is no longer the terminator, so the driver's loop must be driven by notifications with an explicit, bounded turn-end predicate.

**Minimal event loop** (one `session/prompt`, one turn):

1. Record the transcript index, send `session/prompt`, and **do not** wait for the response first — start the read loop immediately, because `user_message` and `running` may legally precede it (`prompt-lifecycle.mdx:129`).
2. Read lines until the terminator or a deadline. For each line:
   - **response with our id** → capture it; extract `messageId`; do **not** return.
   - **`session/update`** → append `(transcript_index, entry)`; if `update.sessionId != our session` still record it (that is `ACP-PROMPT-002`'s evidence, not a reason to stop).
   - **`session/request_permission`** → reply `{"outcome":{"outcome":"selected","optionId":<options[0].optionId>}}`, or `{"outcome":{"outcome":"cancelled"}}` once cancel has been sent for this turn (`tool-calls.mdx:304`). Record it.
   - **any other agent→client request** (`elicitation/create`, and anything v1-shaped like `fs/*`/`terminal/*`) → reply `-32601`, record it on `client_requests_seen`.
   - **`elicitation/complete` or any other notification** → record, continue.
3. **Turn-end predicate** (the crux). Accept a `state_update` with `state == "idle"` for our `sessionId`, observed at a transcript index **after** we sent the prompt, **and** either (a) it carries a `stopReason`, or (b) a `state_update {state:"running"}` for that session was observed earlier in this turn. Rationale: (a)/(b) each independently exclude the legal "session-ready idle" that the Python SDK's agent emits (§6.2). A bare idle matching neither is held as a *candidate* terminator: wait one `quiet_period(timeout)`; if nothing more arrives, end the turn with `turn_end_kind="bare_idle"` and let the test decide (advisory/informational), instead of hanging.
4. Return a `V2PromptTurn(response_entry, message_id, updates, client_requests_seen, running_at_index, idle_entry, stop_reason, turn_end_kind, timed_out)`.

**Bounded waits — the driver must never hang** (the non-conforming agents it must survive):

| Agent misbehaviour | Bound |
|---|---|
| Never answers `session/prompt` | per-read `--timeout` (`agent_launch.default_timeout`) via `AgentProcess.read_line`, as in v1. |
| Answers, then never sends `idle` | an explicit **turn deadline** (suggest `default_timeout`, or a new `--tck-turn-timeout`) measured from the prompt send; on expiry return with `timed_out=True` so `ACP-STATE-202` FAILs with a message, rather than falling through to the `--test-timeout` watchdog. |
| Streams updates forever | cap the recorded update count (suggest 2000) **and** keep the turn deadline; stop reading past the cap. |
| Sends a bare `idle` with no `stopReason` and no prior `running` | the `quiet_period` candidate rule above — terminate, don't wait. |
| Sends `idle` *before* the prompt response | keep reading for the response until the per-read timeout, then return with `response_entry=None`; do not treat the early idle as "no turn happened". |
| Rejects the prompt with a JSON-RPC error | return immediately with the error; no turn-end wait at all (no insertion ⇒ no obligations). |
| Emits a second `idle` after the first (background churn) | ignore everything after the terminator except for `ACP-STATE-207`'s informational record, which does one `quiet_period` post-idle read. |
| Sends `session/request_permission` with `options: []` | the driver must not index `options[0]` blindly — answer `{"outcome":{"outcome":"cancelled"}}` and let `ACP-PERM-201` FAIL. |
| Sends a `session/update` with an unknown `sessionUpdate` | record and continue; never crash on the discriminator (`ACP-INFO-V2UNKNOWNUPDATE-001`). |

**Serialize prompts per session.** Because X1 is unspecified and both reference agents hard-error on overlap, the driver must never issue a second `session/prompt` for a session before that session's turn-end predicate fired (or the turn deadline expired). `ACP-PROMPT-204` (distinct `messageId`s) therefore runs two *sequential* turns.

**Suggested fixture agents** (all stdlib, deterministic, offline; a v2 `_base_v2.py` mirroring `_base.py`):

- `v2_conforming.py` — response(`messageId`) → `user_message` → `running` → `agent_message_chunk` → `idle{end_turn}`. The baseline PASS-everything fixture.
- `v2_updates_before_response.py` — emits `user_message` + `running` *before* the prompt response. Conforming; proves the driver doesn't require response-first.
- `v2_idle_ready.py` — emits `idle` (no `stopReason`) right after `session/new`, then a normal turn. Conforming; the Python-SDK pattern; proves the turn-end predicate ignores the ready-idle.
- `v2_prompt_returns_stop_reason.py` — v1-shaped `{"stopReason":"end_turn"}`. FAILs only `ACP-PROMPT-201`.
- `v2_prompt_null_message_id.py` — `{"messageId": null}`. FAILs only `ACP-PROMPT-201`.
- `v2_no_user_message.py` — never echoes the user message. FAILs only `ACP-PROMPT-203`.
- `v2_wrong_user_message_id.py` — echoes under a different `messageId`. FAILs only `ACP-PROMPT-203`.
- `v2_duplicate_message_id.py` — same `messageId` for every submission. FAILs only `ACP-PROMPT-204`.
- `v2_no_running.py` — response → `user_message` → `idle{end_turn}`. FAILs only `ACP-STATE-201`.
- `v2_never_idle.py` — response + `running` + content, then silence. FAILs `ACP-STATE-202` within the turn deadline (this is the fixture that proves the driver's bound works).
- `v2_idle_without_stop_reason.py` — bare `idle`. FAILs only advisory `ACP-STATE-203`.
- `v2_bad_stop_reason.py` — `idle{stopReason:"done"}`. FAILs only `ACP-STATE-204`.
- `v2_bad_state.py` — `state_update{state:"working"}`. FAILs only `ACP-STATE-205`.
- `v2_blocks_until_turn_end.py` — withholds the prompt response until after it has sent `idle`. FAILs advisory `ACP-PROMPT-202`.
- `v2_full.py` — advertises `capabilities.session.prompt.{image,audio,embeddedContext}` as `{}` markers and accepts all three. Drives `ACP-PROMPTCAP-001..003` to PASS. (Required: `testy` v2 advertises only `{"session":{}}`, so it cannot serve this role.)
- `v2_calls_elicitation_unadvertised.py` — sends `elicitation/create` mid-turn. FAILs `ACP-CLIENTCAP-201`.
- `v2_permission_no_title.py` / `v2_permission_no_options.py` — FAIL `ACP-PERM-201`.
- `v2_updates_after_idle.py` — content after `idle{end_turn}`. **Must PASS everything** (`prompt-lifecycle.mdx:497`) — the regression guard against re-importing v1's "nothing after the end" instinct.

**Unobservable from a client harness — do not write tests for these:**
- Whether the prompt response was truly sent *at insertion* rather than after some internal queueing step (P5/P6). Only the gross ordering vs. `idle` is observable, hence `ACP-PROMPT-202` is advisory + race-skipped.
- Whether the agent treated an unknown permission outcome as approval (C4) — the TCK cannot see side effects.
- Whether `content` was *omitted* vs. *`null`* mattering to the agent's own state (U4 patch semantics); the TCK can see which the agent sent, but cannot force either.
- `messageId` reuse across replay (P11) — requires retention, which is explicitly not required (`prompt-lifecycle.mdx:153`); belongs to the resume/replay slice anyway.
- Whether the agent "was already running" and so legitimately skipped a `running` update (§4 point 4) — which is exactly why `ACP-STATE-201` is phrased as a conditional on a stop-reason-bearing idle, not as "every prompt must be followed by `running`".

---

## Discrepancies

1. **`stopReason` on the idle `state_update`: MUST in prose, SHOULD in schema.** `docs/protocol/v2/prompt-lifecycle.mdx:348` and `docs/protocol/v2/migration.mdx:282` both say the agent **MUST** include the corresponding `StopReason` when the idle transition ends foreground work. `schema/v2/schema.json:4904` (`IdleStateUpdate`) has **no `required` list at all**, and its `stopReason` description says "Optional. Omitted or `null` both mean the agent is not reporting a stop reason. Agents **SHOULD** include this when the idle transition ends foreground work." JSON Schema cannot express "required only when the transition ends foreground work", so the laxity may be deliberate — but the RFC-2119 keyword genuinely differs. **This changes a tier**: MANDATORY vs ADVISORY for `ACP-STATE-203`. My recommendation is ADVISORY, following this repo's existing precedent for `ACP-PROMPT-003`, with the requirement text naming both positions. (Carried over from the delta report's Discrepancy 2; re-verified at this revision.)

2. **Baseline prompt content: `text`-only vs `text` + `resource_link`.** `docs/protocol/v2/initialization.mdx:203` — "Agents that advertise `session` **MUST** support `ContentBlock::Text` **and** `ContentBlock::ResourceLink`", echoed by the `PromptRequest.prompt` schema description (`schema/v2/schema.json:6531`). `docs/protocol/v2/content.mdx:33` — "All Agents **MUST** support text content blocks when included in prompts", with no mention of resource links. This is the **identical** conflict `ACP-PROMPT-003` already documents for v1, carried into v2 unchanged. Keep the ADVISORY tier.

3. **`docs/protocol/v2/cancellation.mdx` shows a stale prompt response.** Its internal-cancellation sequence diagram still shows `response to id=1 ({})`, i.e. an empty result, predating the alpha.5 change that made `messageId` required (`schema/v2/CHANGELOG.md:10-13`). Wire truth is the schema: `{"messageId": "…"}`. (Re-confirmed from the delta report; cancellation page is the cancel researcher's, flagged here only because it misrepresents the response shape.)

4. **Python SDK v2 is generated from the *unstable* schema.** `acp-python-sdk:schema/v2/schema.json` (267 `$defs`) is the spec's `schema.unstable.json`, not the stable `schema/v2/schema.json` (175 `$defs`); `acp-python-sdk:schema/v2/VERSION` = `refs/tags/schema-v2.0.0-alpha.5`. The SDK therefore exposes and documents `SessionNotice` / `sessionUpdate: "notice"` (`src/acp/experimental/v2/schema.py:3818`, `docs/experimental-v2.md:107-110`), which exists only in `docs/protocol/v2/draft/prompt-lifecycle.mdx:319-401`. Spec says such unknown non-underscore values are "reserved for future ACP variants" and MUST NOT be treated as extensions (`extensibility.mdx:115-117`). Implementation-vs-spec conflict; recommend INFORMATIONAL handling, not a FAIL.

5. **No discrepancy found** between prose, schema, and both SDKs on: the `messageId` requirement and its type; the `session/update` variant set and required fields; the five stop-reason values; the state value set; the permission request/response shape; or the "response and user-message update may arrive in either order" rule.

---

## Open questions

Adjacent unknowns I did not pursue — route elsewhere:

1. **Is a bare `idle` (no `stopReason`, no preceding `running`) ever *required*?** Specifically: must an agent that handles a prompt with zero foreground work still emit an `idle`? `prompt-lifecycle.mdx:348` says "when the Agent is ready to process a new prompt, it MUST report `idle`" without saying whether a no-op transition counts. Affects whether `ACP-STATE-202` can be MANDATORY unconditionally. Worth an upstream question rather than more reading.
2. **Deep merge semantics of the upsert variants** (`user_message`/`agent_message`/`agent_thought`/`tool_call_update`/`terminal_update`/`_meta`) — three-state omit/`null`/value, and how much of it is client-side-only. Explicitly deferred by my brief; §3 covers wire shape and ordering only.
3. **Cancellation ordering and the `cancelled` stop reason** — owned by the concurrent cancellation researcher; I stated the turn-completion signal fully so they can reference it, and cross-referenced `prompt-lifecycle.mdx:519,530` once.
4. **`session/close` mid-turn** — `docs/protocol/v2/session-setup.mdx:258` says the agent MUST cancel ongoing work as if `session/cancel`. That interacts with the turn-end predicate (the v1 TCK's `ACP-CLOSE-002` used `on_action`). Route to the session-lifecycle slice.
5. **Does the v2 TCK need a v2 cross-check fixture, and is `testy --features unstable_protocol_v2` it?** It works (transcript in §6.1) but advertises only `capabilities: {session:{}}`, so it exercises no prompt capability and no permission path. The Python SDK has **no** v2 example agent. Whether `scripts/cross-check.sh` should grow a v2 arm, and against what, is a build/ops decision.
6. **Should `ACP-CLIENTCAP-202` (no `fs/*`/`terminal/*` on a v2 connection) live in the prompt slice or the capabilities slice?** It is only observable during a prompt turn, but it is a capability-surface statement. Needs an ownership decision to avoid a duplicate id.
