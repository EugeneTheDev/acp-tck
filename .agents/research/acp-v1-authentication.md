# What can a client-side TCK assert about ACP v1 authentication behavior of an agent?

**Sources checked:**

- `agent-client-protocol` (spec, source of truth) @ `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`, 2026-09-18
  ("chore: release (#2172)"). `git pull --ff-only` → "Already up to date".
- `acp-rust-sdk` (reference implementation) @ `b28b8ad188d60f2833e6930ef994bcc35f3bcce5`, 2026-09-18.
  `git pull --ff-only` → "Already up to date".
- `acp-python-sdk` (reference implementation) @ `c1004f8c3eafc647b5f4cd51506c5c8a2d9ae347`, 2026-09-11.
  `git pull --ff-only` → "Already up to date". Generated against `schema-v1.21.0` (`schema/VERSION`).
- `a2a-tck`: not consulted; nothing here needed a design analogy.

Citations are repo-relative. Unprefixed = spec repo. `[rust]` = `acp-rust-sdk`. `[py]` = `acp-python-sdk`.

**Confidence:** high — the normative surface is small and I read every v1 occurrence of
`auth`/`auth_required`/`-32000` in the spec repo and both SDKs. The central negative result (no MUST
for `-32000` gating in v1) is triple-confirmed: absence in the docs, absence of any enforcement in
either reference runtime, and the *presence* of exactly that MUST in v2 only.

---

## Answer

**Nothing in ACP v1 requires an agent to gate anything behind `authenticate`.** `-32000`
(`auth_required`) is a *defined error code* (`schema/v1/schema.json:3549`;
`agent-client-protocol-schema/src/v1/error.rs:183`) that `session/new` **MAY** return
(`agent-client-protocol-schema/src/v1/agent.rs:4837`); no v1 document contains a MUST, SHOULD, or
even a declarative "will" tying non-empty `authMethods` to an auth-gated `session/new`. The
canonical reference test agent proves this is not merely a doc omission: `Testy` advertises a
non-empty `authMethods` *and* `auth.logout`, yet its `session/new` handler never consults its own
`authenticated_methods` set and it never constructs a `-32000` error — the string `auth_required`
and the number `-32000` do not appear anywhere in the entire Rust SDK repo. So a TCK can assert the
**shape** of the auth surface (auth-method validity, the client-capability gate on `terminal`,
`authenticate`/`logout` request+response shapes, error-object well-formedness) and a handful of
**conditional** properties (after a successful `authenticate`, `session/new` must not still return
`-32000`; an agent that advertises no auth methods must not lock the client out of `session/new`),
but it must **not** assert that `-32000` is ever returned, which code an unknown `methodId`
produces, or anything at all about sessions after `logout` — the spec explicitly declines to define
that last one (`docs/protocol/v1/authentication.mdx:218-226`). The two reference implementations
disagree on unknown `methodId` (Rust `Testy` → `-32602`; the Python example accepts any ID and
returns `{}`), and the Python SDK does not route `logout` at all, which is decisive evidence that
neither behavior is a protocol contract. v2's `auth/login` / `auth/logout` — which *do* carry the
missing MUSTs — are out of scope.

---

## Requirements

Tier legend: **MUST** / **SHOULD** / **MAY** = stated with that force in a v1 normative source.
**cap:X** = capability-conditional (only applies when X is advertised). **obs** = only applies once
a given observation has already been made. **client-obligation** = a rule on the *client*, hence
not assertable against an agent. **unspecified** = no v1 source states it.

