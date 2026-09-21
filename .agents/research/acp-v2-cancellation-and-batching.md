# ACP v2: cancellation (`session/cancel`) and JSON-RPC batching / stdio framing

**Sources checked:**
- `agent-client-protocol` (spec, source of truth) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`, 2026-09-21 10:46 UTC, `main` — `git pull --ff-only` → "Already up to date".
- `acp-rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5`, 2026-09-18 — "Already up to date". Probed a **freshly built** `testy` (`cargo build -p agent-client-protocol-test --bin testy --no-default-features --features unstable_protocol_v2`, built into `/tmp/acp-v2-probe-target`, **not** into the checkout's own `target/`; the checkout's pre-existing `target/debug/testy` is a v1-only build and was not modified).
- `acp-python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64`, 2026-09-21 — "Already up to date". Probed the published wheel `agent-client-protocol==1.0.0rc2` via `uv run --no-project --with`.
- `check-a2a-tck`: **not** consulted; nothing here traces to it.

**Confidence:** high — every normative claim is a direct quote from `docs/protocol/v2/{transports,prompt-lifecycle,cancellation,overview,extensibility}.mdx` or `schema/v2/schema.json`, and every SDK claim is backed by either source/tests or a transcript I captured in this run. The one *medium*-confidence area is flagged explicitly: the spec is **silent** on cancel-with-no-active-work and cancel-for-unknown-session, so those are INFORMATIONAL, not requirements.

---

## Answer

**A. Cancellation.** `session/cancel` in v2 is unchanged on the wire — a client→agent notification whose params are `{sessionId}` plus optional `_meta` (`schema/v2/schema.json:6944-6966`, `required: ["sessionId"]`). What changed is the *confirmation*: it is no longer the `session/prompt` response's `stopReason`, but an idle `state_update` notification carrying `stopReason: "cancelled"`, which the Agent **MUST** send *after* all ongoing operations have been aborted and all pending updates have been sent (`prompt-lifecycle.mdx:519`, `:526`; `migration.mdx:317`). The Agent **MAY** keep sending content/tool-call updates after receiving the cancel, but **MUST** get them out before that idle update (`prompt-lifecycle.mdx:530`) — which is a strictly *weaker* ordering rule than v1's `ACP-CANCEL-002`, because v2 also explicitly permits background updates *after* idle (`prompt-lifecycle.mdx:497`). Pending agent→client requests: the *Client* **MUST** answer every outstanding `session/request_permission` with the `cancelled` outcome (`prompt-lifecycle.mdx:515`, `tool-calls.mdx:304`, `schema.mdx:1115-1116`); there is **no** normative requirement that the Agent send `$/cancel_request` for them — that cascade appears only in a non-normative sequence diagram (`cancellation.mdx:60-61`) and `$/cancel_request` handling is itself explicitly optional (`cancellation.mdx:14`). Elicitation cancellation at cancel time is entirely unspecified.

**The claim "v2 cancellation is deterministic" is backed by SDK behaviour, not by spec text.** Nothing in v2 keeps a turn open until the client acts. The observable window is `state_update: running` → `state_update: idle`, and the spec puts no lower bound on its duration; an agent may legally go `running` → `idle{end_turn}` in microseconds, exactly as in v1. I demonstrated this against v2 `testy`: with the `greet` prompt, `running` and `idle{end_turn}` both arrived 1 ms after the prompt response, and a `session/cancel` sent 0.8 s later produced **no output at all**. What *is* deterministic is `testy`'s `wait_for_cancel` scenario, which blocks the turn until cancel arrives (`src/agent-client-protocol-test/src/testy/v2.rs:329-334`, `:256-267`). So v2 removes one v1 failure mode (the turn-end signal can no longer beat the *first* observable event, because `running` is a MUST: `prompt-lifecycle.mdx:159`) but **does not remove the race**, and the TCK still needs a "cancellation not exercised" SKIP.

**B. Batching and framing.** stdio framing is unchanged except for one clause: a line may now also be a **batch array** (`transports.mdx:23-24`; the v1→v2 diff of `transports.mdx` is *only* that clause plus the new `## JSON-RPC Batch Messages` section). ACP adopts JSON-RPC 2.0 §6 essentially verbatim and adds one ACP-specific restriction: `SHOULD NOT` batch lifecycle-sensitive messages (`transports.mdx:77-80`). Sending batches is **MAY** for both sides; *handling* an inbound batch carries three MUSTs (`≥1` entry, never reply to a notification, never emit an empty response array) and several SHOULDs. The Rust SDK implements the whole rule set correctly — and does so on **v1 connections too**, which the v1 spec never authorised. The Python SDK has **no batch support at all**: a batch line crashes the agent process with `AttributeError: 'list' object has no attribute 'get'` (verified). Neither SDK ever *originates* a batch.

---

## Requirements

Tiers below are the tier *inside v2*. All of them are additionally conditional on `protocolVersion: 2` having been negotiated (see `acp-v2-status-and-delta-inventory.md` S4/S7), so in TCK terms every row is `capability:protocol-v2` at the outer level; the tier column is the tier *given* v2.

### A. Cancellation

