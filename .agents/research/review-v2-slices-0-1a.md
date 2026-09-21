# Review: v2 slices V2-0, V2-0b, V2-1a (`589e334..1d795cc` on `v2-support`)

**Sources checked:**
- this repo @ `1d795cc` (worktree `/Users/eugene/Documents/JetBrains/projects/acp-tck-2`, branch `v2-support`; `.agents/state.md` has uncommitted orchestrator edits, ignored)
- spec repo `/Users/eugene/Documents/JetBrains/projects/agent-client-protocol` @ `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e` (read-only: `git show`)
- `.agents/plan.md` (v2 parts 1–2 and the per-topic decision sections), `.agents/research/common-v1-v2-split-analysis.md` §5, `.agents/research/acp-v2-*.md`
- runs performed: `uv run pytest` (160 passed), `uv run acp-tck --cancel-prompt __hang__ --auth-method tck --report-json scratch/v1.json -- python tests/fixtures/agents/v1/conforming_full.py` (exit 0, CONFORMANT), `uv run acp-tck --protocol-version 2 … -- tests/fixtures/agents/v2/conforming.py` (+ two throwaway defect agents under gitignored `scratch/v2fix/`), `uv build --wheel`, `python -m tck --help`

**Confidence:** high — every claim below is backed by a file:line I opened, a `git show` diff against the spec commit, or a command I ran in this worktree. Lower confidence only on the ownership question in finding 6 (whether V2-1b already owns the missing v2 defect fixtures).

## Summary

