# What is the state of ACP v2 support in the Rust and Python reference SDKs, and can their fixtures serve as v2 agents for cross-checking a v2 TCK?

**Sources checked:**
- `rust-sdk` @ `2a78849d3eb3dcb140dade3b8fc938cf1e2b9ce5` (main, 2026-09-18, "chore: release (#348)") — `git pull --ff-only` failed once with `fatal: Cannot fast-forward to multiple branches` (concurrent fetch by another researcher); retried and got `Already up to date`, and `origin/main == HEAD`, so the checkout *is* current.
- `python-sdk` @ `9d07d7871ef4b220b8507e15fc4b1560f0950a64` (main, 2026-09-21, "refactor(v2)!: expand parameters and derive routes from protocols (#150)"); this commit is also tag `1.0.0rc2`. Pulled forward from the `d92b968` recorded in the task.
- `agent-client-protocol` (spec) @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e` (main, 2026-09-21) — used only to confirm what "v2" names.
- `agent-client-protocol-schema` crate **1.9.1** as vendored in the local cargo registry (`~/.cargo/registry/src/index.crates.io-*/agent-client-protocol-schema-1.9.1/`); this is the published build of the spec repo's `agent-client-protocol-schema/` (spec `agent-client-protocol-schema/Cargo.toml:15` → `version = "1.9.1"`).
- crates.io index and PyPI JSON API for published versions.
- **Live wire probes** I ran against locally built binaries (see "Details / observed wire traffic"). Probe scripts are throwaway files under `/tmp/acpv2probe/`; nothing was written into any checkout except cargo's gitignored `target/` (and I restored `target/debug/testy` to the `--no-default-features` build that `scripts/cross-check.sh` expects).

**Confidence:** high — for every claim about wire behavior I have both source citations and reproduced stdio transcripts from binaries built at the revisions above. Medium only for the one ordering finding flagged as "documented, not a bug" vs. "bug" (I cite the doc that makes it intentional).

## Answer

Both reference SDKs implement draft ACP v2 today, behind explicit experimental gates, both generated from the same upstream draft schema `schema-v2.0.0-alpha.5`, and both put integer `2` on the wire as `protocolVersion`. The Rust SDK is the stronger cross-check target: `testy` has a **native** (not converted) v2 agent and a dual-version build (`cargo build -p agent-client-protocol-test --bin testy --no-default-features --features unstable_protocol_v2`) that selects v1 or v2 from the client's `initialize`, so **one binary can serve both the existing v1 cross-check and a new v2 cross-check** — I verified the current v1 baseline is unchanged with that binary. The Python SDK ships a complete v2 runtime in `acp.experimental.v2` (published on PyPI in `1.0.0rc1` and `1.0.0rc2`), but **there is no v2 example agent** — `examples/echo_agent.py` is v1-only — so a Python v2 cross-check needs a small fixture script that the TCK repo writes itself on top of the upstream runtime. Coverage is partial on both sides: testy's v2 agent advertises only `capabilities.session: {}` and implements only `initialize`, `session/new|list|resume|close|prompt|cancel|update`; no client callbacks, permissions, MCP, auth, delete, config options, or modes. The biggest TCK-relevant divergence is version negotiation for a *native* v2-only agent: Rust answers an unsupported `protocolVersion` with `-32600`, Python with `-32602`, and neither downgrades — while both SDKs' *protocol routers* instead normalize any requested version ≥ 2 to exactly 2 and answer `2`.

## Observed behaviors and support status

Tiering here is "what the SDK does", not "what the spec requires" — the spec-side v2 delta and version-negotiation semantics are owned by other researchers. `capability:` rows mark behavior that only applies when the agent advertises the capability.

| # | Observed behavior | Tier / kind | Citation |
|---|---|---|---|
| 1 | Rust SDK implements draft v2 behind the crate feature `unstable_protocol_v2`, deliberately separate from the `unstable` umbrella | fact (feature-gated) | rust-sdk `md/protocol-v2.md:1-10`; `src/agent-client-protocol/Cargo.toml:53`; feature is **not** part of `unstable` (`src/agent-client-protocol/Cargo.toml:6-21`) |
| 2 | Rust SDK generates v2 types from the published crate `agent-client-protocol-schema = "=1.9.1"`, whose `v2` module is itself `unstable_protocol_v2`-gated | fact | rust-sdk `Cargo.toml:38`; schema crate `src/v2/mod.rs:1-10` |
| 3 | `ProtocolVersion::V2` is the integer `2` on the wire (`ProtocolVersion(u16)`, `serde(transparent)`), and `ProtocolVersion::LATEST` is deliberately unavailable when `unstable_protocol_v2` is on | fact | schema crate `src/version.rs:12`, `:24-30`, `:31-39` |
| 4 | `testy` speaks v2 only when built with `--features unstable_protocol_v2`; it then wraps `Testy` in `Agent.protocol_router().with_v1(..).with_v2(..)` and selects from `initialize` | fact | rust-sdk `md/testy.md:11-30`; `src/agent-client-protocol-test/src/bin/testy.rs:9-19`; `src/agent-client-protocol-test/src/testy.rs:231-236`; `src/agent-client-protocol-test/Cargo.toml:13-15` |
| 5 | testy's v2 agent advertises exactly `{"protocolVersion":2,"info":{"name":"test-agent","version":"0.11.0"},"capabilities":{"session":{}}}` — no `authMethods`, no prompt/mcp/delete/additionalDirectories sub-capabilities | fact (observed) | rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:389-395`; probe transcript below |
| 6 | testy's v2 agent handles exactly: `initialize`, `session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt` (requests) and `session/cancel` (notification). Everything else → `-32601` | fact (observed) | rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:398-529`; `md/testy.md:79-100`; probe transcript below |
| 7 | testy's v2 agent never sends an agent→client **request** (no `session/request_permission`, `fs/*`, `terminal/*`, `elicitation/*`) — only `session/update` notifications | fact | rust-sdk `src/agent-client-protocol-test/src/testy/v2.rs:553-562` is the only outbound path; no `send_request` in the file |
| 8 | v2 prompt lifecycle is split: `session/prompt` returns `{"messageId": …}` immediately, then `user_message` → `state_update:running` → content updates → `state_update:idle` + `stopReason` | fact (observed) | rust-sdk `md/protocol-v2.md:132-146`; `src/agent-client-protocol-test/src/testy/v2.rs:288-387`; `tests/testy_v2.rs:112-144` |
| 9 | v2 cancellation is deterministic: `session/cancel` is confirmed by an `idle` state update with `stopReason:"cancelled"`; the prompt response has already been sent, so the v1 cancel *race* does not exist in v2 | fact (observed) | rust-sdk `md/testy.md:92-95`; `src/agent-client-protocol-test/src/testy/v2.rs:175-203`, `:330-334`; `tests/testy_v2.rs:296-301`; probe transcript below |
| 10 | The Rust **agent protocol router** selects the highest configured version ≤ requested (`requested >= 2 → v2`, `1 <= requested < 2 → v1`, else error) and, when `requested != selected`, **rewrites `protocolVersion` in the forwarded params** to the selected version | fact | rust-sdk `src/agent-client-protocol/src/role/acp.rs:484-495` (`highest_compatible`), `:606-637` (`rewrite_initialize_params`), `:864-874` |
| 11 | A **native** (non-routed) Rust `Agent.v2()` rejects any `protocolVersion != 2` with `-32600 "unsupported ACP protocol version N; this endpoint only supports ACP protocol version 2"` — it does not downgrade | fact (observed) | rust-sdk `src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:499-516`, `:857-864`; `md/protocol-v2.md:341-346`; probe transcript below |
| 12 | A native Rust `Agent.v2()` also rejects any non-`initialize` traffic that arrives **before the initialize response has completed**, with `-32600 "ACP initialization must complete before \`X\` can be used"` — reproducible 6/6 by pipelining both lines in one write | documented behavior, not a bug | rust-sdk `md/protocol-v2.md:330-336`; probe transcript below |
| 13 | Python SDK implements draft v2 in `acp.experimental.v2`, generated from `refs/tags/schema-v2.0.0-alpha.5`, with `PROTOCOL_VERSION = 2` | fact | python-sdk `schema/v2/VERSION:1`; `src/acp/experimental/v2/meta.py:1-2`, `:41`; `docs/experimental-v2.md:1-6` |
| 14 | Python v2 is present in the **published** wheels `1.0.0rc1` (2026-09-11) and `1.0.0rc2` (2026-09-21); `1.0.0rc2` == current main HEAD | fact (verified by install) | PyPI JSON API; `uv run --with 'agent-client-protocol==1.0.0rc2' python -c "import acp.experimental.v2"` → `PROTOCOL_VERSION 2` |
| 15 | `examples/echo_agent.py` is **v1-only** (imports `acp.run_agent`, v1 `InitializeResponse`, returns `stop_reason`); the Python SDK ships **no** runnable v2 example or fixture | fact | python-sdk `examples/echo_agent.py:11-17`, `:40-47`, `:69-77`; `ls examples/` has no v2 script |
| 16 | A native Python `v2.run_agent(...)` agent rejects `protocolVersion != 2` with `-32602` and data `{"expectedProtocolVersion":2,"receivedProtocolVersion":N}`; it does not downgrade | fact (observed) | python-sdk `src/acp/experimental/v2/_initialization.py:24-31`; probe transcript below |
| 17 | A native Python v2 agent **awaits** in-flight initialization rather than rejecting concurrent traffic; pre-initialize traffic with no initialize in flight gets `-32600 "ACP v2 connection must be initialized before 'X'"` | fact (observed) | python-sdk `src/acp/experimental/v2/_initialization.py:52-67`; probe transcript below |
| 18 | Python's `acp.experimental.AgentProtocolRouter` mirrors the Rust router: `requested >= 2 → v2` with `protocol_version` forced to 2; it additionally **validates** that the selected agent's initialize response carries the selected version | fact | python-sdk `src/acp/experimental/negotiation.py:57-68`, `:95-129` |
| 19 | Python v2 returns `-32601` for any v2 method the agent object does not implement, including baseline `session/list`/`session/resume` | fact (observed) | python-sdk `src/acp/experimental/v2/_router.py:36-44`, `:62-65`; probe transcript below |
| 20 | Both SDKs return `{}` (not `null`) for empty v2 results (`session/close`, `session/resume`) | fact (observed) | probe transcripts below; python-sdk `_router.py:42-43` (`default_result={}`) |
| 21 | Malformed JSON: Rust replies `{"id":null,"error":{"code":-32700,…,"data":{"line":"…"}}}` and stays usable; Python logs a traceback to stderr and sends **nothing** | divergence (TCK-informational) | probe transcripts below; python-sdk `src/acp/_transport.py:82` |
| 22 | Unknown methods, including `_`-prefixed custom ones with no extension handler, get `-32601` on **both** SDKs in v2 | fact (observed) | probe transcripts; python-sdk `src/acp/experimental/v2/_router.py:67-74`; rust-sdk v2 has no catch-all handler |
| 23 | A second `initialize` on an initialized v2 connection is rejected: Rust `-32600 "ACP connections may only be initialized once; reconnect to initialize again"`, Python `-32600 "ACP v2 connections may only be initialized once"` | fact (observed) | probe transcripts; python-sdk `_initialization.py:25-26`; rust-sdk `md/protocol-v2.md:334-336` |
| 24 | `agent-client-protocol` crate `2.2.0` and `agent-client-protocol-schema` `1.9.1` are published on crates.io; `agent-client-protocol-test` (which owns `testy`) is `publish = false`, so testy is only obtainable from a git checkout | fact | crates.io sparse index; rust-sdk `src/agent-client-protocol-test/Cargo.toml:10` |