| # | Requirement | Tier | Citation (repo: `agent-client-protocol` unless noted) |
|---|-------------|------|-----------|
| `ACP-CANCEL-201` | After `session/cancel` for a session with foreground work in flight, the Agent **MUST** send a `session/update` whose `update` is `{"sessionUpdate":"state_update","state":"idle","stopReason":"cancelled"}`. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:519`; `:526`; `docs/protocol/v2/migration.mdx:317`; `docs/protocol/v2/schema.mdx:234-240` |
| `ACP-CANCEL-202` | Every `session/update` the Agent sends *for the cancelled foreground work* **MUST** precede that idle `state_update`. (Background updates after it are explicitly allowed — see Details §A.5.) | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:530`; cf. `:497` |
| `ACP-CANCEL-203` | The Agent **MUST NOT** surface cancellation as a generic failure: it must catch aborted-operation exceptions and report the `cancelled` stop reason on a `state_update` instead. Concretely: after cancel, the turn must not end with a JSON-RPC error on the `session/prompt` request, nor with an idle `state_update` whose `stopReason` is a non-`cancelled` known value. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:521-528` (the `<Warning>` block, `:526`); `schema/v2/schema.json:4869` (`StopReason`, `cancelled` branch description) |
| `ACP-CANCEL-204` | On receiving `session/cancel`, the Agent **SHOULD** stop all language model requests and abort all in-progress tool call invocations as soon as possible. | SHOULD (**unobservable** — see Testability) | `docs/protocol/v2/prompt-lifecycle.mdx:517`; `docs/protocol/v2/schema.mdx:234-237` |
| `ACP-CANCEL-205` | `session/cancel` is a **notification**: the Agent **MUST NOT** send any JSON-RPC response (result or error) for it. | MUST | `schema/v2/schema.json:6916` (`CancelSessionNotification` sits under `AgentNotification`), `:6944-6966`; `docs/protocol/v2/overview.mdx:185`; `docs/protocol/v2/transports.mdx:66-67` |
| `ACP-CANCEL-206` | `session/cancel` params are exactly `{sessionId}` (required) + optional `_meta`; the Agent **MUST** accept a cancel that carries only `sessionId`, and **MUST** accept one that additionally carries `_meta`. | MUST | `schema/v2/schema.json:6944-6966`; `docs/protocol/v2/prompt-lifecycle.mdx:503-511` |
| `ACP-CANCEL-207` | A custom stop reason **MUST** begin with `_`; an unknown non-`_` stop reason is reserved for future ACP and is non-conformant today. (Applies to the `cancelled` assertion: a v2 agent may not substitute e.g. `aborted`.) | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:481`; `schema/v2/schema.json:4869` (`other` branch description) |
| `ACP-CANCEL-208` | `session/close` on a session with foreground work **MUST** cancel that work as if `session/cancel` had been sent, then free resources. (Overlaps the session-lifecycle slice; listed here because it is the *second* trigger for the ACP-CANCEL-201 sequence.) | MUST | `docs/protocol/v2/session-setup.mdx:258` |
| `ACP-INFO-CANCEL-201` | Behaviour of `session/cancel` for an **unknown `sessionId`**, or for a session with **no foreground work**, is **not specified**. Record only. | INFORMATIONAL (spec silent) | no normative text found; `docs/protocol/v2/prompt-lifecycle.mdx:499-536` says nothing; observed: rust `testy` silently ignores both (`src/agent-client-protocol-test/src/testy/v2.rs:205-221`, probe transcript §A.7) |
| `ACP-INFO-CANCEL-202` | Whether the Agent sends `$/cancel_request` for its own pending `session/request_permission` / `elicitation/create` requests when active work is cancelled is **not required** — only illustrated. Record only. | INFORMATIONAL (MAY at best) | `docs/protocol/v2/cancellation.mdx:14` ("Cancellation remains optional"), `:18` ("**MAY** cancel the corresponding request activity"), `:60-61` (diagram, non-normative) |

