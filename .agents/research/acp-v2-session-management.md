# What does ACP v2 require for the session-management surface beyond `session/prompt`?

**Sources checked:**
- `agent-client-protocol` (spec) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e` (2026-09-21, `main`, == `origin/main`)
- `acp-rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5` (2026-09-18, `main`, == `origin/main`)
- `acp-python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64` (2026-09-21, `main`, == `origin/main`)

> **Refresh note.** `git -C … pull --ff-only` fails in all three checkouts with
> `fatal: Cannot fast-forward to multiple branches` (a local multi-branch tracking config, not a
> stale checkout). I ran `git fetch origin` in each and verified
> `git rev-list --left-right --count HEAD...origin/main` == `0 0`, i.e. all three are exactly at
> `origin/main`. Treat the revisions above as current.

**Confidence:** high for everything the hand-written v2 docs state; **medium** for four derived
items (`session/close` → `state_update`, `session/set_config_option` availability, `session/list`
`cwd`-filter strictness, and how a client can legally obtain a *resumable* session id) — each is
marked inline.

---

## Answer

In v2 the session surface splits cleanly in two: advertising `capabilities.session` (even `{}`)
makes `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`,
`session/cancel` and `session/update` **mandatory** (`docs/protocol/v2/initialization.mdx:149-155`,
`session-list.mdx:10`, `session-setup.mdx:83-84,237-239`), while only `session/delete`,
`session.additionalDirectories` and `session.mcp.{stdio,http}` remain capability-gated. `session/load`
and the entire modes API (`modes`, `session/set_mode`, `current_mode_update`, `SessionMode*`) are
**deleted**; replay is now an *option* on `session/resume` via an inclusive `replayFrom` cursor whose
only stable variant is `{"type":"start"}`, and mode-like state is expressed as session config
options. The ordering contract is explicit and testable: with `replayFrom` omitted or `null` the Agent
**MUST NOT** replay history before responding; with `{"type":"start"}` it **MUST** replay all
*retained* history as `session/update` notifications and **MUST** respond only once every requested
entry has been reported (`session-setup.mdx:118-119,144-145,221-222`) — but "retained" is entirely
agent discretion (`:149-152`), so a TCK may only assert the *ordering*, never that any history exists.
`session/close` keeps its "cancel as if `session/cancel`" MUST, but because the v2 prompt response is
only an insertion ack, close is now observable **only** through the idle `state_update`
(`stopReason: "cancelled"`), not through the prompt reply — so v1's `ACP-CLOSE-002` must be rewritten,
not re-cited. `session/list` gains real `cwd` filtering plus opaque cursor pagination and a
`MUST`-return-empty-array rule; `session/delete` is unchanged; and `session/set_config_option`'s
availability is *still unstated upstream* (no capability marker, absent from the overview's method
lists) even though it is in `schema/v2/meta.json:7`.

---

## Requirements

Tier legend: **MUST** / **SHOULD** / **MAY** as written upstream;
`capability:<path>` = only applies when that `initialize`-result path is a present non-`null`
object; `baseline` = applies whenever `capabilities.session` is present at all (including `{}`).
"(client)" marks obligations on the *Client* — the TCK must **obey** these, not test them.

| # | Requirement | Tier | Citation (repo: `agent-client-protocol` unless noted) |
|---|-------------|------|-----------|
| **Baseline surface** | | | |
| B1 | Supplying `capabilities.session` (even `{}`) commits the Agent to `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, `session/update` | MUST, `capability:capabilities.session` | `docs/protocol/v2/initialization.mdx:149-155`, `:165-167`; `schema/v2/schema.json:3160`; `docs/rfds/v2/required-session-methods.mdx:38-47` (RFD = intent) |
| B2 | Agents that support the `session` surface **MUST** support `session/list` | MUST, baseline | `docs/protocol/v2/session-list.mdx:10` |
| B3 | Agents that support the `session` surface **MUST** support `session/resume` | MUST, baseline | `docs/protocol/v2/session-setup.mdx:83-84` |
| B4 | Agents that support the `session` surface **MUST** support `session/close` | MUST, baseline | `docs/protocol/v2/session-setup.mdx:237-239` |
| B5 | There is **no** `session.list` / `session.resume` / `session.close` / `loadSession` capability field in v2 | (schema fact) | `schema/v2/schema.json:3159-3218` (only `prompt`, `mcp`, `delete`, `additionalDirectories`, `_meta`); `docs/protocol/v2/migration.mdx:43-45` |
| B6 | Clients **MUST** complete `initialize` before `session/new`, `session/list`, `session/delete` | MUST (client) | `session-setup.mdx:8`; `session-list.mdx:10`; `session-delete.mdx:8` |
| **`session/new`** | | | |
| N1 | `session/new` params: `cwd` **required**; `additionalDirectories`, `mcpServers`, `_meta` optional | MUST (shape) | `schema/v2/schema.json:6011-6051` (`required:["cwd"]`) |
| N2 | `mcpServers` is **optional** in v2 (was required-even-if-empty in v1); omitting it and sending `[]` are equivalent | MAY | `docs/protocol/v2/migration.mdx:598`; `schema/v2/schema.json:6048` |
| N3 | The Agent **MUST** respond with a **unique** `sessionId` | MUST | `docs/protocol/v2/session-setup.mdx:69`; `schema/v2/schema.json:3627-3658` (`required:["sessionId"]`) |
| N4 | `session/new` result **MAY** carry `configOptions`; it carries **no** `modes` | MAY / removed | `schema/v2/schema.json:3639-3647`; `docs/protocol/v2/session-config-options.mdx:10`; `migration.mdx:41,598,608` |
| N5 | `session/new` **MAY** fail with `auth_required` (`-32000`) when the Agent requires auth | MAY | `schema/v2/schema.json:5720` (generated from `agent-client-protocol-schema/src/v2/agent.rs:5169`); `docs/protocol/v2/draft/session-setup.mdx:10` — **the stable `session-setup.mdx` never says this** |
| **`session/resume`** | | | |
| R1 | Params: `sessionId` + `cwd` **required**; `additionalDirectories`, `mcpServers`, `replayFrom`, `_meta` optional | MUST (shape) | `schema/v2/schema.json:6274-6334` (`required:["sessionId","cwd"]`) |
| R2 | `replayFrom` omitted **or** `null` ⇒ the Agent **MUST NOT** replay conversation history via `session/update` before responding | **MUST NOT**, baseline | `docs/protocol/v2/session-setup.mdx:118-119` |
| R3 | `replayFrom: {"type":"start"}` ⇒ the Agent **MUST** replay all **retained** history as `session/update` notifications before responding | **MUST**, baseline | `docs/protocol/v2/session-setup.mdx:144-145` |
| R4 | When all requested replay entries have been reported, the Agent **MUST** respond to the `session/resume` request | **MUST**, baseline | `docs/protocol/v2/session-setup.mdx:221-222` |
| R5 | Agents are **not required** to persist/retain any inserted user message; live-only messages may be absent from replay; absence does not contradict a successful prompt response | MAY (explicit escape hatch) | `docs/protocol/v2/session-setup.mdx:149-152`; `prompt-lifecycle.mdx:153,155` |
| R6 | During replay the Agent **MUST** include an opaque, unique `messageId` for each replayed message | **MUST** | `docs/protocol/v2/session-setup.mdx:198-199` |
| R7 | A **retained** user message inserted by `session/prompt` **MUST** replay with the `messageId` returned in that prompt response, including across Agent restarts | **MUST** (conditional on retention, R5) | `docs/protocol/v2/session-setup.mdx:199-201`; `prompt-lifecycle.mdx:153`; `schema/v2/schema.json:4102` |
| R8 | When replay reconstructs a message from its beginning **using chunks**, the Agent **MUST** first send the matching whole-message update (`user_message`/`agent_message`/`agent_thought`) with the same id and `content: []` | **MUST** (conditional) | `docs/protocol/v2/session-setup.mdx:208-212` |
| R9 | `user_message`/`agent_message`/`agent_thought` are upserts keyed by `messageId`; `content` replaces, chunks append; replay is applied in receive order | (semantics) | `docs/protocol/v2/session-setup.mdx:204-219`; `schema/v2/schema.json:4767-4796` |
| R10 | Replay cursors are **inclusive**; `{"type":"start"}` = all retained history | (semantics) | `docs/protocol/v2/session-setup.mdx:126-127`; `schema/v2/schema.json:6335-6400`; `docs/rfds/v2/session-resume-replay.mdx:57-59` |
| R11 | Custom replay-cursor `type`s **MUST** begin with `_`; unknown non-`_` types are reserved for future ACP variants; a receiver that doesn't understand the cursor **should** reject rather than guess | MUST (sender) / SHOULD (receiver) | `schema/v2/schema.json:6354-6362` |
| R12 | `session/resume` response: **no required fields**; `configOptions` and `_meta` optional. Documented empty form is `{}` | MAY | `schema/v2/schema.json:4036-4058`; `docs/protocol/v2/session-setup.mdx:224-233` |
| R13 | Replaying a command reports its message; it does **not** re-execute the command | MUST-ish (flat statement) | `docs/protocol/v2/session-setup.mdx:201-202` |
| **`session/list`** | | | |
| L1 | All `session/list` params are optional; `params: {}` returns the first page | MAY | `docs/protocol/v2/session-list.mdx:61`; `schema/v2/schema.json:6215-6250` (no `required`) |
| L2 | `cwd` filter: must be an absolute path; **only** sessions with a matching `cwd` are returned | MUST-ish (flat statement, no RFC-2119 verb) | `docs/protocol/v2/session-list.mdx:63-66`; `schema/v2/schema.json:6219-6229` |
| L3 | The Agent **MUST** respond with a list of sessions + optional pagination metadata; `sessions` is **required** | **MUST** | `docs/protocol/v2/session-list.mdx:73,108`; `schema/v2/schema.json:3933-3968` (`required:["sessions"]`) |
| L4 | When no sessions match, the Agent **MUST** return an empty `sessions` array | **MUST** | `docs/protocol/v2/session-list.mdx:145` |
| L5 | `SessionInfo`: `sessionId` + `cwd` required; `additionalDirectories`, `title`, `updatedAt`, `_meta` optional (`title`/`updatedAt` nullable) | MUST (shape) | `schema/v2/schema.json:3969-4017` (`required:["sessionId","cwd"]`); `docs/protocol/v2/session-list.mdx:108-138` |
| L6 | `SessionInfo.cwd` is always an absolute path (and *all* protocol paths **MUST** be absolute) | **MUST** | `docs/protocol/v2/session-list.mdx:115-117`; `docs/protocol/v2/overview.mdx:176` |
| L7 | `SessionInfo.updatedAt` is an RFC 3339 timestamp | (typed `format: date-time`) | `schema/v2/schema.json:3999-4003`; `docs/protocol/v2/session-list.mdx:130-132` |
| L8 | `SessionInfo.additionalDirectories`: only Agents that advertise `session.additionalDirectories` **may** include it; it is the **complete ordered** list; omitted ≡ empty; Clients **MUST NOT** merge it with prior values | MAY (agent) / MUST NOT (client) | `docs/protocol/v2/session-list.mdx:35-37,118-125`; `schema/v2/schema.json:3985-3993` |
| L9 | Clients **MUST** treat a missing `nextCursor` as end-of-results, and cursors as opaque (no parse/modify/persist) | MUST (client) | `docs/protocol/v2/session-list.mdx:151-152` |
| L10 | Agents **SHOULD** return an error if the cursor is invalid | **SHOULD** | `docs/protocol/v2/session-list.mdx:153` |
| L11 | Agents **SHOULD** enforce reasonable page sizes internally | SHOULD (unobservable) | `docs/protocol/v2/session-list.mdx:154` |
| L12 | `session_info_update` (`session/update`): all fields optional; omitted = unchanged, `null` = clear; `sessionId`/`cwd`/`additionalDirectories` are **not** in the update | (semantics) | `docs/protocol/v2/session-list.mdx:156-197`; `schema/v2/schema.json:5560-5582` |
| L13 | `session/list` is discovery only — it does **not** restore or modify sessions | (semantics) | `docs/protocol/v2/session-list.mdx:199-205` |
| **`session/close`** | | | |
| X1 | Params: `sessionId` **required** (+ `_meta`); response is an empty object (`{}`), no required fields | MUST (shape) | `schema/v2/schema.json:6401-6423`, `:4059-4072`; `docs/protocol/v2/session-setup.mdx:241-268` |
| X2 | The Agent **MUST** cancel any ongoing work for that session as if `session/cancel` had been called, then free the session's resources | **MUST**, baseline | `docs/protocol/v2/session-setup.mdx:258`; `schema/v2/schema.json:6402`, `:5756` |
| X3 | (X2 ⇒) after all ongoing operations are aborted and pending updates sent, the Agent **MUST** send an **idle `state_update` with `stopReason: "cancelled"`** — *derived* via X2's "as if `session/cancel`" | **MUST** (derived, medium confidence) | `docs/protocol/v2/session-setup.mdx:258` → `prompt-lifecycle.mdx:519,526` |
| X4 | Agents **MAY** return an error if the session does not exist or is not currently active | **MAY** | `docs/protocol/v2/session-setup.mdx:270` |
| X5 | Effect of `session/close` on `session/list` results: **unspecified** | — | no statement anywhere in `docs/protocol/v2/**` |
| X6 | Ordering of the `session/close` *response* relative to the idle `state_update`: **unspecified** | — | no statement; `testy` v2 delays the response until after (`src/agent-client-protocol-test/src/testy/v2.rs:467-477`, rust-sdk) |
| **`session/delete`** | | | |
| D1 | Gated on `capabilities.session.delete`; omitted/`null` = unsupported and Clients **MUST NOT** call it; `{}` = supported | MUST NOT (client), `capability:capabilities.session.delete` | `docs/protocol/v2/session-delete.mdx:35,57`; `schema/v2/schema.json:3187-3198`, `:3363-3374` |
| D2 | Params: `sessionId` **required**; success is an empty result | MUST (shape) | `schema/v2/schema.json:6251-6273`, `:4022-4035`; `docs/protocol/v2/session-delete.mdx:74-86` |
| D3 | Deleted sessions **no longer appear** in future `session/list` results | MUST-ish (flat statement) | `docs/protocol/v2/session-delete.mdx:90` |
| D4 | Deleting an already-deleted or never-existing session **SHOULD** succeed silently | **SHOULD** | `docs/protocol/v2/session-delete.mdx:91` |
| D5 | Soft vs hard delete, `session/resume` on a deleted session, and deleting an **active** session are all implementation-defined | — | `docs/protocol/v2/session-delete.mdx:92-94` |
| **`additionalDirectories`** | | | |
| A1 | Gated on `capabilities.session.additionalDirectories`; supported lifecycle requests are `session/new` **and** `session/resume` | `capability:capabilities.session.additionalDirectories` | `docs/protocol/v2/session-setup.mdx:274-277`; `schema/v2/schema.json:3199-3210`, `:3375-3386` |
| A2 | Each entry **MUST** be an absolute path | **MUST** | `docs/protocol/v2/session-setup.mdx:298`; `overview.mdx:176` |
| A3 | Omitting the field or sending `[]` activates **no** additional roots (no implicit restore on resume) | MUST-ish | `docs/protocol/v2/session-setup.mdx:299-300`; `schema/v2/schema.json:6295` |
| A4 | On `session/resume` the Client **must** send the full intended list again; it may differ from any previous list as long as the request `cwd` matches the session's `cwd` | MUST (client) | `docs/protocol/v2/session-setup.mdx:300` |
| A5 | Clients **MUST only** send `additionalDirectories` when the Agent advertises the capability | **MUST** (client) | `docs/protocol/v2/session-setup.mdx:302` |
| A6 | `cwd` remains the primary working directory and the base for relative paths; the effective root set is `[cwd, ...additionalDirectories]` and **SHOULD** bound file-system tool operations | MUST / SHOULD | `docs/protocol/v2/session-setup.mdx:297,317-324` |
| **MCP servers** | | | |
| M1 | Clients **MAY** include `mcpServers` on `session/new`; transports are advertised as `session.mcp.stdio` / `session.mcp.http` | MAY / `capability:capabilities.session.mcp.{stdio,http}` | `docs/protocol/v2/session-setup.mdx:328,330,465-467`; `schema/v2/schema.json:3303-3362` |
| M2 | Every MCP server object **MUST** carry a `type` discriminator; custom transport types **MUST** begin with `_`; unknown non-`_` types are reserved for future ACP variants | **MUST** | `docs/protocol/v2/session-setup.mdx:334`; `schema/v2/schema.json:6052-6125` |
| M3 | stdio: `type`,`name`,`command` required; `args`,`env` optional (omitted ≡ empty). `command` is an absolute path | MUST (shape) | `docs/protocol/v2/session-setup.mdx:340-369`; `schema/v2/schema.json:6176-6214` (`required:["name","command"]`) |
| M4 | http: `type`,`name`,`url` required; `headers` optional (omitted ≡ empty) | MUST (shape) | `docs/protocol/v2/session-setup.mdx:392-416`; `schema/v2/schema.json:6147-6175` (`required:["name","url"]`) |
| M5 | Before using stdio or HTTP, Clients **MUST** verify the Agent's capabilities | **MUST** (client) | `docs/protocol/v2/session-setup.mdx:440` |
| M6 | Agents **SHOULD** connect to all MCP servers specified by the Client | **SHOULD** (not client-observable in stable v2) | `docs/protocol/v2/session-setup.mdx:469` |
| M7 | A receiver that doesn't understand a transport **should** preserve the raw payload and *otherwise ignore it **or** reject the server configuration* — both permitted | SHOULD, either-or | `schema/v2/schema.json:6089` |
| M8 | The v1 `"type": "sse"` HTTP+SSE transport is **removed** | removed | `docs/protocol/v2/migration.mdx:644` |
| **Config options** | | | |
| C1 | During session setup the Agent **MAY** return `configOptions` (on both `session/new` and `session/resume`) | **MAY** | `docs/protocol/v2/session-config-options.mdx:10`; `schema/v2/schema.json:3639-3647`, `:4040-4049` |
| C2 | `SessionConfigOption`: `configId` + `name` required, plus a `type` discriminator (`select` ⇒ `currentValue`+`options` required; `boolean` ⇒ `currentValue` required); `description`, `category`, `_meta` optional | MUST (shape) | `schema/v2/schema.json:3659-3932`; `docs/protocol/v2/session-config-options.mdx:76-108` |
| C3 | `select` `options` is **either** a flat `ConfigOptionValue[]` **or** a `ConfigOptionGroup[]` — never mixed. Groups require `groupId`, `name`, `options` | MUST (shape) | `docs/protocol/v2/session-config-options.mdx:104-108,124-129`; `schema/v2/schema.json:3810-3898` |
| C4 | The `configOptions` array order is the Agent's preferred priority; Agents **SHOULD** put higher-priority options first; Clients **SHOULD** respect it | **SHOULD** | `docs/protocol/v2/session-config-options.mdx:70-74,185-193` |
| C5 | Agents **MUST** always provide a default value (`currentValue`) for every configuration option | **MUST** | `docs/protocol/v2/session-config-options.mdx:197` |
| C6 | `category` is UX-only and **MUST NOT** be required for correctness; Clients **MUST** tolerate missing/unknown categories. Stable values: `mode`, `model`, `model_config`, `thought_level`; `_`-prefixed = custom | MUST NOT / MUST | `docs/protocol/v2/session-config-options.mdx:163-183`; `schema/v2/schema.json:3776-3805` |
| C7 | Custom option `type`s **MUST** begin with `_`; unknown non-`_` types reserved for future ACP. Clients **SHOULD** preserve the raw option and otherwise ignore it | MUST / SHOULD | `docs/protocol/v2/session-config-options.mdx:203`; `schema/v2/schema.json:3734-3741` |
| C8 | `session/set_config_option` params: `sessionId`, `configId`, plus a required `type`+`value` pair — `type:"id"` with a string, `type:"boolean"` with a bool, or a custom `_`-prefixed type | MUST (shape) | `docs/protocol/v2/session-config-options.mdx:227-260`; `schema/v2/schema.json:6424-6530` |
| C9 | The Agent **MUST** respond with the **complete** list of all configuration options and their current values | **MUST** | `docs/protocol/v2/session-config-options.mdx:262,307-312`; `schema/v2/schema.json:4073-4096` (`required:["configOptions"]`) |
| C10 | Agent-initiated changes arrive as a `config_option_update` `session/update`, which also contains the **complete** configuration state | MUST-ish | `docs/protocol/v2/session-config-options.mdx:314-365`; `schema/v2/schema.json:5538-5559` (`required:["configOptions"]`) |
| C11 | The current value **can be changed at any point during a session** | (semantics) | `docs/protocol/v2/session-config-options.mdx:207` |
| C12 | **No capability gates `session/set_config_option`.** It is in `meta.json`'s `agentMethods` and the schema (`x-side: agent`) but appears in **neither** the overview's Agent "Baseline Methods" list nor any optional-method list | **unstated** | `schema/v2/meta.json:7`; `schema/v2/schema.json:6528-6529`; `docs/protocol/v2/overview.mdx:52-124` (absent); `docs/protocol/v2/initialization.mdx:149-199` (no marker) |
| C13 | There is **no** `clientCapabilities.session.configOptions.boolean` in v2 — the v1 boolean-option client gate is gone | removed | `schema/v2/schema.json:5842-5877` (`ClientCapabilities` = `auth`, `elicitation`, `_meta` only); `docs/protocol/v2/initialization.mdx:113-143` |
| **Modes (removed)** | | | |
| Z1 | The dedicated modes API is **removed**: `modes` on session responses, `session/set_mode`, `current_mode_update`, and all `SessionMode*` types | removed | `docs/protocol/v2/migration.mdx:49,72,606-608`; `docs/rfds/v2/overview.mdx:48-49`; `schema/v2/meta.json` (no `session_set_mode`) |
| Z2 | Mode-like state is expressed as a config option, canonically `configId: "mode"`, `category: "mode"`; the identifier field is `configId` (v1 used `id`) | replacement | `docs/protocol/v2/migration.mdx:610-626`; `docs/protocol/v2/session-config-options.mdx:19-38` |

