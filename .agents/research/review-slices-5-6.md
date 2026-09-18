# Review — slices 5–6 (reporting/verdict, session capabilities, modes/config, prompt caps, auth)

Read-only review at commit `e5fc479`, extracted with `git archive e5fc479 | tar -x -C
/tmp/acp-tck-review`; every experiment below was run in that copy, never in the live tree.
Scope: `src/tck/{report,plugin,requirements}.py`,
`src/tck/conformance/{_helpers,test_initialize,test_session_capabilities,test_session_config,test_prompt_capabilities,test_authentication,test_cancel}.py`,
`tests/fixtures/agents/{_base,conforming_full,gated_by_auth}.py`, `tests/test_cli.py`,
`tests/test_report.py`. Baseline in the /tmp copy: `113 passed, 1 skipped in 94.55s`.

Counts: **2 blockers, 9 should-fix, 14 nits**.

All line numbers are as of `e5fc479`.

---

## Blockers

### B1. `ACP-AUTH-001` sends a second `initialize` on an already-initialized connection → MANDATORY false FAIL
`src/tck/conformance/test_authentication.py:25-27`.

`connected_agent(agent_launch)` defaults to `handshake=True`, so it already performed
`initialize` (`_helpers.py:41-53`) — and with `--auth-method`, `authenticate` as well. The test
then sends **another** `initialize` and requires a `result` object. ACP says `initialize` "must be
the first method called"; nothing in v1 blesses a repeat, and the TCK's own stance is that the
client must not put traffic of unspecified validity on the agent's stdin
(`acp-v1-transport-and-jsonrpc.md` T8, the same argument that produced the `_tck/`-prefixed
probes in review S3). Every sibling test in the module correctly uses `handshake=False`
(`:44`, `:70`).

Verified in the /tmp copy with a fixture that rejects a second `initialize` with `-32600`
(`Once(ConformingAgent)`):

```
E  AssertionError: initialize did not succeed:
   '{"jsonrpc":"2.0","id":2,"error":{"code":-32600,"message":"already initialized"}}'
  ACP-AUTH-001         FAIL
VERDICT: NOT CONFORMANT (1 mandatory failures, 18 not tested)
```

Note `id:2` — proof the TCK itself sent the second handshake.

Fix: read the cached probe instead of connecting at all
(`request.getfixturevalue("agent_initialize_result").result`, which is exactly an
`initialize(protocolVersion=1, clientCapabilities={})` result), or at minimum switch to
`connected_agent(..., handshake=False)`. The cached-probe form also removes one process spawn per
run.

Secondary site, same defect, lower impact: `test_jsonrpc.py:31-37` sends `initialize` twice (once
with an integer id, once with a string id) to prove id echo. That one survives an agent that
answers the repeat with an error (any reply satisfies the assertion) — measured PASS against the
same strict fixture — but it FAILs an agent that simply ignores a second `initialize`. Use one
`initialize` plus a second request that MUST be answered (e.g. `session/new` via `new_session`,
which already SKIPs when auth-gated) for the string-id half.

### B2. `ACP-INIT-003`'s equality check FAILs any agent that supports a version above 1
`src/tck/conformance/test_initialize.py:95-98`; requirement text `requirements.py:156-173`.

The test takes `latest_supported` = the `protocolVersion` returned for a `protocolVersion: 1`
request and then asserts `version == latest_supported` for the 65535 request. Req 5
(`acp-v1-protocol-surface.md` Req 5 / `initialization.mdx:96`) says: **echo** the requested
version if supported, **otherwise return the agent's own latest**. For a dual v1+v2 agent the two
answers are legitimately *different* (`1` for the v1 request, `2` for 65535), so the equality
identifies "the agent's latest" with "its answer to v1" — true only for v1-only agents.

The cited research asked for something weaker: "assert `result.protocolVersion <= max(1, that)`
and, minimally, `!= 65535`" (`testy-cross-check.md` Testability note 1). The implementation is
stricter than its own source, and the same report's open questions explicitly anticipate
dual-version agents (`testy --features unstable_protocol_v2`).

Verified in the /tmp copy with a fixture returning `1` for v1 and `2` otherwise:

```
>  assert version == latest_supported, (
   ACP-INIT-003 FAIL
```

Fix: `assert version != 65535` and `assert version >= latest_supported` (i.e. the answer to an
unsupported request is at least the version it admits supporting), with the failure text
explaining both halves. That still FAILs `testy`/`echo_agent.py` (which echo 65535), which was the
whole point of the strengthening.