## Details

### 1. Rust SDK

**Versions.** Workspace crate `agent-client-protocol` is at **2.2.0** (rust-sdk `Cargo.toml:29`) — that is the *crate* semver, not the protocol version; 2.x of the crate has existed since before v2 protocol work and speaks v1 by default. It pins `agent-client-protocol-schema = "=1.9.1"` (rust-sdk `Cargo.toml:38`). Published crates.io versions of `agent-client-protocol`: `…, 2.0.0, 2.1.0, 2.2.0`; of `agent-client-protocol-schema`: `…, 1.8.0, 1.9.0, 1.9.1`.

**Feature flags.** `unstable_protocol_v2` on `agent-client-protocol` (rust-sdk `src/agent-client-protocol/Cargo.toml:53`) forwards to `agent-client-protocol-schema/unstable_protocol_v2`. It is intentionally *not* in the `unstable` umbrella (`md/protocol-v2.md:1-10`), so you can build **strict v1 + draft v2** with `--no-default-features --features unstable_protocol_v2` — important, because the TCK's existing v1 cross-check uses `--no-default-features` precisely to avoid `unstable`'s non-v1 `mcpCapabilities.acp` field. Related v2 sub-features: `unstable_session_fork` (adds `session/fork`), `unstable_mcp_over_acp`, `unstable_nes`, `unstable_llm_providers`.