| #  | Requirement | Tier | Citation |
|----|-------------|------|----------|
| 1  | `initialize.result.authMethods` is optional (`required` is `["protocolVersion"]` only); when present it is an array of `AuthMethod`; the default/absent value is `[]` | MAY (agent), shape = MUST | `schema/v1/schema.json:2340,2371-2381`; `docs/protocol/v1/initialization.mdx:79` |
| 2  | Every `AuthMethod` (both variants) REQUIRES `id: string` and `name: string`; `description` is optional/nullable; `_meta` optional | MUST | `schema/v1/schema.json:2736-2782` (terminal), `:2783-2838` (agent) |
| 3  | `type` is the discriminator; **absent `type` ⇒ the method is `agent`** | MUST | `docs/protocol/v1/authentication.mdx:80-82`; `schema/v1/schema.json:2702-2731`; `agent-client-protocol-schema/src/v1/agent.rs:567-584` |
| 4  | An agent MAY advertise a `terminal` method **only when** the client advertised `clientCapabilities.auth.terminal: true`; the schema words this as "Agents MUST advertise this method only when the client enabled its terminal authentication capability" | MUST NOT otherwise (client-cap-conditional) | `docs/protocol/v1/authentication.mdx:107-108,126-128`; `schema/v1/schema.json:2736-2745`, `:4634-4651` |
| 5  | `authenticate` params: `methodId` REQUIRED (typed `AuthMethodId` = string); `_meta` optional; no other fields | MUST | `schema/v1/schema.json:4712-4734`; `docs/protocol/v1/authentication.mdx:151-154`; `docs/protocol/v1/schema.mdx:49` |
| 6  | `authenticate` success result is an empty object (`{}`); only `_meta` is defined on it | MUST | `docs/protocol/v1/authentication.mdx:156-163`; `schema/v1/schema.json:2839-2852` |
| 7  | The `methodId` passed MUST be one of the methods advertised in `initialize`, and MUST NOT be a `terminal` method | client-obligation | `schema/v1/schema.json:4716-4721`; `docs/protocol/v1/authentication.mdx:153,187-188`; `schema/v1/schema.json:2740-2744` |
| 8  | After a successful `authenticate`, the client can create new sessions **without receiving an `auth_required` error** | SHOULD (declarative, no RFC-2119 keyword; the only near-normative agent obligation in the whole flow) | `docs/protocol/v1/authentication.mdx:166-167`; `agent-client-protocol-schema/src/v1/agent.rs:4797-4798` |
| 9  | `session/new` **MAY** return an `auth_required` error if the agent requires authentication | MAY | `agent-client-protocol-schema/src/v1/agent.rs:4837`; `schema/v1/schema.json:4330` (doc-string); `docs/protocol/v1/schema.mdx:498` |
| 10 | `-32000` = "Authentication required" — a predefined, reserved-range error code | MUST (code assignment) | `schema/v1/schema.json:3546-3554`; `docs/protocol/v1/schema.mdx:3389-3392`; `agent-client-protocol-schema/src/v1/error.rs:183,203,219` |
| 11 | Any JSON-RPC error object REQUIRES `code` (integer) and `message` (string); `data` is optional and untyped | MUST | `schema/v1/schema.json:3480-3502` |
| 12 | `logout` is available iff `agentCapabilities.auth.logout` is present; omitted/`null` ⇒ unsupported and clients **MUST NOT** call it; `{}` ⇒ supported | cap:`agentCapabilities.auth.logout` (the MUST NOT is a client-obligation) | `docs/protocol/v1/authentication.mdx:50,74-76`; `docs/protocol/v1/initialization.mdx:233-236`; `schema/v1/schema.json:2666-2701` |
| 13 | `logout` params: `{}` (no required fields, `_meta` only); success result: empty object | MUST (shape) | `docs/protocol/v1/authentication.mdx:196-213`; `schema/v1/schema.json:4735-4748`, `:2853-2866` |
| 14 | After a successful `logout`, *new* sessions that require authentication will require re-authentication | SHOULD (declarative; vacuous for agents that never required auth) | `docs/protocol/v1/authentication.mdx:215-216`; `agent-client-protocol-schema/src/v1/agent.rs:4823-4826` |
| 15 | The protocol does **not** guarantee what happens to already-running sessions after `logout` (terminate / keep running / `auth_required` later are all conformant) | explicitly undefined | `docs/protocol/v1/authentication.mdx:218-226`; `agent-client-protocol-schema/src/v1/agent.rs:4826`; `docs/rfds/logout-method.mdx:198-208` |
| 16 | Clients SHOULD be prepared for post-logout session operations to fail with auth errors | SHOULD (client-obligation) | `docs/protocol/v1/authentication.mdx:224-226` |
| 17 | Terminal auth runs entirely outside the ACP connection (separate process, exit code 0 = success, then reconnect + re-`initialize`); no in-band success signal is defined | MUST/SHOULD, all client-side | `docs/protocol/v1/authentication.mdx:169-188`; `docs/rfds/auth-methods.mdx:136-160` |
| 18 | Agent MUST implement `authenticate` when it advertises a protocol-driven method | **unspecified in v1** (this MUST exists only in v2) | absence in `docs/protocol/v1/authentication.mdx`; contrast `docs/protocol/v2/authentication.mdx:52-54` |
| 19 | Agent behavior for an unknown / not-advertised `methodId` | **unspecified** | no v1 source; reference impls disagree (see Discrepancies) |
| 20 | Agent behavior for `authenticate` when `authMethods` is empty/absent | **unspecified in v1** (v2: clients MUST NOT call) | absence; contrast `docs/protocol/v2/authentication.mdx:53-54` |
| 21 | Whether an agent with empty `authMethods` must accept `session/new` | **unspecified** as an auth rule; but `session/new` is an unconditional baseline method, so an unconditional `-32000` there is unactionable | `docs/protocol/v1/authentication.mdx:44-48` (the only way to authenticate is an advertised method); baseline per prior report Req #2 |
| 22 | Error `data` for `-32000` (e.g. `auth_methods`, `reason`) | **unspecified**; the `auth_methods` field was deliberately *removed* from the `Error` type | `docs/rfds/auth-methods.mdx:196`; `schema/v1/schema.json:3496-3499` |

