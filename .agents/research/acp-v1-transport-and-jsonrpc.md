# What transport-level and JSON-RPC-level rules must an ACP v1 agent obey, as observable by a client TCK that launches it as a stdio subprocess?

**Sources checked:**

- Specification (source of truth): `agent-client-protocol` @ `6d08f412a7a1370d3cc9a124e3be3d6acf92641e` (2026-09-18, `chore: release (#2172)`; v1 schema crate version 1.23.0)
- Rust reference implementation: `rust-sdk` @ `b28b8ad188d60f2833e6930ef994bcc35f3bcce5` (2026-09-18, `docs(cookbook): demonstrate v2 session coordination (#364)`; `agent-client-protocol` crate 2.1.0)
- Python reference implementation: `python-sdk` @ `c1004f8c3eafc647b5f4cd51506c5c8a2d9ae347` (2026-09-11, `refactor: simplify web transports with Starlette (#142)`; `acp` 0.12.1)
- A2A TCK: **not consulted** for this question.

All `path:line` citations below are repository-relative to the repo named in the same row/sentence.

**Confidence:** medium-high — transport framing, error codes, and cancellation are directly and unambiguously specified; concurrency ordering, shutdown, timeouts, pre-`initialize` behavior and unknown-`sessionId` behavior are **not** specified for v1 and are only observable as reference-implementation choices, which differ between Rust and Python.

## Answer

For ACP **v1**, the normative transport contract is one short document: messages are UTF-8 JSON-RPC 2.0, newline-delimited, one message per line, with **no embedded newlines**; the client launches the agent as a subprocess; the agent **MUST NOT** write anything to `stdout` that is not a valid ACP message, and **MAY** write arbitrary UTF-8 logging to `stderr` (spec: `docs/protocol/v1/transports.mdx:6,21-27`). Error handling is plain JSON-RPC 2.0 plus two ACP codes — `-32000` auth required and `-32002` resource not found — and one borrowed LSP-style code, `-32800` request cancelled (`agent-client-protocol-schema/src/v1/error.rs:149-224`, rendered in `docs/protocol/v1/schema.mdx:3361-3400`). **Batch arrays are v2-only**: the v1 transports doc lists only "individual JSON-RPC requests, notifications, or responses", while v2 adds an explicit batch section — so a v1 TCK must not require batch support (and should not treat batch rejection as a failure). The spec says essentially nothing normative about request concurrency, response ordering, pre-`initialize` gating, unknown-`sessionId` error codes, process shutdown, or timeouts in v1; the two reference SDKs make *different* choices in several of these places (most sharply: malformed JSON gets a `-32700` reply from Rust and is **silently skipped** by Python), so those must be TCK-optional or informational at most. Concurrency is implicitly required in one direction only: the agent must be able to issue agent→client requests (`session/request_permission`, `fs/*`, `terminal/*`) *while* `session/prompt` is still unanswered (`docs/protocol/v1/prompt-turn.mdx:32-43,254`), which the cancellation doc shows as multiple concurrently outstanding requests (`docs/protocol/v1/cancellation.mdx:51-54`).

## Requirements

| # | Requirement | Tier | Citation (repo) |
|---|-------------|------|-----------------|
| T1 | Messages are JSON-RPC 2.0 and **MUST** be UTF-8 encoded | MUST | spec `docs/protocol/v1/transports.mdx:6` |
| T2 | Agents and clients **SHOULD** support stdio whenever possible | SHOULD | spec `docs/protocol/v1/transports.mdx:13` |
| T3 | The client launches the agent as a subprocess; agent reads JSON-RPC from `stdin`, writes to `stdout` | MUST (definition of the stdio transport) | spec `docs/protocol/v1/transports.mdx:21-22` |
| T4 | Messages are individual requests, notifications, or responses (**no batch arrays in v1**) | MUST (v1); batch is v2-only | spec `docs/protocol/v1/transports.mdx:23` vs. `docs/protocol/v2/transports.mdx:23-24,45-81` |
| T5 | Messages are delimited by `\n` and **MUST NOT** contain embedded newlines | MUST | spec `docs/protocol/v1/transports.mdx:24` |
| T6 | Agent **MAY** write UTF-8 strings to `stderr` for logging; clients **MAY** capture, forward, or ignore it | MAY | spec `docs/protocol/v1/transports.mdx:25` |
| T7 | Agent **MUST NOT** write anything to `stdout` that is not a valid ACP message | MUST | spec `docs/protocol/v1/transports.mdx:26` |
| T8 | Client **MUST NOT** write anything to the agent's `stdin` that is not a valid ACP message (TCK obligation, not agent obligation) | MUST (on the TCK) | spec `docs/protocol/v1/transports.mdx:27` |
| J1 | Successful responses include `result`; errors include an `error` object with `code` and `message` | MUST | spec `docs/protocol/v1/overview.mdx:219-223` |
| J2 | Notifications never receive a response, success or error | MUST | spec `docs/protocol/v1/overview.mdx:223`; `agent-client-protocol-schema/src/v1/error.rs:9` |
| J3 | Request `id` may be a string, a number, or `null`; the responder **MUST** echo the same value | MUST | spec `agent-client-protocol-schema/src/rpc.rs:12-39,245-289` |
| J4 | `jsonrpc` is required and must be exactly `"2.0"` on every message | MUST | spec `agent-client-protocol-schema/src/rpc.rs:118-137`; generated `schema/v1/schema.json` top-level (`"properties": {"jsonrpc": {"enum": ["2.0"]}}, "required": ["jsonrpc"]`) |
| J5 | `params` is optional and omitted when absent (`skip_serializing_none`) | MAY | spec `agent-client-protocol-schema/src/rpc.rs:49-57,110-116` |
| J6 | Unrecognized method name → respond `-32601 "Method not found"` | SHOULD (spec wording is "should") | spec `docs/protocol/v1/extensibility.mdx:80-92` |
| J7 | ACP object keys are `camelCase`; discriminator string values are `snake_case`; envelope fields follow JSON-RPC 2.0 | MUST | spec `docs/protocol/v1/overview.mdx:227` |
| J8 | All file paths in the protocol **MUST** be absolute; line numbers are 1-based | MUST | spec `docs/protocol/v1/overview.mdx:214-215`; `AGENTS.md:1` |
| J9 | Custom methods are prefixed with `_`; `$/`-prefixed protocol-level notifications **may be freely ignored** by the receiver | MAY | spec `docs/protocol/v1/extensibility.mdx:55-92`; `agent-client-protocol-schema/src/v1/protocol_level.rs:75-85` |
| E1 | Error codes: `-32700` parse, `-32600` invalid request, `-32601` method not found, `-32602` invalid params, `-32603` internal, `-32800` request cancelled, `-32000` auth required, `-32002` resource not found; any other integer is permitted (`Other`) | MUST (values) / MAY (use of `Other`) | spec `agent-client-protocol-schema/src/v1/error.rs:149-224`; docs `docs/protocol/v1/schema.mdx:3357-3400` |
| E2 | `error.data` is optional; `resource_not_found` carries `{"uri": …}` by convention | MAY / convention | spec `agent-client-protocol-schema/src/v1/error.rs:43-48,119-128` |
| E3 | `error.message` "should be limited to a concise single sentence" | SHOULD | spec `agent-client-protocol-schema/src/v1/error.rs:41-42`; `docs/protocol/v1/schema.mdx:3347-3350` |
| C1 | On `$/cancel_request` the receiver **MAY** cancel work, **MAY** flush pending notifications, and **MUST** answer the original request with either a valid (possibly partial) result or error `-32800` | MUST (conditional on having received the notification) | spec `docs/protocol/v1/cancellation.mdx:16-24`; `agent-client-protocol-schema/src/v1/protocol_level.rs:96-104` |
| C2 | On internal cancellation (no `$/cancel_request` received) the executing side **SHOULD** send the same `-32800` | SHOULD | spec `docs/protocol/v1/cancellation.mdx:28-38` |
| C3 | Support for `$/cancel_request` is optional; unsupported implementations simply run the request to completion | MAY | spec `docs/protocol/v1/cancellation.mdx:14`; rust-sdk `md/request-cancellation.md:45-52` |
| P1 | Agent **MUST** respond to `session/prompt` with a `stopReason`, and after `session/cancel` **MUST** respond with `cancelled` (not an error) | MUST | spec `docs/protocol/v1/prompt-turn.mdx:217,330-341` |
| P2 | Agent **MAY** send `session/update` after `session/cancel`, but **MUST** send them before the `session/prompt` response | MUST (ordering) | spec `docs/protocol/v1/prompt-turn.mdx:343` |
| P3 | Agent→client requests during an in-flight `session/prompt` are the normal case; multiple may be outstanding at once | implicit MAY | spec `docs/protocol/v1/prompt-turn.mdx:32-43,254`; `docs/protocol/v1/cancellation.mdx:50-54` |
| P4 | Clients **MUST** complete `initialize` and session setup before sending prompts; sessions may not be created before `initialize` | MUST (on the client) | spec `docs/protocol/v1/prompt-turn.mdx:8`; `docs/protocol/v1/initialization.mdx:24`; `docs/protocol/v1/session-setup.mdx:8` |
| P5 | Agent→client `fs/*`, `terminal/*`, `elicitation/create` are capability-conditional: the agent **MUST NOT** call them unless the client advertised the capability | capability:`fs.readTextFile` / `fs.writeTextFile` / `terminal` / `elicitation.*` | spec `docs/protocol/v1/file-system.mdx:10,28`; `docs/protocol/v1/initialization.mdx:130-163` |