**CHANGELOG entries about v2** (rust-sdk `src/agent-client-protocol/CHANGELOG.md`): 2.1.0 (2026-09-04) added "Add runnable draft-v2 agent and one-shot client examples", "`Proxy::protocol_router`/`ProxyProtocolRouter`", "high-level protocol v2 session builders and handles" (lines 41-90); 2.2.0 (2026-09-18) bumped the schema to 1.8/1.9 which "stabiliz[ed] optional programmatic tool-call names in v1 and draft v2" and added "exercise v2 example projection semantics" / "demonstrate v2 session coordination" (lines 5-37). Draft-schema churn from 1.5 through 1.8 is summarised at `md/protocol-v2.md:451-474`.

**`testy` build commands** (rust-sdk `md/testy.md:11-30`):
```
# v1 only, strict (what scripts/cross-check.sh uses today)
cargo build -p agent-client-protocol-test --bin testy --no-default-features
# v1 + unstable + draft v2
cargo build -p agent-client-protocol-test --bin testy --features unstable_protocol_v2
# v1 (strict) + draft v2  -- the build I verified and recommend for the TCK
cargo build -p agent-client-protocol-test --bin testy --no-default-features --features unstable_protocol_v2
```
The binary lands at `target/debug/testy`. `just prep-tests` builds it `--all-features`.

**How testy selects a version.** `src/bin/testy.rs:9-19` uses `Testy::new().protocol_router()` under `cfg(feature = "unstable_protocol_v2")` and plain `Testy::new()` otherwise. `Testy::protocol_router()` (`src/testy.rs:231-236`) = `Agent.protocol_router().with_v1(self).with_v2(self.v2())`. The v1 and v2 implementations are native and keep **independent session state** (`src/testy.rs:218-226`); no conversion layer.

**Router selection rules** (`src/agent-client-protocol/src/role/acp.rs`):
- `SupportedProtocols::highest_compatible` (`:484-495`): `v2 && requested >= 2 → V2`; else `v1 && requested >= 1 → V1`; else `None` → `-32600 "unsupported ACP protocol version N; this endpoint supports ACP protocol versions 1 and 2"` (`:864-874`).
- `rewrite_initialize_params` (`:606-637`): when `requested == selected.version()` the raw params are validated but **preserved byte-for-byte** (so unknown future fields survive); when `requested > 2` and V2 is selected, the request is parsed as `v2::InitializeRequest`, `protocol_version` is forced to `2`, and re-serialized. Consequence: **a v1-shaped `initialize` with `protocolVersion: 65535` now fails with `-32602 "invalid initialize params: missing field \`info\`"`**, because it is routed to v2 and v2 requires `info`.
- A rejected initialize is fatal for the connection: `reject_initialize` (`:952-971`) sends the error, drops the outbound channel, and drains input.
- The first frame must be a request named `initialize`; anything else → `-32600 "first ACP request must be initialize"` (`:524-537`).

