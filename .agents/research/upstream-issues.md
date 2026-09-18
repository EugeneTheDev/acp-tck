# Ready-to-file upstream issue reports

**Sources checked (all pulled `--ff-only` on 2026-09-18, all pulls succeeded):**

| Repo | Local checkout | HEAD verified against |
|---|---|---|
| `agentclientprotocol/agent-client-protocol` (spec) | `/Users/eugene/…/agent-client-protocol` | `d3c1dd78c5f25afbc37a755ebd1982b43dd97069` ("docs: update registry agents (#2180)", 2026-09-18) |
| `agentclientprotocol/rust-sdk` | `/Users/eugene/…/acp-rust-sdk` | `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5` ("chore: release (#348)", 2026-09-18) |
| `agentclientprotocol/python-sdk` | `/Users/eugene/…/acp-python-sdk` | `d92b9683346c9e109895503878315e06d3eedb99` ("chore: migrate HTTP client dependency from httpx to httpx2 (#143)", 2026-09-18) |

**Confidence:** high — every "what the code does" line below was re-read at the HEAD above, not taken
on trust from the earlier research reports.

**Nothing here has been filed.** These are drafts only. Line numbers are HEAD line numbers.

## Summary

| # | Target repo | Title | Severity | TCK fails agents for it today? |
|---|---|---|---|---|
| S1 | spec | `docs/protocol/v1/error.mdx` is an empty stub | medium | no (INFORMATIONAL only) |
| S2 | spec | Baseline prompt content types conflict: `initialization.mdx` vs `content.mdx` | medium | no (forced ADVISORY by the conflict) |
| S3 | spec | `overview.mdx` "Optional Methods" omits five stable v1 agent methods | low | no |
| S4 | spec | Version negotiation: make "MUST NOT echo an unsupported version" explicit | low | n/a (spec clarification for S1/R1/P1) |
| R1 | rust-sdk | `testy` echoes the requested `protocolVersion` verbatim | medium | **yes — ACP-INIT-003, MANDATORY, FAIL** |
| R2 | rust-sdk | `testy` advertises `loadSession: true` but replays nothing | medium | no (passes vacuously; see body) |
| R3 | rust-sdk | `testy` never sets `agentInfo` | low | ADVISORY FAIL (ACP-INIT-004) |
| P1 | python-sdk | `examples/echo_agent.py` echoes the requested `protocolVersion` | medium | **yes — ACP-INIT-003, MANDATORY, FAIL** |
| P2 | python-sdk | Unhandled `_`-prefixed methods return `result: null` instead of `-32601` | medium | ADVISORY FAIL (ACP-JSONRPC-004) |
| P3 | python-sdk | `logout` and `session/delete` have no agent route | medium | would FAIL ACP-AUTH-004 if advertised |
| P4 | python-sdk | Question: stdio transport silently drops malformed lines | question | no |
| P5 | python-sdk | `$/cancel_request` is stabilized in v1 but unimplemented | informational | no |

## Candidates dropped — already fixed at spec HEAD `d3c1dd7`

- **`current_mode_update` documented as `modeId`** — FIXED by `d89c8d3`/`b96b439`.
  `docs/protocol/v1/session-modes.mdx:118` now reads `"currentModeId": "code"`, matching
  `schema/v1/schema.json:4133,4148`.
- **`session/load` empty result shown as `"result": null`** — FIXED by `d89c8d3`.
  `docs/protocol/v1/session-setup.mdx:184` now reads `"result": {}`; the same fix landed at
  `docs/protocol/v1/file-system.mdx:115` for `fs/write_text_file`.
- **`extensibility.mdx` claimed *all* protocol types carry `_meta`** — FIXED.
  `docs/protocol/v1/extensibility.mdx:10-14` now scopes the claim and names `Error` as an exception.

---

# S1 — spec — `docs/protocol/v1/error.mdx` is an empty stub while error codes are fully defined in the schema