---

## Details

### 1. Is the `-32000` gate required? (the core question)

Every v1 statement that links `authMethods` to `-32000`, in full:

| Source | Exact force |
|--------|-------------|
| `docs/protocol/v1/authentication.mdx:134-138` | "**When an Agent requires authentication** and the selected method uses the protocol-driven flow, the Client calls `authenticate`…" — describes the client, conditioned on an agent-internal fact. |
| `docs/protocol/v1/authentication.mdx:166-167` | "After successful authentication, the Client **can** create new sessions without receiving an `auth_required` error for authentication-gated requests." — *permissive*, and only about the post-auth state. |
| `agent-client-protocol-schema/src/v1/agent.rs:4837` / `schema/v1/schema.json:4330` | "`session/new` **may** return an `auth_required` error if the agent requires authentication." |
| `agent-client-protocol-schema/src/v1/agent.rs:4793` | "Called **when the agent requires authentication** before allowing session creation." |
| `docs/protocol/v1/overview.mdx:23,57-60` | "`authenticate` **if required by the Agent**". |
| `docs/protocol/v1/session-setup.mdx` | **No mention of authentication at all** (verified by grep over the whole file). |
| `docs/protocol/v1/error.mdx:6` | "_Documentation coming soon_" — there is no v1 error-semantics page. |

So the tier is **MAY**, on a condition ("the agent requires authentication") that the protocol never
makes observable. The only agent-side obligation with any force is the *post*-condition, Req #8.

Three corroborations that this is intentional, not an editorial gap:

1. **v2 added exactly the missing MUSTs.** `docs/protocol/v2/authentication.mdx:52-54`: "An Agent
   that does so **MUST** implement both `auth/login` and `auth/logout`. If `authMethods` is omitted
   or empty, the Agent does not advertise this surface and Clients **MUST NOT** call either method."
   Mirrored in `schema/v2/schema.unstable.json:7600`. The v1 *unstable* schema still carries the old
   permissive text (`schema/v1/schema.unstable.json:6093`), i.e. v1 was not retrofitted.
2. **Neither reference runtime enforces or emits it.** `auth_required` / `-32000` appear **zero**
   times in `acp-rust-sdk` (`src/` and `md/`); the code is only reachable through the spec repo's
   `Error::auth_required()` helper (`agent-client-protocol-schema/src/v1/error.rs:113-117`), which
   nothing in the SDK calls. In the Python SDK the helper exists at `[py] src/acp/exceptions.py:36-38`
   and has **no** caller in `src/`, `tests/`, `examples/`, or `docs/`.
3. **`Testy`, the canonical reference agent, does not gate.** It advertises
   `auth.logout` (`[rust] src/agent-client-protocol-test/src/testy.rs:411`) and one `agent`-type
   method `testy-agent-auth` (`:413-418`), tracks `authenticated_methods`
   (`:180,462,470`), and yet its `session/new` handler
   (`[rust] src/agent-client-protocol-test/src/testy.rs:1867-1882`) never reads that set. Its own
   integration test drives the sequence `authenticate` → `logout` → `session/new` and expects
   `session/new` to **succeed while logged out**
   (`[rust] src/agent-client-protocol-test/tests/testy.rs:75-91`).

**Conclusion:** a TCK that asserts "non-empty `authMethods` ⇒ `session/new` fails with `-32000`"
would fail the reference agent. That assertion must not be written.

### 2. `authenticate` wire shape and error behavior

```
--> {"jsonrpc":"2.0","id":1,"method":"authenticate","params":{"methodId":"agent-login"}}
<-- {"jsonrpc":"2.0","id":1,"result":{}}
```

| Field | Req. | Type | Citation |
|-------|------|------|----------|
| `params.methodId` | **required** | string (`AuthMethodId`) | `schema/v1/schema.json:4712-4731`; `docs/protocol/v1/authentication.mdx:151-154` |
| `params._meta` | optional | object/null | `schema/v1/schema.json:4722-4730` |
| `result` | — | object; only `_meta` defined ⇒ `{}` | `schema/v1/schema.json:2839-2852` |

