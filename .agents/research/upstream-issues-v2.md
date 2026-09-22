# Ready-to-file upstream issue reports — ACP **v2** (Draft)

**Nothing here has been filed.** These are internal drafts only (user decision, `.agents/plan.md`
"Decisions … License / upstream issue drafts remain internal"). Line numbers are HEAD line numbers
at the revisions below. Companion to `.agents/research/upstream-issues.md` (v1); ids continue that
file's `S*/R*/P*` lettering but restart numbering inside a `v2-` prefix so the two files never
collide.

**Sources checked** (each pulled `git pull --ff-only` on 2026-09-22; all three pulls succeeded —
the "Cannot fast-forward to multiple branches" failure recorded in `.agents/state.md` did **not**
reproduce):

| Repo | Local checkout | HEAD verified against |
|---|---|---|
| `agentclientprotocol/agent-client-protocol` (spec) | `…/agent-client-protocol` | `b9d6aca6757d0f5b6e435cad54f9f04657aa9802` (2026-09-22). `git diff --stat 8f76d6c..b9d6aca -- docs/protocol/v2 schema/v2 docs/rfds/v2` is **empty**, so every line number here is also valid at the TCK's pinned `8f76d6c`. |
| `agentclientprotocol/rust-sdk` | `…/acp-rust-sdk` | `28688b2d97a81975ff875180c3a3e46e6cad0161` (2026-09-21) |
| `agentclientprotocol/python-sdk` | `…/acp-python-sdk` | `9d07d7871ef4b220b8507e15fc4b1560f0950a64` (2026-09-21) = `1.0.0rc2` |

**Confidence:** high — every "what the code does" claim below was re-read at the HEAD above, and
the two runtime claims (P-v2-1, the batch crash; and the strict-version errors) were reproduced or
traced line by line, not taken on trust from the earlier research reports.

## Summary

| # | Target repo | Title | Severity | TCK fails agents for it today? |
|---|---|---|---|---|
| S-v2-1 | spec | `AgentCapabilities.session` doc comment still lists a 4-method baseline; every other source says 7 | medium | no (TCK follows the 7-method reading) |
| S-v2-2 | spec | `migration.mdx:191`: "Stable v2 currently defines no standard Client capability fields" is stale | medium | no (TCK ignores it, per research) |
| S-v2-3 | spec | `migration.mdx:224`: "Stable v2 defines `type: "agent"`" omits the stabilized `terminal` type | low | no |
| S-v2-4 | spec | `IdleStateUpdate.stopReason` is documented **SHOULD** in the schema and **MUST** in the prose | medium | **yes — ACP-STATE-203, CAPABILITY, FAIL** |
| S-v2-5 | spec | `cancellation.mdx:49` sequence diagram still shows an empty `session/prompt` response | low | no |
| S-v2-6 | spec | `docs/protocol/v2/error.mdx` is still "Documentation coming soon" | medium | no (INFORMATIONAL only) |
| S-v2-7 | spec | `session/set_config_option`'s availability is unstated: no capability marker, no baseline statement | question | no (TCK uses an inferred gate) |
| S-v2-8 | spec | Batch composition is restricted by the schema but by no prose and not by JSON-RPC 2.0 | question | no (INFORMATIONAL probe only) |
| P-v2-1 | python-sdk | A JSON-RPC **batch array** on stdin crashes the receive loop (`AttributeError`) | high | **yes — ACP-BATCH-201/202, MANDATORY, FAIL** |
| P-v2-2 | python-sdk | A strict v2 endpoint answers a lower requested `protocolVersion` with an error instead of negotiating down | high | **yes — ACP-INIT-202, MANDATORY, FAIL** |
| P-v2-3 | python-sdk | The shipped `acp.experimental.v2` bindings are generated from the **unstable** v2 schema | medium | would FAIL ACP-ENUM-202 (ADVISORY) if an unstable-only update is emitted |
| R-v2-1 | rust-sdk | A strict single-version endpoint answers an unsupported `protocolVersion` with `-32600` instead of negotiating down | high | **yes — ACP-INIT-202, MANDATORY, FAIL** |
| R-v2-2 | rust-sdk | `md/testy.md:86` says v2 `session/prompt` "returns an empty acceptance response" | low | no (docs only; the code is correct) |

