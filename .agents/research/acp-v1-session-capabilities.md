# For each capability-gated or inferred-support agent method in ACP v1, what exactly must a TCK send, what must the agent return, and what orderings/side effects are observable and normatively required?

**Sources checked:**

- `agent-client-protocol` (spec, source of truth) @ `d89c8d3154c8708a77f31ae32105b4ca5f330b1d`, 2026-09-18 (`docs: correct empty response examples (#2176)`). `git pull --ff-only` succeeded (fast-forward from `6d08f41`, the revision used by `acp-v1-protocol-surface.md`; `schema/v1/schema.json` is **byte-identical** between the two revisions, so that report's schema line numbers remain valid).
- `acp-rust-sdk` (reference implementation, used as *evidence only*) @ `8bc6275a3d6b5accf102718d715017bfbb918c5c`, 2026-09-18 (`feat(acp): update schema dependency to 1.9.0 (#366)`). `git pull --ff-only` succeeded.
- `acp-python-sdk`: not consulted. `a2a-tck`: not consulted.

All `path:line` citations are relative to the **spec repo** unless prefixed `[rust]` (Rust SDK repo).

This report goes one level deeper than `.agents/research/acp-v1-protocol-surface.md` §3, §4 and its Requirements 8, 12, 14–20, 33–35. It does not re-derive the method inventory, version negotiation, stop reasons, `session/cancel` ordering, or the client-implemented method shapes — see that report.

**Confidence:** high for wire shapes, capability-detection rules, and the explicit MUST/SHOULD/MAY statements (all read directly from `schema/v1/schema.json` and `docs/protocol/v1/*.mdx`). Medium for the *derived* obligations (`session/close` implying a `cancelled` prompt response; what counts as "history" during `session/load` replay) — flagged inline. Low/none, and explicitly reported as "spec is silent", for unknown-session error codes, post-delete/post-close prompt behaviour, list ordering, and rejection of non-advertised content blocks.

---

## Answer

Nine of ACP v1's thirteen agent methods are gated: `session/load` by the top-level boolean `agentCapabilities.loadSession`; `session/list`, `session/delete`, `session/resume`, `session/close` and the `additionalDirectories` request field by **object markers** under `agentCapabilities.sessionCapabilities` (omitted or `null` = unsupported, `{}` = supported — `schema/v1/schema.json:2538-2597`); `session/set_mode` and `session/set_config_option` by nothing at all, their support being *inferred* from a non-null `modes` / `configOptions` in a `session/new`, `session/load` or `session/resume` response. The only ordering obligations that are normatively pinned and client-observable are: `session/load` MUST stream the entire conversation as `session/update` notifications and MUST respond only after the last one (`docs/protocol/v1/session-setup.mdx:134,178`); `session/resume` MUST NOT replay history before responding (`:243`); `session/close` MUST cancel ongoing work "as if `session/cancel` had been called" and then free resources (`:299`); `session/set_config_option` MUST return the **complete** option list (`docs/protocol/v1/session-config-options.mdx:255`, `schema/v1/schema.json:3420`); `session/list` MUST return an empty `sessions` array when nothing matches (`docs/protocol/v1/session-list.mdx:166`) and `session/delete` SHOULD succeed silently for an unknown id (`docs/protocol/v1/session-delete.mdx:86`). Everything else a TCK might want to check is undefined: there is **no** specified error code for an unknown `sessionId` on any method (`docs/protocol/v1/error.mdx` is a stub — "_Documentation coming soon_"), no defined agent-side rejection for a content block the agent did not advertise, no ordering guarantee for `session/list`, no requirement that a session created by `session/new` ever appears in `session/list`, and post-`delete`/post-`close` `session/prompt` behaviour is explicitly implementation-defined. MCP capabilities are observable only as *acceptance* of a config shape: the reference agent connects to MCP servers **lazily** at tool-use time, not at `session/new` ([rust] `src/agent-client-protocol-test/src/testy.rs:1460-1530`), so a stdio MCP fixture can only prove Requirement 10 through an agent-specific prompt command and is therefore not a portable conformance test.

---

## Requirements

Tier legend: **MUST** / **SHOULD** / **MAY** as written in the docs; **cap:X** = applies only when the agent advertises X; **inferred:X** = applies only when the agent volunteered X in a prior response; **derived** = follows by reference from another normative statement rather than being stated for this method; **silent** = the spec does not define it (listed so the TCK does not assert it).

| #  | Requirement | Tier | Citation |
|----|-------------|------|----------|
| C1 | `loadSession` is a top-level **boolean**; `false` or absent ⇒ unsupported, and clients MUST NOT call `session/load` | MUST (client) | `docs/protocol/v1/session-setup.mdx:104`; `schema/v1/schema.json:2419-2424` (`type: boolean`, `default: false`) |
| C2 | `sessionCapabilities.{list,delete,additionalDirectories,resume,close}` are **object markers**: omitted or `null` ⇒ unsupported, `{}` ⇒ supported | MUST (detection rule) | `schema/v1/schema.json:2538-2597`; `docs/protocol/v1/session-delete.mdx:52`; `docs/protocol/v1/initialization.mdx:249-262` |
| C3 | `promptCapabilities.{image,audio,embeddedContext}` and `mcpCapabilities.{http,sse}` are **booleans** defaulting to `false`; `false` or absent ⇒ unsupported | MUST (detection rule) | `schema/v1/schema.json:2484-2501, 2514-2525`; `docs/protocol/v1/session-setup.mdx:540-541`; `docs/protocol/v1/initialization.mdx:208-231` |
| C4 | Every capability omitted from `initialize` MUST be treated as UNSUPPORTED | MUST | `docs/protocol/v1/initialization.mdx:106` |
| L1 | `session/load` request MUST carry `sessionId`, `cwd`, `mcpServers` | MUST (schema) | `schema/v1/schema.json:4985`; `docs/protocol/v1/session-setup.mdx:108-112` |
| L2 | On `session/load` the agent MUST replay the entire conversation as `session/update` notifications | cap:`loadSession` + MUST | `docs/protocol/v1/session-setup.mdx:134` |
| L3 | The agent MUST respond to `session/load` only after **all** conversation entries have been streamed | cap:`loadSession` + MUST (ordering) | `docs/protocol/v1/session-setup.mdx:178` |
| L4 | `session/load` result is an **object**; all three fields (`modes`, `configOptions`, `_meta`) optional/nullable; the canonical empty result is `{}`, not `null` | MUST (schema) | `schema/v1/schema.json:3215-3249` (no `required` key); `docs/protocol/v1/session-setup.mdx:180-186` (changed from `result: null` to `result: {}` in `d89c8d3`) |
| L5 | Which `sessionUpdate` kinds constitute "history" is **not** enumerated | silent | `docs/protocol/v1/session-setup.mdx:134-178` shows only `user_message_chunk` and `agent_message_chunk` as *examples* |
| L6 | Behaviour for an unknown / never-created `sessionId` on `session/load` | silent (and explicitly implementation-defined for a *deleted* session) | `docs/protocol/v1/session-delete.mdx:88`; `docs/rfds/session-delete.mdx:76,124`; no statement anywhere for a never-existing id |
| R1 | `session/resume` request MUST carry `sessionId` and `cwd`; `mcpServers` is **optional** (unlike `load`) | MUST (schema) | `schema/v1/schema.json:5075` (`required: ["sessionId","cwd"]`) vs `:4985` |
| R2 | On `session/resume` the agent MUST NOT replay conversation history via `session/update` before responding | cap:`sessionCapabilities.resume` + MUST NOT | `docs/protocol/v1/session-setup.mdx:243` |
| R3 | `session/resume` restores context, reconnects to the requested MCP servers, returns when the session is ready | MUST (stated as behaviour) | `docs/protocol/v1/session-setup.mdx:243` |
| R4 | The `session/resume` response MAY include initial mode / model / config state | MAY | `docs/protocol/v1/session-setup.mdx:253`; `schema/v1/schema.json:3337-3371` |
| S1 | `session/list` params are **all optional**; an empty `params` object returns the first page | MUST (schema) + stated | `schema/v1/schema.json:4989-5010` (no `required`); `docs/protocol/v1/session-list.mdx:82` |
| S2 | `cwd` filter: must be absolute; only sessions with a matching `cwd` are returned | stated behaviour | `docs/protocol/v1/session-list.mdx:84-87`; `schema/v1/schema.json:4993-4996` |
| S3 | The agent MUST respond with `sessions` (required array) and optional `nextCursor` | MUST | `docs/protocol/v1/session-list.mdx:94`; `schema/v1/schema.json:3275` |
| S4 | Each `SessionInfo` MUST have `sessionId` and `cwd`; `additionalDirectories`, `title`, `updatedAt`, `_meta` optional | MUST (schema) | `schema/v1/schema.json:3321` |
| S5 | When no sessions match, the agent MUST return an **empty** `sessions` array (not `null`, not an error) | MUST | `docs/protocol/v1/session-list.mdx:166` |
| S6 | Clients MUST treat a missing `nextCursor` as end-of-results, and cursors as opaque | MUST (client) | `docs/protocol/v1/session-list.mdx:172-173` |
| S7 | Agents SHOULD return an error for an invalid cursor; SHOULD enforce reasonable page sizes internally | SHOULD | `docs/protocol/v1/session-list.mdx:174-175` |
| S8 | Ordering of `sessions`, page size, and whether a `session/new` session ever appears in `session/list` | silent | no ordering statement in `docs/protocol/v1/session-list.mdx` or `docs/rfds/session-list.mdx`; the RFD only mentions "default sorting" informally (`docs/rfds/session-list.mdx:77`) |
| D1 | `session/delete` request MUST carry `sessionId`; result is an empty object | MUST (schema) | `schema/v1/schema.json:5030`, `:3323-3336`; `docs/protocol/v1/session-delete.mdx:69-81` |
| D2 | Deleting an already-deleted or never-existing session SHOULD succeed silently | SHOULD | `docs/protocol/v1/session-delete.mdx:86`; `docs/rfds/session-delete.mdx:77` |
| D3 | Deleted sessions no longer appear in future `session/list` results | stated semantics (MUST-equivalent; it is the *only* behaviour ACP specifies) | `docs/protocol/v1/session-delete.mdx:85,87` |
| D4 | Soft vs hard delete, `session/load` on a deleted session, and deleting an **active** session | explicitly implementation-defined | `docs/protocol/v1/session-delete.mdx:87-89` |
| D5 | Effect of `session/delete` on a subsequent `session/prompt` for that id | silent (follows from D4) | as D4 |
| X1 | `session/close` request MUST carry `sessionId`; result is an empty object | MUST (schema) | `schema/v1/schema.json:5098`, `:3372-3385`; `docs/protocol/v1/session-setup.mdx:295-308` |
| X2 | The agent MUST cancel any ongoing work for the session as if `session/cancel` had been called, then free the session's resources | cap:`sessionCapabilities.close` + MUST | `docs/protocol/v1/session-setup.mdx:299`; `schema/v1/schema.json:5080` |
| X3 | Therefore an in-flight `session/prompt` MUST be answered with `stopReason: "cancelled"`, after all pending updates | **derived** MUST (X2 + cancel contract) | `docs/protocol/v1/session-setup.mdx:299` → `docs/protocol/v1/prompt-turn.mdx:332,339,343` |
| X4 | Agents MAY return an error if the session does not exist or is not currently active | MAY | `docs/protocol/v1/session-setup.mdx:311`; `docs/rfds/session-close.mdx:63` |
| X5 | Whether a closed session disappears from `session/list`, and behaviour of a later `session/prompt` on a closed id | silent | nothing in `docs/protocol/v1/session-setup.mdx` or `docs/rfds/session-close.mdx` |
| A1 | `additionalDirectories` is accepted on `session/new`, `session/load`, `session/resume`; clients MUST only send it when the capability is advertised | cap:`sessionCapabilities.additionalDirectories` + MUST (client) | `docs/protocol/v1/session-setup.mdx:315-318,344` |
| A2 | Each entry MUST be an absolute path | MUST | `docs/protocol/v1/session-setup.mdx:340`; `schema/v1/schema.json:4757-4765` |
| A3 | Omitting the field or sending `[]` activates **no** additional roots; stored roots are never implicitly restored | MUST (stated) | `docs/protocol/v1/session-setup.mdx:341-342`; `schema/v1/schema.json:4961-4969, 5050-5058` |
| A4 | `cwd` remains the primary working directory and base for relative paths; effective root set is `[cwd, ...additionalDirectories]`, which SHOULD bound tool file operations | MUST / SHOULD | `docs/protocol/v1/session-setup.mdx:339,360-367` |
| A5 | On load/resume the client must resend the full intended list; it may differ from any previous list as long as request `cwd` matches the session's `cwd` | MUST (client) | `docs/protocol/v1/session-setup.mdx:342` |
| A6 | Agents MUST validate the field, MUST reject (not silently reduce) invalid/unauthorized entries; `invalid_params` is RECOMMENDED for malformed values; empty strings MUST be rejected | MUST / RECOMMENDED — **completed RFD**, not the protocol page | `docs/rfds/additional-directories.mdx:176-178,256-267`; stabilized per `docs/announcements/additional-directories-stabilized.mdx:9` |
| A7 | Agents that also support `session/list` MAY report `SessionInfo.additionalDirectories`; omitted ≡ empty; clients MUST NOT merge it with prior values | MAY / MUST NOT (client) | `docs/protocol/v1/session-list.mdx:139-146`; `schema/v1/schema.json:3295-3303` |
| M1 | `session/set_mode` request MUST carry `sessionId` + `modeId`; result is an empty object | MUST (schema) | `schema/v1/schema.json:5129`, `:3386-3399`; `docs/protocol/v1/session-modes.mdx:97-104` |
| M2 | `modeId` must be one of the ids listed in `availableModes` | stated constraint on the **client** | `docs/protocol/v1/session-modes.mdx:101-104` |
| M3 | Mode may be changed at any time, idle or mid-generation | stated | `docs/protocol/v1/session-modes.mdx:79` |
| M4 | Agent-initiated mode change is reported via `session/update` with `sessionUpdate: "current_mode_update"` and required field **`currentModeId`** | MUST (schema) | `schema/v1/schema.json:4133,4148`; `agent-client-protocol-schema/src/v1/client.rs:453-455`. **Docs show `modeId` — that is a docs bug**: `docs/protocol/v1/session-modes.mdx:117-119` |
| M5 | Agent behaviour for an invalid/unknown `modeId` in `session/set_mode` | silent | nothing in `docs/protocol/v1/session-modes.mdx` or the schema |
| M6 | Session modes are deprecated in favour of config options and will be removed; agents MAY offer both | informational / SHOULD (transition) | `docs/protocol/v1/session-modes.mdx:6-11`; `docs/protocol/v1/session-config-options.mdx:8-13,330-339` |
| O1 | `session/set_config_option` request MUST carry `sessionId` + `configId` + `value`; `type: "boolean"` selects the boolean variant, absent/unknown `type` with a string payload ⇒ value-id variant | MUST (schema) | `schema/v1/schema.json:5160-5193`; `docs/protocol/v1/session-config-options.mdx:225-253` |
| O2 | The agent MUST respond with the **complete** list of all configuration options and their current values | MUST | `docs/protocol/v1/session-config-options.mdx:255,282-287`; `schema/v1/schema.json:3420` (`required: ["configOptions"]`) |
| O3 | Agents MUST always provide a default value for every configuration option | MUST | `docs/protocol/v1/session-config-options.mdx:196` |
| O4 | Agent-initiated change is reported via `session/update` with `sessionUpdate: "config_option_update"`, required field `configOptions`, also the **complete** state | MUST (schema) + stated | `schema/v1/schema.json:4154,4170`; `docs/protocol/v1/session-config-options.mdx:322` |
| O5 | Agents MUST NOT include `type: "boolean"` options unless the client advertised `session.configOptions.boolean: {}` | MUST NOT (client-cap gated) | `docs/protocol/v1/session-config-options.mdx:127-160`; `schema/v1/schema.json:4598-4633`; `docs/protocol/v1/initialization.mdx:169-178` |
| O6 | `category` is UX-only and MUST NOT be required for correctness; `configOptions` array order is the agent's preferred priority (clients SHOULD respect it) | MUST NOT / SHOULD | `docs/protocol/v1/session-config-options.mdx:164-169,186`; `schema/v1/schema.json:3058-3086` |
| O7 | Agent behaviour for an unknown `configId`, or a `value` not in the option's `options` array, or a type mismatch | silent | nothing in `docs/protocol/v1/session-config-options.mdx` |
| P1 | Agents MUST accept `text` and `resource_link` content blocks in `session/prompt` | MUST | `docs/protocol/v1/initialization.mdx:204`; `schema/v1/schema.json:5210` |
| P2 | `image` / `audio` / `resource` blocks may be sent only when the matching prompt capability is advertised; **clients** MUST restrict content accordingly | cap + MUST (client) | `docs/protocol/v1/prompt-turn.mdx:92`; `docs/protocol/v1/content.mdx:54-56,123-125`; `docs/protocol/v1/initialization.mdx:206-218` |
| P3 | What an agent must do when a client violates P2 | silent — no error code, no rejection shape defined | `docs/protocol/v1/prompt-turn.mdx:92` places the whole burden on the client; `docs/protocol/v1/error.mdx:6` is a stub |
| K1 | All agents MUST support the MCP **stdio** transport | MUST | `docs/protocol/v1/session-setup.mdx:373,381` |
| K2 | New agents SHOULD support the MCP HTTP transport | SHOULD | `docs/protocol/v1/session-setup.mdx:375` |
| K3 | HTTP / SSE server configs may be sent only when `mcpCapabilities.http` / `.sse` is `true` | cap + MUST (client verification) | `docs/protocol/v1/session-setup.mdx:426,475,522,540-541` |
| K4 | Agents SHOULD connect to all MCP servers specified by the client | SHOULD | `docs/protocol/v1/session-setup.mdx:543` |
| K5 | *When* the agent must connect (eagerly at `session/new`, or lazily at first tool use) | silent | the `session/new` sequence diagram notes "Connect to MCP servers" (`docs/protocol/v1/session-setup.mdx:22,27,36`) but no MUST/SHOULD attaches a time to it |

---

## Details

### 0. Capability detection: the exact predicate per gate

Two distinct encodings coexist in v1, and the TCK must not use one rule for both.

**Boolean gates.** `loadSession`, `promptCapabilities.image|audio|embeddedContext`, `mcpCapabilities.http|sse`. Schema type is `boolean` with `"default": false` (`schema/v1/schema.json:2419-2424, 2484-2501, 2514-2525`). Predicate:

```
supported(x) := (x is present) AND (x === true)
```

`false`, `null`, and absence are all "unsupported" (`docs/protocol/v1/session-setup.mdx:104,540-541`). Note the containers themselves are optional: `promptCapabilities` and `mcpCapabilities` are `allOf`-wrapped `$ref`s with object defaults (`:2425-2451`), so a missing `promptCapabilities` means "all three false".

**Object-marker gates.** `sessionCapabilities.{list,delete,additionalDirectories,resume,close}` and `auth.logout`. Schema type is `anyOf [ <MarkerType>, null ]` and each marker type is an object whose only declared property is `_meta` (`schema/v1/schema.json:2538-2597, 2606-2665, 2670-2681`). Predicate:

```
supported(x) := (x is present) AND (x !== null)
```

i.e. presence-and-non-null. `{}` is the canonical "supported" value; `{"_meta": {...}}` is equally supported. The doc text states this explicitly per capability: "Omitted or `null` both mean the Agent does not advertise support. Supplying `{}` means the Agent supports …" (`docs/protocol/v1/session-delete.mdx:52`, `docs/protocol/v1/initialization.mdx:249-262`, and the same wording in each schema description). A TCK **must not** treat `true` as advertising an object-marker capability, and must not treat `{}` as advertising a boolean one.

Container nesting matters: `agentCapabilities.sessionCapabilities` is itself optional with `"default": {}` (`:2452-2461`), so absence of the container means all five markers are unsupported. `AgentCapabilities` has **no** `required` key (`:2415-2479`), and `InitializeResponse` requires only `protocolVersion` (see `acp-v1-protocol-surface.md` Req 3), so an agent advertising nothing at all is conformant.

Every gate carries `x-deserialize-default-on-error: true`, which is a *deserializer* hint for the reference SDKs (malformed value ⇒ use default) and not a protocol requirement. The TCK should not assert anything about malformed capability values; it also must not assume a peer will reject them.

**Inferred gates (no capability at all).** `session/set_mode` and `session/set_config_option` have **no** capability marker anywhere in `AgentCapabilities`. Support is inferred from the session-setup response: a non-null `modes` (`SessionModeState`) implies `session/set_mode`; a non-null, non-empty `configOptions` implies `session/set_config_option`. `modes` and `configOptions` are optional/nullable on all three of `NewSessionResponse` (`:2879-2899`), `LoadSessionResponse` (`:3219-3239`) and `ResumeSessionResponse` (`:3341-3361`). This inference is the TCK's own rule, not a spec statement — the spec only says the agent "**MAY** return a list of modes" (`docs/protocol/v1/session-modes.mdx:17`) / "**MAY** return a list of configuration options" (`docs/protocol/v1/session-config-options.mdx:17`).

### 1. `session/load` — cap `agentCapabilities.loadSession` (boolean)

**Request** `LoadSessionRequest`, `schema/v1/schema.json:4944-4988`:

| field | req | type | notes |
|---|---|---|---|
| `sessionId` | REQUIRED | `SessionId` (string, `:297`) | `:4970-4977` |
| `cwd` | REQUIRED | string, MUST be absolute | `:4957-4960`; `docs/protocol/v1/session-setup.mdx:362` |
| `mcpServers` | REQUIRED | `McpServer[]` (may be `[]`) | `:4948-4956` — required here, unlike `session/resume` |
| `additionalDirectories` | optional | `string[]`, absolute paths | `:4961-4969`; only when cap A1 |
| `_meta` | optional | object\|null | `:4978-4983` |

`required: ["mcpServers","cwd","sessionId"]` (`:4985`).

**Replay obligation.** Two separate sentences:

1. "The Agent **MUST** replay the entire conversation to the Client in the form of `session/update` notifications (like `session/prompt`)." — `docs/protocol/v1/session-setup.mdx:134`.
2. "When **all** the conversation entries have been streamed to the Client, the Agent **MUST** respond to the original `session/load` request." — `:178`.

Together these pin one client-observable ordering: **every** `session/update` that belongs to the replay arrives *before* the JSON-RPC response to the `session/load` request id. The sequence diagram (`:25-32`) shows the same.

**Which update kinds count as "history"? Not specified.** The docs give two worked examples — `user_message_chunk` (`:145`) and `agent_message_chunk` (`:165`) — and add that "If the Agent provides message IDs during replay, each `messageId` is an opaque, unique identifier for the replayed message" (`:176`), which makes `messageId` optional even in replay (`ContentChunk.messageId` is optional, `schema/v1/schema.json:3841-3873`). There is:

- no enumeration of replayable `sessionUpdate` variants (all eleven are structurally legal, `schema/v1/schema.json:3653-3836`);
- no statement about whether `tool_call` / `tool_call_update` / `plan` history must be replayed;
- no chunking, granularity, or fidelity rule (an agent may compact or summarize, and nothing forbids it);
- no requirement that the replay be byte-identical to the original live stream.

By contrast **v2** (excluded from scope) defines this precisely — "the Agent **MUST** replay all retained conversation history … before responding", messages only, `messageId` **required** during replay, retention explicitly not guaranteed (`docs/protocol/v2/session-setup.mdx:144-152,198-221`). That v2 text is the clearest evidence that v1 deliberately leaves the content of replay open, and the TCK must not import the v2 rules into a v1 test.

**Response** `LoadSessionResponse`, `:3215-3249`: an **object** with **no** required fields — `modes?: SessionModeState|null`, `configOptions?: SessionConfigOption[]|null`, `_meta?`. `null` as the whole result is **not** schema-valid: `AgentResponse.Result` requires `result` and constrains it to the response-type union, none of whose members admit `null` (`:2188-2311`). The docs previously showed `"result": null` and were **corrected to `"result": {}` in the checked revision** (`git show d89c8d3 -- docs/protocol/v1/session-setup.mdx`; now `docs/protocol/v1/session-setup.mdx:180-186`). TCK stance: accept `{}` (and any object with the optional fields); treat `null` as non-conforming *per the current schema and docs*, but log it as a known historical-doc artifact rather than a hard failure if the project wants leniency.

**Unknown `sessionId`.** Not specified. The only adjacent statements are "Behavior for `session/load` on a deleted session is implementation-defined" (`docs/protocol/v1/session-delete.mdx:88`, and the rationale at `docs/rfds/session-delete.mdx:76,124`: "return the session anyway, return an error, or any other behavior. The protocol does not prescribe which"). For a *never-created* id there is no statement at all, and `docs/protocol/v1/error.mdx:6` is a stub, so no error code (not even `-32602` or `-32002`, `schema/v1/schema.json:3528-3561`) can be asserted. Reference evidence: the Rust `testy` agent **upserts** on load — an unknown id silently becomes a new session and returns success ([rust] `src/agent-client-protocol-test/src/testy.rs:274-290,1887-1899`). That is one legal implementation among many.

### 2. `session/resume` — cap `sessionCapabilities.resume` (object marker)

**Request** `ResumeSessionRequest`, `:5034-5078`: `sessionId` REQUIRED, `cwd` REQUIRED (absolute), `mcpServers` **optional**, `additionalDirectories` optional, `_meta` optional; `required: ["sessionId","cwd"]` (`:5075`). The optionality of `mcpServers` is the **only structural difference** from `session/load`.

**No-replay obligation.** "Unlike `session/load`, the Agent **MUST NOT** replay the conversation history via `session/update` notifications before responding. Instead, it restores the session context, reconnects to the requested MCP servers, and returns once the session is ready to continue." (`docs/protocol/v1/session-setup.mdx:243`).

Precisely what is forbidden: *conversation-history* `session/update` notifications sent **before** the response. The prohibition is scoped to history and to the pre-response window. It does **not** forbid a `current_mode_update`, `config_option_update`, or `session_info_update` before the response (arguably these are not "conversation history"), and it does not forbid history updates *after* the response. A TCK assertion must therefore be narrow: no `user_message_chunk` / `agent_message_chunk` / `agent_thought_chunk` for that `sessionId` between the request and its response. Reference evidence that the client side tolerates non-history updates in the resume window: [rust] `src/agent-client-protocol/tests/session_restore.rs:170-232` drives a `session/resume` whose response batch includes a `session/update` ("resume update") and the client accepts it.

**Response** `ResumeSessionResponse`, `:3337-3371`: same shape as `LoadSessionResponse` — object, no required fields, `modes?`/`configOptions?`/`_meta?`. The docs add "The response **MAY** also include initial mode, model, or session configuration state when those features are supported by the Agent" (`:253`). Canonical empty result `{}` (`:245-251`).

**Difference from `load`, summarized for the TCK:** (a) different capability encoding — boolean vs object marker; (b) `mcpServers` required vs optional; (c) replay MUST vs MUST NOT; (d) identical response shape. Design intent (RFD, *proposal-tier*): resume exists so agents that cannot reconstruct history can still reconnect, and so a proxy can synthesize `load` from `resume` (`docs/rfds/session-resume.mdx:40-64`).

### 3. `session/list` — cap `sessionCapabilities.list` (object marker)

**Request** `ListSessionsRequest`, `:4989-5010`: **no required fields**. `cwd?: string|null` (absolute; filters to exact matches), `cursor?: string|null` (opaque), `_meta?`. "All parameters are optional. A request with an empty `params` object returns the first page of sessions." (`docs/protocol/v1/session-list.mdx:82`).

Interop caution the TCK should heed without asserting: the JSON-RPC envelope permits `params` to be `null`/absent (`schema/v1/schema.json:4295-4424`, `anyOf [ <union>, null ]`), but the Rust SDK maps a missing `params` to `Value::Null` ([rust] `src/agent-client-protocol/src/jsonrpc.rs:422-423`) and then deserializes it into the typed struct, which fails for a struct type. **Send `"params": {}`**, and do not assert that omitted params is accepted — the spec does not say either way.

**Response** `ListSessionsResponse`, `:3250-3278`: `sessions: SessionInfo[]` **REQUIRED** (`:3275`); `nextCursor?: string|null` (`:3263-3267`); `_meta?`.

`SessionInfo`, `:3279-3322`:

| field | req | type | citation |
|---|---|---|---|
| `sessionId` | REQUIRED | `SessionId` | `:3283-3290`, `:3321` |
| `cwd` | REQUIRED | string, always absolute | `:3291-3294`; `docs/protocol/v1/session-list.mdx:136-138` |
| `additionalDirectories` | optional | `string[]` (absolute); complete ordered list; omitted ≡ empty | `:3295-3303`; `docs/protocol/v1/session-list.mdx:139-146` |
| `title` | optional | string\|null; may be auto-generated | `:3304-3308` |
| `updatedAt` | optional | string\|null, ISO 8601 | `:3309-3313` |
| `_meta` | optional | object\|null | `:3314-3319` |

**Pagination rules** (`docs/protocol/v1/session-list.mdx:168-175`): cursor-based; clients MUST treat missing `nextCursor` as end-of-results; clients MUST treat cursors as opaque (do not parse, modify, or persist); agents SHOULD error on an invalid cursor; agents SHOULD enforce page sizes internally. The RFD adds "The cursor MUST be a string; never send a raw JSON object as the cursor" (`docs/rfds/session-list.mdx:286`) — consistent with the schema's `string|null`.

**Empty result:** MUST be `"sessions": []` (`:166`). Not `null`, not omitted, not an error.

**Ordering: no guarantee.** Nothing in `docs/protocol/v1/session-list.mdx` or the schema constrains order; the RFD mentions "default sorting" only in prose about a request with no filters (`docs/rfds/session-list.mdx:77`), and its revision history records that `sortBy`/`sortOrder` were **removed** (`:326`). Reference evidence: `testy` sorts by `sessionId` string ([rust] `src/agent-client-protocol-test/src/testy.rs:493`). A TCK MUST NOT assert recency ordering, stability across pages, or absence of duplicates across pages.

**Also unspecified:** whether a session returned by `session/new` must appear in `session/list` at all. `session/list` is described as discovery of "sessions known to an Agent" (`:6`) and is "a discovery mechanism only — it does **not** restore or modify sessions" (`:221`), but no MUST connects creation to listability. This is a significant gap: the only way a TCK can populate the list deterministically is via `session/new`, so the natural assertion ("create then list → the new id is present") is **advisory, not mandatory**. `testy` does include created sessions and excludes closed ones ([rust] `testy.rs:479-494`).

### 4. `session/delete` — cap `sessionCapabilities.delete` (object marker)

**Request** `DeleteSessionRequest`, `:5011-5033`: `sessionId` REQUIRED (`:5030`), `_meta?`.
**Response** `DeleteSessionResponse`, `:3323-3336`: object, no required fields; canonical `{}` (`docs/protocol/v1/session-delete.mdx:73-81`).

**Unknown session — confirmed, but it is SHOULD, not MUST.** "Deleting an already-deleted session, or a session that never existed, **SHOULD** succeed silently." (`docs/protocol/v1/session-delete.mdx:86`; identical in `docs/rfds/session-delete.mdx:77`). Prior research Requirement 19 is therefore accurate in substance; the tier is **SHOULD**, so a TCK failure here should be a warning, not a mandatory failure. Reference evidence: `testy` returns success for an unknown id ([rust] `testy.rs:504-506`).

**Observable semantics — exactly one:** "Deleted sessions no longer appear in future `session/list` results." (`:85`). This is the *only* behaviour ACP specifies (`:87`: "ACP only specifies the user-facing session-list behavior"). It is conditional on `sessionCapabilities.list` also being advertised, and on the session having been listable in the first place (see §3).

**Effect on a subsequent `session/prompt` for that id: not specified.** The two adjacent statements are "Behavior for `session/load` on a deleted session is implementation-defined" (`:88`) and "Behavior for deleting an active session is implementation-defined" (`:89`). Nothing covers `session/prompt`. Reference evidence spans the space: `testy` marks the session cancelled+closed and removes it when no prompt is active ([rust] `testy.rs:497-518`), after which `session/prompt` fails with `invalid_params` ([rust] `testy.rs:303-311`) — legal, but not required, and not assertable.

### 5. `session/close` — cap `sessionCapabilities.close` (object marker)

**Request** `CloseSessionRequest`, `:5079-5101`: `sessionId` REQUIRED (`:5098`), `_meta?`. Docs param table at `docs/protocol/v1/session-setup.mdx:295-297`.
**Response** `CloseSessionResponse`, `:3372-3385`: object, no required fields; "On success, the Agent responds with an empty result object" `{}` (`:301-308`).

**"Cancel ongoing work then free."** "The Agent **MUST** cancel any ongoing work for that session as if [`session/cancel`](…#cancellation) had been called, then free the resources associated with the session." (`docs/protocol/v1/session-setup.mdx:299`; same in the schema description at `:5080`, and in the RFD at `docs/rfds/session-close.mdx:32-34`).

**Is `stopReason: "cancelled"` required for an in-flight prompt? Derived yes, medium confidence.** `session/close` incorporates the cancellation contract by reference, and that contract says: after all ongoing operations are aborted and pending updates sent, the agent **MUST** respond to the original `session/prompt` with the `cancelled` stop reason (`docs/protocol/v1/prompt-turn.mdx:332`), MUST NOT surface an abort as a JSON-RPC error instead (`:339`), and MAY emit further `session/update`s but MUST do so before the prompt response (`:343`). No text says "close" explicitly, so this is inference from "as if `session/cancel` had been called" — strong inference, but inference. Reference evidence supports it: `testy`'s close handler sets `cancelled` and `closed` ([rust] `testy.rs:525-532`) and its `finish_prompt` then converts the in-flight prompt's stop reason to `Cancelled` ([rust] `testy.rs:316-335`). Recommended TCK tier: **capability-conditional**, with the failure message stating that the obligation is derived.

Ordering the TCK can observe when a prompt is in flight: `session/close` response and the `session/prompt` response are two independent JSON-RPC responses, and the spec does **not** order them relative to each other. Only the `updates-before-prompt-response` ordering is pinned. Do not assert that the close response arrives after the prompt response, or vice versa.

**Unknown id — confirmed MAY.** "Agents MAY return an error if the session does not exist or is not currently active." (`docs/protocol/v1/session-setup.mdx:311`; RFD `docs/rfds/session-close.mdx:63` phrases it as "might"). Both success and error are conforming; the error code is unconstrained. `testy` returns success ([rust] `testy.rs:527-528`). This is **informational only** for the TCK.

**Also unspecified:** whether a closed session leaves `session/list`, and what a later `session/prompt` on a closed id does.

### 6. `additionalDirectories` — cap `sessionCapabilities.additionalDirectories` (object marker)

**Where it appears:** as an optional `string[]` request field on `session/new` (`schema/v1/schema.json:4757-4765`), `session/load` (`:4961-4969`), `session/resume` (`:5050-5058`); and as an optional response field on `SessionInfo` in `session/list` (`:3295-3303`). "Supported stable lifecycle requests include `session/new`, `session/load`, and `session/resume`." (`docs/protocol/v1/session-setup.mdx:317-318`).

**Rules** (`docs/protocol/v1/session-setup.mdx:337-344`, `:358-367`):
- `cwd` remains the primary working directory and the base for relative paths (`:339,364`).
- Each entry **MUST** be an absolute path (`:340`; general rule also at `docs/protocol/v1/overview.mdx:214` and repo `AGENTS.md:1`).
- Omitting the field or sending `[]` activates **no** additional roots (`:341`).
- On load/resume the client must resend the full intended list; it may differ from any previous or reported list as long as request `cwd` matches the session's `cwd`; omission does **not** implicitly restore stored roots (`:342`).
- Clients **MUST** only send the field when the capability is advertised (`:344`).
- Effective root set is `[cwd, ...additionalDirectories]` and **SHOULD** bound tool file operations (`:367`).

**Observable agent behaviour: essentially none, from the client side alone.** The only unconditional observable is *acceptance*: a conforming agent with the capability must not reject a well-formed request carrying absolute additional directories. The root-set boundary is a SHOULD about the agent's own tool behaviour (`:367`) and is only visible if the agent happens to exercise `fs/*` or `terminal/*` against a path the TCK controls — which requires agent-specific prompting and is therefore not portable. If the agent also advertises `sessionCapabilities.list`, `SessionInfo.additionalDirectories` gives a weak echo channel, but reporting it is **MAY** (`docs/protocol/v1/session-list.mdx:139-146`; `docs/rfds/additional-directories.mdx:114`) and clients MUST NOT assume it is returned (`docs/rfds/additional-directories.mdx:224`).

**Rejection rules live in the completed RFD, not the protocol page.** `docs/rfds/additional-directories.mdx` (Completed / stabilized per `docs/announcements/additional-directories-stabilized.mdx:9`) requires: array of strings when present (`:176`), each entry an absolute path under the same platform rules as `cwd` (`:177`), empty strings MUST be rejected (`:178`), the agent MUST validate before creating/loading/resuming (`:256`), MUST reject rather than silently drop unsupported/unauthorized entries (`:233,267`), with `invalid_params` as the RECOMMENDED class for malformed values (`:265`), and MUST NOT implicitly reactivate stored roots not supplied on the request (`:224`). Per my role's source ordering, RFD text is design intent; here it is a *completed* RFD whose summary was folded into `session-setup.mdx`, so I report both positions. The safe TCK line: assert only what `session-setup.mdx` states; treat "relative path ⇒ error" as **advisory**, since the RFD recommends rather than mandates a code, and `error.mdx` defines nothing.

### 7. `session/set_mode` and `session/set_config_option` — inferred support

#### `session/set_mode`

Request `SetSessionModeRequest`, `:5102-5132`: `sessionId` REQUIRED, `modeId` REQUIRED (`SessionModeId` = string, `:2941-2944`), `_meta?`; `required: ["sessionId","modeId"]` (`:5129`). Response `SetSessionModeResponse`, `:3386-3399`: object, no required fields ⇒ `{}`.

`modes` in the session-setup response is `SessionModeState` (`:2911-2940`): `currentModeId` REQUIRED, `availableModes: SessionMode[]` REQUIRED (`:2939`); each `SessionMode` (`:2945-2974`) requires `id` and `name`, with `description?` nullable. Docs mirror at `docs/protocol/v1/session-modes.mdx:49-75`.

Notification: `sessionUpdate: "current_mode_update"` (`schema/v1/schema.json:3770-3783`), payload `CurrentModeUpdate` (`:4129-4149`) with **one required field, `currentModeId`**. **Docs bug confirmed:** `docs/protocol/v1/session-modes.mdx:117-119` shows `"modeId": "code"`. The Rust model field is `current_mode_id` with the type's camelCase rename (`agent-client-protocol-schema/src/v1/client.rs:453-455`), so the wire name is `currentModeId`. A TCK MUST validate against the schema name and MUST NOT accept `modeId`; this belongs in the Discrepancies register and is worth an upstream issue.

The docs also state the mode may be changed at any point, idle or mid-generation (`:79`), and describe an agent-driven switch-mode tool flow (`:124-170`) — narrative, no additional obligation.

**Invalid `modeId`: not specified.** `:101-104` constrains the *client* ("Must be one of the modes listed in `availableModes`"); nothing says what the agent does otherwise. Reference evidence: `testy` returns `invalid_params` for an unsupported mode and for an unknown/closed session ([rust] `testy.rs:543-569`). Not assertable.

There is **no** normative requirement that `session/set_mode` be followed by a `current_mode_update` notification — the notification is described as the mechanism for *agent-initiated* changes ("The Agent can also change its own mode and let the Client know", `:106-108`). `testy` sends none after a client-driven `set_mode` ([rust] `testy.rs:555-569`). Do not assert an echo notification.

#### `session/set_config_option`

Request `SetSessionConfigOptionRequest`, `:5133-5196`: `sessionId` REQUIRED, `configId` REQUIRED, plus an `anyOf` on the value (`:5161-5193`):

- boolean variant: `{"type": "boolean", "value": <bool>}` — both required (`:5175`);
- value-id variant: `{"value": "<SessionConfigValueId>"}` — `value` required, `type` absent. "This is the default when `type` is absent on the wire. Unknown `type` values with string payloads also gracefully deserialize into this variant." (`:5179`).

Docs mirror at `docs/protocol/v1/session-config-options.mdx:225-253`.

Response `SetSessionConfigOptionResponse`, `:3400-3423`: `configOptions: SessionConfigOption[]` **REQUIRED** (`:3420`). The "complete list" rule is stated twice: "The Agent **MUST** respond with the complete list of all configuration options and their current values" (`docs/protocol/v1/session-config-options.mdx:255`) and "The response always contains the **complete** configuration state. This allows Agents to reflect dependent changes." (`:282-287`). This is the single most testable capability-conditional assertion in this area: after setting one option, the response must contain **every** option id the agent previously advertised (set equality on ids), and the changed option's `currentValue` must equal the value sent.

`SessionConfigOption` (`:2975-3053`): base requires `id` and `name` (`:3015`), with optional `description` (nullable), `category` (nullable), `_meta`; then a `oneOf` discriminated on `type` (`:3016-3052`):

- `type: "select"` ⇒ `SessionConfigSelect` (`:3181-3203`): `currentValue: SessionConfigValueId` REQUIRED **and** `options: SessionConfigSelectOptions` REQUIRED (`:3202`). `SessionConfigSelectOptions` (`:3092-3111`) is either a flat `SessionConfigSelectOption[]` (each requires `value`, `name`; `:3141`) or a grouped `SessionConfigSelectGroup[]` (each requires `group`, `name`, `options`; `:3175`). **Note:** the grouped form is in the schema but *not* documented in `session-config-options.mdx` — a docs gap; the TCK must accept both shapes.
- `type: "boolean"` ⇒ `SessionConfigBoolean` (`:3204-3214`): `currentValue: boolean` REQUIRED (`:3213`).

`category` is an open string enum: `mode`, `model`, `model_config`, `thought_level`, or any other string (`:3058-3086`); UX-only and MUST NOT be required for correctness (`docs/protocol/v1/session-config-options.mdx:164-169`); `_`-prefixed names are free for custom use (`:171`).

Notification: `sessionUpdate: "config_option_update"` (`schema/v1/schema.json:3784-3798`), payload `ConfigOptionUpdate` (`:4150-4171`) with required `configOptions` — field name matches the docs (`docs/protocol/v1/session-config-options.mdx:300-301`), and it too "contains the complete configuration state" (`:322`). No docs bug here.

**Default-value rule.** "Agents **MUST** always provide a default value for every configuration option." (`:196`), so that the agent operates correctly if the client ignores options, does not display them, or does not recognize a type (`:196-202`). Observable form: every `SessionConfigOption` the agent emits carries a `currentValue` — which the schema already makes required in both variants. Practically, the TCK tests this as "`currentValue` present and type-correct on every option in every payload"; the deeper claim (an internal default exists even when the client never sets anything) is not separately observable.

**Boolean gating is client-controlled and therefore deterministic for the TCK.** Agents MUST NOT include `type: "boolean"` options unless the client advertised `clientCapabilities.session.configOptions.boolean: {}` (`docs/protocol/v1/session-config-options.mdx:158-160`; schema `:4574-4633`; detection rule "Omitted or `null` at any level means the Client does not advertise support", `docs/protocol/v1/initialization.mdx:169-178`). The TCK can run two sessions — one advertising the marker, one not — and assert no boolean-typed option appears in the non-advertising run. This is a genuine **MUST NOT** with full client-side control.

**Invalid `configId` / value / type mismatch: not specified.** `:233-237` constrains the *client*'s value ("must be one of the values listed in the option's `options` array"); no agent-side obligation or error code. Reference evidence: `testy` returns `invalid_params` for unknown config id, unsupported value, unknown session, and closed session ([rust] `testy.rs:572-612`). Not assertable.

### 8. Prompt capabilities `promptCapabilities.{image,audio,embeddedContext}`

Exact blocks to send when advertised (`ContentBlock` is tagged by `type`, `schema/v1/schema.json:601-688`, discriminator at `:685-687`):

| cap | `type` | `$def` | required fields | minimal payload |
|---|---|---|---|---|
| `image` | `image` | `ImageContent` `:765-802` | `data`, `mimeType` (`:801`); `uri?` | `{"type":"image","mimeType":"image/png","data":"<base64>"}` (docs example `docs/protocol/v1/content.mdx:46-52`) |
| `audio` | `audio` | `AudioContent` `:803-835` | `data`, `mimeType` (`:834`) | `{"type":"audio","mimeType":"audio/wav","data":"<base64>"}` (`docs/protocol/v1/content.mdx:81-89`) |
| `embeddedContext` | `resource` | `EmbeddedResource` `:965-997` | `resource` (`:996`) | text form: `{"type":"resource","resource":{"uri":"file:///abs/path","mimeType":"text/plain","text":"..."}}`; blob form: `…{"uri":…,"blob":"<base64>"}` |

`EmbeddedResourceResource` (`:890-912`) is `TextResourceContents` (requires `text`, `uri`; `:937`) or `BlobResourceContents` (requires `blob`, `uri`; `:963`); `mimeType` optional in both. Docs: `docs/protocol/v1/content.mdx:104-160`. Baseline blocks the TCK must always be able to send: `text` (requires `text`, `:763`) and `resource_link` (requires `name`, `uri`, `:888`). All five accept optional `annotations` (`Annotations` `:689-720`) and `_meta`. Capability names do not match type names: **`embeddedContext` gates `type: "resource"`**.

**What a rejection looks like when not advertised: undefined.** The spec places the entire burden on the client — "Clients **MUST** restrict types of content according to the Prompt Capabilities" (`docs/protocol/v1/prompt-turn.mdx:92`), and each content section says the block "Requires the `<cap>` prompt capability when included in prompts" (`docs/protocol/v1/content.mdx:54-56,86-89,123-125`). There is **no** statement of what an agent must do on violation: no error code, no `stopReason`, no "MUST reject", no "MAY ignore". `docs/protocol/v1/error.mdx:6` is a stub. Consequences for the TCK:

- Sending a non-advertised block is a **client-side protocol violation** and the TCK must not do it in a mandatory test. If the project wants a negative probe, it must be tiered **informational** and must accept *any* outcome (error of any code, silent acceptance, ignored block, or a stop reason) without failing the agent.
- When a capability *is* advertised, the assertable claim is only that the agent accepts the prompt and completes the turn with a valid `stopReason` — not that it "understood" the content.

### 9. MCP capabilities `mcpCapabilities.{http,sse}` and the stdio requirement (Req 10)

`McpServer` is an `anyOf` with the stdio variant as the **untagged default** (`schema/v1/schema.json:4786-4831`):

| transport | discriminator | `$def` | required fields |
|---|---|---|---|
| stdio | **none** (default variant, `:4821-4829`) | `McpServerStdio` `:4909-4943` | `name`, `command` (absolute path to executable), `args`, `env` — **all four required** (`:4942`) |
| http | `"type": "http"` (`:4793-4798`) | `McpServerHttp` `:4853-4880` | `name`, `url`, `headers` — all required (`:4879`) |
| sse | `"type": "sse"` (`:4809-4814`) | `McpServerSse` `:4881-4908` | `name`, `url`, `headers` — all required (`:4907`) |

`EnvVariable` (`:1213-1233`) and `HttpHeader` (`:4832-4852`) each require `name` + `value`. Docs param tables: stdio `docs/protocol/v1/session-setup.mdx:383-422`, http `:428-471`, sse `:479-518` (SSE is deprecated by MCP itself, `:477`).

**Is anything observable from the client side without running an MCP server? Almost nothing.** The capability gates the *acceptance of a config shape*, and the only spec statements are: all agents MUST support stdio (`:373,381`), new agents SHOULD support HTTP (`:375`), clients MUST verify capabilities before using HTTP/SSE (`:522`), and agents SHOULD connect to all MCP servers specified by the client (`:543`). Therefore:

- Sending an `mcpServers` entry whose transport is advertised and asserting the session-setup request still succeeds is the *only* portable assertion. Even that is weak: nothing forbids an agent from failing `session/new` because a *particular* server is unreachable.
- Sending a non-advertised HTTP/SSE entry is a client-side violation (`:522`) with no defined agent response — informational at best.
- **When** connection happens is unspecified (K5). The sequence diagram's "Connect to MCP servers" note (`:22,27,36`) is illustrative, not normative, and carries no MUST/SHOULD.

**Feasibility of a minimal stdio MCP server fixture for Req 10 — assessment: not worth it as a mandatory conformance test.**

- *What the agent observably does:* the reference agent connects **lazily**. `testy` spawns the stdio MCP child process only inside `with_mcp_client`, which is reached solely from the `call_tool` / `list_tools` prompt commands ([rust] `src/agent-client-protocol-test/src/testy.rs:1460-1530`, dispatched at `:638-657`); `session/new` merely stores the `Vec<McpServer>` ([rust] `:242-258,1869-1880`). It also disconnects after the operation (`mcp_client.cancel()`, [rust] `:1546`) and races the whole thing against session cancellation ([rust] `:1532-1541`). So: **no connection at `session/new`**, and no connection at all unless the model/agent decides to use a tool. (`testy` advertises `mcpCapabilities.http(true)` only; SSE is explicitly unimplemented, [rust] `:402,1527`.)
- *Consequence:* a fixture MCP server can only prove "the agent connected" if something makes the agent want a tool. That requires either (a) an agent-specific prompt (like `testy`'s `call_tool`, which no other agent implements), or (b) a prompt that an LLM-backed agent happens to answer by calling the tool — non-deterministic and unsuitable for a conformance kit.
- *What a fixture can still buy, cheaply:* a fixture stdio server whose **launch** is observable (e.g. it appends to a marker file, or the harness watches for the child process / a handshake on its stdin) turns Req 10 into an **advisory, connection-timing-agnostic** check: "if the agent ever connects, it does so with the `command`/`args`/`env` we supplied". Assert nothing if no connection occurs. A full MCP handshake implementation is not needed for that — but if the fixture does answer `initialize`/`tools/list`, an agent that connects eagerly will get a clean result instead of an error, which avoids penalizing eager agents.
- *Recommendation:* implement the fixture as an **advisory/informational** probe, not a mandatory Req 10 gate. Req 10's MUST ("all Agents MUST support the stdio transport") is, as written, **not client-observable** in the general case — it should be recorded as an untestable requirement with a rationale, exactly like the "SHOULD connect to all MCP servers" SHOULD.

All Rust SDK observations in this section are **reference evidence only**, per the skill's framing: `testy` is one implementation, and its lazy connection is legal precisely because K5 is unspecified.

---

## Testability notes — concrete TCK assertions

One line each, no ids. "cap:X" means the test only runs when X is advertised. "inferred:X" means it only runs when the agent volunteered X.

### Mandatory (unconditional — every v1 agent)

| Assertion |
|---|
| `initialize` result validates against `InitializeResponse`, and `agentCapabilities` (if present) validates against `AgentCapabilities`. |
| Object-marker capabilities, when present, are objects or `null` — never `true`/`false`/strings. |
| Boolean capabilities (`loadSession`, `promptCapabilities.*`, `mcpCapabilities.*`), when present, are booleans — never `{}`. |
| A `session/prompt` containing only `text` blocks is accepted and the turn ends with a valid `StopReason`. |
| A `session/prompt` containing a `resource_link` block is accepted and the turn ends with a valid `StopReason`. |
| `session/new` with an `mcpServers` entry in the **stdio** shape (`name`,`command`,`args`,`env` all present) is accepted. |
| Calling a method whose gating capability is absent is **not** attempted by the TCK (harness self-check, not an agent assertion). |
| Every `session/update` the agent sends validates against `SessionUpdate` and carries a known `sessionUpdate` discriminator. |
| A `current_mode_update` notification, if sent, carries `currentModeId` (schema name) and not `modeId`. |
| A `config_option_update` notification, if sent, carries a `configOptions` array of schema-valid options. |

### Capability-conditional

| Assertion |
|---|
| cap:`loadSession` — `session/load` with valid `sessionId`+`cwd`+`mcpServers` returns a schema-valid `LoadSessionResponse` **object** (not `null`). |
| cap:`loadSession` — no `session/update` for the loaded `sessionId` arrives **after** the `session/load` response (replay-before-response ordering). |
| cap:`loadSession` — every `session/update` received during the load window validates against `SessionUpdate` and targets the requested `sessionId`. |
| cap:`loadSession` — reloading a session the TCK itself populated with one prompt/response yields ≥1 `user_message_chunk` or `agent_message_chunk` before the response. *(See caveat below — recommend advisory.)* |
| cap:`resume` — `session/resume` with only `sessionId`+`cwd` (no `mcpServers`) is accepted and returns a schema-valid `ResumeSessionResponse` object. |
| cap:`resume` — no `user_message_chunk` / `agent_message_chunk` / `agent_thought_chunk` for that `sessionId` arrives between the `session/resume` request and its response. |
| cap:`list` — `session/list` with `params: {}` returns a schema-valid `ListSessionsResponse` with `sessions` present as an array. |
| cap:`list` — every `SessionInfo` has `sessionId` and an absolute `cwd`. |
| cap:`list` — `session/list` filtered by a `cwd` that no session uses returns `"sessions": []` (empty array, not `null`, not an error). |
| cap:`list` — when `cwd` filter is supplied, every returned `SessionInfo.cwd` equals it exactly. |
| cap:`list` — if `nextCursor` is returned, echoing it as `cursor` yields another schema-valid response (and cursors are round-tripped verbatim as opaque strings). |
| cap:`list` + cap:`additionalDirectories` — `SessionInfo.additionalDirectories`, when present, is an array of absolute paths. |
| cap:`delete` — `session/delete` for a valid session returns a schema-valid empty-object result. |
| cap:`delete` + cap:`list` — a session that appeared in `session/list` does not appear in any subsequent `session/list` page after being deleted. |
| cap:`close` — `session/close` for a valid session returns a schema-valid empty-object result. |
| cap:`close` — with a `session/prompt` in flight, `session/close` is followed by a `session/prompt` response carrying `stopReason: "cancelled"` (derived obligation; message should say so). |
| cap:`close` — all `session/update`s for that session precede the `session/prompt` response. |
| cap:`additionalDirectories` — `session/new` with absolute `additionalDirectories` entries is accepted. |
| cap:`additionalDirectories` + cap:`loadSession` — `session/load` with absolute `additionalDirectories` is accepted. |
| cap:`additionalDirectories` + cap:`resume` — `session/resume` with absolute `additionalDirectories` is accepted. |
| inferred:`modes` — `modes` validates as `SessionModeState` with `currentModeId` ∈ `availableModes[].id`. |
| inferred:`modes` — `session/set_mode` with a `modeId` from `availableModes` returns a schema-valid empty-object result. |
| inferred:`configOptions` — every option has `id`, `name`, a `type` of `select`\|`boolean`, and a type-correct `currentValue`; `select` options carry `options` (flat or grouped). |
| inferred:`configOptions` — `session/set_config_option` returns `configOptions` whose **id set equals** the previously advertised id set (complete-list rule). |
| inferred:`configOptions` — the changed option's `currentValue` in the response equals the value the TCK sent. |
| inferred:`configOptions` — with `clientCapabilities.session.configOptions.boolean` **not** advertised, no option anywhere (session-setup response, set-response, or `config_option_update`) has `type: "boolean"`. |
| cap:`promptCapabilities.image` — a prompt containing a schema-valid `image` block is accepted and the turn ends with a valid `StopReason`. |
| cap:`promptCapabilities.audio` — same for a schema-valid `audio` block. |
| cap:`promptCapabilities.embeddedContext` — same for a schema-valid `resource` block (text and blob forms). |
| cap:`mcpCapabilities.http` — `session/new` with an `{"type":"http",name,url,headers}` entry is accepted. |
| cap:`mcpCapabilities.sse` — `session/new` with an `{"type":"sse",name,url,headers}` entry is accepted. |

### Advisory (recommended behaviour; failure is a warning)

| Assertion |
|---|
| cap:`delete` — `session/delete` for a never-created `sessionId` succeeds silently (SHOULD, `session-delete.mdx:86`). |
| cap:`delete` — `session/delete` for an already-deleted `sessionId` succeeds silently (SHOULD). |
| cap:`list` — an invalid/garbage `cursor` produces an error rather than a silently wrong page (SHOULD, `session-list.mdx:174`). |
| cap:`list` — a session just created via `session/new` appears in `session/list` (spec is silent; see non-assertions). |
| cap:`loadSession` — replay of a TCK-authored conversation includes recognizable message chunks (spec does not forbid compaction/summarization). |
| cap:`additionalDirectories` — a **relative** `additionalDirectories` entry or an empty string is rejected (MUST in the completed RFD, `invalid_params` only RECOMMENDED; nothing on the protocol page pins a code). |
| `agentInfo` is present with `name` + `version` (SHOULD, per prior research Req 4). |
| K2 — a newly written agent advertises `mcpCapabilities.http` (SHOULD, `session-setup.mdx:375`). |
| A fixture stdio MCP server, if the agent connects at all, is launched with exactly the `command`/`args`/`env` supplied (connection itself not required). |

### Informational (record the observation; never pass/fail)

| Observation |
|---|
| cap:`close` — behaviour for an unknown `sessionId` (success vs error, and the code): MAY error, both conforming (`session-setup.mdx:311`). |
| cap:`loadSession` — behaviour for an unknown / never-created `sessionId`: unspecified. |
| cap:`loadSession` — behaviour for a **deleted** `sessionId`: explicitly implementation-defined (`session-delete.mdx:88`). |
| `session/prompt` after `session/delete` or `session/close` on that id: unspecified. |
| Ordering of `sessions` in `session/list`, page size, and duplicate/stability behaviour across pages. |
| Whether closed sessions remain in `session/list`. |
| `session/set_mode` with an id not in `availableModes`: whatever happens. |
| `session/set_config_option` with an unknown `configId`, or a value not in `options`: whatever happens. |
| Whether a `current_mode_update` / `config_option_update` follows a client-driven `set_mode` / `set_config_option`. |
| Whether the agent connects to MCP servers at `session/new`, lazily, or never. |
| A prompt containing a content block whose capability was **not** advertised (TCK violates the client MUST to probe): any outcome. |
| Whether the agent tolerates `session/list` with `params` omitted entirely. |

### Must NOT be asserted — the spec is silent

1. **Any error code for an unknown `sessionId`**, on any method. `docs/protocol/v1/error.mdx:6` is a stub; `-32602` and `-32002` exist in `ErrorCode` (`schema/v1/schema.json:3528-3532,3556-3560`) but nothing binds them to sessions.
2. **That `session/load` errors (or succeeds) for an unknown or deleted session** — implementation-defined (`session-delete.mdx:88`).
3. **That `session/close` errors for an unknown/inactive session** — explicit MAY (`session-setup.mdx:311`).
4. **That `session/prompt` fails after `delete` or `close`** of that id — undefined (`session-delete.mdx:89`; nothing for close).
5. **Any particular set, count, or ordering of `sessionUpdate` kinds during `session/load` replay**, and any fidelity/chunking equivalence to the original stream. The v2 rules (`docs/protocol/v2/session-setup.mdx:144-221`) must not be back-ported.
6. **That `messageId` is present during replay** — v1 says "If the Agent provides message IDs …" (`session-setup.mdx:176`) and `ContentChunk.messageId` is optional (`schema/v1/schema.json:3841-3873`). (v2 makes it required — excluded.)
7. **That `session/resume` sends no updates at all before responding** — only *conversation-history* updates are forbidden (`:243`).
8. **Any relative ordering between the `session/close` response and the in-flight `session/prompt` response.**
9. **Any ordering, recency sort, page size, or cross-page stability for `session/list`.**
10. **That a session created by `session/new` must appear in `session/list`** — never stated.
11. **That a closed session must disappear from `session/list`** — never stated (only *deleted* ones, `session-delete.mdx:85`).
12. **That an agent rejects a content block whose prompt capability it did not advertise**, or any shape/code for such a rejection (`prompt-turn.mdx:92` binds only the client).
13. **That an agent rejects a non-advertised MCP transport config** (`session-setup.mdx:522` binds only the client).
14. **When an agent connects to MCP servers**, or that it connects at all (only SHOULD for "all servers", `:543`; no timing).
15. **That `session/set_mode` / `session/set_config_option` reject an invalid id or value**, or with which code.
16. **That a client-driven mode/config change is echoed as a notification.**
17. **That `session/load` may return `result: null`** — conversely, do not assert tolerance of `null`; the schema requires an object and the docs were just corrected to `{}`.
18. **That `additionalDirectories` are honoured as a filesystem boundary** — SHOULD, and unobservable without agent-specific tool use (`:367`).
19. **That `SessionInfo.additionalDirectories` is returned** — MAY (`session-list.mdx:139-146`).
20. **That omitting `params` on `session/list` is accepted** — envelope allows `null`, typed deserialization in the Rust SDK does not; spec silent.

### v1 vs v2 — **v2 is out of scope and excluded from all assertions**

Relevant deltas for this surface (`docs/protocol/v2/migration.mdx:36-56`, `:20-30`): `session/load` is **removed** (use `session/resume` with `replayFrom: {"type":"start"}`, `:42`); `session/resume` becomes **required with no capability marker** and gains `replayFrom` (`:43`); `session/list` and `session/close` become **required, no capability** (`:44-45`); `session/delete` stays optional but its capability path moves to `session.delete` (`:46`); `session/set_mode` is **removed** in favour of `session/set_config_option` (`:49`); `current_mode_update` is **removed** (`:72`); `mcpServers` becomes optional on `session/new` and `modes` leaves the response (`:41`); `messageId` becomes required on message chunks (`:61-63`); `session/prompt` response semantics are redesigned into an acknowledgement plus `state_update` (`:47-48,65`). v2 also specifies replay in detail — "MUST replay all retained conversation history … before responding", opaque unique `messageId` required per replayed message, retention explicitly not guaranteed (`docs/protocol/v2/session-setup.mdx:118-221`). The v2 protocol surface as a whole is labeled **draft** (`docs/protocol/v2/migration.mdx:20`). Do not derive any v1 assertion from v2 text; where it clarifies what v1 leaves open, cite it as contrast only.

---

## Discrepancies

1. **`current_mode_update` field name — docs vs schema (real bug).** `docs/protocol/v1/session-modes.mdx:117-119` shows `"modeId": "code"`; the schema requires `currentModeId` (`schema/v1/schema.json:4133,4148`) and the Rust model is `current_mode_id` (`agent-client-protocol-schema/src/v1/client.rs:453-455`). Schema wins. Worth an upstream docs PR. Prior research (`acp-v1-protocol-surface.md` §3 table) already flagged the schema name; this confirms the docs side.
2. **`session/load` empty result — `null` vs `{}` (just fixed upstream).** `docs/protocol/v1/session-setup.mdx:184` said `"result": null` until commit `d89c8d3` (`docs: correct empty response examples (#2176)`, the tip of the checked revision) changed it to `"result": {}`. The schema never permitted `null` (`AgentResponse` requires `result` matching a response type, `:2188-2311`). Agents built against the old docs may still emit `null`; a strict TCK will flag them. Recommend: assert object, and mention the doc history in the failure text.
3. **`initialization.mdx` Session Capabilities section is incomplete.** `docs/protocol/v1/initialization.mdx:243-267` documents only `delete` and `additionalDirectories`; `list`, `resume` and `close` are documented only on their own pages (`session-list.mdx:37-54`, `session-setup.mdx:192-213,257-278`) and in the schema (`:2538-2597`). No contradiction, but a reader of the initialization page alone would miss three capabilities.
4. **Grouped select options are schema-only.** `SessionConfigSelectGroup` / the grouped `SessionConfigSelectOptions` variant (`schema/v1/schema.json:3092-3176`) has no counterpart in `docs/protocol/v1/session-config-options.mdx`, which documents only a flat `ConfigOptionValue[]` (`:106-124`). The TCK must accept both forms.
5. **`options` optionality for `select`.** Docs mark `options` as a non-required `ResponseField` with the prose "Required when `type` is `"select"`" (`session-config-options.mdx:106-109`); the schema makes it unconditionally required inside `SessionConfigSelect` (`:3202`). No real conflict, but the schema is the testable form.
6. **`additionalDirectories` normative detail lives in the RFD.** `session-setup.mdx:337-344` gives five rules; the completed RFD (`docs/rfds/additional-directories.mdx:176-271`) adds a much larger set of MUSTs (empty-string rejection, mandatory validation, no silent dropping, `invalid_params` RECOMMENDED, symlink-escape prevention) that never reached the protocol page. Per my source ordering these are design intent from a *Completed* RFD — strong, but not the protocol page. I report both; the TCK should assert only the protocol page and tier the RFD rules advisory.
7. **Reference implementation vs spec: `testy` does not replay on `session/load`.** `testy` advertises `loadSession: true` ([rust] `src/agent-client-protocol-test/src/testy.rs:395`) but its `session/load` handler upserts the session and responds immediately with no `session/update` notifications ([rust] `:1887-1899`) — it keeps no v1 message history. Against `docs/protocol/v1/session-setup.mdx:134` this is non-conforming for a non-empty session (vacuously fine for an empty one, which is all `testy` ever has). Practical consequence: **`testy` is not a valid positive fixture for the load-replay test.** (Its v2 path does implement replay, `md/testy.md:93-95` — v2, excluded.)
8. **Reference implementation choices that are legal but must not become assertions.** `testy` errors with `invalid_params` on unknown session for `set_mode`/`set_config_option`/`prompt` but returns **success** for unknown `delete`/`close` ([rust] `:504-506,527-528,543-569,572-612,303-311`); it sorts `session/list` by `sessionId` ([rust] `:493`); it excludes closed sessions from `session/list` ([rust] `:483-485`); it connects to MCP lazily and does not support SSE ([rust] `:402,1460-1530`). All consistent with the spec's silences.

---

## Open questions

- **Req 10 (stdio MCP MUST) testability policy.** My recommendation is advisory-only via a launch-observable fixture; the decision on whether the TCK ships that fixture at all (and whether it implements a real MCP handshake) is a harness-design call for the orchestrator.
- **Leniency policy for `session/load` returning `null`.** Schema and current docs say object; historical docs said `null`. Whether to hard-fail or warn is a project policy decision, not a spec question.
- **Elicitation, terminals, `fs/*`, `logout`/`authenticate`, slash commands, plans, usage, `$/cancel_request`.** Out of scope here; `logout`/auth is covered by `.agents/research/acp-v1-authentication.md`. The elicitation and terminal capability gates use the same object-marker vs boolean split analyzed in §0 and would benefit from an equivalent deep pass.
- **`_meta`-advertised custom capabilities** (`docs/protocol/v1/initialization.mdx:112`, `docs/protocol/v1/extensibility.mdx`) — how, if at all, the TCK should surface them.
- **Whether the TCK should file the two upstream docs bugs** (`modeId` in `session-modes.mdx:117`; the incomplete Session Capabilities list in `initialization.mdx:243-267`).