Nothing in the v1 specification states a shutdown/exit method, a timeout, a maximum line length, a required response ordering, an error code for a pre-`initialize` request, or an error code for an unknown `sessionId`. See **Details §5–§7**.

## Details

### 1. Transport: launch and framing

**Normative text** is entirely in `docs/protocol/v1/transports.mdx` (spec repo; last touched `c1ae9fc9` 2026-06-01):

```
6:  ACP uses JSON-RPC to encode messages. JSON-RPC messages **MUST** be UTF-8 encoded.
21: - The client launches the agent as a subprocess.
22: - The agent reads JSON-RPC messages from its standard input (`stdin`) and sends messages to its standard output (`stdout`).
23: - Messages are individual JSON-RPC requests, notifications, or responses.
24: - Messages are delimited by newlines (`\n`), and **MUST NOT** contain embedded newlines.
25: - The agent **MAY** write UTF-8 strings to its standard error (`stderr`) for logging purposes. Clients **MAY** capture, forward, or ignore this logging.
26: - The agent **MUST NOT** write anything to its `stdout` that is not a valid ACP message.
27: - The client **MUST NOT** write anything to the agent's `stdin` that is not a valid ACP message.
```

The accompanying diagram ends with `Client->>Agent Process: Close stdin, terminate subprocess` (`docs/protocol/v1/transports.mdx:40`) — the only spec-level statement about connection teardown, and it is a diagram, not normative prose.

**The spec does not define the launch configuration** (command / args / env / cwd) as a wire or protocol artifact. The only related normative statements are:

- `session/new`'s `cwd` **MUST** be an absolute path and **MUST** be used for the session *regardless of where the agent subprocess was spawned* (spec `docs/protocol/v1/session-setup.mdx:359-364`). So process cwd and session cwd are explicitly decoupled; a TCK may launch the agent from any directory.
- Terminal authentication assumes the client has a "base launch configuration" for the agent program to which a method's `args` are appended and `env` applied, overriding same-named variables (spec `docs/protocol/v1/authentication.mdx:169-187`). This is the closest the spec comes to acknowledging a `{command, args, env}` launch model, and it is capability-conditional (`clientCapabilities.auth.terminal`, `docs/protocol/v1/initialization.mdx:118-124`).

**Rust SDK — agent side (writer/reader).** `Stdio` wraps `std::io::stdin()`/`stdout()` through `blocking::Unblock` and hands them to `ByteStreams` (rust-sdk `src/agent-client-protocol/src/stdio.rs:47-84`). Framing:

- read: `BufReader::new(incoming).lines()` — split on `\n` (rust-sdk `src/agent-client-protocol/src/jsonrpc.rs:6411`)
- write: `write_line` appends a single `b'\n'`, writes, then **flushes** (rust-sdk `src/agent-client-protocol/src/jsonrpc.rs:6422-6432`); flushing is regression-tested at `src/agent-client-protocol/src/jsonrpc.rs:7419-7425`
- the "no embedded newlines" rule is actively enforced even on the pathological relay path: `malformed_line_value` re-encodes any raw value containing `\r` or `\n` so the emitted line contains neither (rust-sdk `src/agent-client-protocol/src/jsonrpc/transport_actor.rs:192-202`), asserted by `multiline_malformed_frame_is_written_as_one_line_value` (`.../transport_actor.rs:440-463`) and `multiline_invalid_json_rpc_value_is_compacted_without_changing_value` (`.../transport_actor.rs:465-476`).