---

# S-v2-1 — spec — `AgentCapabilities.session`'s doc comment still describes a 4-method baseline

**Repo:** `agentclientprotocol/agent-client-protocol` · **Severity:** medium · **Verified at:** `b9d6aca`

## What the spec says

`agent-client-protocol-schema/src/v2/agent.rs:3947-3952` (the generator source):

```rust
/// Session capabilities supported by the agent.
///
/// Optional. Omitted or `null` both mean the agent does not support the
/// `session/*` method surface. Supplying `{}` means the agent supports the
/// baseline session methods: `session/new`, `session/prompt`,
/// `session/cancel`, and `session/update`.
```

This is generated verbatim into `schema/v2/schema.json:3128` and rendered at
`docs/protocol/v2/schema.mdx:1345`.

## Why it is wrong

Five independent sources say the baseline is **seven** methods, not four:

- `agent-client-protocol-schema/src/v2/agent.rs:4138-4142` → `schema/v2/schema.json:3160`
  (`SessionCapabilities`'s own description): "`session/new`, `session/list`, `session/resume`,
  `session/close`, `session/prompt`, `session/cancel`, and `session/update`".
- `docs/protocol/v2/migration.mdx:190`: "advertising `capabilities.session` at all now
  **requires** supporting the baseline methods `session/new`, `session/list`, `session/resume`,
  `session/close`, `session/prompt`, `session/cancel`, and `session/update`".
- `docs/protocol/v2/initialization.mdx:152`.
- `docs/protocol/v2/session-list.mdx:10`: "Agents that support the `session` method surface
  **MUST** support `session/list`."
- `docs/protocol/v2/session-setup.mdx:83-84` (`session/resume`) and `:237-239` (`session/close`).

There is also no alternative marker the 4-method reading could point at: `SessionCapabilities`'s
property set is exactly `{prompt, mcp, delete, additionalDirectories, _meta}`
(`schema/v2/schema.json:3159-3218`) — there is no `list`/`resume`/`close` key to set.

## Root cause

The 4-method text landed 2026-06-18 (`2b4fcab`); the 7-method wording landed 2026-07-02 in
`a57b538` ("feat(unstable-v2): Unify session/load and session/resume (#1584)"), which is exactly
when `session/load` folded into `session/resume` and the per-method markers were dropped. The
outer field's comment was never updated.

## Suggested fix

Update the doc comment on `AgentCapabilities::session` (`agent.rs:3947-3952`) to the same
seven-method list `SessionCapabilities` already uses, and regenerate `schema/v2/schema.json` and
`docs/protocol/v2/schema.mdx`.

## Impact on implementers

An agent author reading only the outer comment would advertise `capabilities.session: {}` while
implementing four methods, and would then fail conformance against
`session/list`/`resume`/`close`. This is the single doc line most likely to produce a
non-conforming v2 agent.

---

# S-v2-2 — spec — `migration.mdx:191` claims stable v2 defines no Client capability fields

**Repo:** spec · **Severity:** medium · **Verified at:** `b9d6aca`

`docs/protocol/v2/migration.mdx:191`:

> The v1 Client capabilities `fs` and `terminal` are removed entirely … **Stable v2 currently
> defines no standard Client capability fields.** Agent-owned terminal display is baseline
> behavior, not a Client execution capability.

Contradicted by the stable schema itself: `$defs/ClientCapabilities`'s property set is
`{auth, elicitation, _meta}` (`schema/v2/schema.json`, `ClientCapabilities`), with
`$defs/AuthCapabilities.terminal` and `$defs/ElicitationCapabilities.{form,url}` beneath them —
and by `docs/protocol/v2/authentication.mdx:127-154` and `docs/protocol/v2/elicitation.mdx:24-55`,
which document both as normative.

**Root cause:** the sentence was written in `dc3a0a1` (2026-07-08), before `2c66dec` "stabilize
elicitation" (2026-07-24) and `4effcc1` "stabilize terminal authentication" (2026-08-20).

**Suggested fix:** replace the sentence with a list of the three stable client capability fields
(`auth.terminal`, `elicitation.form`, `elicitation.url`) and keep the "v1 `fs`/`terminal` are
removed" clause.

**Why it matters:** a v2 client implementer following this line would advertise nothing, and an
agent would then be forbidden (`$defs/AuthMethodTerminal`: "Agents MUST advertise this method only
when the client enabled its terminal authentication capability") from offering terminal auth at
all — silently disabling a stabilized feature.

---

# S-v2-3 — spec — `migration.mdx:224` omits the stabilized `terminal` auth method type

**Repo:** spec · **Severity:** low · **Verified at:** `b9d6aca`

`docs/protocol/v2/migration.mdx:224`: "Stable v2 defines `type: "agent"`. Custom types **MUST**
begin with `_`."

But `$defs/AuthMethod` (`schema/v2/schema.json:3399-3495`) has three branches: `agent`,
`terminal` (`$defs/AuthMethodTerminal`, `schema.json:3522`), and the open `other` fallback; and
`docs/protocol/v2/authentication.mdx:120-122` documents both defined types.

Same failure mode as S-v2-2 — the sentence predates `4effcc1` "stabilize terminal authentication".

**Suggested fix:** "Stable v2 defines `type: "agent"` and `type: "terminal"`."

---

# S-v2-4 — spec — `IdleStateUpdate.stopReason`: schema says SHOULD, prose says MUST

**Repo:** spec · **Severity:** medium · **Verified at:** `b9d6aca`

Two normative statements about the *same* condition disagree on strength:

- `docs/protocol/v2/prompt-lifecycle.mdx:348`: "When the Agent is ready to process a new prompt,
  it **MUST** report `idle` with a `state_update` notification. **When the transition ends
  foreground work, the Agent MUST include the corresponding `StopReason`**."
- `agent-client-protocol-schema/src/v2/client.rs:845-852` → `schema/v2/schema.json:4909`
  (`$defs/IdleStateUpdate.stopReason`): "Optional. Omitted or `null` both mean the agent is not
  reporting a stop reason. **Agents SHOULD include this when the idle transition ends foreground
  work.**"

The field is legitimately schema-optional, because the same `$def` also serves the *initial
ready-state* idle that ends no turn (emitted right after `session/new` by the Rust reference,
rust-sdk `src/agent-client-protocol/examples/simple_agent_v2.rs:362-368`). That is not the disagreement: the disagreement is that the doc
comment restates the *turn-ending* case — the one the prose makes a MUST — as a SHOULD.

**Suggested fix:** change `client.rs:848` to "Agents **MUST** include this when the idle
transition ends foreground work; it is omitted only for an idle that does not end foreground work
(for example the initial ready state)." Regenerate the schema and `schema.mdx`.

**Impact:** this is the one item in this file that makes the TCK fail an agent that followed a
literal reading of the schema. `ACP-STATE-203` (CAPABILITY tier, scoped to the idle that
terminates an observed `running` turn) asserts the stop reason is present; a SHOULD-following agent
FAILs and the run is reported NOT CONFORMANT.

---

# S-v2-5 — spec — `cancellation.mdx`'s sequence diagram shows an empty `session/prompt` response

**Repo:** spec · **Severity:** low · **Verified at:** `b9d6aca`

`docs/protocol/v2/cancellation.mdx:49`: `Agent-->>Client: response to id=1 ({})`.

`schema/v2/schema.json:4097` (`$defs/PromptResponse`) requires `messageId`, and
`docs/protocol/v2/prompt-lifecycle.mdx:124-127` says the field "is a required, non-null string;
omission and explicit `null` are invalid." The diagram predates the `2.0.0-alpha.5` change that
made `messageId` required (`schema/v2/CHANGELOG.md:10,14` — alpha.5, "return message ID on prompt insertion (#2175)").

**Suggested fix:** `Agent-->>Client: response to id=1 ({"messageId": "msg_user_1"})`.

---

# S-v2-6 — spec — `docs/protocol/v2/error.mdx` is still an empty stub

**Repo:** spec · **Severity:** medium · **Verified at:** `b9d6aca`

The whole v2 error page is six lines ending in `_Documentation coming soon_`
(`docs/protocol/v2/error.mdx:1-6`) — the v2 carry-over of v1 issue **S1** in
`.agents/research/upstream-issues.md`, still unfixed one major version later.

Consequences for a client implementer: the error code for an unknown `sessionId`, for a malformed
line, and for a structurally invalid request are all unspecified. The ACP TCK therefore cannot
assert any of them and registers three INFORMATIONAL record-only probes instead
(`ACP-INFO-UNKNOWNSESSION-001`, `ACP-INFO-PARSE-001`, `ACP-INFO-INVALIDREQ-001`).

**Suggested fix:** at minimum, document the ACP-specific codes that already exist in the schema
(`-32000` authentication required, `-32002` resource not found, `-32800` request cancelled) and
state which JSON-RPC codes apply to an unknown `sessionId` and a parse error.

---

# S-v2-7 — spec (question) — is `session/set_config_option` baseline, capability-gated, or optional?

**Repo:** spec · **Severity:** question · **Verified at:** `b9d6aca`

`docs/protocol/v2/session-config-options.mdx:211` documents `session/set_config_option`, and
`schema/v2/schema.json` defines `SetSessionConfigOptionRequest`/`Response`. But:

- `SessionCapabilities`'s property set (`schema/v2/schema.json:3159-3218`) has **no**
  `configOptions` marker;
- `migration.mdx:190`'s seven-method baseline does **not** include it;
- no page states when an agent is required to support it.

So a client has no documented way to know whether calling it is legal. The ACP TCK works around
this by inferring support from `session/new`'s own result carrying a non-empty `configOptions`
array, and by treating `-32601` as a SKIP rather than a FAIL.

**Ask:** either add a `capabilities.session.configOptions` marker, or state that returning a
non-empty `configOptions` in `session/new`/`session/resume` obliges the agent to implement
`session/set_config_option` (which is what implementers appear to assume).

---

# S-v2-8 — spec (question) — the schema forbids mixed-kind batches; no prose or JSON-RPC 2.0 does

**Repo:** spec · **Severity:** question · **Verified at:** `b9d6aca`

`schema/v2/schema.json:82-124` (`AgentBatchCall`) permits only call-shaped members, and
`:125-288` (`AgentBatchResponse`) only response-shaped members — so a batch mixing a request and a
response is schema-invalid. No prose in `docs/protocol/v2/transports.mdx:47-80` says so, and
JSON-RPC 2.0 §6 does not either. The Rust SDK deliberately *ignores* a response-shaped entry
inside a call batch rather than rejecting it (rust-sdk `md/transport-architecture.md:186-189`).

**Ask:** state the intended receiver behaviour in `transports.mdx` (reject the whole line, reject
the entry with `-32600`, or ignore the entry). The ACP TCK records this as INFORMATIONAL
(`ACP-INFO-BATCH-202`) and asserts nothing.

---

# P-v2-1 — python-sdk — a JSON-RPC batch array on stdin crashes the receive loop

**Repo:** `agentclientprotocol/python-sdk` · **Severity:** high · **Verified at:** `9d07d787` (= `1.0.0rc2`)

## What happens

`src/acp/_transport.py:73-86` reads one line and `json.loads`es it, annotating the result
`message: dict[str, Any]` — but a JSON **array** line parses into a `list`:

```python
# src/acp/_transport.py:82
message: dict[str, Any] = json.loads(line)
```

`src/acp/connection.py:152-154` then calls a dict method on it unconditionally:

```python
def _process_message(self, message: dict[str, Any]) -> None:
    method = message.get("method")
    has_id = "id" in message
```

`AttributeError: 'list' object has no attribute 'get'` propagates out of `_receive_loop`
(`connection.py:138-150`), which catches only `asyncio.CancelledError` and `asyncio.TimeoutError`
— so the loop task dies and the connection stops processing anything.

Reproduced against the released wheel:

```
$ uv run --no-project --with "agent-client-protocol==1.0.0rc2" python -c \
  "from acp.connection import Connection; Connection._process_message(None, [{'jsonrpc':'2.0','id':1,'method':'x'}])"
AttributeError: 'list' object has no attribute 'get'
```

`src/acp/experimental/v2/_connection.py` reuses the same `Connection`, so the v2 runtime inherits
this unchanged.

## What the spec requires

ACP v2 adopts JSON-RPC 2.0 §6 batching as a **MUST-level** transport feature:

- `docs/protocol/v2/transports.mdx:23-24`: "Messages are individual JSON-RPC requests,
  notifications, responses, **or batch arrays**."
- `:57-59`: an empty array "receives a single `Invalid Request` response (`code: -32600`) with
  `id: null`, not a response array."
- `:66-67`, `:70-72`: the receiver **MUST NOT** reply to a notification inside a batch, and
  **MUST NOT** return an empty array for an all-notification batch.

A crash satisfies none of these.

## Suggested fix

In `Connection._process_message`, dispatch on type before touching the message:

```python
if isinstance(message, list):
    if not message:
        self._send_error_response(None, RequestError.invalid_request())
        return
    for item in message:
        self._process_message(item)   # plus response-array aggregation per §6
    return
```

At minimum, the receive loop should not die: catching `Exception` around `_process_message` and
logging would already turn a hard crash into a dropped line.

## Impact

Any agent built on the Python SDK fails ACP v2's two MANDATORY batching requirements
(`ACP-BATCH-201`, `ACP-BATCH-202`) and does so by dying, not by answering wrongly. This is the
expected Python cross-check baseline for the ACP TCK's v2 leg.

---

# P-v2-2 — python-sdk — a strict v2 endpoint errors on a lower requested `protocolVersion`

**Repo:** python-sdk · **Severity:** high · **Verified at:** `9d07d787`

## What happens

Two different paths, two different error codes, neither of them a negotiation:

1. **Native strict v2** — `src/acp/experimental/v2/_initialization.py:26-31`:

   ```python
   if request.protocol_version != PROTOCOL_VERSION:
       raise RequestError.invalid_params({
           "expectedProtocolVersion": PROTOCOL_VERSION,
           "receivedProtocolVersion": request.protocol_version,
       })
   ```
   → `-32602 Invalid params`. (A v1-shaped `initialize` never even gets that far: `info` is
   required by the v2 model, so `agent.py:38`'s `validate_python` raises a pydantic
   `ValidationError`, mapped to `-32602` at `connection.py:211-212`.)

2. **`AgentProtocolRouter` with only a v2 agent configured** —
   `src/acp/experimental/negotiation.py:110-119` falls through to
   `RequestError.invalid_request({"details": f"Unsupported ACP protocol {requested}; configured
   versions are {supported}"})` → `-32600 Invalid request`.

## What the spec requires

`docs/protocol/v2/initialization.mdx:94`:

> If the Agent supports the requested version, it **MUST** respond with the same version.
> **Otherwise, the Agent MUST respond with the latest version it supports.**

There is no error branch. A v2-only agent asked for `1` must answer `{"protocolVersion": 2, …}`
and let the client decide whether it can live with that (`:96`: the *Client* SHOULD then close the
connection).

## Suggested fix

Answer the `initialize` successfully with the endpoint's own latest supported version instead of
raising, and leave rejection to the client. If a strict endpoint genuinely cannot serve a
downgraded client, it should still answer `2` and then reject subsequent non-v2 traffic.

## Impact

Fails ACP v2's `ACP-INIT-202` (MANDATORY) for every native-v2 Python agent. Note the divergence
worth settling with the spec: Rust answers `-32600` for the same scenario (R-v2-1), Python's own
two paths answer `-32602` and `-32600` — three different codes for one undefined-by-the-spec-to-be-an-error
situation.

---

# P-v2-3 — python-sdk — the shipped `acp.experimental.v2` bindings are generated from the *unstable* v2 schema

**Repo:** python-sdk · **Severity:** medium · **Verified at:** `9d07d787`

`src/acp/experimental/v2/schema.py:3819` defines a `SessionUpdate` variant with
`sessionUpdate: Literal["notice"]`. `notice` exists **only** in the spec's unstable artifact:

```
$ grep -c '"notice"' agent-client-protocol/schema/v2/schema.json          # stable
0
$ grep -c '"notice"' agent-client-protocol/schema/v2/schema.unstable.json # unstable
2
```

So the module named `experimental.v2` — whose own docstring calls it the "strict experimental ACP
v2 connection" (`src/acp/experimental/v2/agent.py:53`) — actually models a *superset* of stable
v2. An agent written against these bindings can emit `"sessionUpdate": "notice"` believing it is
in-spec.

## Why that is a conformance problem, not just a naming one

`docs/protocol/v2/extensibility.mdx:116-118`: "Unknown values that do not begin with `_` are
reserved for future ACP variants. Extensions **MUST NOT** define custom non-underscore values."
`notice` is a non-underscore value that is not in stable v2, so a stable-v2 client is required to
treat it as reserved rather than as an extension.

## Suggested fix

Either generate `acp.experimental.v2` from `schema/v2/schema.json` (stable) and put the unstable
surface behind a separate module/feature, or document prominently that `experimental.v2` tracks
`schema.unstable.json` and list the members that are not in stable v2.

(The same caveat already applies to `src/acp/meta.py`'s v2 method inventory, which the ACP TCK's
own research notes is wider than stable v2 — `.agents/plan.md`, "Vendor the stable v2 artifacts
only".)

---

# R-v2-1 — rust-sdk — a strict single-version endpoint answers `-32600` for an unsupported `protocolVersion`

**Repo:** `agentclientprotocol/rust-sdk` · **Severity:** high · **Verified at:** `28688b2d`

`src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:856-864`:

```rust
fn unsupported_protocol_version(
    version: ProtocolVersion,
    supported: ProtocolVersionKind,
) -> crate::Error {
    crate::Error::invalid_request().data(format!(
        "unsupported ACP protocol version {version}; this endpoint only supports ACP protocol version {}",
        supported.as_protocol_version(),
    ))
}
```

`Error::invalid_request()` is `-32600`. The behaviour is deliberate and covered by tests
(`src/agent-client-protocol/tests/protocol_v2.rs:332,540,658,1144`;
`src/agent-client-protocol/src/jsonrpc.rs:6669-6705`), which is why this is filed as a spec-vs-SDK
disagreement rather than a bug report: a strict endpoint by construction cannot honour
`initialization.mdx:94`'s "otherwise, the Agent **MUST** respond with the latest version it
supports".

**Ask:** either (a) have a strict endpoint still answer `initialize` with its own version and
reject only subsequent mismatched traffic, or (b) get the spec to sanction an error response here
and say which code. Today's state — Rust `-32600`, Python `-32602` *and* `-32600` (P-v2-2) — is
three answers to a question the spec says should not be an error at all.

**Impact:** fails ACP v2's `ACP-INIT-202` (MANDATORY). The dual-build `testy`
(`--features unstable_protocol_v2`) routes rather than rejects, so it is *not* affected; only
single-version endpoints are.

---

# R-v2-2 — rust-sdk — `md/testy.md` says v2 `session/prompt` returns an empty response

**Repo:** rust-sdk · **Severity:** low · **Verified at:** `28688b2d`

`md/testy.md:86`: "1. `session/prompt` returns an empty acceptance response."

The code is correct — `src/agent-client-protocol-test/src/testy/v2.rs:498` responds with
`acp::PromptResponse::new(user_message_id)`, i.e. `{"messageId": "testy-v2-user-message-N"}`, as
`schema/v2/schema.json:4097` requires. Only the prose is stale (same staleness as spec S-v2-5).

**Suggested fix:** "`session/prompt` returns an acceptance response carrying the inserted user
message's `messageId`."

---

## Candidates considered and dropped

- **`testy` v2 under-advertising `capabilities.session: {}`** — not a bug. The schema has no
  `list`/`resume`/`close` markers to set (S-v2-1), and testy implements all seven baseline
  methods (`src/agent-client-protocol-test/src/testy/v2.rs:394,407-484`).
- **v2 `session/prompt` concurrency** — genuinely out of scope upstream
  (`docs/rfds/v2/prompt.mdx:86`: "This RFD does not specify queueing, steering, or whether agents
  insert new prompts while busy"), not an omission to report.
- **`stopReason` missing from the initial ready-state idle** — correct by design; see S-v2-4 for
  the part that *is* wrong.
