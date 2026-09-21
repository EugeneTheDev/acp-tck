# Exactly how does protocol version negotiation work once ACP v2 exists, and what can a client (the TCK) observe to determine which version(s) an agent supports?

**Sources checked:**
- `check-specification` — `agentclientprotocol/agent-client-protocol` @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e` (2026-09-21, `git pull --ff-only` → "Already up to date"). Note: newer than the `d3c1dd7` the orchestrator quoted.
- `check-rust-sdk` — `agentclientprotocol/rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5` (2026-09-18, `chore: release (#348)`, `agent-client-protocol` v2.2.0).
- `check-python-sdk` — `agentclientprotocol/python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64` (2026-09-21, `refactor(v2)!: expand parameters and derive routes from protocols (#150)`).
- `check-a2a-tck` — **not** consulted; nothing here needed it.

**Confidence:** high on the spec text and schema shapes (verbatim quotes, exact `required` arrays); high on reference-SDK behaviour (read the negotiation code paths and their own tests); medium on the routing recommendation, which is engineering judgement built on those facts.

## Answer

The negotiation **algorithm is unchanged from v1, word for word**: the client sends the latest version it supports as a single integer, the agent returns the same integer if it supports it, otherwise "the latest version it supports"; if the client can't speak what came back, the *client* SHOULD close the connection (`docs/protocol/v1/initialization.mdx:92-98` and `docs/protocol/v2/initialization.mdx:92-96` are identical prose, and `docs/protocol/v2/migration.mdx:26` says so explicitly). What changed is only the **payload around** `protocolVersion`: v2 renames `clientCapabilities`/`agentCapabilities` → `capabilities` and `clientInfo`/`agentInfo` → `info`, and makes `info` **REQUIRED on both sides** (`schema/v2/schema.json:5838`, `:3086`). There is no version list, no capability field, and no other discovery surface — one scalar per connection, and `docs/protocol/v2/migration.mdx:30` states a connection speaks exactly one negotiated version after `initialize`. A v2-capable agent is **not required** to also support v1; dual support is a non-normative recommendation (`docs/protocol/v2/migration.mdx:8,28`). Because the answer is a scalar, a conforming agent's support set is fully recoverable with **two `initialize` probes in two fresh processes** (request `2`, then request `1`): `answer == requested` proves membership, `answer != requested` proves non-membership *and* reveals `max(S)`. Each probe needs a fresh process: the spec never says `initialize` may be sent twice, and both reference SDKs reject a second one with `-32600` ("ACP connections may only be initialized once", `python-sdk src/acp/experimental/negotiation.py:91`, `rust-sdk src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:602-604`) — which vindicates this repo's `rejects_second_initialize.py` assumption. The catch that drives my recommendation: an agent that simply **echoes** the requested version (which is what *both* reference example agents do — `rust-sdk src/agent-client-protocol-test/src/testy.rs:431`, `python-sdk examples/echo_agent.py:47`) is indistinguishable from a real v2 agent on `protocolVersion` alone, so auto-detection needs a corroborating *shape* check on the result and can still be wrong. Therefore: keep an explicit `--protocol-version {1,2,auto}`, default `1`.

## Requirements

Scope: negotiation and the `initialize` envelope only. "Tier" is the spec's own keyword strength; the TCK tier I'd assign is in *Testability notes*.

| # | Requirement | Tier | Citation (repo: spec = `agent-client-protocol`) |
|---|---|---|---|
| 1 | Clients **MUST** initialize the connection by calling `initialize` before a session can be created, sending the latest protocol version supported, its capabilities, and its implementation information | MUST (client) | spec `docs/protocol/v2/initialization.mdx:24-28` |
| 2 | The `initialize` request **MUST** include the latest protocol version the Client supports | MUST (client) | spec `docs/protocol/v2/initialization.mdx:92` |
| 3 | `initialize.params.protocolVersion` is REQUIRED, a single integer `uint16` 0..=65535 identifying a MAJOR version, bumped only for breaking changes | MUST | spec `schema/v2/schema.json:5805-5811`, `:5838` (`"required": ["protocolVersion","info"]`), `:3090-3096` (`ProtocolVersion`); prose `docs/protocol/v2/initialization.mdx:84` |
| 4 | `initialize.params.info` is REQUIRED in v2 (was optional `clientInfo` in v1); `name` and `version` are REQUIRED strings, `title` optional/nullable | MUST (client) | spec `schema/v2/schema.json:5813-5819`, `:5838`; `Implementation` at `:3097-3125` (`required: ["name","version"]`); prose `docs/protocol/v2/initialization.mdx:248` ("Both Clients and Agents **MUST** provide information about their implementation in the `info` field") |
| 5 | `initialize.params.capabilities` is OPTIONAL, defaults to `{}`; omitted capabilities **MUST** be treated as UNSUPPORTED | MAY / MUST(interpretation) | spec `schema/v2/schema.json:5821-5829`; `docs/protocol/v2/initialization.mdx:102-104` |
| 6 | The Agent **MUST** respond with the chosen protocol version, the capabilities it supports, and its implementation information | MUST (agent) | spec `docs/protocol/v2/initialization.mdx:47` |
| 7 | `initialize.result.protocolVersion` is REQUIRED | MUST (agent) | spec `schema/v2/schema.json:3044-3051`, `:3086` |
| 8 | `initialize.result.info` is REQUIRED in v2 (was optional `agentInfo` in v1) | MUST (agent) | spec `schema/v2/schema.json:3052-3058`, `:3086`; `docs/protocol/v2/initialization.mdx:248` |
| 9 | If the Agent supports the requested version, it **MUST** respond with the same version | MUST (agent) | spec `docs/protocol/v2/initialization.mdx:94` |
| 10 | Otherwise, the Agent **MUST** respond with the latest version it supports | MUST (agent) | spec `docs/protocol/v2/initialization.mdx:94`; restated in the schema field doc `schema/v2/schema.json:3045` ("The protocol version the client specified if supported by the agent, or the latest protocol version supported by the agent") |
| 11 | Clients and Agents **MUST** agree on a protocol version and act according to its specification | MUST (both) | spec `docs/protocol/v2/initialization.mdx:86` |
| 12 | If the Client does not support the version the Agent returned, the Client **SHOULD** close the connection and inform the user | SHOULD (**client**, not agent) | spec `docs/protocol/v2/initialization.mdx:96`; schema field doc `schema/v2/schema.json:3045` ("The client should disconnect, if it doesn't support this version") |
| 13 | A single connection speaks exactly one negotiated version after `initialize`; JSON-RPC framing is unchanged by v2 | stated invariant (no RFC keyword) | spec `docs/protocol/v2/migration.mdx:30` |
| 14 | Supporting v1 alongside v2 is **recommended, not required**. "Treat v2 support as additive. Keep serving `protocolVersion: 1` peers when you add v2" | non-normative guidance (lowercase "should"), **not** a MUST/SHOULD keyword | spec `docs/protocol/v2/migration.mdx:8`, `:28`, `:772`; `docs/announcements/acp-v2-draft.mdx:63` |
| 15 | v2 support **MUST** be gated behind explicit version negotiation and feature flags while v2 is draft; negotiating `protocolVersion: 2` does **not** imply any `schema.unstable.json` feature | MUST (implementer guidance) | spec `docs/protocol/v2/migration.mdx:20-22`; `docs/announcements/acp-v2-draft.mdx:61`; nav tag `docs/docs.json:119-120` (`"group": "v2", "tag": "Draft"`) |
| 16 | `initialize` **SHOULD NOT** be batched (lifecycle-sensitive) | SHOULD NOT | spec `docs/protocol/v2/transports.mdx:77-80` |
| 17 | No dedicated error code exists for an unsupported protocol version; the v2 `ErrorCode` set is the same JSON-RPC + ACP set as v1 (`-32700/-32600/-32601/-32602/-32603/-32800/-32000/-32002` plus an open "Other") | — (absence) | spec `schema/v2/schema.json:4150-4215`; `docs/protocol/v2/error.mdx:6` is a stub ("_Documentation coming soon_") |
| 18 | **Not stated anywhere:** whether a client may send `initialize` twice on one connection. The only "reinitialize" story in the spec is *reconnect* (terminal auth) | spec silent | searched all of `docs/` for `initialize (again\|twice\|more than once)`, `re-?initiali`, `only once`, `once per connection`; the only hits are `docs/protocol/v2/authentication.mdx:207` "Reconnects and reinitializes the ACP Agent" (and its v1/draft mirrors) |

### Negotiation algorithm, case by case

Let `N` = version the client requested, `S` = set of versions the agent supports, `M = max(S)`.

| Case | What the spec REQUIRES the agent to return | Citation |
|---|---|---|
| `N ∈ S` | exactly `N`, in a **successful result** | `initialization.mdx:94` (first clause) |
| `N > M` (e.g. `N = 65535`) | `M` | `initialization.mdx:94` (second clause) |
| `N < min(S)` (e.g. v1 client vs. v2-only agent) | `M` — the text says "the latest version it supports", **not** "the highest version ≤ N". So a v2-only agent **MUST** answer `2` to a `protocolVersion: 1` request, and the client then SHOULD close. | `initialization.mdx:94`, `:96` |
| `N ∉ S` but `min(S) < N < M` (sparse support, e.g. `S = {1,3}`, `N = 2`) | `M` (= `3`), by the same clause. There is no "negotiate down" rule in the text. | `initialization.mdx:94` |
| any unsupported `N` | The spec defines **no error response** for a version mismatch. Requirement 10 is a MUST to *respond with a version*, so a JSON-RPC error is non-conforming by implication. There is no explicit "MUST NOT error" sentence. | `initialization.mdx:94`; absence of a code at `schema/v2/schema.json:4150-4215` |
| Client receives a version it cannot speak | Client SHOULD close the connection and inform the user. **The client closes**; nothing obliges the agent to close or to exit. | `initialization.mdx:96` |

**Is a v2-capable agent required to also support v1?** No. There is no MUST or SHOULD. The migration guide and the announcement *recommend* it in lowercase prose (`migration.mdx:8`, `:28`, `:772`; `acp-v2-draft.mdx:63`), and the reference SDKs ship routers specifically to make dual support easy — but a v2-only agent that answers `2` to every request is spec-conforming.

## Details

### `initialize` params — v1 vs v2, field by field

| Field | v1 | v2 |
|---|---|---|
| `protocolVersion` | REQUIRED, `uint16` (`schema/v1/schema.json:4429-4482`, required array at `:4429`+) | REQUIRED, `uint16` — **unchanged type** (`schema/v2/schema.json:5805-5811`, `:5838`) |
| client capabilities | `clientCapabilities`, OPTIONAL, non-empty default `{fs:{readTextFile:false,writeTextFile:false},terminal:false,auth:{terminal:false}}` | renamed `capabilities`, OPTIONAL, default `{}` (`schema/v2/schema.json:5821-5829`) |
| client info | `clientInfo`, OPTIONAL, nullable, doc-noted "in future versions of the protocol, this will be required" | renamed `info`, **REQUIRED**, non-nullable (`schema/v2/schema.json:5813-5819`, `:5838`) |
| `_meta` | optional, nullable object | unchanged (`schema/v2/schema.json:5831-5836`) |

### `initialize` result — v1 vs v2

| Field | v1 | v2 |
|---|---|---|
| `protocolVersion` | REQUIRED | REQUIRED — **unchanged** (`schema/v2/schema.json:3044-3051`, `:3086`) |
| agent capabilities | `agentCapabilities`, OPTIONAL, boolean-ish defaults | renamed `capabilities`, OPTIONAL, default `{}`; all support markers are now **objects** not booleans (`schema/v2/schema.json:3060-3068`; `docs/protocol/v2/migration.mdx:100-104`) |
| agent info | `agentInfo`, OPTIONAL, nullable | renamed `info`, **REQUIRED** (`schema/v2/schema.json:3052-3058`, `:3086`) |
| `authMethods` | array, default `[]` | array, OPTIONAL, no default; non-empty ⇒ agent MUST implement `auth/login` **and** `auth/logout` (`schema/v2/schema.json:3070-3078`; `docs/protocol/v2/initialization.mdx:78`) |
| `_meta` | optional | unchanged (`schema/v2/schema.json:3079-3084`) |

`ProtocolVersion` itself is byte-identical between the two schemas (`schema/v1/schema.json:2408-2414` vs `schema/v2/schema.json:3090-3096`): `{"type":"integer","format":"uint16","minimum":0,"maximum":65535}`. `Implementation` is also identical (`required: ["name","version"]`, optional nullable `title`, optional `_meta`). Rust named constants: `V0 = 0` ("pre-release … should likely be treated as unsupported"), `V1 = 1`, `V2 = 2` — and `V2` is **`#[cfg(feature = "unstable_protocol_v2")]`**, while `LATEST` is deliberately **unavailable** when that feature is on "so code that opts into the v2 draft must choose `V1` or `V2` explicitly" (spec `agent-client-protocol-schema/src/version.rs:19-39`).

Minimal v2 probe (from the docs, `docs/protocol/v2/initialization.mdx:30-45`):

```json
{"jsonrpc":"2.0","id":0,"method":"initialize",
 "params":{"protocolVersion":2,"capabilities":{},
           "info":{"name":"acp-tck","title":"ACP TCK","version":"…"}}}
```

Minimal conforming v2 reply (`docs/protocol/v2/initialization.mdx:49-76`):

```json
{"jsonrpc":"2.0","id":0,
 "result":{"protocolVersion":2,
           "info":{"name":"my-agent","version":"1.0.0"},
           "capabilities":{"session":{}},
           "authMethods":[]}}
```

### Detection from the client side

Observables per connection: **one integer** (`result.protocolVersion`) plus the result's *shape*. There is no version list — I grepped every `*version*` string key in `schema/v2/schema.unstable.json` and the only ones are `protocolVersion`, `ProtocolVersion`, and `Implementation.version`. `schema/v2/meta.json:2` records `"version": 2` but that is a build artifact, not a wire field. No capability field carries a version. The agent registry RFD explicitly *lacks* a protocol-version field (`docs/rfds/acp-agent-registry.mdx:32,160` and the `2026-02-04` changelog entry at `:209` removed `capabilities`), so there is no out-of-band discovery surface either; `docs/rfds/acp-agent-registry.mdx:17` lists "Ensure protocol-version compatibility" only as an unmet need.

**Inference rule** (derived from requirements 9+10; label: derivation, not quoted spec): for a conforming agent, `answer == N ⟺ N ∈ S`, and `answer != N ⟹ answer == max(S)`. Therefore:

| Sequence (each in a **fresh process**) | What it establishes |
|---|---|
| Probe(`2`, v2-shaped params) → `a₂` | `a₂ == 2` ⟹ `2 ∈ S`. `a₂ == 1` ⟹ `2 ∉ S ∧ max(S) == 1` ⟹ `S = {1}` — one probe fully classifies a v1-only agent. |
| Probe(`1`, v1-shaped params) → `a₁` | `a₁ == 1` ⟹ `1 ∈ S`. `a₁ != 1` ⟹ `1 ∉ S ∧ max(S) == a₁`. |
| Probe(`65535`) → `a∞` | `a∞ == max(S)` directly. This is the existing ACP-INIT-003 probe. |

Two probes (`2` then `1`) therefore classify any conforming agent into {v1-only, v2-only, both} without ever needing a third. **(c) Running a conversation:** because the probe's `initialize` consumes the connection's one-shot handshake, the real suite must start from a fresh process anyway — which is exactly what `connected_agent()` already does per test, so the cost is one extra spawn per run, not per test.

**Can a client send `initialize` twice on one connection?**

- *Spec:* silent (requirement 18). The only reinitialization described is a reconnect after terminal auth (`docs/protocol/v2/authentication.mdx:207`).
- *rust-sdk:* rejects it with `-32600` and the message "ACP connections may only be initialized once; reconnect to initialize again" (`src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:602-604`; an in-flight duplicate gets ":600-601"). Caveat: the whole compat layer is a **no-op** without `unstable_protocol_v2` (`protocol_compat.rs:1-102` is the stub `mod imp`), so a v1-only Rust build does *not* enforce this.
- *python-sdk:* the router raises `-32600` "ACP connections may only be initialized once" (`src/acp/experimental/negotiation.py:90-91`), and a strict v2 connection raises `-32600` "ACP v2 connections may only be initialized once" (`src/acp/experimental/v2/_initialization.py:24-26`).
- *rust-sdk's own client-side fallback goes out of its way to avoid a second `initialize`*: when a v2 probe negotiates v1, it either **replays the already-received response** to a freshly built v1 implementation on the same connection (only if the v1 implementation's initialize params are byte-identical to the normalized v2 params) or **opens a brand-new agent connection** and restarts with v1 (`src/agent-client-protocol/src/role/acp.rs:90-98` doc comment, `:196-245` implementation — note `agent()` is called again at `:241`). Its own tests assert exactly one `initialize` reaches the wire (`python-sdk tests/test_protocol_negotiation.py:138,163,190` via `_initialize_count`).

