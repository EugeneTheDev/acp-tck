# Complete inventory of the ACP protocol version 1 surface, as a client-side TCK observes it when testing an agent

**Sources checked:**

- `agent-client-protocol` (spec, source of truth) @ `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`, 2026-09-18 ("chore: release (#2172)"), `git pull --ff-only` succeeded.
- `acp-rust-sdk` (reference implementation, consulted only for one implicit behavior) @ `b28b8ad188d60f2833e6930ef994bcc35f3bcce5`, 2026-09-18. Already up to date.
- `acp-python-sdk`: not consulted (nothing in scope required it).
- `a2a-tck`: not consulted.

All `path:line` citations below are relative to the **spec repo** unless prefixed with `[rust]`.

**Confidence:** high for the wire surface, capability gating, and normative tiers (all read directly from
`schema/v1/schema.json` and `docs/protocol/v1/*.mdx`). Medium for a handful of items where the spec is silent and
I say so explicitly (e.g. error code an agent must return for an unknown session).

---

## Answer

ACP v1 is a JSON-RPC 2.0 protocol with **13 agent-side methods/notifications** and **11 client-side
methods/notifications** in the *stable* v1 schema, plus one bidirectional `$/cancel_request` notification. A
conforming agent must only implement four things unconditionally — `initialize`, `session/new`,
`session/prompt`, and `session/cancel` — and must be able to *send* `session/update`
(`docs/protocol/v1/initialization.mdx:245`). Everything else is capability-gated, and every capability lives
under `result.agentCapabilities` of the `initialize` response (`schema/v1/schema.json:2415`). The v1
`protocolVersion` value is the integer `1`; the schema types it only as a `uint16`
(`schema/v1/schema.json:2408-2414`) and the named constant lives in Rust at
`agent-client-protocol-schema/src/version.rs:23` (`ProtocolVersion::V1`). Version negotiation is: client sends
its latest; agent echoes it if supported, otherwise returns *its* latest; the client then decides whether to
continue (`docs/protocol/v1/initialization.mdx:94-98`) — there is **no error response** defined for a version
mismatch, so a TCK cannot assert one. v2 (`docs/protocol/v2/`, `schema/v2/`) is a **draft** and out of scope; it
removes `fs/*`, `terminal/*`, `session/load`, `session/set_mode`, renames `authenticate`→`auth/login`, and
redefines the prompt response as an acknowledgement rather than a turn terminator
(`docs/protocol/v2/migration.mdx:36-76`).

---

## Requirements

Tier legend: **MUST** = unconditional agent obligation; **SHOULD**; **MAY**; **cap:X** = only applies when the
agent advertises capability X; **client-cap:X** = only applies when the *client* advertises X (the TCK's mock
client controls this and can therefore drive it deterministically).