**Rust SDK — client side (subprocess launch).** `AcpAgent`/`AcpAgentConfig` is exactly the "launch an agent over stdio" helper a TCK needs (rust-sdk `src/agent-client-protocol/src/acp_agent.rs`):

- config is `{ command: PathBuf, args: Vec<String>, env: BTreeMap<String,String> }`, serialized `camelCase` with `deny_unknown_fields` — **no `cwd` field** (`.../acp_agent.rs:51-59`)
- `spawn_process` sets `stdin`/`stdout`/`stderr` all to `Stdio::piped()` (`.../acp_agent.rs:283-285`); `env` is *added to* the inherited environment (`std_cmd.envs(&self.config.env)`, `.../acp_agent.rs:263`), i.e. no environment scrubbing
- on Unix the child is made its own process-group leader (`process_group(0)`, `.../acp_agent.rs:267-282`) with an explicit rationale: agents behind `npx`/`uvx` wrappers "do not reliably exit on stdin EOF", so the guard SIGKILLs the whole group on drop (`.../acp_agent.rs:306-329`)
- stderr is drained concurrently and a bounded tail (`STDERR_CAPTURE_LIMIT = 64 KiB`, `.../acp_agent.rs:21`) is attached to the exit error message: `format!("Process exited with {status}: {stderr}")` (`.../acp_agent.rs:536-539`)
- `AcpAgent::from_args` parses leading `NAME=value` arguments as env vars, then command, then args (`.../acp_agent.rs:790-815`)

**Python SDK — client side (subprocess launch).** `spawn_stdio_transport(command, *args, env=None, cwd=None, stderr=PIPE, limit=None, shutdown_timeout=2.0)` (python-sdk `src/acp/transports.py:47-56`):

- **does** support `cwd` (passed to `create_subprocess_exec`, `src/acp/transports.py:74,84`)
- environment is **not inherited wholesale**: it starts from an MCP-style allow-list (`DEFAULT_INHERITED_ENV_VARS` = `HOME, LOGNAME, PATH, SHELL, TERM, USER` on POSIX; a Windows list otherwise) and the caller's `env` is merged on top (`src/acp/transports.py:13-44,62-64`). Function-style values beginning `()` are skipped (`src/acp/transports.py:40-42`).
- `stderr` defaults to `PIPE`
- `spawn_agent_process` / `spawn_client_process` / `spawn_stdio_connection` are the public wrappers (`src/acp/stdio.py:142-208`)

**Python SDK — agent side.** `run_agent()` builds asyncio stdio streams and calls `conn.listen()` → `Connection.main_loop()` (python-sdk `src/acp/core.py:39-76`; `src/acp/agent/connection.py:132-134`). Framing:

