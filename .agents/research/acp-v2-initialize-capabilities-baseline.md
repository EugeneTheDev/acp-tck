# What does ACP v2 require of an agent in the `initialize` exchange, how are capabilities encoded and gated, which methods are the always-available baseline, and what is the minimal `session/new` contract?

**Sources checked:**
- `check-specification` — `agentclientprotocol/agent-client-protocol` @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e` (2026-09-21 10:46 UTC, `git pull --ff-only` → "Already up to date"). All `schema/…`, `docs/…`, `agent-client-protocol-schema/…` citations below are from **this** repo unless prefixed otherwise.
- `check-rust-sdk` — `agentclientprotocol/rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5` (2026-09-18). Used only to settle the `capabilities.session` reading and to check what a real v2 fixture advertises.
- `check-python-sdk` — `agentclientprotocol/python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64` (2026-09-21). Used only for schema-provenance checking.
- `check-a2a-tck` — **not** consulted; nothing here needed it.
- Read for orientation, not re-derived: `.agents/research/acp-v2-status-and-delta-inventory.md`, `.agents/research/acp-v2-version-negotiation.md`.

**Confidence:** high — every field, `required` array, and normative sentence below was read directly out of `schema/v2/schema.json` and the v2 prose at the pinned revision; the two ambiguities I found are reported as discrepancies rather than smoothed over. Medium only on the *derived* rule that a v2 agent must not call `fs/*`/`terminal/*` (§4.4): the spec removes those methods but never writes the negative sentence.

---

## Answer

A v2 `initialize` request is `{protocolVersion: <uint16>, info: {name, version, title?}, capabilities?: {}}` — `info` is **REQUIRED on both sides** now (`schema/v2/schema.json:5838`, `:3086`), `capabilities` is optional and defaults to `{}`. The response is `{protocolVersion, info, capabilities?, authMethods?}`, and every capability marker is an **object**: present-and-non-null means supported, omitted-or-`null` means unsupported (`docs/protocol/v2/initialization.mdx:104`, `migration.mdx:181`). There are exactly **four** agent-side top-level capability keys (`session`, `session.prompt{image,audio,embeddedContext}`, `session.mcp{stdio,http}`, `session.delete`, `session.additionalDirectories`, plus the gate-nothing `auth`) and exactly **three** client-side ones (`auth.terminal`, `elicitation.form`, `elicitation.url`) — `migration.mdx:191`'s claim that stable v2 defines no client capability fields is stale (written 2026-07-08, before elicitation and terminal auth were stabilized on 2026-07-24 / 2026-08-20) and the TCK must follow the schema + `initialization.mdx`. The v2 baseline is **conditional, not unconditional**: only `initialize` is unconditionally required; advertising `capabilities.session` (even as `{}`) commits the agent to `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel` and `session/update`, and a non-empty `authMethods` commits it to `auth/login` + `auth/logout`. Minimal `session/new`: params `{cwd: <absolute>}` only (`mcpServers` became optional in v2), response `{sessionId: <string>}` only, and the Agent **MUST** respond with a *unique* session ID (`docs/protocol/v2/session-setup.mdx:69`, `schema/v2/schema.json:6048`, `:3655`).

**On the coordinator's question (empty `session: {}`):** the schema settles it decisively — `SessionCapabilities`'s property set is exactly `{prompt, mcp, delete, additionalDirectories, _meta}` (`schema/v2/schema.json:3159-3218`). There is **no** `session.list`, `session.resume`, or `session.close` key to set, so the "only nested keys are markers" reading is not expressible. `session: {}` *is* the marker for the 7-method baseline. The Rust doc comment at `agent-client-protocol-schema/src/v2/agent.rs:3947-3952` that lists only 4 methods is stale text dating to 2026-06-18 (`2b4fcab`), never updated when the 7-method wording landed 2026-07-02 (`a57b538`, "Unify session/load and session/resume"). `testy` v2 is exactly right, not under-advertising.

---

## Requirements

Every row below is additionally conditional on the connection having negotiated `protocolVersion: 2` (`docs/protocol/v2/migration.mdx:30`; see `.agents/research/acp-v2-version-negotiation.md`). Tier is the spec's own keyword strength; the TCK tier I recommend is in §7.

| # | Requirement | Tier | Citation (spec repo) |
|---|---|---|---|
| I1 | Clients **MUST** call `initialize` before a session can be created, sending the latest protocol version, capabilities, and implementation info | MUST (client) | `docs/protocol/v2/initialization.mdx:24-28`; `docs/protocol/v2/session-setup.mdx:8` |
| I2 | `initialize.params` REQUIRED set is exactly `["protocolVersion","info"]` | MUST (client) | `schema/v2/schema.json:5838` |
| I3 | `initialize.params.capabilities` is OPTIONAL with `default: {}` | MAY | `schema/v2/schema.json:5821-5829` |
| I4 | The Agent **MUST** respond with the chosen protocol version, the capabilities it supports, and its implementation information | MUST (agent) | `docs/protocol/v2/initialization.mdx:47` |
| I5 | `initialize.result` REQUIRED set is exactly `["protocolVersion","info"]` — `info` is REQUIRED (v1's `agentInfo` was optional) | MUST (agent) | `schema/v2/schema.json:3086`; `docs/protocol/v2/initialization.mdx:248` |
| I6 | `Implementation` REQUIRED set is `["name","version"]`; `title` optional/nullable | MUST | `schema/v2/schema.json:3121`, `:3097-3120` |
| I7 | Both Clients and Agents **MUST** provide `info` | MUST (both) | `docs/protocol/v2/initialization.mdx:248` |
| I8 | Implementations **MUST** treat every omitted capability as UNSUPPORTED | MUST (both) | `docs/protocol/v2/initialization.mdx:104` |
| I9 | The Agent **SHOULD** specify whether it supports `session` and `auth` capabilities | SHOULD (agent) | `docs/protocol/v2/initialization.mdx:147` |
| I10 | Every v2 support marker is an object: `{}` (or an object with fields) means supported; omitting the key or supplying `null` means unsupported | MUST (encoding) | `docs/protocol/v2/migration.mdx:181`; every capability field description, e.g. `schema/v2/schema.json:3188`, `:3224` |
| C1 | Supplying `capabilities.session` (including `{}`) means the Agent supports `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, `session/update` | capability:`capabilities.session` ⇒ MUST | `docs/protocol/v2/initialization.mdx:149-155`, `:165-167`; `schema/v2/schema.json:3160`; `docs/protocol/v2/migration.mdx:190` |
| C2 | Agents that support the `session` method surface **MUST** support `session/list` | capability:`capabilities.session` ⇒ MUST | `docs/protocol/v2/session-list.mdx:10` |
| C3 | Agents that support the `session` method surface **MUST** support `session/resume` | capability:`capabilities.session` ⇒ MUST | `docs/protocol/v2/session-setup.mdx:83-84` |
| C4 | Agents that support the `session` method surface **MUST** support `session/close` | capability:`capabilities.session` ⇒ MUST | `docs/protocol/v2/session-setup.mdx:237` |
| C5 | Omitting/`null`ing `capabilities.session` means the Agent does not support the `session/*` surface at all | capability (absence) | `schema/v2/schema.json:3128`; `docs/protocol/v2/initialization.mdx:150-151`; `docs/protocol/v2/migration.mdx:188` |
| C6 | `session.delete` present ⇒ `session/delete` available; omitted/`null` ⇒ Clients **MUST NOT** call it | capability:`capabilities.session.delete` | `docs/protocol/v2/session-delete.mdx:35,57`; `schema/v2/schema.json:3187-3198` |
| C7 | `session.additionalDirectories` present ⇒ `additionalDirectories` accepted on session lifecycle requests; Clients **MUST only** send it when advertised | capability:`capabilities.session.additionalDirectories` | `docs/protocol/v2/session-setup.mdx:302`; `docs/protocol/v2/initialization.mdx:192-199` |
| C8 | Agents that advertise `session` **MUST** support `ContentBlock::Text` and `ContentBlock::ResourceLink` in `session/prompt`; richer content is opt-in via `session.prompt.{image,audio,embeddedContext}` | MUST / capability | `docs/protocol/v2/initialization.mdx:203-226` |
| C9 | Clients **MUST** verify `session.mcp.stdio` / `session.mcp.http` before using those MCP transports | MUST (client) / capability | `docs/protocol/v2/session-setup.mdx:440,465-467` |
| C10 | `capabilities.auth` (agent) advertises authentication **extensions only**; it does **not** advertise `auth/login` or `auth/logout` availability and its only defined property is `_meta` | statement of fact | `docs/protocol/v2/initialization.mdx:80,157-161`; `schema/v2/schema.json:3387-3398` |
| A1 | Returning one or more valid `authMethods` entries means the Agent **MUST** implement both `auth/login` and `auth/logout` | capability:`authMethods` non-empty ⇒ MUST | `docs/protocol/v2/initialization.mdx:78`; `docs/protocol/v2/authentication.mdx:51-54`; `docs/protocol/v2/overview.mdx:54`; `schema/v2/schema.json:3071` |
| A2 | If `authMethods` is omitted or empty, Clients **MUST NOT** call `auth/login` or `auth/logout` | MUST NOT (client) | same as A1; `docs/protocol/v2/migration.mdx:177` |
| A3 | Agents **MUST** advertise a `type: "terminal"` auth method only when the Client enabled `capabilities.auth.terminal` | MUST (agent), client-gated | `schema/v2/schema.json:3522` (`AuthMethodTerminal` description); `docs/protocol/v2/authentication.mdx:151-154` |
| A4 | Every `AuthMethod` carries a REQUIRED `type` discriminator; `agent`/`terminal` variants require `methodId` + `name` | MUST | `schema/v2/schema.json:3399-3494`, `:3567`, `:3597` |
| A5 | The Client **MUST NOT** send `auth/login` for a `terminal` method | MUST NOT (client) | `docs/protocol/v2/authentication.mdx:215-216`; `schema/v2/schema.json:3522` |
| A6 | Custom auth method `type` values **MUST** begin with `_`; unknown non-`_` types are reserved for future ACP | MUST | `docs/protocol/v2/authentication.mdx:120-122`; `schema/v2/schema.json:3436,3440` |
| A7 | `session/new` **may** return an `auth_required` (`-32000`) error if the agent requires authentication | MAY (statement) | `docs/protocol/v2/schema.mdx:428`; `agent-client-protocol-schema/src/v2/agent.rs:5169` |
| A8 | After a successful `auth/login`, the Client can create sessions without receiving `auth_required` | statement of consequence | `docs/protocol/v2/authentication.mdx:192-193`; `docs/protocol/v2/schema.mdx:32-33` |
| A9 | After `auth/logout`, the protocol makes **no** guarantee about already-running sessions | statement (no requirement) | `docs/protocol/v2/authentication.mdx:247-255` |
| S1 | `session/new` params REQUIRED set is exactly `["cwd"]`; `mcpServers` and `additionalDirectories` are optional arrays | MUST | `schema/v2/schema.json:6048`, `:6014-6040` |
| S2 | `cwd` **MUST** be an absolute path, **MUST** be used regardless of spawn dir, **MUST** be the base for relative paths, **MUST** be in the session root set | MUST | `docs/protocol/v2/session-setup.mdx:319-322`; `schema/v2/schema.json:6016` |
| S3 | The Agent **MUST** respond to `session/new` with a **unique** Session ID | MUST | `docs/protocol/v2/session-setup.mdx:69`, `:306` |
| S4 | `session/new` response REQUIRED set is exactly `["sessionId"]`; `SessionId` is a plain `string` | MUST | `schema/v2/schema.json:3655`, `:596-599` |
| S5 | The Agent **MAY** return `configOptions` in the `session/new` result; `modes` no longer exists in v2 | MAY | `docs/protocol/v2/session-config-options.mdx:10`; `schema/v2/schema.json:3639-3647`; `docs/protocol/v2/migration.mdx:598` |
| S6 | Agents **SHOULD** connect to all MCP servers specified by the Client | SHOULD | `docs/protocol/v2/session-setup.mdx:469` |
| E1 | Agents **MUST NOT** request an elicitation mode the Client has not advertised; an unadvertised mode produces `-32602` | MUST NOT (agent) | `docs/protocol/v2/elicitation.mdx:54`, `:166-167` |
| E2 | `capabilities.elicitation` present but `{}` advertises **no** modes; each mode must be explicitly non-null | MUST (encoding) | `docs/protocol/v2/elicitation.mdx:40-52`; `docs/protocol/v2/initialization.mdx:131-139` |
| E3 | Implementations **MUST NOT** add custom fields at the root of a spec type; custom methods **MUST** start with `_` | MUST | `docs/protocol/v2/extensibility.mdx:39`, `:43`, `:52` |
| X1 | The agent **MUST NOT** write anything to stdout that is not a valid ACP message | MUST | `docs/protocol/v2/transports.mdx:27` |

**The general "advertise ⇒ implement" rule.** There is **no single sentence** in v2 saying "an implementation that advertises a capability MUST implement the gated surface." The obligation is carried per-capability, in two forms: (a) *definitional* — "Supplying `{}` means the Agent supports X" (`initialization.mdx:149-155,165-199,207-240`), and (b) *explicit MUST* for the three baseline session methods and the two auth methods (C2/C3/C4/A1). Practically this is a **MUST** for every capability: `initialization.mdx:104` makes omission mean "unsupported", so the only reason to include the key is to claim support, and `session-delete.mdx:57` etc. tell Clients they may then call the method. I recommend the TCK treat *advertised ⇒ must work* as MUST (matching the existing `CAPABILITY` tier), and cite (a)+(b) rather than a nonexistent global rule.

---

## Details

### 1. `initialize` request (client → agent)

`$def InitializeRequest`, `schema/v2/schema.json:5801-5841`. `x-side: "agent"`, `x-method: "initialize"`. `"required": ["protocolVersion", "info"]` (`:5838`).

| Field | Req? | Type / `$def` | Lines | Notes |
|---|---|---|---|---|
| `protocolVersion` | **REQUIRED** | `ProtocolVersion` = integer, `uint16`, 0..65535 | `:5805-5811`, `:3090-3096` | Byte-identical to v1's `ProtocolVersion`. |
| `info` | **REQUIRED** | `Implementation` | `:5813-5819`, `:3097-3122` | v1's `clientInfo` was optional+nullable. `required: ["name","version"]`; `title` is `["string","null"]`. |
| `capabilities` | optional, `default: {}` | `ClientCapabilities` | `:5821-5829`, `:5842-5877` | Not nullable in the schema (it is an `allOf` `$ref`, no `"null"` branch) — send `{}`, not `null`. |
| `_meta` | optional | `["object","null"]`, `additionalProperties: true` | `:5831-5836` | |

**`ClientCapabilities` — the complete v2 client capability surface** (`:5842-5877`): exactly `auth`, `elicitation`, `_meta`. Nothing else. No `fs`, no `terminal`, no `session.configOptions.boolean`.

| Path | `$def` | Lines | Encoding | Gates |
|---|---|---|---|---|
| `capabilities.auth` | `AuthCapabilities` | `:5846-5857`, `:5878-5901` | object-or-`null` container; only defined child is `terminal` | nothing by itself |
| `capabilities.auth.terminal` | `TerminalAuthCapabilities` | `:5882-5893`, `:5902-5913` | object marker (`{}` = supported) | the Agent may advertise `authMethods[*].type == "terminal"` (A3) |
| `capabilities.elicitation` | `ElicitationCapabilities` | `:5858-5869`, `:5914-5949` | object-or-`null` container | **nothing by itself** — `{}` advertises *no* modes |
| `capabilities.elicitation.form` | `ElicitationFormCapabilities` | `:5918-5929`, `:5950-5961` | object marker | agent may send `elicitation/create` in form mode |
| `capabilities.elicitation.url` | `ElicitationUrlCapabilities` | `:5930-5941`, `:5962-5973` | object marker | agent may send `elicitation/create` in URL mode, and `elicitation/complete` |
| `capabilities._meta` (and `_meta` on each nested object) | — | `:5870-5875`, `:5894-5899`, `:5906-5911`, `:5942-5947`, `:5954-5959`, `:5966-5971` | free-form | custom capabilities (`extensibility.mdx:124-146`) |

**Is `migration.mdx:191` or the schema authoritative?** The schema and `initialization.mdx:113-139` / `authentication.mdx:127-154` / `elicitation.mdx:24-55`. `migration.mdx:191` ("Stable v2 currently defines no standard Client capability fields") was written in `dc3a0a1`, 2026-07-08 — *before* `2c66dec` "stabilize elicitation" (2026-07-24) and `4effcc1` "stabilize terminal authentication" (2026-08-20). It is stale prose that nobody updated. **The TCK must treat `capabilities.auth.terminal`, `capabilities.elicitation.form`, and `capabilities.elicitation.url` as real, stable v2 client capabilities** and must *not* generate any requirement from `migration.mdx:191`.

**What the TCK mock client must send.** Minimal valid v2 `initialize` params:

```json
{"protocolVersion": 2, "info": {"name": "acp-tck", "version": "<tck version>"}}
```

For the default conformance run — and specifically for the MANDATORY negative tests — send `capabilities` explicitly as `{}` so that "omitted means unsupported" (I8) is unambiguous on the wire and the transcript shows what was claimed:

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{
  "protocolVersion": 2,
  "info": {"name": "acp-tck", "title": "ACP TCK", "version": "…"},
  "capabilities": {}
}}
```

Variants the suite needs:
- **Terminal-auth negative control (A3):** `capabilities: {}` — no `auth.terminal`. Then assert no `authMethods[*].type == "terminal"`.
- **Elicitation negative control (E1):** `capabilities: {}`. Then assert no `elicitation/create` is ever received.
- **Elicitation positive path (later slice):** `capabilities: {"elicitation": {"form": {}, "url": {}}}`.
- **Never send** `capabilities: {"elicitation": {}}` expecting form support — `elicitation.mdx:47-52` explicitly says `{}` advertises no modes ("Unlike MCP, ACP does not treat `{}` as form support").
- `title` is optional; `name` and `version` are not. A v1-style `clientCapabilities`/`clientInfo` key is a root-level unknown field on a spec type and violates `extensibility.mdx:39`.

### 2. `initialize` response (agent → client)

`$def InitializeResponse`, `schema/v2/schema.json:3040-3089`. `"required": ["protocolVersion", "info"]` (**`:3086`** — this is the confirmation asked for).

| Field | Req? | Type / `$def` | Lines | Notes |
|---|---|---|---|---|
| `protocolVersion` | **REQUIRED** | `ProtocolVersion` (uint16) | `:3044-3051` | negotiated value; see the negotiation report |
| `info` | **REQUIRED** | `Implementation` (`name`+`version` required) | `:3052-3058`, `:3097-3122` | v1's `agentInfo` was optional ⇒ this is a **tier upgrade** from ADVISORY to MANDATORY |
| `capabilities` | optional, `default: {}` | `AgentCapabilities` | `:3060-3068`, `:3123-3158` | not nullable |
| `authMethods` | optional, **no default** | `AuthMethod[]` | `:3070-3078` | omitted ≡ empty ≡ "no auth surface" |
| `_meta` | optional | `["object","null"]` | `:3079-3084` | |

**`AgentCapabilities` — complete enumeration.** Root has exactly `session`, `auth`, `_meta` (`:3123-3158`).

| JSON path | `$def` | Lines | Encoding | Gates | Absence means |
|---|---|---|---|---|---|
| `capabilities.session` | `SessionCapabilities` \| `null` | `:3127-3138`, `:3159-3218` | **object marker** — present & non-null ⇒ supported; `{}` counts | the 7-method session baseline: `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, `session/update` | agent does not support the `session/*` surface at all |
| `capabilities.session.prompt` | `PromptCapabilities` \| `null` | `:3163-3174`, `:3219-3266` | object container | nothing itself; holds the three content markers | no prompt extensions beyond baseline text + resource_link |
| `capabilities.session.prompt.image` | `PromptImageCapabilities` | `:3223-3234`, `:3267-3278` | object marker | `ContentBlock::Image` allowed in `session/prompt` | unsupported |
| `capabilities.session.prompt.audio` | `PromptAudioCapabilities` | `:3235-3246`, `:3279-3290` | object marker | `ContentBlock::Audio` in prompts | unsupported |
| `capabilities.session.prompt.embeddedContext` | `PromptEmbeddedContextCapabilities` | `:3247-3258`, `:3291-3302` | object marker | `ContentBlock::Resource` in prompts | unsupported |
| `capabilities.session.mcp` | `McpCapabilities` \| `null` | `:3175-3186`, `:3303-3338` | object container | nothing itself | no MCP transport support advertised |
| `capabilities.session.mcp.stdio` | `McpStdioCapabilities` | `:3307-3318`, `:3339-3350` | object marker | `McpServer` entries with `type: "stdio"` | unsupported (`session-setup.mdx:465`) |
| `capabilities.session.mcp.http` | `McpHttpCapabilities` | `:3319-3330`, `:3351-3362` | object marker | `McpServer` entries with `type: "http"` | unsupported (`session-setup.mdx:466`) |
| `capabilities.session.delete` | `SessionDeleteCapabilities` | `:3187-3198`, `:3363-3374` | object marker | `session/delete`; Clients **MUST NOT** call it otherwise | unsupported (`session-delete.mdx:57`) |
| `capabilities.session.additionalDirectories` | `SessionAdditionalDirectoriesCapabilities` | `:3199-3210`, `:3375-3386` | object marker | `additionalDirectories` on session lifecycle requests, and `SessionInfo.additionalDirectories` in `session/list` | unsupported; Clients **MUST only** send it when advertised (`session-setup.mdx:302`) |
| `capabilities.session._meta` | — | `:3211-3216` | free-form | custom session extensions | — |
| `capabilities.auth` | `AgentAuthCapabilities` \| `null` | `:3139-3150`, `:3387-3398` | object container whose **only** property is `_meta` | **nothing** — explicitly orthogonal to `authMethods`; does *not* advertise `auth/login`/`auth/logout` | no auth extensions advertised |
| `capabilities._meta` | — | `:3151-3156` | free-form | custom capabilities | — |

There are **no boolean-encoded capabilities anywhere in v2** (`migration.mdx:181`). A v2 agent that sends `"image": true` is schema-invalid, because `PromptImageCapabilities` is `type: "object"`. Likewise `"session": true` fails the `anyOf[SessionCapabilities, null]`. This means the existing plugin's `capability_is_supported(..., boolean=True)` mode is **never needed for v2** — every v2 gate is the default object-marker mode.

**"Absence has defined meaning."** Yes, twice over: globally at `initialization.mdx:104` ("Clients and Agents **MUST** treat all capabilities omitted in the `initialize` request as **UNSUPPORTED**") and per-field in every description ("Omitted or `null` both mean the agent does not advertise support"). Note the global sentence literally says "in the `initialize` request"; the per-field descriptions carry the same rule for the response, so the response side rests on the field descriptions, not on that sentence.

### 3. Auth surface in `initialize`

`authMethods` keeps its v1 name and location (`InitializeResponse.authMethods`, `schema/v2/schema.json:3070-3078`) but is no longer `default: []` — it is simply optional, and *omitted ≡ empty* for availability purposes (`migration.mdx:177`).

`AuthMethod` (`:3399-3494`) is a **tagged union with a required `type` discriminator** and an open fallback:

| Variant | `type` | Required fields | Extra | Lines |
|---|---|---|---|---|
| agent | `"agent"` | `methodId`, `name` | `description?` (nullable), `_meta?` | `:3418-3433`, `:3569-3598` |
| terminal | `"terminal"` | `methodId`, `name` | `description?`, `args?: string[]`, `env?: EnvVariable[]`, `_meta?` | `:3402-3417`, `:3521-3568` |
| other (open fallback) | any other string | `type`, `methodId`, `name` | `additionalProperties: true`, plus a `not` clause excluding the two known `type`s | `:3434-3493` |

v1→v2 renames: `id` → `methodId`; `type` went from optional (defaulting to `agent`) to **required**. `AuthMethodId` is a plain string (`:3496-3499`).

**Availability rules** (this is the whole v2 auth gate — there is no capability marker):
- non-empty `authMethods` ⇒ the Agent **MUST** implement **both** `auth/login` and `auth/logout` (`initialization.mdx:78`; `authentication.mdx:51-54`; `overview.mdx:54`; `migration.mdx:198`; `schema/v2/schema.json:3071`, `:5975-5976`).
- omitted or empty ⇒ Clients **MUST NOT** call either.
- `capabilities.auth` is explicitly *not* the gate (`initialization.mdx:80,157-161`; `schema/v2/schema.json:3140`, `:3388`). v1's `agentCapabilities.auth.logout` marker is gone.
- `terminal`-type methods are additionally client-gated on `capabilities.auth.terminal` (A3), and the Client **MUST NOT** send `auth/login` for one (A5) — it relaunches the agent program instead (`authentication.mdx:195-216`).

Wire shapes: `auth/login` params `{methodId}` (`LoginAuthRequest`, `:5974-5996`, `required: ["methodId"]`); `auth/logout` params `{}` (`LogoutAuthRequest`, `:5997-6010`, no required fields). Both responses are all-optional objects carrying only `_meta` (`LoginAuthResponse` `:3599-3612`, `LogoutAuthResponse` `:3613-3626`); the docs show `"result": {}` for both (`authentication.mdx:182-190`, `:234-242`).

**`-32000` in v2.** The code and name are unchanged from v1 (`schema/v2/schema.json:4150-4215`; `agent-client-protocol-schema/src/v2/error.rs` is byte-identical to v1's per the delta report). Its only normative footprint in the initialize/baseline contract is:
- `session/new` "May return an `auth_required` error if the agent requires authentication" (`docs/protocol/v2/schema.mdx:428`; source `agent-client-protocol-schema/src/v2/agent.rs:5169`). **MAY**, not MUST.
- After a successful `auth/login` the Client can create sessions "without receiving an `auth_required` error" (`authentication.mdx:192-193`; `schema.mdx:32-33`).
- After `auth/logout`, active sessions may start returning `auth_required`; the protocol guarantees nothing (`authentication.mdx:247-255`).
- Notably, **stable** `docs/protocol/v2/session-setup.mdx` does *not* mention `auth_required` at all; only `docs/protocol/v2/draft/session-setup.mdx:10` does. So the `session/new`-may-be-auth-gated statement rests on the generated schema doc, not on the session-setup page.

**Deferred to the later auth slice** (I did not research these): the `auth/login` error taxonomy, what a Client should do on a failed login, terminal-auth reconnect mechanics (`authentication.mdx:195-216`), the `args`/`env` semantics of `AuthMethodTerminal`, and whether logout must invalidate anything observable.

### 4. Baseline method set

#### 4.1 Agent-side (client → agent)

`schema/v2/meta.json:3-15` lists 11 agent methods. Only `initialize` is unconditional.

| Method | Kind | Baseline vs gate | Citation |
|---|---|---|---|
| `initialize` | request | **unconditional MUST** | `docs/protocol/v2/initialization.mdx:24,47`; `schema/v2/meta.json:4` |
| `auth/login` | request | gate: `authMethods` non-empty ⇒ MUST | `initialization.mdx:78`; `authentication.mdx:51-54`; `schema/v2/schema.json:5975-5976` |
| `auth/logout` | request | gate: `authMethods` non-empty ⇒ MUST | same |
| `session/new` | request | gate: `capabilities.session` present ⇒ MUST | `initialization.mdx:149-155,165-167`; `schema/v2/schema.json:3160` |
| `session/list` | request | gate: `capabilities.session` present ⇒ MUST | `session-list.mdx:10`; `initialization.mdx:152`; `migration.mdx:190` |
| `session/resume` | request | gate: `capabilities.session` present ⇒ MUST | `session-setup.mdx:83-84`; `initialization.mdx:152` |
| `session/close` | request | gate: `capabilities.session` present ⇒ MUST | `session-setup.mdx:237`; `initialization.mdx:153` |
| `session/prompt` | request | gate: `capabilities.session` present ⇒ MUST | `initialization.mdx:153`; `migration.mdx:190` |
| `session/cancel` | **notification** | gate: `capabilities.session` present ⇒ MUST | `initialization.mdx:154`; `overview.mdx:118-124` |
| `session/delete` | request | gate: `capabilities.session.delete` | `session-delete.mdx:35,57`; `schema/v2/schema.json:3187-3198` |
| `session/set_config_option` | request | **UNSPECIFIED — see below** | `schema/v2/meta.json:7`; `session-config-options.mdx:211-262` |
| `$/cancel_request` | protocol notification | MAY — "free to ignore" | `schema/v2/schema.json:440`, `:7001-7022`; `meta.json:22-24` |

**The `session/set_config_option` gap, stated exactly.** What the spec *says*: the method exists (`schema/v2/meta.json:7`; `$def`s `SetSessionConfigOptionRequest` `schema/v2/schema.json:6424-6530`, required `["sessionId","configId"]`, plus `type`/`value`; `SetSessionConfigOptionResponse` `:4073-4096`, required `["configOptions"]`); Clients change values by calling it (`session-config-options.mdx:211`); and "The Agent **MUST** respond with the complete list of all configuration options and their current values" (`session-config-options.mdx:262`). What the spec **does not say**: anything about when the method is available. It has **no capability marker** anywhere in `AgentCapabilities`/`SessionCapabilities`; it is **absent** from every baseline enumeration — `overview.mdx:52-124` (the "Baseline Methods" list), `initialization.mdx:149-155` and `:165-167` (the `session: {}` commitment), `SessionCapabilities`'s own description (`schema/v2/schema.json:3160`), and `migration.mdx:190`. `migration.mdx:50` says only "Unchanged". The only indirect signal is `session-config-options.mdx:10`: the Agent **MAY** return `configOptions` at session setup, and `:197` says Agents **MUST** always provide a default value "even if … The Client doesn't support configuration options" — which implies config options are optional end to end. **Conclusion:** the availability rule for `session/set_config_option` is genuinely unstated upstream. The defensible TCK reading is the one the v1 suite already uses for modes/config: *infer* support from `configOptions` being present and non-empty in the `session/new` response, and skip otherwise (`capability="inferred:configOptions"`). Do **not** treat it as part of the `capabilities.session` baseline — no upstream list includes it.

#### 4.2 Client-side (agent → client) — what an *agent* may call

`schema/v2/meta.json:16-21` lists exactly 4 client methods. v1's `fs/read_text_file`, `fs/write_text_file`, `terminal/create`, `terminal/output`, `terminal/release`, `terminal/wait_for_exit`, `terminal/kill` **do not exist in v2** (`migration.mdx:53-54,628-637`; absent from `schema/v2/meta.json` and from `AgentRequest`'s params union, `schema/v2/schema.json:484-513`).

| Method | Kind | Gate | Citation |
|---|---|---|---|
| `session/request_permission` | request | **client baseline — always available**, no capability | `overview.mdx:130-138`; `schema/v2/schema.json:545-595` (`required: ["sessionId","title","options"]`) |
| `session/update` | notification | client baseline (agent must send it as part of `capabilities.session`) | `overview.mdx:160-172`; `initialization.mdx:154`; `schema/v2/schema.json:4269-4299` |
| `elicitation/create` | request | capability: `capabilities.elicitation.form` and/or `.url`; agent **MUST NOT** request an unadvertised mode | `overview.mdx:140-148`; `elicitation.mdx:40-55`; `schema/v2/schema.json:2066-2175` |
| `elicitation/complete` | notification | MAY, only after a URL-mode elicitation the client advertised | `elicitation.mdx:155-164`; `overview.mdx:152-158`; `schema/v2/schema.json:5643-5665` |
| `_`-prefixed extension methods | request/notification | MAY; **MUST** start with `_` | `extensibility.mdx:43,52,97` |

**The v2 equivalent of the v1 "MUST NOT call `fs/*`/`terminal/*` unadvertised" rule set.** There are two rules, and only one of them is written down as such:

1. **Written:** "Agents **MUST NOT** request a mode the Client has not advertised" (`elicitation.mdx:54`), reinforced by "If the Client does not support URL mode, the Agent **MUST NOT** fall back to form mode" (`:110-111`) and "Requests using a mode the Client has not advertised produce JSON-RPC `-32602`" (`:166-167`). Since `capabilities: {}` advertises **no** elicitation at all (`elicitation.mdx:42-43`), a v2 agent sending *any* `elicitation/create` to a client that sent `capabilities: {}` violates this. This is the direct successor of v1's `ACP-CLIENTCAP-003`.
2. **Derived, not written:** there is no sentence saying "a v2 agent MUST NOT call `fs/read_text_file`". The normative hooks are `extensibility.mdx:52` ("implementations **MAY** expose and call custom JSON-RPC requests **as long as their name starts with an underscore**") and `overview.mdx:191` / `extensibility.mdx:116` ("unknown values that do not begin with `_` are reserved for future ACP variants"; the latter is scoped to enum/union values, not method names). Combining them: a request whose method is neither in `schema/v2/meta.json:clientMethods` nor `_`-prefixed is not a legal thing for a v2 agent to send. **I classify this as a derived MUST, medium confidence** — call it out as derived in the requirement text. It cleanly subsumes v1's `ACP-CLIENTCAP-001` (fs) and `-002` (terminal) into one stronger, unconditional rule (no "unadvertised" qualifier is needed — the methods simply do not exist).

Practical consequence for `_helpers.run_prompt`'s v2 twin: the v1 mock client answers unexpected agent→client requests with `-32601`. For v2, `-32601` remains correct for an unknown/removed method (`extensibility.mdx:80-91`), but for an `elicitation/create` in an unadvertised **mode** the spec prescribes `-32602` (`elicitation.mdx:166-167`). Both should be recorded on `client_requests_seen` either way.

### 5. `session/new` minimal contract

**Params** — `NewSessionRequest`, `schema/v2/schema.json:6011-6051`, `"required": ["cwd"]` (`:6048`):

| Field | Req? | Type | Lines | Notes |
|---|---|---|---|---|
| `cwd` | **REQUIRED** | `AbsolutePath` (plain `string`, `:1773-1776`) | `:6015-6022` | absoluteness is a prose MUST (`session-setup.mdx:319`), **not** schema-enforced |
| `additionalDirectories` | optional | `AbsolutePath[]` | `:6023-6031` | only send when `capabilities.session.additionalDirectories` is advertised (`session-setup.mdx:302`) |
| `mcpServers` | **optional in v2** (was required in v1) | `McpServer[]` | `:6032-6040` | omitting ≡ `[]` (`migration.mdx:598`). Only send entries whose transport the agent advertised (`session-setup.mdx:440`) |
| `_meta` | optional | `["object","null"]` | `:6041-6046` | |

Minimal valid v2 `session/new` for the TCK — *omit* `mcpServers` entirely (this is the cleanest v2-vs-v1 difference and avoids the MCP-capability check):

```json
{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"/abs/path"}}
```

**Response** — `NewSessionResponse`, `:3627-3658`, `"required": ["sessionId"]` (`:3655`):

| Field | Req? | Type | Lines |
|---|---|---|---|
| `sessionId` | **REQUIRED** | `SessionId` = plain `string` (`:596-599`) | `:3631-3638` |
| `configOptions` | optional | `SessionConfigOption[]` (`:3659-3771`) | `:3639-3647` |
| `_meta` | optional | `["object","null"]` | `:3648-3653` |

`modes` **does not exist** in v2 (`migration.mdx:598`; not a property of `NewSessionResponse`). The `SessionConfigOption` entries carry `configId` (not `id`), `name`, `type` (`"select"`/`"boolean"`/open fallback), `currentValue`, optional `category`, and `options`/`groupId` for selects (`schema/v2/schema.json:3659-3932`; `session-config-options.mdx:71-135`). Presence is purely the Agent's choice — "**MAY** return a list" (`session-config-options.mdx:10`).

**Uniqueness.** "The Agent **MUST** respond with a unique Session ID that identifies this conversation" (`session-setup.mdx:69`), restated at `:306` and in the `SessionId` `$def` description (`:597`). Same strength as v1 — this is a real MUST in prose, unenforceable by schema. Two `session/new` calls on one connection returning the same id violates it.

**Error behavior.** The only documented failure mode of `session/new` in v2 is `auth_required` (`-32000`) when the agent requires authentication (`docs/protocol/v2/schema.mdx:428`) — and that is a **MAY**, not a MUST. Nothing else is specified: no error is defined for a relative `cwd`, an unadvertised MCP transport, or an unadvertised `additionalDirectories`. Those are all framed as Client MUSTs, with no stated agent-side reaction. A v2 TCK therefore cannot assert on any of them from the client side (see Testability notes).

### 6. Schema-validation notes for a v2 validator

**Top-level layout.** `schema/v2/schema.json:4-462` is an `anyOf` of **7** branches (v1 had 3):

| # | `title` | Lines | Shape | Sub-branches |
|---|---|---|---|---|
| 1 | `Agent` | `:5-42` | object, `required: ["jsonrpc"]` | `Request` → `$defs/AgentRequest`; `Response` → `$defs/AgentResponse`; `Notification` → `$defs/AgentNotification` |
| 2 | `Client` | `:43-80` | object | `Request` → `ClientRequest`; `Response` → `ClientResponse`; `Notification` → `ClientNotification` |
| 3 | `AgentBatchCall` | `:81-123` | **array**, `minItems: 1` | items: `Request`/`Notification`/`ProtocolLevelNotification` |
| 4 | `AgentBatchResponse` | `:124-287` | **array**, `minItems: 1` | items: `Result` (inlined `{id, result}` with the 11-member agent result union) / `Error` (`{id, error}`) |
| 5 | `ClientBatchCall` | `:288-330` | **array**, `minItems: 1` | items: `ClientRequest`/`ClientNotification`/`ProtocolLevelNotification` |
| 6 | `ClientBatchResponse` | `:331-422` | **array**, `minItems: 1` | items: `Result` (3-member client result union) / `Error` |
| 7 | `ProtocolLevel` | `:423-461` | object, `required: ["jsonrpc","method"]` | `$/cancel_request` |

**Naming convention is unchanged from v1:** `Agent*` = *authored by the Agent*. So `AgentRequest` (`:464-523`) holds the agent→client requests (`RequestPermissionRequest`, `CreateElicitationRequest`, `ExtMethodRequest`), `AgentResponse` (`:2890-3039`) holds the agent's responses to the 10 client→agent requests, and `AgentNotification` (`:4217-4268`) holds `UpdateSessionNotification`, `CompleteElicitationNotification`, `ExtNotification`. `ClientNotification` (`:6901-6943`) holds `CancelSessionNotification` + `ExtNotification`. Meanwhile `x-side` means *the side that implements/handles the method* — hence `UpdateSessionNotification` carries `x-side: "client"` while living under `AgentNotification`. The v1 validator's derivation already relies on exactly this split, so it transfers unchanged.

**How a line is recognized.** Same dispatch as v1, plus one new case:
1. If the parsed line is a **JSON array** → it is a batch (branches 3-6); recognize the direction by whether the items are calls (`method` present) or responses (`result`/`error` present). Array lines are new in v2 and must not be rejected by a v1-style "must be an object" check.
2. Object with `method` + `id` → request. Object with `method`, no `id` → notification. `method` starting with `$/` → protocol level (branch 7).
3. Object without `method` → response; `required: ["id","result"]` or `["id","error"]`. As in v1, picking the right `result` schema requires knowing which request it answers, so a v2 `validate_agent_response(method, msg)` is still needed.

**`x-side`/`x-method` coverage: complete.** 28 annotated `$def`s. Every one of the 16 methods in `schema/v2/meta.json` is annotated: 10 agent-side requests × 2 (params + response) + `session/cancel` (notification, 1) = 21; 2 client-side requests × 2 + `session/update` + `elicitation/complete` = 6; `$/cancel_request` = 1. Verified by enumeration (`schema/v2/schema.json` lines 593-594, 2173-2174, 3087-3088, 3610-3611, 3624-3625, 3656-3657, 3966-3967, 4033-4034, 4056-4057, 4070-4071, 4094-4095, 4117-4118, 4297-4298, 5663-5664, 5839-5840, 5994-5995, 6008-6009, 6049-6050, 6248-6249, 6271-6272, 6332-6333, 6421-6422, 6528-6529, 6558-6559, 6659-6660, 6850-6851, 6964-6965, 7021-7022). `ExtRequest`/`ExtResponse`/`ExtNotification` carry no annotation, as in v1. **The `tck.protocol` derivation strategy works unchanged for v2** — `meta.json` has the same `{version, agentMethods, clientMethods, protocolMethods}` shape with `"version": 2` (`schema/v2/meta.json:1-25`).

**`null` in place of an empty-object response: v2 permits it nowhere.** Every agent-side response `$def` is `"type": "object"` with no `"null"` branch and no outer `anyOf` — checked for all ten: `InitializeResponse`, `LoginAuthResponse`, `LogoutAuthResponse`, `NewSessionResponse`, `ListSessionsResponse`, `DeleteSessionResponse`, `ResumeSessionResponse`, `CloseSessionResponse`, `SetSessionConfigOptionResponse`, `PromptResponse`. No v2 doc example shows `"result": null` (grepped all of `docs/protocol/v2/`); `auth/login`, `auth/logout` and `session/close` all show `"result": {}` (`authentication.mdx:188,240`; `session-setup.mdx:265-267`). **The v1 validator's `session/load` → `null` special case has no v2 counterpart and should not be carried over** — `session/load` does not exist in v2, and keeping the special case would silently accept a shape the v2 schema rejects.

**All-optional response `$def`s in v2** (the class the v1 validator special-cased): `LoginAuthResponse` (`:3599-3612`), `LogoutAuthResponse` (`:3613-3626`), `DeleteSessionResponse` (`:4022-4035`), `ResumeSessionResponse` (`:4036-4058`, properties `configOptions`, `_meta`), `CloseSessionResponse` (`:4059-4072`). All five must be sent as `{}` (or with their optional fields), **not** `null`.

**`additionalProperties: false`: zero occurrences in `schema/v2/schema.json`** (same as v1; 125 occurrences of `additionalProperties: true`, all on `_meta` and the open-fallback union branches). So the schema still cannot reject an unknown root key on a spec type, and `extensibility.mdx:39`'s MUST NOT still needs the hand-written `find_unknown_root_keys` check. Its `_allowed_root_properties` walker must additionally handle the v2 pattern where a union branch declares `properties.type` + `allOf: [{$ref: …}]` (e.g. `AuthMethod`, `:3402-3433`) — that shape does not appear in v1's `AuthMethod`.

**Open-union caveat inherited from the delta report** (not re-derived here): `StopReason`'s fallback branch (`:4869`) is a bare `{"type":"string"}` with no `not` guard, so value checks must be done in Python. This does not affect `initialize`/`session/new`, but it does affect `AuthMethod.type` — there the fallback *does* carry a `not` clause (`:3468-3491`), so schema validation correctly rejects an `agent`/`terminal` payload missing `methodId`/`name`.

### 7. Candidate v2 requirement rows

**Id scheme.** v1 and v2 requirements will live in one registry, so ids must not collide. I suggest keeping the `ACP-<AREA>-<NNN>` regex and reserving the **200-series** for v2 (`ACP-INIT-201`, …), which keeps `tests/test_registry.py`'s invariants and the id parser untouched. (Alternative, if the orchestrator prefers an explicit marker: `ACP2-<AREA>-<NNN>` — but that changes the id shape.) Every row is additionally gated on the run having negotiated `protocolVersion: 2`; a v1-only agent must SKIP, never FAIL (per the delta report's S1/S5).

| Id | Text | Tier | Origin | Citation | Conforming vs non-conforming fixture |
|---|---|---|---|---|---|
| `ACP-INIT-201` | `initialize` with `{protocolVersion: 2, info: {...}}` succeeds and the result validates against the vendored v2 schema, with an integer `protocolVersion`. | MANDATORY | (a) = `ACP-INIT-001` re-cited (request shape changed) | `docs/protocol/v2/initialization.mdx:47`; `schema/v2/schema.json:3040-3089` | **Conforming:** returns `{protocolVersion:2, info:{name,version}, capabilities:{session:{}}}`. **Non-conforming:** returns an error, or a result missing `protocolVersion`. |
| `ACP-INIT-202` | When the client requests protocol version 2, the agent returns 2. | MANDATORY (this *is* the v2 gate probe) | (b) changed from `ACP-INIT-002` | `docs/protocol/v2/initialization.mdx:94` | **Conforming:** echoes 2. **Non-conforming (→ whole v2 suite SKIPs, not FAILs):** returns 1. |
| `ACP-INIT-203` | Requesting an unsupported version (65535) with **v2-shaped params** returns a successful result whose `protocolVersion` is not 65535 and is ≥ the agent's answer to a `2` request. | MANDATORY | (a) = `ACP-INIT-003` re-cited; **the probe params must now include `info`** or a v2-capable router answers `-32602` | `docs/protocol/v2/initialization.mdx:94`; `schema/v2/schema.json:5838`; `.agents/research/acp-v2-version-negotiation.md` (router trap) | **Conforming:** answers 2. **Non-conforming:** echoes 65535 (both reference example agents do this in v1). |
| `ACP-INIT-204` | The `initialize` result contains `info` with non-empty string `name` and `version`. | **MANDATORY** | (b) changed — was ADVISORY `ACP-INIT-004` in v1; `info` is in `InitializeResponse.required` in v2 | `schema/v2/schema.json:3086`, `:3121`; `docs/protocol/v2/initialization.mdx:248` | **Conforming:** `info:{name:"x",version:"1.0"}`. **Non-conforming:** omits `info` (a one-line fixture change). |
| `ACP-INIT-205` | No capability value in the `initialize` result is a boolean; every advertised marker is an object or absent/`null`. | MANDATORY | (c) new in v2 | `docs/protocol/v2/migration.mdx:181`; `schema/v2/schema.json:3223-3234` etc. | **Non-conforming:** `capabilities:{session:{prompt:{image:true}}}` (the v1 encoding). Largely subsumed by `ACP-SCHEMA-201`; keep as a separate row only if a clearer diagnostic is wanted. |
| `ACP-SCHEMA-201` | Every message the agent emits during a basic v2 exchange validates against the vendored v2 schema (objects **and** batch arrays). | MANDATORY | (a) = `ACP-SCHEMA-001` re-cited; note the new array-valued top-level branches | `schema/v2/schema.json:4-462` | **Non-conforming:** any malformed field; reuse the v1 defect-fixture pattern. |
| `ACP-SCHEMA-202` | No unknown root-level keys on any agent-authored `params`/`result`. | ADVISORY | (a) unchanged; `additionalProperties:false` still absent in v2 | `docs/protocol/v2/extensibility.mdx:39`; 0 hits for `additionalProperties: false` in `schema/v2/schema.json` | **Non-conforming:** an agent that still sends `agentCapabilities`/`agentInfo` alongside the v2 names. |
| `ACP-SESSION-201` | With `capabilities.session` advertised, `session/new` with an absolute `cwd` and **no** `mcpServers` succeeds with a non-empty string `sessionId`, and the response validates. | **CAPABILITY** `capabilities.session` | (b) changed — MANDATORY in v1; in v2 `capabilities.session` is optional | `docs/protocol/v2/session-setup.mdx:69`; `schema/v2/schema.json:6048`, `:3655`; `docs/protocol/v2/initialization.mdx:165-167` | **Conforming:** `conforming_v2.py` advertising `session:{}`. **Non-conforming:** `advertises_session_but_errors_on_new.py`. |
| `ACP-SESSION-202` | Two `session/new` calls on the same connection return distinct `sessionId`s. | **CAPABILITY** `capabilities.session` | (b) changed tier, same requirement as `ACP-SESSION-002` | `docs/protocol/v2/session-setup.mdx:69,306` | **Non-conforming:** `duplicate_session_id_v2.py`. |
| `ACP-LIST-201` | With `capabilities.session` advertised, `session/list` succeeds and the result validates (`sessions` array present). | **CAPABILITY** `capabilities.session` | (b) changed — v1 gated on `agentCapabilities.sessionCapabilities.list` | `docs/protocol/v2/session-list.mdx:10`; `schema/v2/schema.json:3933-3968` (`required:["sessions"]`) | **Non-conforming:** advertises `session:{}` but answers `-32601` to `session/list` — the exact under-advertising case the coordinator asked about; under the correct reading this is a FAIL. |
| `ACP-RESUME-201` | With `capabilities.session` advertised, `session/resume` of a session just created on the same connection (no `replayFrom`) succeeds. | **CAPABILITY** `capabilities.session` | (b) changed — v1 gated on `…sessionCapabilities.resume`; deeper replay semantics deferred | `docs/protocol/v2/session-setup.mdx:83-84`; `schema/v2/schema.json:6274-6334` (`required:["sessionId","cwd"]`) | **Non-conforming:** `-32601` on `session/resume` while advertising `session:{}`. |
| `ACP-CLOSE-201` | With `capabilities.session` advertised, `session/close` of a live session succeeds. | **CAPABILITY** `capabilities.session` | (b) changed — v1 gated on `…sessionCapabilities.close` | `docs/protocol/v2/session-setup.mdx:237,258` | **Non-conforming:** `-32601` on `session/close`. |
| `ACP-DELETE-201` | When `capabilities.session.delete` is advertised, `session/delete` of a listed session succeeds. | CAPABILITY `capabilities.session.delete` | (a) same requirement as `ACP-DELETE-001`, new path | `docs/protocol/v2/session-delete.mdx:35,57` | As v1, with the new path. |
| `ACP-ADDDIRS-201` | When `capabilities.session.additionalDirectories` is advertised, `session/new` with an absolute `additionalDirectories` entry is accepted. | CAPABILITY `capabilities.session.additionalDirectories` | (a) same as `ACP-ADDDIRS-001`, new path | `docs/protocol/v2/session-setup.mdx:295-302`; `schema/v2/schema.json:6023-6031` | As v1. |
| `ACP-PROMPTCAP-201/202/203` | When `capabilities.session.prompt.{image,audio,embeddedContext}` is advertised, a prompt containing that content block is accepted. | CAPABILITY `capabilities.session.prompt.<key>` | (a) same as `ACP-PROMPTCAP-001/002/003`, new paths + object encoding | `docs/protocol/v2/initialization.mdx:207-226`; `schema/v2/schema.json:3219-3302` | As v1. |
| `ACP-AUTH-201` | When `authMethods` is present, entries' `methodId`s are unique. | ADVISORY | (b) changed field name (`id` → `methodId`); same ADVISORY rationale as v1 (`methodId` is described as "Unique identifier", not a MUST) | `schema/v2/schema.json:3526,3574` | **Non-conforming:** two entries with the same `methodId`. |
| `ACP-AUTH-202` | No `authMethods[*].type == "terminal"` entry is advertised unless the client advertised `capabilities.auth.terminal`. | MANDATORY | (a) same as `ACP-AUTH-002`, new client path; **stronger** citation in v2 (an explicit schema MUST) | `schema/v2/schema.json:3522`; `docs/protocol/v2/authentication.mdx:151-154` | **Non-conforming:** `terminal_auth_unadvertised_v2.py`. |
| `ACP-AUTH-203` | When `authMethods` is non-empty, `auth/logout` is implemented (no capability marker exists in v2). | CAPABILITY `inferred:authMethods` ⇒ MUST | (b) **changed** — v1 gated `logout` on `agentCapabilities.auth.logout`; v2 removes that marker and makes it mandatory | `docs/protocol/v2/initialization.mdx:78`; `docs/protocol/v2/authentication.mdx:51-54,220-223` | **Conforming:** advertises one `agent` method, implements both. **Non-conforming:** advertises `authMethods` but answers `-32601` to `auth/logout`. |
| `ACP-AUTH-204` | With `--auth-method <id>` naming an advertised `type: "agent"` method, `auth/login` returns an object result, and a subsequent `session/new` does not fail with `-32000`. | CAPABILITY `inferred:authMethods` | (b) changed — method renamed `authenticate` → `auth/login`, param `id` → `methodId`; assertion narrowed exactly as v1's `ACP-AUTH-003` | `schema/v2/schema.json:5974-5996`, `:3599-3612`; `docs/protocol/v2/authentication.mdx:160-193` | **Conforming:** `gated_by_auth_v2.py`. **Skip, don't fail**, if `auth/login` errors (bad credentials are legitimate). |
| `ACP-AUTH-205` | With no `authMethods` advertised, `session/new` does not fail with `-32000`. | ADVISORY | (a) same as `ACP-AUTH-005`; still not an explicit MUST in v2 | `schema/v2/schema.json:3070-3078` (optional); `docs/protocol/v2/schema.mdx:428` (MAY) | Same fixture story as v1. |
| `ACP-CLIENTCAP-201` | During a v2 prompt turn, the agent sends no client-bound request or notification whose method is neither a defined v2 client method nor `_`-prefixed — in particular no `fs/*` and no `terminal/*`. | MANDATORY (**derived** — see §4.2 rule 2) | (b) changed: merges `ACP-CLIENTCAP-001` + `-002`, drops the "unadvertised" qualifier | `schema/v2/meta.json:16-21`; `docs/protocol/v2/extensibility.mdx:43,52`; `docs/protocol/v2/migration.mdx:628-637` | **Non-conforming:** `calls_fs_v2.py`, `calls_terminal_v2.py` (port the v1 `SendsClientRequestAgent` base). |
| `ACP-CLIENTCAP-202` | Against a mock client sending `capabilities: {}`, the agent never sends `elicitation/create`. | MANDATORY | (a) same as `ACP-CLIENTCAP-003`, new path + the explicit `{}`-advertises-nothing rule | `docs/protocol/v2/elicitation.mdx:42-43,54` | **Non-conforming:** `calls_elicitation_unadvertised_v2.py`. |
| `ACP-CONFIG-201` | If `session/new`'s result carries `configOptions`, every entry validates (`configId`, `name`, `type`, `currentValue`). | CAPABILITY `inferred:configOptions` | (b) changed field names (`id`→`configId`, `group`→`groupId`) | `schema/v2/schema.json:3659-3932`; `docs/protocol/v2/session-config-options.mdx:71-135` | **Non-conforming:** emits the v1 `id` key. |
| `ACP-CONFIG-202` | `session/set_config_option` responds with the **complete** `configOptions` list. | CAPABILITY `inferred:configOptions` | (a) same as `ACP-CONFIG-002` | `docs/protocol/v2/session-config-options.mdx:262`; `schema/v2/schema.json:4073-4096` (`required:["configOptions"]`) | **Non-conforming:** `config_partial_list_v2.py`. **Availability gate is unstated upstream** (§4.1) — infer, don't assume baseline. |

**v1 ids in this area with NO v2 counterpart:**

| v1 id | Why it has no v2 counterpart | Citation |
|---|---|---|
| `ACP-LOAD-001`, `ACP-LOAD-002`, `ACP-LOAD-003` | `session/load` and `agentCapabilities.loadSession` were removed; replay moved onto `session/resume`'s `replayFrom` | `docs/protocol/v2/migration.mdx:42,189,574-594`; no `LoadSessionRequest`/`Response` in `schema/v2/schema.json` |
| `ACP-CONFIG-003` (no boolean option without `clientCapabilities.session.configOptions.boolean`) | the client capability it depends on does not exist in v2 — `ClientCapabilities` is `{auth, elicitation, _meta}` | `schema/v2/schema.json:5842-5877`; `docs/protocol/v2/migration.mdx:191` |
| `ACP-MODES-001`, `ACP-MODES-002` | `session/set_mode`, `modes` in `session/new`, and `current_mode_update` were all removed; modes are now ordinary `configOptions` with `category: "mode"` | `docs/protocol/v2/migration.mdx:49,72,598,606-608`; `docs/protocol/v2/session-config-options.mdx:165-181` |
| `ACP-AUTH-004` (logout gated on `agentCapabilities.auth.logout`) | that marker is deleted; replaced by `ACP-AUTH-203`'s "non-empty `authMethods` ⇒ MUST" | `docs/protocol/v2/migration.mdx:198`; `schema/v2/schema.json:3387-3398` |
| `ACP-RESUME-002` (resume MUST NOT replay) | still true in v2, but only for `replayFrom` omitted/`null`, and it now sits inside the replay contract — route to the `acp-v2-session-resume-and-replay` slice, not here | `docs/protocol/v2/session-setup.mdx:118-120,144` |
| `ACP-LIST-002`, `ACP-CLOSE-002`, `ACP-DELETE-002` | the underlying behaviours survive, but their v2 assertions depend on the redesigned prompt lifecycle / `SessionInfo` shape; deferred to the session-lifecycle slice | — |

---

## Testability notes

**How a v2 TCK asserts each class of requirement.**

- **v2 gate.** One `initialize` with `protocolVersion: 2` in a fresh process. If `result.protocolVersion != 2`, SKIP the whole v2 suite. Note the negotiation report's caveat: an agent that merely *echoes* the requested version is indistinguishable on that integer alone. A cheap corroborating shape check is available in v2 and not in v1: a genuine v2 agent's result has `info` (required) and, if it has any capabilities, object-valued markers. A v1 agent that echoes `2` will typically emit `agentCapabilities`/`agentInfo` — so "the result contains `agentCapabilities` or `agentInfo`, or lacks `info`" is a strong negative signal for a fake v2. Recommend recording it as an INFORMATIONAL probe rather than making `ACP-INIT-202` depend on it.
- **`info` required (`ACP-INIT-204`).** Pure schema check; catchable by `validate_agent_response("initialize", …)` alone. This is the cleanest new MANDATORY in v2.
- **Capability encoding (`ACP-INIT-205`).** Also pure schema — `"image": true` fails `type: "object"`. Keep the separate row only for diagnostic clarity.
- **`capabilities.session` ⇒ 7 methods (`ACP-SESSION-201/202`, `ACP-LIST-201`, `ACP-RESUME-201`, `ACP-CLOSE-201`).** The gate is `@pytest.mark.capability("capabilities.session")` in the **default object-marker mode** — `{}` must count as advertised. This is the single most consequential gating decision in the v2 suite and is exactly what the coordinator's question turns on; get it wrong in the "nested keys only" direction and `testy` v2 would SKIP all five instead of PASSing them.
- **Client-capability negatives (`ACP-CLIENTCAP-201/202`).** Same mechanism as v1: run a prompt turn against a mock client that sent `capabilities: {}` and assert on `PromptTurn.client_requests_seen`. Split per id (v1's review item 9) so one offending surface fails one id. Answer unexpected requests `-32601`, except an `elicitation/create` with an unadvertised mode, where `-32602` is what the spec prescribes (`elicitation.mdx:166-167`).
- **`authMethods` ⇒ `auth/logout` (`ACP-AUTH-203`).** Directly testable and needs no credentials: `auth/logout` takes `{}` and returns `{}`. Calling it is legal the moment `authMethods` is non-empty (`authentication.mdx:220-223`). A `-32601` is an unambiguous FAIL.
- **`auth/login` when all methods are `terminal`.** **Untestable.** The agent MUST implement `auth/login` (A1) but the Client MUST NOT call it for a terminal method (A5), and there is no non-terminal method to call it with. The TCK must SKIP `ACP-AUTH-204` with a distinct reason when every advertised method has `type: "terminal"`.
- **`session/new` uniqueness (`ACP-SESSION-202`).** Two calls, compare strings — same as v1, no change.

**A conforming minimal v2 fixture agent** (`conforming_v2.py`): answers `initialize` with `{protocolVersion: <requested if 2 else 2>, info:{name,version}, capabilities:{session:{}}}`; implements `session/new` (unique ids), `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, emits `session/update`; sends no `authMethods`; answers `-32601` to unknown methods; writes only ACP to stdout. A `conforming_v2_full.py` adds `session.prompt.{image,audio,embeddedContext}`, `session.mcp.{stdio,http}`, `session.delete`, `session.additionalDirectories`, one `agent`-type `authMethods` entry with `auth/login`+`auth/logout`, and `configOptions` in `session/new`.

**Non-conforming fixtures this area needs:** `no_info_v2.py` (omits `info`), `boolean_capability_v2.py` (`prompt:{image:true}`), `session_marker_no_list_v2.py` (advertises `session:{}`, `-32601` on `session/list` — the under-advertising case), `duplicate_session_id_v2.py`, `terminal_auth_unadvertised_v2.py`, `authmethods_no_logout_v2.py`, `calls_fs_v2.py`, `calls_terminal_v2.py`, `calls_elicitation_unadvertised_v2.py`, `v1_keys_in_v2_response.py` (emits `agentCapabilities`/`agentInfo` → trips `ACP-SCHEMA-202`).

**Unobservable from the client side, therefore untestable here:**
- Whether the agent *would have* honoured a capability it did not advertise — the TCK can only probe what is advertised.
- Every `cwd`/`additionalDirectories`/`mcpServers` validation rule: they are Client MUSTs with no defined agent-side reaction (§5). A TCK sending a relative `cwd` would be the one violating the spec, and the agent's response is undefined either way — do **not** write that test.
- Whether `session/new`'s `-32000` is *justified*: a real agent may legitimately require authentication. Reuse v1's `AUTH-GATED:` skip marker and `Verdict.blocked_by_auth` verbatim.
- Whether `capabilities.auth` (agent) "works" — it gates nothing and has no property but `_meta`. There is nothing to assert. Do not create a requirement for it.
- `session/set_config_option`'s availability (§4.1) — the spec does not define it, so neither a PASS nor a FAIL is honest for an agent that answers `-32601`. Infer from `configOptions` presence, or leave INFORMATIONAL.

---

## Discrepancies

1. **`AgentCapabilities.session` doc comment says 4 baseline methods; everything else says 7.** `schema/v2/schema.json:3128` (and its Rust source `agent-client-protocol-schema/src/v2/agent.rs:3947-3952`, mirrored in the rust-sdk's dependency on `agent-client-protocol-schema =1.9.1`) reads "Supplying `{}` means the agent supports the baseline session methods: `session/new`, `session/prompt`, `session/cancel`, and `session/update`." Against it: `SessionCapabilities`'s own description `schema/v2/schema.json:3160` and `agent-client-protocol-schema/src/v2/agent.rs:4138-4146`, `docs/protocol/v2/initialization.mdx:149-155` and `:165-167`, `docs/protocol/v2/migration.mdx:190`, `docs/protocol/v2/session-list.mdx:10`, `docs/protocol/v2/session-setup.mdx:83-84,237`, and the rust-sdk's `md/testy.md:81-83` — all seven methods. **Resolution: the 7-method reading is authoritative.** Three independent reasons: (i) `SessionCapabilities` has no `list`/`resume`/`close` properties (`schema/v2/schema.json:3159-3218` — only `prompt`, `mcp`, `delete`, `additionalDirectories`, `_meta`), so there is no alternative marker the 4-method reading could point at; (ii) `session-list.mdx:10` and `session-setup.mdx:83,237` are standalone normative MUSTs that do not depend on either doc comment; (iii) git history shows the 4-method text predates the change — it landed 2026-06-18 (`2b4fcab`) and the 7-method text landed 2026-07-02 (`a57b538`, "Unify session/load and session/resume"), which is precisely when `session/load` folded into `session/resume` and the per-method markers were dropped. Nobody updated the outer field's comment. **What the TCK should encode:** `capabilities.session` present-and-non-null ⇒ all seven of `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, `session/update` are required. `testy` v2 (`acp-rust-sdk src/agent-client-protocol-test/src/testy/v2.rs:394` advertises exactly `AgentCapabilities::new().session(SessionCapabilities::new())` = `{"session":{}}`, and `:407-484` handles `initialize`, `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`) is **correctly advertised**, not under-advertised. Worth reporting the stale comment upstream.
2. **`migration.mdx:191` denies that stable v2 has any client capability fields.** Contradicted by `schema/v2/schema.json:5842-5877` (`ClientCapabilities = {auth, elicitation, _meta}`), `docs/protocol/v2/initialization.mdx:113-139`, `docs/protocol/v2/authentication.mdx:127-154`, and `docs/protocol/v2/elicitation.mdx:24-55`. Dated evidence: `migration.mdx:191` was written in `dc3a0a1` (2026-07-08), elicitation stabilized in `2c66dec` (2026-07-24), terminal auth in `4effcc1` (2026-08-20). **Trust the schema and `initialization.mdx`.** (This confirms the delta report's Discrepancy 1 with commit dates.)
3. **`session/set_config_option` has no stated availability rule.** It is in `schema/v2/meta.json:7` with full `$def`s, but is absent from `overview.mdx:52-124`, `initialization.mdx:149-167`, `SessionCapabilities`'s description, and `migration.mdx:190`, and has no capability marker. `migration.mdx:50` says only "Unchanged". This is a genuine upstream gap, not an oversight I can resolve — see §4.1 for the exact wording on both sides.
4. **`auth_required` on `session/new` appears only in generated schema prose.** `docs/protocol/v2/schema.mdx:428` (generated from `agent-client-protocol-schema/src/v2/agent.rs:5169`) says `session/new` may return it; the hand-written **stable** `docs/protocol/v2/session-setup.mdx` never mentions authentication, while the **draft** layer `docs/protocol/v2/draft/session-setup.mdx:10` does. Low impact (it is a MAY either way), but a TCK writing `ACP-AUTH-205` should cite the generated doc and note the stable page's silence.
5. **Python SDK's `acp.experimental.v2` is generated from the *unstable* v2 schema, not stable v2.** Its `src/acp/experimental/v2/meta.py:3-20` lists `providers/list`, `providers/set`, `providers/disable`, `mcp/message`, `session/fork`, `nes/*` — none of which exist in `schema/v2/schema.json` (e.g. `ListProvidersResponse`: 0 occurrences in `schema.json`, 5 in `schema.unstable.json`). Its vendored `schema/v2/VERSION` is `refs/tags/schema-v2.0.0-alpha.5`. Consequence for a future v2 cross-check: the Python SDK is **not** a stable-v2 reference the way `echo_agent.py` is for v1; the Rust `testy` v2 (built with `unstable_protocol_v2`) is the closer match. Reported as an inventory fact — the SDK-status researcher owns the conclusion.
6. **No discrepancy found** on: `initialize` required arrays, `Implementation`, the client capability set, `AuthMethod` shape, `NewSessionRequest`/`NewSessionResponse` required sets, `SessionId` type, error codes, or `x-side`/`x-method` coverage. Docs, schema, and Rust models agree.

---

## Open questions

Adjacent unknowns for the orchestrator to route elsewhere — I did not pursue these:

1. **Is `session/set_config_option` baseline, capability-gated, or unspecified?** I established that upstream is silent (Discrepancy 3) and recommended an inferred gate. Whether to file an upstream issue, and what the config-options slice should assert, is a decision, not a research finding.
2. **What must a v2 `session/prompt` test assert, and how does the `messageId`/`state_update` split change `run_prompt`?** Route to the `acp-v2-prompt-lifecycle-and-state-updates` slice. I deliberately did not touch `PromptResponse` beyond noting `required: ["messageId"]` (`schema/v2/schema.json:4117`).
3. **`session/resume` + `replayFrom` replay ordering and `messageId` reuse.** Route to `acp-v2-session-resume-and-replay`. `ACP-RESUME-201` above asserts only "resume of a live session succeeds".
4. **JSON-RPC batching.** `schema/v2/schema.json:81-422` adds four array-valued top-level branches and `transports.mdx:45-80` adds ~8 rules. The only thing I settled here is that a v2 validator must accept array lines. Route to `acp-v2-jsonrpc-batching`.
5. **Should the v2 suite send `capabilities: {}` or omit `capabilities` entirely by default?** Both are valid (`schema/v2/schema.json:5821-5829`). I recommended explicit `{}` for transcript clarity, but if any agent's deserializer treats the two differently that is worth a cross-check probe.
6. **Elicitation positive-path testing.** Requires the TCK to actually implement a form/URL elicitation responder. Out of scope here; I only covered the negative gate.
7. **Does a v2 agent that omits `capabilities.session` have *any* testable surface?** `migration.mdx:188` says such agents are anticipated ("agents that only serve specialized extension surfaces") but adds "Currently there isn't protocol support for this". If the TCK meets one, every requirement above except `ACP-INIT-*`/`ACP-SCHEMA-*` SKIPs and the verdict would be near-vacuous. Worth an explicit product decision.
8. **Pinning policy for the moving v2 schema.** `schema-v2.0.0-alpha.5` is three days old at this revision and alpha.5 changed `PromptResponse` materially. Carried over from the delta report's open question 6.