**v2 wire shapes (from schema crate 1.9.1).**
- `v2::InitializeRequest` (`src/v2/agent.rs:58-78`): required `protocolVersion` (integer) and **`info: Implementation`** (`name`, `version`, optional `title`); optional `capabilities: ClientCapabilities` (defaults on error), optional `_meta`. Note `info` replaces v1's `clientInfo`, and `capabilities` replaces v1's `clientCapabilities`.
- `v2::InitializeResponse` (`src/v2/agent.rs:123-152`): required `protocolVersion` and **`info: Implementation`**; optional `capabilities: AgentCapabilities`, `authMethods` (omitted when empty), `_meta`. So v2 makes agent info **mandatory** — the TCK's v1 ADVISORY `ACP-INIT-004` becomes a v2 MUST-shaped check (confirm with the spec researcher).
- `v2::AgentCapabilities` (`src/v2/agent.rs:3946-3960`): `session: Option<SessionCapabilities>`, `auth`, plus unstable `providers`/`nes`/`positionEncoding`, `_meta`.
- `v2::SessionCapabilities` (`src/v2/agent.rs:4138-4215`): `prompt`, `mcp`, `delete`, `additionalDirectories`, unstable `fork`, `_meta`.
- v2 agent method names (`src/v2/agent.rs:5057-5089`): `initialize`, `auth/login`, `auth/logout`, `session/new`, `session/list`, `session/delete`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, `session/set_config_option`, plus unstable `session/fork`, `providers/*`. **There is no `session/load` and no `session/set_mode` in v2.** Client methods (`src/v2/client.rs:2443-2461`): `session/request_permission`, `session/update`, `elicitation/create`, `elicitation/complete`. Protocol-level: `$/cancel_request` (`src/v2/protocol_level.rs:72`). This matches the spec's own `schema/v2/meta.json`.

**testy v2 scenario coverage.** `parse_command` is shared with v1, so plain-text prompts work: `help`, `greet`, `echo <msg>`, `wait_for_cancel`, `cancel_status`; any other `run_scenario` returns the text "Testy v2 scenario `X` is not implemented yet" with `stopReason: "refusal"`; MCP commands return a refusal too (`src/testy/v2.rs:324-366`, `:543-551`). So **the v1 scenarios `session_updates` / `content` / `tool_calls` / `callbacks` / `elicitations` / `full` do not exist in v2** (`md/testy.md:96-100`). `session/resume` replays stored history *before* the response, but only for `replayFrom: {type:"start"}`; any other cursor → `-32602 "unsupported session replay cursor"` (`src/testy/v2.rs:130-136`). `session/close` on a session with active foreground work waits for the work to finish (after marking it cancelled) before responding (`src/testy/v2.rs:457-480`).

**Second Rust v2 agent.** `src/agent-client-protocol/examples/simple_agent_v2.rs` is "a small, complete ACP v2 agent" implementing the same baseline (new/list/resume/close/prompt/cancel/update) as a **native, v2-only** `Agent.v2()` with no router (`examples/simple_agent_v2.rs:1-8`, `:334-351`). Build: `cargo build -p agent-client-protocol --features unstable_protocol_v2 --example simple_agent_v2` (`md/protocol-v2-quickstart.md:13-20`). It is useful as a *second* Rust target precisely because it exercises the non-routed negotiation path.

### 2. Python SDK

**Layout.** `src/acp/experimental/v2/` (7.7k lines incl. a 6k-line generated `schema.py`) plus `src/acp/experimental/negotiation.py` (the dual-version router). Public surface: `v2.Agent`, `v2.Client`, `v2.AgentSideConnection`, `v2.ClientSideConnection`, `v2.run_agent`, `v2.connect_to_agent`, `v2.schema`, `v2.PROTOCOL_VERSION` (`src/acp/experimental/v2/__init__.py:1-18`). Docs: `docs/experimental-v2.md` (also in `mkdocs.yml:15`).

**Schema pin.** `schema/v2/VERSION` = `refs/tags/schema-v2.0.0-alpha.5`; v1 stayed on `refs/tags/schema-v1.23.0` (`schema/VERSION`). Landed in `accb008 feat(v2)!: bump ACP draft schema to 2.0.0-alpha.5 (#147)`.

**v2 history on `main`:** `3cc75c9 feat(codegen): generate experimental v2 bindings (#141)` → `198c46d feat(v2): add experimental runtime and negotiation (#139)` → `accb008` (alpha.5) → `a11bb6e`/`9d07d78` (derive routes from protocol metadata; expand handler parameters — a breaking API change to the v2 handler signatures, `docs/experimental-v2.md:76-78`).

**Released versions.** PyPI: latest *stable* is `0.12.1`; pre-releases `1.0.0rc1` (2026-09-11) and `1.0.0rc2` (2026-09-21) both contain `acp/experimental/v2` (I installed both and imported it). `1.0.0rc2` is byte-identical in content to current `main` HEAD. Note: `pyproject.toml:3` still says `version = "0.12.1"` on `main`; the release version is applied at publish time, so do not read the repo's `pyproject.toml` as the released version.

**Exact pin a cross-check script should use.**
```
uv run --no-project --with 'agent-client-protocol==1.0.0rc2' python <v2-agent-script>.py
```
Pinning is still required for the same reason as v1 (an unpinned PEP 723 header resolves the latest *stable* `0.12.1`, which has no `acp.experimental` at all). If the v1 cross-check stays on `1.0.0rc1`, note that the v2 handler signatures changed in `9d07d78` (`prompt(session_id, prompt, …)` expanded parameters), so a v2 fixture written against `rc2` will **not** run on `rc1`.

**No v2 fixture upstream.** `examples/` contains `agent.py`, `client.py`, `duet.py`, `echo_agent.py`, `gemini.py`, `http_*`, `ws_client.py` — all v1. v2 agents exist only inside `tests/test_v2_runtime.py` / `tests/test_v2_routing.py` as in-test classes, not runnable scripts. To cross-check, the TCK repo must author a ~60-line `v2_echo_agent.py` on top of `acp.experimental.v2`. I wrote one at `/tmp/acpv2probe/v2_echo_agent.py` and verified it produces a wire transcript indistinguishable in shape from testy's (see below); it is a throwaway probe, not a deliverable, but it demonstrates feasibility and is the shape to copy. Two gotchas I hit writing it: the `UpdateSessionNotification.update` union wants `RunningSessionStateUpdate` / `IdleSessionStateUpdate` (the similarly named `RunningStateUpdate` / `IdleStateUpdate` are *not* union members and fail validation at send time), and update-sending exceptions surface only as an un-awaited-task traceback on stderr.

