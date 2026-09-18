# How should the ACP TCK run the Rust SDK's `testy` agent (and the Python SDK's `examples/echo_agent.py`) as independently-implemented agents for cross-checking the TCK, and how would each be expected to score?

**Sources checked:**

- `agentclientprotocol/rust-sdk` @ `8bc6275a3d6b5accf102718d715017bfbb918c5c` (2026-09-18, `main`, `feat(acp): update schema dependency to 1.9.0 (#366)`) — local clone `/Users/eugene/Documents/JetBrains/projects/acp-rust-sdk`, `git pull --ff-only` → "Already up to date". Citations prefixed `[rust]`.
- `agentclientprotocol/python-sdk` @ `d92b9683346c9e109895503878315e06d3eedb99` (2026-09-18, `main`, `chore: migrate HTTP client dependency from httpx to httpx2 (#143)`) — local clone `/Users/eugene/Documents/JetBrains/projects/acp-python-sdk`, `git pull --ff-only` → fast-forwarded from `c1004f8c`. Citations prefixed `[py]`.
- This repo @ `09d9d4c17237f7a6583fca09e4c34f01eed350c4` (`src/tck/requirements.py`, `src/tck/conformance/*`, `src/tck/plugin.py`). Citations unprefixed.
- **Measured, not inferred**: every build time, `--help` behaviour, wire transcript and TCK scorecard below was produced by actually building and running the binaries and the TCK on this machine (Apple M3 Max, 16 cores, macOS 25.6, `cargo 1.97.1` / `rustc 1.97.1`, `uv 0.11.15`). Probe scripts were written to `/tmp` only. Nothing in any of the three checkouts' tracked files was modified; `git status` in both SDK checkouts is clean apart from a pre-existing untracked `.idea/`.
- **Not** consulted: `check-specification`, `check-a2a-tck`. This is a tooling/operations question; nothing here is a normative protocol claim. Where a spec claim is needed it is taken second-hand from `.agents/research/acp-v1-protocol-surface.md` / `acp-v1-session-capabilities.md`.
- ⚠️ **Caveat on the TCK side:** this repo's working tree was being edited **concurrently by another agent** while these runs happened (the slice-5 hardening work). At run time the only uncommitted files were `src/tck/harness/process.py` and `src/tck/harness/transcript.py` (bounded stderr capture + `max_line_bytes`); by the time this report was written the dirty set had grown to include `src/tck/plugin.py`, `src/tck/requirements.py`, `src/tck/validation.py` and every `src/tck/conformance/test_*.py`. The scorecards in §3 are therefore measurements of the tree **as of `09d9d4c` plus the two harness files**, and all line citations into this repo are to `09d9d4c`. Re-run the cross-check after that slice lands; if a requirement or assertion changed, §3's per-requirement rows are the thing to re-verify (the reasons behind them, cited to fixture source, do not change).

**Confidence:** **high** for everything in §1–§2 and for the scorecards in §3 — they are direct measurements of the current HEADs, not predictions. **Medium** for the CI numbers in §4 (measured on a 16-core M3 Max with a warm `~/.cargo/registry`; a 4-core GitHub-hosted runner will be slower by a factor I estimate rather than measured) and for the claim that `testy`'s behaviour is stable across upstream releases (it is a test fixture with no stability promise).

---

## Answer

Run `testy` as a plain stdio agent with **no arguments at all** — it has no CLI, no env-var switches, and no config; scenarios are selected purely by **prompt text** (`wait_for_cancel`, `full`, `callbacks`, `echo <msg>`, …), so the TCK drives it as `acp-tck --cancel-prompt wait_for_cancel -- /path/to/target/debug/testy`. Build it with `cargo build -p agent-client-protocol-test --bin testy --no-default-features` (strict v1; the default `unstable` feature is what adds the non-v1 `mcpCapabilities.acp` field to the wire) — measured **17.1 s cold** for 166 crates on a 16-core machine with a warm cargo registry, needing nothing but a Rust ≥ 1.88 toolchain; the binary lands at `target/debug/testy` and is not published anywhere (`publish = false`, and the upstream GitHub releases carry **zero** assets), so the TCK must vendor-and-build. **Measured score: `testy` is CONFORMANT — 15/15 MANDATORY PASS** (with `--cancel-prompt wait_for_cancel`; 13 PASS + 2 cancel SKIPPED with the default long prompt, because `testy` answers any unrecognised prompt instantly), with the single ADVISORY failure `ACP-INIT-004` (it never sets `agentInfo`). `examples/echo_agent.py` is also **CONFORMANT — 13/15 MANDATORY PASS + 2 permanently-SKIPPED cancel tests** (it has no cancel handler and cannot ever exercise them), same `ACP-INIT-004` failure — **but only when pinned to `agent-client-protocol==1.0.0rc1` or run from the checkout**: resolved via its PEP 723 header it gets the latest *stable* `0.12.1`, whose prompt deserializer rejects a plain `{"type":"text","text":"hello"}` block with `-32602`, making it **NOT CONFORMANT** (a released-SDK bug, not an agent bug). The single most important finding for the TCK itself is a **false negative**: `ACP-INIT-003` **PASSES** for both agents even though both echo `65535` verbatim, because `test_unsupported_version_still_succeeds` only asserts "a result, with an integer `protocolVersion`" and never checks that the returned version is one the agent actually supports — the test is strictly weaker than the requirement text it is bound to.

---

## Requirements

Tiering here is about *TCK cross-check engineering*, not protocol MUSTs.