---

## Should-fix

### S3. `ACP-CLOSE-002` drives a prompt turn with no mock client — review S4, reintroduced
`src/tck/conformance/test_session_capabilities.py:299-361`.

The hand-rolled loop reads lines and dispatches only three cases: the prompt response, the close
response, and `session/update`. An agent→client **request** — `session/request_permission` (the
normal case, `prompt-turn.mdx:32-43`) or any `fs/*`/`terminal/*` call — is read and silently
dropped: never answered, not even with `-32601`. A conforming permission-asking agent therefore
never resolves the turn, the loop hits `AgentTimeout`, and a CAPABILITY requirement FAILs. This is
exactly the defect review S4 fixed everywhere else by routing turns through `run_prompt`; the new
slice-6 test reintroduced it in a private copy of the loop. (`asks_permission.py` exists as a
fixture but the CLI self-test for `conforming_full.py` never exercises this path against it, so
nothing catches the regression.)

Fix: extract `run_prompt`'s `_handle_one` mock-client dispatch (`_helpers.py:211-254`) into a
reusable helper and give `run_prompt` an "action on first update" hook (send `session/cancel`
*or* a `session/close` request), then express CLOSE-002 in terms of it. As a bonus that also gives
CLOSE-002 the honest `cancel_race_peek` logic it currently lacks.

### S4. `skip_if_auth_gated` excuses any `-32000`, even from an agent that advertises no auth methods
`src/tck/conformance/_helpers.py:65-88`; consumed at `plugin.py:501-502`.

The predicate is "error code == -32000 and no `--auth-method`" — it never consults `authMethods`.
Consequences: an agent that uses `-32000` as a generic failure code, or that gates `session/new`
while advertising **no** way to authenticate, is SKIPPED on every session-dependent MANDATORY
requirement and the report attributes the whole run to "blocked by authentication" instead of
naming the defect. The auth research calls exactly that shape a defect:
"an agent that advertises none and then returns `-32000` has made the connection unusable with no
defined remedy. Treat as a **defect finding, advisory tier**" (`acp-v1-authentication.md` §5, and
assertion **AUTH-A1**). AUTH-A1 is currently implemented by nothing — there is no registry id for
it.

Fix: consult the cached `initialize` result. If `authMethods` is non-empty → SKIP as today. If it
is absent/empty → do not skip; record the AUTH-A1 advisory (new ADVISORY requirement, e.g.
`ACP-AUTH-005`) and let the ordinary assertion FAIL, so the report blames the agent rather than
the operator's missing flag.

### S5. The auth flow asserts that `authenticate` *succeeds* — an explicit "must NOT assert"
`src/tck/conformance/_helpers.py:56-61` (`connected_agent`) and
`src/tck/conformance/test_authentication.py:81-86` (ACP-AUTH-003).

`acp-v1-authentication.md` "Assertions that must NOT be written" #10: *"`authenticate` succeeds.
A real agent may legitimately fail (bad credentials, user cancelled, network). Only the shape of
a success is assertable (AUTH-C3)."* AUTH-C3 is worded "**If** `authenticate` returns a result,
the result is a JSON object".

Today a legitimate credential failure (or a mistyped `--auth-method`) makes
`connected_agent`'s `assert` fire in the **setup path of every session-dependent test**, so one
operator/credential problem is recorded as a FAIL against ACP-SCHEMA-001, ACP-SESSION-00x,
ACP-PROMPT-00x, ACP-CANCEL-00x, ACP-LOAD-00x … each with the message "authenticate … did not
succeed". That is both a false conformance verdict and an unreadable report.

Fix: in `connected_agent`, on an `authenticate` **error** response, `pytest.skip` with a distinct
marker (e.g. `"AUTH-FAILED: authenticate with methodId=… returned <error>; check
--auth-method"`), surfaced in the verdict the same way `blocked_by_auth` is (a run that could not
authenticate cannot be scored conformant either). In ACP-AUTH-003, assert the *shape* when a
result comes back, and skip-with-reason when an error comes back; keep the hard assertion only for
AUTH-C4 (`session/new` must not answer `-32000` *after* a successful `authenticate`).