**Repo:** `agentclientprotocol/agent-client-protocol` · **Severity:** medium · **Verified at:** `d3c1dd7`

## What the spec says

The entire v1 error page is six lines:

```
docs/protocol/v1/error.mdx:1-6
---
title: "Error"
description: "Error handling in the Agent Client Protocol"
---

_Documentation coming soon_
```

(`docs/protocol/v2/error.mdx` is the identical stub.)

## What the schema defines

`agent-client-protocol-schema/src/v1/error.rs:155-191` defines the complete v1 code set with
doc comments: `-32700` ParseError, `-32600` InvalidRequest, `-32601` MethodNotFound, `-32602`
InvalidParams, `-32603` InternalError, `-32800` RequestCancelled, `-32000` AuthRequired,
`-32002` ResourceNotFound, plus an open `Other(i32)`. None of this is reachable from the docs
site's "Error" page.

## Why it matters for conformance testing

There is no normative v1 text binding a code to a *situation*. Concretely, v1 does not say which
code an agent returns for (a) an unknown/stale `sessionId`, (b) a content block type the agent did
not advertise, (c) a call to a capability-gated method that was never advertised, or (d) whether an
agent advertising `authMethods` must return `-32000` from `session/new` before `authenticate`.
`-32002` and `-32602` exist but are bound to nothing. A TCK therefore cannot write a mandatory
assertion for any of these; ours records the observed code and always passes
(`ACP-INFO-UNKNOWNSESSION-001`, INFORMATIONAL tier). Reference implementations already diverge:
Rust `Testy` answers `-32602` for an unknown `methodId` in `authenticate`
(rust-sdk `src/agent-client-protocol-test/src/testy.rs:451-464`) while the Python example agent
answers success `{}`.

## Suggested fix

Populate `docs/protocol/v1/error.mdx` with (1) the code table generated from `v1/error.rs`, (2) the
`Other(i32)` extension rule, and (3) a short "which code when" section covering at minimum unknown
`sessionId`, unadvertised capability-gated method, unsupported content block, and the `-32000`
pre-authentication contract — even if the answer is an explicit "implementation-defined".

---

# S2 — spec — Baseline prompt content types conflict between `initialization.mdx` and `content.mdx`

**Repo:** `agentclientprotocol/agent-client-protocol` · **Severity:** medium · **Verified at:** `d3c1dd7`

## The conflict

`docs/protocol/v1/initialization.mdx:204`:

> As a baseline, all Agents **MUST** support `ContentBlock::Text` and `ContentBlock::ResourceLink`
> in `session/prompt` requests.

`docs/protocol/v1/content.mdx:31`:

> All Agents **MUST** support text content blocks when included in prompts.

`content.mdx` never restates the `resource_link` obligation, so read alone it narrows the baseline
to text.

## Corroborating evidence for the wider baseline

`PromptCapabilities` (`schema/v1/schema.json:2480`) has gating flags for `image`, `audio` and
`embeddedContext`, but **none** for `resource_link` — consistent with `resource_link` being
ungated baseline rather than an opt-in capability.

## Why it matters for conformance testing

This determines whether "send a prompt containing a `resource_link` block" is a MANDATORY test or an
advisory one. Because the two pages disagree, our TCK is forced to keep it ADVISORY
(`ACP-PROMPT-003`), which means an agent that rejects `resource_link` is not failed — exactly the
kind of hole the initialization page appears to be trying to close.

## Suggested fix

Pick one and make both pages agree. If the `initialization.mdx:204` reading is intended, amend
`content.mdx:31` to "All Agents **MUST** support text and resource link content blocks when included
in prompts", and add the same note to the Resource Link section of `content.mdx`. If the narrower
reading is intended, weaken `initialization.mdx:204` and add a `resourceLink` flag to
`PromptCapabilities`.

---

# S3 — spec — `overview.mdx` "Optional Methods" omits five stable v1 agent methods