Errors — **nothing is specified.** There is no v1 error code for "unknown auth method", "auth
failed", "auth cancelled", or "already authenticated". Reference behavior:

- **Missing/malformed `methodId`** → both runtimes produce `-32602`:
  `[rust] src/agent-client-protocol/src/util.rs:33-38` ("deserialization failures become
  `Error::invalid_params` (`-32602`) … which is the correct JSON-RPC error code for malformed method
  parameters"); `[py] src/acp/connection.py:211-212` (pydantic `ValidationError` →
  `RequestError.invalid_params({"errors": …})`). This is implementation convergence, not spec.
- **Unknown `methodId`** → Rust `Testy` returns `-32602` with a message listing supported methods
  (`[rust] src/agent-client-protocol-test/src/testy.rs:451-464`); its test only asserts
  `is_err()`, not the code (`[rust] .../tests/testy.rs:74-79`). The Python example agent
  **accepts anything** and returns `{}` (`[py] examples/agent.py:61-63`, same in
  `[py] tests/conftest.py:287-288`). Divergent ⇒ untestable.
- **Method not implemented** → Python routes `authenticate` to the agent object's `authenticate`
  attribute; if the agent class does not define it the route's `func` is `None` and the SDK answers
  `-32601 Method not found` (`[py] src/acp/agent/router.py:91-97`, `[py] src/acp/router.py:60-66`).
  Note `adapt_result=normalize_result`, so a handler returning `None` still serializes as `{}`
  (`[py] src/acp/utils.py:59-65`) — i.e. the Python SDK guarantees Req #6's empty-object result.

### 3. Auth method types in v1

Only **two** types exist in stable v1. `env_var` is **gone**: "Removed the remaining unstable
`env_var` types and made the Rust SDK decode legacy descriptors as `agent` in both protocol
versions" (`docs/rfds/auth-methods.mdx:191-192`); "Agents using this former experimental method
should replace it with `agent` or `terminal` authentication" (`:170-174`).

| `type` | What the client does | Observable on the ACP wire | TCK-testable? |
|--------|----------------------|----------------------------|---------------|
| absent or `"agent"` | Sends `authenticate {methodId}` and waits for the result (`docs/protocol/v1/authentication.mdx:80-82,134-149`) | fully: the request, the result object, any error | **Yes**, but only the shape — and only under opt-in, since a real agent's `agent` flow may open a browser or mutate persisted credentials |
| `"terminal"` | Launches the *same configured agent program* as a separate interactive process with the descriptor's `args`/`env`, waits for exit (0 = success), then **reconnects and re-`initialize`s** (`docs/protocol/v1/authentication.mdx:169-188`) | **nothing** — the login process is not the ACP connection (`:186-188`); ACP defines no in-band success signal (`:184-186`) | **Only the advertisement**: descriptor validity (`id`, `name` required; `args` array of strings; `env` string→string map — `schema/v1/schema.json:2736-2782`) and the client-capability gate (Req #4). The flow itself is untestable |
| `env_var` / anything else | — | — | **Not a v1 type.** And note: an unknown `type` is *schema-valid* as an `agent` method (see Discrepancies), so a TCK must not reject it |

### 4. `logout`

```
--> {"jsonrpc":"2.0","id":2,"method":"logout","params":{}}
<-- {"jsonrpc":"2.0","id":2,"result":{}}
```

Gated on `agentCapabilities.auth.logout` being *present* (the object-marker convention: omitted or
`null` ⇒ unsupported, `{}` ⇒ supported — `docs/protocol/v1/authentication.mdx:74-76`;
`schema/v1/schema.json:2666-2701`). `LogoutRequest` has no required fields
(`schema/v1/schema.json:4735-4747`); `LogoutResponse` defines only `_meta`
(`:2853-2865`). No errors are specified for `logout` anywhere.

**Post-logout: the prior report's claim is confirmed, and it is stated twice.**
`docs/protocol/v1/authentication.mdx:218-226`: "The protocol does not guarantee what happens to
already-running sessions after `logout`. Agents may terminate them, keep them running, or return
`auth_required` errors for future session activity." Restated in the Rust model doc-comment
(`agent-client-protocol-schema/src/v1/agent.rs:4823-4826`: "There is no guarantee about the behavior
of already running sessions") and deliberate per the RFD ("This is left as implementation-defined …
The RFD intentionally does not mandate a specific behavior to allow flexibility",
`docs/rfds/logout-method.mdx:198-208`). The RFD's stronger "post-condition: subsequent requests that
require authentication **should** return `auth_required`" (`docs/rfds/logout-method.mdx:186-196`) is
**RFD-only design intent and did not make it into the protocol docs** — do not promote it to a test.