**Router.** `acp.experimental.AgentProtocolRouter(v1=…, v2=…)` (`src/acp/experimental/negotiation.py:149-211`): `_read_protocol_version` requires an integer in `[0, 65535]` (`:34-40`, rejects `bool`); `requested >= 2 and v2 configured → v2`, else `requested >= 1 and v1 configured → v1`, else `-32600 "Unsupported ACP protocol N; configured versions are […]"` (`:103-120`). `_normalize_initialize` forces `protocol_version` to the selected version (`:57-68`), and for a v2→v1 downgrade maps `info → clientInfo`, `capabilities → clientCapabilities` (`:43-54`). After the selected agent answers, the router re-reads the response's version and raises `-32600` if it disagrees with the selection (`:124-128`) — a guard the Rust router does not have in the same place.

### 3. Observed wire traffic (probes I ran)

All transcripts are real stdout from the binaries built at the revisions above. `>` = TCK-side send, `<` = agent output.

**a) testy (dual build), v2 happy path + prompt lifecycle**
```
> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":2,"info":{"name":"tck","version":"0.1.0"}}}
< {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":2,"info":{"name":"test-agent","version":"0.11.0"},"capabilities":{"session":{}}}}
> {"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp"}}
< {"jsonrpc":"2.0","id":2,"result":{"sessionId":"testy-v2-session-1"}}
> {"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"testy-v2-session-1","prompt":[{"type":"text","text":"echo hi"}]}}
< {"jsonrpc":"2.0","id":3,"result":{"messageId":"testy-v2-user-message-0"}}
< {"…","method":"session/update","params":{"sessionId":"…","update":{"sessionUpdate":"user_message","messageId":"testy-v2-user-message-0","content":[{"type":"text","text":"echo hi"}]}}}
< {"…","method":"session/update","params":{"sessionId":"…","update":{"sessionUpdate":"state_update","state":"running"}}}
< {"…","method":"session/update","params":{"sessionId":"…","update":{"sessionUpdate":"agent_message_chunk","messageId":"testy-v2-agent-message-1","content":{"type":"text","text":"hi"}}}}
< {"…","method":"session/update","params":{"sessionId":"…","update":{"sessionUpdate":"state_update","state":"idle","stopReason":"end_turn"}}}
```

**b) testy v2 cancel** — with prompt text `wait_for_cancel`, then a `session/cancel` notification:
```
< {"…"id":3,"result":{"messageId":"testy-v2-user-message-0"}}
< … user_message … state_update:running …
< {"…","method":"session/update","params":{"…","update":{"sessionUpdate":"state_update","state":"idle","stopReason":"cancelled"}}}
```
No `session/prompt` error, no second response — the cancel is observable purely as an `idle`/`cancelled` state update. **There is no cancel race in v2**, so the v1 `--cancel-prompt` / `quiet_period` / "cancellation not exercised" SKIP machinery is unnecessary for v2 against these agents.

**c) testy (dual build), version negotiation matrix**
| request | response |
|---|---|
| `protocolVersion: 1`, v1-shaped params | `{"protocolVersion":1,"agentCapabilities":{loadSession,promptCapabilities,mcpCapabilities:{http,sse},sessionCapabilities:{list,delete,additionalDirectories,resume,close},auth:{logout}},"authMethods":[{"id":"testy-agent-auth",…}]}` — the full v1 agent, unchanged |
| `protocolVersion: 2`, v2-shaped params | `{"protocolVersion":2,"info":…,"capabilities":{"session":{}}}` |
| `protocolVersion: 65535`, **v1-shaped** params | `-32602 "invalid initialize params: missing field \`info\`"` |
| `protocolVersion: 65535`, **v2-shaped** params | `{"protocolVersion":2, …}` (normalized down to 2) |
| `protocolVersion: 0` | `-32600 "unsupported ACP protocol version 0; this endpoint supports ACP protocol versions 1 and 2"` |
| `protocolVersion: 2`, missing `info` | `-32602 "invalid initialize params: missing field \`info\`"` |
| first request not `initialize` | `-32600 "first ACP request must be initialize"` |
| second `initialize` after success | `-32600 "ACP connections may only be initialized once; reconnect to initialize again"` |

**d) testy v2 error handling**
```
nope/does_not_exist   -> -32601 Method not found, data "nope/does_not_exist"
_tck/does_not_exist   -> -32601 (same shape; no extension catch-all)
session/load          -> -32601   (v1-only method, absent in v2)
session/delete        -> -32601   (not advertised, not implemented)
session/set_mode      -> -32601   (v1-only method, absent in v2)
prompt w/ unknown sessionId -> -32602 "unknown session `nope`"
malformed JSON line   -> {"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error","data":{"line":"{not json"}}}  (connection stays usable)
session/cancel for an unknown sessionId -> silently ignored, no response
unknown notification  -> silently ignored
session/list          -> {"sessions":[{"sessionId":…,"cwd":"/tmp","title":"Testy v2 session","updatedAt":"2026-01-01T00:00:00Z"}]}
session/close         -> {}   (empty object, not null)
session/resume        -> {}   (empty object, not null)
```