| #  | Requirement | Tier | Citation |
|----|-------------|------|----------|
| 1 | Agent must support `session/new`, `session/prompt`, `session/cancel`, and `session/update` as a baseline | MUST | `docs/protocol/v1/initialization.mdx:245`; duplicated at `docs/protocol/v1/schema.mdx:4400` |
| 2 | Client must call `initialize` before any session can be created | MUST (client) → observable agent precondition | `docs/protocol/v1/initialization.mdx:24`, `docs/protocol/v1/session-setup.mdx:8` |
| 3 | Agent must respond to `initialize` with the chosen protocol version and its capabilities | MUST | `docs/protocol/v1/initialization.mdx:54`; `schema/v1/schema.json:2340-2407` (`protocolVersion` is the only required field) |
| 4 | Agent should provide `agentInfo` (name/version) | SHOULD | `docs/protocol/v1/initialization.mdx:54,271`; `schema/v1/schema.json:2813-2838` (`name` + `version` required *inside* `Implementation`, the object itself optional) |
| 5 | If the agent supports the requested version it must echo the same version; otherwise it must return the latest it supports | MUST | `docs/protocol/v1/initialization.mdx:96` |
| 6 | Agent must treat every capability omitted from the `initialize` request as UNSUPPORTED | MUST | `docs/protocol/v1/initialization.mdx:106` |
| 7 | Agent must accept `ContentBlock::Text` and `ContentBlock::ResourceLink` in `session/prompt` | MUST | `docs/protocol/v1/initialization.mdx:204` (note: `docs/protocol/v1/content.mdx:31` states only text — see Discrepancies) |
| 8 | Agent may accept `image` / `audio` / `resource` content blocks only if advertised | cap:`agentCapabilities.promptCapabilities.{image,audio,embeddedContext}` | `docs/protocol/v1/initialization.mdx:208-218`; `schema/v1/schema.json:2480-2509` |
| 9 | Agent must return a unique `sessionId` from `session/new` | MUST | `docs/protocol/v1/session-setup.mdx:71`; `schema/v1/schema.json:2867-2910` |
| 10 | Agent must support MCP **stdio** transport in `session/new`/`session/load` | MUST | `docs/protocol/v1/session-setup.mdx:373,381` |
| 11 | Agent should connect to all MCP servers specified by the client | SHOULD | `docs/protocol/v1/session-setup.mdx:543` |
| 12 | Agent may accept MCP HTTP / SSE server configs only if advertised | cap:`agentCapabilities.mcpCapabilities.{http,sse}` | `docs/protocol/v1/session-setup.mdx:426,475,522-541`; `schema/v1/schema.json:2510-2533` |
| 13 | New agents should support the MCP HTTP transport | SHOULD | `docs/protocol/v1/session-setup.mdx:375` |
| 14 | `session/load` available | cap:`agentCapabilities.loadSession` (boolean, top level) | `docs/protocol/v1/session-setup.mdx:89-104`; `schema/v1/schema.json:2415` (`loadSession`) |
| 15 | On `session/load` the agent must replay the entire conversation as `session/update` notifications **before** responding | cap:`loadSession` + MUST | `docs/protocol/v1/session-setup.mdx:134,178` |
| 16 | `session/resume` available; must **not** replay history before responding | cap:`agentCapabilities.sessionCapabilities.resume` (object marker) | `docs/protocol/v1/session-setup.mdx:196-213,243`; `schema/v1/schema.json:2534-2605,2642` |
| 17 | `session/close` available; must cancel ongoing work as if `session/cancel` then free resources | cap:`agentCapabilities.sessionCapabilities.close` | `docs/protocol/v1/session-setup.mdx:261-299`; `schema/v1/schema.json:2654` |
| 18 | `session/list` available; must return `[]` when nothing matches; cursors opaque | cap:`agentCapabilities.sessionCapabilities.list` | `docs/protocol/v1/session-list.mdx:37-54,94,166-175`; `schema/v1/schema.json:2606` |
| 19 | `session/delete` available; deleting a nonexistent session should succeed silently | cap:`agentCapabilities.sessionCapabilities.delete` | `docs/protocol/v1/session-delete.mdx:35-52,86`; `schema/v1/schema.json:2618` |
| 20 | `additionalDirectories` accepted on `session/new`, `session/load`, `session/resume`; each entry must be absolute | cap:`agentCapabilities.sessionCapabilities.additionalDirectories` | `docs/protocol/v1/session-setup.mdx:315-344`; `schema/v1/schema.json:2630` |
| 21 | `logout` available | cap:`agentCapabilities.auth.logout` (object marker; omitted/`null` ⇒ unsupported, `{}` ⇒ supported) | `docs/protocol/v1/authentication.mdx:50,74-76`; `schema/v1/schema.json:2666-2701` |
| 22 | Agent advertises auth options in `initialize.result.authMethods`; `authenticate` is called only for a method whose `type` defines the protocol-driven flow (default `agent`) | conditional on `authMethods` being non-empty | `docs/protocol/v1/authentication.mdx:44-90,134-154`; `schema/v1/schema.json:2702-2812` |
| 23 | Agent may advertise a `terminal` auth method only when the client set `clientCapabilities.auth.terminal` | client-cap:`auth.terminal` + MUST NOT otherwise | `docs/protocol/v1/authentication.mdx:107-128`; `schema/v1/schema.json:4634-4651` |
| 24 | On a prompt turn with no pending tool calls, the agent must respond to `session/prompt` with a `StopReason` | MUST | `docs/protocol/v1/prompt-turn.mdx:217`; `schema/v1/schema.json:3424-3476` |
| 25 | After `session/cancel`, once operations are aborted and pending updates sent, the agent must respond to the in-flight `session/prompt` with `stopReason: "cancelled"` | MUST | `docs/protocol/v1/prompt-turn.mdx:332` |
| 26 | Agent must catch abort exceptions from its own client libraries and still return `cancelled` rather than a JSON-RPC error | MUST | `docs/protocol/v1/prompt-turn.mdx:339` |
| 27 | Agent should stop all model requests and tool invocations as soon as possible on `session/cancel` | SHOULD | `docs/protocol/v1/prompt-turn.mdx:330` |
| 28 | Agent may send `session/update` after `session/cancel`, but must send them **before** the `session/prompt` response | MAY + MUST (ordering) | `docs/protocol/v1/prompt-turn.mdx:343` |
| 29 | Agent must not call `fs/read_text_file` / `fs/write_text_file` unless the client advertised them | MUST NOT | `docs/protocol/v1/file-system.mdx:10,28`; `schema/v1/schema.json:4550-4573` |
| 30 | Agent must not call any `terminal/*` method unless `clientCapabilities.terminal === true` | MUST NOT | `docs/protocol/v1/terminals.mdx:10,25` |
| 31 | Agent must call `terminal/release` when a terminal is no longer needed | MUST | `docs/protocol/v1/terminals.mdx:108,248` |
| 32 | Agent must not request an elicitation mode the client did not advertise (a mismatch yields `-32602`) | MUST NOT | `docs/protocol/v1/elicitation.mdx:54,107-108` |
| 33 | Agent must not include `type: "boolean"` config options unless `clientCapabilities.session.configOptions.boolean` was advertised | MUST NOT | `docs/protocol/v1/session-config-options.mdx:119-121`; `schema/v1/schema.json:4598-4633` |
| 34 | `session/set_config_option` must respond with the **complete** list of options and their current values | MUST (when the agent exposes config options) | `docs/protocol/v1/session-config-options.mdx:216`; `schema/v1/schema.json:3400-3423` (`configOptions` required) |
| 35 | Agent must always provide a default value for every configuration option | MUST | `docs/protocol/v1/session-config-options.mdx:157` |
| 36 | Every plan update must carry the complete list of entries (client replaces wholesale) | MUST (when plans are used) | `docs/protocol/v1/agent-plan.mdx:79` |
| 37 | Agent should report the plan and should report progress via further `plan` updates | SHOULD | `docs/protocol/v1/agent-plan.mdx:12,77` |
| 38 | Agent should report each tool call to the client and should mark it `in_progress` before execution | SHOULD | `docs/protocol/v1/tool-calls.mdx:14`; `docs/protocol/v1/prompt-turn.mdx:235` |
| 39 | Tool call `name` should be included in the first report and should not change later | SHOULD / SHOULD NOT | `docs/protocol/v1/tool-calls.mdx:38-44` |
| 40 | All file paths in the protocol must be absolute; line numbers are 1-based | MUST | `docs/protocol/v1/overview.mdx:214-215`; repo root `AGENTS.md:1` |
| 41 | Implementations must not add custom fields at the root of a spec type; custom data goes in `_meta` | MUST NOT | `docs/protocol/v1/extensibility.mdx:39` |
| 42 | Custom methods must be `_`-prefixed; recipients must respond to custom requests, should ignore unknown custom notifications | MUST / SHOULD | `docs/protocol/v1/extensibility.mdx:43,52,65,109` |
| 43 | `traceparent` / `tracestate` / `baggage` should be reserved as root keys of `_meta` | SHOULD | `docs/protocol/v1/extensibility.mdx:33-37` |
| 44 | Over stdio, the agent must not write non-ACP bytes to stdout; messages are newline-delimited, UTF-8, no embedded newlines | MUST / MUST NOT | `docs/protocol/v1/transports.mdx:6,24,26` |
| 45 | On `$/cancel_request`, the receiver must send *some* response for the original request (valid result or `-32800`) | MUST *if the implementation supports it at all* (support itself is optional) | `docs/protocol/v1/cancellation.mdx:14-23`; `schema/v1/schema.json:98` (`"...free to ignore the notification"`) |
| 46 | On internal cancellation, the executing party should send the same `-32800` | SHOULD | `docs/protocol/v1/cancellation.mdx:35-38` |