The three slices are in good shape: the `common`/`v1` split is genuinely mechanical, v1's observable
behaviour is preserved (same 56 requirement ids, same tiers, same terminal table, same JSON report
keys, exit 0 / CONFORMANT, and the only requirement-text/citation changes are the four documented
ones), and the vendored v2 schema is byte-identical to `schema/v2/{schema,meta}.json` @ `8f76d6c`.
`common/` is effectively version-agnostic: the dotted `capability` gate works unchanged for a v2
`capabilities.…` path, the `initialize` handshake shape now comes from `VersionSpec`, and the only
remaining v1-derived wire literals in `common/` (`"authMethods"`, `"initialize"`) happen to be
correct for v2 as well. Both v2 requirements are genuinely falsifiable — I confirmed with throwaway
defect agents that an echo-any-version agent FAILs `ACP-INIT-201` and a missing-`info` agent FAILs
`ACP-INIT-001` — and both registry citations say what the cited spec lines actually say. The real
gaps are coverage and robustness rather than correctness: there are no v2 negative-control fixtures
in the repo, the new `agent_info_field`/`agent_capabilities_field` rename mechanism and the v2 tier
sets have no test, two v2 helpers raise `TypeError` on unhashable agent-supplied values (violating
the validator's documented "never raises" contract), the open-`other` carve-out is wider than
intended, and a handful of docs — including one user-facing README command that no longer works —
are stale. No blockers.

## Findings

| # | Severity | File:line | Finding | Suggested fix |
|---|----------|-----------|---------|---------------|
| 1 | SHOULD-FIX | `README.md:19` | The documented quick-start command is stale after the `git mv`: `uv run acp-tck -- python tests/fixtures/agents/conforming.py`. I ran it — the agent never starts, and the run reports `VERDICT: NOT CONFORMANT (21 mandatory failures)`. `AGENTS.md:414` was updated to `agents/v1/conforming.py`; README was missed. | Insert `/v1`: `tests/fixtures/agents/v1/conforming.py`. |
| 2 | SHOULD-FIX | `AGENTS.md:873-875`, `AGENTS.md:840`, `AGENTS.md:817`, `src/tck/v1/protocol.py:17` | Four "v2 doesn't exist yet" statements survive in the contributor guide and in code, contradicting the shipped `src/tck/v2/` and `AGENTS.md:13-20`: "Only ACP **v1** is implemented today (`src/tck/v1/`) … so a future v2 effort can add `src/tck/v2/`"; "a *future* `tck.v2.validation` is its own module"; "future protocol version vendors its own schema under its own package (e.g. `src/tck/v2/schema/`)"; "`tck.v2` (once it exists)". | Rewrite each to the present tense; the Conventions bullet should state "v1 is the default and complete suite; v2 (Draft) is a skeleton behind `--protocol-version 2`". |
| 3 | SHOULD-FIX | `src/tck/v2/protocol.py:139-143`, `AGENTS.md:207-210` | Factually wrong rationale for `KNOWN_METHODS`: both say v2 needs it because "v2's top-level schema has a third, bidirectional/side-agnostic `ProtocolLevel` branch v1 does not [have]". v1's schema has exactly the same three top-level branches (`Agent`/`Client`/`ProtocolLevel`, verified by parsing `src/tck/v1/schema/schema.json`), v1's `meta.json:22-24` has the same `protocolMethods`, and `src/tck/v1/protocol.py:120` already defines `PROTOCOL_METHODS`. Only the `KNOWN_METHODS` convenience union is new. Misleading, in the one place a reader checks before a schema refresh. | Reword: "v1 has the same three branches and the same `PROTOCOL_METHODS`; `KNOWN_METHODS` is a new convenience union v1 never needed." |
| 4 | SHOULD-FIX | `src/tck/v2/protocol.py:68`, `src/tck/v2/validation.py:423` | Both raise on an unhashable agent-supplied value, because a `value in frozenset`/`not in set` test is done before any type check. Verified: `is_valid_open_enum_value([], STOP_REASONS)` → `TypeError: cannot use 'list' as a set element`; `find_unknown_root_keys("AuthMethod", {"type": ["x"], "bogus": 1})` → same. This breaks the contract `AGENTS.md:839` states for this module family ("never raises, always returns issues") and the harness principle that nothing an agent writes may crash the TCK. A defective agent emitting `{"stopReason": {}}` or `{"sessionUpdate": []}` is precisely what these checks exist to catch. Latent today (neither helper is wired into a v2 test), but V2-2/V2-6 will wire both. | `is_valid_open_enum_value`: test `isinstance(value, str)` first, then `value in defined or value.startswith("_")`. `_matches_open_fallback_branch`: guard the discriminator with `isinstance(..., str)` before the set test. |
| 5 | SHOULD-FIX | `src/tck/v2/validation.py:405-423` | The open-`other` carve-out is broader than "legitimately using the open fallback". `obj.get(discriminator) not in named_consts` is also true when the discriminator is **absent or `null`** (verified: `find_unknown_root_keys("AuthMethod", {"type": None, "bogus": 1})` → `[]`) and when it is a non-`_`-prefixed unknown string — which `.agents/plan.md` "v2 patches / open enums" declares illegal (custom values MUST begin with `_`). So a malformed object escapes the unknown-root-key check entirely. | Carve out only when the discriminator is present **and** `_`-prefixed (reuse `tck.v2.protocol.is_valid_open_enum_value`'s rule); otherwise fall through to the normal allowed-keys comparison. |
| 6 | SHOULD-FIX | `tests/fixtures/agents/v2/` (only `_base.py`, `conforming.py`); `tests/v2/test_cli.py:56-64` | No v2 negative-control fixture or self-test. `tests/v2/test_cli.py` only asserts the all-PASS path, so nothing in the repo proves `ACP-INIT-001`/`ACP-INIT-201` can FAIL. `.agents/plan.md:246` (slice V2-1) explicitly scoped "conforming + echo-any-version + v2-only-errors-on-v1 + missing-info", and `AGENTS.md:589-591` step 6 asks for a defect fixture per new requirement. Mitigating: I verified by hand (throwaway agents in `scratch/v2fix/`) that both tests *are* falsifiable — echo-any-version → `ACP-INIT-201 FAIL`, missing-`info` → `ACP-INIT-001 FAIL`, both flipping the verdict to NOT CONFORMANT. So this is a coverage gap, not a broken test. | Add `echoes_any_version.py` and `missing_info.py` under `tests/fixtures/agents/v2/` plus `tests/v2/test_cli.py` assertions. If V2-1b already owns them, record that explicitly in `.agents/plan.md`/`state.md` so it isn't dropped between slices. |
| 7 | SHOULD-FIX | `src/tck/common/version.py:37-45`, `src/tck/common/plugin.py:615-616`, `tests/v2/test_cli.py` | `agent_info_field`/`agent_capabilities_field` is the **only** new behavioural logic V2-1a added to `common/plugin.py`, and it has zero automated coverage: `tests/v2/test_cli.py` never passes `--report-json`. I verified manually that a v2 report carries `protocol_version: 2`, `schema_revision: 8f76d6c…`, `agent_info` read from `info`, and `agent_capabilities` read from `capabilities` — but a regression here would be silent. | Add a `--report-json` case to `tests/v2/test_cli.py` mirroring `tests/v1/test_cli.py:850-865`, asserting `protocol_version == 2` and that `agent_info["name"]` is the v2 fixture's name. |
| 8 | SHOULD-FIX | `tests/v2/test_registry.py` (no twin of `tests/v1/test_registry.py:106-133`), `tests/v2/test_cli.py:19` | No v2 equivalent of `test_cli_selftest_tier_sets_match_the_registry`, which `common-v1-v2-split-analysis.md` §5.3 item 9 explicitly asked for ("a v2 mirror of `tests/v1/test_cli.py`'s id sets + the `test_registry` cross-check"). `_MANDATORY_IDS` in `tests/v2/test_cli.py` is hand-maintained with nothing cross-checking it against `REGISTRY`'s `tier` field; `test_registry_has_exactly_the_two_skeleton_requirements` checks the id *set* only. A tier misclassification in V2-1b would go unnoticed — exactly the drift the v1 test was added to catch (review-slices-7.md N10). | Add the tier-set cross-check to `tests/v2/test_registry.py`, importing `tests/v2/test_cli.py` as `v2.test_cli` (note the package-name difference from v1's bare `import test_cli`). |
| 9 | NIT | `src/tck/common/plugin.py:299`, `:339` | The last v1-derived wire literals in the "version-agnostic" core: `init_outcome.result.get("authMethods")` and the `"initialize"` method name. Both are correct for v2 (v2 `InitializeResponse` also has root `authMethods` — `src/tck/v2/schema/schema.json:3070`; `src/tck/v2/schema/meta.json:4` keeps `initialize`), so nothing is broken. But `common-v1-v2-split-analysis.md` §"Testability notes" recommended a grep meta-test asserting `common/` contains zero such occurrences outside docstrings, and that test was not added. | Either promote `authMethods` to a `VersionSpec` field alongside `agent_info_field`, or add a one-line comment at `:299` recording that the key is unchanged in v2 @ `8f76d6c`. Consider the recommended grep meta-test. |
| 10 | NIT | `src/tck/common/version.py:34-36`, `:29`; `src/tck/v1/__init__.py:24,27`; `src/tck/v2/__init__.py:37,40` | `VersionSpec.conformance_package` and `VersionSpec.schema_dir` are populated by both SPECs but read by **nothing** (grepped `src/` and `tests/`: zero consumers). `schema_dir` duplicates `tck.vN.protocol.SCHEMA_DIR`, which is what `validation.py` actually uses; `conformance_package`'s docstring claims it is "for self-tests and diagnostics", and no self-test uses it. | Drop both, or wire `conformance_package` into the report/diagnostics where it would actually help. `.agents/plan.md` D1 named them, so update D1 if they are dropped. |
| 11 | NIT | `src/tck/common/plugin.py:587` (+ `:193`, `:693`) | Loading `tck.common.plugin` directly — which its own docstring forbids — dies with an unreadable `KeyError: <_pytest.stash.StashKey object at 0x…>` out of `_build_report` (verified with `pytest src/tck/v1/conformance -p tck.common.plugin …`). Loading both shims at once dies with `ValueError: option names {'--tck-agent-cmd'} already added` (also verified) — loud enough, no fix needed. | Add to `tck.common.plugin.pytest_configure`: `if VERSION_SPEC_KEY not in config.stash: raise pytest.UsageError("tck.common.plugin is not usable alone; load -p tck.v1.plugin or -p tck.v2.plugin")`. The shim stashes before delegating, so the check is safe. |
| 12 | NIT | `src/tck/v1/plugin.py:25-27`, `src/tck/v2/plugin.py:26-28` | Undocumented footgun in the `vars()`/`globals().update()` shim: the copied hook functions keep `__globals__` pointing at `tck.common.plugin`, so only functions pytest resolves *by name as a hook* (like `pytest_configure`) can be overridden in a shim. Redefining a helper such as `_build_report` or `_transcript_entries_dict` in `tck.v2.plugin` would silently have no effect. V2-3 (batch-aware transport/JSON-RPC) is the first slice likely to attempt this. | One sentence in both shim docstrings and in `AGENTS.md`'s `plugin.py` layout entry: "only pytest hook functions can be overridden here; helpers resolve against `tck.common.plugin`'s own globals." |
| 13 | NIT | `src/tck/v2/validation.py:475-479` | Dead branch: `if "error" in msg and "result" not in msg: return issues` is fully subsumed by the immediately following `if "result" not in msg: return issues`. | Delete the first branch (or keep one with a comment explaining the error case). |
| 14 | NIT | `.agents/plan.md:45` vs `src/tck/__init__.py:24-32` | Plan deviation: plan.md says "`--protocol-version {1,2}` (plugin: `--tck-protocol-version`)", but the implementation routes purely at the CLI level (choosing the plugin module and conformance dir) with no `--tck-*` twin. The implementation is the better choice (D8: exactly one module registers `--tck-*` options) and `AGENTS.md:430-434` documents it correctly — but plan.md still claims the option exists, so a later slice may "restore" it. | Correct plan.md part 2 to describe CLI-level routing with no plugin option. |
| 15 | NIT | `src/tck/conformance/`, `src/tck/harness/` (worktree only) | `git mv` left two empty directories behind (git does not track empty dirs, so a fresh clone is clean). Effect in this worktree: `import tck.conformance` and `import tck.harness` silently succeed as empty namespace packages (verified — `_NamespacePath([...])`) instead of raising `ModuleNotFoundError`, softening D7's clean break and turning an obvious error into a confusing `ImportError: cannot import name`. | `rmdir src/tck/conformance src/tck/harness` in each existing worktree; nothing to commit. |
| 16 | NIT | `tests/v1/test_registry.py:107`, `tests/common/test_report.py:3`, `AGENTS.md:257-259`, `src/tck/common/plugin.py:103,126-130` | Stale internal references: two docstrings still say `tests/test_cli.py` (now `tests/v1/test_cli.py`); `AGENTS.md` describes `tests/conftest.py` as spawning fixtures "under `tests/fixtures/agents/v1/`" and applying "to both `tests/common/` and `tests/v1/`", omitting the new `version="v2"` parameter and `FIXTURES_DIR_V2` (`tests/conftest.py:16-26`) and `tests/v2/`; `--tck-cancel-prompt`/`--tck-auth-method` help text in the version-agnostic module names v1-only ids (`ACP-CANCEL-001/002`, `ACP-AUTH-003`). | Mechanical text fixes; make the help text version-neutral ("the cancellation tests", "the authentication tests"). |
| 17 | NIT | `README.md:120-122` | Overstates v2 coverage: "Batch JSON-RPC arrays and v2's other prompt-lifecycle changes are validated at the schema level (`tck.v2.validation`)". `tck.v2.validation` is *capable* of validating those shapes, but the v2 suite only ever feeds the `initialize` response through it (`src/tck/v2/conformance/test_initialize.py:27`) — no batch or prompt message is validated anywhere yet. | Reword to "`tck.v2.validation` already understands batch arrays and the v2 message shapes, but no v2 conformance test exercises them yet." |
| 18 | NIT | `tests/v2/__init__.py` (present) vs `tests/v1/`, `tests/common/` (absent) | The three duplicated test basenames (`test_cli`, `test_registry`, `test_validation`) avoid pytest's "import file mismatch" only because exactly one side is a package (`v2.test_cli` vs bare `test_cli`). It is deliberate and documented (`AGENTS.md:274-276`) and the suite is green, but a future `tests/v1/test_report.py` would collide with `tests/common/test_report.py`. | Optional: add `__init__.py` to `tests/v1/` and `tests/common/` too, making every test module fully qualified, and update `tests/v1/test_registry.py:118`'s `import test_cli` accordingly. |

## Verified OK

**v1 behaviour preserved (review question 1).** `uv run pytest` → 160 passed. The
`conforming_full.py` regression run exits 0 with `VERDICT: CONFORMANT` and the identical tier
counts (`MANDATORY 21/0/0/0`, `CAPABILITY 19/0/0/0`, `ADVISORY 11/0/1/0`, `INFORMATIONAL 4/0/0/0`).
The JSON report's top-level keys, per-requirement keys, and per-test keys match `AGENTS.md`
§Reporting exactly (`tck_version`, `protocol_version`, `schema_revision`, `agent_command`,
`agent_info`, `agent_capabilities`, `started_at`, `finished_at`, `requirements`, `verdict`; 56
requirement entries; `verdict` = `{conformant, blocked_by_auth, tier_counts}`). I diffed
`git show 589e334:src/tck/requirements.py`'s `REGISTRY` field-by-field against
`tck.v1.requirements.REGISTRY`: identical id set, identical tiers/capabilities, and the only
text/citation changes are the three documented module-path rewordings (`ACP-CANCEL-002`,
`ACP-JSONRPC-003`, `ACP-SCHEMA-002`) plus the `ACP-INIT-003` `info`-probe text/citation/
`source_report` addition. `git diff` on `src/tck/plugin.py → src/tck/common/plugin.py` shows no
`--tck-*` option added, removed, or renamed; the only functional changes are the six `VersionSpec`
lookups. `pyproject.toml`'s marker help text and `description` changed as §5.1 step 11 prescribed.

**`common/` is version-agnostic (question 2).** Grepping `src/tck/common/` for v1 literals returns
only docstrings plus the two code literals in finding 9. No module under `common/` imports from
`v1`/`v2` (grepped), and neither version package imports the other (docstring mentions only). The
`capability` gate is path-driven, not `agentCapabilities`-rooted: `_lookup_capability`
(`common/plugin.py:354-362`) walks any dotted path from the `initialize` *result* root, and I
confirmed `capability_is_supported({... "capabilities": {"session": {}}}, "capabilities.session")`
→ `True` while `"agentCapabilities.session"` → `False`, so `@pytest.mark.capability("capabilities.session")`
will work for v2 as-is. The shim mechanism is sound: `globals().update(...)` runs before the
`pytest_configure` override (`v1/plugin.py:25-32`), so the shim's own hook wins; copied autouse
fixtures work (proved by every v1 and v2 run); and no cross-version state leaks, because
`load_schema`/`_def_validator`/`_allowed_root_properties` are distinct `lru_cache`d function
objects in distinct modules (`tck.v1.validation` vs `tck.v2.validation`), each reading its own
`SCHEMA_DIR`.

**v2 skeleton vs. the research (question 3).** Vendored artifacts are byte-identical:
`git -C <spec> show 8f76d6c:schema/v2/schema.json | diff - src/tck/v2/schema/schema.json` and the
same for `meta.json` both produce no output, and `VENDORED.md`'s commit hash, date, copy commands,
and never-vendor-`.unstable.json` note are accurate. Inventories are right: 11 agent methods,
4 client methods, `PROTOCOL_METHODS == {"$/cancel_request"}`, `KNOWN_METHODS` = 16 = every method in
`meta.json`; `AGENT_NOTIFICATIONS == {"session/cancel"}`, `CLIENT_NOTIFICATIONS ==
{"session/update", "elicitation/complete"}`. Error codes match v1 as the delta inventory says.
The validator does dispatch on `dict` vs non-empty `list` before any `$def` lookup
(`validation.py:245-260`, `:456-471`), flags an empty array as one issue (`:221-226`), carries **no**
`null` special case (`:443-454`, and I confirmed `validate_agent_response("initialize", {... "result": None})`
yields issues), and keeps the hand-written unknown-root-key check with the `other` carve-out.
`is_valid_open_enum_value` correctly accepts defined constants and `_`-prefixed strings and rejects
non-`_` unknowns (`"something_new"` → `False`) — the only problem is the unhashable-input crash
(finding 4). `SPEC.initialize_params()` (`v2/__init__.py:21-25`) sends exactly `protocolVersion`,
`info: {name, version}`, `capabilities: {}` — no terminal marker, no `clientCapabilities`.
`v2/conformance/_helpers.py:50-51` awaits the `initialize` response before anything else is sent
(satisfying the "never pipeline behind `initialize`" constraint) and `:54` sends `auth/login
{methodId}`, v2's rename, with the same `AUTH-GATED:` skip semantics as v1. Both registry citations
check out against the spec commit: `initialization.mdx:24` = "Clients **MUST** initialize the
connection…", `:47` = "The Agent **MUST** respond with the chosen protocol version…, and its
implementation information", `:94` = "If the Agent supports the requested version, it **MUST**
respond with the same version. Otherwise…the latest version it supports"; `schema.json:5838` (cited
by `router_requires_info.py`) is indeed `"required": ["protocolVersion", "info"]` on
`InitializeRequest`, and `InitializeResponse` requires the same pair. The `ACP-INIT-001` vs
`ACP-INIT-201` id decision matches D3 and its 2xx refinement, and `ACP-INIT-201` matches
`_ID_PATTERN`. `uv build --wheel` confirms `tck/v2/schema/{schema,meta}.json` and `VENDORED.md`
ship in the wheel.

