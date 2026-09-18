# Review — slices 1–4 (harness, protocol/validation, plugin, conformance suite, fixtures)

Read-only review at commit `11b0507` (`src/tck/plugin.py`, `src/tck/__init__.py`, `README.md`,
`AGENTS.md`, `tests/test_cli.py` read via `git show 11b0507:<path>`; reporting/verdict/exit-code
concerns deliberately excluded — another agent owns them).

Baseline observed while reviewing: `uv run pytest -q` in the working tree is
`1 failed, 55 passed in 48s`, the failure being
`test_cli.py::test_hangs_until_cancel_agent_passes_cancel_requirements` asserting exit code 0
against the concurrent agent's new verdict-based exit code. Out of scope, noted only so it is
not mistaken for a pre-existing defect in the code reviewed here.

Counts: **1 blocker, 9 should-fix, 9 nits**.

---

## Blockers

### B1. Any agent line larger than 64 KiB crashes the harness with a bare `ValueError` and silently discards the bytes
`src/tck/harness/process.py:92-100` (spawn) and `:168` (`stdout.readline()`).

`asyncio.create_subprocess_exec` is called without `limit=`, so the stdout `StreamReader` keeps
asyncio's default 64 KiB buffer. CPython's `StreamReader.readline()` converts a
`LimitOverrunError` into `raise ValueError("Separator is not found, and chunk exceed the limit")`
**and clears the buffer first** — so the harness (a) raises an exception that is neither
`AgentTimeout` nor `AgentExited` (no test handles it; the plugin's diagnostics path never gets a
usable failure), and (b) loses every byte of that line, breaking the module's own contract
("this harness never drops or crashes on anything the agent sends; it records it",
`process.py:1-8`, `AGENTS.md:152-157`).

Verified:

```
$ uv run python -c "... 200 KB result line ..."
EXC ValueError Separator is not found, and chunk exceed the limit
transcript received: [77]        # only the SENT line survives
```

