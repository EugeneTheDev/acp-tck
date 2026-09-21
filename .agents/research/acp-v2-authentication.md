# What does ACP v2 require of an agent for authentication — `authMethods`, `auth/login`, `auth/logout`, the `-32000` gate, terminal auth, and the client-capability rules?

**Sources checked:**

- `agent-client-protocol` (spec, source of truth) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`, 2026-09-21 ("docs: update registry agents (#2190)"). `git pull --ff-only` → "Already up to date".
- `acp-rust-sdk` (reference implementation) @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5`, 2026-09-18 ("chore: release (#348)"). `git pull --ff-only` → "Already up to date".
- `acp-python-sdk` (reference implementation) @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64`, 2026-09-21 ("refactor(v2)!: expand parameters and derive routes from protocols (#150)", = tag `1.0.0rc2`). `git pull --ff-only` → "Already up to date".
- `a2a-tck`: not consulted; nothing here needed a design analogy.

Citations are repo-relative. Unprefixed = spec repo. `[rust]` = `acp-rust-sdk`. `[py]` = `acp-python-sdk`.
Line numbers in `schema/v2/schema.json` are for the file as committed at `8f76d6c`.

**Confidence:** high for the normative surface — the v2 auth surface is small and I read every v2
occurrence of `auth`, `auth_required`, `-32000`, `authMethods`, `auth/login`, `auth/logout` in the spec
repo plus the full v1↔v2 doc diff. **Medium** for reference behavior, for a negative reason: *neither*
reference SDK implements any v2 auth behavior — `testy`'s v2 agent has no auth at all — so the "what do
the runtimes do" question is answered almost entirely by absence rather than by observed traffic.

---

## Answer

v2 keeps v1's authentication model almost intact but replaces the capability marker with a
**derived** gate: `authenticate` → **`auth/login`**, `logout` → **`auth/logout`**, and an Agent that
returns *one or more valid entries* in `initialize.result.authMethods` **MUST** implement **both**
methods — there is no `logout` capability marker any more, and agent-side `capabilities.auth` is
explicitly orthogonal and gates nothing (`docs/protocol/v2/authentication.mdx:51-58`;
`docs/protocol/v2/initialization.mdx:78,80`; `docs/protocol/v2/overview.mdx:54`;
`schema/v2/schema.json:3071,5975-5976,5998-5999`). The descriptor renames `id` → `methodId`, makes the
`type` discriminator **required** (so v1's "absent `type` means `agent`" rule is gone), turns `env` into
an array of `{name, value}` objects with **unique** names, and adds an explicit open "other" branch whose
custom `type` values **MUST** begin with `_`. The terminal-auth client gate survives, moves to
`capabilities.auth.terminal` (object marker), and is now stated as an explicit schema MUST:
"Agents MUST advertise this method only when the client enabled its terminal authentication capability"
(`schema/v2/schema.json:3522`). **The `-32000` gate did not get stronger**: exactly as in v1, the only
statement is `session/new` "**May** return an `auth_required` error" and it lives only in the *generated*
`schema.mdx`/Rust doc-comment and the *draft* session-setup page — stable
`docs/protocol/v2/session-setup.mdx` never mentions authentication, no `data` shape is defined, no other
method is named, and there is no pre-`initialize` or per-method gating that v1 lacked. So the v1
`--auth-method` flow and the `AUTH-GATED:`/`blocked_by_auth` verdict logic carry over **unchanged in
shape** (only the method name and the `authMethods[*].id`→`methodId` lookup change), while **one v1
CAPABILITY requirement is promoted to a real MUST**: `auth/logout` must work whenever `authMethods` is
non-empty, and — unlike `auth/login` — it can be probed with `params: {}` without the TCK having to guess
a `methodId` or violate a client obligation.

---

## Requirements

Tier legend: **MUST** / **SHOULD** / **MAY** = stated with that force in a v2 normative source.
**cap:X** = capability-conditional. **client** = an obligation on the *Client*, hence not assertable
against an agent-under-test. **unspecified** = no v2 source states it. Everything below is additionally
conditional on `protocolVersion: 2` having been negotiated
(`.agents/research/acp-v2-status-and-delta-inventory.md` S4/S7).

| #   | Requirement | Tier | Citation |
|-----|-------------|------|----------|
| V1  | `initialize.result.authMethods` is **optional** (`required` is `["protocolVersion","info"]`); when present it is an array of `AuthMethod`. Unlike v1 there is **no** `default: []`; omitted ≡ empty for availability purposes. | MAY (presence); MUST (shape) | `schema/v2/schema.json:3070-3078`, `:3086`; `docs/protocol/v2/migration.mdx:177` |
| V2  | **Every** `AuthMethod` entry requires `type` (string), `methodId` (string, `AuthMethodId`) and `name` (string). `description` is optional string-or-`null`; `_meta` optional. v1's "absent `type` ⇒ `agent`" default is **gone**. | MUST | `schema/v2/schema.json:3399-3495` (all three branches require `type`), `:3521-3568` (`AuthMethodTerminal`, `required: ["methodId","name"]`), `:3569-3598` (`AuthMethodAgent`, same), `:3467` (other branch, `required: ["type","methodId","name"]`); `docs/protocol/v2/authentication.mdx:89-91`; `docs/protocol/v2/migration.mdx:197,211` |
| V3  | Stable v2 defines exactly two `type` values: `agent` (protocol-driven login via `auth/login`) and `terminal` (out-of-band relaunch). | MUST (closed set for *defined* types) | `schema/v2/schema.json:3403-3433`; `docs/protocol/v2/authentication.mdx:87-118` |
| V4  | Custom auth-method `type` values **MUST** begin with `_`. Unknown non-`_` types are reserved for future ACP variants. | MUST | `docs/protocol/v2/authentication.mdx:120-122`; `schema/v2/schema.json:3436,3440`; `docs/protocol/v2/migration.mdx:224`; general rule at `docs/protocol/v2/extensibility.mdx:111-121` |
| V5  | A `terminal` entry MAY carry `args` (array of strings) and `env` (array of `EnvVariable` = `{name, value}`, both required). | MUST (shape when present) | `schema/v2/schema.json:3542-3559`, `:3500-3520` |
| V6  | Every `env` entry **MUST** have a unique `name`. | MUST | `schema/v2/schema.json:3552` ("Names MUST be unique"); `docs/protocol/v2/authentication.mdx:202-203` |
| V7  | An Agent **MUST** advertise a `type: "terminal"` method **only when** the Client advertised `capabilities.auth.terminal` (object marker: omitted/`null` ⇒ unsupported, `{}` ⇒ supported). | MUST NOT otherwise (client-capability-gated) | `schema/v2/schema.json:3522` ("Agents MUST advertise this method only when the client enabled its terminal authentication capability"), `:5846-5857`, `:5878-5901`, `:5902-5913`; `docs/protocol/v2/authentication.mdx:127-154`; `docs/protocol/v2/initialization.mdx:119-125`; `docs/rfds/auth-methods.mdx:135-136` |
| V8  | Returning **one or more valid entries** in `authMethods` ⇒ the Agent **MUST** implement **both** `auth/login` **and** `auth/logout`. | cap:`authMethods` non-empty ⇒ MUST | `docs/protocol/v2/authentication.mdx:51-54`; `docs/protocol/v2/initialization.mdx:78`; `docs/protocol/v2/overview.mdx:54`; `docs/protocol/v2/migration.mdx:198,222,730`; `schema/v2/schema.json:3071`, `:5975-5976`, `:5998-5999`; `docs/rfds/auth-methods.mdx:159-162` |
| V9  | If `authMethods` is omitted or empty, Clients **MUST NOT** call `auth/login` or `auth/logout`. | MUST NOT (client) | same as V8; `docs/protocol/v2/migration.mdx:177` |
| V10 | There is **no logout capability marker** in v2. `capabilities.auth` (agent side) advertises authentication *extensions* only; its only defined property is `_meta`, and it does **not** advertise `auth/login`/`auth/logout` availability. | statement of fact | `docs/protocol/v2/authentication.mdx:56-58,220-223`; `docs/protocol/v2/initialization.mdx:80,157-161`; `schema/v2/schema.json:3139-3150`, `:3387-3398` |
| V11 | `auth/login` params: `methodId` **required** (`AuthMethodId` = string); `_meta` optional; nothing else defined. | MUST | `schema/v2/schema.json:5974-5996` (`required: ["methodId"]`); `docs/protocol/v2/authentication.mdx:166-180` |
| V12 | `auth/login` success result is an object; only `_meta` is defined on it (docs show `{}`). No `"null"` branch exists. | MUST (shape) | `schema/v2/schema.json:3599-3612`; `docs/protocol/v2/authentication.mdx:182-190` |
| V13 | Clients **MUST** call `auth/login` only with a method whose `type` defines a protocol-driven login flow, and **MUST NOT** pass a `terminal` method; the `methodId` must be one advertised in `initialize`. | MUST / MUST NOT (client) | `schema/v2/schema.json:5702` (method doc), `:5979`, `:3522`; `docs/protocol/v2/authentication.mdx:177-180,214-216`; `docs/rfds/auth-methods.mdx:156-157` |
| V14 | `auth/logout` params: no required fields (`_meta` only) — docs show `params: {}`. Success result is an object (`{}`). | MUST (shape) | `schema/v2/schema.json:5997-6010`, `:3613-3626`; `docs/protocol/v2/authentication.mdx:225-242` |
| V15 | `session/new` **may** return an `auth_required` (`-32000`) error if the agent requires authentication. | MAY | `docs/protocol/v2/schema.mdx:428`; `schema/v2/schema.json:5720` (method doc-string); `agent-client-protocol-schema/src/v2/agent.rs:5169` |
| V16 | After a successful `auth/login`, the Client can create sessions "without receiving an `auth_required` error for authentication-gated requests". | declarative (near-SHOULD; the only agent-side post-condition) | `docs/protocol/v2/authentication.mdx:192-193`; `docs/protocol/v2/schema.mdx:32-33`; `agent-client-protocol-schema/src/v2/agent.rs:5125` |
| V17 | After a successful `auth/logout`, authentication-gated requests will require completing an advertised flow again. | declarative (vacuous for an agent that never gated) | `docs/protocol/v2/authentication.mdx:244-245`; `docs/protocol/v2/schema.mdx:90-92` |
| V18 | The protocol does **not** guarantee what happens to already-running sessions after `auth/logout` (terminate / keep running / later `auth_required` are all conformant). | explicitly undefined | `docs/protocol/v2/authentication.mdx:247-251` |
| V19 | Clients **SHOULD** be prepared for active-session operations to fail with auth errors after logout. | SHOULD (client) | `docs/protocol/v2/authentication.mdx:253-255` |
| V20 | `-32000` = "Authentication required". Error objects require integer `code` and string `message`; `data` is optional and untyped. Error codes are **byte-identical** to v1. | MUST (code assignment) | `schema/v2/schema.json:4150,4196`, `$defs.Error`; `docs/protocol/v2/schema.mdx:3440-3443`; `agent-client-protocol-schema/src/v2/error.rs` is byte-identical to `src/v1/error.rs` (`diff` empty) |
| V21 | Terminal-auth flow (all client-side): relaunch the *configured agent program* with the descriptor's `args`/`env` appended, present the terminal, exit status 0 = success, then **reconnect + re-`initialize`** and retry the operation that required auth. The descriptor cannot supply a command. | MUST/SHOULD, all client-side | `docs/protocol/v2/authentication.mdx:195-216`; `docs/rfds/auth-methods.mdx:138-157` |
| V22 | Agents **SHOULD** provide `args` that enter a login-only flow and exit when it completes. ACP defines **no** in-band success signal. | SHOULD (agent; unobservable on the ACP connection) | `docs/protocol/v2/authentication.mdx:210-216`; `docs/rfds/auth-methods.mdx:151-154` |
| V23 | Clients **SHOULD NOT** batch `auth/login` (JSON-RPC batch arrays are new in v2). | SHOULD NOT (client) | `docs/protocol/v2/transports.mdx:77-80`; `docs/protocol/v2/migration.mdx:722` |
| V24 | `methodId` uniqueness within `authMethods`. | **description only**, not a MUST ("Unique identifier for this authentication method") | `schema/v2/schema.json:3526`, `:3574`, `:3443-3444` |
| V25 | Whether `auth/login` may be called before/after `session/new`, whether it must be repeated per connection, whether it is idempotent, and whether auth state survives a reconnect. | **unspecified** | absence; the only hint is V21's "reconnect and reinitialize, then retry", which presupposes out-of-band credential persistence but requires nothing |
| V26 | Error behavior of `auth/login`: unknown/not-advertised `methodId`, already-authenticated, credential failure, user cancellation. | **unspecified** — no code is defined for any of them; `-32000` means auth *required*, not auth *failed* | absence; `schema/v2/schema.json:4196` |
| V27 | Error behavior of `auth/logout` (e.g. when not logged in). | **unspecified** | absence |
| V28 | Any pre-`initialize` auth gating, or gating of methods other than `session/new`. | **unspecified** — only `session/new` is named anywhere in v2 (grep of all of `docs/protocol/v2/`, `schema/v2/`, `agent-client-protocol-schema/src/v2/`) | see Details §4 |
| V29 | Observable state change caused by a successful `auth/login`. | **only** V16 (a *negative*: `-32000` stops appearing) | `docs/protocol/v2/authentication.mdx:192-193` |

---

## Details

### 1. `authMethods` on the `initialize` response

```jsonc
"result": {
  "protocolVersion": 2,
  "info": { "name": "my-agent", "title": "My Agent", "version": "1.0.0" },
  "capabilities": {},
  "authMethods": [
    { "methodId": "agent-login", "type": "agent", "name": "Agent login",
      "description": "Sign in using the agent's login flow" }
  ]
}
```
(`docs/protocol/v2/authentication.mdx:60-82`)

`InitializeResponse.authMethods` (`schema/v2/schema.json:3070-3078`) is optional, typed
`AuthMethod[]`, annotated `x-deserialize-default-on-error: true` and
`x-deserialize-skip-invalid-items: true` — i.e. a *decoder* silently drops malformed entries. That is
exactly why the normative sentences all say "one or more **valid** entries": validity is decided
per-entry against the `AuthMethod` union.

**`AuthMethod` union** (`schema/v2/schema.json:3399-3495`) — a three-branch `anyOf`, each branch
requiring `type`:

| Branch | `type` | Required | Optional | `$def` |
|---|---|---|---|---|
| terminal | `"terminal"` (const) | `type`, `methodId`, `name` | `description` (string\|null), `args` (string[]), `env` (`EnvVariable[]`), `_meta` | `:3402-3417` + `AuthMethodTerminal` `:3521-3568` |
| agent | `"agent"` (const) | `type`, `methodId`, `name` | `description`, `_meta` | `:3418-3433` + `AuthMethodAgent` `:3569-3598` |
| other | any string **not** `agent`/`terminal` (enforced by an explicit `not`, `:3468-3491`) | `type`, `methodId`, `name` | `description`, `_meta`, **plus** `additionalProperties: true` (`:3492`) | `:3434-3493` |

`AuthMethodId` is a bare `"type": "string"` (`:3496-3499`). `EnvVariable` is
`{name: string (req), value: string (req), _meta?}` (`:3500-3520`).

Consequences a programmer needs:

- **`type` is now schema-enforced.** An entry with no `type` matches *no* branch, so it is caught by
  ordinary JSON-Schema validation of the `initialize` response. This is a real v1→v2 delta: in v1 an
  entry without `type` validated as an `agent` method.
- **The `_`-prefix rule is NOT schema-enforced.** The "other" branch accepts `"type": "gcloud"` just
  fine; only prose forbids it (`docs/protocol/v2/authentication.mdx:120-122`). A TCK that wants V4 must
  check it in Python.
- **Uniqueness of `methodId` is NOT stated as a MUST** — only the field description says "Unique
  identifier" (`:3526`, `:3574`, `:3443-3444`), exactly as in v1. Same ADVISORY tiering as
  `ACP-AUTH-001`.
- `authMethods` still has **no `ResponseField` entry** in `docs/protocol/v2/initialization.mdx`; it is
  documented only in prose at `:78` and in `authentication.mdx`. (Same documentation gap as v1.)

**The terminal client-capability gate (v1 Req 23 equivalent), verbatim:**

- `schema/v2/schema.json:3522` — "Agents **MUST** advertise this method only when the client enabled its
  terminal authentication capability."
- `docs/protocol/v2/authentication.mdx:151-154` — "If `capabilities.auth.terminal` is omitted or `null`,
  the Client does not advertise support. Supplying `{}` means the Client can reproduce the configured
  Agent invocation in an interactive terminal. An Agent may advertise a `terminal` method only when this
  capability is present."
- `docs/rfds/auth-methods.mdx:135-136` — same rule, design-intent framing.

This is **stronger** than v1, where the MUST lived only in the schema description and the prose said
"only when this capability is `true`". The wire encoding changed from boolean
(`clientCapabilities.auth.terminal: true`) to object marker (`capabilities.auth.terminal: {}`), and the
client capability container moved from `clientCapabilities` to `capabilities`
(`schema/v2/schema.json:5842-5877`, `:5878-5901`, `:5902-5913`).

### 2. `auth/login`

```
--> {"jsonrpc":"2.0","id":1,"method":"auth/login","params":{"methodId":"agent-login"}}
<-- {"jsonrpc":"2.0","id":1,"result":{}}
```
(`docs/protocol/v2/authentication.mdx:166-190`; `docs/protocol/v2/migration.mdx:200-207`)

| Field | Req. | Type | Citation |
|---|---|---|---|
| `params.methodId` | **required** | string (`AuthMethodId`) | `schema/v2/schema.json:5978-5985,5993` |
| `params._meta` | optional | object\|null | `:5986-5991` |
| `result` | — | object; only `_meta` defined ⇒ `{}` | `:3599-3612` |

**Availability.** MUST be implemented iff `authMethods` is non-empty (V8). The wire name is
`auth/login` in `schema/v2/meta.json:5` (key `auth_login`) and in the `x-method` annotations
(`schema/v2/schema.json:5995`, `:3611`), so the TCK's existing `meta.json`/`x-method`-derived method
inventory picks it up with no hand-editing.

**Error behavior: entirely unspecified** (V26). There is no v2 error code for unknown method id, failed
credentials, user cancellation, or "already authenticated". `-32000` is defined as authentication
*required*, not authentication *failed* (`schema/v2/schema.json:4196`). The RFD that would have closed
part of this gap, `docs/rfds/get-auth-state.mdx` (`auth/status` + a capability), is a **proposal only** —
`auth/status` appears **zero** times in `schema/v2/schema.json`, `schema/v2/schema.unstable.json` and
`schema/v2/meta.unstable.json`.

**Before/after `session/new`.** Nothing forbids either ordering. The flow diagrams put `auth/login` in
the initialization phase, before session setup (`docs/protocol/v2/overview.mdx:26-27`;
`docs/protocol/v2/authentication.mdx:20-32`), and the method doc says it is "Called when the agent
requires authentication before allowing session creation" (`schema/v2/schema.json:5702`) — descriptive,
not normative. There is no statement that it must be repeated per connection, no idempotency statement,
and no statement about whether auth state survives a reconnect. The terminal flow's "reconnect and
reinitialize, then retry the operation that required authentication" (`authentication.mdx:207-208`)
*presupposes* that credentials persist out of band, but imposes nothing.

**Observable state change:** exactly one, and it is a negative — after success, authentication-gated
requests stop returning `auth_required` (V16). There is no `authenticated: true` field anywhere, no
`auth/status`, and no notification.

### 3. `auth/logout`

```
--> {"jsonrpc":"2.0","id":2,"method":"auth/logout","params":{}}
<-- {"jsonrpc":"2.0","id":2,"result":{}}
```
(`docs/protocol/v2/authentication.mdx:225-242`)

`LogoutAuthRequest` (`schema/v2/schema.json:5997-6010`) has **no** required fields — only `_meta`.
`LogoutAuthResponse` (`:3613-3626`) likewise. Wire name from `schema/v2/meta.json:14`.

**Availability — confirmed, and it is the single biggest v1→v2 change here.** The capabilities-baseline
report is correct: non-empty `authMethods` implies **both** methods, and v1's
`agentCapabilities.auth.logout` marker is **gone**. Four independent normative statements:

- `docs/protocol/v2/authentication.mdx:51-54` — "Returning one or more valid entries in `authMethods`
  advertises the authentication surface. An Agent that does so **MUST** implement both `auth/login` and
  `auth/logout`. If `authMethods` is omitted or empty, the Agent does not advertise this surface and
  Clients **MUST NOT** call either method."
- `docs/protocol/v2/authentication.mdx:220-223` — "Clients may call it only when the Agent advertised one
  or more valid authentication methods during initialization; **there is no separate logout capability
  marker.**"
- `docs/protocol/v2/initialization.mdx:78` and `docs/protocol/v2/overview.mdx:54` — same sentence.
- `docs/protocol/v2/migration.mdx:198` — "In v1, logout support was opt-in via a capability marker. In
  v2, … the Agent **MUST** implement both … There is no logout support marker; `capabilities.auth`
  remains orthogonal."

Mirrored in the schema doc-strings (`schema/v2/schema.json:5998-5999`, `:3071`) and the Rust models
(`agent-client-protocol-schema/src/v2/agent.rs:139-140,373-374,459-460`).

**Effect on sessions / in-flight turns: explicitly undefined** (V18). `authentication.mdx:247-251`:
"The protocol does not guarantee what happens to already-running sessions after `auth/logout`. Agents
may terminate them, keep them running, or return `auth_required` errors for future session activity."
Nothing at all is said about an *in-flight prompt turn* — not even permissively. The v1 report's
conclusion carries over verbatim.

**`session/new` after logout:** only the declarative V17 ("will require the user to complete one of the
advertised authentication flows again"), which is vacuous for an agent that never gated in the first
place. The stronger "subsequent requests that require authentication **should** return `auth_required`"
lives only in `docs/rfds/logout-method.mdx:186-196` — RFD design intent, **not** protocol text. Do not
promote it.

### 4. The `-32000` (`auth_required`) gate

**Complete inventory of every `auth_required` / `-32000` statement in v2** (grep over
`docs/protocol/v2/**`, `schema/v2/**`, `agent-client-protocol-schema/src/v2/**`):

| Source | Exact force |
|---|---|
| `docs/protocol/v2/schema.mdx:428` = `schema/v2/schema.json:5720` = `agent-client-protocol-schema/src/v2/agent.rs:5169` | "`session/new` **May** return an `auth_required` error if the agent requires authentication." |
| `docs/protocol/v2/schema.mdx:32-33` = `schema/v2/schema.json:5702` = `agent.rs:5125` | "After successful authentication, the client can proceed to create sessions with `new_session` **without receiving an `auth_required` error**." |
| `docs/protocol/v2/authentication.mdx:192-193` | Same, generalized: "…without receiving an `auth_required` error **for authentication-gated requests**." |
| `docs/protocol/v2/authentication.mdx:247-251` | Post-logout: agents "**may** … return `auth_required` errors for future session activity." |
| `docs/protocol/v2/draft/session-setup.mdx:10` | "If the Agent requires authentication, `session/new` **may** fail with an `auth_required` error…" — **draft page only**. |
| `docs/protocol/v2/session-setup.mdx` (stable) | **No mention of authentication at all.** |
| `docs/protocol/v2/error.mdx` | "_Documentation coming soon_" (byte-identical to v1's). |
| `agent-client-protocol-schema/src/v2/error.rs:115` | `Error::auth_required()` constructor; **byte-identical** to the v1 module (`diff` returns empty). |

Answering the sub-questions precisely:

- **Which methods may return it?** Only `session/new` is named. `authentication.mdx:192-193` and
  `:247-251` generalize to "authentication-gated requests" / "future session activity" without naming
  any method. Nothing licenses asserting `-32000` on `session/resume`, `session/list`, `session/prompt`,
  `session/close`, or `session/delete`.
- **Required or merely permitted when `authMethods` is non-empty?** **Merely permitted.** There is no
  MUST anywhere. The condition ("the agent requires authentication") is an agent-internal fact the
  protocol never makes observable. `docs/rfds/get-auth-state.mdx:27` states this as the motivating
  problem, in so many words: "**The `session/new` method is not required by the specification to check
  authorization.** Some agents validate credentials eagerly, others do so lazily (e.g., on the first LLM
  call). The client cannot rely on `session/new` to consistently surface auth issues." (RFD = design
  intent, but here it is an accurate characterization of the normative text, and it is the *current*
  upstream position as of this revision.)
- **`data` shape?** None. `Error.data` is "Optional primitive or structured value … additional
  information" with no type (`schema/v2/schema.json` `$defs.Error`); `Error::auth_required()` attaches no
  `data` at all, unlike `resource_not_found` which attaches `{"uri": …}`
  (`agent-client-protocol-schema/src/v2/error.rs:115-128`). The `auth_methods` field was deliberately
  removed from the `Error` type back in 2026-03-09 (`docs/rfds/auth-methods.mdx:196`).
- **What is the client expected to do?** Complete one of the advertised flows: `auth/login` for an
  `agent`-type method, or the out-of-band relaunch for a `terminal`-type one, then retry
  (`docs/protocol/v2/overview.mdx:27`; `docs/protocol/v2/authentication.mdx:195-208`). Not stated as an
  RFC-2119 MUST.
- **Does v2 add pre-`initialize` or per-method gating v1 lacked?** **No.** Zero new statements. The only
  wording change is the generalization from v1's "new sessions" to v2's "authentication-gated requests"
  (`authentication.mdx:192-193,244-245`), which names nothing new and adds no force.

Worth noting for a v2 harness: both reference runtimes independently reject *any* non-`initialize`
traffic before initialization completes, with `-32600` (`[rust] md/protocol-v2.md:330-336`;
`[py] src/acp/experimental/v2/_initialization.py:52-67`). That is an initialization-ordering rule, not an
auth rule, and it is owned by another slice — mentioned only so it is not mistaken for auth gating.

### 5. Terminal auth (`type: "terminal"`)

Descriptor (`docs/protocol/v2/authentication.mdx:104-118`):

```json
{
  "methodId": "terminal-login",
  "name": "Log in from the terminal",
  "type": "terminal",
  "args": ["--login"],
  "env": [{ "name": "ACP_INTERACTIVE_LOGIN", "value": "1" }]
}
```

Flow (`docs/protocol/v2/authentication.mdx:195-216`; `docs/rfds/auth-methods.mdx:138-157`), all of it
client-side:

1. Launch a **separate interactive process** using the *same configured Agent program and base launch
   configuration* as the ACP connection.
2. Append the descriptor's `args`; apply its `env`, overriding same-named variables in the base launch
   configuration. Every `env` entry **MUST** have a unique `name`.
3. Present the terminal; wait for exit. Exit 0 = success; non-zero, termination without an exit status,
   or cancellation = failure.
4. Reconnect and re-`initialize` the ACP Agent, then retry the operation that required authentication.

Hard constraints that matter to a TCK:

- **The descriptor cannot provide a command** — the Client derives it from its own configuration
  (`:210-212`). So `args`/`env` are the *entire* agent-supplied surface.
- **No in-band success signal exists.** "ACP does not define an output pattern or other in-band success
  signal; Clients may recognize implementation-specific signals only as an extension" (`:212-214`).
- **The terminal process is not the ACP connection**, therefore "the Client **MUST NOT** send an
  `auth/login` request for a terminal method" (`:214-216`; `schema/v2/schema.json:3522`;
  `docs/rfds/auth-methods.mdx:156-157`).

**Client-observable:** only the advertisement — that a `terminal` entry appeared at all, and its
`methodId`/`name`/`description`/`args`/`env` shape. **Nothing** about the flow is observable on the ACP
connection. A TCK without a TTY loses nothing, because a TCK *with* a TTY would also observe nothing:
the whole flow happens in a different process, and the only protocol-level aftermath is a fresh
connection and a fresh `initialize`. A TCK **can** assert V5/V6/V7; it **cannot** assert V21 or V22 at
all (V22 is about a program's behavior when run with different arguments — out of ACP's scope entirely).

### 6. Reference behavior (Rust and Python v2 runtimes)

**Nothing implements v2 auth behavior. There is no reference v2 agent with an auth surface.**

Rust (`acp-rust-sdk` @ `2a78849`):

- Types and JSON-RPC method-name wiring exist:
  `src/agent-client-protocol/src/schema/v2_impls.rs:213-214` binds
  `v2::LoginAuthRequest`/`LoginAuthResponse` → `"auth/login"` and
  `v2::LogoutAuthRequest`/`LogoutAuthResponse` → `"auth/logout"`; the enum tables at `:302-303,326-327`
  mirror it. The only test is a serialization round-trip
  (`src/agent-client-protocol/tests/protocol_v2.rs:811-822`).
- `testy`'s **v2** agent implements **no auth**: its `initialize_response`
  (`src/agent-client-protocol-test/src/testy/v2.rs:389-395`) returns only
  `{protocolVersion, info, capabilities: {session: {}}}` — **no `authMethods`** — and it handles only
  `initialize`, `session/new|list|resume|close|prompt` and `session/cancel`
  (`:398-529`); everything else, including `auth/login`/`auth/logout`, falls through to `-32601`
  (`.agents/research/reference-sdks-v2-status.md` items 5–6, verified there by live wire probe).
  Contrast v1's `Testy`, which *does* advertise `authMethods` and `auth.logout` and tracks an
  `authenticated_methods` set (`src/agent-client-protocol-test/src/testy.rs:180,411-418,451-471`).
- The v1↔v2 protocol router does translate the *client* terminal capability when downgrading a v2
  `initialize` to v1: `capabilities.auth.terminal: {}` → `clientCapabilities.auth.terminal: true`, and it
  **rejects** the downgrade as lossy if `terminal._meta` is present
  (`src/agent-client-protocol/src/role/acp.rs:673-689`). Only relevant to a dual-version agent that
  answers `protocolVersion: 1`.

Python (`acp-python-sdk` @ `9d07d787`):

- `acp.experimental.v2` **does** route both methods — a genuine improvement over v1, where `logout` had
  no route at all. `src/acp/experimental/v2/meta.py:5,19` define the names;
  `src/acp/experimental/v2/interfaces.py:47-51` declare `login(method_id, **kwargs)` and
  `logout(**kwargs)` on the `Agent` protocol with `default_result={}`;
  `src/acp/experimental/v2/client.py:74-82` are the client-side callers.
- **If the concrete agent class does not override the handler, the method answers `-32601`**:
  `MethodRouter._handler` returns `None` when the attribute is still the protocol's own stub, and
  `handle_request` raises `RequestError.method_not_found(spec.method)`
  (`src/acp/experimental/v2/_router.py:27-31,36-39`). So a Python-v2 agent that advertises `authMethods`
  but forgets `logout` is automatically non-conformant against V8 — which is the correct outcome.
- A handler returning `None` is normalized to `{}` (`_router.py:42-43`), so V12/V14's object-result shape
  is guaranteed by the SDK.
- Malformed params (e.g. `auth/login` with no `methodId`) become a pydantic `ValidationError`, mapped to
  `-32602` with `data: {"errors": [...]}` by the shared connection
  (`src/acp/experimental/v2/_connection.py:17-24` delegates to `acp.connection.Connection`;
  `src/acp/connection.py:211-212`).
- **No v2 example agent exists** (`.agents/research/reference-sdks-v2-status.md` item 15), so there is no
  Python-side auth behavior to observe either.

**`auth/login` with an unknown `methodId`:** no reference answer exists in v2. Both v2 runtimes would
call the agent's handler with the string as-is (`AuthMethodId` is an unconstrained string); what the
handler does is entirely up to the fixture author. The v1 divergence (Rust `Testy` → `-32602`; Python
example → success `{}`) has simply not been reproduced in v2 because neither side wrote a v2 auth
fixture.

**Deviations, classified:**

| Observation | Classification |
|---|---|
| `testy` v2 advertises no `authMethods` and answers `-32601` to both auth methods | **Conforming.** V9 means the Client must not call them; the TCK's v2 auth tests should SKIP, not FAIL. **Informational** for cross-check purposes: it means the v2 auth suite gets *zero* upstream coverage. |
| Rust `LoginAuthResponse`/`LogoutAuthResponse` are wrapped in `crate::serde_util::default_on_null!` (`agent-client-protocol-schema/src/v2/agent.rs:323-324,416`), so a Rust client decodes `"result": null` as `{}` — while `schema/v2/schema.json:3599,3613` type both as `"object"` with no `"null"` branch | **Lenient decoder vs. strict schema.** Informational, not a bug: the schema is normative, so a TCK should treat `"result": null` as invalid. Consistent with the capabilities-baseline conclusion that the v1 `session/load`→`null` special case must **not** be carried into v2. |
| Python v2 `interfaces.py` mixes unstable `providers_*` methods into the same `Agent` protocol | Out of scope here; noted only so a fixture author does not mistake them for stable v2. |
| Neither SDK ever constructs `Error::auth_required()` / `-32000` in v2 | **Informational**, and it mirrors v1 exactly. Confirms V15 is a real MAY, not an editorial omission. |

---

## Testability notes

Assume the TCK is the *client* and the agent is a black box, on a connection where `protocolVersion: 2`
was negotiated. Anything below that references the negotiated version SKIPs for a v1-only agent.

**What is assertable without any opt-in (pure advertisement, one or two handshakes):**

- V1/V2/V3 — `authMethods` array-ness and per-entry required fields. In v2 these are caught by ordinary
  JSON-Schema validation of the `initialize` response (v1 could not catch a missing `type`), so the
  existing full-exchange schema requirement covers them; a dedicated auth row is redundant.
- V4 — the `_`-prefix rule for custom `type` values. **Not** schema-catchable (the "other" branch takes
  any non-`agent`/`terminal` string). Needs a Python-side check.
- V7 — the terminal negative control. Requires the default handshake to **omit**
  `capabilities.auth.terminal`; then assert no advertised entry has `type == "terminal"`. This is the
  one MANDATORY-tier, unconditionally executable auth test.
- V5/V6 — terminal descriptor validity (`args` strings, `env` `{name,value}`, unique `name`s). Only
  reachable via a **second** handshake that *does* advertise `capabilities.auth.terminal: {}`; then
  conditional on a terminal entry actually appearing. Same two-handshake trick v1 used, but with more to
  validate.
- V24 — `methodId` uniqueness. ADVISORY (description, not a MUST).

**What is assertable with no `--auth-method`, but is *destructive*:**

- V8's logout half. `auth/logout` takes `params: {}`, so the TCK can call it whenever `authMethods` is
  non-empty **without guessing a `methodId` and without violating any client obligation** (V9 is
  satisfied: `authMethods` *is* non-empty). A `-32601` is a hard V8 violation. This is a genuine v2
  upgrade — in v1 the same check was CAPABILITY-tier and only ran when `agentCapabilities.auth.logout`
  was advertised. The cost: against a real agent it revokes the user's live credentials. The v1 suite
  already accepts that cost for `ACP-AUTH-004`; keeping parity is defensible, but a `--no-logout` escape
  hatch would be kind.

**What needs `--auth-method`:**

- V8's login half and V11/V12/V16. The TCK **must not** send `auth/login` with a `methodId` it invented:
  `schema/v2/schema.json:5979` says the id "Must be one of the methods advertised in the initialize
  response", and V13 forbids passing a `terminal` method. So the `auth/login`-is-implemented check can
  only be driven by an operator-supplied, advertised, non-`terminal` method id — exactly today's
  `--auth-method` contract. Without it, SKIP.

**Conforming vs. non-conforming, per observable:**

- *Non-conforming, unconditionally detectable:* a `terminal` entry when the TCK omitted
  `capabilities.auth.terminal` (V7); an entry missing `type`/`methodId`/`name` (V2, via schema); a custom
  `type` not starting with `_` (V4); duplicate `env` names in a terminal descriptor (V6); non-empty
  `authMethods` + `-32601` on `auth/logout` (V8).
- *Non-conforming only after a successful `auth/login`:* `session/new` still `-32000` (V16).
- *Conforming but indistinguishable:* an agent that never gates, one that gates, and one that gates
  lazily on the first LLM call are all conformant (V15, and `docs/rfds/get-auth-state.mdx:27` says so
  explicitly). The TCK cannot tell "does not require auth" from "requires auth but never enforces it".

**Unobservable from a client harness, therefore untestable:** whether `auth/logout` actually invalidated
anything; whether the agent is internally authenticated (there is no `auth/status` in v2 — the proposal
is RFD-only); the entire terminal flow (V21/V22); the fate of sessions or in-flight turns after logout
(V18, undefined by design); whether auth state persists across connections (V25); auth expiry or refresh
(absent from v2 entirely).

### Assertions that must NOT be written (v2)

1. ❌ "Non-empty `authMethods` ⇒ `session/new` fails with `-32000` before `auth/login`." Still only a MAY
   (V15), and `docs/rfds/get-auth-state.mdx:27` names this exact unreliability as the motivating problem.
2. ❌ "`session/resume` / `session/list` / `session/prompt` / `session/close` return `-32000` when
   unauthenticated." Only `session/new` is ever named (V28).
3. ❌ Any specific error code for an unknown `methodId`, a failed login, a cancelled login, or an
   already-authenticated login (V26). Not even `-32602`: in v2 there is no reference convergence to lean
   on, because no reference agent implements the method.
4. ❌ Any assertion about `error.data` on a `-32000` (V20; `auth_methods` was removed from `Error` in
   2026-03-09, `docs/rfds/auth-methods.mdx:196`).
5. ❌ Anything about existing sessions or in-flight turns after `auth/logout` (V18).
6. ❌ "After `auth/logout`, `session/new` fails with `-32000`." V17 is vacuous for a non-gating agent; the
   stronger wording is RFD-only (`docs/rfds/logout-method.mdx:186-196`).
7. ❌ "`auth/login` or `auth/logout` returns `-32601` when `authMethods` is empty." The agent's response to
   a call the spec forbids the Client from making is undefined — **and the TCK must not make the call**
   (V9, an explicit v2 client MUST NOT; stronger than v1's silence).
8. ❌ `authMethods[*].type ∈ {"agent","terminal"}` as a closed set. Must allow `_`-prefixed customs (V4).
9. ❌ "`auth/login` succeeds." A real agent may legitimately reject bad/expired/cancelled credentials.
   Only the *shape* of a success is assertable, and an error must SKIP, not FAIL. (v1 must-NOT #10,
   unchanged.)
10. ❌ Anything about the terminal login process — exit codes, output patterns, reconnect timing (V21).
11. ❌ "`authMethods` is present in the `initialize` result." Optional, and in v2 not even
    `default: []` (V1).
12. ❌ Sending `auth/login` with a `terminal` `methodId`, or with a `methodId` the agent did not
    advertise. Both are client MUST-NOTs (V13); the TCK holds itself to spec.
13. ❌ Treating a **terminal-only** `authMethods` list as an obligation to answer `auth/login` with a real
    login. The MUST-implement sentence is type-agnostic, but a conforming client can never legally send
    `auth/login` for such an agent (see Discrepancy 2) — so do not probe it.
14. ❌ Deriving anything from the presence/absence of agent-side `capabilities.auth` (V10). It gates
    nothing; its only defined property is `_meta`.
15. ❌ That `auth/login` is idempotent, repeatable, required once per connection, or that auth survives a
    reconnect (V25).

---

## TCK design recommendation *(labelled as such — this is my recommendation, not upstream text)*

**1. The `--auth-method` flow carries over, essentially verbatim.** `auth/login`'s params are
byte-identical to v1 `authenticate`'s (`{methodId}`, required), and the semantics of "call it right after
a successful `initialize`, before any session-dependent test" are unchanged. Concretely, only two things
change in `_helpers.connected_agent(...)`:

- the method name string `"authenticate"` → `"auth/login"` (dispatch on the negotiated version);
- the advertisement lookup used by `skip_if_auth_gated`/`current_initialize_auth_methods()` reads
  `authMethods[*].methodId` instead of `authMethods[*].id` — and, if the TCK ever validates that the
  operator's `--auth-method` matches an advertised entry, it must additionally exclude
  `type == "terminal"` entries (V13).

The success/failure handling should stay identical too: an `auth/login` **error** must SKIP with a
distinct reason (never FAIL — must-NOT #9), and only a JSON-object result unlocks the dependent
assertions.

**2. Keep `AUTH-GATED:` and `Verdict.blocked_by_auth` exactly as they are.** The justification is
unchanged and, importantly, **v2 did not strengthen the `-32000` gate**: a `-32000` on `session/new` is
still a MAY, so it is still not a conformance failure, and the run still cannot be honestly scored
conformant when every session-dependent requirement was starved. The `ACP-AUTH-005` carve-out (only
excuse `-32000` when `authMethods` is non-empty) also carries over unchanged, and its citation gets
*better* in v2: an agent with empty `authMethods` that returns `-32000` has locked the client out of a
surface the client is now **explicitly forbidden** to invoke (V9). It is still not a stated agent MUST,
so it stays **ADVISORY** — do not promote it.

**3. Newly testable in v2 (three items):**

- **`auth/logout` becomes a real, ungated MUST** whenever `authMethods` is non-empty, probeable with
  `params: {}` and no operator input. This is the one requirement whose *tier* genuinely rises v1→v2.
  The v1 capability gate `agentCapabilities.auth.logout` **must be retired**, not re-pathed — that path
  does not exist in v2, so a mechanical port would leave the test permanently SKIPPED and silently drop a
  MUST.
- **Custom `type` values must be `_`-prefixed** (V4) — no v1 analogue (v1 treated an unknown `type` as
  `agent` and the v1 report explicitly forbade asserting on it). Note this is one instance of the v2-wide
  open-enum rule (`docs/protocol/v2/extensibility.mdx:111-121`); if the extensibility slice builds a
  shared "known value or `_`-prefixed" helper, this row should use it rather than re-implement it.
- **Terminal descriptor validation** (V5/V6) via the positive second handshake. v1 had only the negative
  control; v2 adds the `env`-name-uniqueness MUST and the `EnvVariable` object shape.

**4. Nothing became newly untestable.** One thing became *cheaper*: `type` is now schema-required, so the
"every entry has a discriminator" check falls out of the existing full-exchange schema validation and
needs no dedicated code.

**5. Handshake plan** (this is the only structural change to the harness): the **default** v2 handshake
must send `capabilities: {}` (or at least omit `auth.terminal`) so the MANDATORY V7 negative control is
live for the whole run; one dedicated test opens a **second** connection advertising
`capabilities: {auth: {terminal: {}}}` and validates whatever terminal descriptors appear. Same trick as
v1, one extra reason to do it.

**6. Cross-check reality check:** `testy` v2 advertises no `authMethods`, so **every** v2 auth
requirement except V7 (which passes trivially) and V4 (vacuous) will SKIP against the only available
upstream v2 agent. The v2 auth suite therefore gets its entire signal from this repo's own fixtures.
Budget for that when writing them.

### Candidate v2 requirement rows

Ids reuse the `2xx` convention; `ACP-AUTH-201/202/203` keep the numbering already floated in
`.agents/research/acp-v2-initialize-capabilities-baseline.md:310-312`.

| Id | Requirement | Tier | v1 lineage | Citation | Conforming / non-conforming |
|---|---|---|---|---|---|
| `ACP-AUTH-201` | When `authMethods` is present, its entries' `methodId`s are unique. Shape (array-ness, `type`/`methodId`/`name` presence) is deferred to the full-exchange schema requirement. | ADVISORY | `ACP-AUTH-001`, re-cited (`id`→`methodId`); same "description, not a MUST" rationale | `schema/v2/schema.json:3526,3574,3443-3444` | **Conforming:** distinct ids. **Non-conforming:** `duplicate_auth_method_id_v2.py` — two entries sharing `methodId`. |
| `ACP-AUTH-202` | No `authMethods[*].type == "terminal"` entry is advertised unless the client advertised `capabilities.auth.terminal`. Checked on a connection that omits it. | MANDATORY | `ACP-AUTH-002`, new client path, **stronger** citation (explicit schema MUST) | `schema/v2/schema.json:3522`; `docs/protocol/v2/authentication.mdx:151-154`; `docs/protocol/v2/initialization.mdx:119-125` | **Conforming:** `conforming_full_v2.py` advertises only an `agent` method on the default handshake. **Non-conforming:** `terminal_auth_unadvertised_v2.py` — always advertises a `terminal` entry. |
| `ACP-AUTH-203` | When `authMethods` is non-empty, `auth/logout` is implemented: it is **not** answered `-32601`, and if it returns a result the result is a JSON object. Nothing is asserted about sessions afterwards. | CAPABILITY, `capability="inferred:authMethods"` (documentation-only string, per the `requirements.py` convention) — the underlying spec tier is **MUST** | **Replaces** `ACP-AUTH-004`; the v1 gate `agentCapabilities.auth.logout` is **retired**, not re-pathed | `docs/protocol/v2/authentication.mdx:51-54,220-223`; `docs/protocol/v2/initialization.mdx:78`; `docs/protocol/v2/overview.mdx:54`; `docs/protocol/v2/migration.mdx:198`; `schema/v2/schema.json:5997-6010,3613-3626` | **Conforming:** `conforming_full_v2.py` — one `agent` method, both auth methods implemented. **Non-conforming:** `advertises_auth_no_logout_v2.py` — advertises `authMethods` but answers `-32601` to `auth/logout`. |
| `ACP-AUTH-204` | With `authMethods` non-empty **and** `--auth-method <id>` given (id must be advertised and non-`terminal`): `auth/login` is not answered `-32601`; if it returns a result, the result is a JSON object; and a subsequent `session/new` does not fail with `-32000`. An `auth/login` *error* SKIPs (with a distinct reason), it does not FAIL. | CAPABILITY, `capability="inferred:authMethods"` — underlying spec tier: MUST (implemented) + declarative (V16) | `ACP-AUTH-003`, method renamed; same opt-in and same narrowing to "no `-32000`" | `docs/protocol/v2/authentication.mdx:51-54,166-193`; `schema/v2/schema.json:5974-5996,3599-3612`; `docs/protocol/v2/schema.mdx:32-33` | **Conforming:** `gated_by_auth_v2.py` run with `--auth-method tck`. **Non-conforming:** `login_then_still_gated_v2.py` — accepts `auth/login` but keeps returning `-32000` from `session/new`. |
| `ACP-AUTH-205` | If `authMethods` is empty or absent, `session/new` does not fail with `-32000`. | ADVISORY | `ACP-AUTH-005`, re-cited; **do not promote** — v2 still states no agent MUST here | `docs/protocol/v2/authentication.mdx:51-54` (client MUST NOT call either method ⇒ no remedy exists); `docs/protocol/v2/schema.mdx:428` (MAY) | **Conforming:** `conforming_v2.py`. **Non-conforming:** `gates_without_auth_methods_v2.py` — empty `authMethods`, `session/new` always `-32000`. |
| `ACP-AUTH-206` | Every `authMethods[*].type` is `"agent"`, `"terminal"`, or begins with `_`. | MANDATORY | **new in v2** (v1's must-NOT #9 forbade the v1 equivalent) | `docs/protocol/v2/authentication.mdx:120-122`; `schema/v2/schema.json:3436,3440`; `docs/protocol/v2/extensibility.mdx:111-121` | **Conforming:** `type: "agent"`, or a custom `"_vendor-sso"`. **Non-conforming:** `custom_auth_type_unprefixed_v2.py` — advertises `type: "gcloud"`. |
| `ACP-AUTH-207` | On a connection advertising `capabilities.auth.terminal: {}`, every advertised `terminal` descriptor is valid: `args` (if present) is an array of strings, `env` (if present) is an array of `{name, value}` objects, and the `name`s are unique. | MANDATORY, conditional on a terminal entry appearing (SKIP otherwise) | **new in v2** (v1 had only the negative control) | `schema/v2/schema.json:3521-3568,3500-3520,3552`; `docs/protocol/v2/authentication.mdx:202-203` | **Conforming:** `conforming_terminal_auth_v2.py` — advertises a terminal method only when the capability is offered, with unique env names. **Non-conforming:** `terminal_auth_dup_env_v2.py` — two `env` entries named `ACP_TOKEN`. |

**v1 ids to retire for the v2 suite** (each superseded above; none should be reused for a v2 test):

| v1 id | Why it must not be carried over as-is |
|---|---|
| `ACP-AUTH-001` | Field renamed `id` → `methodId`. → `ACP-AUTH-201`. |
| `ACP-AUTH-002` | Client capability path changed (`clientCapabilities.auth.terminal: true` → `capabilities.auth.terminal: {}`), and the encoding changed boolean → object marker. → `ACP-AUTH-202`. |
| `ACP-AUTH-003` | Method renamed `authenticate` → `auth/login`. → `ACP-AUTH-204`. |
| `ACP-AUTH-004` | **Retire the capability gate entirely.** `agentCapabilities.auth.logout` does not exist in v2; a mechanical re-path would SKIP forever and drop a real MUST. → `ACP-AUTH-203`. |
| `ACP-AUTH-005` | Semantics unchanged; re-cite to v2 sources. → `ACP-AUTH-205`. |

**Must-NOT-assert list:** the 15 items in the Testability section above. Items 7, 12, 13, 14 and 15 are
new relative to v1 and are the ones most likely to be violated by a well-meaning port of the v1 tests.

---

## Discrepancies

1. **`docs/protocol/v2/migration.mdx:224` is stale about which auth method types are stable.** It says
   "Stable v2 defines `type: "agent"`." — omitting `terminal`. But `docs/protocol/v2/authentication.mdx:102-118`
   documents `terminal` as a stable v2 type, `schema/v2/schema.json:3402-3417,3521-3568` defines it in the
   **stable** artifact, and `docs/rfds/auth-methods.mdx:189-190` records "2026-08-20: Moved terminal
   authentication to Completed and stabilized its v1 and v2 SDK types, schemas, capabilities, and protocol
   documentation." `git log -L 224,224` dates that migration line to `dc3a0a1`, 2026-07-08 — six weeks
   *before* stabilization. **Same failure mode as the already-documented `migration.mdx:191` staleness.
   Trust the schema + `authentication.mdx`; do not derive any requirement from `migration.mdx:224`.**
   *Tier impact: none if you follow the schema; it would wrongly demote `ACP-AUTH-202`/`207` to "unstable"
   if you followed migration.mdx.*

2. **"One or more valid entries" vs. the `agent`-type justification — affects whether a terminal-only
   agent must implement `auth/login`.** The normative sentence is type-agnostic: "Returning one or more
   **valid entries** in `authMethods` … **MUST** implement both `auth/login` and `auth/logout`"
   (`docs/protocol/v2/authentication.mdx:51-54`; `initialization.mdx:78`; `overview.mdx:54`). But both
   places that *explain* it justify it by the `agent` type:
   `authentication.mdx:84-85` ("Because this response contains an **`agent`** authentication method, the
   Agent must support both…") and `migration.mdx:222` ("Because `type: "agent"` defines a protocol-driven
   login flow, including this entry … requires the Agent to support both…"). For an agent advertising
   **only** `terminal` (or only `_custom`) methods, the literal rule still demands `auth/login`, yet V13
   forbids a conforming Client from ever calling it — the requirement would be unobservable and, for
   `terminal`, arguably meaningless. **Tier impact: real.** It is why `ACP-AUTH-204` must be gated on an
   operator-supplied, advertised, non-`terminal` `methodId` rather than fired for any non-empty
   `authMethods`, and why `ACP-AUTH-203` (logout, which *is* always callable) is the row that carries the
   MUST.

3. **The `-32000` gate rests on generated documentation, not on a hand-written normative page** — exactly
   as in v1. The "`session/new` may return `auth_required`" statement exists only in
   `docs/protocol/v2/schema.mdx:428` (generated from `agent-client-protocol-schema/src/v2/agent.rs:5169`)
   and in `docs/protocol/v2/draft/session-setup.mdx:10`. The **stable**
   `docs/protocol/v2/session-setup.mdx` never mentions authentication, and
   `docs/protocol/v2/error.mdx` is still "_Documentation coming soon_". *Tier impact: this is the reason
   `ACP-AUTH-205` stays ADVISORY and why no `-32000`-is-required assertion may be written.*

4. **Rust decoder leniency vs. strict schema on empty responses.** `LoginAuthResponse` /
   `LogoutAuthResponse` are wrapped in `default_on_null!`
   (`agent-client-protocol-schema/src/v2/agent.rs:323-324,416`), so a Rust client accepts
   `"result": null`; the v2 schema types both as `"object"` with no `"null"` branch
   (`schema/v2/schema.json:3599,3613`), and every v2 doc example shows `{}`
   (`authentication.mdx:182-190,234-242`). **Schema wins**; do not port the v1 validator's
   `session/load`→`null` special case. *Tier impact: none, provided you don't port the special case.*

5. **Agent-side `capabilities.auth` is advertise-able but gates nothing, while
   `docs/protocol/v2/initialization.mdx:147` says the Agent SHOULD specify whether it supports `session`
   **and `auth`** capabilities.** Since `AgentAuthCapabilities`'s only property is `_meta`
   (`schema/v2/schema.json:3387-3398`), "specifying" `auth: {}` conveys nothing. Minor doc incoherence;
   **no tier impact** — just never derive a requirement from its presence or absence.

6. **No reference implementation exercises v2 auth at all.** Not a spec conflict, but it removes the
   corroboration that settled several v1 questions. Any v2 auth behavior the TCK asserts is backed by
   spec text alone; where spec text is silent (V25–V27) there is now *no* implementation convergence to
   fall back on either. Treat all of V25–V27 as firmly untestable.

---

## Open questions

Adjacent unknowns for the orchestrator to route elsewhere — I did not pursue these:

1. **The shared open-enum / `_`-prefix checker.** `ACP-AUTH-206` is one instance of the v2-wide rule at
   `docs/protocol/v2/extensibility.mdx:111-121`, which applies to ~10 unions. Whether auth gets its own
   row or reuses a shared helper belongs to the `acp-v2-open-enums-and-extensibility` slice.
2. **Whether the TCK's v2 `initialize` should advertise `capabilities.auth.terminal` by default.** I
   recommend *no* (so `ACP-AUTH-202` stays live) plus a second handshake for `ACP-AUTH-207`, but the
   overall v2 handshake policy — including `capabilities.elicitation` — is the initialize/capabilities
   slice's call.
3. **Dual-version agents and auth.** The Rust router downgrades v2 `capabilities.auth.terminal: {}` to v1
   `clientCapabilities.auth.terminal: true` and errors on lossy `_meta`
   (`[rust] src/agent-client-protocol/src/role/acp.rs:673-689`). Whether the TCK runs both suites against
   one dual-version binary is the version-negotiation slice's question.
4. **Should the destructive auth calls (`auth/logout`, and `auth/login` against a real agent) get an
   explicit opt-out?** Today's v1 suite calls `logout` whenever the capability is advertised. v2 makes
   that call unconditional for any agent with `authMethods`, so the blast radius grows. Product decision,
   not a protocol question.
5. **`auth/status`.** `docs/rfds/get-auth-state.mdx` proposes it with a capability marker; it is absent
   from both `schema/v2/schema.json` and `schema/v2/schema.unstable.json` at this revision. Worth a
   re-check before v2 stabilizes, since it would make "is this agent authenticated?" observable for the
   first time and would change the testability picture substantially.
6. **JSON-RPC batching and `auth/login`.** V23 is a client SHOULD NOT; whether the TCK's batch tests
   should deliberately avoid auth methods belongs to the batching slice.