**Conclusion:** each probe must be a fresh process. This confirms, rather than contradicts, this repo's `rejects_second_initialize.py` premise.

### Reference SDK behaviour

Both SDKs ship the same three-layer design: a **strict** v1 endpoint, a **strict** v2 endpoint, and a **router** that picks one from the first `initialize`. v2 is feature-gated (`rust-sdk src/agent-client-protocol/Cargo.toml:53` — and note `unstable_protocol_v2` is *not* part of the `unstable` umbrella at `:37-45`, so this repo's `--no-default-features` cross-check build stays strictly v1) / namespace-gated (`python-sdk src/acp/experimental/v2/`, generated from `schema-v2.0.0-alpha.5` per `src/acp/experimental/v2/meta.py:2`).

#### rust-sdk (`agent-client-protocol` 2.2.0)

| Configuration | requested `1` | requested `2` | requested `65535` | requested `0` |
|---|---|---|---|---|
| v1-only build (no feature) — e.g. `testy` today | echoes `1` | echoes `2` | echoes `65535` | echoes `0` |
| strict v1 endpoint, feature **on** | `1` | `-32600` | `-32600` | `-32600` |
| strict v2 endpoint (`Agent.v2()`) | `-32600` | `2` | `-32600` | `-32600` |
| `AgentProtocolRouter` with v1+v2 (`testy` built with the feature) | `1` | `2` | `2` (params must parse as v2) | `-32600` |

- Echo behaviour: `src/agent-client-protocol-test/src/testy.rs:431` (`InitializeResponse::new(request.protocol_version)`), `src/agent-client-protocol-test/src/testy/v2.rs:389-395` and `:410`, `src/agent-client-protocol/examples/simple_agent.rs:13`, `examples/simple_agent_v2.rs:340-348`. **Every** Rust example/fixture agent echoes the requested version.
- Strict-mode rejection of a non-matching request: `src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:499-516` (`incoming_initialize_request`: anything whose version isn't exactly this endpoint's API version → `unsupported_protocol_version`, which is `Error::invalid_request()` = **-32600**, `:857-865`).
- Strict mode also *overwrites* the outgoing version, so the echo above is harmless on a strict endpoint: `protocol_compat.rs:369` (`set_protocol_version(params, mode.api)` on the client side) and `:480-488` (`set_protocol_version(&mut value, negotiated)` on the response side). A strict v2 Rust client therefore **cannot** probe with `65535`.
- Strict-mode client-side check: if the agent answers a version other than the endpoint's own, the response fails with `required ACP protocol version …` = `-32600` (`protocol_compat.rs:536-541`, `:867-873`). `Client::v2()` documents this as "the initialize request resolves with an error so callers can choose an explicit v1 fallback path" (`role/acp.rs:78-88`).
- Router selection: `role/acp.rs:490-501` (`highest_compatible`: `v2 && requested >= 2 → V2`, else `v1 && requested >= 1 → V1`, else `None`) → `:864-874` turns `None` into `Error::invalid_request()` (**-32600**). Selected-vs-requested mismatch is handled by rewriting the params to the selected version (`:606-639`), so a router-backed agent answers `2` to a `65535` request — i.e. the router **fixes** the echo bug.
- **Router trap for the TCK:** when `requested != selected`, `rewrite_initialize_params` parses the params as `v2::InitializeRequest` (`role/acp.rs:633`, via `parse_initialize_params` `:824-829`), and `v2::InitializeRequest.info` is a required, non-defaulted field (spec `agent-client-protocol-schema/src/v2/agent.rs:58-62`). So the TCK's current ACP-INIT-003 probe — `{"protocolVersion": 65535, "clientCapabilities": {}}` — would get **`-32602` invalid params** from a v2-capable router, for a params-shape reason rather than a negotiation reason. No struct anywhere in the schema crate uses `deny_unknown_fields` (grepped: zero hits), so adding an `info` object alongside `clientCapabilities`/`clientInfo` is safe for both v1 and v2 parsers.
- `testy`'s binary switches on the feature: `Testy::new().protocol_router()` when `unstable_protocol_v2` is on, plain `Testy::new()` otherwise (`src/agent-client-protocol-test/src/bin/testy.rs:10-19`; router built at `src/agent-client-protocol-test/src/testy.rs:229-236`). Its own tests assert `1 → 1` (`tests/testy_v2.rs:414-439`) and `2 → 2` (`tests/testy_v2.rs:56-80`).

#### python-sdk

| Configuration | requested `1` | requested `2` | requested `65535` | requested `0` |
|---|---|---|---|---|
| v1 agent (e.g. `examples/echo_agent.py`) | echoes `1` | echoes `2` | echoes `65535` | echoes `0` |
| strict v2 (`experimental.v2.AgentSideConnection`) | `-32602` | `2` | `-32602` | `-32602` |
| `AgentProtocolRouter(v1=…, v2=…)` | `1` | `2` | `2` (params must parse as v2) | `-32600` |
| `AgentProtocolRouter(v1=…)` only | `1` | `1` | `1` | `-32600` |

- Echo behaviour: `examples/echo_agent.py:40-47` (`return InitializeResponse(protocol_version=protocol_version)`). This is the documented cause of this repo's ACP-INIT-003 cross-check baseline.
- v1 models place no constraint on the value beyond `ge=0, le=65535` (`src/acp/schema.py:5422`) and `model_config` never sets `extra="forbid"` (`src/acp/_schema_base.py:35-38`), so a v1 python agent silently accepts a v2-shaped `initialize` and echoes `2`.
- Strict v2: `src/acp/experimental/v2/_initialization.py:27-31` raises `RequestError.invalid_params` (**-32602**) when `request.protocol_version != 2`; `:34-41` raises `-32600` if the agent's *own* response version isn't 2, so a python strict-v2 agent can never emit a wrong version. Wired in at `src/acp/experimental/v2/agent.py:36-46`.
- Strict v2 **client** closes the connection on a version mismatch, matching requirement 12's SHOULD: `src/acp/experimental/v2/client.py:63-71` (`begin` → `send_request` → `complete`; on any failure, `await self._conn.close()` then re-raise).
- Router selection: `src/acp/experimental/negotiation.py:103-120` — `v2 and requested >= 2 → 2`; `v1 and requested >= 1 → 1`; else `RequestError.invalid_request` (**-32600**) "Unsupported ACP protocol {requested}; configured versions are …". Params are normalized to the selected version at `:57-68` (which validates as `v2.schema.InitializeRequest` whenever `requested >= 2` — same required-`info` trap as Rust), and `:124-128` **validates the downstream agent's answer** against the selected version, so a router-backed python agent also cannot echo a wrong version.
- Its own tests pin the observable behaviour: `tests/test_protocol_negotiation.py:122-142` (router + v2 client → v2 agent), `:144-166` (router + v1 client → v1 agent, answer `1`), and crucially `:169-193` — a **v1-only** router receiving a v2-shaped `protocolVersion: 2` request answers `response["protocolVersion"] == 1`. That is precisely the TCK's v2 probe against a v1 agent, and it works.
- Minor field-semantics divergence: python coerces a non-integer `protocolVersion` to `1` rather than rejecting (`src/acp/_deserialize.py:18-25`), whereas Rust rejects a string outright (spec `agent-client-protocol-schema/src/version.rs:65-70`).

## Testability notes

### What a v2 TCK can assert (candidate requirement rows — my recommendation, not spec text)

| Candidate id | Assertion | Recommended tier | Conforming | Non-conforming |
|---|---|---|---|---|
| `ACP-V2-INIT-001` | `initialize` with `{protocolVersion: 2, capabilities: {}, info: {name, version}}` returns a JSON-RPC **result** (not an error) containing an integer `protocolVersion` | MANDATORY (entry condition for the whole v2 run) | any v2 agent | an agent that errors; a dead agent |
| `ACP-V2-INIT-002` | `result.protocolVersion == 2` | MANDATORY *within a v2 run* (this is the run's premise: if it's `1`, the run should have been routed to v1, so report SKIPPED/NOT_APPLICABLE rather than FAIL — see routing below) | `2` | `1` when `--protocol-version 2` was forced |
| `ACP-V2-INIT-003` | `result.info` is present and is an object with non-empty string `name` and `version` (`title` optional, may be `null`) | **MANDATORY** — note the tier **promotion**: the v1 analogue (`ACP-INIT-004`, `agentInfo`) is ADVISORY because v1 made it optional; v2 makes it required (`schema/v2/schema.json:3086`) | `{"name":"x","version":"1.0"}` | omitted `info`; `agentInfo` used instead |
| `ACP-V2-INIT-004` | Unsupported-version probe: `initialize` with `protocolVersion: 65535` (v2-shaped params, `info` included) must return a result whose `protocolVersion` is `!= 65535` and `>= ` the answer the *same agent* gave to a `protocolVersion: 2` request | MANDATORY (exact structural analogue of today's strengthened `ACP-INIT-003`, incl. the `>=`-not-`==` rule) | router-backed `testy` (answers `2`) | any echoing agent (`testy` v1 build, `echo_agent.py`); any agent that errors |
| `ACP-V2-INIT-005` | Downgrade probe: `initialize` with `protocolVersion: 1` (v1-shaped params) must return a result, never an error — either `1` (agent also speaks v1) or the agent's own latest | **ADVISORY** — see the tier argument below | `1` from a dual agent; `2` from a v2-only agent | `-32600` (rust strict v2) / `-32602` (python strict v2) |
| `ACP-V2-INIT-006` | Negative control: `initialize` params **omitting** `info` — spec-wise the request is malformed, so the agent may reject it. Report only. | **INFORMATIONAL** (spec defines no agent-side validation obligation; Rust/python routers answer `-32602`, a bare v1 agent answers happily) | — | — |
| `ACP-V2-INIT-007` | `initialize` must not be answered with both `result` and `error`, must echo the request id, etc. | already covered by the existing `ACP-JSONRPC-*` family — **no new row needed** | | |

**Tier argument for `ACP-V2-INIT-005`.** The spec text is an unambiguous MUST (requirement 10) and it covers `N < min(S)`: a v2-only agent MUST answer `2` to a `protocolVersion: 1` request. But **both** reference SDKs' strict v2 endpoints violate it by design (`rust-sdk protocol_compat.rs:505-510`; `python-sdk _initialization.py:27-31`), and a client can't distinguish "v2-only agent doing the SDK-idiomatic thing" from "broken agent" without already knowing `S`. Two defensible choices, and I am deliberately not picking silently:
- **MANDATORY** — consistent with how this repo already treats `ACP-INIT-003` (shipped MANDATORY with a documented "both upstream agents FAIL" baseline in `docs/cross-check.md`). Honest to the spec; costs another known-fail row.
- **ADVISORY** (my recommendation) — the TCK's *purpose* for this probe in a v2 run is version discovery, not judgement, and a v2-only agent is a legitimate, spec-permitted product. Report the observed behaviour, never fail the verdict on it. `INFORMATIONAL` would be wrong: the spec is not silent here.

### Unobservable from the client side (therefore untestable)

- **The agent's full support set `S`.** Only `max(S)` and per-probe membership are observable, and only if the agent conforms to requirements 9/10. `S = {1,3}` with `N = 2` is indistinguishable from `S = {3}`.
- **Whether a mismatch was intentional.** No error code distinguishes "unsupported version" from any other `-32600`/`-32602` (requirement 17), so a TCK cannot tell a negotiation refusal from a params-validation failure except by the (non-normative) `error.data` string.
- **The client-side SHOULD (requirement 12).** It constrains the *client*. A TCK that drives agents can only hold *itself* to it: on receiving a version it can't speak, the TCK should close the connection and report, not keep driving. Nothing about it is assertable against an agent.
- **Whether a second `initialize` is legal** (requirement 18). Spec-silent; the SDKs agree it isn't, but that agreement isn't a spec requirement. At most an `INFORMATIONAL` probe — and this repo already has `rejects_second_initialize.py` as a *self*-test proving the suite never sends one, which remains the right posture.
- **That an agent "dropped v1"** as opposed to "never had it". Both look like `a₁ != 1`.

### Concrete fix needed in the *existing* v1 suite

`src/tck/conformance/test_initialize.py`'s ACP-INIT-003 probe sends `{"protocolVersion": 65535, "clientCapabilities": {}}`. Against a v2-capable **router** (the shape `testy` takes when built with `unstable_protocol_v2`, and the shape `AgentProtocolRouter` takes in python), that selects v2 and then validates the params as a v2 `InitializeRequest`, which requires `info` — yielding `-32602` and a spurious FAIL. Adding `"info": {"name": "acp-tck", "version": "<ver>"}` to *both* the 65535 probe and the v1 reference probe is harmless for v1 agents (no schema anywhere sets `additionalProperties: false`, and no Rust struct or pydantic model forbids extra keys) and makes the probe survive a router. This is an adjacent finding I am flagging, not fixing.

## Discrepancies

1. **`N < min(S)`: spec MUST vs. both reference SDKs.** Spec: "Otherwise, the Agent **MUST** respond with the latest version it supports" (`docs/protocol/v2/initialization.mdx:94`) — so a v2-only agent must answer `2` to a `protocolVersion: 1` request. rust-sdk strict v2 answers `-32600` (`src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:505-510`, `:857-865`); python-sdk strict v2 answers `-32602` (`src/acp/experimental/v2/_initialization.py:27-31`); **both routers** also error when `requested < min(configured)` — e.g. `protocolVersion: 0` (`rust-sdk role/acp.rs:490-501` + `:864-874`; `python-sdk src/acp/experimental/negotiation.py:106-120`). All three positions reported; no winner picked.
2. **Echo vs. negotiate.** The spec requires an unsupported `N` to come back as `max(S)`. Every stock reference *agent implementation* echoes `request.protocol_version` verbatim (`rust-sdk testy.rs:431`, `testy/v2.rs:389-395`, `examples/simple_agent.rs:13`, `examples/simple_agent_v2.rs:340-348`; `python-sdk examples/echo_agent.py:47`). It only comes out right because the surrounding SDK layer overwrites or validates the value — a *strict* endpoint forces it (`rust-sdk protocol_compat.rs:480-488`; `python-sdk _initialization.py:34-41`), and a *router* rewrites the request and re-checks the answer (`rust-sdk role/acp.rs:606-639`; `python-sdk negotiation.py:122-128`). With **no** version machinery — the plain v1 build, which is what this repo cross-checks — the echo reaches the wire. This is the already-documented `ACP-INIT-003` baseline; it will reproduce verbatim in v2 for any agent not using a router.
3. **`initialize` twice:** spec silent (requirement 18) vs. both SDKs rejecting with `-32600`. Not a conflict so much as an unspecified area the implementations have already settled.
4. **Docs vs. schema on nothing.** For once, `docs/protocol/v2/initialization.mdx` and `schema/v2/schema.json` agree completely on the `initialize` envelope, including the required-`info` change (prose `:248`, schema `:3086`/`:5838`). No v1-style docs/schema drift found in this area.
5. **`protocolVersion` deserialization leniency:** python coerces a non-integer to `1` (`src/acp/_deserialize.py:18-25`); Rust rejects (spec `agent-client-protocol-schema/src/version.rs:65-70`). Schema says `integer` (`schema/v2/schema.json:3092`). Minor; only matters if the TCK ever probes with a string version.

## Recommendation for the TCK's routing (my recommendation, **not** a spec requirement)

**Ship `--protocol-version {1,2,auto}` (plugin: `--tck-protocol-version`), default `1`. Auto-detect is useful but not reliable enough to be the default, and a flag is required regardless.**

**1. One probe per fresh process reveals a lot.** A single `initialize` with `protocolVersion: 2` and v2-shaped params classifies a *conforming* agent completely in the v1-only case (`a₂ == 1 ⟹ S = {1}`, exactly what `python-sdk tests/test_protocol_negotiation.py:169-193` demonstrates) and proves `2 ∈ S` in the v2 case. A second probe with `protocolVersion: 1` tells you whether the agent *also* speaks v1. Two spawns, deterministic, no second `initialize` needed on either connection.

**2. But auto-detect is not reliable, for four independent reasons.**
   - *Echoing agents.* `a₂ == 2` does **not** prove v2 support: a v1 agent that echoes answers `2` (`rust-sdk testy.rs:431`; `python-sdk examples/echo_agent.py:47`) — and those are the two agents this repo already cross-checks against. The only corroborating signal is the *shape* of the result: v2 **requires** `info` (`schema/v2/schema.json:3086`) and has no `agentInfo`/`agentCapabilities`, so `result.info` present + `agentInfo`/`agentCapabilities` absent is a strong v2 marker, and the converse is a strong v1 marker. That is a heuristic built on a *required* field, which is about as good as heuristics get here — but a v1 agent that echoes `2` and omits the optional `agentInfo` emits `{"protocolVersion":2,"agentCapabilities":{}}`, which differs from a conforming v2 reply only by an **absence**. The TCK cannot tell "v2 agent violating the `info` MUST" from "v1 agent violating the negotiation MUST". Unresolvable from the wire.
   - *Agents that gate v2 behind their own flag.* The spec instructs implementers to put v2 behind feature flags while it's draft (`docs/protocol/v2/migration.mdx:20`; `docs/announcements/acp-v2-draft.mdx:61`), and the reference SDKs do exactly that (`rust-sdk Cargo.toml:53`; `python-sdk src/acp/experimental/`). Whether a given binary was built/launched with v2 on is not discoverable over ACP.
   - *A dual-version agent's v1 surface would never be tested.* "Highest wins" auto-detect always picks v2, yet the spec's own recommendation is that agents keep serving v1 peers (`docs/protocol/v2/migration.mdx:28`). Testing that recommendation requires forcing `--protocol-version 1` on a v2-capable agent.
   - *Backward compatibility of this repo's CLI.* Today `acp-tck -- <agent>` means "test v1". If `auto` became the default, an echoing v1 agent would silently flip to being scored against the whole v2 suite and fail nearly everything for the wrong reason. Default `1` keeps every existing invocation and every documented cross-check baseline stable; users opt in.

**3. Therefore:**
   - `--protocol-version 1` (**default**) — today's behaviour, unchanged. No probe, no extra spawn.
   - `--protocol-version 2` — skip detection entirely, run the v2 suite, and let `ACP-V2-INIT-002` FAIL loudly if the agent answers `1`. This is the mode CI should pin for a known-v2 agent.
   - `--protocol-version auto` — probe once (`protocolVersion: 2`, v2-shaped params, fresh process), then route:
     | Probe result | Route | Report |
     |---|---|---|
     | `result.protocolVersion == 2`, `result.info` present, no `agentInfo`/`agentCapabilities` | v2 suite | "negotiated v2" |
     | `result.protocolVersion == 1` | v1 suite | "agent negotiated down to v1" |
     | `result.protocolVersion == 2` but v1-shaped result (`agentInfo`/`agentCapabilities` present, `info` absent) | **v1 suite** (conservative) | **ambiguous** — record it prominently and fail/flag the negotiation requirement; this is the echoing-agent case |
     | JSON-RPC error | v1 suite | "agent cannot negotiate v2: `<code> <message>`" |
     | any other integer (`0`, `3`, …) | abort the run | the TCK holds itself to requirement 12: close the connection, inform the user, exit non-zero |
     Always discard the probe process and spawn fresh for the suite — the handshake is one-shot (requirement 18 + both SDKs' `-32600`).
   - The resolved version belongs in the JSON report as a new top-level key (e.g. `negotiated_protocol_version`) next to `protocol_version`, and in the terminal summary header. `tck.protocol.PROTOCOL_VERSION = 1` can no longer be a single global truth.
   - **Do not** run a v2 agent through the v1 suite automatically. Two protocol surfaces in one run would need two distinct schema/method inventories, two `_helpers` prompt drivers (v2's prompt response no longer ends the turn), and a verdict model that spans both. If dual-surface coverage is wanted, run the tool twice (`--protocol-version 1` then `2`) and, if that becomes routine, add `--protocol-version 1,2` as sugar for two sequential runs writing two report sections — not as a single interleaved run.
   - **Keep the v1 and v2 suites, registries, and vendored schemas fully separate**, per the spec's own SDK guidance (`docs/protocol/v2/migration.mdx:764`: "Keep v1 and v2 schemas, generated models, and test fixtures fully separate"). Vendor `schema/v2/schema.json` + `schema/v2/meta.json` alongside the v1 pair, and keep requirement ids namespaced (`ACP-V2-*`) so `tests/test_registry.py`'s two-way check stays meaningful per version.
   - **Treat v2 requirements as draft-tracking.** `docs/docs.json:119-120` tags v2 "Draft", the schema is at `2.0.0-alpha.5` (`schema/v2/Cargo.toml:3`), and `docs/announcements/acp-v2-draft.mdx:59` warns "various pieces can, and will, change before stabilization". Record the exact `schema-v2.0.0-alpha.N` in `VENDORED.md` and expect churn.

## Open questions

- **The rest of the v2 `initialize` result surface** — `capabilities.session` as a baseline-method marker, the object-vs-boolean support-marker change, `authMethods[*].methodId`/`type`, `auth/login`/`auth/logout` — is the v2 capability-gating question, not the negotiation question. Owned elsewhere (`docs/protocol/v2/initialization.mdx:145-244`, `docs/protocol/v2/migration.mdx:100-145`).
- **v2 prompt lifecycle** (`session/prompt` no longer ends the turn; stop reason moves to an idle `state_update`) rewrites `_helpers.run_prompt` and the whole cancel-race design. Large, separate, and a prerequisite for a usable v2 suite.
- **JSON-RPC batch support on stdio** is new in v2 (`docs/protocol/v2/transports.mdx:40-80`) and touches the harness's line reader and `validate_agent_message` dispatch. Separate.
- **Which v2 schema artifact to vendor** — stable `schema/v2/schema.json` vs `schema.unstable.json`, and how `meta.unstable.json`'s extra surfaces (`nes/*`, `providers/*`, `document/*`, `mcp/*`, `session/fork`) should be excluded. Note the python SDK's v2 `meta.py` is generated from the **unstable** meta (`python-sdk src/acp/experimental/v2/meta.py:1-41`), so its method inventory is wider than stable v2's (`spec schema/v2/meta.json`). Needs a decision.
- **Should the TCK assert requirement 12 on itself** (close the connection on an unspeakable version) as a self-test, the way `rejects_second_initialize.py` self-tests the no-second-`initialize` rule? `python-sdk src/acp/experimental/v2/client.py:63-71` is the reference precedent.
- **Fix ACP-INIT-003's probe params** (add `info`) so the existing v1 suite survives a v2-capable router-based agent. Small, concrete, and in the *v1* suite — routing to a programmer, not a researcher.