**Repo:** `agentclientprotocol/agent-client-protocol` · **Severity:** low · **Verified at:** `d3c1dd7`

## What the docs list

`docs/protocol/v1/overview.mdx:78-103` ("Optional Methods", agent side) lists exactly three:
`session/load` (`:81`), `logout` (`:89`), `session/set_mode` (`:97`). With the baseline methods at
`:50,57,64,72` and the notification at `:107`, the page's total agent inventory is
`initialize`, `authenticate`, `session/new`, `session/prompt`, `session/load`, `logout`,
`session/set_mode`, `session/cancel`.

## What the schema defines

`schema/v1/meta.json` `agentMethods` additionally contains
`session/set_config_option`, `session/list`, `session/delete`, `session/resume`, `session/close` —
all stable v1, all with their own documentation pages (`session-list.mdx`, `session-delete.mdx`,
`session-config-options.mdx`, and `session-setup.mdx:192-213,257-278` for resume/close).

## Why it matters for conformance testing

`overview.mdx` reads as the method index; a TCK (or an agent author) that trusts it will simply not
implement or test five stable methods. We had to derive our method inventory from
`schema/v1/meta.json` instead and note the page as unreliable. Related: `initialization.mdx:243-267`
documents only the `delete` and `additionalDirectories` session capabilities, omitting `list`,
`resume` and `close`, which are schema-only at `schema/v1/schema.json:2538-2597`.

## Suggested fix

Add `ResponseField` entries for the five missing methods to `overview.mdx`'s "Optional Methods", and
the three missing capability markers to `initialization.mdx`'s Session Capabilities section. Ideally
generate the overview inventory from `meta.json` so it cannot drift again.

---

# S4 — spec — Version negotiation: state explicitly that an agent must not echo an unsupported version

**Repo:** `agentclientprotocol/agent-client-protocol` · **Severity:** low · **Verified at:** `d3c1dd7`

## What the spec says

`docs/protocol/v1/initialization.mdx:94-98`:

> The `initialize` request **MUST** include the latest protocol version the Client supports.
> If the Agent supports the requested version, it **MUST** respond with the same version. Otherwise,
> the Agent **MUST** respond with the latest version it supports.
> If the Client does not support the version specified by the Agent in the `initialize` response,
> the Client **SHOULD** close the connection and inform the user about it.

This is normatively unambiguous. The problem is that it is easy to implement wrongly and there is no
worked example of the *unsupported* branch on the page — and `ProtocolVersion` is an open `u16`
newtype (`agent-client-protocol-schema/src/version.rs:12`, with `ProtocolVersion::new(65535)`
exercised at `:104`), so an unknown version deserializes silently instead of erroring.

## What both reference agents do

Both official example agents violate the second sentence: rust-sdk `testy`
(`src/agent-client-protocol-test/src/testy.rs:431`) and python-sdk `examples/echo_agent.py:47` echo
the requested version verbatim. See R1 and P1.

## Why it matters for conformance testing

When both reference implementations get a MUST wrong, the sentence is probably not prominent enough.
Our TCK treats this as MANDATORY (`ACP-INIT-003`) and both reference agents FAIL it, which is the
correct outcome but an awkward one.

## Suggested fix

Add to `initialization.mdx` §Version Negotiation: (1) an explicit "the Agent **MUST NOT** echo back a
version it does not support" sentence, (2) a worked request/response example of the mismatch branch
(client asks `65535`, agent answers `1`), and (3) a note that `protocolVersion` is an open integer,
so implementations must compare against their supported set rather than assuming the value parses
only to a known variant.

---

# R1 — rust-sdk — `testy` echoes the client's requested `protocolVersion` verbatim

**Repo:** `agentclientprotocol/rust-sdk` · **Severity:** medium · **Verified at:** `2a78849`
**TCK status: MANDATORY FAIL** (`ACP-INIT-003`) — `testy` is reported NOT CONFORMANT because of this.

## What the spec says

