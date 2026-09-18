# Should the ACP TCK build its client harness on the official Python SDK or on a hand-rolled JSON-RPC/stdio client — and which agent fixtures can it reuse?

**Sources checked:**
- `agentclientprotocol/python-sdk` @ `c1004f8c3eafc647b5f4cd51506c5c8a2d9ae347` (2026-09-11, `main`, also tagged `1.0.0rc1`) — local clone `/Users/eugene/Documents/JetBrains/projects/acp-python-sdk`, `git pull --ff-only` → "Already up to date".
- `agentclientprotocol/rust-sdk` @ `b28b8ad188d60f2833e6930ef994bcc35f3bcce5` (2026-09-18, `main`) — local clone `/Users/eugene/Documents/JetBrains/projects/acp-rust-sdk`, `git pull --ff-only` → "Already up to date".
- PyPI metadata for `agent-client-protocol` (live query, 2026-09-18).
- **Not** consulted: `check-specification`, `check-a2a-tck`. This question is about tooling, not protocol semantics; nothing here should be read as a normative protocol claim.

**Confidence:** high for everything read directly out of the two checkouts (API surface, examples, test utilities, Testy's documented coverage). Medium for the operational claims I could not execute here (Testy build time, `uv run` startup cost) — these are labelled as estimates, not measurements.

## Answer

Use **both layers, with the raw layer as the primary harness**. The Python SDK's typed client (`acp.connect_to_agent` / `ClientSideConnection`) is a perfectly good driver for happy-path and capability-conditional tests, and it is cheap to adopt — but it structurally cannot produce most of the malformed traffic a TCK must send (it hard-codes `jsonrpc`/integer ids, always emits `params`, serializes through Pydantic with `exclude_defaults=True`), and it silently *swallows* malformed agent output instead of surfacing it. Crucially the SDK's own transport seam is reusable independently of the typed layer: `acp.spawn_stdio_transport` (process spawn + NDJSON byte streams) and `acp.spawn_stdio_connection` / `acp.connection.Connection` (untyped JSON-RPC over those streams) are public, so the TCK does **not** need to hand-roll subprocess management or framing — only a thin "write exactly these bytes, read exactly those bytes" writer for the edge-case tier. For fixtures: **reuse the Rust SDK's `testy` binary** as the known-conforming agent (deterministic, no network, documented full v1 coverage including all agent→client callbacks and a `wait_for_cancel` scenario), **reuse `examples/echo_agent.py`** from the Python SDK as a cheap smoke-level conforming agent, and **write our own** deliberately non-conforming agents in pure Python — nothing upstream ships any, and they must emit raw bytes, which no SDK will let you do.

## Requirements

Tiering here is about *TCK engineering constraints*, not protocol MUSTs — protocol tiering is another researcher's scope.

| # | Requirement on the harness | Tier | Evidence |
|---|---|---|---|
| 1 | Must be able to emit bytes that are not valid JSON | MUST (harness) | SDK cannot: `Connection.send_request` builds a `dict` and hands it to `Transport.send` (python-sdk `src/acp/connection.py:117-119`) |
| 2 | Must be able to emit JSON-RPC envelopes with wrong/missing `jsonrpc`, string ids, duplicate ids, missing `params` | MUST (harness) | Envelope is hard-coded: `{"jsonrpc": "2.0", "id": <int>, "method": ..., "params": ...}` (python-sdk `src/acp/connection.py:113-117`, `:134`) |
| 3 | Must be able to send arbitrary unknown method names | SHOULD (harness) | SDK only exposes `ext_method`, which force-prefixes `_` (python-sdk `src/acp/client/connection.py:339-343`) — but raw `Connection.send_request("anything", {...})` is public and takes any string |
| 4 | Must observe *all* raw bytes the agent writes, including non-JSON lines | MUST (harness) | `NdjsonTransport.receive` logs and **drops** unparseable lines and keeps looping (python-sdk `src/acp/_transport.py:81-86`); `Connection._process_message` silently ignores envelopes with neither `method` nor `id` (`src/acp/connection.py:152-165`) |
| 5 | Must control exactly which optional params appear on the wire | MUST (harness) | `serialize_params` uses `exclude_none=True, exclude_defaults=True` (python-sdk `src/acp/utils.py:54-56`), so default-valued fields are silently omitted |
| 6 | Needs subprocess spawn + graceful shutdown + NDJSON framing | reusable, don't rewrite | `spawn_stdio_transport` (python-sdk `src/acp/transports.py:47-118`) already does stdin-EOF → wait → terminate → kill escalation |
| 7 | Needs a full raw message transcript for assertions/reporting | reusable | `Connection.add_observer` / `StreamObserver` / `StreamEvent` delivers deep-copied raw dicts in both directions (python-sdk `src/acp/connection.py:27-38`, `:107-109`, `:166-183`) |
| 8 | Fixture agents must be deterministic and offline | MUST (fixtures) | see §3 |

## Details

### 1. Python SDK client API

**Package identity.** Distribution name `agent-client-protocol`, import package `acp` (python-sdk `pyproject.toml:2`, `src/acp/`). `requires-python = ">=3.10,<3.15"` (`pyproject.toml:11`), classifiers list 3.10–3.14 (`pyproject.toml:14-20`). A TCK on **Python ≥3.14 is inside the supported window** (3.14 is classified; the upper bound excludes 3.15 only).

**Versions.** Working-tree `version = "0.12.1"` (`pyproject.toml:3`), but HEAD of `main` is tagged `1.0.0rc1` and PyPI carries releases up to `1.0.0rc1` (pre-release) with `0.12.1` as latest stable. PyPI `requires_python` for the published dist is `>=3.10,<3.15`.

**Dependencies.** Runtime: `pydantic>=2.7`, `pydantic-core>=2.18.1` only (`pyproject.toml:23-26`). **No anyio, no trio** — the SDK is plain `asyncio` (`src/acp/connection.py:3`, `src/acp/transports.py:3`). Optional extras: `http` → `httpx[http2]`, `websockets`, `starlette`; `logfire` → `logfire`, `opentelemetry-sdk` (`pyproject.toml:54-57`). For a stdio TCK the dependency footprint is just Pydantic.

**Spawning an agent and connecting over stdio.** Three public entry points, in descending level of abstraction, all in `src/acp/stdio.py` and re-exported from `acp/__init__.py:78-79`:

| Function | Signature (abbrev.) | Yields | Citation |
|---|---|---|---|
| `spawn_agent_process` | `(to_client: Callable[[Agent], Client] \| Client, command, *args, env=, cwd=, transport_kwargs=, **connection_kwargs)` async CM | `(ClientSideConnection, asyncio.subprocess.Process)` | `src/acp/stdio.py:161-183` |
| `spawn_stdio_connection` | `(handler: MethodHandler, command, *args, env=, cwd=, observers=, **transport_kwargs)` async CM | `(Connection, Process)` — **untyped** | `src/acp/stdio.py:142-158` |
| `spawn_stdio_transport` | `(command, *args, env=, cwd=, stderr=PIPE, limit=, shutdown_timeout=2.0)` async CM | `(StreamReader, StreamWriter, Process)` — **raw bytes** | `src/acp/transports.py:47-118` |

`connect_to_agent(client, writer, reader)` (`src/acp/core.py:79-111`) wraps an already-spawned process's pipes; `ClientSideConnection` is the class behind it (`src/acp/client/connection.py:109-141`) and is nominally deprecated as a direct import from the `acp` top level (`src/acp/__init__.py:87-91`) though `acp.core.ClientSideConnection` is fine. Env handling defaults to a *trimmed* environment (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER` on POSIX) unless you pass `env=` (`src/acp/transports.py:13-44`, `:62-64`) — relevant for a TCK that wants a hermetic agent environment, and a nice thing to copy.

**Client-side method implementation.** You pass an object satisfying the `Client` Protocol (`src/acp/interfaces.py:85-160`): `request_permission`, `session_update`, `write_text_file`, `read_text_file`, `create_terminal`, `terminal_output`, `release_terminal`, `wait_for_terminal_exit`, `kill_terminal`, `create_elicitation`, `complete_elicitation`, `ext_method`, `ext_notification`. It is a `typing.Protocol` — structural, no base class required. `build_client_router` wires methods to wire names (`src/acp/client/router.py:92-163`). Semantics worth knowing:
- Terminal methods are registered `optional=True` with a `default_result`, so a client that omits them answers `null`/`{}` rather than `-32601` (`src/acp/client/router.py:103-144`, `src/acp/router.py:61-66`). **A TCK that wants to test "agent calls terminal/* against a client that did not advertise the capability" must not rely on this default** — it must supply a handler that raises `RequestError.method_not_found`, as `examples/client.py:71-97` does.
- `elicitation/*` is gated: without `use_unstable_protocol=True` the route warns and raises `-32601` (`src/acp/router.py:67-72`, `src/acp/client/router.py:146-161`).
- Unknown inbound methods → `RequestError.method_not_found` → `-32601` (`src/acp/router.py:180-182`); `_`-prefixed → extension handler (`src/acp/router.py:174-178`).

**Receiving `session/update`.** It is a notification routed to `Client.session_update(session_id=..., update=..., **meta)` (`src/acp/client/router.py:163`). There is a non-obvious behaviour a TCK must know: `ClientSideConnection` wraps the client in `_SessionUpdateTracker` (`src/acp/client/connection.py:59-107`) and `prompt()` **awaits all in-flight `session/update` handlers before returning**, on both the success and the exception path (`src/acp/client/connection.py:265-276`). That removes a race the TCK would otherwise have to handle itself, and is worth imitating in a raw harness.

**Sending `session/cancel`.** `await conn.cancel(session_id=...)` → `notify_model(conn, "session/cancel", CancelNotification(...))` (`src/acp/client/connection.py:331-337`, method name from `src/acp/meta.py:14`).

**Agent errors and connection close.**
- An error response becomes `RequestError(code, message, data)` raised from the awaiting call (`src/acp/connection.py:246-251`, `src/acp/exceptions.py:8-46`). Codes are exposed as constructors: `-32700/-32600/-32601/-32602/-32603/-32000 auth_required/-32002 resource_not_found`.
- A *malformed* response (right shape at JSON-RPC level, wrong shape at ACP level) raises `pydantic.ValidationError` from `request_model` (`src/acp/utils.py:90-98`) — the TCK gets an exception, not the offending payload, unless it also registered a `StreamObserver`.
- EOF from the agent ends the receive loop and rejects every pending request with `ConnectionError("Connection closed")` (`src/acp/connection.py:138-151`, `:261-272`); subsequent sends fail fast via `_raise_if_unavailable` (`:274-276`). Covered by tests at `tests/test_rpc.py:420-448`.
- A receive timeout (`receive_timeout=` kwarg) converts into `RequestError.internal_error({"details": "Agent timeout"})` (`src/acp/connection.py:148-149`) — a slightly odd conflation a TCK should not depend on.
- `Connection.close()` is idempotent, rejects pending requests, closes the transport, shuts down the task supervisor (`src/acp/connection.py:82-91`).

**Stability.** Mixed. The v1 surface is explicitly kept back-compatible: `acp.core` is a compatibility re-export shim (`src/acp/core.py:1-6`), `@compatible_class` keeps camelCase/params-object call styles alive with `DeprecationWarning`s (`src/acp/utils.py:244-268`, `src/acp/router.py:23-48`), and `ClientSideConnection`/`AgentSideConnection` are soft-deprecated in favour of `connect_to_agent`/`run_agent` (`src/acp/__init__.py:81-92`). So: stable-ish but actively churning naming, and the project is at `1.0.0rc1`, i.e. pre-1.0 semantics until that ships. `Connection`, `spawn_stdio_transport`, `spawn_stdio_connection`, `StreamObserver` are all in `__all__` and thus public contract (`src/acp/connection.py:24`, `src/acp/transports.py:11`, `src/acp/stdio.py:21-26`, `src/acp/__init__.py:169-176`).

**Protocol version targeted.** The stable surface is **v1**: `PROTOCOL_VERSION = 1`, generated from `refs/tags/schema-v1.21.0` (`src/acp/meta.py:2`, `:50`; `schema/VERSION`). v2 exists but is **fully segregated** under `acp.experimental.v2` with its own generated schema (`src/acp/experimental/v2/schema.py`, 5978 lines), its own method table and `PROTOCOL_VERSION = 2` generated from `refs/tags/schema-v2.0.0-alpha.3` (`src/acp/experimental/v2/meta.py:2`, `:41`; `schema/v2/VERSION`), and its own connection/router (`src/acp/experimental/v2/_connection.py`, `_router.py`).

**Impact on a v1-only TCK: essentially zero, with three caveats.**
1. Import hygiene is enough: `import acp` gives you v1 only. Nothing in the stable path references v2. The docs state the runtimes are strict and non-translating: "v1 messages are not accepted by a v2 connection, and v2 messages are not translated into v1 calls" (`docs/experimental-v2.md`, "Agents that serve both versions" section).
2. The v1 surface the SDK exposes is **schema v1.21.0**, which is much larger than an early-v1 baseline: `session/fork`, `session/resume`, `session/close`, `session/list`, `session/delete`, `providers/*`, `nes/*`, `document/did*` are all in `AGENT_METHODS` (`src/acp/meta.py:3-32`). A v1 TCK must decide per-method which of these are capability-conditional rather than baseline — do not infer "v1 requires this" from the SDK's method table.
3. Dual-version agents under test may route on the `initialize` protocol version (`AgentProtocolRouter`, `src/acp/experimental/negotiation.py`, documented in `docs/experimental-v2.md`). A v1 TCK sending `protocolVersion: 1` will land on the agent's v1 branch, which is what we want — but the TCK should assert the *response* version rather than assume. Note also that v2's `CLIENT_METHODS` **drops `fs/*` and `terminal/*` entirely** (`src/acp/experimental/v2/meta.py:31-39`) versus v1 (`src/acp/meta.py:33-48`); if the TCK ever grows a v2 tier, the client-side fixture surface changes shape, not just names.

### 2. Suitability for a TCK: what the typed layer can and cannot do

The failure modes are not "Pydantic is annoying", they are structural. Concretely:

| Edge case a TCK must produce | Typed `ClientSideConnection`? | Raw `Connection`? | Raw writer needed? |
|---|---|---|---|
| Unknown method name (`foo/bar`) | No — only `_`-prefixed via `ext_method` (`src/acp/client/connection.py:339-343`) | **Yes** — `send_request("foo/bar", {...})` (`src/acp/connection.py:111`) | no |
| Wrong param types (`cwd: 42`) | No — Pydantic validates at model construction | **Yes** — params are `JsonValue = Any` (`src/acp/connection.py:20`, `:117`) | no |
| Missing required params | No — model construction fails locally | **Yes** | no |
| Request before `initialize` | **Yes** (nothing enforces ordering client-side) | Yes | no |
| Unsupported protocol version (`protocolVersion: 999`) | **Yes** — it is just an `int` (`src/acp/client/connection.py:142-160`) | Yes | no |
| `protocolVersion` of the wrong JSON type (`"v1"`, `null`) | No | **Yes** | no |
| Omitted-vs-present optional field control | No — `exclude_none=True, exclude_defaults=True` (`src/acp/utils.py:56`) | **Yes** — you pass the dict | no |
| Notification with no `params` key at all | No | No — `params` is always emitted (`src/acp/connection.py:134`) | **yes** |
| Missing/incorrect `"jsonrpc"` | No | No — hard-coded (`src/acp/connection.py:117`, `:134`) | **yes** |
| String or duplicate request `id` | No | No — monotonic int (`src/acp/connection.py:113-114`) | **yes** |
| Invalid JSON bytes, truncated line, no trailing newline, BOM, embedded newline | No | No — `json.dumps` of a dict, always newline-framed | **yes** |
| Batch array (`[{...},{...}]`) | No | No | **yes** |
| Observe agent's *non-JSON* output line | No — dropped silently (`src/acp/_transport.py:81-86`) | No — same transport | **yes** |
| Observe raw wire for a well-formed exchange | Yes, via `add_observer` (`src/acp/connection.py:107-109`) | Yes | no |

So there are exactly two capability cliffs: **envelope-level malformation** and **byte-level malformation / byte-level observation**. Both need a writer/reader the TCK owns.

**Can the transport layer be reused separately from the typed layer? Yes, cleanly, and this is the key finding.** The SDK deliberately factored a message-level seam: `Transport` Protocol with `send(dict)/receive()->dict|None/close()`, `NdjsonTransport` wrapping byte streams, and `memory_transport_pair()` for in-process pairs (`src/acp/_transport.py:27-148`). The layering is:

```
spawn_stdio_transport   → (StreamReader, StreamWriter, Process)   [bytes]      public
  NdjsonTransport       → dict in / dict out                      [messages]   private module, public __all__
    Connection          → JSON-RPC ids, futures, handler dispatch  [rpc]       public
      ClientSideConnection → Pydantic models, ACP method names     [typed]     public
```

A TCK can cut at any level. Note `_transport.py` is an underscore module — `NdjsonTransport` and `memory_transport_pair` are in its `__all__` but importing them is importing a private module; treat as semi-public and pin the SDK version if you rely on them.

**Recommendation (harness): two-tier, raw-first.**

- **Tier A — raw wire harness (TCK-owned, the backbone).** Own a small `WireClient` that:
  - spawns via `acp.spawn_stdio_transport(...)` (reuse #6 above — the terminate/kill escalation and trimmed env are not worth reimplementing) **or** via a plain `asyncio.create_subprocess_exec` if you want zero SDK dependency at this tier;
  - writes `bytes` you construct (including deliberately invalid bytes) directly to the `StreamWriter`;
  - reads lines from the `StreamReader` **without** discarding unparseable ones, recording every line verbatim into a transcript;
  - correlates ids itself and implements client-side handlers as plain `dict`→`dict` callables so it can answer `session/request_permission`, `fs/*`, `terminal/*` with responses that are themselves controllable (including deliberately wrong ones, for reciprocal tests).

  This is small — the SDK's entire untyped connection is 276 lines (`src/acp/connection.py`), and the TCK's version needs less (no telemetry, no legacy-handler resolution, no task supervisor).

- **Tier B — typed assertions on top.** Do **not** drive the SDK's `ClientSideConnection`. Instead, depend on `agent-client-protocol` only for its **generated Pydantic models** (`acp.schema`) and validate captured payloads with `Model.model_validate(raw_dict)`. You get schema conformance checking for free, with precise `ValidationError.errors()` for the report, and you keep full wire control. `acp.meta.AGENT_METHODS` / `CLIENT_METHODS` / `PROTOCOL_VERSION` (`src/acp/meta.py`) give you the method-name table without hand-copying strings.

  Caveat: `acp.schema` is generated from schema tag v1.21.0 (`src/acp/meta.py:2`) — the TCK's notion of "the v1 baseline" must come from the spec repo, not from whatever that generated file happens to contain. Use the models as a *convenience validator* and keep the authoritative assertions spec-derived.

- **Optional Tier C — SDK-driven happy path as a cross-check.** A handful of tests that drive a fixture agent through `acp.spawn_agent_process` prove the TCK's own raw client is not diverging from a real client's behaviour (e.g. that our framing is what a real client emits). Cheap insurance, ~1 test module.

**Concrete modules/classes to reuse:** `acp.transports.spawn_stdio_transport`, `acp.transports.default_environment`, `acp.schema.*` (models), `acp.meta.AGENT_METHODS/CLIENT_METHODS/PROTOCOL_VERSION`, `acp.exceptions.RequestError` (code constants). **Reuse as design patterns, not imports:** `Connection.add_observer`/`StreamEvent` (transcript recording, `src/acp/connection.py:27-38`), `_SessionUpdateTracker` (drain in-flight `session/update` before completing a prompt assertion, `src/acp/client/connection.py:59-107`), `spawn_stdio_transport`'s shutdown escalation (`src/acp/transports.py:96-118`), `NdjsonTransport._read_line`'s `LimitOverrunError` reassembly (`src/acp/_transport.py:91-104`). **Do not build on:** `ClientSideConnection`, `build_client_router`, `MessageRouter`.

### 3. Example / test agents shipped upstream

#### Python SDK (`examples/`, included in the sdist via `pyproject.toml:64`)

| File | What it is | Capabilities | Deterministic? | Network/LLM? | How to run |
|---|---|---|---|---|---|
| `examples/echo_agent.py:34-85` | `EchoAgent`: `initialize` echoes the client's `protocol_version` back verbatim, `new_session` returns `uuid4().hex`, `prompt` emits one `AgentMessageChunk` per input block then `stop_reason="end_turn"` | `AgentCapabilities` not advertised at all (bare `InitializeResponse(protocol_version=...)`, `:47`) | Mostly — but the session id is a random UUID (`:56`) and it injects `_meta` `{"echo": true}` (`:73-74`) | none | PEP 723 header declares `requires-python >=3.10,<3.15` + `agent-client-protocol` (`:1-6`), so **`uv run examples/echo_agent.py` works directly** |
| `examples/agent.py:33-133` | `ExampleAgent`: fuller surface — `initialize` (advertises `AgentCapabilities()` + `Implementation`), `authenticate`, `new_session` (counter ids: `"0"`, `"1"`, …, `:73-76`), `load_session`, `set_session_mode`, `prompt` (echoes "Client sent:" then each block), `cancel`, `ext_method`/`ext_notification` | `AgentCapabilities()` = all defaults; no fs/terminal usage, never calls back into the client except `session/update` | **Yes** — sequential session ids, fixed strings | none | `uv run python examples/agent.py` (no PEP 723 header; needs the SDK on the path) |
| `examples/duet.py:20-43` | Harness, not an agent: spawns `agent.py` via `spawn_agent_process` and drives it with `client.py`'s `ExampleClient` | — | — | none | `python examples/duet.py` |
| `examples/client.py:55-228` | `ExampleClient` — a *client*, useful as a template for the TCK's client-side handlers: every fs/terminal method raises `RequestError.method_not_found` (`:56-97`), elicitation declines (`:99-101`) | — | yes | none | `python examples/client.py <agent-cmd>` |
| `examples/gemini.py` (456 lines) | Real Gemini CLI integration | — | **No** | **Yes — real LLM** | opt-in only; tests gated behind `ACP_ENABLE_GEMINI_TESTS=1` (`AGENTS.md:36`, `tests/test_gemini_example.py`) |
| `examples/http_server.py`, `http_client.py`, `ws_client.py` | Remote-transport demos | — | — | localhost sockets | not relevant to a stdio TCK |

**Assessment as known-conforming fixtures:** `echo_agent.py` is the best Python candidate — one file, PEP 723-self-describing so `uv run` resolves its deps, sub-second startup, no network. Two caveats: (a) it echoes back *whatever* `protocolVersion` the client sends (`:47`), so it is **not** a valid fixture for negotiation tests — a TCK asserting "agent must clamp to a version it supports" would see this agent wrongly pass with `999`; (b) its random session id defeats golden-transcript comparison. `agent.py` is more deterministic and covers more methods but advertises no real capabilities and never exercises agent→client callbacks, so it cannot be a fixture for `fs/*`, `terminal/*`, or `session/request_permission` tests.

#### Rust SDK

| Path | What it is | Capabilities | Deterministic? | Network/LLM? | How to run |
|---|---|---|---|---|---|
| `src/agent-client-protocol-test/src/testy.rs` (2106 lines) + `src/bin/testy.rs` | **`testy`, "a deterministic ACP test agent with typed JSON prompt commands"** (`src/testy.rs:1-5`). Prompt text is either a plain scenario word or a JSON `TestyCommand` (`:57-91`). Scenarios: `session_updates`, `content`, `tool_calls`, `callbacks`, `elicitations`, `cancel_status`, `wait_for_cancel`, `full` (`:97-114`, aliases at `:130-142`) | `load_session`, prompt caps image/audio/embedded_context, MCP http, session list/delete/additional_directories/resume/close, auth logout (`:393-412`); auth method `testy-agent-auth` (`:414-419`) | **Yes, by design** | **None** | `cargo build -p agent-client-protocol-test --bin testy` → `target/debug/testy`, speaks stdio (`md/testy.md:10-12`, `:29-30`; binary decl `Cargo.toml:21-23`) |
| `src/agent-client-protocol-test/src/testy/v2.rs` (555 lines) | v2 variant, behind `unstable_protocol_v2`; the binary then routes on `initialize` (`src/bin/testy.rs:10-19`, `md/testy.md:14-21`) | v2 session baseline only (`md/testy.md:81-99`) | yes | none | `--features unstable_protocol_v2` |
| `src/agent-client-protocol/examples/simple_agent.rs` | ~20 lines: answers `initialize` and nothing else (`:1-21`) | none | yes | none | `cargo run --example simple_agent` |
| `src/agent-client-protocol/examples/simple_agent_v2.rs` | v2 counterpart, `required-features = ["unstable_protocol_v2"]` (`src/agent-client-protocol/Cargo.toml:17-20`) | v2 | yes | none | feature-gated |
| `src/agent-client-protocol-test/src/bin/mcp_echo_server.rs` (82 lines) | An **MCP** echo server, not an ACP agent — fixture for MCP-bridge tests | — | yes | none | `cargo build ... --bin mcp-echo-server` |
| `src/agent-client-protocol-test/examples/arrow_proxy.rs` + `src/arrow_proxy.rs:16-47` | Proxy that prefixes `>` on `session/update` agent-message chunks | — | yes | none | built by `just prep-tests` |
| `src/agent-client-protocol/examples/yolo_one_shot_client.rs`, `src/yopo/` | One-shot *clients* (`yopo` = "You Only Prompt Once", `src/yopo/Cargo.toml:9`) | — | — | — | `cargo run --example yolo_one_shot_client -- --command "python my_agent.py" "What is 2+2?"` (`examples/yolo_one_shot_client.rs:9-12`) |

**`testy` assessment — this is the fixture to reuse.** Documented v1 coverage (`md/testy.md:59-77`) is exactly the TCK's target surface: every stable client→agent v1 request/notification (`initialize`, `authenticate`, `logout`, `session/new|load|list|delete|resume|close|set_mode|set_config_option|prompt|cancel`), and the `full`/`callbacks` scenarios drive **every stable agent→client callback**: `session/request_permission`, `fs/write_text_file`, `fs/read_text_file`, `terminal/create|output|wait_for_exit|kill|release`, plus elicitation form/URL × session/request scope × accept/decline/cancel. `wait_for_cancel` gives a deterministic hook for cancellation tests. It is capability-aware: if the client does not advertise form elicitation it returns "a deterministic invalid-params prompt error" instead of sending the request (`md/testy.md:72-77`) — i.e. it is already written to be driven by *varying* client capabilities, which is precisely what a TCK does.

Practical caveats before adopting it:
- **`publish = false`** (`src/agent-client-protocol-test/Cargo.toml:10`) — not on crates.io. The TCK must vendor the rust-sdk checkout (git submodule or pinned clone) and build it, or ship a prebuilt binary. This is the main cost.
- **Startup cost**: runtime startup is negligible (a Rust binary); the *build* is the cost — a cold `cargo build` of the workspace with `--all-features` is on the order of minutes (estimate — not measured here). Mitigate by building once in CI and caching `target/`, and by pointing tests at the binary path rather than `cargo run`, which is exactly what the SDK itself does (`src/test_binaries.rs:1-7`, `:59-63`).
- **It is not a strict conformance oracle.** `handle_initialize` responds with `InitializeResponse::new(request.protocol_version)` — it echoes the client's version unchanged (`src/testy.rs:421-435`), same weakness as the Python echo agent. Do not use it to validate negotiation-clamping tests.
- Default build enables the `unstable` feature (`Cargo.toml:13-14`), which pulls in unstable v1 surfaces. For a strict-v1 fixture use `--no-default-features` (`md/testy.md:23-27`).

### 4. How the reference SDKs test themselves

**Python.** Two distinct patterns, both worth copying:

1. **Real socket pair, not in-memory.** `tests/conftest.py:64-128` defines `_Server`: `asyncio.start_server` on `127.0.0.1:0` plus `asyncio.open_connection`, exposing `server_reader/server_writer/client_reader/client_writer`. The `connect` fixture (`tests/conftest.py:348-369`) can start **either side independently** (`connect_agent=True, connect_client=False`). That asymmetry is the whole trick: with the client side *not* constructed, the test owns `client_writer` and can inject arbitrary raw bytes and read raw response lines. This is exactly the TCK's edge-case pattern, already proven upstream:
   - unknown method → `-32601`: `tests/test_rpc.py:513-524`
   - missing required param → `-32602`: `tests/test_rpc.py:479-494`
   - legacy string `protocolVersion` accepted: `tests/test_rpc.py:497-510`
   - envelopes with neither `id` nor `method`, and `{"foo":"bar"}` → no response at all: `tests/test_rpc.py:675-691`
   - blank / `\r\n` / whitespace lines skipped: `tests/test_rpc.py:694-705`
   - ordering: notification then response on one write → response must not overtake: `tests/test_rpc.py:146-190`
   - EOF rejects pending requests / fails new ones fast: `tests/test_rpc.py:420-448`
2. **In-memory transport pair** for in-process agent↔client: `memory_transport_pair()` (`src/acp/_transport.py:138-148`), used by `tests/test_protocol_negotiation.py:8` and `tests/test_connection_recovery.py`. `tests/test_connection_recovery.py:17-30` also shows driving a bare `Connection(handler, writer, reader, listening=False)` and feeding a `StreamReader` directly with `feed_data`/`feed_eof` — the cheapest possible harness for framing tests (oversized frames, `LimitOverrunError` recovery).
3. **Subprocess round-trip**: `tests/test_rpc.py:890` `test_spawn_agent_process_roundtrip` exercises the real spawn path against a temp-file agent.
4. **Golden files**: `tests/golden/*.json` (≈40 files) + `tests/test_golden.py` pin the exact JSON for each request/response/update shape. The TCK can read these directly as **ready-made valid-payload fixtures** — e.g. `tests/golden/initialize_request.json`, `request_permission_request.json`, `session_update_tool_call.json`, `cancel_notification.json`. They are v1.21.0-generated, so check each against the spec before treating it as normative, but as *inputs to feed an agent* they are immediately useful.

**Can the TCK import these?** No — `tests/` is not an installable package (only `src/acp` is; `tests/` is merely included in the sdist per `pyproject.toml:64`). `tests/conftest.py`'s `TestClient` (`:131-246`, an in-memory fake client with a `files` dict, queued permission outcomes, and a `notifications` list) and `TestAgent` (`:248-336`, fixed `session_id="test-session-123"`) are excellent **templates to imitate**, and `TestAgent`'s fixed session id is exactly the determinism property `echo_agent.py` lacks.

**Rust.** In-process pairs over `tokio::io::duplex`, compat-wrapped into futures `AsyncRead`/`AsyncWrite`: `setup_test_streams()` at `src/agent-client-protocol/tests/jsonrpc_hello.rs:30-47`. Notable is the separation of concerns in the test suite itself — a **TCK-shaped taxonomy worth copying wholesale** (all under `src/agent-client-protocol/tests/`): `jsonrpc_hello`, `jsonrpc_advanced`, `jsonrpc_batch`, `jsonrpc_connection_builder`, `jsonrpc_deep_chain_stack`, `jsonrpc_edge_cases`, `jsonrpc_error_handling`, `jsonrpc_request_cancellation`, `jsonrpc_transport_close`, `jsonrpc_unhandled_messages`, then protocol-level `session_ordering`, `session_restore`, `meta_propagation`, `schema_*`. `jsonrpc_edge_cases.rs:17-62` shows the malformed-envelope cases the Rust SDK considers must-reject: scalar `params`, conflicting envelope fields.

### 5. Existing Rust tooling that overlaps a TCK

Nothing in either SDK is a conformance suite — `grep -rni "conformance|compliance|tck"` over `md/` and the crate READMEs returns **zero hits**. But four pieces overlap meaningfully:

1. **`testy`** — a ready-made deterministic agent-under-test/fixture (§3). This is the biggest "don't duplicate" item: writing our own full-surface conforming agent would duplicate 2100 lines of already-maintained, upstream-tracked behaviour.
2. **`agent-client-protocol-conductor`** (`src/agent-client-protocol-conductor/README.md:1-30`) — spawns a chain `Editor ← stdio → Conductor → Proxy… → Agent` and presents as a single agent. A TCK could use it as a **message-interception point** to observe or mutate traffic between a real client and a real agent — i.e. the "wire tap" a TCK otherwise builds itself. Its `--trace ./trace.jsons` flag writes one JSON event per line, flushed (`md/trace-viewer.md:10-38`), with exactly three event variants (request / response / notification).
3. **`agent-client-protocol-trace-viewer`** (`md/trace-viewer.md`) — renders those traces as an interactive sequence diagram. Directly comparable to what a TCK's failure report wants to show. Either reuse the `.jsons` event format so our transcripts open in their viewer, or at minimum copy the format.
4. **`agent-client-protocol-polyfill`** (`src/agent-client-protocol-polyfill/Cargo.toml:9`) — "polyfill proxies for backward compatibility"; relevant only if the TCK ever wants to test old agents through a shim. Also `arrow_proxy` as a trivial known proxy fixture.

No upstream tool sends malformed traffic or asserts conformance. That is genuinely unoccupied ground.

## Testability notes

- **Non-conforming fixtures must be hand-written, and they must be raw-byte agents.** Neither SDK ships any, and neither SDK *can* produce most non-conformances (the Rust `Responder`/`RawJsonRpcMessage` types reject scalar params at construction — `tests/jsonrpc_edge_cases.rs:17-48` — and the Python `Connection` hard-codes the envelope). Write them in pure Python as ~40-line scripts that read stdin lines and `sys.stdout.write(...)` exact strings. Suggested catalogue, each one file, each a single deliberate defect: responds with wrong `id`; never responds; responds twice to the same `id`; emits invalid JSON; omits `"jsonrpc"`; returns a result *and* an error; returns `stopReason` not in the enum; sends `session/update` for an unknown `sessionId`; sends `session/update` after `session/prompt` already returned; advertises no fs capability but calls `fs/read_text_file`; returns a `protocolVersion` higher than the client offered; exits mid-request; closes stdout without EOF-ing cleanly. These are trivially deterministic and cost ~1 ms to start.
- **Determinism checklist for reusing an upstream fixture:** fixed session ids (Python `echo_agent.py` fails this, `:56`; `conftest.py` `TestAgent` passes, `:275`), no timestamps in payloads, no random ordering of concurrent updates, no `_meta` injection (`echo_agent.py:73-74` injects `{"echo": true}`).
- **Both upstream "conforming" agents echo the client's `protocolVersion` unchanged** (`examples/echo_agent.py:47`, `src/agent-client-protocol-test/src/testy.rs:431`). Version-negotiation tests therefore need a TCK-written fixture with an explicit supported-version set. Whether echoing is itself conforming is a spec question and out of my scope — flag it to whoever owns the negotiation inventory.
- **Unobservable from the client side:** whether the agent's internal router rejected a message versus never received it (both look like "no response"); the difference between "dropped a malformed line" and "didn't read it"; and, critically, anything the agent writes to **stderr** — `spawn_stdio_transport` pipes stderr by default (`src/acp/transports.py:53`) and the TCK should capture and attach it to failure reports, since many real agents explain themselves there.
- **Timeouts are the TCK's own problem.** The SDK's `receive_timeout` collapses into a misleading `-32603 "Agent timeout"` (`src/acp/connection.py:148-149`); a raw harness should distinguish "no response within N s" from a protocol error in its report.

## Discrepancies

- **Python SDK version metadata is internally inconsistent.** `pyproject.toml:3` says `version = "0.12.1"` while HEAD of `main` is tagged `1.0.0rc1` and PyPI has a `1.0.0rc1` release; `git show 1.0.0rc1:pyproject.toml` still reads `0.12.1`. Pin by exact version string, not by "latest".
- **Python and Rust are on different protocol schema generations.** Python v1 bindings ← `schema-v1.21.0` (`src/acp/meta.py:2`), Python v2 ← `schema-v2.0.0-alpha.3` (`src/acp/experimental/v2/meta.py:2`); Rust pins `agent-client-protocol-schema = "=1.8.0"` (`Cargo.toml:38`) with core crate at `2.1.0`. Their notions of "v1" may not be byte-identical. Resolve against the spec repo before treating either as the baseline.
- **Client-side handling of unimplemented optional methods differs in kind.** Python's router answers `terminal/*` with a default result when no handler exists (`src/acp/client/router.py:103-144` + `src/acp/router.py:61-66`), whereas `examples/client.py:71-97` raises `-32601` for the same methods. Two upstream behaviours for the same situation; the TCK must decide which one its reference client exhibits and must not infer a protocol requirement from either.
- No spec-vs-implementation conflicts are reported here because I deliberately did not consult the spec repo for this tooling question.

## Open questions

- What does the spec actually require of an agent that receives an unsupported `protocolVersion` — clamp, error, or echo? Both reference fixtures echo. Route to the negotiation/spec-inventory researcher; it determines whether `testy` and `echo_agent.py` are safe fixtures for that tier.
- Which of schema v1.21.0's methods (`session/fork`, `session/resume`, `session/close`, `session/list`, `session/delete`, `providers/*`, `nes/*`, `document/did*`) are baseline-v1 versus capability-conditional? Owned by the spec-inventory researcher; determines the TCK's tier assignment and how much of `testy`'s surface is even in scope.
- Does the TCK want to be installable as a pure-PyPI tool (`uvx acp-tck ./my-agent`)? If yes, the Rust `testy` dependency is a CI-only, developer-only fixture and must not leak into the runtime dependency set — that constraint should be settled before the fixture layout is designed.
- Should the TCK's transcript format be `agent-client-protocol-conductor`'s `.jsons` event format so traces open in the upstream trace viewer? Cheap to decide now, expensive to retrofit.
- Is a v2 tier in scope at all? If so, note that v2 drops `fs/*` and `terminal/*` from the client method set (`src/acp/experimental/v2/meta.py:31-39`), so the client-fixture design changes shape and should be considered before the v1 harness hardens.