This is not a pathological case: a `session/update` carrying a tool-call diff, an image content
block, or `fs/write_text_file` params trivially exceeds 64 KiB. The python-sdk sizes its stdin
buffer at 50 MiB for exactly this reason (`acp-v1-transport-and-jsonrpc.md` §6, "50 MiB stdin
buffer ... de-facto line-length budget"; also Open question "Is there a maximum message size").
Every requirement in the run would currently report an opaque error for such an agent.

Fix: pass `limit=64 * 1024 * 1024` (or a documented `AgentLaunch.max_line_bytes`) to
`create_subprocess_exec`, and wrap the `readline()` call so a still-overlong line is surfaced as
a dedicated harness error (e.g. `AgentLineTooLong`) that carries the transcript and the bytes
consumed so far, rather than `ValueError`.

---

## Should-fix

### S2. ACP-TRANSPORT-002 (UTF-8) is reported FAIL for agents whose stdout is perfectly valid UTF-8
`src/tck/conformance/test_transport.py:19-49`; self-test at `tests/test_cli.py:131-142`
(`11b0507`).

One test carries both `@pytest.mark.requirement("ACP-TRANSPORT-001", "ACP-TRANSPORT-002")`, and
`pytest_runtest_makereport` records the *same* status for every id on the marker. So the
`banner_on_stdout.py` fixture — whose banner is plain ASCII — is reported as violating "The
agent's stdout is valid UTF-8" (`requirements.py:69-76`, citing `transports.mdx:6`). That is a
false positive against the cited requirement, and `test_cli.py`'s
`assert statuses.get("ACP-TRANSPORT-002") == "FAIL"` freezes the wrong behaviour into the
self-tests. Symmetrically, no fixture ever emits invalid UTF-8 on stdout, so TRANSPORT-002's
actual condition (`entry.text_error is not None`) is never exercised — it is a trivially-passing
assertion today.

Fix: split into two tests over the same recorded transcript (one asserting `text_error is None`
for TRANSPORT-002, one asserting JSON/JSON-RPC shape for TRANSPORT-001), and add a fixture that
writes a lone `b"\xff\xfe"` line to stdout so TRANSPORT-002 has a real negative control.

### S3. MANDATORY ACP-JSONRPC-002 is proved only from a response the spec does not require, and the probe method violates the extensibility rule the TCK cites
`src/tck/conformance/test_jsonrpc.py:34-53` (and `:56-64`, `:93-106`).

`test_unknown_method_response_is_result_xor_error_with_valid_shape` obtains its evidence
exclusively from the reply to `tck/does_not_exist`. Replying at all is only SHOULD
(`acp-v1-transport-and-jsonrpc.md` J6, and ACP-JSONRPC-004 is correctly tiered ADVISORY for that
reason). An agent that simply ignores an unrecognised request — permitted — times out here and
is recorded as a **MANDATORY** FAIL for a requirement about response *shape*. Two further
points: the probe name is not `_`-prefixed, contradicting Req 42 / J9 ("custom methods must be
`_`-prefixed") which the TCK holds agents to, and per T8 the client "MUST NOT write anything to
the agent's stdin that is not a valid ACP message"; and the same unprefixed name is reused in
ACP-JSONRPC-005, whose test additionally asserts `session/new` succeeds — an agent that gates
`session/new` behind `-32000` (the auth case the plan defers to slice 6/7) FAILs it.

Fix: rename the probe to `_tck/does_not_exist`; assert ACP-JSONRPC-002's envelope rules over
responses that MUST exist (initialize, `session/new`, plus every response in the ACP-SCHEMA-001
exchange via `_validate_response_envelope`), and keep the unknown-method reply as an *additional*
check that is skipped when no reply arrives.

### S4. `test_transport.py` and ACP-SCHEMA-001 drive a prompt turn with no mock client, so any agent that asks for permission deadlocks and FAILs
`src/tck/conformance/test_transport.py:33-40`, `src/tck/conformance/test_initialize.py:97-102`.

Both send `session/prompt` and then `wait_for_response(...)` directly, never answering
agent→client requests. A real agent that issues `session/request_permission` (the normal case —
`prompt-turn.mdx:32-43`, transport report P3) or any `fs/*` call gets no reply, never resolves
the turn, and both MANDATORY requirements (ACP-TRANSPORT-001/002, ACP-SCHEMA-001) fail with an
`AgentTimeout` for a conforming agent. `_helpers.run_prompt` exists precisely to avoid this and
is used by every other prompt test.

Fix: route both turns through `run_prompt`, then run the assertions over
`agent.transcript` / `turn` as today.

### S5. ACP-CANCEL-002 asserts a requirement it is not bound to (update `sessionId` attribution)
`src/tck/conformance/test_cancel.py:123-127`.

ACP-CANCEL-002 is Req 28 — *ordering* ("no `session/update` after the prompt response",
`prompt-turn.mdx:343`). The test additionally asserts every observed update carries the prompted
`sessionId`, which is ACP-PROMPT-002/Req 1 territory. An agent with impeccable ordering but a
mis-attributed update is reported as violating Req 28, i.e. the FAIL is attributed to the wrong
requirement (the plan's "no special cascade logic" decision is about *cascading*, not about one
test asserting another requirement's content). `AGENTS.md:79-80` documents this as an intended
cascade, which is what makes it worth fixing deliberately rather than by accident.

Fix: delete that loop; keep only the ordering assertions (`turn.updates` are structurally
pre-response, plus the post-response quiet-period check).

### S6. `capability` marker implements only the "non-null" encoding, and treats a dead agent as "not applicable"
`src/tck/plugin.py:208-224` (`11b0507`).

`.agents/plan.md` "Capability detection" is explicit: boolean gates (`loadSession`,
`promptCapabilities.*`, `mcpCapabilities.*`) count as supported **iff `=== true`**; object
markers (`sessionCapabilities.*`, `auth.logout`) iff present and non-null. The gate only checks
`value is None`, so `{"loadSession": false}` — the honest way to say "unsupported" — passes the
gate and the capability test runs and FAILs a conforming agent. Same for `0` / `""`. No test
carries the marker today, so this is latent, but slice 6 is built entirely on it. Secondly,
`outcome.result is None` (dead agent, spawn failure, initialize error) yields
`pytest.skip("initialize failed: ...")`, which the four-status model treats as *not applicable* —
a completely broken agent can therefore score "n/a" on every capability requirement instead of
failing.

Fix: accept a path spec that distinguishes the two encodings (e.g. `capability("…", boolean=True)`
or infer from the vendored schema's type at that path) and require `is True` for booleans; and
make "initialize failed" a FAIL/NOT TESTED outcome rather than a plain skip.

### S7. `send_raw` awaits `drain()` with no deadline → confirmed unbounded hang, with no per-test watchdog anywhere
`src/tck/harness/process.py:128-135`; `src/tck/plugin.py:pytest_pyfunc_call` (`asyncio.run`, no
timeout); no `pytest-timeout` in `pyproject.toml`.

Verified against an agent that stays alive without reading stdin:

```
HANG: send_raw/drain blocked with no deadline     # 1 MB line, drain never returns
```

Every read path honours a deadline; the write path does not. With a large `--cancel-prompt` (or
a `resource` block) and an agent that has stopped reading stdin — a realistic hung-agent
shape — the whole run hangs forever, which for a conformance tool is worse than any FAIL. The
plugin has no global per-test deadline to catch it either.

Fix: `await asyncio.wait_for(self._process.stdin.drain(), timeout=self._launch.default_timeout)`
raising `AgentTimeout`, and add a belt-and-braces per-test watchdog (wrap the coroutine in
`asyncio.wait_for(…, per_test_budget)` inside `pytest_pyfunc_call`).

### S8. `close()` never drains the remaining stdout, so the transcript is incomplete and post-response stdout garbage escapes ACP-TRANSPORT-001
`src/tck/harness/process.py:225-253`.

`close()` closes stdin and walks the SIGTERM/SIGKILL ladder without ever reading what is still
buffered in the stdout pipe. Consequences: (a) `transcript` is not "everything sent and
received" as documented (`AGENTS.md:172-175`); (b) an agent that writes a banner, a progress
bar, or pretty-printed JSON to stdout *after* the last response the test awaited is never
observed, so ACP-TRANSPORT-001 passes it — a false negative on the report's "single
highest-value transport test" (Testability note 1, "Read the agent's stdout as raw bytes for a
whole session"). Note the transport research also says valid lines emitted after stdin close are
conforming, so the drain must record-and-classify, not fail on lateness.

Fix: in `close()`, before/while waiting out the grace period, drain stdout with a short deadline
and record every remaining line (including a trailing partial line — that path already works,
verified) so the transport/schema assertions can run over the complete byte stream.

### S9. MANDATORY verdicts hinge on hard-coded sub-second quiet periods
`src/tck/conformance/test_jsonrpc.py:89-90` (1.0 s), `src/tck/conformance/test_cancel.py:137-138`
(0.3 s), `test_cancel.py:39` (`_CANCEL_RACE_WINDOW = 1.0`),
`src/tck/conformance/_helpers.py:214` (`_CANCEL_RACE_PEEK = 0.1`).

ACP-JSONRPC-003 concludes "notifications get no response" after 1.0 s, and ACP-CANCEL-002
concludes "no update follows the response" after 0.3 s. Both are false negatives by construction
for a slower agent (a reply at 1.1 s / a late update at 0.4 s PASSes), and both are the only
thing separating PASS from FAIL on a loaded machine — none of them scale with `--tck-timeout`,
even though users are told to raise that flag for slow agents (`AGENTS.md:100-103`). The
self-test suite is already sensitive to this: `cancel_wrong_stop_reason.py` must `sleep(1.2)` to
clear `_CANCEL_RACE_WINDOW` by 0.2 s, and `tests/test_cli.py` must pass `--timeout 5` for that
one fixture.

Fix: derive the quiet periods from a single configurable knob (e.g.
`quiet_period = max(0.5, min(2.0, timeout / 10))`), document them as heuristics in the
requirement text, and record the observed wait via `record_property` as the cancel test already
does for the race window.

### S10. `agent_initialize_result` swallows only two exception types; teardown failures never reach a requirement record
`src/tck/plugin.py:182-205` and `:291-311` (`11b0507`).

`except (AgentTimeout, AgentExited)` misses the realistic failures: a bad command
(`FileNotFoundError`), a non-executable agent (`PermissionError`), and the `ValueError` of B1.
Those propagate out of the session-scoped fixture and error every capability-gated test instead
of producing the documented `InitializeOutcome(None, why)`. Separately,
`pytest_runtest_makereport` only records for `report.when in {"setup", "call"}`, so a test whose
call passes but whose teardown errors (e.g. `close()` raising) stays recorded as PASS while
pytest reports an ERROR — the requirement table and pytest disagree.

Fix: catch `OSError` (and the new line-too-long error) in the fixture; record a FAIL (or an
explicit `ERROR` status) for `report.when == "teardown"` failures.

---

## Nits

### N11. `_response_method_defs` indexes the result branch positionally
`src/tck/validation.py:122` — `defs["AgentResponse"]["anyOf"][0]`. Correct today (verified:
branch 0 is `{id, result}`, branch 1 is `{id, error}`), but a schema refresh that reorders the
`anyOf` silently maps every method to the error branch and `_response_method_defs()` goes empty,
turning every `validate_agent_response` call into "not a known method". Select the branch whose
`properties` contains `result`.

### N12. `validate_agent_response`'s docstring over-claims for error responses
`src/tck/validation.py:305-323` says error responses get `error` "validated against the shared
`Error` schema"; the code only runs the hand-written `_validate_error_envelope` (integer `code`,
string `message`), and `data` is not looked at. The leniency itself is right per
`acp-v1-transport-and-jsonrpc.md` §3 (accept `data` absent *or* `null`, never assert its shape) —
only the docstring is wrong.

### N13. ACP-INIT-002 hard-asserts `protocolVersion == 1`
`src/tck/conformance/test_initialize.py:36-45`; `requirements.py:142-149`. Req 5 only says the
agent echoes the requested version *if it supports it*, otherwise returns its own latest — a
v2-only agent legally answers `2`. Acceptable for a v1-only TCK, but the failure message should
read "agent does not support protocol v1" rather than implying an echo violation.

### N14. `entry.parsed["result"][...]` chains turn protocol failures into Python tracebacks
`src/tck/conformance/test_initialize.py:44,72`, `test_session.py:40,46`, `_helpers.py:43`
(`new_session`). On an error response these raise `TypeError: 'NoneType' object is not
subscriptable` / `KeyError`, so the FAIL text for ACP-INIT-002/004, ACP-SESSION-002 and every
prompt/cancel test that calls `new_session` is an interpreter traceback rather than a protocol
diagnosis. Guard with the same `isinstance(msg, dict) and "result" in msg` pattern the other
tests use.

### N15. `run_prompt` ignores `agent.pending()`
`src/tck/conformance/_helpers.py:105-112`. Lines read during the `initialize` / `session/new`
waits sit in `_pending` and are never inspected, so a `session/update` an agent emits before the
prompt response is invisible to ACP-PROMPT-002 / ACP-CANCEL-002. Harmless for the current
fixtures; drain `pending()` into `updates` at the start of the turn (and note the
`wait_for_response`-vs-`pending()` interaction is otherwise sound — `read_line` records into
`transcript` *before* the predicate runs, so no line can be lost).

### N16. ACP-JSONRPC-003's detector requires an `id` key
`src/tck/conformance/test_jsonrpc.py:84-87`. A peer that answers a notification with
`{"jsonrpc":"2.0","error":{…}}` and no `id` at all is not detected (false negative). Treat any
line that is neither a request/notification nor a known-id response as a reply.

### N17. The mock client's two most important branches are exercised by no fixture
`src/tck/conformance/_helpers.py:140-163`. Nothing in `tests/fixtures/agents/` ever sends
`session/request_permission` or an `fs/*`/`terminal/*` request, so the permission-answering path
(including the `outcome: "cancelled"` switch after cancel) and the `-32601` path are dead code in
the self-test suite — yet every prompt and cancel test depends on them, and slice 6's negative
tests are built on `client_requests_seen`. Add a `asks_permission.py` fixture and one that calls
`fs/read_text_file`.

### N18. `AgentTimeout` carries the transcript but not stderr
`src/tck/harness/process.py:25-34` vs `:37-51`. `AgentExited` carries `stderr`; a timeout is the
*more* common failure and stderr is usually where the agent explains itself. The plugin attaches
it separately, so this only bites direct harness users — still worth parity.

### N19. stderr is accumulated without bound
`src/tck/harness/process.py:107-119`. The Rust SDK caps its capture at 64 KiB
(`acp-v1-transport-and-jsonrpc.md` §6). A chatty agent under a long `--timeout` can grow the
chunk list arbitrarily; keep a bounded tail (plus a "truncated N bytes" marker).

### N20. Unbounded `await proc.wait()` after SIGKILL
`src/tck/harness/process.py:247`. Everything else in `close()` is deadline-guarded; this one is
not. `os.killpg(proc.pid, …)` itself is correct on macOS/Linux given `start_new_session=True`
(the child is its own group leader, so `pid == pgid`), and `ProcessLookupError` is suppressed for
the already-exited race — only the final wait needs a timeout.

---

## Checked and found sound (no action)

- **Method→schema derivation is on the correct side.** The vendored schema names its envelopes by
  *author*, so `AgentRequest`/`AgentNotification` really are agent-authored
  (verified: the derived map is `fs/*`, `terminal/*`, `session/request_permission`,
  `session/update`, `elicitation/*`, `$/cancel_request`), and `AgentResponse`'s result branch
  yields the 12 agent-implemented methods. `protocol.py:119-124`'s cross-derivation
  (`AGENT_NOTIFICATIONS` from `ClientNotification`) is likewise correct — confusing, but
  documented, and it produces exactly `{session/cancel}` / `{session/update,
  elicitation/complete}`.
- **`null`-response leniency scope.** `_response_schema_permits_null` fires only for the
  all-optional object responses (`session/load`, `session/resume`, `session/close`,
  `session/delete`, `session/set_mode`, `authenticate`, `logout`) and never for
  `initialize` / `session/new` / `session/prompt` / `session/list` /
  `session/set_config_option` — exactly the plan's "`null` empty responses" decision and
  Discrepancy 3.
- **UTF-8 and partial-line handling.** Verified an undecodable final line with no trailing
  newline is recorded as an entry with `text_error` set and then EOF raises `AgentExited`
  (`process.py:171-183`); multibyte sequences cannot be split because decoding happens per
  complete line.
- **Per-test process isolation.** Every conformance test spawns its own `AgentProcess` through
  `connected_agent`; the only shared state is `lru_cache`d read-only schema data and the
  session-scoped initialize probe, which owns a separate short-lived process.
- **Cancel SKIP-vs-FAIL logic** (`test_cancel.py:43-66`) matches the plan's decision, including
  the honest `cancelled_at_index=None` peek in `run_prompt`, and does not convert a race into
  either verdict.
- **Fixtures.** Each defect fixture trips its documented requirement and nothing else that
  matters; the only accidental extras are benign (`answers_notifications.py` no longer resolves a
  hanging prompt because it returns before `super()._handle_notification`, unreachable given the
  cancel tests SKIP for it; `unknown_method_no_error.py`'s `_KNOWN_METHODS` omission of
  notification names is harmless since it overrides `_handle_request` only). `conforming.py` is
  lenient about request validity (it never rejects a malformed `session/prompt`), which does not
  mask any current TCK assertion but will once slice 6/7 adds negative params tests.