> If the Agent supports the requested version, it **MUST** respond with the same version. Otherwise,
> the Agent **MUST** respond with the latest version it supports.
> — spec `docs/protocol/v1/initialization.mdx:96` @ `d3c1dd7`

## What the code does

`src/agent-client-protocol-test/src/testy.rs:421-435` — `handle_initialize` responds with
`InitializeResponse::new(request.protocol_version)`, i.e. the requested value, unconditionally.

The SDK core *does* implement correct negotiation
(`highest_compatible_agent_protocol`, `src/agent-client-protocol/src/role/acp.rs:864-874`, called
from `select_agent_protocol` at `:523-551`, which rewrites the params to the selected version) —
but that whole path is `#[cfg(feature = "unstable_protocol_v2")]` (`:519`, `:876`). In the
strict-v1 `--no-default-features` build recommended for conformance fixtures
(`md/testy.md:23-27`), no negotiation runs and `request.protocol_version` is whatever the client
sent, since `ProtocolVersion` is a transparent `u16`
(spec `agent-client-protocol-schema/src/version.rs:12`).

## Minimal repro

Measured by the TCK against a `--no-default-features` build (transcript from this project's
`docs/cross-check.md:107-108`):

```
--> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":65535,"clientCapabilities":{}}}
<-- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":65535, ...}}
```

Expected: `"protocolVersion": 1`.

## Why it matters

`testy` is the reference *agent under test* for client and harness authors; a fixture that violates
a MUST teaches the violation. It also means `testy` cannot be used as a positive fixture for version
negotiation.

## Suggested fix