---

## Details

### 0. Which "v2" this describes

`docs/protocol/v2/*.mdx` + `schema/v2/schema.json` + `schema/v2/meta.json` are the **stable v2
surface** and are what this report covers. Two other layers exist and must not be conflated:

- `docs/protocol/v2/draft/*.mdx` — a *draft-on-top-of-v2* layer. Session-management deltas there:
  live-only `notice` updates are not conversation history and **SHOULD NOT** be replayed
  (`docs/protocol/v2/draft/session-setup.mdx:155-158`), `session/new` may fail with `auth_required`
  is stated explicitly (`:10`), and a `model_config` `context_size` config option example is added.
- `schema/v2/schema.unstable.json` + `schema/v2/meta.unstable.json` — adds `session/fork`
  (+ `session.fork` capability, `schema/v2/schema.unstable.json:3532,3744`), an `acp` MCP transport
  (`:3663`), `providers/*`, `nes/*`, `mcp/message`, `document/did*`.
- Upstream still tags the **whole** of v2 as "Draft" in the docs nav (v1 is "Latest"):
  `docs/docs.json` → Protocol tab → group `v2`, `"tag": "Draft"`.

### 1. Per-method reference

#### `session/new` — baseline (`capabilities.session`)

| Param | Type | Req? | Notes |
|---|---|---|---|
| `cwd` | `AbsolutePath` (string) | **required** | primary working directory; MUST be absolute, MUST be used regardless of spawn dir, MUST be the relative-path base, MUST be in the effective root set (`session-setup.mdx:317-322`) |
| `additionalDirectories` | `AbsolutePath[]` | optional | gated on `session.additionalDirectories` (A1/A5) |
| `mcpServers` | `McpServer[]` | optional | **changed from v1**; omitted ≡ `[]` |
| `_meta` | object\|null | optional | |