### S6. `--collect-only` (and any run that executed nothing) is overridden to exit 1 / "NOT CONFORMANT"
`src/tck/plugin.py:539-552`, contradicting its own module docstring (`:9-12`) and
`AGENTS.md:216-217` ("`--collect-only`, usage errors, and interrupted runs keep pytest's own exit
code").

`--collect-only` finishes with `ExitCode.OK`, which **is** in the guarded tuple, so the override
fires. Measured in the /tmp copy:

```
$ pytest src/tck/conformance -p tck.plugin --collect-only -q --tck-agent-cmd "python .../conforming.py"
  MANDATORY      PASS=0, FAIL=0, SKIPPED=0, NOT_TESTED=19
VERDICT: NOT CONFORMANT (0 mandatory failures, 19 not tested)
hint: no MANDATORY requirement passed -- the agent may have failed to start or never responded...
exit=1
```

(Not reachable through the `acp-tck` CLI, which rejects the flag — but the plugin is documented as
usable directly via `-p tck.plugin`, and the docstring makes a promise it does not keep.)

Fix: add `and not config.getoption("collectonly", False)` and, more robustly, require that at
least one test actually produced a record (`any(state.status is not None for state in states)`
or `session.testscollected and not session.config.option.collectonly`). Consider also leaving the
exit code alone when nothing ran, instead of inventing a verdict.

### S7. A `-k`-scoped run prints a verdict + a hint that blames the agent for deselection
`src/tck/plugin.py:586-601`; `-k` is a documented, first-class CLI option (`README.md:51`,
`AGENTS.md:207`).

Measured (`-k test_id_is_echoed…` against `never_responds.py`):

```
VERDICT: NOT CONFORMANT (1 mandatory failures, 18 not tested)
hint: no MANDATORY requirement passed -- the agent may have failed to start or never responded;
      check --agent-cwd/--timeout/--startup-timeout ...
```

The 18 `NOT TESTED` are deselected tests, not agent behaviour, and nothing in the output says so.
`tests/test_cli.py` works around this in four docstrings ("the overall exit code is *not* asserted
here… a `-k`-scoped run necessarily leaves every other MANDATORY requirement NOT_TESTED"), which
is precisely the signal that the tool should say it itself.

Fix: when `config.getoption("keyword")`/`-m`/`--deselect` was used, or when
`session.testscollected` is less than the number of collected-then-deselected items, print
"`N` requirement(s) are NOT TESTED because their tests were deselected (`-k <expr>`); a scoped run
cannot produce a conformance verdict" and suppress the "agent may have failed to start" hint
(which should only fire when tests *ran* and nothing mandatory passed).

### S8. The JSON report's transcript is unbounded while stderr is capped
`src/tck/plugin.py:389-397` (`_transcript_entries_dict`) vs `:377-386` (`_truncate_stderr`).

The harness deliberately never truncates or drops an oversize stdout line (review B1 fix;
`AGENTS.md:344`, `max_line_bytes` = 64 MiB) and bounds stderr to the last 64 kB. The report then
copies **every** transcript entry verbatim into the JSON for every FAIL outcome, so one agent that
emits a multi-MB `session/update` (an image block, a tool-call diff) produces a report that is
orders of magnitude larger than the 20 kB stderr the same code carefully trims. `Report.to_dict`
is also the thing `json.dumps(..., indent=2)`-ed in memory at `plugin.py:546`.

Fix: cap each entry's `raw` (e.g. 4 kB with a `...[truncated N bytes]...` marker, mirroring
`_STDERR_TRUNCATE_MARKER`) and cap entry count (first/last N with a gap marker), then document the
cap next to the stderr cap in `AGENTS.md:314-318` / `README.md:64-68`.

### S9. Fixture leniency hides whether the TCK's own requests have the right shape
`tests/fixtures/agents/_base.py:216-218` (`_handle_authenticate`), `:206-214`
(`_handle_set_config_option`), `:224-243` (`_handle_prompt`); `gated_by_auth.py:1-9`.

`_handle_authenticate` ignores `params` entirely — any `methodId`, or none at all, authenticates.
So nothing in the self-test suite proves the TCK sends the schema-**required** `methodId`
(`acp-v1-authentication.md` Req 5, AUTH-C5); `gated_by_auth.py`'s docstring even claims it
requires "that methodId", which is not what `_base` does. Likewise `_handle_prompt` never looks at
non-text content blocks, so `ACP-PROMPTCAP-001/002/003` PASS regardless of whether the TCK's
`image`/`audio`/`resource` blocks are schema-valid (§8 of the capabilities research is the only
thing keeping `test_prompt_capabilities.py:53-56,72-75,94-102` honest — no test checks it), and
`_handle_set_config_option` ignores `type`, so the boolean-variant request shape (O1:
`{"type":"boolean","value":<bool>}`) is unverified.

Fix (cheapest first): have `_base` reject requests whose params are structurally wrong for the
method (`-32602`) for at least `authenticate` (`methodId` required) and `session/prompt` (each
block validated against the `ContentBlock` `$def`); systematically, implement the plan's open
question "`validate_client_message`" and assert in the self-tests that the TCK's own outgoing
traffic validates. Fix `gated_by_auth.py`'s docstring either way.

### S10. Two mock-client branches every prompt/cancel test depends on are still dead in the self-tests
`src/tck/conformance/_helpers.py:227-250`; review N17 was only half-fixed.

`asks_permission.py` exercises the permission path, but it answers the prompt as soon as the client
answers the permission request, so in the cancel tests `run_prompt` always answers
`{"outcome":"selected"}` and then loses the race — `test_cli.py:246-247` asserts the cancel ids are
SKIPPED, confirming the `{"outcome":"cancelled"}` branch (`_helpers.py:230`) never runs. And no
fixture anywhere sends `fs/*`/`terminal/*`/`elicitation/create`, so the `-32601`
`client_requests_seen` branch (`:240-250`) is still entirely dead — and `client_requests_seen`
itself has no consumer in `src/` or `tests/` at all (grep), even though the module docstring
promises slice 6 negative tests built on it.

Fix: add (a) a fixture that holds its permission request open until `session/cancel` arrives (so
the client answers `cancelled` and the prompt resolves `cancelled`), and (b) a fixture that calls
`fs/read_text_file` mid-turn against a client that advertised `clientCapabilities: {}`, plus an
assertion over `client_requests_seen` so the field stops being write-only.

### S11. Runtime: ~40 % of the 95 s suite is two tests, both cheaply fixable
Measured in the /tmp copy (`pytest -q --durations=20`):

```
29.04s tests/test_cli.py::test_wrong_id_echo_fails_id_dependent_requirements
 9.52s tests/test_cli.py::test_per_test_watchdog_fails_a_hung_test_fast
 4.72s tests/test_cli.py::test_conforming_full_agent_passes_everything_with_cancel_prompt_hang
 4.52s tests/test_harness.py::test_never_responds_raises_agent_timeout_with_transcript
 3.43s tests/test_cli.py::test_cancel_wrong_stop_reason_fails_cancel_001_only
~1.8s  × 14 other unscoped CLI runs
```

1. `test_wrong_id_echo_fails_id_dependent_requirements` (`tests/test_cli.py:252-259`) does a full
   unscoped run in which *every* correlated read times out at `--timeout 1`/`--startup-timeout 1`
   across 43 tests — and asserts exactly one id (`ACP-JSONRPC-001 == FAIL`). Passing
   `timeout="0.2", startup_timeout="0.2"` (the fixture answers instantly, just with the wrong id)
   or scoping with `k="jsonrpc"` cuts ~25 s with no loss of signal.
2. `test_per_test_watchdog_fails_a_hung_test_fast` (`:449-464`) spends ~9 of its 9.5 s in two
   `close()` ladders against `never_responds.py` (measured: the CLI run itself reports
   `1 failed, 42 deselected in 9.37s` while the watchdog is 0.3 s). `process.py:308-347` spends
   `grace=2.0` draining stdout, `2.0` waiting, then SIGTERM + `min(grace,1.0)` draining again. The
   drain only needs to collect bytes already buffered; a much shorter drain window (0.1–0.25 s, or
   `grace/10`) keeps review S8's guarantee and saves ~7 s here plus a little in every other
   hung-agent test.
3. Structural win for later: the 16 unscoped CLI runs each pay ~0.6 s pytest start plus ~30 agent
   spawns. Reusing the cached `agent_initialize_result` in the tests that only need an
   `initialize` result (ACP-AUTH-001 — see B1 — ACP-AUTH-002, ACP-INIT-004, and INIT-003's
   "reference" process) removes 3–4 process spawns per CLI run, i.e. a few seconds across the
   suite.

---

## Nits

### N12. `test_report.py:63-75` passes trivially
`test_a_setup_or_teardown_error_is_reported_as_fail_with_the_exception_text` constructs a
`TestOutcome(status=FAIL, message="AgentExited: …")` and then asserts that its `status` is FAIL and
its `message` contains "AgentExited". No production code runs; the documented behaviour it claims
to "lock in" (`plugin._phase_status` folding a teardown failure into the test's status) is never
touched. Move it to `tests/test_plugin.py` as a `pytester` run with a fixture whose teardown
raises, asserting the recorded status/message.

### N13. `_table_statuses` silently drops `NOT TESTED` rows
`tests/test_cli.py:126-133` only records lines with exactly two tokens; the terminal label is
`NOT TESTED` (two words, `plugin.py:572`), so such ids vanish from the parsed dict rather than
being recorded. `assert set(statuses) == _ALL_IDS` catches it in the two full-coverage tests, but
every `statuses.get(x) == "PASS"` loop elsewhere relies on `None != "PASS"` rather than on seeing
the real status. Join the tail tokens (`" ".join(parts[1:])`) and normalize to `NOT_TESTED`.

### N14. Quiet-period assertions accept only `AgentTimeout`
`test_session_capabilities.py:93-96` (LOAD-002), `test_cancel.py:141-144` (CANCEL-002),
`test_session_config.py:134-139` (MODES-002, via `except AgentTimeout`). If the agent reaches EOF
during the quiet period the harness raises `AgentExited` (`process.py:254-260`), so an agent that
exits promptly turns a PASS into a FAIL. Use `pytest.raises((AgentTimeout, AgentExited))` /
`except (AgentTimeout, AgentExited)`.

### N15. CANCEL-002 and CLOSE-002 still assert another requirement's content
`test_cancel.py:126-128` ("cancel must resolve the prompt with a success result") is ACP-CANCEL-001
(Reqs 25/26); `test_session_capabilities.py:390-398` asserts the same for CLOSE-002 *and* then
re-asserts `stopReason == "cancelled"` after the race check. Milder than review S5 (the tests are
about the same event), but it means an error-shaped cancel response is reported as an *ordering*
violation too. Consider `pytest.skip("prerequisite not met: …")` or a bare early return with the
message pointing at the sibling requirement.

### N16. MODES-002 asserts the *value* of a notification the spec does not require
`test_session_config.py:147-150`. The research pins only the field **name** (`currentModeId`, docs
bug confirmed) and explicitly lists "a client-driven mode change is echoed as a notification" under
must-NOT #16. An agent that emits `current_mode_update` and then autonomously switches again inside
the quiet period FAILs a CAPABILITY requirement for conforming behaviour. Assert the field name,
record the value via `record_property`.

### N17. CONFIG-002 uses subset where the research says set equality
`test_session_config.py:226-229` asserts `original_ids <= returned_ids`;
`acp-v1-session-capabilities.md` Testability says "id set **equals** the previously advertised id
set". Subset is the better reading (O2's own rationale is "so Agents can reflect dependent
changes", which may add options), so this is intentional-and-right — but add a one-line comment
saying so, or the next reader "fixes" it into equality and breaks conforming agents.

### N18. `blocked_by_auth` detection is a substring match; the docs say prefix
`plugin.py:491,501` uses `_AUTH_GATED_MARKER in state.message`; `AGENTS.md:324-325` says "a message
**starting** `AUTH-GATED:`". The message is `str(report.longrepr)`, which for a skip is
`(path, lineno, "Skipped: <reason>")` — so `startswith` would not work as written either. Prefer an
explicit signal (`record_property("acp_tck_auth_gated", "1")` or a dedicated stash key) over
string sniffing, and make the docs match.

### N19. `README.md:84-88` contradicts `compute_verdict` (and itself)
"a requirement no test ever ran is `NOT_TESTED` — deliberately counted as a failure for
`MANDATORY`/`CAPABILITY` tiers" — but `report.py:177-182` counts only `MANDATORY` `NOT_TESTED`, as
`README.md:89-93` and `AGENTS.md:322-326` correctly state four lines later. Drop "`/CAPABILITY`".

### N20. `transcript.index(entry)` is O(n²) and identity-by-equality
`_helpers.py:221` (per dispatched line) and `test_session_capabilities.py:167`. `TranscriptEntry`
carries a monotonic timestamp so equal-value collisions are improbable, but a chatty turn makes
this quadratic and the index is already known to the harness. Have `read_line`/`_record` return or
expose the index.

### N21. CONFIG-002 can still produce a Python traceback instead of a diagnosis
`test_session_config.py:196` does `{option["id"] for option in config_options}` without the
`isinstance(option, dict) and "id" in option` guard CONFIG-001 applies at `:168` — the review-N14
class of failure, in a test that runs independently of CONFIG-001.

### N22. `TestOutcome.properties` is typed `dict[str, str]` but `record_property` accepts any scalar
`report.py:70`, `plugin.py:449-450`. Every call site formats a string today
(`test_cancel.py:62-64`, `test_session_capabilities.py:381-383`), so this is only a typing lie —
but a future `record_property("x", {...})` would silently break `json.dumps`. Either coerce with
`str(value)` at the collection point or widen the type and assert JSON-scalar-ness.

### N23. xfail/xpass behaviour is undocumented and untested
`_phase_status` (`plugin.py:428-437`) maps an xfail to `SKIPPED` (`report.skipped` is true) and a
non-strict xpass to `PASS`; a strict xfail-pass lands as `FAIL`. Nothing in `report.py`'s model
docstring or `AGENTS.md` says so, and no test covers it. Either document it or add a registry
meta-test forbidding `xfail` in the conformance suite (the cleaner option — a conformance suite has
no business with expected failures).

### N24. ACP-AUTH-003 asserts more than AUTH-C4
`test_authentication.py:93-98` requires `session/new` to fully succeed after `authenticate`;
AUTH-C4 only forbids a `-32000`. An unrelated `-32603` is then reported against ACP-AUTH-003 as
well as ACP-SESSION-001. Narrow to "no `-32000`" (and let SESSION-001 own general `session/new`
health), or widen the requirement text to say it deliberately re-checks session creation.

### N25. `test_session_config.py:242` passes `client_capabilities={}`, which is already the default
Harmless, and the surrounding docstring explains the intent (CONFIG-003 must connect *without*
`session.configOptions.boolean`) — but as written the argument looks load-bearing while changing
nothing. Keep the comment, drop the argument, or annotate it as deliberately explicit.

---

## Previous review (`review-slices-1-4.md`) — follow-through

| Item | State | Evidence at `e5fc479` |
|---|---|---|
| **B1** oversize line crashes harness | **fixed** | `process.py:73,118` pass `limit=self._launch.max_line_bytes` (64 MiB default); `_read_raw_line` returns `(raw, oversize)` and records losslessly (`:209-239,262`); `AGENTS.md:344` documents "never truncated or dropped, only flagged" |
| **S2** TRANSPORT-002 false positive | **fixed** | two tests over one transcript (`test_transport.py:44-45,56-57`); negative control `invalid_utf8.py` + `tests/test_cli.py:217-224`; banner test now asserts TRANSPORT-002 `PASS` (`:201-214`) |
| **S3** JSONRPC-002 evidence / probe naming | **fixed** | evidence from `initialize` + an invalid-params `session/new` (`test_jsonrpc.py:47-60`, docstring states the rationale); probes renamed `_tck/does_not_exist` (`:74,120`) |
| **S4** prompt turns without a mock client | **partial** | `test_transport.py:26-41` and SCHEMA-001 (`test_initialize.py:139-147`) now go through `run_prompt`; **but** the new `ACP-CLOSE-002` reintroduces a hand-rolled loop with no client dispatch — see S3 above |
| **S5** CANCEL-002 asserting sessionId attribution | **fixed** | loop deleted; `test_cancel.py:129-131` documents why (mild residue in N15) |
| **S6** capability marker encodings / dead agent | **fixed** | `capability_is_supported(..., boolean=)` implements both (`plugin.py:306-320`); every marker call site passes `boolean=True` for `loadSession`/`promptCapabilities.*`; init failure now `pytest.fail`s rather than skipping (`:331-335`) |
| **S7** `drain()` deadline + per-test watchdog | **fixed** | `asyncio.wait_for(stdin.drain(), …)` (`process.py:167`); `--tck-test-timeout` watchdog (`plugin.py:185-204`), covered by `tests/test_cli.py:449-464` |
| **S8** `close()` never drains stdout | **fixed** | `_drain_remaining_stdout` called three times in the ladder (`process.py:328,335,339`); `garbage_after_response.py` + `tests/test_cli.py:227-235` |
| **S9** hard-coded quiet periods | **partial** | `quiet_period()`/`cancel_race_peek()` derive from `--tck-timeout` (`_helpers.py:113-128`) and the requirement texts say so (`requirements.py:104-113,276-287`); still hard-coded: `run_prompt(cancel_wait=0.5)` (`_helpers.py:159`) and CLOSE-002's `cancel_wait = 0.5` (`test_session_capabilities.py:309`). Defensible (they gate *when to act*, not a verdict) but the second is a copy of the first |
| **S10** fixture swallows only two exception types / teardown never recorded | **fixed** | `except (AgentTimeout, AgentExited, OSError)` (`plugin.py:282`); `pytest_runtest_makereport` no longer filters on `report.when`, and `_phase_status` folds any phase (`:428-459`), so a teardown failure now worsens the recorded status |
| **N11** positional `anyOf` branch | **fixed** | content-based selection with a comment citing N11 (`validation.py:117-124`) |
| **N12** over-claiming docstring | not re-checked in scope (outside slice 5/6 files) |
| **N13** INIT-002 message | **fixed** | `test_initialize.py:49-52` ("agent does not support protocol v1") |
| **N14** raw `KeyError`/`TypeError` on error responses | **fixed** (mostly) | guards throughout (`_helpers.new_session:105-109`, `test_initialize.py:45,73,110`); residue at `test_session_config.py:196` → N21 |
| **N15** `run_prompt` ignores `pending()` | **fixed** | `_helpers.py:256-263` drains `pending()` through the same dispatch |
| **N16** JSONRPC-003 detector required `id` | **fixed** | `"method" not in parsed` predicate with a comment citing N16 (`test_jsonrpc.py:104-108`) |
| **N17** permission / `-32601` branches unexercised | **partial** | `asks_permission.py` added (covers the "selected" branch); the `cancelled` branch and the whole `fs/*`/`terminal/*` `-32601` branch are still dead — see S10 |
| **N18** `AgentTimeout` without stderr | **fixed** | `stderr=self.stderr_text()` at every raise site (`process.py:252,259,287`) and in `run_prompt` (`_helpers.py:269-273`) |
| **N19** unbounded stderr | **fixed** | bounded to the last 64 kB with a truncation marker (`AGENTS.md:368`) |
| **N20** unbounded `wait()` after SIGKILL | **fixed** | `asyncio.wait_for(proc.wait(), timeout=grace)` (`process.py:340-341`) |

---

## Checked and found sound (do not re-litigate)

- **Verdict aggregation.** `aggregate_status` (FAIL > PASS > SKIPPED > none→NOT_TESTED,
  `report.py:116-123`) and the per-nodeid phase fold (`plugin.py:451-459`) do the right thing for
  the awkward cases: a requirement with both a SKIPPED and a FAIL record aggregates to FAIL
  (`tests/test_report.py:46-50`); setup errors, harness `AgentExited`/`AgentTimeout`, and teardown
  failures all land as FAIL with the exception text; `call` FAIL + `teardown` FAIL concatenates
  both messages instead of dropping one.
- **Verdict rule.** `MANDATORY` FAIL/NOT_TESTED, `CAPABILITY` FAIL, and `blocked_by_auth` are the
  only inputs; `CAPABILITY` SKIPPED/NOT_TESTED and every `ADVISORY`/`INFORMATIONAL` status are
  verdict-inert — matches `AGENTS.md:319-326` and is covered by `tests/test_report.py:126-184`.
  A `MANDATORY` requirement that SKIPs for a legitimate reason (ACP-AUTH-003 without
  `--auth-method`) correctly does not break the verdict.
- **Exit-code interplay with `-x`/interrupts.** `-x` raises `Session.Failed` → `TESTS_FAILED`, so
  the override applies and yields 1 (the truncated run leaves mandatory NOT_TESTED anyway);
  `KeyboardInterrupt`/`exit()` → `INTERRUPTED`, which is outside the guarded tuple and left alone.
  Only `--collect-only` slips through (S6).
- **JSON serializability.** Every value reaching `to_dict()` is a JSON scalar/list/dict:
  `agent_command` is `shlex.split` output (no `Path`), transcript `raw` is text or a
  `<undecodable: …>` placeholder (never `bytes`), timestamps and durations are plain floats,
  `agent_info`/`agent_capabilities` come straight from parsed agent JSON. Round-trip covered
  (`tests/test_report.py:223-229`) and exercised end-to-end by four `--report-json` CLI tests.
- **Capability paths and encodings.** Every marker matches the research's two encodings:
  `boolean=True` for `agentCapabilities.loadSession` and `promptCapabilities.{image,audio,embeddedContext}`;
  presence-and-non-null for `sessionCapabilities.{list,delete,resume,close,additionalDirectories}`
  and `auth.logout`. `_lookup_capability` treats a missing segment exactly like an explicit `null`
  (C4). The gate is evaluated against a probe that sends the same `clientCapabilities: {}` the
  tests use, so capability answers cannot drift between probe and test.
- **Inferred gates.** MODES/CONFIG tests do their own `session/new` and skip on
  `modes`/`configOptions` absent, with the documentation-only `capability="inferred:…"` string kept
  out of the plugin's lookup path (`test_session_config.py:1-18`) — the smallest change that keeps
  `Requirement.__post_init__`'s invariant. `if not config_options` (CONFIG-002) correctly also skips
  the empty-list case, per §0's "non-null, non-empty".
- **Staying inside the "must NOT assert" lists.** Spot-checked against
  `acp-v1-session-capabilities.md` items 1–20 and `acp-v1-authentication.md` items 1–12: no test
  asserts an error code for an unknown `sessionId`, load/close behaviour on unknown sessions,
  replay kinds/counts/fidelity (LOAD-002 asserts ordering only), any `session/list` ordering or
  that a new session is listable, rejection of unadvertised content types or MCP transports, MCP
  connection timing, `-32000` gating from non-empty `authMethods`, post-`logout` session state, or
  `AuthMethod.type ∈ {agent, terminal}` (AUTH-002 filters `type == "terminal"` only). RESUME-002 is
  correctly narrowed to the three history kinds in the pre-response window
  (`test_session_capabilities.py:150,170-182`). LOAD-003 and DELETE-002 are ADVISORY, matching the
  `{}`-vs-`null` doc history and D2's SHOULD tier. CONFIG-003 is the genuine client-controlled
  MUST NOT (O5) and is MANDATORY.
- **CLOSE-002's race handling** (modulo S3's missing mock client): SKIP — never PASS, never FAIL —
  when the close could not be sent, or when a valid non-`cancelled` stop reason arrives inside
  `quiet_period` of the close; no assertion about the relative order of the close and prompt
  responses (must-NOT #8); the observed window is recorded via `record_property`.
- **Cancel SKIP/FAIL split** (`test_cancel.py:42-68`) still matches the plan, including the honest
  `cancelled_at_index=None` peek, and an invalid stop reason is judged rather than excused.
- **`conforming_full.py` correctness.** `session/list`'s `cwd` filter is exact-match on the
  stored `session/new` `cwd` (S2) and returns `[]` on no match (S5), so LIST-002 is a real check;
  `session/load` replays stored `agent_message_chunk` history *before* replying `{}` (L2/L3/L4) and
  upserts an unknown id (legal, testy-like); `session/resume` deliberately replays nothing (R2);
  `session/close` resolves an in-flight prompt with `stopReason: "cancelled"` before its own `{}`
  (X2/X3); `session/delete` pops with a default (D2); `set_config_option` returns the full
  `_visible_config_options()` list with the new value applied (O2), and the boolean option is
  filtered out for a client that did not advertise the marker (O5) — which is what lets the same
  fixture satisfy both CONFIG-002 and CONFIG-003. `initialize` always answers `1` regardless of the
  requested version, so it is a valid positive fixture for INIT-002/003.
- **Defect-fixture targeting.** Each slice-6 fixture trips exactly the requirement its self-test
  names (`load_replays_after_response` → LOAD-002 only, `resume_replays_history` → RESUME-002 only,
  `load_returns_null` → LOAD-003 only, `mode_update_uses_modeId` → MODES-002 only,
  `config_partial_list` → CONFIG-002 only, `boolean_option_unadvertised` → CONFIG-003,
  `terminal_auth_unadvertised` → AUTH-002, `advertises_load_but_errors` → LOAD-001 + verdict,
  `echoes_any_version` → INIT-003 with INIT-002 still PASSing). The `gated_by_auth.py` pair of
  self-tests covers both `--auth-method` branches, including `verdict.blocked_by_auth` in the JSON.
- **Registry hygiene.** `Requirement.__post_init__` enforces `capability` iff `CAPABILITY`;
  `pytest_collection_modifyitems` rejects unknown marker ids as a `UsageError`; both meta-tests in
  `tests/test_registry.py` still hold at 43 ids; every citation carries the pinned spec revision via
  `_cite`/`SCHEMA_REVISION`.