Reference behavior: Rust `Testy` clears its `authenticated_methods` set and returns `{}`
(`[rust] src/agent-client-protocol-test/src/testy.rs:466-471`), keeps all sessions alive, and
happily creates new ones afterwards (`[rust] .../tests/testy.rs:83-91`). **The Python SDK does not
implement `logout` at all** — `AGENT_METHODS["logout"] = "logout"` exists
(`[py] src/acp/meta.py:21`) but `build_agent_router` registers no route for it
(`[py] src/acp/agent/router.py:55-117`) and the `Agent` protocol has no `logout` member
(`[py] src/acp/interfaces.py`), so a Python-SDK agent answers `-32601` (`[py] src/acp/router.py:176-182`).
Consequently a Python-SDK agent can never legitimately advertise `auth.logout`.

### 5. Empty / absent `authMethods`

- `authMethods` is **not** in `InitializeResponse.required` (`schema/v1/schema.json:2367-2369`), its
  schema default is `[]`, and the official initialization example ships `"authMethods": []`
  (`docs/protocol/v1/initialization.mdx:79`). `initialization.mdx` has no `ResponseField` entry for
  it at all — it is documented only in `authentication.mdx:44-48`.
- **Must such an agent accept `session/new` without `authenticate`?** Not stated. But the only way
  the protocol offers a client to authenticate is "an advertised authentication method"
  (`docs/protocol/v1/authentication.mdx:44-48,151-154`), so an agent that advertises none and then
  returns `-32000` has made the connection unusable with no defined remedy. Treat as a **defect
  finding, advisory tier** — not MUST.
- **What if a client calls `authenticate` anyway?** v1 says nothing (v2 makes it a client
  MUST NOT, `docs/protocol/v2/authentication.mdx:53-54`). Plausible agent answers all being
  conformant: `-32601` (Python SDK when the handler is absent), `-32602` (Testy-style unknown-ID
  rejection), or `{}` success (Python example agent). A TCK **must not send this request** as part
  of a conformance run: it is a client-side protocol violation in spirit, and the response is
  unspecified. At most run it under an explicit "robustness/informational" opt-in and only assert
  that the connection stays alive.

### 6. v2-only — EXCLUDED

Listed only so the TCK does not accidentally import v2 rules into v1 tests:

- `authenticate` → **`auth/login`**, plus a new **`auth/logout`** (replacing v1's top-level
  `logout`): `docs/protocol/v2/authentication.mdx:8-10,24-25,35-36,210-219`;
  `[rust] src/agent-client-protocol/src/schema/v2_impls.rs:214,303,327`.
- Non-empty `authMethods` ⇒ agent **MUST** implement both `auth/login` and `auth/logout`; empty ⇒
  clients **MUST NOT** call either (`docs/protocol/v2/authentication.mdx:52-58,80-85`;
  `schema/v2/schema.unstable.json:7600`; `docs/rfds/auth-methods.mdx:157-160`).
- v2 renames the descriptor key `id` → `methodId`, makes `env` an array of `{name, value}` objects,
  makes the client capability an object (`auth: {terminal: {}}`), requires unknown method types to
  begin with `_` (`docs/protocol/v2/authentication.mdx:116`), and models unknown types as an
  explicit `AuthMethod::Other` variant (`agent-client-protocol-schema/src/v2/agent.rs:6055-6090`).
- v1↔v2 capability translation exists in the Rust SDK
  (`[rust] src/agent-client-protocol/src/role/acp.rs:673-688`) and is lossy for
  `auth.terminal._meta`.

---

## Testability notes

Everything below assumes the TCK is the *client* and the agent under test is a black box.

**Two execution modes are needed.** Most auth assertions are only reachable if the TCK is allowed to
actually call `authenticate` / `logout`, which for a real agent can open a browser, write credential
files, or revoke a live token. Recommend: default mode = *advertisement-only* (everything derivable
from `initialize` alone, plus passive `-32000` observation); an explicit `--auth` opt-in (with a
configured `methodId`) unlocks the request-level tests; `logout` needs its own opt-in because it is
destructive to the user's real session.

**What a conforming vs. non-conforming agent looks like, per observable:**