**Client-side MUSTs** (obligations on the *TCK's own mock client*, not assertions against the agent — but the TCK must satisfy them or it is itself non-conformant):

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| (client) | After sending `session/cancel`, the Client **MUST** respond to all pending `session/request_permission` requests with `{"outcome":{"outcome":"cancelled"}}`. | MUST | `docs/protocol/v2/prompt-lifecycle.mdx:515`; `docs/protocol/v2/tool-calls.mdx:304-313`; `docs/protocol/v2/schema.mdx:1115-1116`, `:4623-4630` |
| (client) | The Client **SHOULD** preemptively mark non-finished tool calls of the active work as `cancelled` when it sends `session/cancel`, and **SHOULD** still accept tool-call updates that arrive afterwards. | SHOULD | `docs/protocol/v2/prompt-lifecycle.mdx:513`, `:532`; `docs/protocol/v2/schema.mdx:1198-1201` |

### B. Framing and JSON-RPC / batching

| # | Requirement | Tier | Citation |
|---|-------------|------|----------|
| `ACP-TRANSPORT-201` | Every line the agent writes to stdout is a single valid ACP message: a JSON-RPC 2.0 **object** *or* a **non-empty JSON-RPC batch array** whose every element is a JSON-RPC object. (This is `ACP-TRANSPORT-001` with the array case added — see §C for the exact rewrite.) | MUST | `docs/protocol/v2/transports.mdx:23-24`, `:27`; `schema/v2/schema.json:82-424` (`AgentBatchCall`/`AgentBatchResponse`, `minItems: 1`) |
| `ACP-TRANSPORT-202` | The agent's stdout is valid UTF-8. | MUST | `docs/protocol/v2/transports.mdx:6` |
| `ACP-TRANSPORT-203` | Messages are newline-delimited and **MUST NOT** contain embedded newlines — a batch array must therefore be serialised on one line too. | MUST | `docs/protocol/v2/transports.mdx:25` |
| `ACP-JSONRPC-201` | A response's `id` echoes the request `id` exactly (integer and string ids), including for responses delivered inside a batch response array. | MUST | `docs/protocol/v2/overview.mdx:189`; `schema/v2/schema.json:125-288` (`AgentBatchResponse.items` → `Result`/`Error`, both `required: ["id", …]`); `docs/protocol/v2/transports.mdx:68-69` |
| `ACP-JSONRPC-202` | A response carries exactly one of `result`/`error`; an error object has an integer `code` and a string `message`. | MUST | `docs/protocol/v2/overview.mdx:183-184`; `schema/v2/schema.json:125-288` (disjoint `Result`/`Error` branches); `agent-client-protocol-schema/src/v2/error.rs:155-187` |
| `ACP-JSONRPC-203` | Notifications never receive a response, success or error — **including a notification inside a batch**. | MUST | `docs/protocol/v2/overview.mdx:185`; `docs/protocol/v2/transports.mdx:64-67` |
| `ACP-JSONRPC-204` | An unknown method yields `-32601`. Spec wording is still "should". | ADVISORY (SHOULD) | `docs/protocol/v2/extensibility.mdx:80-91` |
| `ACP-JSONRPC-205` | After an erroneous request — including an invalid or empty batch — the connection remains usable. | ADVISORY | `docs/protocol/v2/overview.mdx:179-185`; `docs/protocol/v2/extensibility.mdx:80-91`; observed in both SDK test suites (rust `tests/jsonrpc_batch.rs:1105-1142`, `:747-782`) |
| `ACP-BATCH-201` | An **empty array** (`[]`) receives a **single** `Invalid Request` (`-32600`) response object with `id: null` — **not** a response array. | MUST | `docs/protocol/v2/transports.mdx:57-59`; `schema/v2/schema.json:82,125,289,332` (`minItems: 1` on all four batch envelopes) |
| `ACP-BATCH-202` | The receiver **MUST NOT** reply to a Notification, including one inside a batch. A **notification-only batch** produces no output at all; the receiver **MUST NOT** return an empty array. | MUST | `docs/protocol/v2/transports.mdx:66-67`, `:70-72` |
| `ACP-BATCH-203` | A non-empty batch containing invalid entries produces a **per-entry** `-32600` with `id: null`; the batch does not fail wholesale and valid siblings still run. | MUST (phrased without an RFC-2119 keyword — "produce"; see Discrepancies §4) | `docs/protocol/v2/transports.mdx:73-75` |
| `ACP-BATCH-204` | The receiver **SHOULD** reply to a batch containing at least one Request with **one array** of the corresponding Response objects, emitted after all batch Requests have been processed. | SHOULD | `docs/protocol/v2/transports.mdx:62-65` |
| `ACP-BATCH-205` | Responses **MAY** appear in any order in the array; the sender **SHOULD** match them to requests by `id`. (An assertion on *order* would be wrong.) | MAY / SHOULD | `docs/protocol/v2/transports.mdx:68-69` |
| `ACP-BATCH-206` | The receiver **MAY** process batch entries concurrently, in any order, with any parallelism. (No ordering assertion is legitimate.) | MAY | `docs/protocol/v2/transports.mdx:60-61` |
| `ACP-BATCH-207` | A client or agent **MAY** send a batch. Notification-only and mixed request/notification batches are valid. An agent **MAY** therefore spontaneously emit a batch of `session/update` notifications. | MAY | `docs/protocol/v2/transports.mdx:47-51`; `schema/v2/schema.json:289-331` (`ClientBatchCall.items` = `ClientRequest` \| `ClientNotification` \| `ProtocolLevelNotification`) |
| `ACP-BATCH-208` | Clients and agents **SHOULD NOT** batch lifecycle-sensitive messages: `initialize`, `auth/login`, `session/new`, `session/resume`, `session/prompt`. | SHOULD NOT | `docs/protocol/v2/transports.mdx:77-80`; `docs/protocol/v2/migration.mdx:722` |
| `ACP-INFO-BATCH-201` | If the batch line itself is invalid JSON, "return a single Parse error (`-32700`) with `id: null`". This is the same behaviour ACP already leaves unasserted in v1 (`ACP-INFO-PARSE-001`): the SDKs disagree. Record only. | INFORMATIONAL | `docs/protocol/v2/transports.mdx:55-56`; disagreement: rust replies `-32700`, python emits nothing and crashes/logs (see §B.4) |
| `ACP-INFO-BATCH-202` | The v2 schema forbids a *call* batch from containing response-shaped entries and a *response* batch from containing calls, but no prose states this, and JSON-RPC 2.0 §6 does not either. Rust silently ignores a response-shaped entry inside a call batch rather than answering `-32600`. Record only. | INFORMATIONAL (schema-only restriction) | `schema/v2/schema.json:82-124` vs `:125-288`; rust-sdk `src/agent-client-protocol/tests/jsonrpc_batch.rs:318-323,347` and `md/transport-architecture.md:186-189` |

---

## Details

### A.1 `session/cancel` wire shape (v2)

Unchanged from v1. Client → Agent **notification**, no `id`, no response.

```json
{
  "jsonrpc": "2.0",
  "method": "session/cancel",
  "params": { "sessionId": "sess_abc123def456" }
}
```

`docs/protocol/v2/prompt-lifecycle.mdx:503-511`. Schema `$def` `CancelSessionNotification`
(`schema/v2/schema.json:6944-6966`):

| field | type | required | notes |
|---|---|---|---|
| `sessionId` | `SessionId` (string) | **yes** | |
| `_meta` | `object \| null` | no | `additionalProperties: true`, `x-deserialize-default-on-error: true` |

`x-side: "agent"`, `x-method: "session/cancel"`. It is reachable from the top level only via
`AgentNotification` (`schema/v2/schema.json:6916`), i.e. it is a notification, never a request.
The v2 schema-definition *type name* changed from v1's `CancelNotification` to
`CancelSessionNotification` with **no wire change** (`docs/protocol/v2/migration.mdx:710`).

### A.2 The conforming cancellation sequence

Normative, in order. `→` is client→agent, `←` is agent→client.

```
→  session/prompt            (id=N)
←  {"id":N,"result":{"messageId":"…"}}      MUST arrive on insertion, not completion
                                            (prompt-lifecycle.mdx:110, :124-127)
←  session/update  user_message | user_message_chunk(s), same messageId
                                            (prompt-lifecycle.mdx:129; may precede the response)
←  session/update  state_update{state:"running"}
                                            MUST, when foreground work starts (prompt-lifecycle.mdx:159)
   … zero or more content / tool_call_update / plan_update / usage_update …
→  session/cancel {"sessionId": …}          MAY, at any time (prompt-lifecycle.mdx:501)
   [client MUST now answer every pending session/request_permission with
    {"outcome":{"outcome":"cancelled"}}     (prompt-lifecycle.mdx:515)]
←  (optional) further session/update content / tool-call updates
                                            MAY, but MUST precede the next line
                                            (prompt-lifecycle.mdx:530)
←  session/update  state_update{state:"idle", stopReason:"cancelled"}
                                            MUST (prompt-lifecycle.mdx:519, :526)
```

After that idle update, the Client may prompt again (`prompt-lifecycle.mdx:536`), and the Agent
**MAY** still emit unrelated background `session/update` notifications — which "do not change the
state" (`prompt-lifecycle.mdx:497`).

Note what is *absent*: the spec places **no constraint at all** on the `session/prompt` request's
own response in the cancellation path, because that response was already sent at insertion time.
An in-flight `session/prompt` that has *not yet been answered* when the cancel lands is
under-specified; the only applicable rule is the general one that the response means insertion
(`prompt-lifecycle.mdx:110`) and that "Requests rejected before insertion use a JSON-RPC error
response".

### A.3 Observed sequence — rust `testy` v2 (captured in this run)

Built from `2a78849` with `--features unstable_protocol_v2`. Transcript, timestamps relative:

```
>> [0.000] {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":2,"info":{"name":"probe","version":"0"}}}
<< [0.003] {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":2,"info":{"name":"test-agent","version":"0.11.0"},"capabilities":{"session":{}}}}
>> [0.501] {"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp"}}
<< [0.503] {"jsonrpc":"2.0","id":2,"result":{"sessionId":"testy-v2-session-1"}}
>> [1.002] session/prompt id=3, text "wait_for_cancel"
<< [1.006] {"jsonrpc":"2.0","id":3,"result":{"messageId":"testy-v2-user-message-0"}}
<< [1.006] session/update  user_message        (messageId testy-v2-user-message-0)
<< [1.006] session/update  state_update running
   --- 1.5 s of silence: the turn stays open ---
>> [2.504] session/cancel {"sessionId":"testy-v2-session-1"}
<< [2.506] session/update  state_update idle, stopReason "cancelled"
>> [4.005] session/cancel again (no foreground work)  →  NOTHING emitted
```

`wait_for_cancel` is recognised as **plain prompt text** (not only the JSON command form): the v2
agent calls the shared `parse_command` (`src/agent-client-protocol-test/src/testy/v2.rs:324` →
`src/agent-client-protocol-test/src/testy.rs:1657-1682`), which maps `"wait_for_cancel"` /
`"wait for cancel"` via `TestyScenario::from_prompt`
(`src/agent-client-protocol-test/src/testy.rs:138`). So **the v1 cross-check's
`--cancel-prompt wait_for_cancel` carries over unchanged to v2 testy.** The scenario body is
`self.wait_for_cancelled(&session_id).await` then `StopReason::Cancelled`
(`src/agent-client-protocol-test/src/testy/v2.rs:329-334`, waiter at `:256-267`); `finish_prompt`
emits the idle update (`:191-197`) and forces `Cancelled` whenever the session is flagged
cancelled or closed (`:186-190`). Upstream's own test asserts exactly this order
(`src/agent-client-protocol-test/tests/testy_v2.rs:271-301`), and `md/testy.md:92-95` states the
intent: "`wait_for_cancel` makes this separation deterministic for client tests".

`mark_cancelled` only flips the flag **if `foreground_work` is true**
(`src/agent-client-protocol-test/src/testy/v2.rs:205-221`) — hence the silent no-op above.

### A.4 The race, demonstrated

Second transcript, same binary, `greet` instead of `wait_for_cancel`:

```
>> [0.603] session/prompt id=3, text "greet"
<< [0.606] {"jsonrpc":"2.0","id":3,"result":{"messageId":"testy-v2-user-message-0"}}
<< [0.606] session/update  user_message
<< [0.607] session/update  state_update running
<< [0.608] session/update  agent_message_chunk "Hello, world!"
<< [0.608] session/update  state_update idle, stopReason "end_turn"
>> [1.404] session/cancel  →  NOTHING emitted
```

The whole `running`→`idle` window was **1 ms**. No spec text prevents this. Therefore:

- `reference-sdks-v2-status.md` item 9 and its testability note ("No race window, no
  `--cancel-prompt`, no 'cancellation not exercised' SKIP") are **true of testy's
  `wait_for_cancel` scenario and false of v2 in general**. They are SDK-fixture properties.
- What v2 *does* buy the TCK over v1: `state_update: running` is a **MUST**
  (`prompt-lifecycle.mdx:159`), so a conforming agent always gives the client one guaranteed
  observable "turn started" event before completion. In v1 an agent could answer `session/prompt`
  with no `session/update` at all, leaving the TCK nothing to trigger on but a timer. So v2
  narrows the race from "the whole turn may be invisible" to "the visible window may be
  arbitrarily short", and the TCK's cancel trigger should be *on receipt of the `running`
  update*, not on a timer.
- A second, *deterministic* lever exists and has no v1 analogue: `session/close` **MUST** cancel
  ongoing work as if `session/cancel` (`docs/protocol/v2/session-setup.mdx:258`), and it is a
  **request**, so the agent's response to it is a hard synchronisation point. Upstream testy
  withholds the close response until foreground work finishes
  (`src/agent-client-protocol-test/src/testy/v2.rs:457-480`, and
  `tests/testy_v2.rs:313+` `testy_v2_close_cancels_active_work_before_responding`). That still
  does not force a *slow* turn, but it removes the "did my message even land?" ambiguity.

### A.5 What v1's `ACP-CANCEL-002` becomes

v1 `ACP-CANCEL-002` ("no `session/update` after the prompt response") has **no valid v2
counterpart in that form**, for two reasons:

1. The prompt response is no longer the end of the turn (`prompt-lifecycle.mdx:155`: "A
   successful prompt response is not an `idle` signal").
2. Even relative to the idle update, v2 *explicitly permits* subsequent `session/update`
   notifications: "Background activity **MAY** continue and emit other `session/update`
   notifications while the Agent reports `idle`. These notifications do not change the state."
   (`prompt-lifecycle.mdx:497`).

The surviving, narrower rule is `ACP-CANCEL-202`: updates *belonging to the cancelled foreground
work* must precede the idle update (`prompt-lifecycle.mdx:530`). A client-side harness cannot in
general distinguish "foreground work update" from "background update", so see Testability.

### A.6 Stop reason carriage

`IdleStateUpdate` (`schema/v2/schema.json:4904-4939`) has **no `required` list**; `stopReason` is
`StopReason | null` with the description "Optional. Omitted or `null` both mean the agent is not
reporting a stop reason. Agents SHOULD include this when the idle transition ends foreground
work." Prose says **MUST** (`prompt-lifecycle.mdx:348`, `:462`, `:519`). See Discrepancies §1.

`StopReason` (`schema/v2/schema.json:4869-4903`) is an **open union**: five known consts plus a
bare `{"type":"string"}` fallback with **no `not` exclusion**. Schema validation therefore cannot
reject a wrong stop reason — the TCK must compare in Python. `StateUpdate`
(`schema/v2/schema.json:4940+`) *does* carry a `not` guard on its `other` branch, so an unknown
`state` discriminator is still distinguishable.

### A.7 Cancel outside an active turn / unknown session

No normative text. `prompt-lifecycle.mdx:499-536` covers only the in-flight case. Observed:
rust `testy` v2 silently ignores `session/cancel` for an unknown `sessionId` and for a session
with no foreground work (`src/agent-client-protocol-test/src/testy/v2.rs:205-221`; both probed,
zero bytes emitted). Silence is also the only behaviour consistent with `ACP-CANCEL-205`
(notifications get no response) — an *error response* would itself be non-conformant. So the
honest TCK position is: assert only "no response object correlating to this notification",
record the rest.

### B.1 Framing: exactly what changed

`diff docs/protocol/v1/transports.mdx docs/protocol/v2/transports.mdx` is **two hunks**:

- `transports.mdx:23-24`: "Messages are individual JSON-RPC requests, notifications, responses,
  **or batch arrays**." (v1 line 23 had no "or batch arrays").
- a new `## JSON-RPC Batch Messages` section, `transports.mdx:45-80`.

Everything else is byte-identical: UTF-8 MUST (`:6`), stdio SHOULD (`:13`), newline delimiting
and no embedded newlines (`:25`), stderr MAY be arbitrary UTF-8 (`:26`), agent **MUST NOT** write
non-ACP to stdout (`:27`), client **MUST NOT** write non-ACP to stdin (`:28`), custom transports
(`:86-90`).

### B.2 The batch rule set, verbatim tiering

From `docs/protocol/v2/transports.mdx:45-80`:

| Line | Text (condensed) | Keyword |
|---|---|---|
| 47-48 | "ACP follows the JSON-RPC 2.0 batch rules." | (adoption statement) |
| 48-51 | "A client or agent **MAY** send an array filled with Request objects. A Notification is a Request object without an `id`, so notification-only and mixed request/notification batches are valid." | MAY |
| 55-56 | "If the batch itself is invalid JSON, return a single `Parse error` response (`code: -32700`) with `id: null`." | *no keyword* ("return") |
| 57-59 | "The batch **MUST** be an array with at least one value. An empty array receives a single `Invalid Request` response (`code: -32600`) with `id: null`, not a response array." | MUST |
| 60-61 | "The receiver **MAY** process batch entries as concurrent tasks, in any order, and with any degree of parallelism." | MAY |
| 62-63 | "The receiver **SHOULD** respond with an array containing the corresponding Response objects after all batch Request objects have been processed." | SHOULD |
| 64-65 | "A Response object **SHOULD** exist for each Request object, except that there **SHOULD NOT** be any Response object for Notifications." | SHOULD / SHOULD NOT |
| 66-67 | "The receiver **MUST NOT** reply to a Notification, including a Notification within a batch." | MUST NOT |
| 68-69 | "Response objects **MAY** appear in any order within the response array. The sender **SHOULD** match responses to requests by `id`." | MAY / SHOULD |
| 70-72 | "If there are no Response objects to send, such as for an all-notification batch, the receiver **MUST NOT** return an empty array and should return nothing." | MUST NOT |
| 73-75 | "Invalid entries in a non-empty batch produce their own `Invalid Request` responses (`code: -32600`) with `id: null`; they do not make the entire batch fail." | *no keyword* ("produce") |
| 77-80 | "Clients and agents **SHOULD NOT** batch lifecycle-sensitive messages such as `initialize`, `auth/login`, `session/new`, `session/resume`, and `session/prompt`." | SHOULD NOT |

Two notes on "adopt verbatim vs restrict":
- Lines 47-75 are a faithful restatement of JSON-RPC 2.0 §6 — I found **no** ACP deviation from
  it in the prose.
- Line 77-80 is the one **ACP-specific addition** (a restriction on senders, not receivers).
- The *schema* adds a restriction the prose does not state: see §B.3.

### B.3 Schema shape of a batch

`schema/v2/schema.json`'s top-level `anyOf` gains four array branches (v1 had three object
branches only):

| Branch | Line | `items` may be | `minItems` |
|---|---|---|---|
| `AgentBatchCall` | `:82` | `AgentRequest` \| `AgentNotification` \| `ProtocolLevelNotification` | 1 |
| `AgentBatchResponse` | `:125` | `Result` (`required: [id, result]`) \| `Error` (`required: [id, error]`) | 1 |
| `ClientBatchCall` | `:289` | `ClientRequest` \| `ClientNotification` \| `ProtocolLevelNotification` | 1 |
| `ClientBatchResponse` | `:332` | `Result` \| `Error` | 1 |

Every item still requires `"jsonrpc": "2.0"`. `ProtocolLevelNotification`
(`schema/v2/schema.json:6967-7000`) is `$/cancel_request`
(`CancelRequestNotification`, `:7001+`, `required: ["requestId"]`, `x-side: "protocol"`) — so
**`$/cancel_request` is explicitly legal inside a batch**.

The restriction the prose never states: a **call batch may not contain responses**, and a
**response batch may not contain calls**. JSON-RPC 2.0 §6 does not say this. It matters for the
TCK's validator (a vendored-v2 `validate_agent_message` will reject a mixed array) and for the
`AgentBatchResponse` direction: a batch the *agent* emits must be either all calls or all
responses.

### B.4 What the SDKs actually do

**Rust SDK — full, correct, and version-agnostic.**

Design statement: "Batch support is shared by the stable v1 and draft v2 APIs because it belongs
to the JSON-RPC transport layer" (`md/transport-architecture.md:169-170`); "Batch framing is a
shared JSON-RPC transport feature, not a v2-only protocol feature. Both v1 and v2 accept incoming
batches … **The SDK does not originate batches of requests or notifications.**"
(`md/protocol-v2.md:20-23`, repeated at `md/transport-architecture.md:190-192` and
`md/migration_v2.0.md:99-103`).

Behaviour, per `md/transport-architecture.md:172-192` and the 1442-line
`src/agent-client-protocol/tests/jsonrpc_batch.rs`:

| Rule | Rust behaviour | Citation |
|---|---|---|
| mixed request/notification/invalid batch | one response array containing only response-bearing entries; notifications produce nothing | `tests/jsonrpc_batch.rs:285-398` (8-entry batch → 4-element array) |
| invalid scalar entry | own `-32600`, `id: null` | `tests/jsonrpc_batch.rs:362` |
| invalid *params* on a valid request entry | `-32602` keyed to that entry's `id` | `tests/jsonrpc_batch.rs:368` |
| handler error on an entry | `-32603` keyed to that `id`, siblings unaffected | `tests/jsonrpc_batch.rs:374-375` |
| all-invalid non-empty batch | array of per-entry `-32600` | `tests/jsonrpc_batch.rs:747-780` |
| empty array | **single object** `-32600`, `id: null`; never an empty array | `tests/jsonrpc_batch.rs:1105-1142`; `md/transport-architecture.md:184-185` |
| notification-only batch | nothing at all (proved with a barrier request) | `tests/jsonrpc_batch.rs:1144-1207` |
| response-shaped entry inside a call batch | **silently ignored**, no `-32600` | `tests/jsonrpc_batch.rs:318-323,347`; `tests/jsonrpc_batch.rs:783-830`; `md/transport-architecture.md:186-189` |
| batch of *responses* inbound | routed to pending requests by `id` | `tests/jsonrpc_batch.rs:1209+` |
| dropped `Responder` for a batched request | `-32603` fallback so siblings are not stranded | `md/transport-architecture.md:180-183`; `tests/jsonrpc_batch.rs:569-625` |
| duplicate ids in one batch | distinct response slots | `tests/jsonrpc_batch.rs:894-937` |
| batch on a **v1** connection | accepted, one response array | `tests/jsonrpc_batch.rs:1339-1442` (`v1_agent_accepts_inbound_batch_through_default_component_adapter`) |
| originating a batch | **never** | `md/protocol-v2.md:22-23`; no public send-batch API (`grep "pub fn .*batch"` finds only `TransportBatch` constructors/iterators in `src/agent-client-protocol/src/jsonrpc.rs:167-196`) |

Confirmed live against the v2 `testy` build (transcript captured this run):

```
>> [{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp"}},
    {"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"nope"}}]
<< [{"jsonrpc":"2.0","id":2,"result":{"sessionId":"testy-v2-session-1"}}]

>> []
<< {"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Invalid request"}}

>> [17,true,null]
<< [{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Invalid request"}},
    {…same…},{…same…}]

>> [{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"nope"}}]
<< (nothing)

>> {"jsonrpc":"2.0","id":9,"method":"session/list","params":{}}
<< {"jsonrpc":"2.0","id":9,"result":{"sessions":[…]}}     ← connection still usable
```

Note the first batch contained `session/new`, which `transports.mdx:77-80` says SHOULD NOT be
batched; testy accepted it without complaint — correct, since SHOULD NOT binds the *sender*.

One more Rust behaviour with TCK relevance: `AgentProtocolRouter` will version-select from a
batch "whose first call-shaped entry is `initialize`", preserving the whole frame
(`md/transport-architecture.md:198-206`, `md/protocol-v2.md:400-408`) — i.e. batching
`initialize` is tolerated there too.

**Python SDK — no batch support; a batch kills the process.**

There is no batch handling anywhere in the stdio path. `_transport.py:82` does
`message: dict[str, Any] = json.loads(line)` with no array check (the annotation is a lie for
array input), and `connection.py:152-153` then calls `message.get("method")`.
`_process_message` is invoked **synchronously** from `_receive_loop` (`connection.py:145`) inside
a `try` that catches only `asyncio.CancelledError` / `asyncio.TimeoutError`
(`connection.py:146-149`), so the `AttributeError` escapes and terminates the agent.

Verified live against `agent-client-protocol==1.0.0rc2` + `examples/echo_agent.py` (v1 agent —
the v2 API reuses the very same `Connection`: `src/acp/experimental/v2/_connection.py:7`,
`src/acp/experimental/v2/agent.py:9,67` → `open_connection`):

```
>> {"jsonrpc":"2.0","id":1,"method":"initialize",…}
<< {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1}}
>> [{"jsonrpc":"2.0","id":2,"method":"session/new",…},{"jsonrpc":"2.0","method":"session/cancel",…}]
   (no stdout; process exits 1)
stderr: File ".../acp/connection.py", line 153, in _process_message
            method = message.get("method")
        AttributeError: 'list' object has no attribute 'get'
```

The only place Python mentions batches at all is the HTTP server, which rejects them:
`src/acp/http/server.py:242-243` returns HTTP 501 `"Batch requests are not supported"`, documented
at `docs/web-transport.md:238`. Python never emits a batch.

(The 501 posture matches the upstream Streamable-HTTP RFD, which also defers batching:
`docs/rfds/streamable-http-websocket-transport.mdx:269`, `:352`, `:364` — a **proposal**, not a
requirement, and out of scope for stdio.)

### B.5 Design intent (RFD, labelled as such)

`docs/rfds/v2/overview.mdx:60` — "Follow JSON-RPC 2.0 batch request and notification behavior" —
and the changelog entry `docs/rfds/v2/overview.mdx:130` ("2026-06-02: Recorded the v2 decision to
follow JSON-RPC 2.0 batch request and notification behavior"). This is design intent confirming
the "adopt §6 verbatim" reading; it is a **proposal record**, not itself normative.

---

## C. v1 requirement ids: carry, rewrite, or drop

| v1 id | v2 fate | Why |
|---|---|---|
| `ACP-TRANSPORT-001` | **Text MUST change.** Current: "Every line the agent writes to stdout is a single valid JSON-RPC 2.0 message." Proposed v2 text (`ACP-TRANSPORT-201`): *"Every line the agent writes to stdout parses as JSON and is either a single JSON-RPC 2.0 message object or a non-empty array whose every element is a JSON-RPC 2.0 message object."* Cite `docs/protocol/v2/transports.mdx:23-24,27` and `schema/v2/schema.json:82,125` (`minItems: 1`). Note that an **empty array `[]` on stdout is non-conformant** (`minItems: 1`), so the check is genuinely "non-empty array", not "array". | `transports.mdx:23-24` |
| `ACP-TRANSPORT-002` | **Reuse, re-cite.** Same rule, `docs/protocol/v2/transports.mdx:6`. | byte-identical |
| `ACP-JSONRPC-001` | **Reuse, re-cite + widen.** Must now also hold for responses delivered inside a batch response array. New citation `docs/protocol/v2/overview.mdx:189`, `schema/v2/schema.json:125-288`, `transports.mdx:68-69`. The old citation (`agent-client-protocol-schema/src/rpc.rs`) is v1-shaped; prefer the v2 schema. | |
| `ACP-JSONRPC-002` | **Reuse, re-cite.** `docs/protocol/v2/overview.mdx:183-184`; `agent-client-protocol-schema/src/v2/error.rs:155-187` (byte-identical to v1's `error.rs`). | |
| `ACP-JSONRPC-003` | **Reuse, text widened.** Add "including a notification inside a batch". Citation `docs/protocol/v2/overview.mdx:185` + `docs/protocol/v2/transports.mdx:66-67` (the batch clause is a *hard* MUST NOT, unlike v1's inference from overview prose). | |
| `ACP-JSONRPC-004` | **Reuse, re-cite.** Still "should". `docs/protocol/v2/extensibility.mdx:80-91`. | |
| `ACP-JSONRPC-005` | **Reuse, re-cite**, and extend the probe set to include `[]` and an all-invalid batch. | |
| `ACP-CANCEL-001` | **Replaced**, not re-cited. Its subject (the `session/prompt` response carrying `stopReason: "cancelled"`) no longer exists. → `ACP-CANCEL-201` + `ACP-CANCEL-203`. | `migration.mdx:317`; `prompt-lifecycle.mdx:110` |
| `ACP-CANCEL-002` | **Replaced and weakened.** → `ACP-CANCEL-202` (updates for the cancelled foreground work precede the idle update), because v2 explicitly allows background updates afterwards (`prompt-lifecycle.mdx:497`). | |
| *(new in v2)* | `ACP-CANCEL-205/206` (notification discipline + params shape), `ACP-CANCEL-207` (`_`-prefix rule for custom stop reasons), `ACP-CANCEL-208` (close ⇒ cancel), the whole `ACP-BATCH-2xx` family. | |

---

## Testability notes

### Cancellation

**The v2 cancel driver.** Replace v1's "send cancel on first update or after `cancel_wait`" with:

1. send `session/prompt`; record the response's `messageId`;
2. wait for `session/update` with `update.sessionUpdate == "state_update" and update.state == "running"` **for this `sessionId`** — this is the MUST-guaranteed turn-start marker (`prompt-lifecycle.mdx:159`) and is a strictly better trigger than v1's "first update of any kind";
3. send `session/cancel`;
4. wait for the next `state_update` with `state == "idle"`.

**Guard against a pre-`running` `idle`.** The upstream client quickstart warns that "an idle
update queued before running is only the session's earlier ready state" (rust-sdk
`md/protocol-v2-quickstart.md:48-52`, already noted by the SDK-status researcher). The TCK must
anchor on `running` first; testy v2 does *not* emit a ready-state idle, so testy alone will not
catch that bug in the TCK.

**The SKIP is still required.** Two honest SKIP conditions, mirroring v1's design:

- `S1` — the idle update was already read before `session/cancel` could be written (the whole
  `running`→`idle` window closed first). Demonstrated above at 1 ms against testy.
- `S2` — `session/cancel` was sent, but the idle update arrives with a valid non-`cancelled`
  stop reason within `quiet_period(timeout)` of the cancel (measured on transcript monotonic
  timestamps). The agent may simply have finished on its own.

Outside those, judge normally: `stopReason == "cancelled"` → PASS; a known non-`cancelled` stop
reason outside the window, or a JSON-RPC error ending the turn, → FAIL. Keep
`record_property("acp_tck_cancel_race_ms", …)`. **`--cancel-prompt` stays useful and its default
should stay a long free-form prompt**; for the cross-check, `--cancel-prompt wait_for_cancel`
works against v2 testy exactly as it does against v1 testy.

**`ACP-CANCEL-202` is only partially testable.** From the client side you cannot tell a
"foreground work" update from a legal background update. The defensible assertion is the narrow
one: *no `tool_call_update` / message-content update that belongs to a tool call or message the
agent had already started before the cancel may arrive after the idle `cancelled` update.* Even
that requires tracking entity ids. A weaker, fully sound version: *after the idle `cancelled`
update, no further `state_update` for this session arrives within `quiet_period(...)` unless a
new prompt was sent* — that one is defensible because a state change requires new foreground
work, which only a new prompt can start (`prompt-lifecycle.mdx:485-497`). Recommend implementing
the weaker form as `ACP-CANCEL-202` (MANDATORY) and leaving the entity-tracking version out.

**`ACP-CANCEL-204` is unobservable.** "Stop LLM requests and tool invocations as soon as possible"
has no wire signature. Register it for documentation completeness at ADVISORY and let it be
`NOT_TESTED`, or do not register it at all. Do not invent a latency threshold.

**Permission-request interaction is testable and worth a dedicated fixture.** A conforming agent
that issues `session/request_permission` mid-turn, gets `{"outcome":{"outcome":"cancelled"}}`
back after the client's `session/cancel`, and then emits idle/`cancelled` is the interesting
case; v1's `asks_permission.py`/`asks_permission_closable.py` pattern maps over directly. Note
that upstream testy v2 **never** sends an agent→client request
(`src/agent-client-protocol-test/src/testy/v2.rs:553-562` is the only outbound path), so the
cross-check will not exercise it.

**Non-conforming agents a TCK should catch:**

| Fixture idea | Trips |
|---|---|
| after cancel, resolves the turn with an idle `state_update` carrying `stopReason: "end_turn"` (with a ≥1.2 s delay so it lands outside the race window, exactly as `cancel_wrong_stop_reason.py` does today) | `ACP-CANCEL-201` |
| after cancel, emits **no** idle `state_update` at all (just stops) | `ACP-CANCEL-201` |
| after cancel, ends the turn by sending a JSON-RPC error `-32800` on the already-answered prompt id, or emits an idle update with `stopReason: "_aborted"` / `"aborted"` | `ACP-CANCEL-203`, `ACP-CANCEL-207` |
| emits the idle `cancelled` update first, *then* flushes the tool-call updates it was holding | `ACP-CANCEL-202` |
| replies to the `session/cancel` notification with a result or an error | `ACP-CANCEL-205` |
| rejects a `session/cancel` whose params carry an extra `_meta` object | `ACP-CANCEL-206` |

### Batching

**The TCK is the client, so the asymmetry is total:** it can force the agent's *receiving*
behaviour completely, and cannot force the agent to *send* a batch at all. `ACP-BATCH-207`
(MAY send) is therefore untestable as an assertion — but it is exactly why `ACP-TRANSPORT-201`
must tolerate arrays on stdout.

Cleanly assertable, all MANDATORY, all cheap and deterministic:

| Probe line | Expected | Requirement |
|---|---|---|
| `[]` | exactly one **object** `{"jsonrpc":"2.0","id":null,"error":{"code":-32600,…}}`; never `[...]` | `ACP-BATCH-201` |
| `[{…notification…}]` (use `_tck/*` or `session/cancel` for a live session) | **nothing** within `quiet_period(timeout)`, proved with a following barrier request whose response must be the next line read | `ACP-BATCH-202` |
| `[17, true, null]` | an array of exactly 3 `-32600`/`id:null` errors | `ACP-BATCH-203` |
| `[{id:A, method:"session/list"}, {id:B, method:"session/list"}]` | one array with responses for both A and B, matched **by id, order-independent** | `ACP-BATCH-204` (ADVISORY) + `ACP-JSONRPC-201` |
| mixed `[request, notification, 17]` | one array of exactly 2 entries: the request's response and one `-32600`/`id:null`; nothing for the notification | `ACP-BATCH-202` + `ACP-BATCH-203` |
| any single request after every probe above | normal response — connection survives | `ACP-JSONRPC-205` |

Implementation notes for whoever writes these:

- **Use the `_`-prefix rule for probe methods** exactly as the v1 suite does: `_tck/does_not_exist`
  etc., so a probe can never collide with a real v2 method (`docs/protocol/v2/extensibility.mdx:52`).
- **`ACP-BATCH-202` needs a barrier**, not a sleep. Upstream's own test does this
  (`rust-sdk tests/jsonrpc_batch.rs:1172-1179`): send the notification-only batch, immediately send
  an ordinary request, and assert the *first* line read back is that request's response. A pure
  quiet-period wait works too but is slower and weaker.
- **`ACP-BATCH-204` must not assert order** (`transports.mdx:68-69`) and must not assert *timing*
  ("after all Requests have been processed" is unobservable — you cannot see processing, only
  output). Assert set-equality of ids and that exactly one array line was emitted.
- **Do not batch lifecycle methods in the probes.** `transports.mdx:77-80` says SHOULD NOT; if the
  TCK batches `initialize` or `session/new` it is itself violating a SHOULD NOT and any resulting
  failure is ambiguous. Use `session/list` / `_tck/*` / `session/cancel`.
- **A batch probe can kill a Python-SDK-based agent outright.** Since the reference Python runtime
  crashes the process on any array line (§B.4), the batch tests must run **last**, or in their own
  connection, or the whole remaining suite will cascade into `AgentExited` failures. Strong
  recommendation: give the batch family its own `connected_agent()` so a crash is contained. The
  existing harness already records `AgentExited` with exit code and stderr, so the failure will be
  legible.
- **Whether the batch family should be MANDATORY at all is a tiering judgement the orchestrator
  should make consciously.** The spec's keywords say MUST for `ACP-BATCH-201/202` — but the
  reference Python SDK fails them by *crashing*, which means every Python-SDK-based v2 agent in
  existence today is non-conformant on this axis. That is a legitimate finding, not a reason to
  downgrade; but it will dominate the v2 cross-check scorecard. An alternative is to ship
  `ACP-BATCH-201/202/203` as MANDATORY (they are MUSTs) and accept that `docs/cross-check.md`'s v2
  baseline records "python: FAIL ACP-BATCH-* (process crash)".

**Unobservable / untestable from a client harness:**

- whether the agent processes batch entries concurrently (`ACP-BATCH-206`, MAY — nothing to assert);
- whether an agent *would* emit a batch (`ACP-BATCH-207`);
- whether the agent honours `SHOULD NOT batch lifecycle messages` when *sending* (`ACP-BATCH-208`) —
  the agent's only outbound calls are `session/request_permission` and `elicitation/*`, none of which
  are on the lifecycle list, so this rule has no observable agent-side surface;
- the `-32700`-for-invalid-JSON-batch rule (`ACP-INFO-BATCH-201`) — same SDK disagreement the v1
  suite already parks in `ACP-INFO-PARSE-001`.

---

## Discrepancies

1. **`stopReason` on the idle update: MUST in prose, SHOULD/optional in schema.** Prose:
   "When the transition ends foreground work, the Agent **MUST** include the corresponding
   `StopReason`" (`docs/protocol/v2/prompt-lifecycle.mdx:348`); "the Agent **MUST** send an idle
   `state_update` session update with the `cancelled` stop reason" (`:519`). Schema:
   `IdleStateUpdate` has **no `required` list** and `stopReason`'s own description says "Optional.
   … Agents **SHOULD** include this" (`schema/v2/schema.json:4904-4939`). The schema cannot express
   "required only when the transition ends foreground work", so the laxity may be deliberate.
   **For the cancellation path specifically the prose MUST is unambiguous** (`:519` is not hedged),
   so `ACP-CANCEL-201` is safely MANDATORY. A *general* "every idle carries a stopReason" check
   would not be. (Already flagged as Discrepancy 2 in `acp-v2-status-and-delta-inventory.md`;
   restating because it bears directly on my tier.)

2. **`docs/protocol/v2/cancellation.mdx:49` shows a stale prompt response.** The diagram line
   `Agent-->>Client: response to id=1 ({})` predates alpha.5's `messageId` requirement
   (`schema/v2/schema.json` `PromptResponse`, `required: ["messageId"]`;
   `schema/v2/CHANGELOG.md:10-13`). Wire truth is `{"messageId":"…"}`. The rust SDK's own doc has
   the same staleness: `md/testy.md:87` says "`session/prompt` returns an empty acceptance
   response", but the code returns `PromptResponse::new(user_message_id)`
   (`src/agent-client-protocol-test/src/testy/v2.rs:498`) and the test asserts
   `PromptResponse::new("testy-v2-user-message-0")`
   (`src/agent-client-protocol-test/tests/testy_v2.rs:276`). Documentation only; no behavioural
   conflict.

3. **Rust SDK accepts batches on v1 connections; the v1 spec does not define batching.**
   `docs/protocol/v1/transports.mdx:23` lists only "requests, notifications, or responses", and
   v1 has no batch section at all. The Rust SDK deliberately treats batching as a transport-layer
   feature shared by v1 and v2 (`md/transport-architecture.md:169-170`, `md/protocol-v2.md:20-22`)
   and has a passing test for a v1 agent answering a batch
   (`src/agent-client-protocol/tests/jsonrpc_batch.rs:1339-1442`). This is a permissive superset,
   not a conflict with any v1 MUST — but it means **the TCK must not add batch probes to its v1
   suite** on the strength of Rust's behaviour, and conversely a v1 agent that rejects a batch is
   not non-conformant.

4. **Two v2 batch rules are stated without an RFC-2119 keyword** but read as mandatory:
   `transports.mdx:55-56` ("return a single `Parse error` …") and `:73-75` ("Invalid entries …
   produce their own `Invalid Request` responses"). I have tiered `:73-75` as MUST
   (`ACP-BATCH-203`) because it is an unhedged statement of required output and both the schema
   and the Rust SDK implement it that way, and I have tiered `:55-56` as INFORMATIONAL
   (`ACP-INFO-BATCH-201`) because it collides with the pre-existing, already-parked
   parse-error disagreement between the SDKs. **Flagging the `:73-75` call explicitly so the
   orchestrator can overrule it** — a strict reading ("no keyword ⇒ not normative") would make it
   ADVISORY.

5. **Python SDK vs. v2 MUSTs on batching: hard non-conformance, not a grey area.**
   `ACP-BATCH-201` and `ACP-BATCH-202` are MUSTs; the Python runtime satisfies neither, and the
   failure mode is a process crash (`src/acp/connection.py:152-153`, verified). Since
   `src/acp/experimental/v2/_connection.py:7` reuses the same `Connection`, v2 inherits it
   unchanged. This is worth an upstream issue, and it is the single biggest tiering risk in this
   report (see Testability).

6. **Schema restricts batch composition beyond JSON-RPC 2.0 and beyond the ACP prose.** A
   `*BatchCall` array may not contain responses and a `*BatchResponse` array may not contain calls
   (`schema/v2/schema.json:82-124` vs `:125-288`). No prose says so; JSON-RPC 2.0 §6 does not say
   so; and the Rust SDK deliberately *ignores* a response-shaped entry inside a call batch rather
   than rejecting it (`md/transport-architecture.md:186-189`). Parked as `ACP-INFO-BATCH-202`.

7. **"v2 cancellation is deterministic" (`reference-sdks-v2-status.md` item 9 and its testability
   note) overstates the spec.** The cited evidence is all `testy` code and `testy` tests. No spec
   text keeps a turn open, and I reproduced the race against testy itself with a fast prompt (§A.4).
   Recommend the orchestrator amend that report's item 9 to read "deterministic *for testy's
   `wait_for_cancel` scenario*", and keep the "cancellation not exercised" SKIP in the v2 suite.

8. **No discrepancy found** on: the `session/cancel` wire shape (docs, schema, and both SDKs
   agree), the error-code set (`agent-client-protocol-schema/src/v2/error.rs` is byte-identical to
   the v1 file), the framing rules, or the batch rule set as the Rust SDK implements it.

---

## Open questions

Adjacent, not pursued — route elsewhere:

1. **What must an Agent do with a `session/prompt` that is still *unanswered* when `session/cancel`
   arrives?** The response means insertion (`prompt-lifecycle.mdx:110`) and cancel is about
   foreground work, so arguably the insertion still succeeds and the response is still
   `{messageId}`. But nothing states it. → prompt-lifecycle researcher.
2. **Is a bare `state_update: idle` with no `stopReason` ever conformant after a cancel?** Turns on
   Discrepancy 1. → prompt-lifecycle researcher (who owns the state machine).
3. **Does `elicitation/create` have to be cancelled when active work is cancelled?** The `cancelled`
   MUST at `prompt-lifecycle.mdx:515` names only `session/request_permission`; elicitation's own
   page never mentions active-work cancellation. → elicitation slice.
4. **Should the v2 TCK's own mock client ever *send* a batch as a conformance probe of the
   `initialize` path?** `AgentProtocolRouter` explicitly supports "a batch whose first call-shaped
   entry is `initialize`" (rust-sdk `md/transport-architecture.md:198-201`), but
   `transports.mdx:77-80` says SHOULD NOT batch `initialize`. Doing it would test a real
   compatibility path while violating a SHOULD NOT. → orchestrator / negotiation researcher.
5. **Vendoring `schema/v2/schema.json` breaks `tck.validation`'s single-object assumption.** The
   top level is now an `anyOf` including four array branches, and `validate_agent_message(msg: dict)`
   is typed for dicts only. Someone must decide the v2 validator's shape (per-entry validation plus
   an envelope-kind check) before the batch tests can validate what they read. → schema/vendoring slice.
6. **Should there be a `NOT_TESTED`-by-design tier for `ACP-CANCEL-204`?** It is a real SHOULD with
   no wire signature. The registry currently has no "registered but deliberately unobservable"
   concept; today such an id would pollute the report as `NOT_TESTED`. → orchestrator.