---

## Details

### 1. Method / notification inventory (stable v1)

Method names are defined in `schema/v1/meta.json:2-33` (`agentMethods`, `clientMethods`, `protocolMethods`) and
as Rust constants in `agent-client-protocol-schema/src/v1/agent.rs:4728-4770` and
`agent-client-protocol-schema/src/v1/client.rs:2627-2658`. Each schema `$def` also carries `x-side` /
`x-method` annotations that authoritatively map struct → wire method (e.g. `schema/v1/schema.json:2405-2406`).

#### 1a. Client → Agent requests (the agent must handle)

| Wire method | Params (`$def`) | Result (`$def`) | Tier for an agent |
|---|---|---|---|
| `initialize` | `InitializeRequest` `schema/v1/schema.json:4429` | `InitializeResponse` `:2340` | **MUST** |
| `authenticate` | `AuthenticateRequest` `:4712` | `AuthenticateResponse` `:2839` (empty obj) | Conditional: only meaningful if `authMethods` contains a protocol-driven method |
| `logout` | `LogoutRequest` `:4735` (empty obj) | `LogoutResponse` `:2853` | cap:`agentCapabilities.auth.logout` |
| `session/new` | `NewSessionRequest` `:4749` | `NewSessionResponse` `:2867` | **MUST** |
| `session/load` | `LoadSessionRequest` `:4944` | `LoadSessionResponse` `:3215` | cap:`agentCapabilities.loadSession` |
| `session/resume` | `ResumeSessionRequest` `:5034` | `ResumeSessionResponse` `:3337` | cap:`agentCapabilities.sessionCapabilities.resume` |
| `session/close` | `CloseSessionRequest` `:5079` | `CloseSessionResponse` `:3372` | cap:`agentCapabilities.sessionCapabilities.close` |
| `session/list` | `ListSessionsRequest` `:4989` | `ListSessionsResponse` `:3250` | cap:`agentCapabilities.sessionCapabilities.list` |
| `session/delete` | `DeleteSessionRequest` `:5011` | `DeleteSessionResponse` `:3323` | cap:`agentCapabilities.sessionCapabilities.delete` |
| `session/set_mode` | `SetSessionModeRequest` `:5102` | `SetSessionModeResponse` `:3386` | **No capability field.** Implied by the agent returning `modes` from `session/new`/`load`/`resume`. Deprecated in favour of config options (`docs/protocol/v1/session-modes.mdx:6-11`) |
| `session/set_config_option` | `SetSessionConfigOptionRequest` `:5133` | `SetSessionConfigOptionResponse` `:3400` | **No agent capability field.** Implied by the agent returning `configOptions` |
| `session/prompt` | `PromptRequest` `:5197` | `PromptResponse` `:3424` | **MUST** |
| `_*` (extension) | `ExtRequest` `:2169` | `ExtResponse` `:3477` | MAY |

#### 1b. Client → Agent notifications

| Wire method | Params | Tier |
|---|---|---|
| `session/cancel` | `CancelNotification` `schema/v1/schema.json:5808` — `{sessionId REQUIRED, _meta?}`, `x-method` at `:5829` | **MUST** handle |
| `_*` | `ExtNotification` `:4276` | MAY |

#### 1c. Agent → Client requests (the TCK's mock client must implement these so the agent can use them)

| Wire method | Params | Result | Gate |
|---|---|---|---|
| `session/request_permission` | `RequestPermissionRequest` `:342` | `RequestPermissionResponse` `:5401` | **Client baseline — no capability** (`docs/protocol/v1/overview.mdx:118-126`) |
| `fs/read_text_file` | `ReadTextFileRequest` `:301` | `ReadTextFileResponse` `:5382` | client-cap `clientCapabilities.fs.readTextFile` |
| `fs/write_text_file` | `WriteTextFileRequest` `:266` | `WriteTextFileResponse` `:5368` | client-cap `clientCapabilities.fs.writeTextFile` |
| `terminal/create` | `CreateTerminalRequest` `:1156` | `CreateTerminalResponse` `:5480` | client-cap `clientCapabilities.terminal === true` |
| `terminal/output` | `TerminalOutputRequest` `:1234` | `TerminalOutputResponse` `:5503` | same |
| `terminal/release` | `ReleaseTerminalRequest` `:1265` | `ReleaseTerminalResponse` `:5562` | same |
| `terminal/wait_for_exit` | `WaitForTerminalExitRequest` `:1296` | `WaitForTerminalExitResponse` `:5576` | same |
| `terminal/kill` | `KillTerminalRequest` `:1327` | `KillTerminalResponse` `:5602` | same |
| `elicitation/create` | `CreateElicitationRequest` `:1358` | `CreateElicitationResponse` `:5616` | client-cap `clientCapabilities.elicitation.{form,url}` — per-mode |
| `_*` | `ExtRequest` `:2169` | `ExtResponse` | MAY |