| # | Requirement on the cross-check setup | Tier | Evidence |
|---|---|---|---|
| T1 | `testy` must be built from a vendored checkout; no prebuilt artefact exists | MUST | `publish = false` [rust] `src/agent-client-protocol-test/Cargo.toml:10`; `gh release view --json assets` → `{"assets":[]}` for `v2.1.0`, and no `agent-client-protocol-test-*` tag exists at all |
| T2 | Use `--no-default-features` for a strict-v1 fixture | SHOULD | default = `["unstable"]` [rust] `src/agent-client-protocol-test/Cargo.toml:13-14`; measured wire delta: `mcpCapabilities.acp: false` appears only in the default build (§1.3) |
| T3 | The TCK must pass `--cancel-prompt wait_for_cancel` when cross-checking with `testy`, or the cancel tier is untested | MUST (for coverage) | `parse_command` [rust] `testy.rs:1657-1682` + `TestyScenario::from_prompt` `:130-142`; measured: default prompt → 2 × SKIPPED, `wait_for_cancel` → 2 × PASS (§3.1) |
| T4 | `echo_agent.py` must be version-pinned, not PEP 723-resolved | MUST | measured: PyPI-stable `0.12.1` fails `session/prompt` with `-32602` on a baseline text block (§3.3) |
| T5 | Neither fixture may be used to validate version negotiation | MUST NOT | `InitializeResponse::new(request.protocol_version)` [rust] `testy.rs:431`; `InitializeResponse(protocol_version=protocol_version)` [py] `examples/echo_agent.py:47` |
| T6 | Neither fixture may be used as a positive fixture for `session/load` replay | MUST NOT | `testy`'s load handler responds immediately with no updates [rust] `testy.rs:1887-1899`; measured (§2.6). `echo_agent` has no `load_session` at all yet answers `{}` |
| T7 | `testy`'s `full`/`callbacks` scenarios must **not** be used as the TCK's prompt fixture | MUST | measured: with `clientCapabilities: {}` the turn ends in a `-32602` **error**, not a stop reason (§2.5) |
| T8 | Treat both fixtures as version-pinned inputs, not as moving targets | SHOULD | `agent-client-protocol-test` is `version = "0.11.0"` but unpublished and untagged; nothing upstream promises `testy`'s prompt vocabulary is stable |

---

## Details

### 1. Building `testy`

#### 1.1 Feature matrix

`agent-client-protocol-test` ([rust] `src/agent-client-protocol-test/Cargo.toml:12-15`):

```toml
[features]
default = ["unstable"]
unstable = ["agent-client-protocol/unstable"]
unstable_protocol_v2 = ["agent-client-protocol/unstable_protocol_v2"]
```

Three features, all forwarding into the core crate ([rust] `src/agent-client-protocol/Cargo.toml:32-53`):

| Feature | What it pulls in | Effect on `testy` |
|---|---|---|
| *(none)* — `--no-default-features` | core crate with `default = []` | **strict stable v1 only.** This is the documented "stable-only coverage" build ([rust] `md/testy.md:23-27`) |
| `unstable` (the **default**) | schema features `unstable_end_turn_token_usage`, `unstable_llm_providers`, `unstable_mcp_over_acp`, `unstable_plan_operations`, `unstable_session_compaction`, `unstable_session_fork`, `unstable_session_notices` ([rust] `src/agent-client-protocol/Cargo.toml:37-45`) | **no code changes** — `grep 'feature = "unstable"' src/agent-client-protocol-test/src` returns **zero hits**, and there are zero `cfg(feature="unstable")` sites in the core crate either; the only effect is that *schema types gain fields*, which then serialize (§1.3) |
| `unstable_protocol_v2` | `agent-client-protocol-schema/unstable_protocol_v2` | compiles in `testy/v2.rs` and swaps `Testy::new().connect_to(...)` for `Testy::new().protocol_router().connect_to(...)` ([rust] `src/bin/testy.rs:10-19`), i.e. the binary then routes v1/v2 off the `initialize` version. **Do not use for a v1 TCK** |

#### 1.2 Exact commands, prerequisites, measured times

```bash
# strict-v1 fixture (recommended)
cargo build -p agent-client-protocol-test --bin testy --no-default-features
# → target/debug/testy
```

Documented at [rust] `md/testy.md:23-30`; the binary declaration is [rust] `src/agent-client-protocol-test/Cargo.toml:21-23`.

**Prerequisites: a Rust toolchain and `cargo`, and nothing else.** There is no `rust-toolchain.toml` in the repo (`cat rust-toolchain.toml` → absent), so the host toolchain is used; the workspace requires `rust-version = "1.88.0"` ([rust] `Cargo.toml:23`). No `cc`-heavy native deps are needed for this binary: with `--no-default-features` the build pulls 166 crates, all pure Rust in this configuration (the build succeeded on a stock toolchain with no system packages installed). `reqwest` is in the graph via `rmcp`'s `transport-streamable-http-client-reqwest` feature but is configured `default-features = false, features = ["rustls", "json"]` ([rust] `Cargo.toml:66`), so no OpenSSL. Network access is needed only to populate `~/.cargo/registry`.

**Measured (Apple M3 Max, 16 cores, warm cargo registry, no network fetch):**

