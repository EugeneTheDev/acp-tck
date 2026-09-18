# Review — slice 7 / 7b (`3e55deb`)

**Reviewed at:** commit `3e55deb` ("Record final slice 7b verification in state"), extracted to
`/tmp/acp-tck-review2` via `git archive`. All `file:line` references below are relative to the
repo root at that commit. No file in the live tree was modified.

**Scope:** new/changed since `e5fc479` — `src/tck/conformance/{test_client_capabilities,
test_extensibility,test_diagnostics,test_informational,_helpers,test_authentication,
test_initialize,test_jsonrpc,test_cancel,test_session_capabilities,test_session_config}.py`,
`src/tck/validation.py` (`find_unknown_root_keys`), `src/tck/plugin.py`, `src/tck/report.py`,
`src/tck/harness/process.py` (`close_grace`), `src/tck/requirements.py` (all 56 entries),
`tests/fixtures/agents/_base.py`, `tests/test_cli.py`. Plus release readiness for v0.1.

**Verification performed in the /tmp copy only:**

- `uv run pytest -q` → **125 passed in 117 s** (matches `state.md`'s claim). `--durations=15`
  collected for the runtime section.
- `uv build` → wheel inspected (40 entries).
- Wheel installed into a clean `uv venv -p 3.14`; `acp-tck` run against a copied fixture agent.
- `--collect-only`, `-k`-scoped, and zero-match runs: exit codes measured.
- `find_unknown_root_keys` exercised over every `$def` the two method maps resolve to.
- Four purpose-built throwaway agents in `/tmp` (non-exiting, SIGTERM-ignoring, exits-on-bad-JSON)
  to probe the close ladder, the watchdog, and the INFORMATIONAL probes.

**Counts:** 1 blocker, 9 should-fix, 10 nits.

---

## Blockers

### B1. `pyproject.toml` is not publishable, and the README tells users to `uvx acp-tck`

`pyproject.toml:4` — `description = "Add your description here"`. There is also no `license`
(and no `LICENSE`/`COPYING` file anywhere in the tree), no `classifiers`, no
`[project.urls]`, no `authors`, no `keywords`.

Measured wheel metadata (`acp_tck-0.1.0.dist-info/METADATA`):

```
Metadata-Version: 2.3
Name: acp-tck
Version: 0.1.0
Summary: Add your description here
Requires-Dist: jsonschema==4.26.0
Requires-Dist: pytest==9.1.1
Requires-Python: >=3.14
```

Why this is a blocker rather than a nit: `README.md:22-26` documents the primary install path as
`uvx acp-tck -- <agent command>`, which only works once the package is on PyPI. Shipping v0.1
with `Summary: Add your description here` is the single most visible thing a first external user
sees (it is the PyPI card and the `pip show` summary), and publishing with no license at all
means nobody can legally use the TCK to certify their agent — the entire point of the artifact.
`requires-python = ">=3.14"` is also worth a deliberate decision rather than an inherited default:
it excludes every currently-common interpreter, and nothing in the source obviously needs 3.14.

Fix: set a real `description`; add `license = "…"` (+ a `LICENSE` file, which `uv_build` will
then include); add `classifiers` (at minimum `Development Status`, `Intended Audience`,
`Topic :: Software Development :: Testing`, `Programming Language :: Python :: 3.14`) and
`[project.urls] Homepage/Repository/Issues`; confirm or lower `requires-python`.

**Otherwise packaging is sound** (see "Checked and sound"): the wheel carries
`tck/schema/v1/{schema.json,meta.json,VENDORED.md}` and all 14 `tck/conformance/test_*.py`
modules plus `conftest.py`, and leaks nothing from `tests/` — verified by installing it into a
clean 3.14 venv and running a real `-k initialize` conformance pass from outside the repo.

---

## Should-fix

### S1. An agent that dies on malformed input turns the "always PASSes" ACP-INFO-PARSE-001 into a FAIL with a raw asyncio traceback

`src/tck/conformance/test_informational.py:21-30` (`_probe_connection_usable_after`) and
`src/tck/harness/process.py:163-182` (`send_raw`).

`send_raw` guards only `asyncio.TimeoutError` around `drain()`. When the agent has already
exited, `stdin.write()`/`drain()` raise `ConnectionResetError` / `BrokenPipeError` (plain
`OSError`), which nothing in the probe path catches — `_probe_connection_usable_after` catches
only `(AssertionError, AgentTimeout, AgentExited)`.

Reproduced with a 15-line agent that `sys.exit(3)`s on a non-JSON line (exactly what the task
asked about for Python-SDK-shaped agents that die on invalid input):

```
  ACP-INFO-INVALIDREQ-001 PASS  (silent; conn after: usable (sessionId='s1'))
  ACP-INFO-PARSE-001   FAIL
  ACP-INFO-UNKNOWNSESSION-001 PASS  (replied with error code -32601)

>           raise ConnectionResetError('Connection lost')
E           ConnectionResetError: Connection lost
/…/asyncio/streams.py:166: ConnectionResetError
```

This contradicts `requirements.py:806-822` ("Always PASSes"), `README.md:81-82` ("so it always
reports `PASS`"), and the module docstring at `test_informational.py:1-9` ("none of these ever
fail"). It also produces exactly the failure class review-slices-1-4 N14 / 5-6 N21 were about:
a bare Python exception instead of a diagnosis.

Fix (preferred, fixes the whole class): in `send_raw`, wrap the write+drain in
`except OSError as exc: raise AgentExited(..., exit_code=self._process.returncode, stderr=…,
transcript=…)`. The three probes and `_probe_connection_usable_after` then already handle it.
Secondarily, add `OSError` to `_probe_connection_usable_after`'s except clause and record
`behaviour = "agent exited"` rather than letting the outcome be a FAIL.

### S2. The two INFORMATIONAL probes wait a full `--timeout` for silence — 60 s of dead wall-clock on every real run, and a guaranteed FAIL at `--timeout >= 120`

`src/tck/conformance/test_informational.py:49` and `:88` use
`read_line(timeout=agent_launch.default_timeout)` to conclude "silent".

The Python reference SDK **silently drops** both a malformed line and a non-envelope object
(`acp-v1-transport-and-jsonrpc.md:124-125`, Discrepancy 2), so "silent" is the *normal* outcome
for a large fraction of real agents. The transport report's own instruction is explicit
(`acp-v1-transport-and-jsonrpc.md:235`): *"a v1 TCK **must not fail** an agent for skipping, and
must be prepared for no response at all (so this test needs its **own short timeout** and a 'no
reply' outcome bucket, **not a hang**)."* The code uses the full per-response deadline instead.

Measured against `conforming.py` (which skips malformed lines) at the default `--timeout 30`:

```
$ acp-tck -k informational -- python tests/fixtures/agents/conforming.py
  ACP-INFO-INVALIDREQ-001 PASS  (silent; …)
  ACP-INFO-PARSE-001   PASS  (silent; …)
3 passed, 53 deselected in 60.16s
```

And the full default-timeout run against `conforming_full.py` is **72.4 s**, i.e. ~83 % of a real
run's wall-clock is these two probes idling. Worse, a user who raises `--timeout` to cope with a
slow agent crosses the `--tck-test-timeout` default of 120 s (`plugin.py:102-112`) and the probe
is then killed by the watchdog and reported FAIL — an "always PASSes" requirement failing purely
because of a harness-policy interaction.

Fix: use `quiet_period(agent_launch.default_timeout)` (already the suite's documented
"conclude absence" primitive, `_helpers.py:133-140`) for the silence read in both probes, and
keep `default_timeout` only for the `initialize` and follow-up `session/new` reads. That is both
the research's instruction and a ~58 s saving per run.

### S3. `close()` burns the grace period twice before it ever checks whether the process died — ~4 s of teardown per process for an npx/uvx-wrapped agent

`src/tck/harness/process.py:336-337`:

```python
await self._drain_remaining_stdout(grace)
exited_on_stdin_close = await self._wait(proc, grace)
```

`_drain_remaining_stdout` returns early on stdout EOF, so a well-behaved agent costs nothing.
But for an agent that keeps stdout open after stdin EOF — the documented `npx`/`uvx` wrapper case
the class docstring itself calls out (`process.py:93-95`, and rust-sdk's rationale quoted at
`acp-v1-transport-and-jsonrpc.md:197`) — the drain burns the **full** grace, and only then does
`_wait` burn another, before SIGTERM is even sent.

Measured with a non-exiting agent, one test (two processes: the session-scoped
`agent_initialize_result` fixture + the test's own):

```
--close-grace default (2.0):  1 passed, 55 deselected in 8.26s
--close-grace 0.2:            1 passed, 55 deselected in 1.06s
```

≈4 s per process. The suite spawns ~60 agent processes, so a real agent that does not exit on
stdin EOF pays roughly **4 minutes of pure teardown**, with no diagnostic value beyond the single
ADVISORY `ACP-SHUTDOWN-001` bit.

Secondary correctness point: because the drain runs first, `exited_on_stdin_close` is really
"exited within ~2×grace", so `ACP-SHUTDOWN-001` is twice as lenient as `--tck-close-grace`'s help
text ("Grace period … budgeted at each stage") implies.

Fix: race the two — e.g. `asyncio.wait({drain_task, wait_task}, timeout=grace,
return_when=FIRST_COMPLETED)` — or drain with a short fixed deadline (`min(grace, 0.25)`; it only
needs to pick up bytes already in the pipe) and give the full `grace` to `proc.wait()` alone.
Either way `exited_on_stdin_close` then means what it says.

### S4. Review 5-6 S7 (the `-k` deselection hint) is only half-implemented — the hint is hidden exactly when the run looks most plausible

`src/tck/plugin.py:718-734`. The deselection hint is nested inside
`if mandatory[Status.PASS.value] == 0 and (n_fail + n_not_tested) > 0:`, so it only prints when
*no* MANDATORY requirement passed. Review 5-6 S7's requested fix was the opposite: print it
"when `config.getoption("keyword")`/`-m`/`--deselect` was used", and *suppress* the
"agent may have failed to start" hint when tests ran and nothing mandatory passed.

Measured (`-k initialize` against `conforming.py`):

```
  MANDATORY      PASS=4, FAIL=0, SKIPPED=0, NOT_TESTED=19
VERDICT: NOT CONFORMANT (0 mandatory failures, 19 not tested)
                                  ← no hint at all
```

A user who scopes a run to debug one area — the documented use of `-k`
(`README.md:52`, `__init__.py:78`) — gets "NOT CONFORMANT, 19 not tested" with nothing telling
them it is the selection talking. `tests/test_cli.py` still works around this in five docstrings
(":309", ":326-328", ":486-488", ":626-629", ":702-707"), which is precisely the signal S7
identified. `state.md:39-40` claims all 5-6 should-fix items are addressed; this one is not.

Fix: hoist the `keyword or markexpr` branch out of the `mandatory[PASS] == 0` guard — print it
whenever a selector was given **and** `n_not_tested > 0`, and keep the "agent may have failed to
start" branch for the unscoped `mandatory[PASS] == 0` case only.

### S5. `ACP-AUTH-001` is MANDATORY but its only real assertion is `AUTH-A5`, which the cited research classifies as **advisory**

`src/tck/requirements.py:591-607`; test at
`src/tck/conformance/test_authentication.py:20-37`.

The registry text says the test "adds the id-uniqueness check that schema validation alone does
not express", and the citation is `(AUTH-M1, AUTH-M2)`. But AUTH-M1/M2 are *shape* assertions
("is a JSON array"; "every element has a string `id`/`name`") — and the test explicitly defers
shape to ACP-SCHEMA-001, so the only thing it actually asserts beyond `isinstance(list)` is
uniqueness. Uniqueness is `AUTH-A5` in the same research table, filed under **Advisory**, with
the reason stated (`acp-v1-authentication.md:305`):

> | AUTH-A5 | Advertised auth-method `id`s are unique within `authMethods` | the schema only
> *describes* `id` as "Unique identifier" (`schema/v1/schema.json:2740`); **no MUST** |

So an agent with duplicate auth-method ids is forced to `NOT CONFORMANT` on the strength of a
schema *description*. This is exactly the "MANDATORY entry whose citation is only SHOULD/MAY"
pattern.

Fix: either (a) retier `ACP-AUTH-001` to ADVISORY and re-cite it `AUTH-A5`, or (b) keep it
MANDATORY but make it actually assert AUTH-M1/M2 (array-ness, and `id`/`name` being non-empty
strings) and move uniqueness into a separate ADVISORY id. (a) is the smaller change and matches
the research verbatim.

### S6. `ACP-EXT-001` is MANDATORY on the basis of a tier the two vendored research reports disagree about

`src/tck/requirements.py:719-734`; test at `test_extensibility.py:16-31`.

`acp-v1-protocol-surface.md:365-366` does say `_`-prefixed "requests must be answered (with a
result or `-32601`)" (Req 42, MUST). But `acp-v1-transport-and-jsonrpc.md:35` tiers the *same
observable* — a request naming a method the recipient does not recognise — as **SHOULD** (J6,
"spec wording is 'should'"), and its Testability note 5 (`:225`) says to tier it as SHOULD.

The suite now takes both positions about the *identical wire event*: for `_tck/does_not_exist`,
`ACP-JSONRPC-004` (`test_jsonrpc.py:89-92`) **skips** on silence because "replying is only
SHOULD"; for `_tck/unknown`, `ACP-EXT-001` **fails** on silence and drags the verdict to NOT
CONFORMANT. The registry acknowledges this as a "judgment call", but a MANDATORY tier is the one
place a judgment call has a hard cost for a third-party agent author.

Confidence: medium — a plausible reading is that Req 42's MUST covers custom requests the
recipient *implements*, while an unrecognised `_` method falls under J6's SHOULD, which would
make MANDATORY wrong. Fix: resolve it against the spec text once (`extensibility.mdx:43,52,65,
109` vs `:80-92`) and record the resolution in *both* reports; if it stays MANDATORY, add the
cross-reference to `acp-v1-transport-and-jsonrpc.md` so the next reader does not find two
reports contradicting each other.

### S7. `ACP-JSONRPC-005` fails (advisory) against an agent that legally never replies to an unknown method

`src/tck/conformance/test_jsonrpc.py:133-138`:

```python
bad_id = await agent.send_request("_tck/does_not_exist")
await agent.wait_for_response(bad_id, timeout=agent_launch.default_timeout)
session_id = await new_session(...)
```

Replying to an unrecognised method is only SHOULD (J6), and the sibling test three functions up
handles that correctly by skipping. Here the unguarded `wait_for_response` raises `AgentTimeout`,
which is folded to FAIL — even though the requirement being tested ("the connection remains
usable after an erroneous request") is fully checkable without a reply, and the silent agent has
in fact *demonstrated* the property.

Also costs a full `--timeout` of dead wall-clock in that case.

Fix: `with contextlib.suppress(AgentTimeout): await agent.wait_for_response(bad_id,
timeout=quiet_period(...))`, then proceed to the `new_session` check (which is the actual
assertion).

### S8. The `ACP-CLIENTCAP-002/003` probes use an fs-flavoured prompt, so their PASS is vacuous by construction, not by accident

`src/tck/conformance/test_client_capabilities.py:31`:

```python
_PROMPT_TEXT = "Read the file README.md in the current directory and summarize it."
```

All three tests share `_methods_called_with_no_client_capabilities`, so `terminal/*` and
`elicitation/create` are probed with a prompt that invites *file* access, in a `tmp_path` cwd
that contains no `README.md`. The module docstring is upfront that PASS may be vacuous, and
Reqs 29/30/32 are genuinely MUST NOTs that do not require the agent to try — but as written the
two non-fs tests have close to zero chance of provoking the behaviour they guard, while still
costing a full extra agent process and prompt turn each (3 processes, 3 turns).

Fix: give each test its own capability-shaped prompt text (e.g. "run `ls -la` in a shell and show
me the output" for terminal; "ask me which of two options I'd prefer before continuing" for
elicitation), or — if the vacuity is accepted — collapse the three into one prompt turn whose
`client_requests_seen` is filtered three ways and bind the three requirement ids to three
assertions over that one turn (which is cheaper and loses nothing, since per-id attribution comes
from the filters, not from separate turns).

### S9. `ACP-AUTH-003` is tiered MANDATORY for an assertion the research files as capability-conditional

`src/tck/requirements.py:622-643`. The entry's own text opens with *"Capability-conditional
(AUTH-C4)"*, and `acp-v1-authentication.md:293` lists AUTH-C4 under **Capability-conditional**,
not Mandatory. It is nonetheless `Tier.MANDATORY, capability=None`.

The practical effect today is benign (the test SKIPs without `--tck-auth-method`, and SKIPPED does
not break the MANDATORY verdict), so this is a classification/reporting defect rather than a false
FAIL: it shows up under `[MANDATORY]` in the terminal table and in
`verdict.tier_counts["MANDATORY"]`, misrepresenting how many unconditional requirements the run
covered.

Fix: use the same encoding `ACP-MODES-001`/`ACP-CONFIG-001` already use for exactly this problem
(`Tier.CAPABILITY` + a documentation-only `capability="inferred:…"` string, `requirements.py:460`,
`:498`) — e.g. `capability="inferred:authMethods+--tck-auth-method"` — or state in the entry's
text why it is deliberately MANDATORY despite the citation, so the contradiction inside a single
`Requirement` is not left for a reader to resolve.

---

## Nits

### N1. README's Options list omits `--close-grace`

`README.md:33-53` lists every CLI flag except `--close-grace`, which exists
(`__init__.py:62-70`) and is documented in `AGENTS.md:250`. A first external user reading only the
README cannot discover the one knob that fixes S3's teardown cost.

### N2. README overstates the INFORMATIONAL contract

`README.md:81-82` ("The test never asserts on the probed behaviour itself (so it always reports
`PASS`)") and the four registry texts (`requirements.py:815`, `:831`, `:846`, `:801`) are
falsified by S1 and by the plain dead-agent case. Measured against `exits_immediately.py`:

```
INFORMATIONAL  PASS=0, FAIL=0, SKIPPED=0, NOT_TESTED=0 → FAIL=4
```

All four INFORMATIONAL requirements FAIL when `initialize` fails. That is defensible (the
verdict is unaffected), but the documentation should say "never asserts on the probed behaviour;
still reports FAIL if the prerequisite handshake itself fails" rather than "always PASSes".

### N3. README mis-tiers the extensibility family

`README.md:115` calls it "an `ADVISORY`/`INFORMATIONAL` extensibility and hygiene family covering
unknown custom methods, …" — but `ACP-EXT-001` (unknown custom methods) is MANDATORY
(`requirements.py:722`) and is the only member with verdict weight.

### N4. `ACP-SCHEMA-002` is ADVISORY for a MUST NOT, and the text justifies it on testability grounds

`requirements.py:778-793`. Req 41 is a MUST NOT (`acp-v1-protocol-surface.md:86`). The stated
reason for ADVISORY is that the vendored schema has no `additionalProperties: false`, i.e. a
*testability* fact, not a tier fact. The hedge is defensible (the walker is a permissive
union, so a false positive on an unknown agent would be worse than a missed detection), but the
entry should say *that* — "downgraded to ADVISORY because the check is a hand-written
approximation and a false positive would be unrecoverable" — rather than implying the tier
follows from the schema's shape. I verified the approximation is currently exact for the vendored
schema (see "Checked and sound"), so the downgrade is conservative, not wrong.

### N5. `_allowed_root_properties` drops sibling keywords next to a `$ref`

`src/tck/validation.py:334-341` returns immediately after following a `$ref`, ignoring any
`properties`/`allOf` sibling on the same node. JSON Schema 2020-12 allows those siblings, and if
a future re-vendor introduces one, this silently *narrows* the allowed set and produces false
positives for `ACP-SCHEMA-002`.

I verified this cannot bite today: a full walk of `schema/v1/schema.json` found **zero** nodes
carrying `$ref` alongside any keyword other than `description`/`title`/`x-method`/`x-side`.

Fix (cheap): after recursing into the `$ref` target, fall through to the sibling handling instead
of `return`ing.

### N6. `_allowed_root_properties` is not memoised

`validation.py:315-356` re-parses the composition on every emitted message, while its siblings
(`_def_validator`, `_request_and_notification_method_defs`, `_response_method_defs`) are all
`lru_cache`d. Add `@lru_cache(maxsize=None)`.

### N7. `ACP-EXT-001` reports a harness exception instead of its own requirement message on silence

`test_extensibility.py:26-31`. An agent that never answers `_tck/unknown` fails with
`AgentTimeout: no matching message within 30s` rather than the carefully worded
"a `_`-prefixed custom method request must receive a response (Req 42)". Since this is the one
MANDATORY assertion in the module (see S6), catching `(AgentTimeout, AgentExited)` and
`pytest.fail(..., pytrace=False)` with the Req-42 wording would make the finding self-explaining.

### N8. `ACP-JSONRPC-001`'s docstring describes behaviour the test does not have

`test_jsonrpc.py:33-34` claims the string-id half "uses `session/new` (via `new_session`, which
SKIPs -- not crashes -- on an auth-gated agent)". The body (`:44-48`) hand-rolls `send_request`
and never calls `new_session`/`skip_if_auth_gated`. Harmless (id echo holds for a `-32000` reply
too) but the docstring should not claim a guard that is absent.

### N9. Review 5-6's N12 and N20 are still open

- `tests/test_report.py:63-75` still constructs a `TestOutcome(status=FAIL, message="AgentExited: …")`
  and asserts its own inputs — no production code runs. This is the one self-test in scope that
  passes trivially (`state.md:76` lists it as a deliberate deferral).
- `src/tck/conformance/_helpers.py:300` and `test_session_capabilities.py:168` still call
  `agent.transcript.index(entry)` per dispatched line (O(n²), identity-by-equality).

Both are acknowledged deferrals in `state.md`, so this is a status note, not a new finding.

### N10. `tests/test_cli.py`'s tier sets are hand-maintained with no meta-test

`tests/test_cli.py:26-89`. I verified all four sets currently match `REGISTRY` exactly
(MANDATORY 23 / CAPABILITY 18 / ADVISORY 11 / INFORMATIONAL 4 = 56). Only the *union* is
guarded (`:211`, `:584`), so a new requirement filed into the wrong set would still pass CI while
silently dropping it from `test_exits_immediately_fails_gracefully`'s MANDATORY loop. Derive the
four sets from `REGISTRY` by tier, or add a meta-test asserting the match.

### N11. Requirement count and two citations drift from the code

- `.agents/state.md:43` and `.agents/plan.md:49` both say **57 requirements**; the registry has
  **56** (`len(REGISTRY)`, verified).
- `ACP-CONFIG-003` (`requirements.py:539-543`) cites only
  `schema/v1/schema.json:2975-3399`, while the normative MUST NOT lives at
  `docs/protocol/v1/session-config-options.mdx:119-121` (`acp-v1-protocol-surface.md:78`).
- `ACP-AUTH-002` (`requirements.py:617-619`) cites only `schema/v1/schema.json:2736-2782`, while
  AUTH-M4's normative text is `docs/protocol/v1/authentication.mdx:126-128`
  (`acp-v1-authentication.md:284`).

(`spec-drift-check.md` already queues three other citation fixes for slice 8; fold these in.)

### N12. Terminal table column breaks for the long `ACP-INFO-*` ids

`plugin.py:695` uses `{req_id:<20}`, but `ACP-INFO-UNKNOWNSESSION-001` is 27 chars and
`ACP-INFO-INVALIDREQ-001` is 23, so those rows lose alignment:

```
  ACP-SHUTDOWN-001     NOT TESTED
  ACP-INFO-INVALIDREQ-001 NOT TESTED
```

Cosmetic only — `_table_statuses`'s regex (`tests/test_cli.py:151`) still parses them, verified.
Widen to `{req_id:<28}`.

### N13. `test_unknown_session_id_behaviour` can mis-record a permission-asking agent as "silent"

`test_informational.py:124-133` uses bare `wait_for_response`, which has no mock client. An agent
that issues `session/request_permission` while handling the bogus-session prompt will never be
answered, and the probe records `behaviour = "silent"` after burning a full `--timeout`. Bounded,
never wrong in the conformance sense (the requirement never asserts), but the recorded note is
misleading. Either route it through `run_prompt` or record "no response within Ns (agent had
N outstanding client requests)".

---

## Checked and sound (do not re-litigate)

**Tier correctness (all 56 entries cross-checked against the cited research).** Every MANDATORY
entry other than `ACP-AUTH-001` (S5), `ACP-AUTH-003` (S9), and `ACP-EXT-001` (S6) rests on a
genuine MUST/MUST NOT in the cited report: TRANSPORT-001/002 (T5/T7, T1), JSONRPC-001/002/003
(J3, J1, J2), INIT-001/002/003 (Reqs 3, 5), SCHEMA-001, SESSION-001/002 (Req 9),
PROMPT-001/002 (Reqs 24, 1), CANCEL-001/002 (Reqs 25/26, 28), CONFIG-003 (Req 33),
AUTH-002 (AUTH-M4), CLIENTCAP-001/002/003 (Reqs 29, 30, 32). No ADVISORY entry hides a MUST
except the deliberate, documented `ACP-SCHEMA-002` downgrade (N4). `ACP-JSONRPC-004`
(J6 SHOULD), `ACP-JSONRPC-005` (explicitly labelled "de-facto rule inferred from reference-SDK
regression tests"), `ACP-INIT-004` (Req 4 SHOULD), `ACP-PROMPT-003` (documented Discrepancy 2),
`ACP-LOAD-003`/`ACP-DELETE-002` (D2 SHOULD), `ACP-META-001` (Req 43 SHOULD), `ACP-ERROR-001`
(E3 SHOULD), `ACP-SHUTDOWN-001` (Testability note 11, "report as a warning, not a failure"),
and `ACP-AUTH-005` (AUTH-A1, explicitly Advisory at `acp-v1-authentication.md:301`) are all
correctly ADVISORY. All 18 CAPABILITY entries carry a `capability` path; the
`inferred:modes`/`inferred:configOptions` documentation-only encoding is documented at both the
registry and test-module level. `Requirement.__post_init__`'s capability↔tier invariant plus the
two-way registry↔marker meta-tests (`tests/test_registry.py:93-102`) hold.

**`find_unknown_root_keys` (SCHEMA-002) has no false positives on the vendored schema.** I dumped
the resolved allowed-set for every `$def` both method maps produce (24 defs). Unions are handled
permissively in the right direction (`elicitation/create` resolves to the full cross-variant
union, so no variant is wrongly rejected); `$ref` chains resolve; `_meta` is always allowed; the
free-form `additionalProperties: true` objects (`_meta`, `rawInput`/`rawOutput`) are all *nested*,
never at a checked root, so they are never walked. The `found_any_properties → None` escape hatch
is a genuine safety valve but almost never fires in practice, because the empty-ish responses
(`AuthenticateResponse`, `LogoutResponse`, `CloseSessionResponse`, `DeleteSessionResponse`,
`SetSessionModeResponse`) still declare `_meta` as a real property and therefore resolve to
`['_meta']` — i.e. a stray root key in an "empty" result *is* caught. Extension (`_*`) methods are
skipped at both the test and the validation layer.

**Verdict / exit code.** Measured: `--collect-only` → exit **0** with "no test executed in this
run" and no verdict line (S6 of the prior review is genuinely fixed, including the
`ran_any_test` guard that `exitstatus in (OK, TESTS_FAILED)` alone would have missed); a zero-match
`-k` → pytest's own **5**, untouched; a scoped run with failures → **1**. `compute_verdict`'s
four-status model, the `blocked_by_auth` force-to-false, and the MANDATORY-`NOT_TESTED`-counts-as-
failure rule all match `README.md:95-101`.

**Transcript cap.** `_TRANSCRIPT_MAX_ENTRIES = 400` / `half = 200` / `entries[:200] + marker +
entries[-200:]` is correct: no overlap, no off-by-one (the cap only engages at ≥401 entries, so
`gap ≥ 1`), and `_truncate_raw`'s byte-boundary slice is safe via `errors="replace"`.

**`_table_statuses` after the N13 fix is not trivially satisfied.** The regex genuinely parses
`NOT TESTED` (two words) and rows carrying a trailing `(note)` suffix — I confirmed both against
live output, including the long `ACP-INFO-*` ids. The two full-coverage self-tests now compare
against `_ALL_IDS | _INFORMATIONAL_IDS` explicitly, and
`test_noisy_stderr_and_parse_error_reply_agent_informational_notes` asserts a *specific* recorded
note ("replied -32700 with id:null", non-zero stderr bytes), so the INFORMATIONAL note plumbing
is covered by a real assertion, not by always-PASS scaffolding.

**Auth gating after 7b.** `skip_if_auth_gated` (`_helpers.py:76-108`) fires only when *all* of:
the response is `-32000`, no `--tck-auth-method` was given, **and** the cached `initialize`
advertised at least one `authMethods` entry (5-6 S4 correctly followed through). An agent with
non-empty `authMethods` that does **not** gate is entirely unaffected — verified end-to-end:
`conforming_full.py` (advertises `authMethods`, never gates) is CONFORMANT with only
`ACP-AUTH-005` SKIPPED. An agent that gates but whose `authenticate` fails is SKIPped, not
FAILed, with a distinct reason (must-NOT #10 respected, 5-6 S5 followed through). The
`AUTH-GATED:` marker survives `str(report.longrepr)` and reaches `Verdict.blocked_by_auth`
(substring match is *required* here, since longrepr prefixes the file/line — the docstring's
"prefixed" refers to the skip reason, which is accurate).

**No remaining hang path found.** Every wait is bounded: `read_line`/`wait_for_message`
(explicit deadlines), `send_raw`'s `drain()` (`default_timeout`), `run_prompt`'s
`overall_deadline`, `_drain_remaining_stdout` (deadline loop), `_read_raw_line`'s `max_total`
defensive cap, and the 120 s `--tck-test-timeout` watchdog on top. I specifically checked whether
the watchdog's cancellation skips `close()`'s SIGTERM/SIGKILL ladder and leaves an orphan: it does
**not**. With a SIGTERM-ignoring, never-exiting agent and `--test-timeout 1`, the ladder ran to
SIGKILL and `pgrep` found zero survivors afterwards (Python delivers `CancelledError` once, so
the `__aexit__` awaits complete normally). `close()` is also idempotent via `_closed`.

**Runtime.** Self-test suite: 125 passed in 117 s; slowest are `wrong_id_echo` (7.6 s),
`conforming_full` (7.1 s), `asks_permission` (5.3 s) — all already `-k`-scoped or justified per
5-6 S11. The `--tck-close-grace` plumbing (CLI → plugin → `AgentLaunch` → `__aexit__`) works and
is exercised by `test_per_test_watchdog_fails_a_hung_test_fast`. Real-run hot spots are S2 and S3,
not the self-tests.

**Fixtures.** `_base.py`'s tightened strictness (`_content_block_error` on every prompt block,
`methodId` validated against advertised `authMethods`, unknown-`sessionId` → `-32602`,
`_visible_config_options` honouring Req 33 with an `ignore_boolean_gating` escape for the defect
fixture) is real strictness, not theatre — 5-6 S9 followed through. `SendsClientRequestAgent`
gives the three CLIENTCAP defect fixtures one shared, correct mid-turn-client-request shape.
`asks_permission_closable.py` exercises both branches of `run_prompt`'s permission-answering
logic, including the `outcome: "cancelled"` branch that was dead before (5-6 S10a).

**Other prior-review follow-through confirmed in code:** B1 (AUTH-001 no longer sends a second
`initialize`), B2 (INIT-003 is `!= 65535 and >= latest_supported`, not equality — and
`supports_v1_and_v2.py` exists as the regression fixture), S3 (`ACP-CLOSE-002` now drives
`run_prompt`'s `on_action` hook, no hand-rolled loop), S8 (per-entry 4 kB + 400-entry transcript
caps), N14 (`pytest.raises((AgentTimeout, AgentExited))` at all three quiet-period sites),
N15 (CANCEL-002 and CLOSE-002 defer the success-shape finding to their sibling requirement),
N16 (MODES-002 records rather than asserts the mode value), N21 (CONFIG-002's `isinstance` guard),
N22 (`str(value)` coercion at the single collection point), N23 (`xfail` is a `UsageError`),
N25 (explicit `client_capabilities={}` in CONFIG-003).

**`acp-tck --help` vs README:** every flag in `--help` appears in the README with matching
defaults, except `--close-grace` (N1). `--version` and the no-command usage error (exit 2) behave
as README states.