**Test quality (question 4).** No `xfail` anywhere (and `common/plugin.py:205-210` actively forbids
it in a conformance suite); the only `skip` in the v1 regression run is the legitimate
`ACP-AUTH-005` empty-`authMethods` case. `tests/v1/test_cli.py::test_router_requires_info_passes_everything`
is a real guard on the V2-0b fix, not a tautology: with the `info` removed from the probe,
`router_requires_info.py` replies `-32602` and `ACP-INIT-003` FAILs, so the test's
`assert statuses.get(req_id) == "PASS"` would fail. `router_requires_info.py` faithfully models the
router trap described at `acp-v2-version-negotiation.md:137,185` (routes `>= 2` to v2, validates
`info`, answers `protocolVersion: 2`); the implementation adds `info` to the 65535 probe only,
which follows plan.md part 2 (narrower than the research's "both probes") and is harmless because
the reference probe requests version 1. `ACP-INIT-201` would catch an `echoes_any_version`-style v2
defect — its `assert version_b != 65535` fires — which I confirmed empirically. `tests/v2/test_cli.py`
usefully pins that the default and `--protocol-version 1` paths still run the v1 registry.

**Docs (question 5).** `AGENTS.md`'s intro, Layout tree (both `src/tck/v2/` and `tests/v2/`),
Running section, `--protocol-version` explanation, `tests/fixtures/agents/v2/` catalogue entry, and
`router_requires_info.py` entries (`:319`, `:716`) are all present and accurate; the
`tests/v2/__init__.py` rationale is explicitly documented. `README.md` gained a `--protocol-version`
option entry and a v2 protocol-scope paragraph. `docs/cross-check.md` and `scripts/` paths were
updated. `.gitignore` already contains `scratch/`.

## Open questions

1. **Does slice V2-1b own the v2 defect fixtures and the `--report-json`/tier-set v2 tests
   (findings 6, 7, 8)?** `.agents/state.md:41` says V2-1b is "full v2 init/session" off `1d795cc`,
   and plan.md's V2-1 scope named the fixtures. If yes, findings 6–8 need only a note in plan.md; if
   no, they belong in the fix slice. I did not read the sibling worktree, per instructions.
2. **Should `find_unknown_root_keys`'s open-fallback carve-out compose with the enum rule or stay
   independent (finding 5)?** plan.md says non-`_` unknown discriminators FAIL (an ENUM-2xx
   requirement) while the carve-out currently treats them as legitimate. Tightening the carve-out
   makes the two checks agree; leaving it means an object with an illegal discriminator escapes the
   root-key check but is caught by the enum check instead. Owner: whoever writes ENUM-201..203 in
   V2-6.
3. **Does the v2 `--auth-method` flow need a `capabilities.auth`-aware variant?** `v2/conformance/_helpers.py`
   sends `auth/login` whenever `--tck-auth-method` is given, but the v2 decisions say non-empty
   `authMethods` (not a capability marker) is what commits an agent to `auth/login`. Out of scope
   here; belongs to V2-5.
4. **Should `common/` grow the grep meta-test §"Testability notes" recommended** ("`rg -n
   'protocolVersion|session/|\"initialize\"' src/tck/common/` returns nothing but docstrings")?
   As written it would currently fail on the two literals in finding 9, so adopting it requires
   deciding finding 9 first.