| Result | Type | Req? |
|---|---|---|
| `sessionId` | `SessionId` (string) | **required** |
| `configOptions` | `SessionConfigOption[]` | optional |
| `_meta` | object\|null | optional |

Schema: `schema/v2/schema.json:6011-6051` (request), `:3627-3658` (response).
Errors: `auth_required` (`-32000`) **MAY** be returned (N5 — generated prose only, not in the
hand-written stable page). Nothing else is specified.

#### `session/resume` — baseline

| Param | Type | Req? |
|---|---|---|
| `sessionId` | `SessionId` | **required** |
| `cwd` | `AbsolutePath` | **required** |
| `additionalDirectories` | `AbsolutePath[]` | optional (capability-gated) |
| `mcpServers` | `McpServer[]` | optional |
| `replayFrom` | `ReplayFrom` \| `null` | optional |
| `_meta` | object\|null | optional |

`ReplayFrom` is a tagged union with exactly one stable variant,
`{"type":"start"}` (`ReplayFromStart`, whose only property is `_meta`), plus an extensible
`other` variant (`schema/v2/schema.json:6335-6400`).

Result: `ResumeSessionResponse` — **no required fields**; optional `configOptions`, `_meta`
(`schema/v2/schema.json:4036-4058`). Documented empty form is `{}`
(`session-setup.mdx:224-230`). Unlike v1's `session/load`, the docs never show `null` here, so
the v1 `null`-tolerance quirk (`ACP-LOAD-003`) has no v2 analogue in prose — though the vendored
v2 schema still types it as an all-optional object, so the TCK's existing
`validate_agent_response` leniency applies unchanged.

Errors: **nothing specified.** No statement about unknown `sessionId`, about resuming a session
that is already active on this connection, about `cwd` mismatch, or about resuming a deleted
session (the latter explicitly implementation-defined, `session-delete.mdx:93`).

#### `session/list` — baseline

| Param | Type | Req? |
|---|---|---|
| `cwd` | `AbsolutePath` \| `null` | optional — filter |
| `cursor` | `SessionListCursor` (opaque string) \| `null` | optional — pagination |
| `_meta` | object\|null | optional |

| Result | Type | Req? |
|---|---|---|
| `sessions` | `SessionInfo[]` | **required** |
| `nextCursor` | `SessionListCursor` \| `null` | optional |
| `_meta` | object\|null | optional |

`SessionInfo` = `sessionId` (req), `cwd` (req), `additionalDirectories?`, `title?: string|null`,
`updatedAt?: string|null (date-time)`, `_meta?`.
Schema: `:6215-6250`, `:3933-4017`, cursor `:4018-4021`.

- **Filtering:** `cwd` only; must be absolute; "Only sessions with a matching `cwd` are returned."
- **Pagination:** opaque `cursor` in, opaque `nextCursor` out; absent `nextCursor` = end (L9);
  invalid cursor **SHOULD** error (L10).
- **Ordering:** **no guarantee of any kind.** No statement about recency, `updatedAt`, or
  stability across pages.
