# What is ACP v2 upstream today, where does its material live, what is its maturity, and — at inventory level — what differs from v1?

**Sources checked:**
- `agent-client-protocol` (spec, source of truth) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`, 2026-09-21 10:46 UTC, branch `main` (pulled `d3c1dd7..8f76d6c` at the start of this run).
- `acp-rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5`, 2026-09-18 (already up to date) — *inventory-level only, another researcher owns SDK status*.
- `acp-python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64`, 2026-09-21 (already up to date) — *inventory-level only*.

**Confidence:** high for location/status/schema shape (read directly from the spec repo's own generated
artifacts, Cargo features, and docs navigation); **medium** for completeness of the delta table — it is
assembled from the upstream migration guide cross-checked against the two JSON schemas, but v2 is moving
(the `session/prompt` → `messageId` change landed 3 days before this report) and I did not read every one of
the ~19 v2 doc pages line by line.

---

## Answer

ACP v2 exists upstream today as a **published Draft**, not a stable protocol version. Its material lives in
four places in the spec repo: generated JSON Schema artifacts in `schema/v2/` (`schema.json`, `meta.json`,
plus `schema.unstable.json` / `meta.unstable.json`), prose in `docs/protocol/v2/**` (19 stable pages
including a 772-line `migration.mdx`, plus a `docs/protocol/v2/draft/` unstable layer), design intent in
`docs/rfds/v2/**` (12 RFDs), and Rust models in `agent-client-protocol-schema/src/v2/**`. `v1/` and `v2/` at
the repo root are **not** top-level directories — they are subdirectories of `schema/`, `docs/protocol/`, and
`docs/rfds/`. Upstream is unambiguous that v2 is draft: `README.md:23` says "**The current stable ACP
protocol version is `1`**", the docs navigation tags the v2 group `"tag": "Draft"` (`docs/docs.json:119-120`),
the Rust `ProtocolVersion::V2` constant only exists behind an explicitly opted-into
`unstable_protocol_v2` Cargo feature that is *deliberately excluded* from the `unstable` umbrella
(`agent-client-protocol-schema/Cargo.toml:39-42`, `src/version.rs:24-30`), and the schema artifact is versioned
`2.0.0-alpha.5` (`schema/v2/Cargo.toml:3`, released 2026-09-18).

Yes, there is a `schema/v2/schema.json` + `schema/v2/meta.json` exactly analogous to `schema/v1/` (same
generator, same `npm run generate` pipeline, same layout), and the v2 `$def`s carry the **same `x-side` /
`x-method` annotations** the v1 ones do (28 annotated `$def`s in v2 vs 46 in v1) — so this repo's
`tck.protocol` / `tck.validation` derivation strategy transfers. One structural change does affect that code:
the v2 schema's top level is an `anyOf` of **seven** branches (`Agent`, `Client`, `AgentBatchCall`,
`AgentBatchResponse`, `ClientBatchCall`, `ClientBatchResponse`, `ProtocolLevel`) rather than v1's three,
because v2 adds JSON-RPC batch arrays.

**The delta is large.** Wire-level: 8 v1 agent/client methods removed, 2 renamed, 1 method's response
semantics completely redesigned; 40 schema `$def`s removed and 45 added; 3 `session/update` variants removed
and 7 added; both `initialize` params and result restructured (role-agnostic `info`/`capabilities`, `info`
now required); every capability boolean becomes an object marker and moves under `capabilities.session`;
almost every enum becomes open/extensible; and stdio gains JSON-RPC batch handling. Unchanged: error codes,
the five content block types, the five stop reason values (but not where they are carried), `_meta` and
`_`-prefixed custom-method extensibility, and the stdio framing rules themselves.

---

## Requirements

This table is **status/meta requirements about v2 itself**, not the per-feature v2 conformance requirements
(those are the delta inventory in §Details and need per-area follow-up research before the TCK encodes them).

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| S1 | The current **stable** ACP protocol version is `1`. v2 is not stable. | Statement of fact | spec `README.md:23` |
| S2 | v2 is published as a **Draft**; "various pieces can, and will, change before stabilization". | Statement of fact (guidance) | spec `docs/announcements/acp-v2-draft.mdx:57-61` |
| S3 | Implementers **SHOULD** gate v2 behind explicit version negotiation *and* feature flags until it stabilizes; don't ship by default in production. | SHOULD (guidance) | spec `docs/protocol/v2/migration.mdx:20`; `docs/announcements/acp-v2-draft.mdx:61` |
| S4 | To use v2, the Client sends `"protocolVersion": 2` in `initialize`. The negotiation *mechanism* is unchanged from v1. | MUST (mechanism unchanged) | spec `docs/protocol/v2/migration.mdx:26`; `docs/protocol/v2/initialization.mdx:90-96` |
| S5 | v2 support is **additive**: implementers **SHOULD** keep serving `protocolVersion: 1` peers. | SHOULD (guidance) | spec `docs/protocol/v2/migration.mdx:8, 28, 770-772`; `docs/announcements/acp-v2-draft.mdx:63` |
| S6 | A single connection speaks exactly one negotiated version after `initialize`. | MUST (stated as invariant) | spec `docs/protocol/v2/migration.mdx:30` |
| S7 | Negotiating `protocolVersion: 2` does **not** imply any `schema.unstable.json` draft feature; each is gated by its own capability/flag. | MUST (capability-conditional) | spec `docs/protocol/v2/migration.mdx:22` |
| S8 | The v2 stable baseline is defined by `schema/v2/schema.json`. | Statement of fact | spec `docs/protocol/v2/migration.mdx:20` |

**Implication for TCK tiering:** every v2 protocol requirement is, at minimum, *conditional on the agent
answering `initialize` with `protocolVersion: 2`*. There is no upstream statement that any agent MUST support
v2 — the opposite (S1, S5). So the whole v2 suite should be gated the way a capability is, on the negotiated
version, and a v1-only agent must SKIP (not FAIL) all of it.

---

## Details

### 1. Where v2 lives

The spec repo root has **no** `v1/` or `v2/` directories. `v1`/`v2` are subdirectories of three trees.
Verified layout at `8f76d6c`:

| Purpose | v1 path | v2 path |
|---|---|---|
| Generated JSON Schema (stable) | `schema/v1/schema.json` (247 KB, 170 `$defs`) | `schema/v2/schema.json` (289 KB, 175 `$defs`) |
| Method-name tables (stable) | `schema/v1/meta.json` | `schema/v2/meta.json` |
| Generated JSON Schema (+unstable features) | `schema/v1/schema.unstable.json` | `schema/v2/schema.unstable.json` |
| Method-name tables (+unstable) | `schema/v1/meta.unstable.json` | `schema/v2/meta.unstable.json` |
| Artifact version marker crate | `schema/v1/Cargo.toml` + `CHANGELOG.md` | `schema/v2/Cargo.toml` (`version = "2.0.0-alpha.5"`) + `CHANGELOG.md` |
| Rust models | `agent-client-protocol-schema/src/v1/*.rs` (13 files) | `agent-client-protocol-schema/src/v2/*.rs` (13 files, incl. new `terminal.rs`, `schema_util.rs`) |
| Prose docs (stable) | `docs/protocol/v1/*.mdx` (21 pages) | `docs/protocol/v2/*.mdx` (19 pages) |
| Prose docs (unstable layer) | `docs/protocol/v1/draft/*.mdx` | `docs/protocol/v2/draft/*.mdx` |
| Design RFDs | `docs/rfds/*.mdx` (flat, shared) | `docs/rfds/v2/*.mdx` (12 RFDs + `overview.mdx`) |

Both trees are produced by one generator, `schema-generator`, from the single Rust source of truth:
`schema-generator/src/main.rs:168-177` selects the output path by the `(unstable_protocol_v2, unstable)`
feature pair, and `:208-214` does the same for the `meta*.json` files. `package.json`'s `generate` script
runs all four combinations.

**Files a programmer would vendor** (mirroring what `src/tck/schema/v1/` does today), at commit
`8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`:

```
schema/v2/schema.json   ->  src/tck/schema/v2/schema.json
schema/v2/meta.json     ->  src/tck/schema/v2/meta.json
```

Caveat for `VENDORED.md`: unlike v1, the v2 artifact is a moving prerelease. It is tagged upstream as
`schema-v2.0.0-alpha.5` (2026-09-18). Pinning the *tag* as well as the commit is worth doing — the Python
SDK does exactly that (`acp-python-sdk:schema/v2/VERSION` contains `refs/tags/schema-v2.0.0-alpha.5`).

### 2. Maturity evidence, verbatim

- `README.md:23` — "**The current stable ACP protocol version is `1`.**"
- `docs/docs.json:118-121` — the v2 navigation group carries `"tag": "Draft"` (v1's carries `"tag": "Latest"`, `docs/docs.json:66-67`).
- `docs/protocol/v2/migration.mdx:20` — "This guide describes the stable v2 baseline (`schema/v2/schema.json`). The v2 protocol surface as a whole is still labeled draft, so gate **v2 support behind explicit version negotiation and feature flags until it stabilizes.**"
- `docs/announcements/acp-v2-draft.mdx:59` — "**v2 is a Draft**. … **However, various pieces can, and will, change before stabilization.** That is the point of the draft stage: to receive feedback before we stabilize it."
- `docs/announcements/acp-v2-draft.mdx:61` — "gate your implementation behind the version negotiation **AND** feature flags. Don't ship it by default in production until we are closer to stabilization."
- `agent-client-protocol-schema/Cargo.toml:39-42` — "`# Protocol v2 is intentionally NOT part of the 'unstable' umbrella. # It introduces a parallel 'v2' module with a different wire version, so it # must be opted into explicitly.` / `unstable_protocol_v2 = []`"
- `agent-client-protocol-schema/src/version.rs:24-30` — `V2` is documented as "an unstable draft used for protocol iteration. It is only available when the `unstable_protocol_v2` feature is enabled and must be selected explicitly."
- `agent-client-protocol-schema/src/version.rs:31-39` — `LATEST` = `V1`, and `LATEST` is *deliberately removed* when `unstable_protocol_v2` is on, forcing an explicit choice.
- `schema/v2/Cargo.toml:3,6` — `version = "2.0.0-alpha.5"`, `description = "Version marker for ACP v2 JSON Schema artifacts"`; `schema/v2/src/lib.rs:1` — "Version marker package for ACP v2 JSON Schema **GitHub prereleases**."
- `AGENTS.md:70` — the repo's own commit-scope list defines `unstable-v2` as "Any changes that would only touch v2".
- **Churn:** `schema/v2/CHANGELOG.md:10-13` — `2.0.0-alpha.5` shipped 2026-09-18 and contains
  `feat(unstable-v2): return message ID on prompt insertion (#2175)`, i.e. the single biggest observable
  change to the prompt response landed **three days before this report**. Alphas 1–5 span 2026-07-20 to
  2026-09-18.

Reference SDKs (inventory note only — out of my scope, flagged for the SDK-status researcher):
`acp-rust-sdk` has `schema::v2` and a native v2 Testy fixture
(`src/agent-client-protocol-test/src/testy/v2.rs:1` — "Native draft protocol v2 support for Testy");
`acp-python-sdk` ships `src/acp/experimental/v2/` pinned to `schema-v2.0.0-alpha.5`
(`docs/experimental-v2.md:3-7` — "**Experimental.** Protocol v2 is a draft…").

### 3. Schema-mechanics delta (what breaks this repo's tooling)

| Aspect | v1 | v2 | Citation |
|---|---|---|---|
| `x-side` / `x-method` on method `$def`s | yes, 46 annotated `$def`s | **yes, same encoding**, 28 annotated `$def`s | `schema/v1/schema.json`, `schema/v2/schema.json` (counted; per-method table below) |
| `meta.json` shape | `{version, agentMethods, clientMethods, protocolMethods}` | **identical shape**, `"version": 2` | `schema/v1/meta.json:1-2`, `schema/v2/meta.json:1-2` |
| Top-level `anyOf` | 3 branches: `Agent`(`:6`), `Client`(`:44`), `ProtocolLevel` | **7 branches**: `Agent`(`:6`), `Client`(`:44`), `AgentBatchCall`(`:82`), `AgentBatchResponse`(`:125`), `ClientBatchCall`(`:289`), `ClientBatchResponse`(`:332`), `ProtocolLevel`(`:424`) | `schema/v1/schema.json:4-119`, `schema/v2/schema.json:4-424` |
| Batch sub-branches | n/a | `*BatchCall` → `Request` \| `Notification` \| `ProtocolLevelNotification`; `*BatchResponse` → `Result` \| `Error` | `schema/v2/schema.json:82-424` |
| `additionalProperties: false` | 0 occurrences | **0 occurrences** — same gap; `find_unknown_root_keys` is still needed | counted in both files |
| Open-enum fallback branches | none | present on most unions: a trailing `title: "other"` / `"unknown"` branch | e.g. `schema/v2/schema.json:4869` (`StopReason`), `:4300` (`SessionUpdate`) |
| `x-deserialize-default-on-error` | 251 occurrences | 222 | both files |
| `contentEncoding` / `"format": "uri"` | 0 / 1 | **5 / 7** (base64 and URI fields now annotated) | both files; `docs/protocol/v2/migration.mdx:670` |

**Important consequence for the TCK's validator:** in v2 the `StopReason` fallback branch is a bare
`{"type": "string"}` with **no `not` exclusion** (`schema/v2/schema.json:4869`, last branch), so JSON-Schema
validation alone can no longer reject an invalid stop reason. The `SessionUpdate` "other" branch *does*
carry a `not: {anyOf: [...known consts...]}` (`schema/v2/schema.json:4300`, last branch), so known
discriminators still validate strictly there. Any v2 equivalent of `ACP-PROMPT-001` must therefore check the
stop-reason value in Python, not lean on the schema.

**Method tables (`x-method`/`x-side`), v2 stable** — 14 agent-side, 4 client-side, 1 protocol-level:

```
agent:    initialize, auth/login, auth/logout, session/new, session/list, session/resume,
          session/close, session/delete, session/prompt, session/cancel (notification),
          session/set_config_option
client:   session/request_permission, session/update (notification),
          elicitation/create, elicitation/complete (notification)
protocol: $/cancel_request (notification)
```

(from `schema/v2/meta.json:3-21` and the `x-method` annotations)

### 4. Delta inventory v1 → v2

Tier column = the tier *within v2*, as stated upstream. Everything below is additionally conditional on
`protocolVersion: 2` having been negotiated (S4/S7 above).

#### 4.1 Methods — agent side (client → agent)

| v1 | v2 | Tier in v2 | Citation |
|---|---|---|---|
| `initialize` | same name, **params and result restructured** | MUST | `migration.mdx:38`, `schema/v2/schema.json:5801` (req) / `:3040` (resp) |
| `authenticate` | **renamed** `auth/login` | capability-conditional: MUST implement iff `authMethods` non-empty; Clients MUST NOT call otherwise | `migration.mdx:39,198`; `docs/protocol/v2/initialization.mdx:78`; `docs/protocol/v2/overview.mdx:54` |
| `logout` (gated on `agentCapabilities.auth.logout`) | **renamed** `auth/logout`; **no capability marker** — required iff `authMethods` non-empty | capability-conditional (same gate as `auth/login`) | `migration.mdx:40,198`; `docs/protocol/v2/authentication.mdx:52-58` |
| `session/new` | `mcpServers` now **optional**; response no longer has `modes` | MUST (baseline, iff `capabilities.session` advertised) | `migration.mdx:41,598`; `schema/v2/schema.json:6011,3627` |
| `session/load` | **REMOVED** — use `session/resume` with `replayFrom: {type:"start"}` | — | `migration.mdx:42,574-594`; `LoadSessionRequest`/`Response` absent from v2 `$defs` |
| `session/resume` (gated on `sessionCapabilities.resume`) | **baseline, no capability marker**; gains optional `replayFrom` | MUST (baseline) | `migration.mdx:43,190`; `docs/protocol/v2/session-setup.mdx:83`; `schema/v2/schema.json:6274` |
| `session/list` (gated on `sessionCapabilities.list`) | **baseline, no capability marker** | MUST (baseline) | `migration.mdx:44,190`; `docs/protocol/v2/session-list.mdx:10` |
| `session/close` (gated on `sessionCapabilities.close`) | **baseline, no capability marker** | MUST (baseline) | `migration.mdx:45,190`; `docs/protocol/v2/session-setup.mdx:237` |
| `session/delete` | unchanged; still gated on `session.delete` | capability: `capabilities.session.delete` | `migration.mdx:46`; `docs/protocol/v2/session-delete.mdx:35,57` |
| `session/prompt` | same request shape; **response semantics redesigned** (see 4.4) | MUST (baseline) | `migration.mdx:47,249-301`; `schema/v2/schema.json:4097` |
| `session/cancel` (notification) | same name and shape; **completion now reported via `state_update`** | MUST (baseline) | `migration.mdx:48,315-317`; `docs/protocol/v2/prompt-lifecycle.mdx:519` |
| `session/set_mode` | **REMOVED** — use `session/set_config_option` | — | `migration.mdx:49,606-608` |
| `session/set_config_option` | unchanged (but `id` → `configId`) | MAY (present in v2 meta table, not listed in the baseline set) | `migration.mdx:50,624-626`; `docs/protocol/v2/session-config-options.mdx:231` |
| `$/cancel_request` | unchanged | MAY | `migration.mdx:55`; `schema/v2/meta.json:20` |

#### 4.2 Methods — client side (agent → client)

| v1 | v2 | Tier in v2 | Citation |
|---|---|---|---|
| `session/request_permission` | same name; **params restructured** (required `title`, optional `description`, optional tagged-union `subject`) | MUST (client baseline) | `migration.mdx:51,478-530`; `schema/v2/schema.json:545` (`required: [sessionId, title, options]`) |
| `session/update` (notification) | same name; variant set changed (4.5) | MUST (client baseline) | `migration.mdx:52`; `docs/protocol/v2/overview.mdx:160-172` |
| `fs/read_text_file`, `fs/write_text_file` | **REMOVED** | — | `migration.mdx:53,628-635` |
| `terminal/create`, `terminal/output`, `terminal/release`, `terminal/wait_for_exit`, `terminal/kill` | **REMOVED** | — | `migration.mdx:54,628-637` |
| `elicitation/create` | unchanged shape; capability path renamed `clientCapabilities.elicitation` → `capabilities.elicitation` | capability: `capabilities.elicitation.{form,url}` | `docs/protocol/v2/elicitation.mdx:25-33`; `schema/v2/meta.json:17` |
| `elicitation/complete` (notification) | unchanged | capability-conditional (URL mode) | `docs/protocol/v2/elicitation.mdx`; `schema/v2/meta.json:18` |

#### 4.3 `initialize` params / result

| Field | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| request `protocolVersion` | required | required | MUST | `schema/v1/schema.json:4429` / `schema/v2/schema.json:5801` |
| request client capabilities | `clientCapabilities` (optional) | **`capabilities`** (optional) | MAY | same |
| request client info | `clientInfo` (optional, nullable) | **`info` (REQUIRED)** | MUST | `schema/v2/schema.json:5801` `required: ["protocolVersion","info"]`; `docs/protocol/v2/initialization.mdx:248` |
| response `protocolVersion` | required | required | MUST | `schema/v1/schema.json:2340` / `schema/v2/schema.json:3040` |
| response agent capabilities | `agentCapabilities` | **`capabilities`** | SHOULD (per `initialization.mdx:147`) | `docs/protocol/v2/migration.mdx:82` |
| response agent info | `agentInfo` (optional) | **`info` (REQUIRED)** | MUST | `schema/v2/schema.json:3040` `required: ["protocolVersion","info"]`; `docs/protocol/v2/initialization.mdx:248` |
| `authMethods` | optional array | optional array; **non-empty ⇒ MUST implement `auth/login` + `auth/logout`**; omitted/empty ⇒ Clients **MUST NOT** call either | MUST / capability-conditional | `docs/protocol/v2/initialization.mdx:78`; `migration.mdx:177,198` |
| `Implementation` shape (`name`,`title?`,`version`) | same | **identical** `$def` | MUST | `schema/v1` & `schema/v2` `$defs.Implementation` (byte-identical required set) |

Note: this is a direct TCK-relevant upgrade. The v1 `ACP-INIT-004` requirement (`agentInfo` present) is
ADVISORY in v1 but becomes **MANDATORY** in v2, since `info` is in `InitializeResponse.required`.

#### 4.4 Prompt lifecycle (the biggest semantic change)

| Signal | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| `session/prompt` response | `{stopReason}` — arrives when the turn *ends* | **`{messageId}`** — arrives when the user message is *inserted*; the Agent **MUST** respond without waiting for foreground work; **MUST NOT** respond merely on receipt/queue/ID-assignment | MUST | `migration.mdx:251-257`; `docs/protocol/v2/prompt-lifecycle.mdx:110`; `schema/v2/schema.json:4097` (`required: ["messageId"]`) |
| User message echo | implicit (the request itself) | Agent **MUST** report it via `user_message` (full array) or `user_message_chunk` updates, using the **same** `messageId`; Clients MUST tolerate either ordering vs. the response | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:129`; `migration.mdx:261` |
| Distinct submissions | n/a | Agents **MUST** assign distinct `messageId`s to distinct submissions even with identical content | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:151` |
| Work started | prompt request pending | `state_update` with `state: "running"` — Agent **MUST** send when foreground work starts/resumes | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:159`; `migration.mdx:278` |
| Work blocked | implicit | `state_update` with `state: "requires_action"` — Agent **SHOULD** send while waiting on permission | SHOULD | `docs/protocol/v2/prompt-lifecycle.mdx:371`; `migration.mdx:309` |
| Work ended | prompt response `stopReason` | `state_update` with `state: "idle"`; Agent **MUST** report `idle` when ready for a new prompt, and **MUST** include the `stopReason` when the transition ends foreground work | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:348`; `migration.mdx:282` |
| Cancellation confirmed | prompt response `stopReason: "cancelled"` | idle `state_update` with `stopReason: "cancelled"`, sent **after** all pending updates | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:519,526,530`; `migration.mdx:317` |
| Background updates | ambiguous in v1 | explicitly allowed while `idle`; they do not change state | MAY | `docs/protocol/v2/prompt-lifecycle.mdx` "Session States"; `schema/v2/schema.json:4940` (`StateUpdate` description) |
| Stop reason values | `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled` (closed `oneOf`) | **same five values**, but the union is now **open** (`anyOf` + bare-string fallback); custom values **MUST** begin with `_` | MUST | `schema/v1/schema.json:3447` vs `schema/v2/schema.json:4869`; `docs/protocol/v2/prompt-lifecycle.mdx:481` |
| Stop reason carrier | `PromptResponse.stopReason` (required) | `IdleStateUpdate.stopReason` (optional, nullable; "Agents SHOULD include this when the idle transition ends foreground work") | MUST at prose level (`prompt-lifecycle.mdx:348`), **SHOULD** at schema-description level | conflict noted in §Discrepancies |

#### 4.5 `session/update` variants

| v1 `sessionUpdate` | v2 | Tier | Citation |
|---|---|---|---|
| `user_message_chunk` / `agent_message_chunk` / `agent_thought_chunk` | kept; **`messageId` now required** on every chunk and update | MUST | `migration.mdx:61-63,327`; `docs/protocol/v2/prompt-lifecycle.mdx:246` |
| — | **NEW** `user_message`, `agent_message`, `agent_thought` — whole-message upserts keyed by `messageId`, `content` array with omit/`null`/value patch semantics; chunks append | MUST (when used) | `migration.mdx:64,329-339`; `schema/v2/schema.json:4767` (`UserMessage`, `required: ["messageId"]`) |
| — | **NEW** `state_update` (`running` / `idle` / `requires_action`, open union) | MUST | `migration.mdx:65`; `schema/v2/schema.json:4940` |
| `tool_call` (create) | **REMOVED**; the first `tool_call_update` for an unseen `toolCallId` creates the call | MUST | `migration.mdx:66,345`; `ToolCall` `$def` absent from v2 |
| `tool_call_update` | kept; now an explicit upsert, only `toolCallId` required, `title` **SHOULD** be on the first report | MUST / SHOULD | `migration.mdx:67,345`; `schema/v2/schema.json:674` (`required: ["toolCallId"]`) |
| — | **NEW** `tool_call_content_chunk` — appends one `ToolCallContent` item | MAY | `migration.mdx:68,370-385`; `schema/v2/schema.json:5040` (`required: ["toolCallId","content"]`) |
| — | **NEW** `terminal_update` — Agent-owned **display-only** terminal upsert keyed by `terminalId`; patch fields `command`, `cwd` (absolute), `output` (base64 snapshot, replaces), `exitStatus` | MAY | `migration.mdx:69,387-420`; `schema/v2/schema.json:5111` (`required: ["terminalId"]`) |
| — | **NEW** `terminal_output_chunk` — appends independently-base64-encoded bytes | MAY | `migration.mdx:70,422-432`; `schema/v2/schema.json:5173` (`required: ["terminalId","data"]`) |
| `plan` (flat entries list) | **replaced** by `plan_update` with a tagged-union payload (`type: "items"`, required `planId`, `entries`) | MAY | `migration.mdx:71,532-570`; `schema/v2/schema.json:5397` (`PlanUpdate`, `required: ["plan"]`) |
| `current_mode_update` | **REMOVED** — use `config_option_update` | — | `migration.mdx:72,606-608` |
| `available_commands_update` | kept; command `input` now a tagged union with required `type` (`"text"`) | MUST (when used) | `migration.mdx:73`; `docs/protocol/v2/slash-commands.mdx:64-70` |
| `config_option_update`, `session_info_update`, `usage_update` | unchanged | — | `migration.mdx:74-76` |
| — | **NEW** open fallback: an unknown `sessionUpdate` string is schema-valid; receivers SHOULD preserve it | SHOULD | `schema/v2/schema.json:4300` (last `anyOf` branch, `title: "other"`) |

#### 4.6 Capabilities

| v1 path | v2 path | Encoding change | Tier | Citation |
|---|---|---|---|---|
| `agentCapabilities` | `capabilities` | — | SHOULD | `migration.mdx:82` |
| `agentCapabilities.loadSession: bool` | **REMOVED** | — | — | `migration.mdx:189` |
| `agentCapabilities.sessionCapabilities.{list,resume,close}` | **REMOVED** — advertising `capabilities.session` at all now *requires* the 7-method baseline (`session/new`, `list`, `resume`, `close`, `prompt`, `cancel`, `update`) | object marker `session: {}` ⇒ baseline | MUST (capability-conditional on `capabilities.session`) | `migration.mdx:190,602-604`; `docs/protocol/v2/initialization.mdx:149-167` |
| `agentCapabilities.sessionCapabilities.delete` | `capabilities.session.delete` | object marker (unchanged) | capability | `docs/protocol/v2/initialization.mdx:186-190` |
| `agentCapabilities.sessionCapabilities.additionalDirectories` | `capabilities.session.additionalDirectories` | object marker (unchanged) | capability | `docs/protocol/v2/initialization.mdx:192-199` |
| `agentCapabilities.promptCapabilities.{image,audio,embeddedContext}: bool` | `capabilities.session.prompt.{image,audio,embeddedContext}: object` | **boolean → object marker** | capability | `migration.mdx:179-187`; `schema/v2/schema.json:3219` |
| `agentCapabilities.mcpCapabilities.{http: bool, sse: bool}` | `capabilities.session.mcp.{stdio: object, http: object}` — `sse` **removed**, `stdio` **newly explicit** | boolean → object; membership change | capability | `migration.mdx:645`; `schema/v2/schema.json:3303` |
| `agentCapabilities.auth.logout` | **REMOVED**; `capabilities.auth` remains but is orthogonal (extensions only) | — | — | `migration.mdx:198`; `docs/protocol/v2/initialization.mdx:80,157-161` |
| `clientCapabilities.fs.{readTextFile,writeTextFile}` | **REMOVED** | — | — | `migration.mdx:632`; absent from v2 `ClientCapabilities` (`schema/v2/schema.json:5842`) |
| `clientCapabilities.terminal: bool` | **REMOVED** | — | — | `migration.mdx:633` |
| `clientCapabilities.session.configOptions.boolean` | **REMOVED** (`ClientSessionCapabilities`, `BooleanConfigOptionCapabilities` `$def`s gone) | — | — | v2 `$defs` diff; `schema/v2/schema.json:5842` |
| `clientCapabilities.auth.terminal` | `capabilities.auth.terminal` | object marker (unchanged) | capability | `docs/protocol/v2/initialization.mdx:119-125` |
| `clientCapabilities.elicitation.{form,url}` | `capabilities.elicitation.{form,url}` | object marker (unchanged) | capability | `docs/protocol/v2/initialization.mdx:131-139` |

Net v2 client capability surface: **`auth`, `elicitation`, `_meta` only** (`schema/v2/schema.json:5842`).

#### 4.7 Content blocks

| Aspect | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| Block types | `text`, `image`, `audio`, `resource_link`, `resource` | **same five**, plus an open fallback branch | MUST | `schema/v1/schema.json:601` vs `schema/v2/schema.json:954`; `migration.mdx:668` |
| Custom types | n/a | custom block types **MUST** begin with `_`; non-`_` unknowns reserved for future ACP | MUST | `docs/protocol/v2/content.mdx` ("Content Types" §) |
| `resource_link.icons` | absent | **NEW** optional `Icon[]` (required `src`; optional `mimeType`, `sizes`, `theme: light\|dark`) | MAY | `migration.mdx:668`; `docs/protocol/v2/content.mdx` ("Resource Link" §); `$def` `Icon`/`IconTheme` new in v2 |
| MCP alignment | MCP `2025-06-18` | MCP `2026-07-28` | — | `docs/protocol/v2/content.mdx` (link targets) |
| Schema tightening | loose | `contentEncoding: "base64"` on base64 payloads, `format: "uri"` on URI fields, `annotations.priority` bounded 0–1 | MUST (schema-level) | `migration.mdx:670` |

#### 4.8 Other enum/union deltas (all become **open** unions in v2)

| Type | v1 values | v2 values | Citation |
|---|---|---|---|
| `ToolCallStatus` | `pending`, `in_progress`, `completed`, `failed` | **+ `cancelled`** + open fallback | `schema/v2/schema.json:819`; `migration.mdx:368` |
| `ToolKind` | 10 values incl. `other` | same 10 + open fallback branch (schema `title: "unknown"`) | `schema/v2/schema.json` `$defs.ToolKind` |
| `PlanEntryStatus` | `pending`, `in_progress`, `completed` | **+ `cancelled`** + open fallback | `migration.mdx:570` |
| `PlanEntryPriority` | `high`, `medium`, `low` | same + open fallback | v2 `$defs.PlanEntryPriority` |
| `PermissionOptionKind` | 4 kinds | same 4 + open fallback; **an Agent receiving an outcome it doesn't understand MUST NOT treat it as approval** | `migration.mdx:528`; `docs/protocol/v2/tool-calls.mdx:322,346` |
| `McpServer` | `http`, `sse`, `stdio` (stdio untagged) | `http`, `stdio` (**`type` discriminator now required on all**, `sse` **removed**) + open fallback; `args`/`env`/`headers` now optional | `migration.mdx:643-646`; `docs/protocol/v2/session-setup.mdx:334`; `schema/v2/schema.json:6052` |
| `AvailableCommandInput` | `unstructured` (untagged) | `text` (`type: "text"` required) + open fallback | `migration.mdx:674-692`; `docs/protocol/v2/slash-commands.mdx:64-70` |
| `AuthMethod` type | `agent` (default when absent), `terminal` | `agent`, `terminal`, + open fallback; **`type` now required**, `id` → `methodId` | `migration.mdx:197,211-224`; `docs/protocol/v2/authentication.mdx` |
| `ToolCallContent` | `content`, `diff`, `terminal` (client-owned terminal) | `content`, `diff` (**restructured**), `terminal` (**Agent-owned, display-only, `{type,terminalId}` only**) + open fallback | `migration.mdx:387-434,436-476` |
| `SessionConfigOptionCategory` | `mode`, `model`, `model_config`, `thought_level`, `other` | **unchanged** | both `$defs` |

#### 4.9 ID renames (wire-visible)

| Where | v1 | v2 | Citation |
|---|---|---|---|
| Auth method descriptor | `id` | `methodId` | `migration.mdx:704`; `docs/protocol/v2/authentication.mdx` |
| Session config option | `id` | `configId` | `migration.mdx:705`; `docs/protocol/v2/session-config-options.mdx:78,231` |
| Session config select group | `group` | `groupId` | `migration.mdx:706`; `docs/protocol/v2/session-config-options.mdx:127,135` |

Schema-definition renames with **no** wire change (matter only to codegen): `SessionNotification` →
`UpdateSessionNotification`, `CancelNotification` → `CancelSessionNotification`,
`AuthenticateRequest/Response` → `LoginAuthRequest/Response`, `LogoutRequest/Response` →
`LogoutAuthRequest/Response` (`migration.mdx:710`, confirmed in the `$defs` diff).

#### 4.10 Error codes

**Unchanged.** `docs/protocol/v1/error.mdx` and `docs/protocol/v2/error.mdx` are byte-identical (both are
"*Documentation coming soon*"), and `agent-client-protocol-schema/src/v1/error.rs` and
`src/v2/error.rs` are byte-identical (`diff` returns empty). v2 codes, from
`agent-client-protocol-schema/src/v2/error.rs:155-187`: `-32700` ParseError, `-32600` InvalidRequest,
`-32601` MethodNotFound, `-32602` InvalidParams, `-32603` InternalError, `-32800` RequestCancelled,
`-32000` AuthRequired, `-32002` ResourceNotFound. Same set, same numbers as v1.

#### 4.11 `_meta` / extensibility

| Aspect | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| `_meta` on object types | yes | yes; wording generalized | MAY | `docs/protocol/v2/extensibility.mdx:10` (diff vs v1:10-14) |
| `_meta` patch semantics | n/a | in upsert updates, top-level `_meta` follows omit/`null`/value patch semantics; nested `_meta` is scoped, omission ≡ `null` | MUST | `migration.mdx:717` |
| Custom methods `_`-prefixed | yes | **unchanged** | MUST | `migration.mdx:718`; `docs/protocol/v2/extensibility.mdx` |
| Unknown notifications | SHOULD ignore | **unchanged** | SHOULD | `docs/protocol/v2/extensibility.mdx:108` |
| Enum/union extension | ad-hoc (config options only) | **NEW normative section**: `_`-prefixed values reserved for implementations; unknown non-`_` reserved for future ACP; "Extensions **MUST NOT** define custom non-underscore values"; "Implementations **MUST NOT** treat unknown non-underscore values as custom extensions"; receivers **SHOULD** preserve unknown values | MUST / SHOULD | `docs/protocol/v2/extensibility.mdx:111-121` (the block added relative to v1) |
| Custom capabilities | via `_meta` in capability objects | unchanged mechanism, restructured example | SHOULD | `docs/protocol/v2/extensibility.mdx:124-146` |

#### 4.12 Transport / JSON-RPC

| Aspect | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| Framing | newline-delimited, UTF-8, no embedded newlines, stdout is ACP-only | **unchanged** | MUST | `docs/protocol/v1/transports.mdx:19-28` vs `docs/protocol/v2/transports.mdx:19-28` (diff is only the batch-array clause) |
| Message kinds on the wire | "individual JSON-RPC requests, notifications, or responses" | "requests, notifications, responses, **or batch arrays**" | MAY (sending); MUST (handling) | `docs/protocol/v1/transports.mdx:23` vs `docs/protocol/v2/transports.mdx:23-24` |
| Batch: allowed to send | not mentioned in v1 | "A client or agent **MAY** send an array filled with Request objects"; notification-only and mixed batches valid | MAY | `docs/protocol/v2/transports.mdx:47-51` |
| Batch: invalid JSON | — | single `-32700` response, `id: null` | MUST-ish ("return") | `docs/protocol/v2/transports.mdx:55-56` |
| Batch: empty array | — | "The batch **MUST** be an array with at least one value." Empty ⇒ single `-32600` with `id: null`, **not** a response array | MUST | `docs/protocol/v2/transports.mdx:57-59` |
| Batch: concurrency | — | receiver **MAY** process entries concurrently, in any order | MAY | `docs/protocol/v2/transports.mdx:60-61` |
| Batch: response array | — | receiver **SHOULD** respond with an array of the corresponding Responses after all Requests are processed; responses **MAY** be in any order | SHOULD / MAY | `docs/protocol/v2/transports.mdx:62-69` |
| Batch: notifications | — | receiver **MUST NOT** reply to a Notification, including within a batch | MUST | `docs/protocol/v2/transports.mdx:66-67` |
| Batch: all-notification batch | — | receiver **MUST NOT** return an empty array; returns nothing | MUST | `docs/protocol/v2/transports.mdx:70-72` |
| Batch: invalid entries | — | each produces its own `-32600` with `id: null`; the batch does not fail wholesale | MUST-ish | `docs/protocol/v2/transports.mdx:73-75` |
| Batch: lifecycle messages | — | **SHOULD NOT** batch `initialize`, `auth/login`, `session/new`, `session/resume`, `session/prompt` | SHOULD NOT | `docs/protocol/v2/transports.mdx:77-80`; `migration.mdx:722` |
| Remote transport | — | streamable HTTP + WebSocket is a **separate RFD, not part of core v2** | out of scope | `migration.mdx:724`; `docs/protocol/v2/transports.mdx:82-84` |
| Custom transports | MAY | unchanged | MAY | `docs/protocol/v2/transports.mdx:86-90` |

This confirms the note in `.agents/research/acp-v1-transport-and-jsonrpc.md`: batching is genuinely a v2-only
matter, and v1's transports page never mentions it.

#### 4.13 Session setup / resume / replay

| Aspect | v1 | v2 | Tier | Citation |
|---|---|---|---|---|
| `mcpServers` on `session/new` | **required** (even if `[]`) | **optional**; omitting ≡ `[]` | MAY | `migration.mdx:598`; `schema/v2/schema.json:6011` (`required: ["cwd"]`) |
| `modes` in `session/new`/`resume` response | present, optional | **REMOVED** | — | `migration.mdx:598`; `schema/v2/schema.json:3627` |
| `configOptions` in responses | optional, nullable array | present, non-nullable array type | — | `schema/v1:2867` vs `schema/v2:3627` |
| `replayFrom` on `session/resume` | n/a | optional tagged union; omitted/`null` ⇒ Agent **MUST NOT** replay; `{type:"start"}` ⇒ Agent **MUST** replay all retained history as ordinary `session/update` notifications **before** responding | MUST (capability-conditional on `capabilities.session`) | `docs/protocol/v2/session-setup.mdx:118,144,198-222`; `schema/v2/schema.json:6335` |
| Replay message IDs | n/a | Agent **MUST** include a unique `messageId` for each replayed message; a retained prompt-inserted user message **MUST** reuse its original ID | MUST | `docs/protocol/v2/session-setup.mdx:198-199`; `prompt-lifecycle.mdx:153` |
| `session/close` semantics | close the session | Agent **MUST** cancel ongoing work as if `session/cancel`, then free resources | MUST | `docs/protocol/v2/session-setup.mdx:258` |
| `additionalDirectories` | capability-gated, absolute paths | unchanged gate; each `session/resume` **MUST** send the full intended list (omitting ⇒ no additional roots, not "restore previous") | MUST / capability | `migration.mdx:600`; `docs/protocol/v2/session-setup.mdx:298,302` |

### 5. Migration / compatibility statements (requirement vs. guidance)

| Statement | Classification | Citation |
|---|---|---|
| "Migrating does not mean dropping v1. … implementers should support both versions side by side: negotiate the version per connection, keep your v1 support working, and add v2 behind feature flags until it stabilizes." | **Guidance** (no RFC-2119 keyword) | `migration.mdx:8` |
| "Treat v2 support as additive. Keep serving `protocolVersion: 1` peers when you add v2" | **Guidance** | `migration.mdx:28` |
| "Nothing about v2 changes the underlying JSON-RPC framing, so a single connection always speaks exactly one negotiated version after `initialize`." | **Requirement** (stated invariant, no keyword) | `migration.mdx:30` |
| "gate **v2 support behind explicit version negotiation and feature flags until it stabilizes**" | **Guidance** (bold, no keyword) | `migration.mdx:20` |
| "Negotiating `protocolVersion: 2` does **not** imply any of them [unstable features]. Gate each behind its own capability or feature flag the same as v1." | **Requirement** (normative consequence of `schema.unstable.json` being a separate artifact) | `migration.mdx:22` |
| "If the Agent supports the requested version, it **MUST** respond with the same version. Otherwise, the Agent **MUST** respond with the latest version it supports." | **MUST** (identical wording to v1) | `docs/protocol/v2/initialization.mdx:94` |
| "If the Client does not support the version specified by the Agent … the Client **SHOULD** close the connection and inform the user" | **SHOULD** | `docs/protocol/v2/initialization.mdx:96` |
| "Supporting both versions is the recommended path, not an edge case … the cleanest approach is to keep two thin protocol surfaces behind shared application logic and select one after `initialize`." | **Guidance** | `migration.mdx:770-772` |
| "Keep v1 and v2 schemas, generated models, and test fixtures fully separate, and gate unstable-v2 surfaces independently of `protocolVersion: 2`." (SDK checklist) | **Guidance**, directly applicable to this TCK's architecture | `migration.mdx:764` |
| "Model omitted vs `null` vs concrete values distinctly wherever v2 defines patch semantics. A plain nullable/optional type erases a distinction the protocol depends on." | **Guidance** (SDK checklist) — but the *underlying* three-state semantics are normative | `migration.mdx:765` |
| "Reject malformed payloads for _known_ discriminator values instead of demoting them to the unknown-variant fallback." | **Guidance** (SDK checklist) | `migration.mdx:766` |
| "**v2 is a Draft** … various pieces can, and will, change before stabilization." / "Don't ship it by default in production" | **Guidance** (announcement) | `docs/announcements/acp-v2-draft.mdx:59,61` |
| Deprecations | Only one explicit deprecation: MCP HTTP+SSE (`"type": "sse"`) is **removed** in v2 and described as "the deprecated HTTP+SSE transport". Everything else is removal, not deprecation — v1 is not deprecated. | `migration.mdx:644` |

There is **no** upstream statement that an agent MUST support v2, and no statement that v1 is deprecated or
sunset.

---

## Testability notes

General shape for a v2 TCK, given the above:

- **Everything gates on the negotiated version.** The probe is one `initialize` with
  `"protocolVersion": 2`; if the response's `protocolVersion` is not `2`, every v2 requirement SKIPs. This
  mirrors the existing capability-gate mechanism but at a coarser level. A v1-only agent must not FAIL.
- **`info` is newly assertable as MANDATORY.** `InitializeResponse.required == ["protocolVersion","info"]`
  makes the v1-ADVISORY `agentInfo` check a hard v2 MUST, catchable by pure schema validation.
- **Stop-reason validity is no longer schema-checkable.** The v2 `StopReason` fallback accepts any string
  with no `not` guard, so a v2 analogue of `ACP-PROMPT-001` must compare against the five known values in
  Python and separately assert the `_`-prefix rule for anything else.
- **The prompt turn's observable end moved.** A v2 prompt test can no longer wait on the `session/prompt`
  response for completion. It must (a) assert the response arrives promptly and carries a non-empty string
  `messageId`, and (b) wait for an idle `state_update`. This also changes the cancel race window logic: the
  v1 `run_prompt` race heuristics (peek for an early response) do not map directly, because in v2 the
  response is *expected* to arrive early and is not the turn's end.
- **Baseline-method tests become MANDATORY-when-`capabilities.session`-present.** `session/list`, `resume`,
  `close` lose their individual markers. A v2 agent advertising `capabilities.session` and failing
  `session/list` is non-conformant — which is a stronger assertion than the v1 CAPABILITY tier.
- **`fs/*` and `terminal/*` negative tests get simpler and stronger.** In v2 these methods do not exist at
  all, so a v2 agent calling them is unconditionally non-conformant — no "unadvertised capability" framing
  needed. `ACP-CLIENTCAP-001/002` become "these methods MUST NOT appear on a v2 connection, period";
  `ACP-CLIENTCAP-003` (`elicitation/create`) keeps its capability gate but on the new path.
- **Batching is testable but asymmetric.** The TCK is the *client*, so it can send a batch and assert the
  agent's response-array behaviour (ordering-independent match by `id`, no response for notification-only
  batches, per-entry `-32600` for invalid entries, single `-32600` for `[]`). It cannot force the agent to
  *send* batches. The `MUST NOT return an empty array` and `MUST NOT reply to a notification in a batch` rules
  are the cleanest MANDATORY assertions; the `SHOULD respond with an array` rule is ADVISORY.
- **Largely unobservable from a client harness:** the three-state patch semantics of upserts (a conforming
  and a non-conforming agent can produce identical wire traffic for a given prompt — the TCK cannot force an
  agent to emit a `null` clear); `requires_action` state reporting (SHOULD, and only observable if the agent
  happens to request permission); replay-ID reuse across separate connections (testable only if the agent
  retains history, which is not required — `prompt-lifecycle.mdx:153`).
- **Open enums neuter several schema-hygiene checks.** The existing `ACP-SCHEMA-002` (unknown root keys)
  still applies — v2 also has zero `additionalProperties: false` — but any check that relied on a closed
  discriminator (`sessionUpdate` value, `stopReason`, `ToolCallStatus`, `ToolKind`, content `type`) must be
  rewritten as "known value, OR `_`-prefixed custom" rather than "member of the known set".

---

## Discrepancies

1. **Migration guide vs. initialization doc vs. schema, on v2 client capabilities.**
   `docs/protocol/v2/migration.mdx:191` states: "Stable v2 currently defines **no standard Client capability
   fields**." This is contradicted by `docs/protocol/v2/initialization.mdx:113-139`, which documents
   `capabilities.auth.terminal` and `capabilities.elicitation` as client capability fields, and by
   `schema/v2/schema.json:5842`, where `ClientCapabilities` has exactly `{auth, elicitation, _meta}`.
   The schema and `initialization.mdx` agree; `migration.mdx:191` appears stale (it likely predates the
   `stabilize elicitation` / `stabilize terminal authentication` commits, `schema/v2/CHANGELOG.md:25-27`,
   alpha.3). **Recommendation: trust the schema + `initialization.mdx`.**

2. **`stopReason` on the idle `state_update`: MUST in prose, SHOULD/optional in schema.**
   `docs/protocol/v2/prompt-lifecycle.mdx:348` — "When the transition ends foreground work, the Agent
   **MUST** include the corresponding `StopReason`". But `IdleStateUpdate` (`schema/v2/schema.json` `$defs`)
   has no `required` list at all, and the `stopReason` description reads "Optional. Omitted or `null` both
   mean the agent is not reporting a stop reason. Agents **SHOULD** include this when the idle transition
   ends foreground work." The schema cannot express "required only when the transition ends foreground
   work", so this may be intentional laxity — but the tier differs (MUST vs SHOULD) and a TCK must pick one.

3. **`docs/protocol/v2/cancellation.mdx` shows a stale prompt response.** Its sequence diagram (the
   `response to id=1 ({})` line in the internal-cancellation diagram) shows an empty result, predating the
   alpha.5 change that made `messageId` required in `PromptResponse`
   (`schema/v2/CHANGELOG.md:10-13`, `schema/v2/schema.json:4097`). Wire truth is the schema: `{"messageId": "…"}`.

4. **`session/set_config_option` and `session/delete` are in the v2 method table but not in the
   "baseline" list.** `docs/protocol/v2/overview.mdx:52-124` lists the agent baseline as `initialize`,
   `auth/login`, `auth/logout`, `session/new`, `session/prompt`, `session/list`, `session/resume`,
   `session/close`, `session/cancel` — omitting `session/set_config_option`, which
   `docs/protocol/v2/initialization.mdx:165-167` also omits from the `session: {}` commitment, while
   `migration.mdx:190` lists the same 7. So `session/set_config_option` has **no capability marker and is
   not in the baseline** — its availability rule is unstated. Flagged as an open question, not resolved here.

5. **No discrepancy found** on error codes, framing, content block set, or stop-reason values: docs, schema,
   and Rust models agree across v1 and v2.

---

## Recommended follow-up research slices

Each of these differs enough from v1 that it needs its own report before the TCK encodes tests.

1. **`acp-v2-prompt-lifecycle-and-state-updates`** — the single largest change. Needs: exact `PromptResponse`
   contract, the full `state_update` state machine (including legal transitions, whether `running` before
   the response is legal, what "ready for a new prompt" means), ordering guarantees between the response and
   `user_message`, and what a TCK can actually assert without racing. Supersedes v1's `ACP-PROMPT-*`.
2. **`acp-v2-cancellation`** — cancellation confirmation moved from the prompt response to an idle
   `state_update` with a required ordering constraint ("MUST finish sending pending updates first"). The
   entire v1 cancel-race heuristic in `_helpers.run_prompt` needs re-derivation. Supersedes `ACP-CANCEL-*`.
3. **`acp-v2-initialize-capabilities-and-baseline`** — the `info`/`capabilities` rename, `info` becoming
   required, object-vs-boolean markers, and the "advertising `capabilities.session` commits you to 7
   methods" rule that converts several v1 CAPABILITY requirements into v2 MANDATORY ones. Must resolve
   discrepancy 1 and open question on `session/set_config_option`.
4. **`acp-v2-jsonrpc-batching`** — an entirely new, entirely testable MANDATORY surface with ~8 distinct
   rules (`transports.mdx:45-80`) and a corresponding top-level schema shape change
   (`AgentBatchCall`/`AgentBatchResponse`). No v1 analogue at all.
5. **`acp-v2-session-resume-and-replay`** — `session/load` is gone; `session/resume` + `replayFrom` now
   carries replay ordering MUSTs, `messageId` reuse MUSTs, and a "replay before responding" MUST. Merges and
   replaces v1's `ACP-LOAD-*` and `ACP-RESUME-*`.
6. **`acp-v2-upsert-patch-semantics`** — the omit/`null`/value three-state model across messages, tool calls,
   terminals, and `_meta`, plus chunk-append composition. Needed both to write tests and to decide what is
   honestly unobservable from a client harness. No v1 analogue.
7. **`acp-v2-open-enums-and-extensibility`** — the new normative "`_`-prefix or reserved" rule
   (`extensibility.mdx:111-121`) applies to ~10 unions and changes how *every* discriminator assertion in
   the suite must be written. Also needs to settle how the vendored v2 schema's open fallbacks interact with
   `tck.validation` and `find_unknown_root_keys`.
8. **`acp-v2-authentication`** — `authenticate`/`logout` → `auth/login`/`auth/logout`, the `logout` capability
   marker removed and replaced by "non-empty `authMethods` ⇒ both methods MUST exist", `id` → `methodId`,
   `type` now required. Reshapes all five of v1's `ACP-AUTH-*`.

**Areas that appear unchanged — plan to reuse v1 requirements with re-cited v2 sources rather than
re-research:**

- **Error codes** — `error.rs` byte-identical between v1 and v2; same eight codes. Reuse `ACP-ERROR-001`.
- **stdio framing and transport hygiene** — the *only* v1→v2 diff in `transports.mdx` is the batch clause.
  UTF-8, newline delimiting, no embedded newlines, stdout-is-ACP-only, stderr-may-be-anything are verbatim
  identical. Reuse `ACP-TRANSPORT-001/002` unchanged (note: a v2 batch array *is* a valid ACP message, so
  `ACP-TRANSPORT-001`'s "every stdout line is a JSON-RPC object" assertion must be relaxed to allow arrays).
- **Core JSON-RPC envelope rules** (id echo, result-xor-error, no reply to notifications, `-32601` for
  unknown methods) — unchanged apart from batching. Reuse `ACP-JSONRPC-001..005` with batch-aware wording.
- **Version negotiation *mechanism*** — `initialization.mdx:90-96` is word-for-word the v1 rule. Reuse
  `ACP-INIT-003`'s logic (only the requested/expected version numbers change).
- **Content block type set** — same five types; only `resource_link.icons`, the MCP revision, and the open
  fallback are new. Reuse `ACP-PROMPTCAP-001/002/003` with the new capability paths.
- **`_meta` and `_`-prefixed custom methods** — unchanged (`migration.mdx:718`). Reuse `ACP-EXT-001`,
  `ACP-META-001`.
- **`session/delete`** — "Unchanged. Still optional via `session.delete` capability" (`migration.mdx:46`).
  Reuse `ACP-DELETE-001/002` with the new capability path.
- **`elicitation/*`** — only the capability path changed (`clientCapabilities.elicitation` →
  `capabilities.elicitation`); the 14-line doc diff is entirely link/path churn.
- **`session/list`, `session_info_update`, `usage_update`, `config_option_update`** — semantics unchanged;
  only the capability gating for `list` changed (baseline now).
- **`SessionConfigOptionCategory`** — identical value set in both schemas.

---

## Open questions

Adjacent unknowns for the orchestrator to route elsewhere — I did not pursue these:

1. **Is `session/set_config_option` baseline, capability-gated, or unspecified in v2?** It has no capability
   marker, appears in `schema/v2/meta.json:7`, but is excluded from every "baseline" list
   (`overview.mdx:52-124`, `initialization.mdx:165-167`, `migration.mdx:190`). Its availability rule is
   genuinely unstated upstream as far as I can tell. (Route to slice 3.)
2. **What exactly does "the stable v2 baseline" include with respect to elicitation and terminal auth?**
   They are in `schema/v2/schema.json` (stable) but `migration.mdx` never mentions them, and `migration.mdx:191`
   denies they exist. (Discrepancy 1; route to slice 3.)
3. **Reference-SDK v2 maturity and whether a v2 cross-check fixture exists** — `acp-rust-sdk` has
   `testy::v2::V2Testy` and `acp-python-sdk` has `acp.experimental.v2`. Whether either is complete enough to
   serve as the v2 equivalent of this repo's `scripts/cross-check.sh` baseline is a separate question. The
   orchestrator said another researcher owns SDK status.
4. **Version-negotiation details** (what a v2-capable TCK should send when the agent answers `1`, whether the
   TCK should run both suites against a dual-version agent, `protocolVersion: 65535` probing under v2) — the
   orchestrator said another researcher owns negotiation.
5. **Does the v2 `terminal` display surface need capability negotiation at all?** `migration.mdx:191` says
   "Agent-owned terminal display is baseline behavior, not a Client execution capability", but a Client that
   cannot render one has no way to say so. Worth confirming before writing a `terminal_update` test.
6. **Stability risk / pinning policy for a moving target.** v2 changed materially 3 days before this report
   (alpha.5). Whoever writes the vendoring slice should decide whether to pin `schema-v2.0.0-alpha.5` and
   accept staleness, or track `main` and accept churn.