Note `clientCapabilities.terminal` is a **single boolean** gating all five terminal methods
(`schema/v1/schema.json:4483` `terminal: boolean`; `docs/protocol/v1/initialization.mdx:146`), whereas `fs` is a
two-boolean object (`schema/v1/schema.json:4550`).

#### 1d. Agent → Client notifications

| Wire method | Params | Tier |
|---|---|---|
| `session/update` | `SessionNotification` `:3622` — `{sessionId REQUIRED, update: SessionUpdate REQUIRED, _meta?}` | Agent **MUST** be able to send (`docs/protocol/v1/initialization.mdx:245`) |
| `elicitation/complete` | `CompleteElicitationNotification` `:4253` — `{elicitationId REQUIRED, _meta?}` | Only for URL-mode elicitation; agent MAY send (`docs/protocol/v1/elicitation.mdx:158-163`) |
| `_*` | `ExtNotification` `:4276` | MAY |

#### 1e. Bidirectional / protocol-level

| Wire method | Params | Tier |
|---|---|---|
| `$/cancel_request` | `CancelRequestNotification` `:5831` — `{requestId: RequestId REQUIRED, _meta?}`; `x-side: "protocol"` at `:5851` | Optional to *support*; if supported, must produce a response for the cancelled request (`docs/protocol/v1/cancellation.mdx:14-23`). Receivers are explicitly "free to ignore" `$/`-prefixed notifications (`schema/v1/schema.json:98`) |

### 2. Version negotiation

- Client sends `initialize.params.protocolVersion` — required, integer `uint16` 0..=65535
  (`schema/v1/schema.json:2408-2414`, `:4429-4482`). It **MUST** be the latest version the client supports
  (`docs/protocol/v1/initialization.mdx:94`).
- Agent returns `initialize.result.protocolVersion` — required
  (`schema/v1/schema.json:2340-2407`). Same value if supported, else the agent's own latest
  (`docs/protocol/v1/initialization.mdx:96`).