- **Closed sessions:** unspecified — nothing says a closed session leaves the list.
  (`testy` v2 keeps them: `active:false` sessions still enumerate,
  rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:87-106`.)
- **Deleted sessions:** MUST NOT appear in future results (D3).
- **New sessions:** nothing says a session created by `session/new` must appear in
  `session/list` at all. `session/list` lists "sessions known to an Agent"
  (`session-list.mdx:6`).

#### `session/close` — baseline

Params `{sessionId}`; result `{}` (both all-optional-`_meta` objects).
The substantive obligation is X2/X3. The **v1→v2 change that matters most for the TCK**: in v1
the close-cancels-work obligation was observable through the still-pending `session/prompt`
response resolving with `stopReason:"cancelled"`. In v2 `session/prompt` has **already
responded** with only a `messageId` (`schema/v2/schema.json:4097-4119`,
`prompt-lifecycle.mdx:155`), so the only client-observable consequence of `session/close` during
foreground work is the idle `state_update` carrying `stopReason:"cancelled"`.

#### `session/delete` — `capability:capabilities.session.delete`

Params `{sessionId}` (required); result `{}`. Semantics block is short and unusually explicit
about what is *not* specified (D3–D5).

#### `session/set_config_option` — **gate unstated (C12)**

Params: `sessionId`, `configId`, and a required `{type, value}` pair. The union
(`schema/v2/schema.json:6452-6527`) is:

```json
{"sessionId":"…","configId":"mode","type":"id","value":"code"}
{"sessionId":"…","configId":"brave_mode","type":"boolean","value":true}
{"sessionId":"…","configId":"_x","type":"_custom","value":<any>}
```

Result: `{configOptions: SessionConfigOption[]}` — `configOptions` is **required**
(`:4073-4096`), and the docs state the completeness rule twice (`:262`, `:307-312`).

### 2. `session/resume` in depth — the v1 load+resume unification

Upstream commit `a57b538d27af0b464dd845c8ca9a4deec0ed2367`
(*"feat(unstable-v2): Unify session/load and session/resume (#1584)"*, 2026-07-02) removed
`session/load`, `LoadSessionRequest`, `LoadSessionResponse` from the v2 schema and added
`replayFrom`. The design record is `docs/rfds/v2/session-resume-replay.mdx` (RFD = **intent**,
not a requirement) and the *normative* text is `docs/protocol/v2/session-setup.mdx:81-233`.

**Does resume replay history? Conditionally — and it is the same method for both v1 behaviours:**

| `replayFrom` | Behaviour | Tier | Citation |
|---|---|---|---|
| omitted | **MUST NOT** replay history via `session/update` before responding. Restores context, reconnects requested MCP servers, returns when ready. | MUST NOT | `session-setup.mdx:118-121` |
| `null` | identical to omitted | MUST NOT | `session-setup.mdx:118`; `schema/v2/schema.json:6313` |
| `{"type":"start"}` | **MUST** replay *all retained* history as `session/update` notifications **before** responding | MUST | `session-setup.mdx:144-145` |
| `{"type":"_x"}` / unknown non-`_` | undefined; receiver **should** reject rather than guess | SHOULD | `schema/v2/schema.json:6356` |

**Ordering MUSTs, precisely:**

1. `session-setup.mdx:144-145` — "the Agent **MUST** replay all retained conversation history to
   the Client in the form of `session/update` notifications **before responding**."
2. `session-setup.mdx:221-222` — "When all requested replay entries have been reported to the
   Client, the Agent **MUST** respond to the original `session/resume` request."
3. `session-setup.mdx:118-119` — the mirror-image MUST NOT for the no-cursor case.

Together these give a clean, observable ordering contract: with `{"type":"start"}` every replay
update precedes the response; with no cursor, no *history* update precedes it. The sequence
diagram (`:28-34`) shows exactly that.

**Which `session/update` variants carry replay?** Not enumerated. What *is* said:

- "User, agent, and thought messages can each be replayed as message updates with full `content`
  arrays **or as chunks**" (`:146-147`) — i.e. `user_message`/`agent_message`/`agent_thought`
  and/or `user_message_chunk`/`agent_message_chunk`/`agent_thought_chunk`.
- `migration.mdx:592`: replay uses "the same message, **tool-call, and plan** updates as live
  traffic" — so `tool_call_update` and `plan_update` are also legitimate replay traffic.
- Anything else in the 16-variant `SessionUpdate` union (`schema/v2/schema.json:4300-4737`) is
  neither required nor forbidden during replay. **Do not assert a variant whitelist.**
- Draft-only: `notice` updates are live-only and **SHOULD NOT** be replayed
  (`docs/protocol/v2/draft/session-setup.mdx:155-158`).

**Message-id rules during replay** (R6–R9). The chunk-reconstruction rule (R8) is the sharpest
new testable MUST in this area:

> "When replay reconstructs a message from its beginning using chunks, the Agent **MUST** first
> send the corresponding message update (`user_message`, `agent_message`, or `agent_thought`)
> with the same ID and `content: []`." (`session-setup.mdx:208-211`)

and R7:

> "A retained user message inserted by `session/prompt` **MUST** use the ID returned in that
> prompt response, including after reconnecting or restarting the Agent."
> (`session-setup.mdx:199-201`)

**What the response carries:** nothing required. `configOptions` optionally, and
`session-setup.mdx:232-233` adds "The response **MAY** also include initial session configuration
state when that feature is supported by the Agent." No state/`state_update`, no `sessionId` echo,
no message count, no cursor.

**Unknown or already-active session:** **completely unspecified.** No error code, no MAY, no
SHOULD — in contrast to `session/close` (X4: explicit MAY) and `session/delete` (D4: explicit
SHOULD-succeed-silently). The reference implementation returns `-32602` for an unknown session,
for a session with foreground work in flight, and for a `cwd` mismatch
(rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:108-143`). Treat all three as
**must-NOT-assert**.

**The v1 distinction, restated in v2 terms:** v1's `ACP-LOAD-002` ("load replays before response")
becomes the `replayFrom: {"type":"start"}` branch, and v1's `ACP-RESUME-002` ("resume does not
replay") becomes the omitted/`null` branch. **Same method, two cursors.** v2 is also *stronger*
than v1 on the negative side: v1's prohibition was narrow (the TCK scoped it to the three
history-chunk variants in the pre-response window); v2 says plainly "**MUST NOT** replay the
conversation history via `session/update` notifications before responding", which covers
whole-message upserts as well as chunks.

### 3. `session/close` vs `session/delete`

| | `session/close` | `session/delete` |
|---|---|---|
| Gate | baseline (`capabilities.session`) | `capabilities.session.delete` |
| Target | an **active** session | a session in **`session/list`** history |
| Obligation | MUST cancel ongoing work as if `session/cancel`, then free resources (X2) | remove from future `session/list` results (D3) |
| In-flight turn | MUST cancel ⇒ (derived) idle `state_update` `stopReason:"cancelled"` (X3) | **implementation-defined** (D5) |
| Effect on `session/list` | **unspecified** (X5) | MUST no longer appear (D3) |
| Unknown / non-existent id | **MAY** error (X4) | **SHOULD** succeed silently (D4) |
| Result shape | `{}` | `{}` |
| Resumable afterwards? | unspecified | implementation-defined (D5) |

### 4. `additionalDirectories` and `mcpServers`

