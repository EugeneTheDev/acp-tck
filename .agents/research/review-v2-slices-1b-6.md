# Review: v2 slices V2-1b … V2-6 (`1d795cc..26bf0f2` on `v2-support`)

**Sources checked:**
- this repo @ `26bf0f2` + two workbench commits (worktree `/Users/eugene/Documents/JetBrains/projects/acp-tck-2`, branch `v2-support`)
- spec `/Users/eugene/…/agent-client-protocol` @ `b9d6aca6757d0f5b6e435cad54f9f04657aa9802` (pulled `--ff-only`, 2026-09-22). **`git diff --stat 8f76d6c..b9d6aca -- docs/protocol/v2 schema/v2 docs/rfds/v2` is empty**, so every citation pinned at `8f76d6c` is still line-accurate at HEAD, and `src/tck/v2/schema/{schema,meta}.json` are byte-identical to upstream (`diff -q`, both clean).
- rust-sdk @ `28688b2d` and python-sdk @ `9d07d787` (= `1.0.0rc2`), both pulled `--ff-only`
- `.agents/plan.md` (every "— decisions" section, the tiering rule, D3 + its 2xx refinement, version-mismatch handling, "Deferred nits"), `.agents/research/acp-v2-*.md`, `.agents/research/review-v2-slices-0-1a.md`
- runs performed in this worktree: `uv run pytest` → **239 passed in 359 s**; `uv run acp-tck --protocol-version 2 --cancel-prompt __hang__ --auth-method tck --allow-logout --report-json … -- python tests/fixtures/agents/v2/conforming_full.py` → exit 0, **CONFORMANT**, 95 passed / 8 skipped, zero FAIL, zero NOT_TESTED; a throwaway strict-v2 agent under `--protocol-version 1` (gitignored `scratch/vmcheck/strict_v2.py`) to test the `blocked_by_version_mismatch` claim; `uv run --with agent-client-protocol==1.0.0rc2 python -c …` to reproduce the Python SDK batch crash.
- citation audit: all 106 registry citations were machine-extracted and the cited spec lines printed; I read the extracted text for ~90 of them, covering **every** area (INIT, SCHEMA, SESSION, PROMPT, STATE, PROMPTCAP, PERM, CLIENTCAP, CANCEL, TRANSPORT, JSONRPC, BATCH, RESUME, LIST, CLOSE, DELETE, ADDDIRS, MCP, CONFIG, AUTH, PATCH, ENUM, META, EXT, ERROR, SHUTDOWN, STDERR, INFO).

**Confidence:** high — every finding below is backed by a file:line I opened, a spec line I printed, or a command I ran in this worktree. The per-fixture cascade table in finding 15 comes from ~45 unscoped `--protocol-version 2` runs, one per defect fixture, diffed against each self-test's asserted set. Lower confidence only on the *probability* judgements in findings 1 and 26 (how likely a real agent is to refuse to resume a just-created session, or to emit a spontaneous notification before answering `[]`) — the mechanism is certain, the frequency is not.

## Summary

Six slices, 106 requirements, 103 conformance tests, all green, and the citation quality is
genuinely high: of the ~90 citations I opened, every one says what the registry row claims, and
the two areas where the spec is weak (`error.mdx` still a stub, `$/`-prefixed notifications) are
correctly parked as INFORMATIONAL rather than guessed at. The session-baseline tiering rule is
applied consistently (every `capabilities.session`-dependent row is `Tier.CAPABILITY`, only
`initialize`-level rows are MANDATORY), the version-mismatch machinery works and is honest, the
cancel race keeps v1's "never score a race" discipline, and `conforming_full.py` drives 98 of 106
ids to PASS with zero FAIL and zero NOT_TESTED.

The problems are concentrated in three places. First, **`ACP-RESUME-202..205` do not use the
three-route `obtain_resumable_session` helper that `ACP-RESUME-201` uses**, so an agent that the
TCK itself admits it may be unable to obtain a resumable session from gets four CAPABILITY FAILs
and a false `NOT CONFORMANT` — the one finding I would block a merge on. Second, several probes
**assert more than the research allows**: `ACP-CONFIG-202` asserts the echoed `currentValue`
(explicitly reserved as ADVISORY by the session-management report), `ACP-BATCH-203/204` depend on
an agent replying to an unknown `_`-prefixed method (only a SHOULD — the JSON-RPC module's own
test SKIPs for exactly that reason), and the `ACP-BATCH-204` probe batches `session/new`, which is
the very SHOULD NOT the TCK registers as `ACP-BATCH-208`. Third, **batch-array blindness is
inconsistent**: `run_prompt`, `test_transport`, `test_enums`, `test_initialize` and parts of
`test_cancel` unwrap a JSON array line, while `ACP-JSONRPC-003` (MANDATORY), `ACP-CANCEL-202`,
`ACP-SCHEMA-002` and `_helpers.resume_session` do not — those four silently pass (or silently see
nothing) against a spontaneously batching agent, and the same six-line flattening snippet is
copy-pasted in six places instead of living in `_helpers`.