| Scenario | Command | Wall time | Notes |
|---|---|---|---|
| **Cold** — empty `CARGO_TARGET_DIR` | `--no-default-features` | **17.13 s** (cargo's own "Finished … in 17.13s"; `/usr/bin/time -p real 17.16`) | 166 `Compiling` lines; resulting target dir 1.1 GiB, binary 43.5 MB |
| Cold, default features (`unstable`) | *(no flag)* | 17.93 s | same order |
| Warm target, only local crates dirty (`cargo clean -p agent-client-protocol -p agent-client-protocol-test`) | `--no-default-features` | **4.71 s** | the realistic "cache hit, SDK bumped" CI case |
| Warm target, nothing dirty | — | < 0.5 s | no-op |

A build was **attempted and succeeded**; the estimate ceiling in `.agents/research/reference-sdks-as-harness.md:158` ("on the order of minutes") was pessimistic for a single-binary `--no-default-features` build. Scale for CI in §4.

#### 1.3 `--help` and the CLI surface: there is none

`src/bin/testy.rs` is 22 lines and never reads `std::env::args` ([rust] `src/agent-client-protocol-test/src/bin/testy.rs:1-22`); `clap` is not a dependency of the crate ([rust] `src/agent-client-protocol-test/Cargo.toml:26-39`). **Measured:**

```
$ printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}\n' \
    | ./target/debug/testy --help --nonsense foo
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,...}}
exit=0
```

So: **`--help` prints no help.** Arguments are silently ignored and the process speaks ACP on stdio regardless. It exits `0` on stdin EOF (measured). The only environment influence is `tracing_subscriber::fmt().with_writer(std::io::stderr).init()` ([rust] `src/bin/testy.rs:6-8`), i.e. structured logs on **stderr** (ANSI-coloured, `RUST_LOG`-filterable — the crate enables `tracing-subscriber/env-filter` via the workspace dep, [rust] `Cargo.toml:58`; the filter claim is inference from that feature, the stderr-only claim is measured). Nothing is ever written to stdout except JSON-RPC lines — good for `ACP-TRANSPORT-001`.

#### 1.4 Does the `unstable` default break strict-v1 validation? Measured: no, but it is visible

Identical `initialize` request, two binaries, diffed:

```
--no-default-features : "mcpCapabilities":{"http":true,"sse":false}
default (unstable)    : "mcpCapabilities":{"http":true,"sse":false,"acp":false}
```

`acp` is not a property of `McpCapabilities` in this repo's vendored schema (`src/tck/schema/v1/schema.json`, `$defs.McpCapabilities` has only `http`, `sse`, `_meta`). It does **not** cause a failure, because **no `$def` in the vendored schema sets `additionalProperties: false`** (checked: 0 of 170), so unknown properties validate. Confirmed by running the TCK against both binaries: identical scorecards (§3.1). Recommendation stands for `--no-default-features` anyway — it is the honest strict-v1 fixture, and it insulates the cross-check from any future strict extra-field assertion.

### 2. Driving `testy`

#### 2.1 Scenario selection is **prompt text only**

No flags, no env. `process_prompt` concatenates the `text` of every `ContentBlock::Text` in the prompt, space-joined, ignoring all other block types ([rust] `testy.rs:1646-1655`), then `parse_command` ([rust] `testy.rs:1657-1682`) resolves it in this order:

1. empty/whitespace → `Greet`;
2. **parses as JSON `TestyCommand`** → that command (`#[serde(tag = "command", rename_all="snake_case")]`, [rust] `testy.rs:57-83`), e.g. `{"command":"run_scenario","scenario":"wait_for_cancel"}`;
3. `help` (case-insensitive) → `Help`;
4. a scenario alias (`TestyScenario::from_prompt`, [rust] `testy.rs:130-142`) → `RunScenario`;
5. `echo <message>` prefix → `Echo`;
6. **anything else → `Greet`**, i.e. `"Hello, world!"` + `end_turn`.

Point 6 is the operationally important one: an unrecognised prompt is never an error and never slow.

| Goal | Prompt text | Measured result |
|---|---|---|
| **normal short turn** | anything unrecognised, e.g. `hello` | one `agent_message_chunk` `"Hello, world!"` (with `messageId: "testy-message-end-turn-<n>"`), then `{"stopReason":"end_turn"}` |
| **long/hanging turn for cancel** | `wait_for_cancel` (aliases `wait for cancel`; JSON `{"command":"run_scenario","scenario":"wait_for_cancel"}`) | **no output at all** until `session/cancel` arrives (measured: nothing for 1.5 s), then `{"stopReason":"cancelled"}` and **no** trailing `agent_message_chunk` (suppressed at [rust] `testy.rs:668`). Implementation: `wait_for_cancelled` parks on a `tokio::sync::Notify` ([rust] `testy.rs:380-391`, `:752-755`) |
| `session/request_permission` | `callbacks` or `full` | `session/request_permission` with two options (`allow_once`, `reject_once`) — [rust] `testy.rs:1309-1335` |
| `fs/read_text_file` (+ `fs/write_text_file`) | `callbacks` or `full` | `fs/write_text_file` to `/tmp/testy-write.txt`, then `fs/read_text_file` of the same path with `line:1, limit:20` — [rust] `testy.rs:1340-1367` |
| `terminal/*` | `callbacks` or `full` | `terminal/create` (`printf`), `terminal/output`, `terminal/wait_for_exit`, `terminal/kill`, `terminal/release` — [rust] `testy.rs:1372-1449`. `full` additionally creates/releases a terminal for tool-call content ([rust] `testy.rs:761-788`, `:1055-1104`) |
| every stable `session/update` variant | `session_updates` (aliases `session updates`, `updates`) or `full` | `session_info_update`, `current_mode_update` (correct schema name `currentModeId`), `config_option_update`, `available_commands_update`, `usage_update`, then user/thought/agent chunks with text/image/audio/resource_link/resource content, tool_call + two tool_call_update, plan — [rust] `testy.rs:809-849`, `:851-936`, `:937-1054` |
| elicitations only | `elicitations` / `elicitation` / `elicit` | `elicitation/create` form + URL modes; **errors out** if client caps missing (§2.5) |
| report cancel state | `cancel_status` — **note the alias `cancel` also maps here**, [rust] `testy.rs:137` | `cancel_status: not_cancelled` + `end_turn` |
| MCP | JSON only: `{"command":"call_tool","server":…,"tool":…}` / `{"command":"list_tools","server":…}` | connects to the stdio/http MCP server lazily, at this point only ([rust] `testy.rs:638-657`, `:1460-1546`) |
| self-documentation | `help` | one chunk listing all commands (measured; text at [rust] `testy.rs:1684-1697`) |

#### 2.2 `initialize`

Handler [rust] `testy.rs:421-435`; capabilities [rust] `testy.rs:393-412`; auth methods [rust] `testy.rs:414-419`. **Measured response to `{"protocolVersion":1,"clientCapabilities":{}}` (`--no-default-features`):**

```json
{"protocolVersion":1,
 "agentCapabilities":{
   "loadSession":true,
   "promptCapabilities":{"image":true,"audio":true,"embeddedContext":true},
   "mcpCapabilities":{"http":true,"sse":false},
   "sessionCapabilities":{"list":{},"delete":{},"additionalDirectories":{},"resume":{},"close":{}},
   "auth":{"logout":{}}},
 "authMethods":[{"id":"testy-agent-auth","name":"Testy agent auth",
                 "description":"Deterministic no-op authentication for ACP client testing"}]}
```

- **No `agentInfo`.** The field exists in the schema crate (`agent_info: Option<Implementation>`, default `None` — `~/.cargo/registry/…/agent-client-protocol-schema-1.9.0/src/v1/agent.rs:154,175,196`) and `testy` never sets it. `grep -rn agent_info src/agent-client-protocol/src src/agent-client-protocol-test/src` → **no hits anywhere in the Rust SDK**. The builder's `.name("test-agent")` ([rust] `testy.rs:1838`) is *only* a debugging log label — "Set the \"name\" of this connection -- used only for debugging logs" ([rust] `src/agent-client-protocol/src/jsonrpc.rs:1208-1212`), and it is indeed what appears in the stderr tracing spans (measured). So **`ACP-INIT-004` fails structurally, not incidentally.**
- **`protocolVersion` is echoed verbatim.** Measured: `1 → 1`, `2 → 2`, `65535 → 65535`. Source: `InitializeResponse::new(request.protocol_version)` [rust] `testy.rs:431`.
- A *non-integer* `protocolVersion` is rejected at deserialization: measured `{"protocolVersion":"1"}` → `-32602` with `data: {"error":"invalid type: string \"1\", expected u16","json":{…},"phase":"deserialization"}`.
- The only thing `initialize` records from the client is `client_capabilities.elicitation` ([rust] `testy.rs:426-428`). **`clientCapabilities.fs` and `.terminal` are never inspected**, which is why §2.5 happens.
- `initialize` is **not** required first: measured, `session/new` as the very first message succeeds. There is no state machine.

#### 2.3 `session/new`

Handler [rust] `testy.rs:1866-1883`; ids from `create_session` [rust] `testy.rs:242-258`.

- Session ids are **deterministic and sequential**: `testy-session-1`, `testy-session-2`, … (measured). Ideal for golden transcripts, and it satisfies `ACP-SESSION-002` (distinct ids).
- Response always carries **both** `modes` (`chat`/`plan`, current `chat` — [rust] `testy.rs:1615-1626`) and `configOptions` (one `select` option `verbosity` ∈ {`brief`,`normal`,`verbose`}, current `normal` — [rust] `testy.rs:1628-1642`). So by `acp-v1-session-capabilities.md` §0's inference rule, `testy` advertises *inferred* support for both `session/set_mode` and `session/set_config_option`.
- **`mcpServers` is required**: measured, omitting it → `-32602` `missing field 'mcpServers'` (typed deserialization, not an explicit check).
- **`cwd` is NOT validated for absoluteness**: measured, `{"cwd":"relative/dir"}` → success, and the relative path is later echoed verbatim in `session/list`. `testy` is therefore **not** a fixture for any "reject relative `cwd`" test.
- `additionalDirectories` is accepted and echoed in `session/list` (measured). Stdio-shape `mcpServers` entries are accepted without any connection attempt at `session/new` (measured; lazy connection confirmed at [rust] `testy.rs:1460-1546`).

#### 2.4 `session/load`, `list`, `delete`, `resume`, `close`, `set_mode`, `set_config_option`

| Method | Handler | Measured behaviour |
|---|---|---|
| `session/load` | [rust] `testy.rs:1884-1902` → `upsert_session` `:274-290` | **advertises `loadSession: true` and replays nothing.** Measured: after a real prompt turn on `testy-session-1`, `session/load` of that id returned `{modes, configOptions}` with **zero** `session/update` notifications. An **unknown** id silently becomes a new session and returns success (measured with `sessionId: "never-existed"`, which then appeared in `session/list`). Confirms `acp-v1-session-capabilities.md` Discrepancy 7 empirically |
| `session/list` | [rust] `testy.rs:474-495` | returns `sessions` sorted by `sessionId` string ([rust] `:493`), excluding `closed` sessions ([rust] `:483-485`); `title` is a fixed `"Testy session"`, `updatedAt` a fixed `"2026-01-01T00:00:00Z"` (measured — fully deterministic). `cwd` filter is exact-match. **`params` must be present**: measured, omitting `params` entirely → `-32602` `invalid type: null, expected struct ListSessionsRequest` (exactly the interop hazard flagged at `acp-v1-session-capabilities.md:170`) |
| `session/delete` | [rust] `testy.rs:497-518` | `{}`; unknown id → **success** (measured) |
| `session/resume` | [rust] `testy.rs:1903-1921` → same `upsert_session` | accepted **without** `mcpServers` (measured); returns `{modes, configOptions}`; sends no history updates (there is no history) |
| `session/close` | [rust] `testy.rs:520-541` | `{}`; unknown id → **success**; marks `cancelled`+`closed` so an in-flight prompt resolves `cancelled` via `finish_prompt` ([rust] `:316-335`) |
| `session/set_mode` | [rust] `testy.rs:543-570` | `{}` for `chat`/`plan`; `-32602` for anything else (measured: `bogus` → `-32602` with `data: "unsupported mode \`bogus\`; …"`). Emits **no** `current_mode_update` echo |
| `session/set_config_option` | [rust] `testy.rs:572-612` | returns the **complete** `configOptions` list with the new `currentValue` (measured: `verbosity=brief` → full option object with `currentValue:"brief"`), satisfying `acp-v1-session-capabilities.md` O2. Accepts either `"value":"brief"` or `{"value":…}` ([rust] `:1798-1818`) |
| `authenticate` / `logout` | [rust] `testy.rs:451-472` | `{}` for `testy-agent-auth`; `-32602` for any other method id |
| **unknown method** | SDK-level, [rust] `src/agent-client-protocol/src/jsonrpc/incoming_actor.rs:618-621` | `-32601` `{"code":-32601,"message":"Method not found","data":"frobnicate/unknown"}` (measured). Unknown **notifications** are logged and ignored, no response ([rust] `incoming_actor.rs:612-615`; measured) |
| **invalid JSON line** | SDK-level | measured: `{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error","data":{"line":"{not json"}}}` — and the connection stays fully usable afterwards |

#### 2.5 What `testy` does when the client advertises `clientCapabilities: {}` — **the important trap**

Measured, with the TCK-style empty client capabilities and a mock client answering every inbound request with `-32601`:

1. `testy` **still sends** `session/request_permission`, `fs/write_text_file`, `fs/read_text_file`, `terminal/create` (twice), etc. It never consults `clientCapabilities.fs`/`.terminal` — only `.elicitation` is stored ([rust] `testy.rs:426-428`). Each callback's outcome (including the `-32601`) is merely appended to the scenario report and the scenario continues ([rust] `testy.rs:1327-1370`, `request_report_until_cancelled`).
2. The turn then **fails with a JSON-RPC error instead of a stop reason**: `{"code":-32602,"message":"Invalid params","data":"client does not support form elicitation"}` — the deliberate gate at [rust] `testy.rs:1146-1153` / `:1766-1768`, documented at [rust] `md/testy.md:72-77`.

Consequences for the TCK: (a) the `full`/`callbacks`/`elicitations` prompts are **unusable** as prompt fixtures unless the TCK's mock client advertises `elicitation` form *and* URL capabilities (T7); (b) `testy` is a good *negative* fixture for a future "agent calls a client method whose capability was not advertised" probe — it is a client-direction violation, deliberately unpoliced; (c) the TCK's own prompt tests, which send short unrecognised text, never touch any of this — which is exactly why they pass (§3.1).

Agent→client request ids are **UUID strings** (measured, e.g. `"6455412c-754f-495d-b1dc-9ee2b032092f"`), useful if the TCK ever asserts that a client must echo string ids.

#### 2.6 Cancellation semantics

`session/cancel` → `mark_cancelled` ([rust] `testy.rs:344-358`): if a prompt is active it sets `cancelled` and wakes the `Notify`; if **no** prompt is active it only sets `pending_cancel_status` and emits nothing (measured: zero output — which is what makes `ACP-JSONRPC-003` pass). `finish_prompt` ([rust] `:316-335`) converts the stop reason to `Cancelled` if either `cancelled` or `closed`, and the final `agent_message_chunk` is suppressed for a cancelled turn ([rust] `:668-677`). Measured end-to-end: `wait_for_cancel` prompt → silence → `session/cancel` → `{"stopReason":"cancelled"}`, with **no** `session/update` before or after. Both `ACP-CANCEL-001` (success result, `cancelled`) and `ACP-CANCEL-002` (no late updates) are satisfied, the latter vacuously.

### 3. Measured TCK outcomes

All runs: `uv run --no-sync python -m tck [--cancel-prompt …] -- <agent cmd>`.

#### 3.1 `testy` — CONFORMANT

| Requirement | Tier | `--cancel-prompt wait_for_cancel` | default cancel prompt | Why (cited) |
|---|---|---|---|---|
| ACP-TRANSPORT-001 | MANDATORY | **PASS** | PASS | all stdout is NDJSON; tracing goes to stderr ([rust] `src/bin/testy.rs:6-8`) |
| ACP-TRANSPORT-002 | MANDATORY | **PASS** | PASS | `serde_json` output, ASCII-escaped |
| ACP-JSONRPC-001 | MANDATORY | **PASS** | PASS | measured: int `424242` and string `"tck-string-id"` both echoed |
| ACP-JSONRPC-002 | MANDATORY | **PASS** | PASS | `-32601` object with int `code` + string `message` ([rust] `incoming_actor.rs:620`) |
| ACP-JSONRPC-003 | MANDATORY | **PASS** | PASS | `session/cancel` on an idle session produces nothing ([rust] `testy.rs:344-358`) |
| ACP-JSONRPC-004 | ADVISORY | **PASS** | PASS | exactly `-32601` ([rust] `incoming_actor.rs:620`) |
| ACP-JSONRPC-005 | ADVISORY | **PASS** | PASS | connection survives; measured also across `-32700` |
| ACP-INIT-001 | MANDATORY | **PASS** | PASS | schema-valid `InitializeResponse`, integer version ([rust] `testy.rs:430-434`) |
| ACP-INIT-002 | MANDATORY | **PASS** | PASS | echoes `1` for `1` ([rust] `testy.rs:431`) |
| **ACP-INIT-003** | MANDATORY | **PASS** ⚠️ | PASS ⚠️ | **false negative.** `testy` echoes `65535` ([rust] `testy.rs:431`; measured). The requirement text says "carrying its latest supported version", but `test_unsupported_version_still_succeeds` (`src/tck/conformance/test_initialize.py:48-61`) asserts only `"result" in msg` and `isinstance(version, int)` — see §5 |
| ACP-INIT-004 | ADVISORY | **FAIL** | FAIL | no `agentInfo`; the field is never set anywhere in the Rust SDK ([rust] `testy.rs:430-434`) |
| ACP-SCHEMA-001 | MANDATORY | **PASS** | PASS | passes for **both** feature builds; `mcpCapabilities.acp` is tolerated because no `$def` sets `additionalProperties:false` (§1.4) |
| ACP-SESSION-001 | MANDATORY | **PASS** | PASS | `testy-session-1`, schema-valid ([rust] `testy.rs:1866-1883`) |
| ACP-SESSION-002 | MANDATORY | **PASS** | PASS | sequential counter ([rust] `testy.rs:250-257`) |
| ACP-PROMPT-001 | MANDATORY | **PASS** | PASS | unrecognised text → `Greet` → `end_turn` ([rust] `testy.rs:1681`, `:629`) |
| ACP-PROMPT-002 | MANDATORY | **PASS** | PASS | the single `agent_message_chunk` is schema-valid and carries the right `sessionId` ([rust] `testy.rs:670-676`, `:1774-1780`) |
| ACP-PROMPT-003 | ADVISORY | **PASS** | PASS | non-text blocks are simply ignored by `extract_text_from_prompt` ([rust] `testy.rs:1646-1655`), so the turn still ends `end_turn` |
| ACP-CANCEL-001 | MANDATORY | **PASS** | **SKIPPED** | `wait_for_cancel` parks until cancelled ([rust] `testy.rs:752-755`); the default long prompt is unrecognised → instant `Greet`, so `run_prompt` never gets to interrupt |
| ACP-CANCEL-002 | MANDATORY | **PASS** | **SKIPPED** | same; no updates at all during a cancelled turn ([rust] `testy.rs:668`) |

Totals — with `wait_for_cancel`: **MANDATORY 15 PASS / 0 FAIL / 0 SKIPPED; ADVISORY 3 PASS / 1 FAIL; VERDICT: CONFORMANT** (17 passed, 1 failed, 3.1 s). With the default prompt: MANDATORY 13 PASS / 2 SKIPPED, same verdict. Identical scorecard for the default-features (`unstable`) binary.

#### 3.2 `echo_agent.py` from the checkout / pinned to `1.0.0rc1` — CONFORMANT

How to run (both measured):

```bash
# (a) from the checkout, using its own uv env
acp-tck --agent-cwd /path/to/acp-python-sdk -- uv run --no-sync python examples/echo_agent.py
# (b) standalone, version-pinned (bypasses the PEP 723 header on purpose)
acp-tck -- uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python /path/to/echo_agent.py
```

| Requirement | Status | Why (cited) |
|---|---|---|
| ACP-TRANSPORT-001/002 | PASS | `NdjsonTransport` [py] `src/acp/_transport.py` |
| ACP-JSONRPC-001 | PASS | measured: int + string ids echoed |
| ACP-JSONRPC-002/004 | PASS | `-32601` with `data: {"method": …}` from the router ([py] `src/acp/router.py:180-182`) |
| ACP-JSONRPC-003 | PASS | `session/cancel` un-handled ⇒ notification silently dropped (measured: no response) |
| ACP-JSONRPC-005 | PASS | measured |
| ACP-INIT-001/002 | PASS | `InitializeResponse(protocol_version=protocol_version)` [py] `examples/echo_agent.py:47` |
| **ACP-INIT-003** | **PASS** ⚠️ | echoes `65535` verbatim ([py] `examples/echo_agent.py:47`; measured) — same false negative as `testy` |
| ACP-INIT-004 | **FAIL** | bare `InitializeResponse` with no `agent_info` ([py] `examples/echo_agent.py:47`) |
| ACP-SCHEMA-001 | PASS | note it injects `_meta` (`{"echo": true}` on the chunk and its content, `{"source":"echo_agent"}` on the notification — [py] `examples/echo_agent.py:73-76`); `_meta` is schema-legal |
| ACP-SESSION-001/002 | PASS | `uuid4().hex` ([py] `examples/echo_agent.py:56`) — non-empty and distinct, but **non-deterministic** |
| ACP-PROMPT-001 | PASS | one chunk per block, `end_turn` ([py] `examples/echo_agent.py:70-77`) |
| ACP-PROMPT-002 | PASS | update carries the `sessionId` it was given (it never validates that the session exists) |
| ACP-PROMPT-003 | PASS | the `resource_link` block yields an extra chunk with `text: ""` (measured: `getattr(block,"text","")` → `""` at [py] `examples/echo_agent.py:71`) but the turn succeeds |
| ACP-CANCEL-001/002 | **SKIPPED (permanently)** | no `cancel` method on `EchoAgent` at all; the turn completes in single-digit ms, so `run_prompt` can never interrupt it. Measured skip reason: "prompt turn completed before `session/cancel` could be sent". **No prompt text can fix this** — unlike `testy`, there is no hang scenario |

Totals: **MANDATORY 13 PASS / 0 FAIL / 2 SKIPPED; ADVISORY 3 PASS / 1 FAIL; VERDICT: CONFORMANT** (7.5 s from the checkout, 8.1 s pinned standalone).

#### 3.3 `echo_agent.py` resolved via its PEP 723 header — **NOT CONFORMANT (released-SDK bug)**

`uv run /path/to/echo_agent.py` honours the inline metadata ([py] `examples/echo_agent.py:1-6`), which pins nothing, so uv installs the latest **stable** release, `0.12.1` (measured). Result:

```
MANDATORY      PASS=12, FAIL=1, SKIPPED=2
ADVISORY       PASS=2,  FAIL=2
VERDICT: NOT CONFORMANT (1 mandatory failures, 0 not tested)
```

`ACP-PROMPT-001` (MANDATORY) and `ACP-PROMPT-003` (ADVISORY) fail. Measured cause — a baseline text-only prompt is rejected:

```
--> {"id":5,"method":"session/prompt","params":{"sessionId":…,"prompt":[{"type":"text","text":"hello"}]}}
<-- {"id":5,"error":{"code":-32602,"message":"Invalid params",
      "data":{"errors":[{"type":"missing","loc":["type"],"msg":"Field required","input":{"text":"hello"}}]}}}
```

The published `0.12.1` deserializer strips/loses the `type` discriminator before validating the content block, so *every* prompt fails. This is fixed on `main` (`1.0.0rc1`): the same script against `==1.0.0rc1` passes (§3.2). **Determinism / operational caveats for this fixture:** random `uuid4` session ids defeat golden transcripts ([py] `:56`); `_meta` injection ([py] `:73-76`); it answers `session/load` with `{}` and `session/list` with `result: null` despite advertising **no** capabilities (measured — `result: null` is not schema-valid, but the TCK never calls either since the caps are absent, so it is invisible today); invalid JSON on stdin is logged and **dropped**, with no `-32700` (measured, [py] `src/acp/_transport.py:81-86`) — the opposite of `testy`; and the first run pays uv resolution cost (~3–7 s) unless the environment is pre-warmed.

### 4. CI feasibility

**No prebuilt binary exists, anywhere.** `agent-client-protocol-test` is `publish = false` ([rust] `src/agent-client-protocol-test/Cargo.toml:10`) — confirmed, so nothing on crates.io. `gh release list` shows only per-crate `release-plz` tags (`agent-client-protocol-v2.1.0` etc.); `gh release view --json assets` on the latest is `{"assets":[]}`, and **no release exists for `agent-client-protocol-test` at all**. Upstream CI (`.github/workflows/{ci,deny,mdbook,publish}.yml`) contains **zero** cache steps (`grep -rn 'cache\|Swatinem' .github/workflows` → no hits), so there is no upstream pattern to copy either. Building is the only option.

Recommended job shape:

```yaml
jobs:
  cross-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5                    # the TCK
      - uses: actions/checkout@v5                    # the fixture, pinned by SHA
        with:
          repository: agentclientprotocol/rust-sdk
          ref: 8bc6275a3d6b5accf102718d715017bfbb918c5c
          path: .fixtures/rust-sdk
      - uses: dtolnay/rust-toolchain@stable          # no rust-toolchain.toml upstream; >=1.88 needed
      - uses: Swatinem/rust-cache@v2                 # caches ~/.cargo/{registry,git} + target/
        with:
          workspaces: .fixtures/rust-sdk
          key: testy-nodefault
      - run: cargo build --manifest-path .fixtures/rust-sdk/Cargo.toml
             -p agent-client-protocol-test --bin testy --no-default-features
      - run: uv run acp-tck --cancel-prompt wait_for_cancel
             -- .fixtures/rust-sdk/target/debug/testy
```

Notes, with the measured numbers behind them:

- **Cache key must include the feature set.** A `--no-default-features` target dir and a default-features one are different artefacts; mixing them forces rebuilds. `Swatinem/rust-cache` keys on lockfile + rustc version, so add an explicit `key:`.
- **Size.** The target dir is **1.1 GiB** for this one binary (measured), which is large for the 10 GiB GitHub cache budget. Two mitigations: cache only `~/.cargo/registry` + `~/.cargo/git` and accept the full 17 s–3 min compile (dependencies dominate: 166 crates, of which 164 are third-party); or add `CARGO_PROFILE_DEV_DEBUG=0` / `debug = false`, which should cut both the 43.5 MB binary and the target dir substantially (untested here).
- **Time budget.** Measured 17.1 s cold / 4.7 s "SDK crates dirty" / <0.5 s no-op on 16 cores with a warm registry. A 4-core `ubuntu-latest` runner is roughly 4× less parallel, so expect **~1–3 min cold** plus ~20–40 s of crates.io download on a cold registry cache, and **~10–20 s** on a cache hit. This is comfortably inside a normal CI budget; there is no need for a prebuilt-binary release of our own.
- **Pin the fixture by SHA, not by branch.** `testy`'s prompt vocabulary is not a stability contract and a scenario rename would silently turn the cross-check's cancel tier into SKIPs (T3/T8).
- **The Python fixture is much cheaper and should run unconditionally**: `uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python echo_agent.py` needs no compiler and no checkout (copy the ~85-line example, or `actions/checkout` the python-sdk at a SHA). Pin the version (T4) or CI will break the day a new stable release ships. Consider running both the pinned-good and the `0.12.1` variants: the latter is a **free, real-world negative fixture** that the TCK correctly reports as NOT CONFORMANT (§3.3).
- **Assert the expected scorecard, not just the exit code.** Both fixtures currently produce a non-zero exit only via the ADVISORY `ACP-INIT-004` failure, which does not change the verdict; a cross-check job should diff `--report-json` against a committed expectation (e.g. "15 MANDATORY PASS, `ACP-INIT-004` FAIL") so a *new* regression is distinguishable from the known `agentInfo` gap.

---

## Testability notes

1. **`ACP-INIT-003` is currently untestable by the test bound to it.** Both independent agents echo an unsupported `65535` and both PASS. The requirement says the agent "returns a successful result carrying **its latest supported version**"; the test (`src/tck/conformance/test_initialize.py:48-61`) checks only success + integer type. A strengthened assertion needs a reference point the client can obtain — the natural one is the version returned for a `protocolVersion: 1` request (`ACP-INIT-002`): assert `result.protocolVersion <= max(1, that)` and, minimally, `!= 65535`. That would flip both fixtures to FAIL, which is the *correct* outcome (and the reason `reference-sdks-as-harness.md:197` warns neither fixture is valid for negotiation tests). This is a TCK-correctness decision, not a fixture problem — route it to whoever owns `ACP-INIT-003`.
2. **The cancel tier is only exercised with an agent-specific prompt.** `--cancel-prompt` exists precisely for this, and `wait_for_cancel` is the one string that makes `testy` hang deterministically. Cross-check CI must pass it, and the report should record *which* prompt was used, because "2 SKIPPED" and "2 PASS" are the same agent.
3. **`echo_agent` can never exercise cancellation.** It is a valid fixture for the other 13 mandatory requirements and a useful independent check that the harness is not `testy`-shaped, but it cannot cross-check the cancel logic at all. If the TCK wants a second, non-Rust cancel fixture, it must write one (a ~30-line asyncio agent that sleeps until `session/cancel`).
4. **Neither fixture stresses the harness's own robustness**: both are fast, small-payload, well-behaved, and never write non-JSON to stdout. The `max_line_bytes` / stderr-capture hardening currently in flight in `src/tck/harness/` is not exercised by either — `testy`'s largest single line in the `full` scenario is a few hundred bytes. Oversize-line and dirty-stdout coverage still needs TCK-owned fixtures.
5. **`testy` is a strong *negative* fixture for future capability-conditional tiers**, and that is arguably its highest value beyond the happy path: it advertises `loadSession: true` and replays nothing (would FAIL the planned cap:`loadSession` replay assertion, `acp-v1-session-capabilities.md` line 349/386 — confirmed empirically here); it rejects `session/list` with omitted `params` (line 407/430); it accepts a relative `cwd`; and it calls `fs/*`/`terminal/*` against a client that advertised nothing. Every one of those is a legal-or-undefined choice per that report, so they belong in ADVISORY/INFORMATIONAL tiers — but they make `testy` an excellent tripwire for accidentally over-strict tests.
6. **What the cross-check actually proves.** Both agents are independent implementations of the *same* reference lineage, and both share the two known weaknesses (version echo, missing `agentInfo`). A PASS from both therefore validates the TCK's *plumbing* (framing, id correlation, ordering, timeouts, schema wiring) and rules out gross over-strictness — it does **not** validate that the TCK's assertions match the spec. For that, the deliberately non-conforming fixtures (`reference-sdks-as-harness.md:195`) remain the only instrument.

---

## Discrepancies

1. **Requirement text vs. test strength for `ACP-INIT-003`** (this repo): `requirements.py:152-162` demands "its latest supported version"; `test_initialize.py:48-61` asserts only success + integer. Both independent agents exploit the gap. Highest-value finding of this report.
2. **`testy` advertises `loadSession: true` but performs no replay** ([rust] `testy.rs:395` vs `:1887-1899`) — non-conforming against `session-setup.mdx:134` for a non-empty session. Confirmed empirically (a session with a completed prompt turn replayed nothing). Already recorded as `acp-v1-session-capabilities.md` Discrepancy 7; this report adds the measurement.
3. **`echo_agent` answers capability-gated methods it does not advertise**: `session/load` → `{}` and `session/list` → **`result: null`** with no `agentCapabilities` at all (measured). `result: null` is not valid per `ListSessionsResponse`. Harmless for the TCK (which gates on capabilities) but disqualifies `echo_agent` from any capability-conditional tier.
4. **Released vs. HEAD Python SDK disagree on baseline prompt handling**: `0.12.1` (the PyPI *stable* that PEP 723 resolves) rejects `{"type":"text","text":"…"}` with `-32602`; `1.0.0rc1`/`main` accepts it. The same source file is conformant or not depending purely on the resolved dependency — a trap for any "just `uv run` the example" instruction, including the one in `reference-sdks-as-harness.md:133`.
5. **Default `testy` build emits a non-v1 field** (`mcpCapabilities.acp`, from the `unstable` default feature). Not a conformance failure against the vendored schema (nothing is `additionalProperties: false`), but it means the *default* `cargo build` of `testy` is not a strict-v1 agent. `--no-default-features` is the right fixture build; `md/testy.md:23-27` already says so, `reference-sdks-as-harness.md:160` already recommended it, and this report supplies the observable delta.
6. **`reference-sdks-as-harness.md:158` estimated "on the order of minutes" for the `testy` build.** Measured: 17.1 s cold for `--no-default-features` on 16 cores with a warm registry. Superseded.

---

## Open questions

- **Should `ACP-INIT-003`'s test be strengthened** (§Testability 1)? If yes, both cross-check fixtures move to "1 mandatory FAIL expected", and the CI expectation file must encode that as the *correct* result — which is a slightly awkward thing for a cross-check job to assert. Owner: whoever owns the initialize requirements.
- **Does the project want the `0.12.1` echo agent as a permanent negative fixture** (a genuinely non-conforming, third-party-shaped agent for free), or is depending on a known-broken published version too fragile?
- **Vendoring mechanism for the rust-sdk**: submodule vs. `actions/checkout` with a pinned SHA vs. a committed `.fixtures/rust-sdk.sha` file. Affects developer ergonomics (`just cross-check` locally) more than CI.
- **Whether the cross-check should also run `testy --features unstable_protocol_v2`** to confirm the TCK's `protocolVersion: 1` request lands on the v1 branch of a dual-version agent (`AgentProtocolRouter`, [rust] `src/bin/testy.rs:10-14`). Cheap, and the only upstream dual-version agent available. Out of scope here.
- **A second cancel-capable fixture** in a non-Rust language (§Testability 3) — worth ~30 lines, but it would be TCK-authored and therefore not an *independent* implementation, which weakens the cross-check argument. Design call.