**`additionalDirectories`** is unchanged in spirit from v1 but v2 states explicitly that
`session/resume` is a supported carrier ("Supported stable lifecycle requests include
`session/new` and `session/resume`", `session-setup.mdx:276-277`) and adds the no-implicit-restore
rule (A3/A4). The client-side MUST (A5) is a **TCK hygiene rule**, not a test: the TCK must not
send `additionalDirectories` to an agent that does not advertise the capability.

**`mcpServers`** — the client-observable surface is *thin*. Stable v2's client methods are
`session/request_permission`, `session/update`, `elicitation/create`, `elicitation/complete`
(`schema/v2/meta.json:16-21`). There is **no** `mcp/connect` / `mcp/message` / `mcp/disconnect`
in stable v2 (those exist only in `meta.unstable.json:34-36`). So v1's conclusion **holds for
stable v2**: whether the Agent actually connected to a stdio or HTTP MCP server is *not
client-observable*. The only observable is "the lifecycle request succeeded / failed".

**What MUST the Agent do when an unadvertised variant is sent?**

- For an **advertised-shape-but-unsupported-transport** (`stdio` sent to an agent with no
  `session.mcp.stdio`): **nothing is specified.** The rule is phrased entirely as a *Client*
  MUST-verify (M5). There is no agent-side MUST-reject and no MUST-ignore. **Must-NOT-assert.**
- For an **unknown / custom `type`**: `schema/v2/schema.json:6089` gives the receiver an explicit
  either-or — "preserve the raw payload when storing, replaying, proxying, or forwarding session
  setup data, and otherwise **ignore it or reject** the server configuration." Both a success and
  an error are conforming. The only thing that is *not* conforming is dying or never answering.

### 5. Config options and what replaced modes

The v2 config-options surface is the v1 surface with three edits and one deletion:

| v1 | v2 |
|---|---|
| `SessionConfigOption.id` | `configId` (`schema/v2/schema.json:3663-3669`; `migration.mdx:624`) |
| group `group`/`groupId` naming | `groupId` (`schema/v2/schema.json:3865-3871`) |
| `clientCapabilities.session.configOptions.boolean` gates `type:"boolean"` options | **deleted** — no such client capability exists in v2 (C13) |
| `modes` / `session/set_mode` / `current_mode_update` / `SessionMode*` | **deleted**; use a `category:"mode"` config option, `session/set_config_option`, `config_option_update` (Z1/Z2) |

Everything else carries over: the MAY on returning `configOptions`, the MUST-provide-a-default
(C5), the complete-list MUST on the `session/set_config_option` response (C9) and on
`config_option_update` (C10), and `category` being UX-only (C6).

`session/set_config_option`'s **availability remains unstated upstream** (C12) — restating, not
resolving, per the capabilities report. The observable facts: it is in `meta.json`'s
`agentMethods`, it has `x-side: "agent"`/`x-method: "session/set_config_option"` in the schema,
no capability object mentions it, and `docs/protocol/v2/overview.mdx` lists neither it nor
`session/delete` in any Agent method section. The only *available* hook is inference from
`configOptions` being present in a `session/new`/`session/resume` response — exactly the v1
`inferred:configOptions` pattern. **Hypothesis (not cited anywhere upstream):** an Agent that
returns `configOptions` must implement `session/set_config_option`, since C11 says the value "can
be changed at any point during a session" and there is no other way to change it. Label it as a
hypothesis in the registry text.

### 6. Reference behaviour

#### Rust SDK — `testy` v2 (`src/agent-client-protocol-test/src/testy/v2.rs`, rust-sdk @ `2a78849`)

Build/run note: v2 is behind a cargo feature —
`cargo build -p agent-client-protocol-test --bin testy --features unstable_protocol_v2`
(`src/agent-client-protocol-test/Cargo.toml:12-15`, `src/agent-client-protocol-test/src/bin/testy.rs:10-19`).
With the feature on, the binary installs an `AgentProtocolRouter` that picks v1 or v2 from the
client's `initialize` (`src/agent-client-protocol-test/src/testy.rs:231-236`). **Use a scratch
`--target-dir` under `/tmp`.**

| Method | `testy` v2 behaviour | Line | Verdict |
|---|---|---|---|
| `initialize` | `capabilities: {session: {}}` only, `info: {name:"test-agent", version:<pkg>}`; echoes the requested `protocolVersion` verbatim | `:389-395`, `:407-413` | version echo = the same false-negative pattern the TCK's strengthened `ACP-INIT-003` already catches in v1 |
| `session/new` | returns `{sessionId:"testy-v2-session-N"}`; stores `cwd` + `additionalDirectories`; **no** `configOptions` | `:57-78`, `:417-425` | conforming |
| `session/list` | filters by `cwd` when given; sorts by `sessionId` string; sets `title:"Testy v2 session"` and `updatedAt:"2026-01-01T00:00:00Z"` on every entry; **never** returns `nextCursor`; includes **closed** (`active:false`) sessions; emits `additionalDirectories` when non-empty even though `session.additionalDirectories` is **not** advertised | `:87-106`, `:429-437` | conforming (the `additionalDirectories` echo is only reachable if a client violates A5 → **informational**, not a bug) |
| `session/resume` | unknown session → `-32602`; foreground work in flight → `-32602`; `cwd != session.cwd` → `-32602`; unknown replay cursor → `-32602`; `replayFrom:start` replays `UserMessage`/`AgentMessage` **whole-message upserts** (never chunks) **before** responding; replaces `additionalDirectories` from the request; result `{}` | `:108-143`, `:439-456` | conforming; all four error cases are **spec-silent** → informational |
| `session/close` | unknown session → `-32602`; marks inactive; if foreground work, marks cancelled and **defers the close response until the turn's idle `state_update` has been sent** | `:223-240`, `:457-480` | conforming; the response ordering is stricter than the spec requires (X6) → **informational** |
| `session/prompt` | `-32602` on a closed session; `-32602` on overlapping foreground work; responds with `messageId` immediately, then `user_message` → `state_update running` → content → `state_update idle{stopReason}` | `:145-165`, `:288-387`, `:481-515` | conforming |
| `session/cancel` | marks cancelled only if foreground work exists | `:205-221`, `:516-526` | conforming |
| `session/delete` | **not implemented** → `-32601` (and `session.delete` not advertised) | — | conforming |
| `session/set_config_option` | **not implemented** → `-32601` (and no `configOptions` ever advertised) | — | conforming |

Notable: `testy` v2 records history only as whole-message upserts
(`V2SessionData.history`, `:39`, `:282-286`, `:378-383`), so it never exercises the R8
chunk-clearing rule, and it *does* preserve the prompt-response `messageId` into replay
(`:492-497` stores the `UserMessage` built with the same id it returned) — i.e. R7 is satisfied.

#### Python SDK (`acp-python-sdk` @ `9d07d78`)

- The v2 surface lives under `src/acp/experimental/v2/` and is generated from the **unstable**
  schema: `schema/v2/VERSION` = `refs/tags/schema-v2.0.0-alpha.5`, and
  `scripts/gen_all.py:25` reads `schema/v2/schema.unstable.json`. Consequently its v2
  `agentMethods` include `session/fork`, `providers/*`, `nes/*`, `mcp/message`,
  `document/did*` (`schema/v2/meta.json` in the python-sdk checkout). **It is not a stable-v2
  binding.** Anything the TCK infers from it must be filtered against the spec's
  `schema/v2/meta.json`.
- The typed Agent protocol declares `new_session`, `list_sessions`, `delete_session`,
  `fork_session`, `resume_session`, `close_session`, `set_config_option`
  (`src/acp/experimental/v2/interfaces.py:74-127`), with `default_result={}` on
  `session/delete` and `session/close` (`:89`, `:115`) — a handler returning `None` is serialized
  as `{}` (`src/acp/experimental/v2/_router.py:42-44`).
- Unimplemented methods raise `-32601` (`_router.py:36-39,62-65`); unknown notifications are
  silently dropped (`:56-61`); `_`-prefixed methods route to
  `handle_extension_request`/`handle_extension_notification` (`:67-74`).
- **There is no v2 example agent and no v2 session-semantics implementation.** `examples/`
  contains only v1 agents, and `tests/test_v2_runtime.py` / `test_v2_routing.py` only exercise
  routing/typing (the one session-config test is `test_v2_runtime.py:464-485`). So the Python SDK
  provides **no observable reference behaviour** for `session/list`/`resume`/`close`/`delete`
  semantics — only for wire shapes and the `-32601`/`{}` conventions. Nothing here is a bug; it
  is simply not an agent.

---

## Testability notes

### The hard problem: getting a legally resumable session id

There is **no spec-guaranteed way** for a black-box client to obtain a session id it is entitled
to `session/resume`. All three candidate routes are unspecified:

1. Resume the session you just created on this connection — nothing says an *already-active*
   session is resumable (`testy` v2 allows it when idle, rejects it mid-turn, `:117-122`).
2. `session/close` then resume — nothing says a closed session is resumable (X5).
3. `session/list` then resume the first entry — the documented flow
   (`session-list.mdx:199-205`), but nothing says a session created by `session/new` appears in
   `session/list` at all.

**Recommended harness strategy** (medium confidence, my design call, not upstream): try (1),
then (3), then (2), recording each error; treat `-32601` on `session/resume` as a **FAIL** of
`ACP-RESUME-201` (B3 makes the method mandatory), but treat any *other* error from all three
routes as a **SKIP** with the recorded errors in the message. Never FAIL on `-32602`/`-32002`
here — the spec authorizes no interpretation of those.

### Assertable vs. unassertable, by requirement

| Requirement | How to assert | Honest limits |
|---|---|---|
| B1–B4 (baseline methods) | send each method; `-32601` ⇒ FAIL | the *only* unambiguous failure signal; any other error is not provably non-conformant |
| N3 (unique `sessionId`) | two `session/new`, compare strings | unchanged from v1 |
| R2 (no replay without cursor) | resume with `replayFrom` absent; assert **zero** `session/update` for that `sessionId` between the request and its response | **vacuous** for an agent that retains nothing. Cannot distinguish "obeyed" from "nothing to replay". Record the count. |
| R3+R4 (replay before response) | resume with `{"type":"start"}`; assert every `session/update` for that session arrives **before** the response, and none within `quiet_period(timeout)` **after** | Cannot assert that *any* history is replayed (R5). Zero updates is conforming — record as INFORMATIONAL, do not FAIL. |
| R6 (`messageId` on replayed messages) | schema validation already covers it (`required:["messageId"]` on all six message variants, `schema/v2/schema.json:4738,4767,4797,4827`) | keep a separate id only for report legibility |
| R7 (prompt id survives replay) | prompt once, capture the response's `messageId`, resume with `start`, then: FAIL only if a replayed `user_message`/`user_message_chunk` carries content equal to the prompted content but a **different** `messageId` | a *narrow* trigger on purpose. Absence of the message is conforming (R5), so the test must not require presence. |
| R8 (chunk replay needs a `content: []` primer) | in the replay window, FAIL if a `*_chunk` appears for a `messageId` that had no preceding whole-message update in that same window | vacuous for agents that replay only whole messages (`testy` v2) |
| R11 (unknown cursor) | send `replayFrom: {"type":"_tck/nope"}`; assert the agent answers *something* (success or error) | SHOULD-level; INFORMATIONAL at best |
| L3 (`sessions` array) | `session/list` with `params: {}` | clean MANDATORY |
| L2 (`cwd` filter) | list with `cwd: <a real absolute dir>`; assert **every** returned entry's `cwd` equals it | robust (per-entry check, immune to pre-existing sessions). Do **not** assert the reverse direction (that a session at that cwd appears). |
| L4 (empty array) | list with a `cwd` that no session can plausibly use (e.g. a fresh temp dir); assert `sessions == []` | clean MANDATORY; guard against `null` |
| L6 (`cwd` absolute) | `os.path.isabs` on every entry | platform-correct because the agent runs locally |
| L7 (`updatedAt` RFC 3339) | parse when present | ADVISORY (`format` is annotation-only in JSON Schema) |
| L10 (invalid cursor) | send `cursor: "_tck-invalid"`; expect an error | SHOULD; a lenient agent returning an empty page is conforming. Suggest ADVISORY or INFORMATIONAL. |
| ordering / paging stability | — | **unassertable**; no upstream guarantee |
| D3 (delete removes from list) | only if the session appeared in `session/list` first; list → delete → list → assert absent | SKIP when the session was never listed |
| D4 (silent delete) | delete a random uuid sessionId twice | ADVISORY, same as v1 |
| X2/X3 (close cancels the turn) | start a turn that stays in flight, send `session/close`, then require an idle `state_update` with `stopReason:"cancelled"` for that session | **derived** (X3). Same race problem as v1's cancel tests: if the turn already went idle before close was sent, SKIP ("close not exercised"), never PASS/FAIL. The prompt *response* is no longer a signal — do not look at it. |
| X6 (close response vs idle) | — | **must not assert**; `testy` orders one way, the spec allows either |
| A1/A2 (additionalDirectories) | on `session/new` **and** `session/resume`, with absolute paths, only when advertised | the *effect* is unobservable; only acceptance is |
| M1–M4 (MCP shapes) | `session/new` with a well-formed stdio / http entry, only when the matching capability is advertised; assert acceptance | **the connection itself is unobservable in stable v2** (no `mcp/*` client methods). Point a stdio entry at a harmless absolute `command` that need not exist — the agent's connect failure is its own business, and failing `session/new` because an MCP server is unreachable is not provably non-conformant. Consider INFORMATIONAL rather than CAPABILITY for that reason. |
| M7 (custom transport) | send `{"type":"_tck/none","name":"x"}`; assert the agent answers at all | INFORMATIONAL — ignore and reject are both conforming |
| C2/C3/C5 (option shapes) | validate each entry returned by `session/new`/`session/resume`; plus the derived `select.currentValue ∈ options` (flat or grouped) | the `currentValue ∈ options` link is **not** schema-enforced; it is derived from C5 + the field descriptions |
| C9 (complete list on set) | set one option, assert the response's `configId` set ⊇ the previously-known set | the "dependent changes" note (`:307-312`) permits *adding* options and changing *other* values, so only a **subset** violation is a FAIL. Asserting `currentValue == the value you sent` is weaker than it looks — an agent may legitimately reflect a dependent adjustment; keep that sub-assertion ADVISORY. |
| C10 (`config_option_update` complete) | when such an update is observed, assert its `configId` set ⊇ the last known set | vacuous when unobserved |
| C12 (set_config_option availability) | gate on `inferred:configOptions`; a `-32601` when **no** `configOptions` were ever advertised must be a SKIP, not a FAIL | the gate is genuinely unstated upstream |

### Conforming vs. non-conforming fixture sketches

A `conforming_v2_full.py` needs, at minimum: `capabilities.session` with `delete: {}`,
`additionalDirectories: {}`, `mcp: {stdio: {}, http: {}}`, `prompt: {...}`; a `session/new` that
returns `configOptions` (one `select` with `category:"mode"`, one `boolean`, one grouped
`select`); per-session history recorded as whole messages **and** (for a second session) as
chunk sequences primed with `content: []`; `session/list` with real `cwd` filtering and a
two-page cursor; `session/resume` honouring both cursor states; `session/close` emitting
`state_update idle{stopReason:"cancelled"}`; `session/delete` removing from list;
`session/set_config_option` returning the full list.

Defect fixtures that trip exactly one row each:

| Fixture | Trips |
|---|---|
| `v2_session_marker_no_list.py` — advertises `session:{}`, `-32601` on `session/list` | `ACP-LIST-201` |
| `v2_session_marker_no_resume.py` / `…no_close.py` | `ACP-RESUME-201` / `ACP-CLOSE-201` |
| `v2_resume_replays_without_cursor.py` — replays history when `replayFrom` is absent | `ACP-RESUME-203` |
| `v2_resume_replays_after_response.py` — answers `session/resume` first, then replays | `ACP-RESUME-202` |
| `v2_resume_chunks_without_primer.py` — replays chunks with no `content: []` message first | `ACP-RESUME-205` |
| `v2_resume_renumbers_message_ids.py` — replays the prompt's user message with a fresh id | `ACP-RESUME-204` |
| `v2_list_ignores_cwd_filter.py` — returns every session regardless of `cwd` | `ACP-LIST-203` |
| `v2_list_returns_null_sessions.py` — `{"sessions": null}` | `ACP-LIST-201` (schema) |
| `v2_list_empty_is_error.py` — errors instead of `sessions: []` | `ACP-LIST-202` |
| `v2_delete_keeps_in_list.py` — succeeds but still lists the session | `ACP-DELETE-202` |
| `v2_close_no_state_update.py` — answers `session/close` and never emits idle/cancelled | `ACP-CLOSE-202` |
| `v2_config_partial_list.py` — `session/set_config_option` returns only the changed entry | `ACP-CONFIG-202` |
| `v2_config_update_partial.py` — `config_option_update` with a subset | `ACP-CONFIG-206` |
| `v2_config_select_bad_current.py` — `currentValue` not in `options` | `ACP-CONFIG-204` |
| `v2_emits_current_mode_update.py` — emits the removed v1 variant | the enum-extensibility rule (see Open questions) |

---

## Candidate v2 requirement rows

Ids follow the 200-series convention already adopted by
`.agents/research/acp-v2-initialize-capabilities-baseline.md:291`. Rows marked **[baseline]**
were already proposed in that report — I re-cite them here with the deeper detail this area
owns; the orchestrator should keep a single registry entry per id and let that report own the
gate wording.

| Id | Requirement | Tier | Citation | Conforming / non-conforming |
|---|---|---|---|---|
| `ACP-SESSION-201` **[baseline]** | `session/new` with an absolute `cwd` and **no** `mcpServers` succeeds with a non-empty string `sessionId`; the response validates | CAPABILITY `capabilities.session` | `session-setup.mdx:69`; `schema/v2/schema.json:6048`, `:3655` | ✓ `{"sessionId":"s1"}` / ✗ `-32601`, or a result with no `sessionId` |
| `ACP-SESSION-202` **[baseline]** | Two `session/new` calls return distinct `sessionId`s | CAPABILITY `capabilities.session` | `session-setup.mdx:69` | ✗ `v2_duplicate_session_id.py` |
| `ACP-SESSION-203` | `session/new` is accepted with `mcpServers` **omitted** and with `mcpServers: []` (equivalent forms) | CAPABILITY `capabilities.session` | `migration.mdx:598`; `schema/v2/schema.json:6032-6040,6048` | ✗ an agent that requires `mcpServers` (the v1 shape) and answers `-32602` when it is absent |
| `ACP-RESUME-201` **[baseline]** | `session/resume` (no `replayFrom`) of a session obtained per the harness strategy above succeeds with a schema-valid object result | CAPABILITY `capabilities.session` | `session-setup.mdx:83-84`; `schema/v2/schema.json:6274-6334`, `:4036-4058` | ✗ `-32601`. Any other error ⇒ **SKIP** |
| `ACP-RESUME-202` | With `replayFrom: {"type":"start"}`, every `session/update` for that session arrives **before** the `session/resume` response, and none arrives within `quiet_period(timeout)` after it | MANDATORY (MUST), CAPABILITY `capabilities.session` | `session-setup.mdx:144-145,221-222` | ✓ updates… then `{}` / ✗ `v2_resume_replays_after_response.py`. Zero updates = conforming, recorded |
| `ACP-RESUME-203` | With `replayFrom` **omitted**, no conversation-history `session/update` for that session arrives before the response | MANDATORY (MUST NOT), CAPABILITY `capabilities.session` | `session-setup.mdx:118-119` | ✗ `v2_resume_replays_without_cursor.py`. Vacuous when the agent retains nothing |
| `ACP-RESUME-204` | A retained user message inserted by `session/prompt` replays with the `messageId` returned by that prompt response | MANDATORY (MUST, conditional on retention) | `session-setup.mdx:199-201`; `schema/v2/schema.json:4102` | ✗ `v2_resume_renumbers_message_ids.py`. SKIP when the message is not replayed at all (R5) |
| `ACP-RESUME-205` | During replay, a `*_chunk` for a `messageId` is preceded in the replay window by the matching whole-message update (with `content: []` when reconstructing from the beginning) | MANDATORY (MUST, conditional) | `session-setup.mdx:208-212` | ✗ `v2_resume_chunks_without_primer.py`. Vacuous for whole-message replay |
| `ACP-RESUME-206` | Every replayed message update / chunk carries a `messageId` | MANDATORY (schema-covered) | `session-setup.mdx:198-199`; `schema/v2/schema.json:4767,4797,4827,4738` | keep for report legibility only; already caught by schema validation |
| `ACP-LIST-201` **[baseline]** | `session/list` with `params: {}` succeeds; `sessions` present as an array | CAPABILITY `capabilities.session` | `session-list.mdx:10,73`; `schema/v2/schema.json:3933-3968` | ✗ `v2_session_marker_no_list.py`, `v2_list_returns_null_sessions.py` |
| `ACP-LIST-202` | `session/list` filtered by a `cwd` no session uses returns `sessions: []` (never `null`, never an error) | MANDATORY (MUST), CAPABILITY `capabilities.session` | `session-list.mdx:145` | ✗ `v2_list_empty_is_error.py` |
| `ACP-LIST-203` | With a `cwd` filter, **every** returned `SessionInfo.cwd` equals the requested `cwd` | MANDATORY (flat statement, derived tier) | `session-list.mdx:63-66` | ✗ `v2_list_ignores_cwd_filter.py` |
| `ACP-LIST-204` | Every `SessionInfo.cwd` is an absolute path | MANDATORY | `session-list.mdx:115-117`; `overview.mdx:176` | ✗ an entry with `"cwd": "project"` |
| `ACP-LIST-205` | `SessionInfo.updatedAt`, when present and non-`null`, parses as RFC 3339 | ADVISORY | `schema/v2/schema.json:3999-4003`; `session-list.mdx:130-132` | ✗ `"updatedAt": "yesterday"` |
| `ACP-LIST-206` | `sessionId`s within one `session/list` response are unique | ADVISORY (derived from "Unique identifier") | `schema/v2/schema.json:3974`; `session-list.mdx:112-114` | ✗ the same id twice |
| `ACP-LIST-207` | `session/list` with an invalid `cursor` returns an error | ADVISORY (SHOULD) | `session-list.mdx:153` | a lenient empty page is conforming — consider INFORMATIONAL instead |
| `ACP-LIST-208` | INFORMATIONAL: record whether a session created by `session/new` on this connection appears in `session/list`, and whether a `session/close`d session still appears | INFORMATIONAL | no upstream statement (X5; `session-list.mdx:6`) | never assert |
| `ACP-CLOSE-201` **[baseline]** | `session/close` of a live, idle session succeeds with a schema-valid empty-object result | CAPABILITY `capabilities.session` | `session-setup.mdx:237-239,258-268`; `schema/v2/schema.json:6401-6423`, `:4059-4072` | ✗ `v2_session_marker_no_close.py` |
| `ACP-CLOSE-202` | `session/close` during foreground work cancels it: an idle `state_update` with `stopReason: "cancelled"` for that session is observed | MANDATORY (**derived**, medium confidence), CAPABILITY `capabilities.session` | `session-setup.mdx:258` → `prompt-lifecycle.mdx:519,526` | ✗ `v2_close_no_state_update.py`. SKIP when the turn ended before close landed. **Do not look at the prompt response** |
| `ACP-DELETE-201` **[baseline]** | `session/delete` of an existing session succeeds with an empty-object result | CAPABILITY `capabilities.session.delete` | `session-delete.mdx:35,57,74-86` | ✗ advertises `delete:{}` but answers `-32601`/errors |
| `ACP-DELETE-202` | After a successful `session/delete`, the session no longer appears in `session/list` | CAPABILITY `capabilities.session.delete` | `session-delete.mdx:90` | ✗ `v2_delete_keeps_in_list.py`. SKIP when the session never appeared in the list |
| `ACP-DELETE-203` | Deleting an already-deleted or never-created `sessionId` succeeds silently | ADVISORY (SHOULD) | `session-delete.mdx:91` | verbatim re-cite of v1 `ACP-DELETE-002` |
| `ACP-ADDDIRS-201` **[baseline]** | `session/new` with an absolute `additionalDirectories` entry is accepted | CAPABILITY `capabilities.session.additionalDirectories` | `session-setup.mdx:274-302`; `schema/v2/schema.json:6023-6031` | ✗ advertises the marker, `-32602` on the field |
| `ACP-ADDDIRS-202` | `session/resume` with an absolute `additionalDirectories` entry (same `cwd` as the session) is accepted | CAPABILITY `capabilities.session.additionalDirectories` | `session-setup.mdx:276-277,300`; `schema/v2/schema.json:6294-6302` | new in v2 (v1 had no resume carrier statement) |
| `ACP-MCP-201` | When `capabilities.session.mcp.stdio` is advertised, `session/new` with a well-formed stdio entry (`type`,`name`,`command` absolute) is accepted | CAPABILITY `capabilities.session.mcp.stdio` | `session-setup.mdx:336-386,440,465`; `schema/v2/schema.json:6176-6214` | ✗ advertises `stdio:{}`, `-32602` on a valid stdio entry. **Consider INFORMATIONAL** — a connect failure is not provably non-conformant (M6 is a SHOULD) |
| `ACP-MCP-202` | When `capabilities.session.mcp.http` is advertised, `session/new` with a well-formed http entry (`type`,`name`,`url`) is accepted | CAPABILITY `capabilities.session.mcp.http` | `session-setup.mdx:388-436`; `schema/v2/schema.json:6147-6175` | same caveat as `ACP-MCP-201` |
| `ACP-MCP-203` | INFORMATIONAL: with an `_`-prefixed custom MCP transport `type`, record whether the agent ignores it (success) or rejects it (error) — both conforming; only silence/death is not | INFORMATIONAL | `schema/v2/schema.json:6089`; `session-setup.mdx:334` | never assert on which branch |
| `ACP-CONFIG-201` **[baseline]** | Every `configOptions` entry in `session/new`'s result validates: `configId`, `name`, `type`, `currentValue`; `select` carries `options` (flat **or** grouped, not mixed) | CAPABILITY `inferred:configOptions` | `schema/v2/schema.json:3659-3932`; `session-config-options.mdx:76-129` | ✗ emits the v1 `id` key instead of `configId` |
| `ACP-CONFIG-202` **[baseline]** | `session/set_config_option` responds with the **complete** `configOptions` list (every previously-known `configId` present) | CAPABILITY `inferred:configOptions` | `session-config-options.mdx:262,307-312`; `schema/v2/schema.json:4073-4096` | ✗ `v2_config_partial_list.py`. Gate is unstated (C12) — SKIP on `-32601` when no options were advertised |
| `ACP-CONFIG-203` | `session/resume`'s `configOptions`, when present, validates the same way as `ACP-CONFIG-201` | CAPABILITY `inferred:configOptions` | `session-setup.mdx:232-233`; `schema/v2/schema.json:4040-4049` | new carrier in v2 |
| `ACP-CONFIG-204` | A `select` option's `currentValue` is one of its `options` values (flat or grouped) | MANDATORY (derived from C5 + field descriptions; **not** schema-enforced) | `session-config-options.mdx:99-108,197`; `schema/v2/schema.json:3899-3921` | ✗ `v2_config_select_bad_current.py` |
| `ACP-CONFIG-205` | After a successful `session/set_config_option`, the returned entry for that `configId` carries the value that was sent | ADVISORY | `session-config-options.mdx:240-244` vs the dependent-changes escape at `:307-312` | keep ADVISORY: the completeness note explicitly permits reflecting dependent changes |
| `ACP-CONFIG-206` | An observed `config_option_update` carries the **complete** configuration state (its `configId` set ⊇ the last known set) | MANDATORY (conditional; vacuous when unobserved) | `session-config-options.mdx:365`; `schema/v2/schema.json:5538-5559` | ✗ `v2_config_update_partial.py` |

### v1 ids to retire

| v1 id | Why | Citation |
|---|---|---|
| `ACP-LOAD-001` | `session/load` and the `loadSession` capability are **removed** from v2. Its intent lives on in `ACP-RESUME-201`/`202` | `migration.mdx:42,576`; `docs/rfds/v2/session-resume-replay.mdx:35`; `schema/v2/meta.json` (no `session_load`) |
| `ACP-LOAD-002` | replaced by `ACP-RESUME-202` (same ordering MUST, now on `session/resume` + `replayFrom:start`) | `session-setup.mdx:144-145,221-222` |
| `ACP-LOAD-003` | v2 has no `session/load`, and `session/resume`'s docs show `{}` only — the v1 `null`-vs-`{}` docs artifact has no v2 analogue | `session-setup.mdx:224-230`; `schema/v2/schema.json:4036-4058` |
| `ACP-RESUME-001` | gate changed: `agentCapabilities.sessionCapabilities.resume` no longer exists; resume is baseline. Re-minted as `ACP-RESUME-201` | `schema/v2/schema.json:3159-3218`; `migration.mdx:43` |
| `ACP-RESUME-002` | replaced by `ACP-RESUME-203`, which is **broader**: v2's MUST NOT covers the whole conversation history, not only the three chunk variants | `session-setup.mdx:118-119` |
| `ACP-LIST-001` / `-002` | gate changed (`sessionCapabilities.list` removed; list is baseline). Re-minted as `ACP-LIST-201`/`202` | `session-list.mdx:10`; `migration.mdx:44` |
| `ACP-DELETE-001` / `-002` | same requirements, new capability path `capabilities.session.delete`. Re-minted as `ACP-DELETE-201`/`203` | `session-delete.mdx:35`; `schema/v2/schema.json:3187-3198` |
| `ACP-CLOSE-001` | gate changed (close is baseline). Re-minted as `ACP-CLOSE-201` | `session-setup.mdx:237-239`; `migration.mdx:45` |
| `ACP-CLOSE-002` | **must be rewritten, not re-cited.** Its assertion ("the prompt resolves with `stopReason:"cancelled"`") is impossible in v2: `PromptResponse` has no `stopReason` and has already been sent. Replaced by `ACP-CLOSE-202` | `schema/v2/schema.json:4097-4119`; `prompt-lifecycle.mdx:155`; `migration.mdx:47-48` |
| `ACP-ADDDIRS-001` | same requirement, new capability path. Re-minted as `ACP-ADDDIRS-201` | `schema/v2/schema.json:3199-3210` |
| `ACP-MODES-001` | `modes` is gone from every session response | `migration.mdx:41,606-608`; `docs/rfds/v2/overview.mdx:48` |
| `ACP-MODES-002` | `session/set_mode` and `current_mode_update` are gone; the `currentModeId`-vs-`modeId` docs bug it encoded is moot | `migration.mdx:49,72`; `schema/v2/meta.json` |
| `ACP-CONFIG-001` | superseded by `ACP-CONFIG-201`/`204` (field renamed `id` → `configId`) | `migration.mdx:624`; `schema/v2/schema.json:3663` |
| `ACP-CONFIG-002` | same requirement, new citation. Re-minted as `ACP-CONFIG-202` | `session-config-options.mdx:262` |
| `ACP-CONFIG-003` | **retire outright.** v2 has no `clientCapabilities.session.configOptions.boolean`; `ClientCapabilities` is `auth`, `elicitation`, `_meta`. There is no v2 rule restricting `type:"boolean"` options | `schema/v2/schema.json:5842-5877`; `docs/protocol/v2/initialization.mdx:113-143` |

### Must-NOT-assert list (v2 leaves these open)

1. **Unknown `sessionId` on `session/resume`, `session/prompt`, `session/set_config_option`.** No
   error code, no MAY, no SHOULD anywhere in `docs/protocol/v2/**`. (`testy` v2 answers `-32602`.)
   Note the one exception: `session/close` has an explicit **MAY** error (X4) and `session/delete`
   an explicit **SHOULD succeed silently** (D4) — assert neither as mandatory.
2. **Resuming an already-active session, or with a `cwd` different from the session's.** The only
   hint is A4's conditional clause "as long as the request `cwd` matches the session's `cwd`" —
   that constrains the *Client*, and prescribes no Agent response. (`testy` v2: `-32602` for both.)
3. **Whether a `session/new`-created session appears in `session/list`.** Unstated.
4. **Whether a closed session still appears in `session/list`, or is resumable.** Unstated (X5).
5. **`session/list` ordering**, pagination stability, page size, and whether `nextCursor` is ever
   produced at all.
6. **Which `session/update` variants appear during replay**, how many, and their fidelity. "User,
   agent, and thought messages" plus tool-call/plan updates are *permitted*, not required.
7. **That any conversation history exists to replay.** R5 is an explicit escape hatch.
8. **Ordering of the `session/close` response relative to the idle `state_update`** (X6).
9. **Whether `session/close` on an already-closed or unknown session errors** (X4 is a MAY).
10. **Whether an Agent must reject `mcpServers` entries whose transport it did not advertise.**
    Unstated for `stdio`/`http`; explicitly either-or for unknown types (M7).
11. **Whether an MCP server was actually connected.** Not client-observable in stable v2 (M6 is a
    SHOULD with no observable).
12. **Whether `session/set_config_option` is available at all** when the Agent advertised
    `capabilities.session` but returned no `configOptions` (C12).
13. **That `SessionInfo.additionalDirectories` is absent when the capability is unadvertised.**
    The spec only phrases it as a MAY for advertising Agents (L8); it never forbids the field
    otherwise. (`testy` v2 emits it when non-empty without advertising the marker.)
14. **`session/delete` on an active session**, and soft-vs-hard delete (D5).
15. **Effects of `session/resume`'s `mcpServers`/`additionalDirectories` on the session's actual
    root set or tool availability** — A6's boundary rule is a SHOULD with no ACP-observable
    surface now that `fs/*` and `terminal/*` are removed.

---

## Discrepancies

1. **Baseline method count: 4 vs 7 — tier-relevant.**
   `AgentCapabilities.session`'s field doc says supplying `{}` means the Agent supports
   "`session/new`, `session/prompt`, `session/cancel`, and `session/update`"
   (`schema/v2/schema.json:3128`, generated from
   `agent-client-protocol-schema/src/v2/agent.rs:3951-3952`). **Four methods — no `list`, no
   `resume`, no `close`.** Every other source says seven: `SessionCapabilities`' own doc
   (`schema/v2/schema.json:3160`; `agent.rs:4140-4142`),
   `docs/protocol/v2/initialization.mdx:149-155` and `:165-167`,
   `docs/protocol/v2/session-list.mdx:10`, `docs/protocol/v2/session-setup.mdx:83-84,237-239`,
   `docs/protocol/v2/migration.mdx:604`, and `docs/rfds/v2/required-session-methods.mdx:38-47`.
   **Reading:** the 4-method text is a stale doc-comment left behind by the
   required-session-methods change (the RFD's implementation plan step 2 says "Update the v2 docs
   to describe these methods as baseline", `required-session-methods.mdx:84-85`). Weight of
   evidence is overwhelmingly on seven. **Recommendation:** tier `ACP-LIST-201`,
   `ACP-RESUME-201`, `ACP-CLOSE-201` as CAPABILITY-on-`capabilities.session` (i.e. a `-32601`
   FAILs), and note this discrepancy in each registry row's citation so a future reader can see
   why. Worth reporting upstream.

2. **Replay: prose MUST vs generated SHOULD — tier-relevant.**
   `docs/protocol/v2/session-setup.mdx:118-119,144-145,221-222` state the replay contract as
   **MUST NOT** / **MUST** / **MUST**. The generated method docs say "should":
   `schema/v2/schema.json:5747` ("If `replayFrom` is set, the agent **should** replay retained
   conversation history before responding", from `agent.rs:5196-5198`) and
   `schema/v2/schema.json:6313` ("Omitted or `null` both mean the Agent **should** resume without
   replaying"). **Recommendation:** follow the hand-written normative prose (MANDATORY for
   `ACP-RESUME-202`/`203`) — the schema doc-comments are descriptive summaries, and the
   `check-specification` skill designates normative documentation as the contract. Record the
   conflict in the registry citation.

3. **`session/list` MUST vs generated SHOULD.** `session-list.mdx:73` — "The Agent **MUST**
   respond with a list of sessions"; `schema/v2/schema.json:5729` — "The agent **should** return
   metadata about sessions". Low impact: `required: ["sessions"]` in
   `ListSessionsResponse` (`:3965`) settles the shape regardless.

4. **`auth_required` on `session/new`.** Present only in generated prose
   (`schema/v2/schema.json:5720`, from `agent.rs:5169`) and in the *draft* layer
   (`docs/protocol/v2/draft/session-setup.mdx:10`); the **stable**
   `docs/protocol/v2/session-setup.mdx` never mentions authentication. (Already noted as
   Discrepancy 4 in the initialize/capabilities report; repeated here because it affects
   `session/new` test design.)

5. **`L2` phrasing.** "Only sessions with a matching `cwd` are returned"
   (`session-list.mdx:63-66`) is a flat statement inside a `<ParamField>` description, not an
   RFC-2119 MUST. I tier `ACP-LIST-203` MANDATORY because it is the filter's entire meaning and
   is cleanly observable, but a reviewer could defensibly argue ADVISORY.

6. **Python SDK v2 ≠ stable v2.** `acp-python-sdk`'s v2 bindings are generated from
   `schema/v2/schema.unstable.json` at `schema-v2.0.0-alpha.5`
   (`acp-python-sdk/schema/v2/VERSION`, `scripts/gen_all.py:25`), so they expose `session/fork`,
   `providers/*`, `nes/*`, `mcp/message` and an `acp` MCP transport that are **not** in stable v2
   (`agent-client-protocol/schema/v2/meta.json`). Not a bug — but the TCK must never take the
   Python SDK's v2 method inventory as the v2 surface.

7. **`testy` v2 reports `SessionInfo.additionalDirectories` without advertising
   `session.additionalDirectories`** (rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:95`
   vs `:394`). Only reachable if the Client violates A5, and the field is skipped when empty
   (`agent-client-protocol-schema/src/v2/agent.rs:1889`). **Informational**, not a bug.

8. **`testy` v2 defers the `session/close` response until foreground work finishes**
   (rust-sdk `…/testy/v2.rs:467-477`). Stricter than the spec requires (X6). **Informational** —
   and a reason the TCK must not assert either ordering.

---

## Open questions

1. **`session/set_config_option` availability (C12).** Unresolved upstream: no capability marker,
   absent from every doc method list, present in `meta.json`/schema. Someone should either file
   an upstream question or the orchestrator should accept the `inferred:configOptions` gate plus
   an explicit "hypothesis" note in the registry text. *Do not* mark it baseline.
2. **How the TCK legally obtains a resumable session id.** My recommended
   try-three-routes-then-SKIP strategy is a *harness design* decision, not a protocol finding.
   Route to whoever owns the v2 `_helpers` port.
3. **Whether `ACP-MCP-201/202` should be CAPABILITY or INFORMATIONAL.** Acceptance of a
   well-formed MCP entry is observable, but a real agent may legitimately fail `session/new`
   because the server is unreachable, and M6 is only a SHOULD. This is a tiering judgement call
   for the orchestrator.
4. **`state_update` / `stopReason` semantics after `session/close`.** `ACP-CLOSE-202` depends on
   the prompt-lifecycle report's `state_update` model (idle + `stopReason`) and on its
   Discrepancy 1 (MUST-in-prose vs SHOULD-in-schema for `stopReason` on idle). Owned by
   `.agents/research/acp-v2-prompt-lifecycle.md`; `ACP-CLOSE-202`'s tier should track whatever
   that report's `ACP-STATE-203` settles on.
5. **An agent that emits the removed `current_mode_update` (or a `modes` key) in v2.** Because
   `SessionUpdate` has an extensible `other` variant (`schema/v2/schema.json:4559-4572`), such an
   update **validates** against the schema; the violation is the "unknown non-`_` discriminator
   values are reserved for future ACP variants" rule
   (`docs/protocol/v2/overview.mdx:191`, `docs/protocol/v2/extensibility.mdx`). That general rule
   is owned by `.agents/research/acp-v2-patches-enums-extensibility.md` — route the
   `current_mode_update`-specific fixture there rather than duplicating it in the session area.
6. **`session/fork`, the `acp` MCP transport, and draft `notice` non-replay.** Unstable/draft
   session-management surfaces (`schema/v2/schema.unstable.json:3532,3663,4989`;
   `docs/protocol/v2/draft/session-setup.mdx:155-158`). Out of scope for a stable-v2 TCK slice;
   flagging so nobody re-discovers them mid-implementation.
7. **Upstream bug reports.** Discrepancies 1 and 2 are worth filing upstream; that is an
   orchestrator decision, not mine.