- *Non-conforming, unconditionally detectable*: advertises a `terminal` method although the TCK's
  `initialize` omitted `clientCapabilities.auth.terminal` (Req #4); auth-method entries missing `id`
  or `name`; `authMethods` present but not an array; an error object without `code`/`message`.
- *Non-conforming, only after a successful `authenticate`*: `session/new` still fails `-32000`
  (Req #8).
- *Conforming but indistinguishable*: an agent that never gates, an agent that gates, and an agent
  that gates only `session/load` are all conformant. A TCK cannot tell "does not require auth" from
  "requires auth but forgot to enforce it".

**Unobservable from the client, therefore untestable:** whether credentials were actually
invalidated by `logout`; whether the agent is internally in an authenticated state; the terminal
auth flow (a separate OS process — `docs/protocol/v1/authentication.mdx:186-188`); the fate of
active sessions after `logout` (undefined by design, `:218-226`); any notion of auth expiry or
refresh (absent from v1 entirely).

**One harness trick worth noting:** Req #4 requires *two* `initialize` handshakes against the same
agent binary — one with `auth.terminal` omitted (assert no `terminal` method appears) and one with
`auth.terminal: true` (record what appears, assert descriptor validity). This is the only auth test
in the whole area that is both mandatory-tier and unconditionally executable.

### Proposed TCK assertions

**Mandatory** (unconditional; a failure is a spec violation):

| ID | Assertion | Citation |
|----|-----------|----------|
| AUTH-M1 | If `initialize.result.authMethods` is present it is a JSON array (absent ⇒ treat as `[]`) | `schema/v1/schema.json:2371-2381` |
| AUTH-M2 | Every element is an object with a string `id` and a string `name`; `description`, if present, is a string or `null` | `schema/v1/schema.json:2740-2782,2787-2820` |
| AUTH-M3 | Every element whose `type == "terminal"` has `args` = array of strings (if present) and `env` = object of string→string (if present) | `schema/v1/schema.json:2755-2775` |
| AUTH-M4 | When the TCK's `initialize` request omits `clientCapabilities.auth.terminal` (or sends `false`), **no** advertised method has `type == "terminal"` | `docs/protocol/v1/authentication.mdx:126-128`; `schema/v1/schema.json:2736-2745` |
| AUTH-M5 | Any error response the agent sends at any point is a well-formed JSON-RPC error: integer `code`, string `message` | `schema/v1/schema.json:3480-3502` |

**Capability-conditional:**

| ID | Condition | Assertion | Citation |
|----|-----------|-----------|----------|
| AUTH-C1 | `agentCapabilities.auth.logout` present (`{}`) **and** logout opt-in enabled | `logout` with `params: {}` does not fail with `-32601 Method not found` (the capability means "the method is available") | `docs/protocol/v1/initialization.mdx:233-236`; `docs/protocol/v1/authentication.mdx:74-76` |
| AUTH-C2 | same, and the call returned a result | The result is a JSON object (`{}`, or `{_meta: …}`) — not `null`, not a scalar, not an array | `docs/protocol/v1/authentication.mdx:205-213`; `schema/v1/schema.json:2853-2865` |
| AUTH-C3 | `authMethods` contains a method with absent-or-`"agent"` `type`, and `--auth` opt-in supplies that `methodId` | If `authenticate` returns a result, the result is a JSON object | `docs/protocol/v1/authentication.mdx:156-163`; `schema/v1/schema.json:2839-2852` |
| AUTH-C4 | AUTH-C3 succeeded | A subsequent `session/new` does **not** fail with `-32000` | `docs/protocol/v1/authentication.mdx:166-167`; `agent-client-protocol-schema/src/v1/agent.rs:4797-4798` |
| AUTH-C5 | `--auth` opt-in enabled | `authenticate` with `params: {}` (no `methodId`) returns an error rather than a success result — `methodId` is schema-required | `schema/v1/schema.json:4712,4732-4733` (required) |

**Advisory** (report as a warning; the spec permits the behavior but it is incoherent or
implementation-divergent):

| ID | Assertion | Why advisory |
|----|-----------|--------------|
| AUTH-A1 | If `authMethods` is empty/absent, no request fails with `-32000` (an unactionable auth requirement: the client has no advertised flow to satisfy) | v1 never forbids it; only v2 makes the surface rule explicit (`docs/protocol/v2/authentication.mdx:52-54`) |
| AUTH-A2 | If `authMethods` is non-empty and contains a protocol-driven (`agent`) method, `authenticate` is not answered with `-32601` | the "MUST implement" exists only in v2 (`docs/protocol/v2/authentication.mdx:52`; `docs/rfds/auth-methods.mdx:157-160`) |
| AUTH-A3 | `authenticate` with a *not advertised* `methodId` returns an error (not a success) | unspecified; Rust `Testy` errors (`[rust] .../testy.rs:451-464`), the Python example succeeds (`[py] examples/agent.py:61-63`) |
| AUTH-A4 | AUTH-C5's and AUTH-A3's error code is `-32602` | not in the spec; both reference runtimes converge on it (`[rust] src/agent-client-protocol/src/util.rs:33-38`; `[py] src/acp/connection.py:211-212`) |
| AUTH-A5 | Advertised auth-method `id`s are unique within `authMethods` | the schema only *describes* `id` as "Unique identifier" (`schema/v1/schema.json:2740`); no MUST |
| AUTH-A6 | `authMethods` entries carry a non-empty `name` (it is the client's UI label) | required-but-unconstrained string |

**Informational** (record in the report, never pass/fail):

- AUTH-I1: the advertised auth surface — count and types of methods, whether `auth.logout` is
  advertised, whether the agent changed its advertisement when `auth.terminal` was offered.
- AUTH-I2: whether `session/new` was auth-gated at all before `authenticate` (i.e. did any `-32000`
  ever appear), and the full error object when it did.
- AUTH-I3: observed post-`logout` behavior of an already-created session (probe with a cheap
  session-scoped call, record terminate / keep-alive / `-32000`) — purely descriptive, since
  `docs/protocol/v1/authentication.mdx:218-226` blesses all three.
- AUTH-I4: presence of any `type` value other than `agent`/`terminal` (a forward-compat signal, not
  an error — see Discrepancies).

### Assertions that must NOT be written (spec is silent or explicitly non-committal)

1. ❌ "Non-empty `authMethods` ⇒ `session/new` (or `session/load`, `session/list`, …) fails with
   `-32000` before `authenticate`." Only a MAY (`agent-client-protocol-schema/src/v1/agent.rs:4837`),
   and the reference agent `Testy` would fail it (`[rust] src/agent-client-protocol-test/src/testy.rs:1867-1882`,
   `[rust] .../tests/testy.rs:75-91`).
2. ❌ "`session/load` / `session/resume` / `session/prompt` return `-32000` when unauthenticated."
   Even weaker than #1 — only `session/new`'s doc-string mentions `auth_required` at all; the
   `session/load` doc-string does not (`agent-client-protocol-schema/src/v1/agent.rs:4842-4852`), and
   `docs/protocol/v1/session-setup.mdx` never mentions authentication.
3. ❌ Any specific error code for a **failed** authentication, a **cancelled** authentication, or an
   unknown `methodId`. No code is defined; `-32000` means "authentication *required*", not
   "authentication failed" (`schema/v1/schema.json:3549-3553`).
4. ❌ Any assertion about `error.data` on a `-32000` (no `auth_methods`, no `reason`). The
   `auth_methods` field was explicitly removed from the `Error` type
   (`docs/rfds/auth-methods.mdx:196`); `data` is untyped (`schema/v1/schema.json:3496-3499`). The
   `{"reason": "auth_required"}` shape in `docs/rfds/next-edit-suggestions.mdx:558-574` is an RFD
   proposal for an unstable method, not v1.
5. ❌ Anything about **existing** sessions after `logout` — terminated, alive, or erroring are all
   conformant (`docs/protocol/v1/authentication.mdx:218-226`).
6. ❌ "After `logout`, `session/new` fails with `-32000`." The doc only says new sessions "will
   require the user to complete one of the advertised authentication flows **again**"
   (`:215-216`) — vacuous for an agent that never gated. The stronger RFD wording
   (`docs/rfds/logout-method.mdx:186-196`) is design intent only.
7. ❌ "`logout` returns `-32601` when the capability is not advertised." That direction is a
   *client* MUST NOT (`:74-76`); the agent's response to a call it never invited is undefined.
8. ❌ "`authenticate` is rejected when `authMethods` is empty." Unspecified in v1 (v2-only rule) —
   and the TCK should not make the call in a conformance run at all.
9. ❌ "`AuthMethod.type` ∈ {`agent`, `terminal`}." See Discrepancies: an unknown `type` is
   schema-valid as an `agent` method in v1 and the Rust decoder accepts it. The "unknown types must
   start with `_`" rule is v2-only (`docs/protocol/v2/authentication.mdx:116`).
10. ❌ "`authenticate` succeeds." A real agent may legitimately fail (bad credentials, user
    cancelled, network). Only the *shape* of a success is assertable (AUTH-C3).
11. ❌ Anything about the terminal login process (exit code handling, output patterns, reconnect
    timing) — all client-side and off-connection (`docs/protocol/v1/authentication.mdx:169-188`).
12. ❌ "`authMethods` is present in `initialize.result`." Optional, default `[]`
    (`schema/v1/schema.json:2367-2381`).

---

## Discrepancies

1. **Unknown `type` is silently an `agent` method in v1 — schema and intent diverge from v2.** The
   v1 `AuthMethod` union is `#[serde(tag = "type")]` with an **untagged** `Agent` fallback
   (`agent-client-protocol-schema/src/v1/agent.rs:573-584`), and `AuthMethodAgent` neither declares a
   `type` field nor sets `additionalProperties: false` (`schema/v1/schema.json:2783-2838`).
   Therefore `{"id":"x","name":"X","type":"env_var"}` **validates** against the `agent` branch and
   decodes as an `agent` method — which is exactly the documented migration behavior
   ("made the Rust SDK decode legacy descriptors as `agent`", `docs/rfds/auth-methods.mdx:191-192`).
   Meanwhile the prose says "The `type` field acts as the discriminator" (`:2702-2705`) and v1 has no
   `Other` variant, whereas v2 both reserves `_`-prefixed unknown types and models them explicitly
   (`agent-client-protocol-schema/src/v2/agent.rs:6055-6090`). *Consequence for the TCK:* an unknown
   `type` must be treated as an `agent` method (informational), never as a failure.
2. **Reference implementations disagree on unknown `methodId`.** Rust `Testy` → `-32602` with a
   descriptive message (`[rust] src/agent-client-protocol-test/src/testy.rs:451-464`); the Python
   example agent → success `{}` for any ID (`[py] examples/agent.py:61-63`). The spec takes no
   position. Advisory tier only (AUTH-A3).
3. **The Python SDK cannot serve `logout` at all.** The method name is generated
   (`[py] src/acp/meta.py:21`) and the request/response models exist
   (`[py] src/acp/schema.py:1114,1829`), but no route and no `Agent`-protocol member exist
   (`[py] src/acp/agent/router.py:55-117`; `[py] src/acp/interfaces.py`), so the answer is `-32601`.
   This is an SDK gap relative to the stabilized v1 method
   (`docs/rfds/logout-method.mdx:210-212`, "RFD marked as Completed; `logout` is stabilized"), not a
   protocol ambiguity — but it means AUTH-C1 will fail any Python-SDK agent that advertises the
   capability.
4. **Stable v1 docs drop a sentence the v1 *draft* docs carry.** `docs/protocol/v1/draft/session-setup.mdx:10`
   says "If the Agent requires authentication, `session/new` **may** fail with an `auth_required`
   error until the Client completes the authentication flow"; the stable
   `docs/protocol/v1/session-setup.mdx` has no such line. Either way it is a MAY, so it does not
   change any tier — noted so a future reader does not mistake the draft page for stable text.
5. **`authMethods` is undocumented in `initialization.mdx`.** It appears in the example
   (`docs/protocol/v1/initialization.mdx:79`) but has no `ResponseField` entry among the documented
   `initialize` response fields, unlike every capability. Documentation gap, no behavioral effect.

---

## Open questions

1. **`-32000` on client→agent *client-side* methods.** Nothing here covers whether a *client* may
   ever return `-32000` to an agent (e.g. `fs/read_text_file`). Out of scope for an agent-under-test
   TCK, but relevant if the TCK ever gains an agent-side mode.
2. **`nes/*` and `auth_required`.** `docs/rfds/next-edit-suggestions.mdx:558-574` proposes
   `-32000` with `data.reason` on `nes/start` and is the only place any `data` shape for `-32000`
   is sketched. NES is an unstable/RFD surface; whoever owns "unstable v1 methods" should decide
   whether the TCK touches it at all.
3. **Baseline `session/new` conformance with an auth-gating agent.** If the TCK runs its normal
   session/prompt suites against an agent that *does* gate, every one of those tests fails with
   `-32000`. The harness needs a policy (skip-with-reason vs. fail) for "agent requires auth and no
   `--auth` credentials were supplied". That is a harness-design question, not a protocol question.
4. **Whether the TCK should attempt the reconnect half of terminal auth.** Req #17 ends with
   "reconnects and reinitializes"; a TCK *could* verify that a second `initialize` on a fresh
   connection still works, but that is really an initialization/lifecycle test, not an auth test.