**e) `simple_agent_v2` (native v2, no router)**
```
protocolVersion 1     -> -32600 "unsupported ACP protocol version 1; this endpoint only supports ACP protocol version 2"
protocolVersion 65535 -> -32600 "unsupported ACP protocol version 65535; this endpoint only supports ACP protocol version 2"
initialize ok         -> {"protocolVersion":2,"info":{"name":"simple-agent-v2","version":"2.2.0"},"capabilities":{"session":{}}}
malformed JSON        -> -32700 with id:null (same as testy)
unknown method        -> -32601
```
Pipelining `initialize` and `session/new` in a **single write** (both lines in one `write()`) reproduces **6/6**:
```
< {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":2,…}}
< {"jsonrpc":"2.0","id":2,"error":{"code":-32600,"message":"Invalid request","data":"ACP initialization must complete before `session/new` can be used"}}
```
Sending `session/new` only *after reading* the initialize response succeeds 5/5. testy-behind-the-router and the Python v2 runtime both succeed 6/6 on the pipelined case.

**f) Python v2 (`acp.experimental.v2`, 1.0.0rc2, my throwaway echo fixture)**
```
< {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":2,"info":{"name":"v2-echo-agent","version":"0.1.0"},"capabilities":{"session":{}}}}
< {"jsonrpc":"2.0","id":2,"result":{"sessionId":"py-v2-session-1"}}
< {"jsonrpc":"2.0","id":3,"result":{"messageId":"user-1"}}
< session/update user_message ; state_update:running ; agent_message_chunk ; state_update:idle stopReason end_turn
protocolVersion 1     -> -32602 {"errors":[{"type":"missing","loc":["info"],…}]}
protocolVersion 65535 -> -32602 {"expectedProtocolVersion":2,"receivedProtocolVersion":65535}
second initialize     -> -32600 {"details":"ACP v2 connections may only be initialized once"}
traffic before init   -> -32600 {"details":"ACP v2 connection must be initialized before 'session/new'"}   (and the later initialize still succeeds)
nope/x, _tck/x, session/load, session/list, session/resume -> -32601 {"method": "<name>"}
session/close (implemented) -> {}
malformed JSON line   -> NO response; a Python traceback on stderr ("Error parsing JSON-RPC message")
session/cancel unknown session -> silently ignored
```

### 4. Cross-check feasibility