- read: `readuntil(b"\n")` with `LimitOverrunError` re-assembly so a message longer than the buffer limit is still delivered (python-sdk `src/acp/_transport.py:91-104`); default stdin buffer limit is **50 MiB** (`src/acp/core.py:33-36`, justified by multimodal payloads — note asyncio's default is 64 KiB)
- write: `json.dumps(payload, separators=(",", ":")) + "\n"`, encoded UTF-8, then `drain()` (python-sdk `src/acp/task/sender.py:28-29,50-51`). `json.dumps` defaults to `ensure_ascii=True`, so output is pure ASCII and can never contain a raw newline. Writes are serialized through a single queue/loop task (`src/acp/task/sender.py:43-58`), so the SDK never interleaves two partial lines.
- blank/whitespace-only lines are skipped (`src/acp/_transport.py:78-80`), regression-tested at `tests/test_rpc.py:695-712` (`test_blank_lines_skipped`, including `\r\n`)

Neither SDK writes anything but protocol lines to `stdout`; both route diagnostics to `stderr`/logging (Python uses `logging.exception`, e.g. `src/acp/connection.py:214-218`; Rust uses `tracing`).

### 2. JSON-RPC 2.0 as applied by ACP

**Envelope.** `JsonRpcMessage<M>` flattens a required `jsonrpc: "2.0"` over a `Request`/`Response`/`Notification` (spec `agent-client-protocol-schema/src/rpc.rs:118-137`). The generated v1 JSON Schema root is an `anyOf` over Agent/Client/ProtocolLevel messages, each an object with `"required": ["jsonrpc"]` and `jsonrpc` constrained to the enum `["2.0"]` (spec `schema/v1/schema.json`, top-level `anyOf`).

**Request ids.** `RequestId` is an untagged enum of `Null | Number(i64) | Str(String)` (spec `agent-client-protocol-schema/src/rpc.rs:31-39`), with round-trip tests for all three including negative numbers (`.../rpc.rs:244-289`). The doc comment carries the JSON-RPC guidance verbatim: `null` is discouraged, and fractional numbers SHOULD NOT be used (`.../rpc.rs:14-20`). Note `i64`, not arbitrary-precision: a TCK sending an id larger than `i64::MAX` would be outside what the reference schema models.

The Python SDK allocates its **outgoing** ids as integers starting at `0` and incrementing (`src/acp/connection.py:113-114`) and correlates responses through `dict[int, Future]` (`src/acp/connection.py:56`) — so a *Python-based* peer will only ever emit numeric ids, but it accepts whatever id key the peer used (`_handle_response`, `src/acp/connection.py:238-252`, keyed on the raw JSON value). Rust generates UUID-string ids in some paths (`uuid::Uuid` import in `src/agent-client-protocol/src/jsonrpc/incoming_actor.rs:8`; the `$/cancel_request` example in `md/request-cancellation.md:16-23` shows a UUID string `requestId`). **TCK consequence:** an agent must accept both numeric and string ids; testing string ids is fair game, testing `null` ids for *requests* is not (discouraged by JSON-RPC itself and used by both SDKs as the "unknown id" sentinel in error replies).

**Batch: v1 = not part of the transport.** The v1 transports doc lists only individual messages (`docs/protocol/v1/transports.mdx:23`). The v2 doc changes that line to "requests, notifications, responses, **or batch arrays**" and adds a full normative "JSON-RPC Batch Messages" section (`docs/protocol/v2/transports.mdx:23-24,45-81`) — **v2 material, excluded from v1 requirements**. The v1 *draft* transports doc is byte-identical to the stable v1 doc (verified by `diff`), so batch is not sneaking into v1 as a draft either. The v1 JSON Schema root contains no array alternative.

The spec's Rust **types** do define `JsonRpcBatch<M>` and re-export it from both `v1` and `v2` modules (spec `agent-client-protocol-schema/src/rpc.rs:170-232`; `agent-client-protocol-schema/src/v1/mod.rs:17`), rejecting empty batches at deserialization (`.../rpc.rs:221-232,292-298`). This is a *type availability* fact, not a v1 wire requirement — the generated v1 schema does not admit arrays. See **Discrepancies**.

**Response shape (`result` XOR `error`).** `Response` is an untagged two-variant enum: `{id, result}` or `{id, error}` (spec `agent-client-protocol-schema/src/rpc.rs:66-83`). Rust enforces the exclusivity strictly: a message with both `result` and `error`, or with `method` plus `result`, or a notification carrying `error`, fails to deserialize (rust-sdk `src/agent-client-protocol/tests/jsonrpc_edge_cases.rs:65-85`) and is classified `-32600` (rust-sdk `src/agent-client-protocol/src/jsonrpc/transport_actor.rs:366-386`). Rust also rejects **scalar** `params` (`params: 1`, `params: true`) at the envelope level (`.../jsonrpc_edge_cases.rs:17-48`), matching JSON-RPC's structured-params rule. Python is permissive: `_handle_response` prefers `result` if present, else `error`, else resolves with `None` (`src/acp/connection.py:243-252`).

**Error-reply behavior table (agent receiving bad input).** Rows marked *spec* are normative; rows marked *rust* / *python* are reference behavior only.

| Input | Spec | rust-sdk | python-sdk |
|---|---|---|---|
| Unparseable JSON on a line | not specified | `-32700 "Parse error"`, `id: null`, `data: {"line": "<raw>"}` — `src/agent-client-protocol/src/jsonrpc/transport_actor.rs:16-26` + `.../tests/jsonrpc_error_handling.rs:232-259` (exact expected JSON) | **silently skipped**, logged, loop continues — `src/acp/_transport.py:81-86`; asserted by `tests/test_rpc.py:676-693` |
| Valid JSON, invalid envelope (e.g. `17`, `{"jsonrpc":"2.0"}`, `{"foo":"bar"}`) | not specified | `-32600 "Invalid request"`, `id: null` — `.../transport_actor.rs:50-59,430-438` | **no response at all** — `src/acp/connection.py:152-164` only dispatches when `method` is present or (`id` present ⇒ treat as response); `tests/test_rpc.py:676-693` asserts silence |
| Empty batch `[]` | not specified in v1 (v2: `-32600`, `id: null`) | `-32600`, `id: null`, single object not array — `.../transport_actor.rs:29-32,410-418`; `.../tests/jsonrpc_batch.rs:1105-1140` | `message.get` on a `list` raises `AttributeError` out of `_process_message` → receive loop dies → `_disconnect()` and all pending requests fail (`src/acp/connection.py:152-164,254-256`). **Inference from code reading; no test covers it.** |
| Non-empty batch | not specified in v1 | processed; one consolidated response array with one entry per call, notifications produce none — `.../tests/jsonrpc_batch.rs:284-398,1338-1430` (the latter uses a real v1 `Agent`) | same `AttributeError` path as above (inference) |
| Unknown method (request) | `-32601 "Method not found"` (SHOULD) — `docs/protocol/v1/extensibility.mdx:80-92` | `-32601 "Method not found"`, `data` = the method name string — `src/agent-client-protocol/src/jsonrpc/incoming_actor.rs:616-621`; exact wire shape at `.../tests/jsonrpc_unhandled_messages.rs:229-252` | `-32601 "Method not found"`, `data` = `{"method": "<name>"}` — `src/acp/exceptions.py:24-26`; `src/acp/router.py:176-182`; `tests/test_rpc.py:514-526` |
| Unknown method (notification) | no response ever (J2) | logged, ignored — `.../incoming_actor.rs:614-617` (`"Ignoring unhandled notification"`); `.../tests/jsonrpc_unhandled_messages.rs:113` | raised then swallowed by `_run_notification`'s blanket `except Exception` — `src/acp/connection.py:226-236` |
| Known method, params fail validation | not specified (`-32602` is the obvious code) | `-32602 "Invalid params"` with `data` = serde error string (blanket `From<serde_json::Error>`) — `agent-client-protocol-schema/src/v1/error.rs:298-302`; asserted on the wire at `.../tests/jsonrpc_error_handling.rs:733-800` including "connection stays alive" | `-32602 "Invalid params"` with `data` = `{"errors": [...pydantic errors...]}` — `src/acp/connection.py:211-212`; `tests/test_rpc.py:480-495` |
| Handler raises an unexpected exception | not specified | propagated as the handler's own `Error`; `into_internal_error` yields `-32603` with `data` = the error string — `agent-client-protocol-schema/src/v1/error.rs:130-136` | `-32603 "Internal error"` with `data` = `{"details": str(exc)}` (or the parsed JSON if the message happens to be JSON) — `src/acp/connection.py:213-223` |
| Any request **before** `initialize` | **not specified for v1** | **no gating in v1.** `ProtocolMode::v1_agent()` uses `InitializationRole::Unchecked` → `ensure_initialized` always `Ok` (`src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:169-176,616-625`), and the whole `ProtocolCompat` is a no-op unless the `unstable_protocol_v2` feature is on (`.../protocol_compat.rs:1-98`). The `-32600 "Invalid request"` + `data: "ACP initialization must complete before \`{method}\` can be used"` reply, and the "may only be initialized once" reply, are **v2-only** (`.../protocol_compat.rs:594-625`, roles set at `.../protocol_compat.rs:193-205`). | no gating; routes are registered independently of lifecycle (`src/acp/agent/router.py`) |
| Request naming an unknown `sessionId` | **not specified for v1.** The only nearby statement: for `session/close`, "Agents MAY return an error if the session does not exist or is not currently active" (`docs/protocol/v1/session-setup.mdx:311`) | no framework-level handling; the only reference examples that do this are **v2** and use `-32602` invalid params with message `unknown session \`{id}\`` (`src/agent-client-protocol/examples/simple_agent_v2.rs:86,118,141,221`) | no framework-level handling |

Both SDKs keep the connection alive after every error above (Rust: explicit regression tests `test_invalid_params_keeps_connection_alive` `.../jsonrpc_error_handling.rs:634-708` and `test_notification_errors_are_ignored_and_connection_stays_alive` `.../jsonrpc_error_handling.rs:824-911`; Python: `tests/test_rpc.py:480-526` continue using the connection). That is the strongest *de facto* rule the TCK can lean on: **an error must not tear down the connection.**

### 3. ACP-specific error codes

Canonical list (spec `agent-client-protocol-schema/src/v1/error.rs:149-224`, docs-rendered at `docs/protocol/v1/schema.mdx:3357-3400`). `message` strings are the `strum` display names, which both `From<ErrorCode> for Error` (`.../error.rs:264-268`) and the Python constructors (`src/acp/exceptions.py:16-43`) use verbatim — so the message conventions coincide across both SDKs:

| Code | Canonical `message` | Meaning / when used | `data` convention |
|---|---|---|---|
| `-32700` | `Parse error` | invalid JSON received | rust: `{"line": "<raw line>"}` (`.../transport_actor.rs:23`) |
| `-32600` | `Invalid request` | JSON is valid but not a Request object; empty batch; conflicting envelope fields | rust v2 initialization gating adds a human-readable string (`.../protocol_compat.rs:598-625`) |
| `-32601` | `Method not found` | method does not exist or is not available; expected reply to unrecognized `_`-prefixed custom methods | rust: bare method-name string; python: `{"method": name}` |
| `-32602` | `Invalid params` | invalid method parameters; also the spec's chosen code when an agent requests an `elicitation/create` mode the client never advertised (`docs/protocol/v1/elicitation.mdx:166`) | rust: serde error string; python: `{"errors": [...]}` |
| `-32603` | `Internal error` | implementation-defined server error | rust: `err.to_string()`; python: `{"details": str(exc)}`; rust EOF case: `{"reason":"incoming_transport_closed","method":"…"}` |
| `-32800` | `Request cancelled` | request aborted by `$/cancel_request`, by internal cancellation, by resource constraints, or by shutdown | — |
| `-32000` | `Authentication required` | authentication must complete before this operation; expected on `session/new` and on authentication-gated requests, and possibly on existing sessions after `logout` | RFD example (proposal only) shows `{"reason": "auth_required"}` — `docs/rfds/next-edit-suggestions.mdx:558-574` |
| `-32002` | `Resource not found` | a resource such as a file was not found | `{"uri": "<uri>"}` — spec `agent-client-protocol-schema/src/v1/error.rs:119-128`; python `src/acp/exceptions.py:40-43` |
| any other `i32` | `Unknown error` | `ErrorCode::Other(i32)` — arbitrary codes are legal and must round-trip | — |

Notes for the TCK:

- `-32001` is **not** defined; the ACP custom range is documented as `-32000..-32099` (`agent-client-protocol-schema/src/v1/error.rs:141-142`).
- `-32800` sits outside that range (borrowed from LSP) and is grouped with the "standard" codes in the enum.
- The v1 docs page for errors is a stub — `docs/protocol/v1/error.mdx:6` is literally `_Documentation coming soon_` (as are `docs/protocol/v1/draft/error.mdx` and `docs/protocol/v2/error.mdx`). **The schema is the only authority for error codes.**
- `data` is optional and, on deserialization, is `DefaultOnError` — a malformed `data` becomes `None` rather than failing the whole error object (spec `agent-client-protocol-schema/src/v1/error.rs:45-48`). A TCK must therefore not assume `data` is absent just because a peer dropped it.
- Python's `RequestError.to_error_obj()` always emits the `data` key, so a Python agent's errors contain `"data": null` when there is no data (python-sdk `src/acp/exceptions.py:45-46`). A TCK must accept `data: null` as equivalent to absent.
- `auth_required` (`-32000`) is referenced by name (not code) throughout the v1 authentication docs: after successful `authenticate` the client should stop seeing it (`docs/protocol/v1/authentication.mdx:166-167`); after `logout`, existing sessions may start returning it (`docs/protocol/v1/authentication.mdx:218-226`). The only concrete `-32000` JSON example anywhere is in an **RFD** (proposal, not requirement): `docs/rfds/next-edit-suggestions.mdx:558-574`.

### 4. Concurrency

**Spec.** There is no normative statement in v1 about concurrent client→agent requests or response ordering. What exists:

- A connection "can support several concurrent sessions" (spec `docs/get-started/architecture.mdx:20`) — narrative, not normative.
- The prompt-turn diagram and text require the agent to issue agent→client requests (`session/request_permission`, and `fs`/`terminal` calls during tool execution) **while the `session/prompt` request is still unanswered** (spec `docs/protocol/v1/prompt-turn.mdx:32-43,233-235,254`). This is the one concurrency property that is effectively mandatory for any non-trivial agent.
- The cancellation example shows the agent with **two** agent→client requests outstanding simultaneously (`terminal/create` id=2 and `session/request_permission` id=3) plus the in-flight prompt id=1, then cascading `$/cancel_request` for both (spec `docs/protocol/v1/cancellation.mdx:50-64`). So multiple concurrently outstanding requests in the agent→client direction are explicitly sanctioned.
- Client obligations on cancel: the client **MUST** respond to all pending `session/request_permission` with the `cancelled` outcome, and **SHOULD** preemptively mark unfinished tool calls `cancelled` (spec `docs/protocol/v1/prompt-turn.mdx:326-328`); it **SHOULD** still accept tool-call updates arriving after it sent `session/cancel` (`:345`). These are TCK-client obligations, and also the behaviors a TCK must implement in its own fake client.
- After a turn completes "the Client may send another `session/prompt`" (spec `docs/protocol/v1/prompt-turn.mdx:349`) — suggestive of one prompt per session at a time, but **not** stated as a prohibition, and no error code is defined for a second concurrent prompt.

Since JSON-RPC 2.0 correlates strictly by `id`, out-of-order responses are inherently permitted; nothing in v1 restricts that.

**Rust SDK.** A single **dispatch loop** processes incoming messages one at a time and *waits for each handler to complete before reading the next message* (rust-sdk `src/agent-client-protocol/src/concepts/ordering.rs:7-39`). Consequences a TCK should know:

- A naively written Rust agent (handler bodies doing the work inline via `on_receive_request`) will answer requests **strictly in arrival order** and will not overlap them. The docs explicitly call out the resulting deadlock if a handler `block_task()`s on a nested request (`.../ordering.rs:41-58`).
- Concurrency is opt-in: `cx.spawn(...)` releases the loop (`.../ordering.rs:64-88`), and the session-start helpers are two-phase precisely so user code runs outside the ordering barrier (`.../ordering.rs:29-34`).
- So "agent responds out of order" is legal but **not** what the Rust reference does by default. A TCK must not require out-of-order responses, and must not require in-order ones either.
- Batch entries received in one array are answered in one consolidated array; responses may be withheld until every call in the batch has completed (`.../tests/jsonrpc_batch.rs:400-487`), and duplicate ids inside one batch get distinct response slots (`.../tests/jsonrpc_batch.rs:893-935`). **v2-relevant only.**

**Python SDK.** Every incoming request and notification is dispatched into its **own asyncio task** (`src/acp/connection.py:152-164`), so handlers genuinely overlap and responses are emitted **in completion order, not arrival order**. `test_concurrent_reads` fires five `fs/read_text_file` requests with `asyncio.gather` and asserts all resolve (`tests/test_rpc.py:405-417`). Outgoing writes are still serialized line-by-line through `MessageSender` (`src/acp/task/sender.py:43-58`), so lines never interleave.

**Cancellation of in-flight requests.**

- Rust implements `$/cancel_request` end-to-end: a `RequestCancellationRegistry` is threaded through dispatch (`src/agent-client-protocol/src/jsonrpc/incoming_actor.rs:651`), dropping an unconsumed `SentRequest` *sends* a cancel to the peer, and `detach()` opts out (rust-sdk `md/request-cancellation.md:53-58`). Unknown/completed request ids are silently ignored; malformed cancel params are logged and ignored with no reply (`md/request-cancellation.md:36-43`). Cancellation propagates **hop by hop** in proxy chains because ids are per-connection (`md/request-cancellation.md:60-79`).
- Python **does not implement** `$/cancel_request`. The method name is defined (`src/acp/meta.py:49`, `PROTOCOL_METHODS = {"cancel_request": "$/cancel_request"}`) but no route is registered, so it lands in `MessageRouter.__call__`'s unknown-method path (`src/acp/router.py:176-182`) whose `RequestError` is then swallowed because it arrived as a notification (`src/acp/connection.py:226-236`) — i.e. silently ignored, which is exactly what the spec permits for `$/` notifications (`docs/protocol/v1/extensibility.mdx` / `agent-client-protocol-schema/src/v1/protocol_level.rs:75-85`).
- **TCK consequence:** `$/cancel_request` support is MAY. A conforming agent may ignore it entirely. What *is* testable: after `session/cancel`, the agent must eventually answer the outstanding `session/prompt` with `stopReason: "cancelled"` (P1/P2 above).

### 5. Shutdown

**There is no shutdown or exit method in ACP v1.** The v1 agent method list (spec `docs/protocol/v1/overview.mdx:47-112`) and the v1 method-name table (`schema/v1/meta.json`) contain: `initialize`, `authenticate`, `session/new`, `session/load`, `session/set_mode`, `session/set_config_option`, `session/prompt`, `session/cancel`, `session/list`, `session/delete`, `session/resume`, `session/close`, `logout`, plus `$/cancel_request`. Nothing resembling `shutdown`/`exit`. `session/close` frees one session's resources (`docs/protocol/v1/session-setup.mdx:282-311`) and does not end the connection. `logout` ends the *authenticated state*, with no guarantee about running sessions (`docs/protocol/v1/authentication.mdx:216-226`).

The only spec statement about teardown is the diagram step `Client->>Agent Process: Close stdin, terminate subprocess` (`docs/protocol/v1/transports.mdx:40`). So: **close stdin, then kill if needed.**

**Rust SDK.** `connect_to` is reactive: it returns `Ok(())` when the incoming stream reaches clean EOF, *after* draining responses and notifications already accepted by the outgoing queue (rust-sdk `src/agent-client-protocol/src/concepts/connections.rs:62-68`). Therefore a Rust reference agent exits its `connect_to`/`main` on stdin EOF — tested by `connect_to_returns_cleanly_on_incoming_eof_with_spawned_work` and `connect_to_flushes_response_queued_before_incoming_eof` (`src/agent-client-protocol/tests/jsonrpc_transport_close.rs:281-310`). Every request still awaiting a response at EOF fails with `-32603 "Incoming transport closed"` and `data = {"reason":"incoming_transport_closed","method":"…"}` (rust-sdk `src/agent-client-protocol/src/jsonrpc.rs:3517-3541`; `src/agent-client-protocol/src/concepts/connections.rs:94-100`); `is_incoming_transport_closed()` is the public discriminator. Truncated input (EOF mid-line) is a clean shutdown, not an error (`.../tests/jsonrpc_error_handling.rs:269-290`).

On the client side, `AcpAgent` races the protocol future against child exit; after a clean protocol shutdown it allows the child a `SHUTDOWN_GRACE_PERIOD = 1 s` to exit and otherwise terminates it (`src/agent-client-protocol/src/acp_agent.rs:24,735-770`). On Unix, dropping the connection SIGKILLs the child's whole **process group** (`.../acp_agent.rs:306-329`), with the documented rationale that wrapper launchers (`npx`, `uvx`) orphan the real agent, which then "does not reliably exit on stdin EOF" (`.../acp_agent.rs:271-281`).

**Python SDK.** `spawn_stdio_transport`'s teardown is the canonical TCK shutdown ladder (python-sdk `src/acp/transports.py:96-118`): `stdin.write_eof()` → `drain` → `close` → `wait_closed` → `wait_for(process.wait(), 2.0)` → `terminate()` → `wait_for(..., 2.0)` → `kill()` → `wait()`. On the agent side, `run_agent` exits when `main_loop` returns on EOF (`src/acp/core.py:73-76`; EOF is `receive() is None` at `src/acp/connection.py:141-143`, `src/acp/_transport.py:76-77`), and pending outbound requests are failed with `ConnectionError("Connection closed")` (`src/acp/connection.py:261-272`), tested at `tests/test_rpc.py:420-446`. `test_spawn_agent_process_roundtrip` exits the `spawn_agent_process` context and asserts `process.returncode is not None` (`tests/test_rpc.py:889-914`) — i.e. the reference Python echo agent does exit within the 2 s grace after stdin close.

**What a TCK can reasonably assert:** that after closing the agent's stdin the process exits within a generous grace period (both SDKs use 1–2 s; a TCK should be far more lenient), and that `SIGKILL`-of-process-group is available as the fallback. It cannot assert a specific exit code — nothing in the spec or either SDK defines one. Nor can it assert that the agent stops writing to stdout the instant stdin closes: Rust deliberately **flushes already-queued responses after EOF** (`src/agent-client-protocol/tests/jsonrpc_transport_close.rs:302-364`), so late-but-valid stdout lines after stdin close are conforming.

### 6. Timing / timeouts

**The v1 specification states no timeouts at all** (no occurrence of "timeout" in `docs/protocol/v1/`). Implementation-side numbers, all reference behavior, never requirements:

| Value | Where | Meaning |
|---|---|---|
| 1 s `SHUTDOWN_GRACE_PERIOD` | rust-sdk `src/agent-client-protocol/src/acp_agent.rs:24` | grace after protocol shutdown before terminating the child; also caps a final write after stdout EOF (`.../acp_agent.rs:566-600,712-717`) and how long to wait for the stderr tail after exit (`.../acp_agent.rs:521-534`) |
| 2 s `shutdown_timeout` (×2 stages) | python-sdk `src/acp/transports.py:55,110-118` | stdin-close → terminate → kill ladder |
| `receive_timeout=None` (default) | python-sdk `src/acp/connection.py:52`, `src/acp/_transport.py:64-68,106-107` | **no** read timeout by default; if set, a read timeout surfaces as `-32603` with `{"details": "Agent timeout"}` (`src/acp/connection.py:148-149`) |
| 50 MiB stdin buffer | python-sdk `src/acp/core.py:33-36` | not a timeout, but a de-facto line-length budget; Python re-assembles beyond it anyway (`src/acp/_transport.py:96-101`) |
| 64 KiB stderr capture | rust-sdk `src/agent-client-protocol/src/acp_agent.rs:21` | bounded stderr tail retained for exit diagnostics |

There is no request-level timeout on either side. A TCK must therefore pick its own timeouts and treat them as harness policy, not conformance criteria — and must document them, because "agent took too long" is not an ACP violation.

## Testability notes

**Directly assertable from a client-side stdio TCK (hard, spec-backed):**

1. **T5/T7 — one message per line, nothing else on stdout.** Read the agent's stdout as raw bytes for a whole session, split on `\n`, and assert every non-empty line parses as JSON *and* as a JSON-RPC message with `jsonrpc == "2.0"`. Non-conforming agent: prints a banner, a progress bar, or pretty-printed multi-line JSON to stdout. This is the single highest-value transport test and it needs no protocol knowledge beyond framing.
2. **T1 — UTF-8.** Decode stdout strictly; assert no decode errors. Additionally provoke non-ASCII round-trips (prompt containing emoji / CJK / combining characters) and check the echoed content survives. Note both SDKs emit ASCII-escaped JSON by default, so a TCK must accept `\uXXXX` escapes as equivalent.
3. **J3 — id echo and id types.** Send `initialize` with (a) a numeric id, (b) a string id, (c) a large-but-`i64`-safe numeric id, and assert the response `id` is byte-equal-by-JSON-value. Non-conforming agent: coerces string ids to numbers, or reindexes ids.
4. **J2 — notifications get no response.** Send `session/cancel` (a defined v1 notification) and an unknown `_tck/ping` notification; assert **no** line with a matching `id` or any error appears. Note Python's agent swallows unknown notifications and Rust logs-and-ignores them, so silence is the expected behavior for both.
5. **J6 — unknown method ⇒ `-32601`.** Send `{"jsonrpc":"2.0","id":N,"method":"tck/does_not_exist","params":{}}`. Assert `error.code == -32601`. Tier this as SHOULD (the spec says "should"), and do **not** assert anything about `error.data`: Rust sends a bare string, Python sends `{"method": …}`.
6. **E1/E3 — error object shape.** Whenever an error comes back, assert `code` is an integer and `message` is a non-empty string; accept `data` absent **or** `null` (Python always emits the key). Do not assert exact message strings — but *do* note that both SDKs use the canonical strings from `ErrorCode`'s `strum` display, so a soft/informational check against `{"Parse error","Invalid request","Method not found","Invalid params","Internal error","Request cancelled","Authentication required","Resource not found"}` is a reasonable *warning*-level assertion.
7. **"Errors are not fatal."** After each negative test, send a valid `initialize`-or-later request on the same connection and assert it succeeds. This mirrors explicit regression tests in both SDKs and is the most useful robustness assertion available.
8. **T6 — stderr is free-form.** Capture it, never parse it, never fail on it. The only defensible assertion: stderr content must not be required for the session to work. Useful as *diagnostics attached to failures* (both SDKs do exactly this).
9. **P1/P2 — cancel ordering.** Start a prompt, send `session/cancel`, and assert: the `session/prompt` response eventually arrives, is a **success** with `stopReason: "cancelled"` (not an error), and every `session/update` for that session is observed *before* it. This is a real MUST with a clean observable.
10. **C1 — `$/cancel_request`.** Optional tier. Send it for an outstanding agent→client request id the agent issued to the TCK… wait, note the direction: `$/cancel_request` from the client can only target a *client→agent* request. So: send `session/prompt`, then `$/cancel_request` with that prompt's id, and accept **either** a normal/partial result **or** `-32800`. Failing to answer at all is the only violation, and only for agents that acknowledge cancellation support — which v1 gives no capability flag for, so this can only ever be a warning.
11. **Shutdown.** Close stdin and assert the process exits within a lenient window; escalate `SIGTERM` then `SIGKILL` (kill the process *group* on Unix — the Rust SDK's rationale about `npx`/`uvx` wrappers applies verbatim to a TCK). Report "did not exit on stdin close" as a warning, not a failure: no spec text requires it. Accept valid stdout lines emitted after stdin close.

**Assertable only as warnings / informational (no spec backing, SDKs disagree):**

- Malformed JSON ⇒ `-32700` with `id: null`. Rust does this; Python silently skips. A v1 TCK **must not fail** an agent for skipping, and must be prepared for *no response at all* (so this test needs its own short timeout and a "no reply" outcome bucket, not a hang).
- Valid JSON / invalid envelope ⇒ `-32600`. Same split.
- Batch arrays. **Do not test in a v1 suite** except as a capability probe: Rust answers with a response array, Python's receive loop crashes and the connection dies (inference). A TCK that sends a batch to a Python-based agent will destroy the connection, so if probed at all it must be the **last** test on a throwaway connection.
- Request before `initialize`. Neither SDK gates it in v1 — so an agent that answers `session/new` without `initialize` is *not* violating anything observable. Do not assert `-32600`/`-32002`/anything. (The `-32600` "initialization must complete" behavior is v2-only.)
- Unknown `sessionId`. Assert only that *some* error comes back (and even that is `MAY` per `docs/protocol/v1/session-setup.mdx:311` for `session/close`). Do not assert a code; if you want a preferred code, `-32602` matches the reference v2 examples.
- Response ordering. Cannot be asserted in either direction: Rust's default dispatch is strictly serial, Python's is fully concurrent. A concurrency *smoke* test (send N valid requests, assert all N are answered and ids match) is fair; asserting overlap or asserting ordering is not.

**Unobservable from the client side (untestable):**

- Whether the agent *internally* processes concurrently vs. serially (only latency hints at it).
- Whether `error.data` content is "correct".
- Exit codes, signal handling details beyond "process ended".
- Whether the agent obeys `-32800` semantics for internal cancellation it never told us about.
- `cwd`/`env` handling of the launch itself — the spec has no launch descriptor for v1, so a TCK's choices here (does it pass a scrubbed env like Python's allow-list, or inherit like Rust?) are harness configuration, and any agent that needs extra env vars must be configured, not failed.

**Suggested tiering.** Mandatory: T1, T5, T7, J1–J4, J6(as SHOULD-warn), E1 shape, P1, P2, errors-non-fatal, shutdown-warn. Capability-conditional: everything touching `fs/*`, `terminal/*`, `elicitation/*`, `session/load`, `logout`, `session/delete|resume|close`, `additionalDirectories`, `auth`. Informational only: parse-error reply, invalid-request reply, batch, pre-`initialize` gating, unknown-`sessionId` code, `$/cancel_request`.

## Discrepancies

1. **Batch: schema types vs. wire schema vs. v1 doc.** The spec's Rust schema crate defines and re-exports `JsonRpcBatch` from the **v1** module (`agent-client-protocol-schema/src/rpc.rs:170-232`; `agent-client-protocol-schema/src/v1/mod.rs:17`), and the Rust SDK fully implements batch reception for v1 agents (`src/agent-client-protocol/tests/jsonrpc_batch.rs:1338-1430` uses a real `Agent` with `ProtocolVersion::V1`). But the generated **v1 JSON Schema** root admits only objects, and the **v1 transports doc** enumerates only individual messages (`docs/protocol/v1/transports.mdx:23`), while the normative batch section exists **only** in v2 (`docs/protocol/v2/transports.mdx:45-81`). Meanwhile the Python SDK cannot receive a batch at all. Reading: batch is a v2 feature that the Rust SDK accepts leniently on v1 connections. **Recommendation: v1 TCK treats batch as out of scope.**
2. **Malformed JSON: Rust replies, Python ignores.** Rust: `-32700` with `id: null` and `data.line` (`src/agent-client-protocol/src/jsonrpc/transport_actor.rs:16-26`, expect-tested). Python: log + skip (`src/acp/_transport.py:81-86`, asserted in `tests/test_rpc.py:676-693`). The spec is silent. Same split for invalid envelopes (`-32600` vs. silence).
3. **Empty batch:** Rust returns a single `-32600` object (explicitly *not* an array) — which matches the v2 rule (`docs/protocol/v2/transports.mdx:50-52`) even on v1 connections. Python breaks. Spec silent for v1.
4. **`error.data` presence:** Python always serializes the `data` key (`null` when unset, `src/acp/exceptions.py:45-46`); Rust omits it (`skip_serializing_none`, `agent-client-protocol-schema/src/v1/error.rs:32`). Both are valid JSON-RPC; consumers must accept both.
5. **`error.data` for `-32601`:** Rust sends the method name as a bare string; Python sends `{"method": name}`. No convention is specified.
6. **`$/cancel_request`:** stabilized in the v1 spec (`schema/v1/meta.json` `protocolMethods`, `docs/protocol/v1/cancellation.mdx`, `docs/announcements/request-cancellation-stabilized.mdx:11`) and fully implemented in Rust; **not implemented** in the Python SDK (only the name constant exists, `src/acp/meta.py:49`). Permitted, since the spec makes `$/` notifications ignorable — but it means the reference Python agent is a conforming agent that ignores cancellation.
7. **Pre-`initialize` gating is v2-only in Rust**, yet the v1 spec says clients **MUST** initialize first (`docs/protocol/v1/initialization.mdx:24`). The obligation is placed on the client with no stated agent-side enforcement and no error code — so "agent enforces lifecycle" is not a v1 requirement. Contrast v2, which specifies second-initialization behavior (`docs/protocol/v2/…`; rust-sdk `md/protocol-v2.md:332`, `src/agent-client-protocol/src/jsonrpc/protocol_compat.rs:594-625`). **v2 material, excluded.**
8. **`docs/protocol/v1/error.mdx` is an empty stub** (`:6`) while error codes are fully defined in the schema. Anyone reading only the docs site's "Error" page learns nothing; the TCK must cite the schema.
9. **`cwd` in the launch config:** Python's spawner accepts `cwd` (`src/acp/transports.py:52,74`), Rust's `AcpAgentConfig` does not (`src/agent-client-protocol/src/acp_agent.rs:51-59`). The spec resolves the ambiguity in favor of irrelevance: the session `cwd` **MUST** be honored regardless of where the agent was spawned (`docs/protocol/v1/session-setup.mdx:359-364`).
10. **Environment policy differs:** Rust merges the configured env onto the full inherited environment; Python starts from a 6-variable POSIX allow-list. A TCK's choice here changes which agents can start at all. Recommend Rust-style inheritance plus explicit overrides, and document it.

## Open questions

- **Is a second concurrent `session/prompt` on the same session legal in v1, and if not, which error?** `docs/protocol/v1/prompt-turn.mdx:349` only says the client "may send another" once the turn completes. Adjacent to the prompt-lifecycle question and likely owned by another researcher; v2's `prompt-lifecycle.mdx` reworks this entirely.
- **What are the v1 stabilized-but-newer session methods' transport implications** (`session/list`, `session/delete`, `session/resume`, `session/close`, `session/set_config_option`) — they appear in `schema/v1/meta.json` and `docs/protocol/v1/session-setup.mdx` but are capability-gated; the capability-matrix question is a separate scope.
- **Is there a maximum message size / line length a TCK should respect?** Nothing in the spec. Python's 50 MiB default buffer (`src/acp/core.py:33-36`) is the only datapoint, and Rust's `futures` `lines()` is unbounded. Worth a dedicated decision for the TCK's own fuzz/limits tier.
- **Should the TCK offer a "strict JSON-RPC" optional tier** that asserts the Rust-style `-32700`/`-32600` replies, given the spec is silent and the Python reference disagrees? This is a TCK policy question, not a protocol question.
- **Registry-provided launch descriptors** (`docs/get-started/registry.mdx`, `docs/announcements/acp-agent-registry-stabilized.mdx`) may define a canonical `{command, args, env}` shape outside `docs/protocol/`; not examined here.