Clamp in `handle_initialize`: respond with `min(request.protocol_version, ProtocolVersion::LATEST)`
(or the agent's own supported maximum) rather than echoing. Alternatively make the negotiation in
`role/acp.rs` unconditional for v1 rather than gating it behind `unstable_protocol_v2`, which would
fix every agent built on the SDK at once — that is likely the better fix.

---

# R2 — rust-sdk — `testy` advertises `loadSession: true` but replays no `session/update` notifications

**Repo:** `agentclientprotocol/rust-sdk` · **Severity:** medium · **Verified at:** `2a78849`
**TCK status:** currently PASSes (see below) — not a failure today, but a false positive.

## What the spec says

> — spec `docs/protocol/v1/session-setup.mdx:134` @ `d3c1dd7`: on `session/load` the Agent must
> stream the entire conversation history back to the Client via `session/update` notifications
> before responding to the request.

## What the code does

`src/agent-client-protocol-test/src/testy.rs:395` advertises `.load_session(true)`. The handler at
`:1884-1900` calls `upsert_session(...)` and immediately responds with
`LoadSessionResponse::new().modes(...).config_options(...)` — it sends no `session/update`
notifications and keeps no v1 message history to replay. (The v2 path does implement replay,
`md/testy.md:93-95`; this is about the v1 agent.)

## Why it matters for conformance testing

Advertising a capability and then not honouring it is precisely the class of defect a TCK exists to
catch. In practice `testy` escapes: our `ACP-LOAD-002` loads a session that has had no prompt turn,
so "zero updates" is vacuously correct and the test PASSes. That makes `testy` unusable as a
positive fixture for replay — we cannot distinguish "correctly replayed an empty history" from "does
not implement replay". Any TCK that seeds a prompt turn before `session/load` would fail it.

## Minimal repro (reasoned from the code, not measured)

1. `initialize` → `session/new` → `session/prompt` (one completed turn) → note the `sessionId`.
2. Reconnect, `initialize`, then
   `{"jsonrpc":"2.0","id":9,"method":"session/load","params":{"sessionId":"<id>","cwd":"/tmp","mcpServers":[]}}`.
3. Observed: the `session/load` result arrives with zero intervening `session/update` notifications.
   Expected: at least the user and agent message chunks of the seeded turn, all before the response.

## Suggested fix

Either record v1 turn history in `Testy` and replay it as `session/update` notifications before
responding (preferred — it makes `testy` a usable replay fixture), or stop advertising
`load_session(true)` in the v1 capability set so the advertisement matches the behaviour.

---

# R3 — rust-sdk — `testy` never sets `agentInfo` in the `initialize` result

**Repo:** `agentclientprotocol/rust-sdk` · **Severity:** low · **Verified at:** `2a78849`
**TCK status:** ADVISORY FAIL (`ACP-INIT-004`) — does not affect the verdict.

## What the spec says

The `initialize` response carries an `agentInfo` (`Implementation`) object with `name` and `version`
— spec `docs/protocol/v1/initialization.mdx:54,271`, schema `schema/v1/schema.json:2813-2838`.
It is not a MUST, which is why this is filed as a polish item.

## What the code does

`src/agent-client-protocol-test/src/testy.rs:430-434` builds
`InitializeResponse::new(request.protocol_version).agent_capabilities(...).auth_methods(...)` — no
`.agent_info(...)`. `rg agent_info src/agent-client-protocol-test/src/` returns nothing at all.

## Minimal repro

From this project's cross-check run (`docs/cross-check.md:111-116`): the `initialize` result never
contains an `agentInfo` key.

```
--> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}
<-- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,"agentCapabilities":{…},"authMethods":[…]}}
```

## Why it matters

`testy` is the canonical example of a fully-featured agent; omitting `agentInfo` signals that it is
unimportant, and client authors building a UI against `testy` will never see the field populated. It
is also the only optional `initialize` field `testy` does not exercise.

## Suggested fix

Add `.agent_info(Implementation::new("testy", env!("CARGO_PKG_VERSION")))` to the
`InitializeResponse` built in `handle_initialize`.

---

# P1 — python-sdk — `examples/echo_agent.py` echoes the client's requested `protocolVersion`

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** medium · **Verified at:** `d92b968`
**TCK status: MANDATORY FAIL** (`ACP-INIT-003`) — `echo_agent` is reported NOT CONFORMANT for this.

## What the spec says

> If the Agent supports the requested version, it **MUST** respond with the same version. Otherwise,
> the Agent **MUST** respond with the latest version it supports.
> — spec `docs/protocol/v1/initialization.mdx:96` @ `d3c1dd7`

## What the code does

`examples/echo_agent.py:40-47`:

```python
async def initialize(self, protocol_version: int, ...) -> InitializeResponse:
    return InitializeResponse(protocol_version=protocol_version)
```

The requested value is returned unchanged. The SDK exposes the correct answer as
`acp.meta.PROTOCOL_VERSION` (`src/acp/meta.py:50`, `= 1`) and performs no negotiation itself.

## Minimal repro

Measured by the TCK (this project's `docs/cross-check.md:92-108`), against
`uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python echo_agent.py`:

```
--> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":65535,"clientCapabilities":{}}}
<-- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":65535}}
```

Expected: `"protocolVersion": 1`.

## Why it matters

`echo_agent.py` is the copy-paste starting point for Python agent authors, so the defect propagates.

## Suggested fix

In the example: `return InitializeResponse(protocol_version=min(protocol_version, PROTOCOL_VERSION))`
(importing `PROTOCOL_VERSION` from `acp.meta`). Better still, do the clamp centrally in the SDK's
`initialize` route so every Python agent is conformant by default, and add a note to the example.

---

# P2 — python-sdk — Unhandled `_`-prefixed extension methods return `result: null` instead of `-32601`

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** medium · **Verified at:** `d92b968`
**TCK status:** ADVISORY FAIL (`ACP-JSONRPC-004`); the MANDATORY "responds at all" check
(`ACP-EXT-001`) still passes, so the verdict is unaffected.

## What the spec says

> If the receiving end doesn't recognize the custom method name, it should respond with the standard
> "Method not found" error
> — spec `docs/protocol/v1/extensibility.mdx:84`, with a `-32601` example at `:87-94` @ `d3c1dd7`.

## What the code does

`src/acp/agent/router.py:106-111`:

```python
async def _handle_extension_request(name: str, payload: dict[str, Any]) -> Any:
    ext = getattr(agent, "ext_method", None)
    if ext is None:
        raise RequestError.method_not_found(f"_{name}")
    return await ext(name, payload)
```

The `None` guard is dead for any agent that *subclasses* `acp.Agent`: `acp.interfaces.Agent` is a
`Protocol` that declares a default no-op body `async def ext_method(...) -> dict[str, Any]: ...`
(`src/acp/interfaces.py:250`; the `Client` protocol has the same at `:158`). A subclass therefore
inherits a callable stub returning `None`, `getattr` finds it, and `None` is forwarded as the
JSON-RPC `result`. `examples/echo_agent.py:34` does exactly this (`class EchoAgent(Agent)`).

## Minimal repro

Measured (this project's `docs/cross-check.md:133-136`), against `echo_agent.py`:

```
--> {"jsonrpc":"2.0","id":2,"method":"_tck/does_not_exist"}
<-- {"jsonrpc":"2.0","id":2,"result":null}
```

Expected: `{"jsonrpc":"2.0","id":2,"error":{"code":-32601,"message":"Method not found"}}`.

## Why it matters

`result: null` is not a valid response body for any v1 method, and it makes an unimplemented
extension indistinguishable from a successfully handled one. Clients probing for optional extensions
will conclude they are supported.

## Suggested fix

Either drop the `...` default bodies for `ext_method`/`ext_notification` from the `Protocol`
declarations (make them `@abstractmethod`-like / not inheritable), or make the router treat a `None`
return from `ext_method` as "unhandled" and raise `RequestError.method_not_found(f"_{name}")`.

---

# P3 — python-sdk — `logout` and `session/delete` have no agent route, so a Python agent cannot serve them

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** medium · **Verified at:** `d92b968`
**TCK status:** would FAIL `ACP-AUTH-004` (CAPABILITY tier) for any Python agent advertising
`agentCapabilities.auth.logout`; currently SKIPped because no Python agent can advertise it usefully.

## What the spec says

`logout` and `session/delete` are stable v1 agent methods: both are in
`schema/v1/meta.json` `agentMethods`, `logout` is documented at
`docs/protocol/v1/overview.mdx:89` (gated on `agentCapabilities.auth.logout`) and
`docs/protocol/v1/authentication.mdx`; `session/delete` has its own page
(`docs/protocol/v1/session-delete.mdx`). Both RFDs are Completed.

## What the code does

The method names are generated (`src/acp/meta.py:17,21`) and the request/response models exist
(`src/acp/schema.py:1114,1829`; `LogoutCapabilities` at `:3150`), but
`build_agent_router` (`src/acp/agent/router.py:56-104`) registers no route for either, and
`src/acp/interfaces.py`'s `Agent` protocol (`:165-254`) declares neither a `logout` nor a
`delete_session` member. `grep -n "delete_session\|def logout" src/acp/**.py` returns nothing for the
v1 surface. Consequently every such call falls through to the unknown-method path.

## Minimal repro (reasoned from the routing table, not measured — no Python agent can advertise it)

```
--> {"jsonrpc":"2.0","id":5,"method":"logout","params":{}}
<-- {"jsonrpc":"2.0","id":5,"error":{"code":-32601,"message":"Method not found","data":{"method":"logout"}}}
```

Same for `{"method":"session/delete","params":{"sessionId":"…"}}`.

## Why it matters

A Python agent physically cannot honour `agentCapabilities.auth.logout` or the session `delete`
capability, so it can never truthfully advertise them. For a conformance kit this is worse than a
plain gap: the only correct Python behaviour is to advertise nothing, which silently removes two
stable methods from the testable surface for the whole ecosystem.

## Suggested fix

Add `logout` and `delete_session` members to the `Agent` protocol in `interfaces.py` and register
`router.route_request(AGENT_METHODS["logout"], LogoutRequest, agent, "logout", adapt_result=normalize_result)`
and the `session/delete` equivalent in `build_agent_router`, mirroring how `session/close` is wired
at `router.py:70-77`.

---

# P4 — python-sdk — Question: should the stdio transport silently drop malformed lines?

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** question / informational · **Verified at:** `d92b968`
**TCK status:** not asserted (the v1 spec is silent; our TCK records transport behaviour, never fails on it).

## What the code does

`src/acp/_transport.py:73-86` — `receive()` logs and `continue`s on any JSON parse failure:

```python
try:
    message: dict[str, Any] = json.loads(line)
except Exception:
    logging.exception("Error parsing JSON-RPC message")
    continue
```

No response is emitted. The same silence applies to well-formed JSON that is not a valid JSON-RPC
envelope.

## What the Rust SDK does

`src/agent-client-protocol/src/jsonrpc/transport_actor.rs:16-26` replies with `-32700` and
`"id": null`, carrying the offending line in `error.data.line`; invalid envelopes get `-32600`.

## What the spec says

`docs/protocol/v1/transports.mdx` @ `d3c1dd7` is silent on malformed input. JSON-RPC 2.0 §5 says a
server that receives invalid JSON "MUST" reply `-32700` with `id: null`, but ACP does not restate it.

## Why this is a question, not a bug report

Silently dropping may well be deliberate — stdio agents share stdout with stray prints, and a
`-32700` storm in response to log noise would be worse. But the two reference SDKs behaving
oppositely means clients cannot rely on either, and a TCK cannot assert anything here.

## Ask

1. Is the drop-and-log behaviour intentional, or an oversight relative to the Rust SDK?
2. If intentional, would you accept a note in `docs/protocol/v1/transports.mdx` stating that
   malformed-line handling is implementation-defined, so both behaviours are explicitly conformant?

---

# P5 — python-sdk — `$/cancel_request` is stabilized in v1 but not implemented

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** informational · **Verified at:** `d92b968`
**TCK status:** not asserted, and not a conformance failure (see below).

## What the spec says

`$/cancel_request` is stable v1: it is in `schema/v1/meta.json` `protocolMethods`
(`{"cancel_request": "$/cancel_request"}`), documented at `docs/protocol/v1/cancellation.mdx`, and
`docs/announcements/request-cancellation-stabilized.mdx:11` records the stabilization.

## What the code does

Only the name constant exists: `src/acp/meta.py:49`
(`PROTOCOL_METHODS = {"cancel_request": "$/cancel_request"}`), mirrored for v2 at
`src/acp/experimental/v2/meta.py:40`. `rg cancel_request src/acp/` finds no sender, no route and no
handler — the v1 agent router (`src/acp/agent/router.py:56-104`) wires `session/cancel` only. The
Rust SDK implements `$/cancel_request` fully.

## Why it matters for conformance testing

This is *not* a violation — `$/`-prefixed notifications are ignorable by design, so a Python agent
that never acts on `$/cancel_request` is conformant. Filing it so the gap is on record: a Python
agent cannot cancel an outbound client request, and cannot be cancelled at request granularity, so
the Python reference implementation is not usable as a fixture for any `$/cancel_request` test. Note
`examples/echo_agent.py` additionally implements no `session/cancel` handling at all and completes
prompts in single-digit milliseconds, so it is permanently un-cancellable in practice (our
`ACP-CANCEL-001/002` SKIP against it).

## Suggested fix

Implement `$/cancel_request` on both directions of the v1 connection (send on caller-side task
cancellation; on receipt, cancel the in-flight task and answer the original request with `-32800`
`RequestCancelled`, matching the Rust SDK). If that is out of scope for now, a `README`/docs note
that `$/cancel_request` is unimplemented in the Python SDK would prevent the same rediscovery.