Two smaller themes recur. First, several *descriptions* claim more than the code does: registry
texts (`ACP-CLIENTCAP-202` on notifications, `ACP-AUTH-204` on "advertised, non-terminal" method
ids, `ACP-JSONRPC-001/003/005` on batch coverage), four defect-fixture docstrings ("the rest of
the turn is unaffected" — it is not), and the docs (`AGENTS.md` still says "52 requirements",
claims `conforming_full.py` passes "literally every one of the 106 ids", and both `AGENTS.md` and
`tck.common.report`'s own docstring assert that `blocked_by_version_mismatch` is "always `false`
for a v1 run" — which I disproved in 30 seconds with a strict-v2 fixture). Second, the `-k`
scoping added in V2-4b for runtime has quietly decoupled eleven self-tests from reality: an
unscoped run of the five broad V2-2/V2-3 defect fixtures now also FAILs twelve V2-6 ids that
nobody has recorded, because V2-6 added three test modules and the older self-tests' `-k`
expressions were never revisited. Nothing is *wrong* in the suite because of it, but the
self-tests no longer pin what they claim to pin.

The fixtures themselves are in good shape: every wire shape `_base.py` emits validates against the
vendored schema and matches the cited `$defs` by hand, the `session/resume` replay ordering and
the `content: []` chunk primer are correct, and ~30 defect fixtures' asserted FAIL sets match an
unscoped run exactly.

On the four open tiering/id questions the plan deferred to this pass, my recommendations are in
"Decisions recommended": keep `ACP-AUTH-202` (and fix the contradictory *rationale* instead),
keep `ACP-MCP-201/202` INFORMATIONAL, and re-tier the four always-SKIP ADVISORY rows to
INFORMATIONAL.

## Findings

1 BLOCKER, 20 SHOULD-FIX, 22 NIT.

| # | Severity | File:line | Finding | Suggested fix |
|---|----------|-----------|---------|---------------|
| 1 | BLOCKER | `src/tck/v2/conformance/test_session_capabilities.py:105-117,134-142,163-166,203-206` vs `:77` | `ACP-RESUME-201` obtains its session through `obtain_resumable_session` (`_helpers.py:392-428`), which tries three routes and SKIPs if none works. `ACP-RESUME-202/203/204/205` instead do `connected_agent` + `_session_with_history` + a direct `resume_session`, then hard-assert `isinstance(msg.get("result"), dict)`. Route (1) "resume the session you just created" is exactly the route the research says is not guaranteed (`acp-v2-session-management.md:475-479`: "treat any *other* error from all three routes as a SKIP"). Against an agent where only the list route works, `ACP-RESUME-201` SKIPs while four CAPABILITY rows FAIL -> a false `NOT CONFORMANT`. | Route 202-205 through `obtain_resumable_session` (it already yields the connection and session id), or at minimum convert a non-`-32601` error on the setup `session/resume` into the same SKIP `ACP-RESUME-201` produces. |
| 2 | SHOULD-FIX | `src/tck/v2/conformance/test_session_config.py:219-224` | `ACP-CONFIG-202` additionally asserts `changed["currentValue"] == new_value`. `acp-v2-session-management.md:508` (C9) says verbatim: "Asserting `currentValue == the value you sent` is weaker than it looks -- an agent may legitimately reflect a dependent adjustment; keep that sub-assertion ADVISORY." The registry text for the row covers only the superset check, which `:213` already does correctly. A conforming agent that adjusts a dependent option FAILs a CAPABILITY row. | Drop the equality assertion, or demote it to a `record_property` observation. |
| 3 | SHOULD-FIX | `src/tck/v2/conformance/test_batch.py:152-161`, `:208` | The `ACP-BATCH-204/205` probe batches `session/new` -- the exact method `ACP-BATCH-208` registers as "SHOULD NOT batch lifecycle-sensitive messages" (`transports.mdx:77-80`), and which `acp-v2-cancellation-and-batching.md:517-519` explicitly forbids the TCK from batching ("if the TCK batches `initialize` or `session/new` it is itself violating a SHOULD NOT and any resulting failure is ambiguous. Use `session/list` / `_tck/*` / `session/cancel`"). `test_batch.py:208`'s own docstring then claims "the TCK itself never batches these". | Swap `session/new` for `session/list` (or a second `_tck/*`). That also removes the need for `login_if_needed`/`skip_if_auth_gated_msg` in this file (`:51-54`, `:67`, `:176`). |
| 4 | SHOULD-FIX | `src/tck/v2/conformance/test_batch.py:125,138-140` and `:162,180-184` | `ACP-BATCH-203` and `204` both make their assertion depend on the agent *responding to* `_tck/does_not_exist` -- an unknown-method reply is only a SHOULD (`extensibility.mdx:80`), which is why `test_jsonrpc.py:99-112` (`ACP-JSONRPC-004`) SKIPs rather than fails in the same situation. `:183-184` goes further and requires an **error**: an agent that returns `result: null` for unknown `_` methods (the documented v1 behaviour of the Python SDK) FAILs. Both rows are ADVISORY so the verdict cannot flip, but the FAIL is unsound -- and real: `tests/v2/test_cli.py:1842-1853` only survives because of its `-k test_extensibility` scope. | 203: use two structurally invalid entries (`acp-v2-cancellation-and-batching.md:493`'s `[17, true, null]` shape) so no SHOULD is in the path. 204: use a must-answer method, or SKIP on `AgentTimeout`, and accept a `result` as well as an `error`. |
| 5 | SHOULD-FIX | `test_jsonrpc.py:91-92`; `test_cancel.py:210-218`; `test_extensibility.py:227-231`; `_helpers.py:230-233` | Four transcript scans match only `isinstance(parsed, dict)`, so a message delivered inside a JSON-RPC batch array is invisible to them: `ACP-JSONRPC-003` (**MANDATORY** -- "notifications never receive a response ... including a notification inside a batch") silently PASSes a batch-delivered reply; `ACP-CANCEL-202`'s "no `state_update` after the cancelled idle" silently PASSes a batched one; `ACP-SCHEMA-002` skips batch lines entirely (`continue`); `resume_session` never sees a batched `session/resume` response or replay update and times out instead. `tests/fixtures/agents/v2/emits_batch_updates.py` proves the scenario is real, and `run_prompt` (`_helpers.py:674-682`), `test_transport.py:82-88`, `test_enums.py:275-283`, `test_initialize.py:313-324`, `test_cancel.py:298-303` all *do* unwrap. | Add one `_helpers.iter_messages(entry) -> list[dict]` (flatten a list line, pass through a dict line, drop anything else) and use it at every transcript-scanning site, including `resume_session`'s wait loop. |
| 6 | SHOULD-FIX | `src/tck/v2/requirements.py` `ACP-CLIENTCAP-202` text; `_helpers.py:733-747`; `test_client_capabilities.py:39-43` | The row says "Every agent->client request **/notification** method observed during a prompt turn is a member of `CLIENT_METHODS` or `PROTOCOL_METHODS` ... or begins with `_`". But `run_prompt` records only messages carrying an `id` (`_helpers.py:733`); any other agent-authored *notification* falls through to the `return` at `:747` and is never added to `client_requests_seen`. An agent emitting a notification named `foo/bar` passes. | Record non-`session/update` agent notifications too (a second `PromptTurn` field, or add them to `client_requests_seen`), or narrow the requirement text to requests only. |
| 7 | SHOULD-FIX | `src/tck/v2/conformance/test_authentication.py:168-176` (and `:226-233`); `_helpers.py:98-102` | The TCK sends `auth/login` in two cases its own source research forbids. (a) `ACP-AUTH-204` never checks that `--auth-method`'s id is among the advertised `methodId`s, nor that its `type != "terminal"` -- `acp-v2-authentication.md:470-471` must-NOT #12: "Sending `auth/login` with a `terminal` `methodId`, or with a `methodId` the agent did not advertise. Both are client MUST-NOTs (V13); the TCK holds itself to spec." The registry text for `ACP-AUTH-204` already *claims* "naming a non-`terminal`, advertised `methodId`". (b) `login_if_needed` sends `auth/login` whenever `--auth-method` is set, without checking `authMethods` is non-empty -- must-NOT #7; `current_initialize_auth_methods()` is already imported at `_helpers.py:39`. | Validate the id against `init_result["authMethods"]` and SKIP with a precise reason instead of sending; gate `login_if_needed` on non-empty `authMethods`. |
| 8 | SHOULD-FIX | `src/tck/v2/conformance/test_session_capabilities.py:452`, `:472` | The `ACP-MCP-201/202` probes send `mcpServers` entries with **no `type` discriminator** (`{"name","command","args"}` / `{"name","url"}`). Every `$defs/McpServer` branch has `"required": ["type"]` (verified by parsing the vendored schema). The rows claim "a well-formed stdio/http MCP server entry"; a conforming agent answers `-32602` and the probe records `accepted=False` -- a misleading datum about a request the TCK itself malformed. | Add `"type": "stdio"` / `"type": "http"`. |
| 9 | SHOULD-FIX | `src/tck/v2/conformance/test_session_capabilities.py:178-192` | `ACP-RESUME-204` asserts `turn.message_id in replayed_ids` as soon as *any* `user_message` replays, and matches only `"user_message"` (never `"user_message_chunk"`). `acp-v2-session-management.md:490` (R7) prescribes a deliberately narrower trigger: "FAIL only if a replayed `user_message`/`user_message_chunk` carries content equal to the prompted content but a **different** `messageId` ... Absence of the message is conforming (R5), so the test must not require presence." | Match on content, consider both kinds, and FAIL only on the content-matches/id-differs case. |
| 10 | SHOULD-FIX | `src/tck/v2/conformance/test_extensibility.py:92-94` | `ACP-META-001`'s test asserts, as its third assertion, that the turn's `stopReason` is a defined constant or `_`-prefixed. That is verbatim `ACP-STATE-203`'s requirement, not `_meta`-acceptance. Measured consequence: it is the *only* reason `bad_stop_reason.py` and `missing_message_id.py` also FAIL `ACP-META-001` in an unscoped run -- two of the six undocumented cascades in finding 15. | Drop the third assertion (keep "a normal acceptance receipt arrived" + "the turn reached a terminating idle"). |
| 11 | SHOULD-FIX | `src/tck/common/report.py:164-171`; `AGENTS.md:1806` | Both state that `blocked_by_version_mismatch` is "v2 only ... always `false` for a v1 run -- no v1 test ever emits this marker". False: the marker is emitted by the **version-agnostic** capability gate (`src/tck/common/plugin.py:431-444`), which compares the negotiated version against `spec.protocol_version` for *any* version. Verified: a strict-v2 agent (the spec-mandated behaviour under `ACP-INIT-202`) answering `2` to a v1 `initialize`, run under `--protocol-version 1`, produces `"blocked_by_version_mismatch": true`. Also, the terminal hint at `common/plugin.py:827-832` says "negotiated **down** to a different version", which is wrong in exactly this case. | Correct both texts; note the symmetric v1-side behaviour is now live (plan.md calls it "a later slice"); make the hint direction-neutral. |
| 12 | SHOULD-FIX | `AGENTS.md:1536-1543`, `AGENTS.md:818` | Stale docs. `:1542` says the v2 registry has "**52 requirements** in all" and its coverage list stops at V2-3 -- the registry has 106 ids and also covers session management, auth, patches, enums and hygiene. `:818` claims `conforming_full.py` PASSes "literally every one of the 106 ids"; the measured result is 98 PASS + 8 legitimate SKIP (`ACP-AUTH-205/207`, `ACP-BATCH-206/207/208`, `ACP-CANCEL-204`, `ACP-PATCH-206/207`), which the self-test itself already encodes. | Update the count and coverage list; change to "every exercisable id (98 of 106; 8 SKIP)". |
| 13 | SHOULD-FIX | `README.md:61-65` | "`--allow-logout` ... (never affects conformance either way, since it's a `CAPABILITY`-tier check)". A CAPABILITY **FAIL** is precisely what flips the verdict, so passing the flag against an agent whose `auth/logout` errors *does* make the run NOT CONFORMANT. `AGENTS.md:1609` states it correctly ("omitting `--allow-logout` never by itself makes a run NOT CONFORMANT"). | Reword to `AGENTS.md`'s phrasing. |
| 14 | SHOULD-FIX | `src/tck/v2/conformance/test_extensibility.py:159-169` | `ACP-EXT-202` performs its own `initialize` on a `handshake=False` connection and then judges a v2-only shape (`find_unknown_root_keys("AgentCapabilities", ...)`) without calling `skip_if_version_mismatch`; it degrades to a *misleading* skip ("initialize result has no capabilities object") for a v1 agent and loses the `blocked_by_version_mismatch` signal the plan's rule intends. Separately, `:162`'s `login_if_needed` call is pointless here (nothing session-dependent follows) and can SKIP an otherwise-passing row when `auth/login` fails. | Call `skip_if_version_mismatch(msg["result"])` before reading `capabilities`; drop the `login_if_needed` call. |
| 15 | SHOULD-FIX | `tests/v2/test_cli.py:732,829,964,983,1041,1098,1164,1765,1780,1795,1842` | Eleven `-k`-scoped self-tests assert a FAIL set that is narrower than an unscoped run's, and six of those cascades are documented nowhere. Measured by running each fixture unscoped: `tool_call_update_missing_id`/`plan_missing_plan_id`/`message_chunk_missing_message_id` each also FAIL `ACP-PROMPT-205`; `bad_stop_reason` also FAILs `ACP-META-001`; `missing_message_id` also FAILs `ACP-META-001`+`ACP-PATCH-203`; `custom_method_no_response` also FAILs `ACP-BATCH-203/204/205`+`ACP-ERROR-001` (recorded only in `.agents/state.md`, and its test is even *named* `..._fails_ext_001_only`); and the five broad V2-2/V2-3 fixtures (`no_idle_after_running`, `update_wrong_session`, `cancel_no_idle`, `cancel_returns_error`, `cancel_wrong_stop_reason`) each additionally FAIL the twelve V2-6 ids `ACP-PATCH-201/203/204/205/206/207/208`, `ACP-ENUM-201/202`, `ACP-META-001/201`, `ACP-SCHEMA-002` (+`ACP-PATCH-209` for the two cancel ones). Root cause: V2-6 added three modules but the V2-2/V2-3 self-tests' `-k` expressions and their otherwise careful cascade docstrings were never revisited. | Widen the `-k` expressions and the asserted sets, or add one comment per test naming the ids an unscoped run additionally FAILs. Fixing findings 4 and 10 first removes three of the six undocumented cascades outright. A full unscoped run of one defect fixture is ~9 s, so widening is affordable for the narrow cases. |
| 16 | SHOULD-FIX | `tests/fixtures/agents/v2/tool_call_update_missing_id.py:7-13`, `plan_missing_plan_id.py:7-12`, `message_chunk_missing_message_id.py:9-11`, `custom_method_no_response.py:6-7` | Four defect-fixture docstrings claim "the rest of the turn is unaffected" / "every other method is dispatched normally". The first three override `_send_rich_turn_updates`, which `_base.py:390` calls on **every** turn, so their malformed update is emitted in every prompt-driven test and `ACP-PROMPT-205` (CAPABILITY -- affects the verdict) schema-validates it; the fourth swallows every `_`-prefixed method, which the batch and diagnostics probes rely on. The fixture catalogue in `AGENTS.md:923-931` inherits the same wrong claims verbatim ("FAILs only `ACP-PATCH-204`", "FAILs only `ACP-PATCH-205`", "FAILs only `ACP-EXT-001`"). | Correct the four docstrings (and their `AGENTS.md` entries) to name the requirements each fixture really trips. |
| 17 | SHOULD-FIX | `tests/v2/test_registry.py:251-269` vs `tests/v1/test_registry.py:106-140` | The v2 tier cross-check asserts only `_MANDATORY_IDS` and `_CAPABILITY_IDS`; the v1 twin asserts all four tiers. `tests/v2/test_cli.py:119,145` already define `_ADVISORY_IDS`/`_INFORMATIONAL_IDS` and both currently match the registry, so this is a 6-line addition -- and it matters right now, because the recommended re-tiering of `ACP-BATCH-206/207/208`/`ACP-CANCEL-204` is exactly the drift it would catch. | Add the two missing assertions. |
| 18 | SHOULD-FIX | `src/tck/v2/requirements.py` `ACP-JSONRPC-001`/`003`/`005` texts; `test_jsonrpc.py:5-15` | The three texts claim batch coverage ("including for responses delivered inside a batch response array" / "including a notification inside a batch" / "including an invalid or empty batch") that the bound tests never exercise -- the module docstring says both things: `:5-10` claims the probes "widen to also cover a batch-delivered response/notification", `:12-15` says the file "never receives a batch-shaped probe". `:12-15` matches the code; the evidence exists but is bound to `ACP-BATCH-201/202/204`. | Either add the `ACP-JSONRPC-*` ids as a second `@pytest.mark.requirement` on the corresponding `test_batch.py` tests, or delete the clauses and the contradictory docstring paragraph. |
| 19 | SHOULD-FIX | `_helpers.py` (absent); `test_batch.py:46-68`, `test_session_config.py:51-68`, `test_authentication.py:30-52`, `test_transport.py:45-57`, `test_initialize.py:31-35,64-68,118-121,172-174,198-201,229-232,278-281` | Four near-identical copies of "fresh connection -> manual `initialize` -> `skip_if_version_mismatch` -> `login_if_needed`" (the `test_batch`/`test_session_config` pair is byte-identical apart from its docstring), plus seven inline copies of the initialize params -- two of which bypass `SPEC.initialize_params()` and hardcode `{"protocolVersion": 2, "info": {"name": "acp-tck", "version": "0"}}` with no `capabilities` key and a fake version, while `src/tck/v2/__init__.py:17-26` sends `capabilities: {}` and the real TCK version. Also duplicated: batch flattening (6 copies, finding 5), the "silent / exited / replied" ladder (7 copies: `test_informational.py:72-88,113-140,156-168,189-201`, `test_batch.py:222-233,251-257`, `test_cancel.py:429-438`), `_update_of` (`test_session_capabilities.py:40-50` == `test_session_config.py:139-147`), and the cancel race gate (`test_cancel.py:83-109` ~ `:352-374`). D6's "honest duplication" is about v1-vs-v2 machinery, not copies inside `tck.v2.conformance`. | Add `_helpers.v2_only_agent(launch, *, capabilities=None, yield_result=False)`, `_helpers.iter_messages(entry)`, `_helpers.probe_behaviour(agent, ...) -> str`, and move `_update_of` in. Route every manual `initialize` through `SPEC.initialize_params()`. |
| 20 | SHOULD-FIX | `src/tck/v2/conformance/test_enums.py:49-77` | The four `ENUM-201` and three `ENUM-202` constant sets are hand-copied into a test module. I verified all seven match the vendored schema exactly today -- but v2 is a Draft that "should be expected to churn" (`src/tck/v2/schema/VENDORED.md:6-11`), and a new upstream constant would turn a *conforming* agent into a FAIL with nothing to catch the drift. `STOP_REASONS` at least lives in `tck.v2.protocol:50`. | Move the sets to `tck.v2.protocol` next to `STOP_REASONS` and add a meta-test in `tests/v2/test_validation.py` deriving each from `schema.json`'s `anyOf`/`const` branches. |
| 21 | SHOULD-FIX | `src/tck/v2/conformance/test_enums.py:266-283`; `test_batch.py:101-110` | Two read loops have no *aggregate* deadline: each `read_line` is bounded by `--timeout`, but the loop restarts the budget on every line, so a chatty agent keeps them going until the `--tck-test-timeout` watchdog. `_helpers.resume_session:217-227` and `run_prompt:635-758` show the right pattern (one `overall_deadline`). | Compute a deadline once and pass `min(remaining, ...)` to each read. |
| 22 | NIT | `src/tck/v2/conformance/_helpers.py:782`, `:798` | `run_prompt`'s two trailing peeks pass the raw `peek_timeout` instead of clamping to `overall_deadline`, so a call can exceed `timeout` by up to ~1 s -- contradicting the docstring at `:554-556` ("Every wait below is bounded by `timeout`"). | Clamp both to the remaining budget, or soften the docstring. |
| 23 | NIT | `src/tck/v2/conformance/test_authentication.py:69-70`, `:84` | `ACP-AUTH-201` `return`s and `ACP-AUTH-206` iterates an empty list when `authMethods` is absent -- both record a **PASS**, not a SKIP. For `ACP-AUTH-206` (MANDATORY) a vacuous PASS on an agent with no auth surface is the more misleading. | `pytest.skip("agent advertises no authMethods")` in both. |
| 24 | NIT | `test_session_capabilities.py:306`; `test_patches.py:190` | Absolute-path checks use `cwd.startswith("/")`; `acp-v2-session-management.md:497` (L6) prescribes `os.path.isabs`. | Use `os.path.isabs`, or state that POSIX-only is deliberate. |
| 25 | NIT | `src/tck/v2/conformance/test_cancel.py:220` | `ACP-CANCEL-202` wraps its quiet-period read in `pytest.raises((AgentTimeout, AgentExited))`, so an agent that **crashes** immediately after the cancelled idle scores PASS. | Assert on `AgentTimeout` only, or record the exit as a distinct failure. |
| 26 | NIT | `src/tck/v2/conformance/test_batch.py:77-83` | `ACP-BATCH-201` (MANDATORY) reads exactly one line after sending `[]` and judges it. A single spontaneous notification arriving first would FAIL a MANDATORY row. | Read until a response-shaped line (bounded), ignoring notifications. |
| 27 | NIT | `src/tck/v2/requirements.py` `ACP-ENUM-201` citation | The row is promoted to CAPABILITY on the grounds that its four sites "carry dedicated per-site MUST prose", but the citation is only the generic `extensibility.mdx:111-118`. The per-site MUSTs exist: `tool-calls.mdx:75` (ToolKind), `tool-calls.mdx:373` (ToolCallStatus), `agent-plan.mdx:88` (priority), `agent-plan.mdx:100` (plan-entry status). | Add the four lines to the citation. |
| 28 | NIT | `src/tck/v2/requirements.py` `ACP-JSONRPC-001` citation | `docs/protocol/v2/overview.mdx:189` is the *camelCase naming conventions* sentence; it supports "id echoes exactly" only via its trailing clause "The JSON-RPC envelope fields ... follow the JSON-RPC 2.0 specification". | Keep it but say why, or lead with `transports.mdx:68-69`. |
| 29 | NIT | `src/tck/v2/requirements.py` `ACP-CANCEL-208` / `ACP-CLOSE-202` | Two registry ids, one requirement, one test, the same citation (`session-setup.mdx:258`) -- the `ACP-CLOSE-202` text admits it ("deliberately reused verbatim ... purely for V2-4's own report legibility"). A reader of the tier counts sees the same defect twice. `ACP-CANCEL-205` is likewise a strict subset of `ACP-JSONRPC-003` applied to one method. | Keep and state the double-count in the report legend, or drop `ACP-CANCEL-208` in favour of `ACP-CLOSE-202` (where the MUST lives). |
| 30 | NIT | `src/tck/v2/conformance/test_patches.py:292-297` | `ACP-PATCH-209` requires `running` to appear *after* the last `requires_action`. `prompt-lifecycle.mdx:371` conditions that on work actually resuming; a turn ending in `refusal`/`cancelled` right after the permission answer never resumes. ADVISORY, so low impact. | SKIP when the turn's `stopReason` is `refusal`/`cancelled`. |
| 31 | NIT | `src/tck/v2/conformance/test_session_capabilities.py:355-359` | `ACP-DELETE-202` evaluates `((before_msg.get("result") or {}).get("sessions") or [])` before the comprehension's own `isinstance(before_msg, dict)` guard, so a malformed `session/list` response raises `AttributeError` (an opaque FAIL) instead of asserting. | Guard first. |
| 32 | NIT | `src/tck/v2/conformance/test_session_config.py:161` | `_pick_settable_option` is `async def` with no `await`. | Make it a plain function. |
| 33 | NIT | `test_session_capabilities.py:284-289`, `:303-308`; `:122` | `ACP-LIST-203/204` loop over a possibly empty `sessions` list without recording the entry count, so the report cannot distinguish "checked 3 entries" from "checked none". `ACP-RESUME-202`'s trailing-update check is not filtered by `sessionId` (`_update_of` ignores `params.sessionId`) while the research scopes it to the resumed session. | `record_property` the counts; filter by `sessionId`. |
| 34 | NIT | `test_jsonrpc.py:128`; `test_diagnostics.py:47` | Two vacuous assertions: the first re-asserts what `new_session` (`_helpers.py:181`) already guaranteed; the second `json.dumps(data)` round-trips a value that came from `json.loads` (the comment admits it). | Delete, or replace with a check that can fail. |
| 35 | NIT | `src/tck/common/plugin.py:132-140` | The version-agnostic option module's `--tck-allow-logout` help text names v2's `ACP-AUTH-203` *and* v1's `ACP-AUTH-004` -- the recurrence of `review-v2-slices-0-1a.md` finding 16, now in both directions. | Describe the behaviour, not the ids. |
| 36 | NIT | `src/tck/common/version.py:29,34`; `src/tck/v1/__init__.py:24,27`; `src/tck/v2/__init__.py:37,40`; `tests/v1/`, `tests/common/` | Two plan "Deferred nits" are still open: `VersionSpec.schema_dir`/`conformance_package` still have no consumer outside `tests/common/test_version.py` (review-0-1a #10), and `tests/v1/`/`tests/common/` still lack `__init__.py` (#18). | Decide: drop both fields (and update D1) or wire `conformance_package` into the report. |
| 37 | NIT | `tests/fixtures/agents/v2/_base.py:361-400` vs `tests/fixtures/agents/v1/_base.py:268-280` | The v2 fixture base never validates `session/prompt`'s `sessionId` (nor the `prompt` array's shape); v1's does, deliberately, since slice 7b ("`_base.py` should answer an unknown `sessionId` with an error, not a result"). Consequence: `ACP-INFO-UNKNOWNSESSION-001` records `"replied with a result (no error)"` against `conforming.py`, i.e. the probe's own baseline models an agent that runs a whole turn for a session it never created. | Port the v1 `-32602` guard (and, optionally, the prompt-shape validation) to the v2 `_base.py`. |
| 38 | NIT | `tests/fixtures/agents/v2/bad_stop_reason.py:9`, `no_idle_after_running.py`, `no_running_update.py`, `missing_message_id.py`, `echo_wrong_message_id.py` | Five v2 fixture docstrings reference `ACP-PROMPT-002`, which exists only in the v1 registry (v2's equivalent is `ACP-PROMPT-205`). | Mechanical text fix. |
| 39 | NIT | `tests/fixtures/agents/v2/vendor_stop_reason.py` | Its docstring says it "must PASS every V2-2a requirement", but it FAILs `ACP-CANCEL-201/206/207/208` and `ACP-CLOSE-202` -- correctly, and its self-test (`tests/v2/test_cli.py:761-808`) documents this at length. Only the fixture docstring is stale. | Point the docstring at the self-test. |
| 40 | NIT | `tests/fixtures/agents/v2/wrong_id_echo.py`; `tests/v2/test_cli.py:1334` | Unscoped, `wrong_id_echo.py` FAILs all 106 ids -- the intended "cascading failure is the correct verdict shape" case, but unlike the other broad fixtures it carries no comment saying so next to its `-k jsonrpc` scope. | One comment. |
| 41 | NIT | `tests/v2/test_registry.py:42` | `test_registry_has_exactly_the_v2_6_requirements` hard-codes the 106-id set behind a slice-named function, so it needs renaming at every future slice; v1 has no equivalent. | Rename to something slice-neutral. |
| 42 | NIT | `tests/v2/test_cli.py:163-168` | `_ALWAYS_SKIPPED_IDS` is not literally always: `ACP-CANCEL-204` and `ACP-INFO-CANCEL-202` FAIL (not SKIP) against the three hang fixtures, because an `AgentTimeout` in shared setup is a FAIL. `cancel_no_idle.py:8-11` documents this honestly; the set's name does not. | Rename or add the caveat to the set's comment. |
| 43 | NIT | `scratch/` (this review) | I left a throwaway strict-v2 agent (`scratch/vmcheck/strict_v2.py`) and four artefacts (`scratch/vm.json`, `vm2.json`, `v2full.json`, `pytest-full.log`) under the gitignored `scratch/`. | `rm -rf scratch/vmcheck scratch/vm.json scratch/vm2.json scratch/v2full.json scratch/pytest-full.log`. |

## Decisions recommended

- **`ACP-AUTH-202` vs re-citing v1's `ACP-AUTH-002`: keep `ACP-AUTH-202`; fix the *rationale*, not the id.** The registry's stated reason ("the gate's wire encoding changed boolean → object marker") does not survive contact with its own neighbours: `ACP-PROMPTCAP-001/002/003` reuse v1 ids across exactly the same boolean→object-marker change, and `ACP-SESSION-001/002` reuse v1 ids across a MANDATORY→CAPABILITY tier change that `ACP-PROMPT-205` cites as its reason for *not* reusing `ACP-PROMPT-002`. So the file has two contradictory justifications for structurally identical situations. The *behaviour* is nonetheless coherent under a different rule, which is the one actually implemented: **an area whose method names or capability surface changed wholesale renumbers into the 2xx block as a unit (AUTH, CONFIG, RESUME, LIST, CLOSE, DELETE, ADDDIRS); connection-level rows that are byte-identical to v1 keep their v1 id (INIT-001/003, SCHEMA-001/002, JSONRPC-001..005, TRANSPORT-002, EXT-001, META-001, ERROR-001, SHUTDOWN-001, STDERR-001, INFO-*)**. Renaming `ACP-AUTH-201/202/204/205` → `001/002/003/005` now would churn `requirements.py`, three test modules, `tests/v2/test_cli.py`'s four id sets, `tests/v2/test_registry.py` and `AGENTS.md` for zero behavioural gain, and would leave the AUTH block a mix of `001/002/003/005/203/206/207`, which reads worse in a v2 report than a clean 2xx block. **Action:** write the area-block rule into `.agents/plan.md` as a D3 refinement, and rewrite the two contradictory paragraphs (`requirements.py`'s `ACP-PROMPT-205` "a changed tier is a changed requirement" and `ACP-AUTH-202`'s "changed wire encoding") to cite the area-block rule instead.
- **`ACP-MCP-201/202`: keep INFORMATIONAL.** The source report recommends it explicitly and flags the tier as a judgement call (`acp-v2-session-management.md:505,579-580,718-720`): whether an MCP server was actually connected is *not client-observable in stable v2* (there are no `mcp/*` client methods, `meta.json:16-21`), and M6 ("Agents **SHOULD** connect to all MCP servers") is only a SHOULD (`session-setup.mdx:469`). A CAPABILITY row would have to assert "`session/new` did not error", which a conforming agent may legitimately do because the server is unreachable — the TCK cannot supply a real MCP server. Record the decision in plan.md and close the open item. (Do fix finding 8 first: the probes are currently schema-invalid, so even the recorded datum is not trustworthy.)
- **`ACP-BATCH-206`, `ACP-BATCH-207`, `ACP-BATCH-208`, `ACP-CANCEL-204`: re-tier to INFORMATIONAL, do not drop.** All four are unconditionally SKIPped — `tests/v2/test_cli.py:163-168` encodes them as `_ALWAYS_SKIPPED_IDS`, and the measured `conforming_full.py` run SKIPs exactly them plus four fixture-specific ones. Three of them (`test_batch.py:187-211`) are plain `def`s that never even spawn an agent. The registry's own tier definitions make INFORMATIONAL the honest home ("spec silent / cannot be judged; reported only"): `BATCH-206`/`207` are MAY-level, `BATCH-208` is a property of the *sender* (and the agent side of it is unobservable, since no agent→client method is lifecycle-sensitive), and `CANCEL-204`'s "as soon as possible" has no wire signal. Keeping them preserves spec-inventory traceability, which is worth more than deleting them (v1's Req 10 precedent cuts the other way, but v1 had no INFORMATIONAL tier at the time). `ACP-CANCEL-204` is the best of the four — it drives the real scenario and records `acp_tck_cancel_sent`/`acp_tck_stop_reason` (`test_cancel.py:246-247`) — so while re-tiering it, consider making the other three at least record *something* (e.g. whether any batch line was ever observed from the agent) rather than being inert placeholders.
- **`conforming_full.py`'s three remaining SKIPs (`ACP-AUTH-207`, `ACP-PATCH-206/207`): both deferred nits are cheap; do them.** For **`ACP-AUTH-207`**, the pattern already exists in the repo: `test_authentication.py:111-125` opens a *dedicated* second connection advertising `capabilities: {"auth": {"terminal": {}}}` via `_initialized_agent(..., capabilities=…)` (`:32-54`), while the default handshake (`src/tck/v2/__init__.py:17-25`) sends `capabilities: {}`; and `terminal_env_duplicate_names.py:35-45` already implements the conditional override correctly. Give `conforming_full.py` the same `_initialize_result` override (better: promote it into `_base.py` as an opt-in `terminal_auth_method=` kwarg) that **appends** — not replaces — an entry like `{"methodId": "tck-terminal", "type": "terminal", "name": "Terminal", "args": ["--login"], "env": [{"name": "TCK_TOKEN", "value": "x"}]}` when and only when the client's `initialize` params carried `capabilities.auth.terminal`. Nothing else flips: `ACP-AUTH-202` connects *without* the capability and still sees no terminal entry, `ACP-AUTH-201` (unique `methodId`s) and `ACP-AUTH-206` (`"terminal"` is a defined value) stay green, `--auth-method tck` still resolves for `ACP-AUTH-204`, and `AuthMethodTerminal` requires only `methodId`+`name`, so `ACP-SCHEMA-001` is unaffected. For **`ACP-PATCH-206/207`**, append two updates to `_send_rich_turn_updates` (`_base.py:411-475`), behind the existing `emit_rich_turn_updates` flag: `{"sessionUpdate": "terminal_update", "terminalId": "term-0001", "command": "echo hi", "cwd": <the session's own stored absolute cwd>, "output": {"data": "aGkK"}}` and `{"sessionUpdate": "terminal_output_chunk", "terminalId": "term-0001", "data": "aGkK"}`. Both validate clean through `tck.v2.validation` (`TerminalUpdate` requires only `terminalId`; `TerminalOutputChunk` requires `terminalId`+`data`), both kinds are already in `test_enums.py`'s `_SESSION_UPDATE_KIND`, `_record_history` ignores non-message kinds so replay/`ACP-RESUME-*` are untouched, and the three PATCH defect fixtures override `_send_rich_turn_updates` wholesale so they are unaffected. That takes `conforming_full.py` from 98/106 to 101/106, leaving only the four always-SKIP rows and `ACP-AUTH-205` (which is *about* the empty-`authMethods` case and must SKIP here).
- **Bonus tier question surfaced by the citation audit (not on the deferred list): `ACP-BATCH-201` MANDATORY vs `ACP-BATCH-203` ADVISORY.** Both cite receiver sentences with no RFC-2119 keyword (`transports.mdx:57-59` "An empty array **receives** a single Invalid Request response"; `:73-75` "Invalid entries … produce…"); the MUST at `:57` is on the *sender* ("The batch **MUST** be an array with at least one value"). `ACP-BATCH-202` is different — it has two genuine MUST NOTs (`:66-67`, `:70-72`) — and is correctly MANDATORY. plan.md decided 201 MANDATORY explicitly, so this is a decision to re-confirm rather than a defect; I would keep it MANDATORY (the behaviour is unambiguous and universally implemented) but record in the row text that the RFC-2119 force is on the sender, so the ADVISORY/MANDATORY split with 203 does not look arbitrary.

## Verified OK

**Registry and citations (question 1).** All 106 citations resolve to a real file and line in the
spec @ `8f76d6c`/`b9d6aca`; none is dangling. Every row I opened says what its text claims —
including the ones easiest to get wrong: `ACP-INIT-201`'s two-branch rule (`initialization.mdx:94`),
`ACP-INIT-203`'s `required: ["protocolVersion","info"]` (`schema.json:3086`, `:3121`),
`ACP-INIT-204`'s "every marker is an object" (`migration.mdx:181` + `AgentCapabilities`
`anyOf[$ref, null]`), `ACP-STATE-201/202/203` (`prompt-lifecycle.mdx:159,348,464-481`),
`ACP-PATCH-203`'s distinct-`messageId` MUST (`prompt-lifecycle.mdx:151`, whose full sentence does
contain "Agents **MUST** assign distinct message IDs to distinct inserted submissions"),
`ACP-PATCH-205` (`agent-plan.mdx:71`), `ACP-PATCH-206/207` (`tool-calls.mdx:409,439-440,441-446,469-472`),
`ACP-RESUME-202/203/205` (`session-setup.mdx:144-145,118-119,208-212,221-222`),
`ACP-LIST-202` (`session-list.mdx:145`), `ACP-DELETE-203` (`session-delete.mdx:91`),
`ACP-AUTH-202`/`207` (`$defs/AuthMethodTerminal`: "Agents MUST advertise this method only when the
client enabled its terminal authentication capability" / "Names MUST be unique"),
`ACP-CANCEL-201/202/203/208` (`prompt-lifecycle.mdx:519,526,530`, `session-setup.mdx:258`), and
`ACP-BATCH-201/202` (`transports.mdx:57-59,66-72`). I also independently confirmed the two facts
the whole tiering rests on: `SessionCapabilities`'s property set really is
`{prompt, mcp, delete, additionalDirectories, _meta}` (no list/resume/close marker exists), and
`ClientCapabilities` really is `{auth, elicitation, _meta}`.

**Tiering (question 1).** The plan's rule is applied without exception: every row about a
`capabilities.session` baseline method is `Tier.CAPABILITY` with `capability="capabilities.session"`,
MANDATORY is reserved for `initialize`-level and connection-level rows (INIT-*, SCHEMA-001,
TRANSPORT-*, JSONRPC-001/002/003, BATCH-201/202, EXT-001, AUTH-202/206/207), and ADVISORY rows
that still need a SKIP gate (`ACP-PROMPT-003`, `ACP-PATCH-208/209`, `ACP-ENUM-202/203`,
`ACP-META-201`, `ACP-SCHEMA-002`) carry the capability *marker* on the test while leaving
`Requirement.capability = None` — a documented, consistent pattern that satisfies
`Requirement.__post_init__`'s invariant. `tests/v2/test_registry.py`'s tier cross-check
(added in V2-1c per `review-v2-slices-0-1a` finding 8) keeps the hand-maintained id sets in
`tests/v2/test_cli.py` honest — for two of the four tiers; see finding 17. I checked the other
two by hand and they match today.

**The prompt driver (question 2).** `run_prompt`'s turn-end predicate is exactly the plan's:
`_helpers.py:713-717` accepts an idle for the prompted session iff it carries a `stopReason` **or**
a prior `running` for that session was observed, so the legal "session-ready idle" a conforming
agent may emit after `session/new` can never be mistaken for a turn end. The cancel trigger fires
on the `running` transition (`:776-788`) with a `cancel_wait` fallback, per the cancellation
research. `entry.matches_id` (`common/harness/transcript.py:73-79`) correctly excludes
`method`-bearing messages, so an agent→client request can never be mistaken for the prompt's
response. Every wait bottoms out in `read_line`/`wait_for_message`, both deadline-enforcing
(`common/harness/process.py:300-317`); the only unbounded-in-aggregate paths are findings 21 and
22, and the per-test watchdog backstops both. `login_if_needed` correctly exists because several
modules self-initialize (its absence was a real auth-gate bypass), `skip_if_auth_gated`/`_msg`
only excuse `-32000` when `authMethods` is non-empty and no `--auth-method` was given (v1's AUTH-A1
rule, re-cited as `ACP-AUTH-205`), `skip_if_version_mismatch` emits the exact marker
`common/plugin.py` scans for, and `obtain_resumable_session` implements the three-route strategy
with the `-32601`-is-a-hard-FAIL carve-out the research demands (`_helpers.py:375-385`) — its
problem is that only two tests use it (finding 1). No test pipelines a request behind `initialize`
before its response (every site awaits `wait_for_response` first), honouring the Rust-SDK
constraint.

**Honest SKIPs and the cancel race (question 3).** `_skip_if_cancel_not_exercised`
(`test_cancel.py:83-109`) reproduces v1's two situations faithfully — response-before-cancel, and
a valid non-`cancelled` stop reason inside the race window — with the window derived from
`quiet_period(--timeout)` rather than a constant, and `acp_tck_cancel_race_ms`/`_window_ms`
recorded. Critically, a *missing* `stopReason` is not swallowed by the "not in STOP_REASONS" early
return in a way that hides a defect: it falls through to `ACP-CANCEL-201`'s real assertion. The
turn-scoped SKIP reasons elsewhere ("no foreground work observed", "no turn-ending idle observed",
"no `tool_call_update` observed", "no permission request observed") are accurate and each names
the row that *would* catch the defect. Silence probes use `quiet_period`, never the full
`--timeout`, at every site I checked except the deliberately documented unknown-`sessionId` probe
(`test_informational.py:21-26,114`).

**Must-NOT-assert compliance (question 3).** Against the session-management report's 15 items and
the authentication report's list, the suite is clean except findings 2, 7 and 9: no test asserts a
`-32000` gate implied by non-empty `authMethods`, anything about `error.data`, post-logout session
state, a closed `{"agent","terminal"}` type set, the presence of `authMethods`, that a freshly
created session appears in `session/list`, or that `auth/login` succeeds (failures SKIP). The
patches report's client-application rules are respected: no test asserts create-before-update
ordering, unknown-key error paths, or any client-side merge semantics — only id
presence/uniqueness/stability, absolute `cwd`, `planId`, standalone base64 and the running/idle
ordering. `ACP-STATE-203` is correctly scoped to the idle that terminates an observed `running`
turn; the forbidden unscoped "every idle has a stopReason" check does not exist anywhere.

**`common/` and v1 preservation (question 5).** The whole diff to `common/` since `1d795cc` is:
the `--tck-allow-logout` option + its `_ALLOW_LOGOUT` contextvar, the `VERSION_SPEC_KEY`
`UsageError` guard (review-0-1a finding 11), the version-mismatch branch in `_tck_capability_gate`,
`blocked_by_version_mismatch` threading through `_build_report`/`compute_verdict`/`Verdict`, and
the terminal hint. No `--tck-*` option was renamed or removed; the only new key in the v1 JSON
report is the documented `blocked_by_version_mismatch`; `uv run pytest` is green and the v1
`conforming_full.py` regression still exits 0. The only v2-derived content in `common/` is help
text and a docstring (finding 35) — no v2 wire literal, no import from `tck.v2`. The two v1-derived
literals `review-v2-slices-0-1a` finding 9 flagged (`"authMethods"`, `"initialize"`) now carry
comments recording that they are unchanged in v2.

**Fixtures (question 4).** Every wire shape `_base.py` emits was fed through `tck.v2.validation`
(all clean) *and* checked by hand against the `$defs` it claims to implement — which matters,
because the vendored schema sets `additionalProperties: false` nowhere, so validation alone is
weak evidence. Confirmed correct: `state_update` running / idle(+`stopReason`) / idle(bare) /
`requires_action` (`_base.py:518-528,601,628`); `user_message` echoing the client's own `prompt`
array (`:512-516`, `UserMessage` requires only `messageId`); `agent_message_chunk` (`:420-435,497-504`,
`ContentChunk` requires `messageId` + a *single* `content` block, not an array — the fixture gets
this right); `tool_call_update` create+patch (`:438-456`); `plan_update` (`:459-475`,
`PlanUpdateContent` branch `type: "items"` with required `planId`/`entries`, `PlanEntry` with
required `content`/`priority`/`status`); `auth/login`/`auth/logout` returning `{}` with the
`methodId` checked against the advertised list (`:267-278`); and `conforming_full.py:50-62`'s
`configOptions` entry against `SessionConfigSelect`/`SessionConfigSelectOption`. The
`session/resume` replay is right in both respects the research singles out: updates are `_notify`-ed
**before** `self._reply` (R2 ordering, `_base.py:304-323`) and `_record_history` (`:530-548`)
inserts the R9 whole-message primer (`content: []`) the first time a `*_chunk` `messageId`
appears. Independently, `ACP-SCHEMA-001` and `ACP-SCHEMA-002` PASS over the whole
`initialize` → `session/new` → `session/prompt` exchange, and the prose-derived rows
(`ACP-RESUME-202..205`, `ACP-PATCH-201/203/204/205/208/209`, `ACP-ENUM-201/202/203`) PASS against
it — so the fixture's shapes are corroborated by three independent checks, not just its own
docstrings. The v2 `_base.py` is deliberately dual-version
(`tests/fixtures/agents/v2/_base.py:256-257`: `negotiated = requested if requested in
_SUPPORTED_VERSIONS else PROTOCOL_VERSION`), which is why no existing fixture can exercise the
v1-side version-mismatch path in finding 11.

**Defect fixtures and their self-tests (question 3, last part).** Every defect fixture does trip
the requirement its docstring claims — the problems (findings 15, 16) are all in the *"nothing
else is affected"* half of the claim. An unscoped `--protocol-version 2` run of each `-k`-scoped
self-test's fixture (~45 runs) reproduced the asserted FAIL set **exactly** for about thirty of
them, including every capability fixture (`advertises_delete_but_errors`, `list_errors_when_empty`,
`close_no_cancel_idle`, all three `resume_*`, `config_partial_list`), all five auth fixtures, both
custom-`sessionUpdate` controls, the transport/JSON-RPC negatives mirrored from v1
(`banner_on_stdout`, `invalid_utf8`, `garbage_after_response`, `answers_notifications`,
`result_and_error`, `unknown_method_no_error`, `rejects_batch`), and the negotiation fixtures
(`echoes_any_version`, `v2_only_errors_on_v1`, `missing_info`, `boolean_session_capability`).

**Docs (question 6) that are accurate.** The 106-id count at `AGENTS.md:790`, the CLI option list
in `README.md:32-70` (matches `python -m tck --help` exactly), the `--allow-logout` paragraph at
`AGENTS.md:1602-1613`, the verdict/report key documentation (`README.md:88,119-122`,
`AGENTS.md:1792-1805` — `:1806` itself is finding 11), and the v2 fixture catalogue: all 57 files
in `tests/fixtures/agents/v2/` are named in `AGENTS.md`, with no entries for files that do not
exist (four of those entries inherit their fixture's over-broad "nothing else is affected" claim —
finding 16).

**The `check-*` skills' refresh step (question 6).** The `.agents/state.md` open question is **not
reproducible today**: `git -C … pull --ff-only` succeeded on all three checkouts (spec
`8f76d6c..b9d6aca`, rust-sdk fast-forwarded, python-sdk already current), and the spec checkout's
remote config is clean (`remote.origin.fetch = +refs/heads/*:refs/remotes/origin/*`, one local
branch, `branch.main.merge = refs/heads/main`). So no `SKILL.md` change is needed. If the
orchestrator wants belt-and-braces, the cheapest addition is one sentence to each skill's "Refresh
before research" section: "if `pull --ff-only` fails, run `git fetch origin` and verify
`git rev-list --left-right --count HEAD...origin/main` is `0 0` before proceeding, and report the
pull failure" — but I would not spend a programmer slice on it without a reproduction.

## Open questions

- **Does the harness need batch-aware response matching at all?** `wait_for_response` →
  `matches_id` (`common/harness/process.py:315-317`, `transcript.py:73-79`) only matches a
  top-level object, so an agent that answers an *unbatched* request with a one-element batch array
  is unreachable for every test except `run_prompt` and `test_batch`. `ACP-TRANSPORT-201` permits
  such a line, and `ACP-BATCH-204` is only a SHOULD. Low probability, but it decides whether
  finding 5's `iter_messages` helper should instead be pushed down into the harness. Routed to
  whoever owns V2-8.
- **Should the v2 suite grow a negative control for `ACP-CLIENTCAP-202` via a notification?** Only
  relevant once finding 6 is fixed; there is no fixture today that emits an undefined agent→client
  notification.
- **`--protocol-version 1` against a strict-v2 agent is now a half-implemented path.** Finding 11
  shows `blocked_by_version_mismatch` already fires for v1 runs, but v1's MANDATORY shape rows
  (`ACP-INIT-002`, `ACP-SCHEMA-001`) have no `skip_if_version_mismatch` equivalent and would FAIL.
  plan.md calls the symmetric v1 side "a later slice"; someone should decide whether to finish it
  or to document the mixed behaviour.
- **Cross-check exposure.** Findings 1, 3, 4 and 8 are all most likely to show up first against a
  third-party agent, i.e. in the V2-7 cross-check leg that is in flight in a sibling worktree.
  Whoever merges V2-7 should re-read those four before attributing an unexpected FAIL to the agent
  under test.