- **v1 value = integer `1`.** The JSON Schema does not constrain it to `1` — it is just `uint16`. The named
  constant is Rust-only: `ProtocolVersion::V1 = Self(1)` at
  `agent-client-protocol-schema/src/version.rs:23`; `V0 = 0` (pre-release, "should likely be treated as
  unsupported", `:19`); `LATEST = V1` when the `unstable_protocol_v2` feature is off (`:39`). Wire encoding is a
  bare JSON number — a string like `"1.0.0"` must fail to deserialize
  (`agent-client-protocol-schema/src/version.rs:66-70`).
- **Mismatch behaviour:** the *client* SHOULD close the connection and inform the user
  (`docs/protocol/v1/initialization.mdx:98`). There is **no defined agent-side error** for an unsupported
  version — the agent still returns a successful `initialize` result with a different number. A TCK must not
  expect a JSON-RPC error here.
- [rust] The reference SDK negotiates by "highest compatible ≤ requested"
  (`src/agent-client-protocol/src/role/acp.rs:490-502`): given `requested >= V2` and v2 enabled it picks V2,
  else if `requested >= V1` it picks V1, else `None`. This is *implementation* behavior, not spec.
- **v2 is draft and excluded.** `docs/protocol/v2/migration.mdx:20-22` says the v2 surface as a whole is still
  labeled draft. Everything under `docs/protocol/v2/`, `schema/v2/`, and `docs/rfds/v2/` is out of scope.
  Likewise, everything present only in `schema/v1/schema.unstable.json` (diff of
  `schema/v1/meta.json` vs `meta.unstable.json`) is **v1-unstable, excluded**: `document/didOpen|didChange|
  didClose|didSave|didFocus`, `nes/start|suggest|accept|reject|close`, `providers/list|set|disable`,
  `mcp/message`, `mcp/connect`, `mcp/disconnect`, `session/fork`. The corresponding Rust items are behind
  `unstable_nes`, `unstable_llm_providers`, `unstable_mcp_over_acp`, `unstable_session_fork`,
  `unstable_end_turn_token_usage` cfgs (`agent-client-protocol-schema/src/v1/agent.rs:4613-4680`). All files
  under `docs/protocol/v1/draft/` are the draft (unstable) mirror of the stable v1 docs and must not be used
  for TCK requirements.

### 3. Session lifecycle

**`session/new`** (`schema/v1/schema.json:4749`):

| field | req | type |
|---|---|---|
| `cwd` | REQUIRED | string, must be absolute (`docs/protocol/v1/session-setup.mdx:362`) |
| `mcpServers` | REQUIRED | `McpServer[]` (may be empty) |
| `additionalDirectories` | optional | `string[]`, only when cap advertised |
| `_meta` | optional | object\|null |

Response `NewSessionResponse` (`:2867`): `sessionId` REQUIRED; `modes` optional/nullable `SessionModeState`;
`configOptions` optional/nullable array; `_meta`.

`McpServer` is an untagged-ish union (`:4786`): `McpServerHttp` (`type:"http"`, `name`,`url`,`headers` all
required, `:4853`), `McpServerSse` (`type:"sse"`, `:4881`), `McpServerStdio` (**no `type` discriminator** —
default variant — `name`,`command`,`args`,`env` **all required**, `:4909`).

**`session/load`** (cap:`loadSession`) — `LoadSessionRequest` `:4944`: `sessionId`, `cwd`, `mcpServers` all
REQUIRED, `additionalDirectories` optional. Ordering guarantee: replay the *entire* conversation as
`session/update` notifications first, respond only after all entries are streamed
(`docs/protocol/v1/session-setup.mdx:134,178`). `LoadSessionResponse` `:3215` has *no* required fields
(`modes?`, `configOptions?`, `_meta?`).

**`session/resume`** (cap:`sessionCapabilities.resume`) — `ResumeSessionRequest` `:5034`: `sessionId`, `cwd`
REQUIRED; `mcpServers` **optional** here (unlike `load`). The agent **MUST NOT** replay history before
responding (`docs/protocol/v1/session-setup.mdx:243`).

**`session/prompt`** — `PromptRequest` `:5197`: `sessionId` REQUIRED, `prompt: ContentBlock[]` REQUIRED.
`PromptResponse` `:3424`: `stopReason` REQUIRED.

**Stop reasons** (`StopReason`, `schema/v1/schema.json:3447-3476`; docs `prompt-turn.mdx:292-310`):
`end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`. Closed enum in v1.

**`session/cancel`** — notification, `{sessionId}`. Ordering contract the TCK can assert:

1. Client sends `session/cancel` and (SHOULD) marks unfinished tool calls cancelled locally
   (`prompt-turn.mdx:326`).
2. Client **MUST** answer every in-flight `session/request_permission` with
   `{"outcome":{"outcome":"cancelled"}}` (`prompt-turn.mdx:328`, `tool-calls.mdx:180`).
3. Agent SHOULD abort model + tool work (`prompt-turn.mdx:330`).
4. Agent MAY emit further `session/update`s, but **all of them must precede** the prompt response
   (`prompt-turn.mdx:343`).
5. Agent **MUST** respond to the outstanding `session/prompt` with `stopReason: "cancelled"` — not an error
   (`prompt-turn.mdx:332,339`).

`session/close` behaves "as if `session/cancel` had been called", then frees resources
(`session-setup.mdx:299`); agents MAY error if the session does not exist or is not active (`:311`).

**`session/update` variants** — `SessionUpdate`, discriminated by `sessionUpdate`
(`schema/v1/schema.json:3653-3836`, discriminator declared at `:3841`):

| `sessionUpdate` | Payload flattened from | Required payload fields | Schema line |
|---|---|---|---|
| `user_message_chunk` | `ContentChunk` `:3841` | `content: ContentBlock` (`messageId?`) | `:3665` |
| `agent_message_chunk` | `ContentChunk` | same | `:3681` |
| `agent_thought_chunk` | `ContentChunk` | same | `:3697` |
| `tool_call` | `ToolCall` `:3874` | `toolCallId`, `title` | `:3713` |
| `tool_call_update` | `ToolCallUpdate` `:380` | `toolCallId` only | `:3729` |
| `plan` | `Plan` `:4021` | `entries: PlanEntry[]` (each `content`,`priority`,`status` required) | `:3745` |
| `available_commands_update` | `AvailableCommandsUpdate` `:4107` | `availableCommands` | `:3761` |
| `current_mode_update` | `CurrentModeUpdate` `:4129` | **`currentModeId`** | `:3777` |
| `config_option_update` | `ConfigOptionUpdate` `:4150` | `configOptions` | `:3793` |
| `session_info_update` | `SessionInfoUpdate` `:4172` | none (`title?`, `updatedAt?`) | `:3809` |
| `usage_update` | `UsageUpdate` `:4216` | `used`, `size` (`cost?` → `{amount,currency}` both required, `Cost` `:4194`) | `:3825` |

`ToolCall` optional fields: `name?`, `kind?` (default `other`), `status?` (default `pending`), `content?`,
`locations?`, `rawInput?`, `rawOutput?`. `ToolKind` enum (`:465`): `read, edit, delete, move, search, execute,
think, fetch, switch_mode, other`. `ToolCallStatus` (`:520`): `pending, in_progress, completed, failed`.
`ToolCallContent` (`:545`) is `{type:"content", content: ContentBlock}` | `{type:"diff", ...Diff}` |
`{type:"terminal", terminalId}`. `Diff` (`:1019`): `path` REQUIRED, `newText` REQUIRED, `oldText` optional.

**`session/request_permission`** (agent→client) — `RequestPermissionRequest` `:342`: `sessionId`,
`toolCall: ToolCallUpdate`, `options: PermissionOption[]` all REQUIRED. `PermissionOption` `:1094`:
`optionId`, `name`, `kind` all REQUIRED; `PermissionOptionKind` `:1131` = `allow_once | allow_always |
reject_once | reject_always`. Response `:5401`: `outcome` REQUIRED, either `{"outcome":"cancelled"}` or
`{"outcome":"selected","optionId":...}` (`:5424`, `:5459`).

### 4. Content blocks and prompt capabilities

`ContentBlock` (`schema/v1/schema.json:601-688`) — tagged by `type`, five variants:

| `type` | `$def` | Required fields | Accepted in a prompt |
|---|---|---|---|
| `text` | `TextContent` `:736` | `text` | **MUST** accept (`initialization.mdx:204`, `content.mdx:31`) |
| `resource_link` | `ResourceLink` `:836` | `uri`, `name` | **MUST** accept (`initialization.mdx:204`) |
| `image` | `ImageContent` `:765` | `data`, `mimeType` (`uri?`) | cap:`promptCapabilities.image` |
| `audio` | `AudioContent` `:803` | `data`, `mimeType` | cap:`promptCapabilities.audio` |
| `resource` | `EmbeddedResource` `:965` | `resource` (`TextResourceContents` `:913` = `uri`+`text`, or `BlobResourceContents` `:939` = `uri`+`blob`) | cap:`promptCapabilities.embeddedContext` |

All five accept optional `annotations` (`Annotations` `:689`) and `_meta`. Note the *capability names do not
match the type names*: `embeddedContext` gates `type: "resource"`.

The spec puts the burden on the client ("Clients **MUST** restrict types of content according to the Prompt
Capabilities", `prompt-turn.mdx:92`) and does **not** state what an agent must do when a client violates this.
There is no defined error for "unsupported content block".

### 5. Client-implemented methods the TCK must provide

The TCK's mock client must implement `session/request_permission` unconditionally
(`docs/protocol/v1/overview.mdx:118-126`), plus whichever of `fs/*`, `terminal/*`, `elicitation/create` it
advertises. Shapes:

- `fs/read_text_file`: `{sessionId, path}` required, `line?` (1-based), `limit?` → `{content}`
  (`schema/v1/schema.json:301`, `:5382`; docs `file-system.mdx:48-64`).
- `fs/write_text_file`: `{sessionId, path, content}` all required → `{}`; the client **MUST** create the file
  if missing (`file-system.mdx:100`).
- `terminal/create`: `{sessionId, command}` required; `args?`, `env?: EnvVariable[]`, `cwd?`,
  `outputByteLimit?` → `{terminalId}` returned immediately (`:1156`, `:5480`). Truncation must occur at a
  character boundary (`terminals.mdx:85`).
- `terminal/output`: `{sessionId, terminalId}` → `{output, truncated, exitStatus?}`; `TerminalExitStatus`
  `:5538` has `exitCode?` and `signal?`, both nullable.
- `terminal/wait_for_exit`: `{sessionId, terminalId}` → `{exitCode?, signal?}` (`:5576`).
- `terminal/release`, `terminal/kill`: `{sessionId, terminalId}` → `{}`.
- `elicitation/create`: `CreateElicitationRequest` `:1358` — only `message` is required at the top level;
  scope is flattened (`sessionId`+optional `toolCallId`, or `requestId`, `:1468`/`:1495`) and `mode` is
  required and explicit (`elicitation.mdx:60-61`). Gated per mode by `clientCapabilities.elicitation.form` /
  `.url` — presence-and-non-null semantics, `{}` does **not** imply form support, deliberately unlike MCP
  (`elicitation.mdx:40-52`; `schema/v1/schema.json:4652-4711`).

Client capability object, exactly as it appears in `initialize.params.clientCapabilities`
(`schema/v1/schema.json:4483-4549`):

```
clientCapabilities: {
  fs: { readTextFile?: bool, writeTextFile?: bool },   // :4550
  terminal?: bool,                                      // :4483
  session?: { configOptions?: { boolean?: {} } },       // :4574, :4598, :4622
  auth?: { terminal?: bool },                           // :4634
  elicitation?: { form?: {}, url?: {} },                // :4652
  _meta?: {}
}
```

Agent capability object, in `initialize.result.agentCapabilities` (`schema/v1/schema.json:2415-2479`):

```
agentCapabilities: {
  loadSession?: bool,                                   // gates session/load
  promptCapabilities?: { image?, audio?, embeddedContext? },   // :2480
  mcpCapabilities?: { http?, sse? },                    // :2510
  sessionCapabilities?: {                               // :2534
    list?: {}, delete?: {}, additionalDirectories?: {}, resume?: {}, close?: {}
  },
  auth?: { logout?: {} },                               // :2666, :2690
  _meta?: {}
}
```

Object-marker capabilities use *presence and non-nullness* as the signal; `null` ≡ omitted ≡ unsupported;
`{}` ≡ supported (`docs/protocol/v1/authentication.mdx:74-76`, `docs/protocol/v1/session-delete.mdx:52`,
`docs/protocol/v1/initialization.mdx:249-262`).

### 6. Authentication and extension rules

- `authenticate` params: `{methodId}` REQUIRED (`schema/v1/schema.json:4712`). Result: empty object `{}`
  (`:2839`).
- `AuthMethod` (`:2702`) is a union: `AuthMethodTerminal` (requires `type:"terminal"`; `id`,`name` required;
  `description?`, `args?`, `env?`, `:2736`) and `AuthMethodAgent` (**no `type` field required** — default
  variant; `id`,`name` required, `:2783`). "When no `type` is present, the method is treated as `agent`"
  (`docs/protocol/v1/authentication.mdx:80-82`).
- Clients **MUST NOT** send `authenticate` for a `terminal` method (`authentication.mdx:153,187`).
- After a successful `authenticate`, authentication-gated requests must stop returning `auth_required`
  (`authentication.mdx:166`). The relevant error code is **`-32000` Authentication required**
  (`schema/v1/schema.json:3547-3553`). Note: the docs never state *normatively* that an agent must return
  `-32000`; the code exists in the schema and is referenced narratively.
- `logout` params `{}`, result `{}`; post-logout behaviour for active sessions is explicitly **undefined**
  (`authentication.mdx:218-226`) — untestable.
- `_meta`: every protocol type carries `_meta: {[k: string]: unknown}` (`extensibility.mdx:10`). In the schema
  it is always `type: ["object","null"]` with `x-deserialize-default-on-error: true` (e.g.
  `schema/v1/schema.json:5153-5158`) — i.e. a malformed `_meta` is tolerated, not fatal.
- `_`-prefixed methods: reserved for extensions; requests must be answered (with a result or `-32601`),
  unknown notifications should be ignored (`extensibility.mdx:43,65,80-91,109`). Custom capabilities are
  advertised under a capability object's `_meta` (`extensibility.mdx:111-132`).

### 7. Error codes

`ErrorCode` (`schema/v1/schema.json:3503-3569`): `-32700` parse, `-32600` invalid request, `-32601` method not
found, `-32602` invalid params, `-32603` internal, `-32800` request cancelled, `-32000` authentication
required, `-32002` resource not found, plus an open "other integer" variant. `Error` object requires `code`
and `message`; `data` optional (`:3480-3502`). `docs/protocol/v1/error.mdx:6` is literally
*"Documentation coming soon"* — there is **no normative error-mapping document for v1**.

---

## Testability notes

**Strongly assertable (good mandatory-tier tests):**

- `initialize` returns `protocolVersion` (integer) and, when the client sent `1`, returns exactly `1` for any
  agent that supports v1. Req #5.
- Sending `protocolVersion: 65535` must still yield a successful result with the agent's latest version — not
  an error. Req #5. (Negative control: an agent that errors here is non-conforming.)
- `session/new` with an absolute `cwd` and `mcpServers: []` returns a non-empty `sessionId`. Req #9.
- A trivial text-only `session/prompt` eventually resolves with one of the five `StopReason` strings. Req #24.
- Cancellation: send `session/prompt`, then `session/cancel`; the prompt **must** resolve with
  `stopReason: "cancelled"` (not an error, not `end_turn`). Req #25/#26. The mock client should answer any
  outstanding `session/request_permission` with `cancelled` so the agent is not blocked (Req step 2).
- Ordering after cancel: record the arrival order of `session/update` vs. the prompt response on the same
  connection; any update for that session arriving *after* the response violates Req #28. This is directly
  observable at the transport layer.
- `session/load` replay ordering: with `loadSession` advertised, every replay `session/update` must arrive
  before the `session/load` response. Req #15. Conversely `session/resume` must emit **zero**
  `session/update`s before its response. Req #16.
- Capability honesty (negative tests): advertise `clientCapabilities` with `fs` absent and `terminal` absent,
  then drive a prompt that would naturally want file access; any `fs/*` or `terminal/*` request from the
  agent is a violation of Req #29/#30. Same pattern for `elicitation/create` with no advertised mode (Req #32)
  and for `type:"boolean"` config options with no `session.configOptions.boolean` (Req #33).
- Capability-gated method availability: if `sessionCapabilities.list` is advertised, `session/list` must
  succeed and return a `sessions` array (empty allowed). If it is *not* advertised, the TCK simply must not
  call it — the spec says clients MUST NOT, and says nothing about what an agent returns, so "calls
  unadvertised method → expect -32601" is **not** a conformance assertion.
- Schema validation of every message the agent emits against `schema/v1/schema.json` (the `Agent` branch,
  `:5-42`) is the single highest-value structural test.
- Transport hygiene: any non-JSON line on stdout, or an embedded newline inside a message, violates Req #44
  and is trivially detected by the TCK's line reader.
- `_meta` round-trip: attach `_meta.traceparent` to a `session/prompt`; the agent must not reject it. Attaching
  an unknown root-level field to a spec type is what's forbidden (Req #41), and a TCK can check the *agent's*
  emitted objects for unknown root keys.
- `_foo/bar` extension request: the agent must respond, either with a result or `-32601` (Req #42).

**Weakly assertable / needs a cooperative agent-under-test:**

- Req #1's "`session/update`" obligation: an agent that answers a prompt with only a stop reason and no
  updates is arguably conforming (the docs make tool-call and message reporting SHOULD, not MUST —
  `tool-calls.mdx:14`, `agent-plan.mdx:12`). The TCK can only assert that *if* updates are sent they are
  well-formed and reference the right `sessionId`.
- Plan completeness (Req #36) is only checkable if the agent emits ≥2 `plan` updates.
- `terminal/release` (Req #31) requires the agent to actually use terminals; the TCK can flag leaked
  terminal IDs at session close as a SHOULD-level finding.
- MCP stdio support (Req #10): testable only by shipping a trivial stdio MCP server in the TCK and asserting
  the agent connects (observable if the server logs a handshake). This is a heavyweight test.

**Unobservable from the client side (do not write tests):**

- "Agent SHOULD stop model requests as soon as possible" (Req #27) — no timing contract is specified.
- Post-`logout` behaviour of active sessions — explicitly undefined (`authentication.mdx:220-222`).
- Whether the agent honours `cwd` as the root-set boundary (`session-setup.mdx:367`) — SHOULD, and the
  boundary is enforced inside the agent.
- Terminal-type authentication (Req #23) — the flow runs outside the ACP connection entirely
  (`authentication.mdx:169-188`); the TCK can only assert that the agent does not advertise a `terminal`
  method when `clientCapabilities.auth.terminal` is absent.
- Everything in `elicitation.mdx`'s URL-security section (`:110-132`) — human-UX requirements.

**Suggested tier split for the TCK:**

- *Mandatory*: Reqs 1, 2, 3, 5, 6, 7, 9, 24, 25, 26, 28, 40, 41, 42, 44, plus full schema validation of agent
  output.
- *Capability-conditional (run iff advertised)*: 8, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 33, 34.
- *Client-capability-driven negative tests (the TCK controls the advertisement)*: 29, 30, 32, 33.
- *Advisory/SHOULD (report, don't fail)*: 4, 11, 13, 27, 31, 35, 36, 37, 38, 39, 43, 46.
- *Not gated by any capability but not baseline either* — `session/set_mode` and
  `session/set_config_option`: run them only if `session/new` returned `modes` / `configOptions`
  respectively. This is the one place where the TCK must infer support from response content rather than from
  `initialize`.

---

## Discrepancies

1. **`current_mode_update` field name.** Docs use `"modeId"` (`docs/protocol/v1/session-modes.mdx:118`, and
   `docs/protocol/v1/schema.mdx:841` shows `modeId` required). The JSON Schema requires **`currentModeId`**
   (`schema/v1/schema.json:4133`, required at `:4148`), as does the generated `SessionUpdate` variant
   (`:3777-3792`). The `modeId` name is correct only for the `session/set_mode` *request*
   (`schema/v1/schema.json:5102-5129`, docs `session-modes.mdx:92,101`). **Schema wins** (it is the generated
   contract and the Rust type matches). The TCK should accept `currentModeId` and, at most, report `modeId` as
   a doc bug. This is a live docs bug worth filing upstream.
2. **Baseline prompt content types.** `docs/protocol/v1/initialization.mdx:204` says agents MUST support
   `ContentBlock::Text` **and** `ContentBlock::ResourceLink`. `docs/protocol/v1/content.mdx:31` says only
   "All Agents MUST support text content blocks". `resource_link` has no gating capability in
   `PromptCapabilities` (`schema/v1/schema.json:2480`), which corroborates initialization.mdx. Treat
   text + resource_link as the baseline; consider a `resource_link` prompt test *advisory* until upstream
   clarifies, since content.mdx could be read as narrowing it.
3. **`session/load` response shape.** `docs/protocol/v1/session-setup.mdx:184-186` shows
   `"result": null`. The schema defines `LoadSessionResponse` as an object with all-optional fields
   (`schema/v1/schema.json:3215-3246`). A TCK must accept both `null` and `{}` (and an object carrying
   `modes`/`configOptions`). Same pattern at `docs/protocol/v1/file-system.mdx:110` where
   `fs/write_text_file` is shown returning `null` while the schema says object.
4. **Capability name in prose.** `docs/protocol/v1/initialization.mdx:265` refers to the "top-level
   `load_session` capability"; the wire field is `loadSession` (`schema/v1/schema.json:2415`). Cosmetic.
5. **`docs/protocol/v1/overview.mdx` is incomplete.** Its "Optional Methods" list (`:78-102`) omits
   `session/list`, `session/delete`, `session/resume`, `session/close`, and `session/set_config_option`, all of
   which are in the stable v1 schema and have their own doc pages. Use the schema + `meta.json`, not
   overview.mdx, as the method inventory.
6. **`docs/protocol/v1/error.mdx` is a stub** ("Documentation coming soon", `:6`). There is no normative v1
   guidance on which error code an agent returns for an unknown `sessionId`, an unsupported content block, or
   a call to an unadvertised capability-gated method. `-32002` (Resource not found) and `-32602` (Invalid
   params) exist in the schema but are not bound to those situations by any normative text. **Do not write
   mandatory TCK tests asserting specific error codes for these cases.**
7. **No conflicts found** between the spec repo and the Rust reference SDK on anything checked. The SDK's
   "highest compatible version ≤ requested" negotiation
   (`[rust] src/agent-client-protocol/src/role/acp.rs:490-502`) is a faithful implementation of
   `initialization.mdx:96`, not a deviation.

---

## Open questions

1. **What error must an agent return for an unknown/stale `sessionId`?** Unspecified in v1 docs and schema
   (see Discrepancy 6). Would need a reference-implementation survey (`check-rust-sdk` / `check-python-sdk`)
   to establish a de-facto answer, and it would be at best SHOULD-tier for the TCK.
2. **Are `session/update` notifications permitted outside a prompt turn in v1?** The v2 announcement says v1
   "didn't *prohibit*" them but that it "was a common point of confusion"
   (`docs/announcements/acp-v2-draft.mdx:25`). No v1 normative statement either way. Affects whether the TCK
   may treat an out-of-turn update as a violation. Recommend: do not.
3. **Is an agent allowed to reject a prompt containing a content type it did not advertise, and how?** The
   obligation is placed on the client (`prompt-turn.mdx:92`); agent-side behaviour is undefined.
4. **`session/set_mode` / `session/set_config_option` discoverability.** Neither has a capability marker in v1.
   Is returning `modes`/`configOptions` from a session-creating method the intended and *only* signal?
   `initialization.mdx:264-267` hints modes will be unified later but does not settle it.
5. **Does `-32000` (auth required) have normative agent semantics in v1**, i.e. must an agent that advertises
   `authMethods` return `-32000` from `session/new` before `authenticate`? `authentication.mdx:166` implies it
   ("without receiving an `auth_required` error") but never states it as a requirement. This materially affects
   whether the TCK can test authentication at all; worth a separate research pass.
6. **RFD-only surfaces.** `docs/rfds/*.mdx` contains many proposals (e.g. `meta-propagation`,
   `request-cancellation`, `plan-operations`). Several have corresponding
   `docs/announcements/*-stabilized.mdx` pages and *are* in stable v1; the rest are proposals only. I used
   `schema/v1/schema.json` + `schema/v1/meta.json` as the stable/unstable boundary rather than the RFD list.
   If the orchestrator wants an RFD-by-RFD stability map, that is a separate question.