**Rust — feasible today, recommended primary v2 target.**
```bash
# one binary serves both the v1 and the v2 cross-check
cd "$ACP_RUST_SDK"
cargo build -p agent-client-protocol-test --bin testy --no-default-features --features unstable_protocol_v2
# v1 run (unchanged)
acp-tck --cancel-prompt wait_for_cancel --report-json "$OUT/testy-v1.json" -- "$ACP_RUST_SDK/target/debug/testy"
# v2 run (whatever the v2 TCK's protocol-version flag ends up being)
acp-tck --protocol-version 2 --cancel-prompt wait_for_cancel --report-json "$OUT/testy-v2.json" -- "$ACP_RUST_SDK/target/debug/testy"
```
I ran the **existing v1 suite** against that dual-version binary: `MANDATORY PASS=20 FAIL=1`, `CAPABILITY PASS=18 SKIPPED=1`, `ADVISORY PASS=10 FAIL=1 SKIPPED=1`, `INFORMATIONAL PASS=4`, verdict NOT CONFORMANT with only `ACP-INIT-003` (MANDATORY) and `ACP-INIT-004` (ADVISORY) failing — **identical to the documented baseline in `docs/cross-check.md`**. Caveat: `ACP-INIT-003` fails for a *different reason* on the dual build (`-32602 missing field \`info\`` from the v2 route, instead of the v1 build's echoed `65535`). If the TCK ever tightens the expected failure message, that will matter; the pass/fail table does not change. Recommendation: keep the v1 cross-check on the `--no-default-features` binary (separate `target/` artifact names or sequential rebuilds) so the v1 baseline is not entangled with v2 routing, **or** consciously re-baseline `ACP-INIT-003`'s message.

Expected v2 baseline against testy (my predictions from the probes; a v2 TCK should confirm):
- Everything in the baseline session surface should PASS: initialize shape (incl. mandatory `info`), `session/new` uniqueness, split prompt lifecycle, `state_update` ordering, cancel-via-idle, `session/list`, `session/resume` replay-before-response, `session/close`.
- Every capability-conditional family should SKIP: prompt content capabilities, MCP, `session/delete`, `additionalDirectories`, `session/fork`, `auth/login`/`auth/logout`, `session/set_config_option`, elicitation, permissions, terminal/fs callbacks. testy advertises only `capabilities.session: {}`.
- `session/request_permission` and all client-capability negative tests should PASS trivially — testy v2 sends no agent→client requests at all.
- No known v2 non-conformance to pre-declare for testy, unlike `ACP-INIT-003` in v1. The v1 `ACP-INIT-004` analogue disappears because v2 `InitializeResponse.info` is required and testy supplies it.

Optional second Rust target: `simple_agent_v2` (`cargo build -p agent-client-protocol --features unstable_protocol_v2 --example simple_agent_v2`, binary at `target/debug/examples/simple_agent_v2`). It exercises the *native* v2 negotiation path, which testy's router hides. **A v2 TCK run against it must not pipeline requests behind `initialize`** or it will get `-32600` (item 12).

**Python — feasible only with a TCK-authored fixture.** There is no upstream v2 agent to point at. Two options:
1. **Write `tests/fixtures/agents/v2_echo_agent.py` in this repo** on top of `acp.experimental.v2` and run it as:
   ```
   acp-tck --protocol-version 2 --report-json "$OUT/py-v2.json" -- \
     uv run --no-project --with 'agent-client-protocol==1.0.0rc2' python tests/fixtures/agents/v2_echo_agent.py
   ```
   This is weaker evidence than `echo_agent.py` (we author the handler logic), but it still cross-checks the *upstream runtime*: framing, routing, initialization guard, param validation, response serialization, `_meta` handling. Note it in `docs/cross-check.md` so nobody mistakes it for an independently authored agent.
2. **Ask upstream** for an `examples/v2_echo_agent.py`, and keep Python out of the v2 cross-check until then.

Expected Python v2 baseline with option 1: same PASS/SKIP profile as testy, plus two informational deltas — no `-32700` reply to a malformed line (item 21, the same behavior the v1 TCK already records under `ACP-INFO-PARSE-001`), and `-32601` for any baseline `session/*` method the fixture does not implement (item 19), so implement `list`/`resume`/`close` in the fixture if the v2 TCK treats `capabilities.session: {}` as advertising them.

**Schema vendoring.** The v2 draft JSON Schema the TCK should vendor lives in the spec repo at `schema/v2/schema.json` + `schema/v2/meta.json`, tag `schema-v2.0.0-alpha.5` (commit `6d08f41`, 2026-09-18); there are no `schema/v2` commits after that tag on spec `main` (`8f76d6c`). Both SDKs are on exactly that draft. There are also `schema.unstable.json` / `meta.unstable.json` variants — the stable-draft pair is what corresponds to a `--no-default-features`-style build.

### 5. TypeScript SDK (optional third target)

`/Users/eugene/Documents/JetBrains/projects/acp-typescript-sdk` **exists** but is stale: HEAD `f1c01412e2c3e081f13f343b9e6586c5a4759b8f` (main, 2026-07-25) — I did **not** pull it, per instructions. Even at that revision it already has draft v2: `src/v2/acp.ts`, `src/v2/schema/`, `schema/v2/`, a `src/protocol-router.ts` + `src/protocol-router.test.ts`, a top-level design note `v2_negotiation.md`, and — most usefully — a **runnable dual-version example** `src/examples/dual-version-agent.ts` that wires a v1 agent and a v2 agent behind one router (`src/examples/dual-version-agent.ts:1-40`). Its v2 API is opt-in via `@agentclientprotocol/sdk/experimental/v2`, package `@agentclientprotocol/sdk@1.3.0`, and it uses the same "native v2 only accepts version 2" guard shape as the other two (`src/v2/acp.ts:180-186` raises with `{expectedProtocolVersion, actual}` and the message "The v2 API only supports protocol version N"). It is a plausible third cross-check target with a *lower* setup cost than the Python one (a real upstream example agent already exists), but the checkout is two months stale and no skill governs it, so someone should decide whether to adopt and pin it before relying on it.

## Testability notes

- **Negotiation is the one thing a v2 TCK must decide up front.** All three implementations refuse to answer a v1 `initialize` from a v2-only agent, and refuse to downgrade. A v2 TCK that probes "unsupported version" (the v2 analogue of `ACP-INIT-003`) will see three different shapes depending on the agent: `-32600` (Rust native), `-32602` (Python native), or a successful `protocolVersion: 2` (either SDK's router, which normalizes anything ≥ 2 down to 2). Until the spec says which is required, that probe belongs in the INFORMATIONAL tier. This overlaps the version-negotiation researcher's scope — I am reporting only what the SDKs do.
- **A v2 TCK must not pipeline.** Send `initialize`, read the response, *then* send the next request. Otherwise native Rust `Agent.v2()` agents fail with `-32600` (item 12) and the TCK will report a false non-conformance. This also means the TCK cannot reuse a "fire several requests, collect responses" pattern for the handshake.
- **Cancellation becomes deterministic and cheap to test.** `session/prompt` returns immediately with `messageId`, and completion is signalled by `state_update: idle` + `stopReason`. So the v2 cancel test is: prompt → wait for `state_update:running` → send `session/cancel` → assert the next `state_update:idle` carries `stopReason: "cancelled"`. No race window, no `--cancel-prompt`, no "cancellation not exercised" SKIP. Both SDKs behave this way.
- **`messageId` correlation is the only prompt↔update linkage.** `session/update` carries `sessionId` and entity IDs but no prompt/turn ID (rust-sdk `md/protocol-v2.md:159-163`). A TCK cannot attribute arbitrary intervening updates to its own prompt; it can only match the `user_message` update whose `messageId` equals the prompt response's `messageId`. Both SDKs emit exactly that.
- **`idle` is ambiguous before `running`.** `simple_agent_v2` emits a `state_update: idle` right after `session/new` (its initial ready state), and the upstream client example explicitly says "an idle update queued before running is only the session's earlier ready state" (rust-sdk `md/protocol-v2-quickstart.md:48-52`). A v2 TCK must wait for `running` before treating the next `idle` as turn completion, or it will mis-score agents that publish a ready state. testy does *not* emit that initial idle; `simple_agent_v2` does — so testy alone will not catch this bug in the TCK.
- **Capability-conditional tiering is coarser in v2.** `capabilities.session: {}` is a single marker; the sub-capabilities (`prompt`, `mcp`, `delete`, `additionalDirectories`, `fork`) are separate object markers, and `auth/login`/`auth/logout` are gated by a non-empty `authMethods`, *not* by `capabilities.auth` (schema crate `src/v2/agent.rs:139-144`, `:3968-3976`). With testy advertising only `session: {}`, essentially every optional family will SKIP — which means the v2 cross-check will exercise far less of the suite than the v1 one does against `conforming_full.py`. Plan for that: the v2 cross-check is a plumbing sanity check, not coverage.
- **Unobservable from the client side:** whether an agent *persists* replayable history (v2 `session/resume` replay is optional per rust-sdk `md/protocol-v2.md:133-134` and testy only replays for `replayFrom: {type:"start"}`); whether the absence of a malformed-line reply is deliberate or a swallowed crash (Python); and whether a `-32601` for a baseline `session/*` method means "not advertised" or "advertised but unimplemented" (the Python runtime produces the same code for both — item 19).
- **What a conforming vs. non-conforming v2 agent looks like on the initialize probe:** conforming = `{"protocolVersion":2,"info":{"name":…,"version":…},…}`; non-conforming shapes a TCK should catch = missing `info` (v2 makes it required, unlike v1's optional `agentInfo`), `protocolVersion` echoed as something other than 2 when the agent claims v2, and `capabilities` present but with a non-object `session`.

## Discrepancies

1. **Unsupported-version error code diverges between the two native v2 runtimes.** Rust: `-32600 Invalid request` (`src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:857-864`). Python: `-32602 Invalid params` with `{"expectedProtocolVersion":2,"receivedProtocolVersion":N}` (`src/acp/experimental/v2/_initialization.py:27-31`). TypeScript (stale checkout) matches Python's data shape (`src/v2/acp.ts:180-186`). **TCK-relevant informational item** — do not assert a code here until the spec settles it.
2. **Malformed-JSON handling diverges, same as in v1.** Rust replies `-32700` with `id: null` and keeps going; Python emits nothing and logs a traceback. **TCK-relevant informational item** (the v1 suite already treats this as `ACP-INFO-PARSE-001`; carry that forward to v2 unchanged).
3. **Pre-initialize / pipelined traffic diverges.** Rust native v2 rejects immediately with `-32600` even while `initialize` is in flight (documented at rust-sdk `md/protocol-v2.md:330-331`); Python *awaits* the in-flight initialization and then serves the request (`src/acp/experimental/v2/_initialization.py:61-67`). Both reject when nothing is in flight. **TCK-relevant informational item, plus a hard constraint on how the TCK drives the handshake.** Not a bug on either side — Rust documents it deliberately — but it is a real interop hazard worth reporting upstream.
4. **The schema crate contradicts itself about what `capabilities.session: {}` implies.** `AgentCapabilities.session`'s doc comment says `{}` means "the agent supports the baseline session methods: `session/new`, `session/prompt`, `session/cancel`, and `session/update`" (schema crate `src/v2/agent.rs:3948-3953`), while `SessionCapabilities`'s own doc says `{}` means "`session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`, `session/cancel`, and `session/update`" (`src/v2/agent.rs:4138-4146`). rust-sdk `md/testy.md:81-83` sides with the longer list ("the complete advertised v2 session baseline: initialize, session/new, session/list, session/resume, session/close, session/prompt, session/cancel, session/update"), and testy implements the longer list. **This directly determines whether a v2 TCK's `session/list`/`resume`/`close` tests are MANDATORY-when-`session: {}` or CAPABILITY-tier.** I am not resolving it — it is a spec question (see Open questions).
5. **Rust router vs. native Rust disagree on `protocolVersion: 65535`.** Router: normalizes to 2 and answers `2` (if the params parse as v2). Native `Agent.v2()`: `-32600`. Same SDK, same version, two answers depending on how the agent was wired. Not a bug — but it means "the Rust reference SDK's behavior" is not a single answer, and a TCK baseline must name which binary it was measured against.
6. **The v1 `ACP-INIT-003` failure message changes with the dual-version testy build** (`-32602 missing field \`info\`` instead of an echoed `65535`), even though the pass/fail table is unchanged. Flagged so the cross-check baseline in `docs/cross-check.md` is not silently invalidated if someone switches the build flags.
7. No contradiction found between the two SDKs on the actual v2 *message shapes* — initialize result, prompt acceptance, the four-update prompt lifecycle, `{}` for empty results, and `-32601` for unknown/`_`-prefixed methods are byte-compatible (modulo JSON key order) across testy, `simple_agent_v2`, and the Python v2 runtime.

## Open questions

- **Does `capabilities.session: {}` make `session/list` / `session/resume` / `session/close` mandatory in v2?** Discrepancy 4 above. Route to the spec-side v2-delta researcher; it decides the tier of at least six prospective TCK requirements.
- **What is the normative v2 answer to an unsupported requested `protocolVersion`** (error vs. downgrade-and-answer-2; and if error, which code)? Discrepancy 1/5. Route to the version-negotiation researcher.
- **Is `_meta` / unknown-root-key hygiene expressible against the v2 JSON Schema,** i.e. does `schema/v2/schema.json` set `additionalProperties` anywhere, or does the v2 TCK need the same hand-written `find_unknown_root_keys` gap-filler this repo already has for v1? Not investigated — out of my scope.
- **Should the TCK vendor `schema/v2/schema.json` or `schema/v2/schema.unstable.json`,** and how should it track `2.0.0-alpha.N` churn (the draft has moved 5 times)? A refresh policy question for the orchestrator.
- **Adopt the TypeScript SDK as a third cross-check target?** It has the only upstream-authored runnable dual-version example agent, but the local checkout is stale (2026-07-25) and no skill governs it. Needs a decision plus a skill/`.repo` before anyone depends on it.
- **Should the Python v1 cross-check pin move from `1.0.0rc1` to `1.0.0rc2`?** I ran the v1 suite against `echo_agent.py` on `rc2` and got exactly the documented baseline (`ACP-INIT-003` MANDATORY FAIL, `ACP-INIT-004` + `ACP-JSONRPC-004` ADVISORY FAIL), so the bump is safe — but it is the v1 maintainer's call, and a v2 fixture will need `rc2` regardless (the v2 handler signatures changed in `9d07d78`).
