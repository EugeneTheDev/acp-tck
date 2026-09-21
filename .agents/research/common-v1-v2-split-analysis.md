# Which parts of `src/tck/` and `tests/` are version-agnostic, which are v1-specific, and what coupling points must a `common`/`v1`/`v2` split cut?

**Sources checked:**
- `acp-tck-2` (this repo) @ `589e334`, branch `v2-support`, worktree clean at time of reading (2026-09-21).
  Every `path:line` below is repo-relative to this repo unless prefixed otherwise.
- `a2a-tck` @ `263b9cfaf16a554bdfb166a7ba5b67716e946349` (2026-09-01), read-only, via the
  `check-a2a-tck` skill — **inspiration only**, see §4. Cited as `a2a-tck:<path>:<line>`.
- Not consulted: `check-specification`, `check-rust-sdk`, `check-python-sdk`. This question is about
  this repo's own code; every place where the answer depends on an ACP-v2 protocol fact is flagged
  explicitly as **[v2-FACT]** with the exact fact that decides it.

**Confidence:** high for the inventory, the import graph, and the coupling points (all read directly
from source); medium for the migration plan and the fixture-family recommendation (they depend on v2
deltas nobody has reported yet — every such dependency is marked **[v2-FACT]**).

---

## Answer

Roughly **35–40 % of the ~5 550 Python lines under `src/tck/` is genuinely version-agnostic
machinery** — the whole harness (500 LOC), almost all of `plugin.py` (~735 of 751), `report.py`
(~216 of 218), `__main__.py`, and most of the CLI shell — and **~60 % is v1 protocol content**: the
entire `src/tck/conformance/` tree (2 481 LOC, every line of which names v1 methods and shapes) plus
the 818 lines of requirement declarations in `requirements.py`. `validation.py` (424 LOC) is the
swing vote: its algorithm is fully generic but it is hard-wired to one schema directory, so whether
it lands in `common/` depends on whether v2's schema keeps the same `x-method`/`x-side` +
`AgentRequest`/`AgentResponse`/`ProtocolLevel` envelope structure **[v2-FACT]**. The five hardest
coupling points are (1) `requirements.REGISTRY` as a module-level global read from four places
outside its own module, (2) the session-scoped autouse `agent_initialize_result` fixture
(`src/tck/plugin.py:309-339`) that hardcodes `protocolVersion: 1` and is the single source of truth
for capability gating, `authMethods`, and the report's agent metadata, (3) `validation.py`'s
`@lru_cache`d, singleton-schema design (`src/tck/validation.py:29,65,93,116,315`), (4)
`_helpers.connected_agent`/`run_prompt` — a v1 mock *client* woven through every conformance test,
and (5) the two self-tests that hand-mirror the registry (`tests/test_registry.py:105-131`,
`tests/test_cli.py:26-95`). My recommendation is **one version's suite per CLI invocation** (pytest
pointed at `tck/v1/conformance` or `tck/v2/conformance`, exactly one plugin module loaded): the
combined-run option breaks `Report.protocol_version` (`src/tck/report.py:196`), forces requirement-id
namespacing, makes `Verdict.conformant` (`src/tck/report.py:149`) meaningless for a v1-only agent,
and cannot keep v1's JSON report byte-identical. Six decisions (registry ownership, `Tier` sharing,
id namespacing, report version granularity, one-vs-two runs, validation sharing) must be settled
*before* the mechanical move, because each changes where files land.

---

## Classification table

Legend: **C** = version-agnostic → `common/`; **V1** = v1-specific → `v1/`; **M** = mixed (generic
module with version-specific lines listed in §1).

| # | Path | LOC | Class | What makes it that class |
|---|------|-----|-------|--------------------------|
| 1 | `src/tck/harness/process.py` | 405 | **C** | Pure NDJSON/JSON-RPC-2.0 stdio transport. Only ACP references are docstrings (`:1,3,74`) and the literal `"jsonrpc": "2.0"` envelope (`:207,214`). No method names, no `protocolVersion`. |
| 2 | `src/tck/harness/transcript.py` | 79 | **C** | Raw bytes + best-effort decode; zero protocol knowledge (grep for `protocolVersion|session/|initialize` returns nothing). |
| 3 | `src/tck/harness/__init__.py` | 16 | **C** | Re-exports only. |
| 4 | `src/tck/report.py` | 218 | **M** | Aggregation, `Status`, `Verdict`, JSON shape are generic. V1 coupling: `from .requirements import REGISTRY, Tier` (`:34`) and `build_requirement_results` iterating the global (`:130-131`). `protocol_version`/`schema_revision` (`:196-197`) are *fields*, not constants — already injected. |
| 5 | `src/tck/plugin.py` | 751 | **M** | ~735 lines are version-agnostic pytest plumbing. 10 version-specific sites, listed in §1.2. |
| 6 | `src/tck/validation.py` | 424 | **M** (→ **C** if **[v2-FACT]** holds) | Algorithm is schema-shape-driven, not v1-value-driven. Sole coupling: `from .protocol import load_schema` (`:29`), plus five `@lru_cache`s (`:65,93,116,315`) keyed only by def-name, implicitly assuming *one* schema per process. |
| 7 | `src/tck/protocol.py` | 130 | **M** | `PROTOCOL_VERSION = 1` (`:15`), `SCHEMA_DIR = …/"v1"` (`:24`), `SCHEMA_REVISION` (`:26`), v1 error codes (`:34-41`), v1 `StopReason` closed enum (`:44-57`) are all v1 data. The derivation helpers `_collect_ref_names` (`:81-93`) and `_notification_methods` (`:96-111`) are generic schema-walking code. |
| 8 | `src/tck/requirements.py` | 893 | **M** | `Tier` (`:28-32`), `Requirement` + its invariant (`:35-55`), `_cite` (`:58-59`), `get()` (`:885-893`) are machinery (~62 LOC). `_DECLARATIONS` (`:62-880`, 818 LOC, 56 entries) and `SPEC_REVISION` (`:21-25`) are pure v1 content. |
| 9 | `src/tck/__init__.py` (CLI) | 147 | **M** | argparse shell and pytest-arg assembly are generic. V1 coupling: `conformance_dir = Path(__file__).parent / "conformance"` (`:108`, also `:117` as `--rootdir`) and `"-p", "tck.plugin"` (`:112-113`). No `--protocol-version` option exists. |
| 10 | `src/tck/__main__.py` | 8 | **C** | `from tck import main`. |
| 11 | `src/tck/conformance/__init__.py` | 6 | **V1** | Docstring says "The ACP v1 conformance suite". |
| 12 | `src/tck/conformance/conftest.py` | 6 | **C** (content-free) | Intentionally empty; would be duplicated verbatim per version. |
| 13 | `src/tck/conformance/_helpers.py` | 391 | **V1** | `connected_agent` sends `initialize` with `PROTOCOL_VERSION` (`:44-53`); `new_session` sends `session/new {cwd, mcpServers}` (`:121`); `run_prompt` is a v1 mock client (`session/prompt`, `session/update`, `session/request_permission`, `session/cancel` — `:237,258,302,306,317`). `quiet_period`/`cancel_race_peek` (`:133-148`) are the only genuinely generic functions here. |
| 14 | `src/tck/conformance/test_transport.py` | 65 | **V1** | Assertions are generic (valid JSON, `jsonrpc == "2.0"`, UTF-8 — `:51-53,65`) but the *driver* is v1 (`initialize`→`session/new`→`session/prompt`, `:26-41`). |
| 15 | `src/tck/conformance/test_jsonrpc.py` | 152 | **V1** | v1 `initialize` params (`:43,74`), v1 `_tck/` probe convention. |
| 16 | `src/tck/conformance/test_initialize.py` | 182 | **V1** | Entirely about v1 negotiation, incl. the strengthened 65535 rule (`:87-107`). |
| 17 | `src/tck/conformance/test_session.py` | 58 | **V1** | `session/new` semantics. |
| 18 | `src/tck/conformance/test_prompt.py` | 79 | **V1** | v1 `StopReason` set, `session/update` shape. |
| 19 | `src/tck/conformance/test_cancel.py` | 154 | **V1** | `session/cancel` + `stopReason: "cancelled"`. |
| 20 | `src/tck/conformance/test_session_capabilities.py` | 392 | **V1** | Nine `@pytest.mark.capability("agentCapabilities.…")` paths, all v1. |
| 21 | `src/tck/conformance/test_session_config.py` | 270 | **V1** | `modes`/`configOptions`, inferred gates. |
| 22 | `src/tck/conformance/test_prompt_capabilities.py` | 110 | **V1** | `agentCapabilities.promptCapabilities.{image,audio,embeddedContext}`. |
| 23 | `src/tck/conformance/test_authentication.py` | 146 | **V1** | Hardcodes `{"protocolVersion": 1, …}` three times (`:46,80,119`) — note: *literal `1`*, not the constant. |
| 24 | `src/tck/conformance/test_client_capabilities.py` | 86 | **V1** | `fs/*`, `terminal/*`, `elicitation/create`. |
| 25 | `src/tck/conformance/test_extensibility.py` | 132 | **V1** | `_meta` on `session/prompt`; `find_unknown_root_keys` against v1 `$def`s. |
| 26 | `src/tck/conformance/test_diagnostics.py` | 85 | **V1** | Drives v1 `initialize` (`:28`); the `ERROR-001`/`SHUTDOWN-001`/`STDERR-001` assertions themselves are version-agnostic in spirit. |
| 27 | `src/tck/conformance/test_informational.py` | 167 | **V1** | Drives v1 `initialize` (`:52,92`) and `session/prompt`. |
| 28 | `src/tck/schema/v1/{schema,meta}.json` + `VENDORED.md` | data | **V1** | Verbatim vendored @ `6d08f412…` (`src/tck/schema/v1/VENDORED.md:9`). A `schema/v2/` sibling is the natural home for v2. |
| 29 | `scripts/cross-check-summary.py` | 142 | **C** | Consumes the report JSON by string keys only (`:31-40`); knows nothing about which version produced it. |
| 30 | `scripts/cross-check.sh` | — | **V1** | Pins v1-speaking upstream agents and `--cancel-prompt wait_for_cancel`. |
| 31 | `tests/conftest.py` | 27 | **M** | Generic helper, but `FIXTURES_DIR` is a single hardcoded path (`:15`). |
| 32 | `tests/test_harness.py` | 310 | **M** | Tests generic harness behaviour, but every case drives a v1 fixture with `{"protocolVersion": 1}` (`:30,42,47,58,59,81,108,130,161,182,209,229,244,283`) and `session/new`/`session/prompt`/`session/cancel` (`:287,293,303`). |
| 33 | `tests/test_validation.py` | 268 | **M** | Generic assertions about `validate_agent_*`, all against v1 payloads and v1 `$def` names. |
| 34 | `tests/test_plugin.py` | 58 | **C** | Pure `capability_is_supported` unit tests on synthetic dicts — the only fully version-free test file besides `test_cross_check_summary.py`. |
| 35 | `tests/test_report.py` | 272 | **M** | Aggregation logic is generic; the test data is drawn from the live v1 `REGISTRY` (`:82,85,88,101,123,183,229`). |
| 36 | `tests/test_registry.py` | 132 | **V1** | Registry invariants + two-way marker cross-check against `tck.conformance` (`:75-90`) + the tier-set cross-check against `test_cli.py` (`:105-131`). |
| 37 | `tests/test_cli.py` | 949 | **V1** | Hand-maintained v1 id sets (`:26-95`) and ~45 end-to-end verdict assertions against v1 fixtures. |
| 38 | `tests/test_cross_check_summary.py` | 142 | **C** | Exercises the generic summary script. |
| 39 | `tests/fixtures/agents/_base.py` | 428 | **V1** | `PROTOCOL_VERSION = 1` (`:18`), v1 `ContentBlock` variants (`:23`), v1 method dispatch (`:128-163`). |
| 40 | `tests/fixtures/agents/*.py` (38 scripts) | ~1 400 | **V1** (3 exceptions) | 31 of 38 import `_base`; `exits_immediately.py` (9 LOC), `never_responds.py` (17 LOC) are protocol-free; `dies_on_bad_json.py` and `asks_permission_closable.py` are hand-rolled but still v1. |

---

## Details

### 1. Module inventory and line-level coupling

#### 1.1 `src/tck/protocol.py` — the declared "one place" that is not one place

The module docstring for `PROTOCOL_VERSION` already anticipates this work:

> "This is a v1-only assumption baked into the whole package… A future v2 effort must find and
> update every place that reads this constant — start here." — `src/tck/protocol.py:18-20`

The constant is read from six modules:

| Reader | Line | Use |
|---|---|---|
| `src/tck/plugin.py` | `:30` import, `:327` | the session-scoped `initialize` handshake |
| `src/tck/plugin.py` | `:608` | `Report.protocol_version` |
| `src/tck/conformance/_helpers.py` | `:15` import, `:47` | `connected_agent`'s handshake |
| `src/tck/conformance/test_initialize.py` | `:10,21,118` | |
| `src/tck/conformance/test_jsonrpc.py` | `:21,43` | |
| `src/tck/conformance/test_diagnostics.py` | `:9,28` | |
| `src/tck/conformance/test_informational.py` | `:24,52,92` | |

Plus three places that bypass the constant entirely and hardcode the literal `1`:
`src/tck/conformance/test_authentication.py:46,80,119`, and
`src/tck/conformance/test_initialize.py:41,74` (deliberately, since those tests are *about*
negotiation). `tests/test_harness.py` hardcodes `1` in 14 places. Any migration script that
mass-renames the constant will silently miss all of these; they must be found by grepping the
literal, not the symbol.

`SCHEMA_DIR` (`:24`) resolves `Path(__file__).parent / "schema" / "v1"` — so wherever `protocol.py`
physically lands, the schema directory follows it. This is the single line that decides whether
`schema/` sits under `common/` (with a version subdirectory argument) or is duplicated per version
package.

`SCHEMA_REVISION` (`:26`) is deliberately the single source for three consumers:
`requirements.SPEC_REVISION` (`src/tck/requirements.py:21,23`), `Report.schema_revision`
(`src/tck/plugin.py:609`), and `tests/test_registry.py:53-62`'s assertion that every citation ends
in that exact 40-hex hash. A v2 registry pinned to a different spec commit therefore *cannot* share
a single global `SCHEMA_REVISION` — this is a hard fork point, not a preference.

The error codes (`:34-41`) and `STOP_REASONS` (`:44-57`) are v1 values that may or may not carry
over **[v2-FACT: does v2 keep the same `ErrorCode` set and the same closed `StopReason` enum?]**.
Structurally they are independent constants, so duplicating them costs ~25 lines per version.

#### 1.2 `src/tck/plugin.py` — 10 version-specific sites in 751 lines

Everything else in this file (options, async support, the watchdog, process tracking, transcript
truncation, `_TestState` collection, JSON writing, the exit-code override) is version-agnostic.

| # | Line(s) | Symbol / text | Why version-specific | Cut |
|---|---|---|---|-----|
| P1 | `:30` | `from .protocol import PROTOCOL_VERSION, SCHEMA_REVISION` | both are v1 values | inject via a version-spec object |
| P2 | `:40` | `from .requirements import REGISTRY, Tier` | `REGISTRY` is v1 content; `Tier` is machinery | split the import: `Tier` from `common`, `REGISTRY` injected |
| P3 | `:171,175-178` | marker help strings naming `tck.requirements.REGISTRY` and the cached `initialize` result | cosmetic but wrong after the move | text edit |
| P4 | `:188` | `if req_id not in REGISTRY:` inside `pytest_collection_modifyitems` | validates markers against the *active* registry | needs the active registry |
| P5 | `:309-339` | `agent_initialize_result` fixture | sends `{"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}` (`:326-328`) and parses the v1 result | **the hardest one** — see §2.3 |
| P6 | `:342-368` | `_lookup_capability` / `capability_is_supported` | dotted-path lookup into the initialize result; *generic given a path*, but presumes capabilities live in the initialize result at all | **[v2-FACT: does v2 still advertise capabilities as a nested object in `initialize`'s result?]** |
| P7 | `:557` | `_TIER_ORDER = [Tier.MANDATORY, …]` | only depends on `Tier` | shared if `Tier` is shared |
| P8 | `:608-609` | `protocol_version=PROTOCOL_VERSION, schema_revision=SCHEMA_REVISION` | v1 values into the report | inject |
| P9 | `:685` | `sorted(req_id for req_id, req in REGISTRY.items() if req.tier is tier)` in the terminal summary | iterates the global registry | needs the active registry |
| P10 | `:596` | `build_requirement_results(tests_by_req)` | delegates the same global-registry read into `report.py` | inject |

Note `_AUTH_GATED_MARKER` (`:572`) and the `blocked_by_auth` mechanism (`:582-583,711-712,743-750`)
are generic *string plumbing*, but the concept they encode ("authentication gates `session/new`") is
a v1 protocol concern owned by `_helpers.skip_if_auth_gated`. The plugin side can stay in `common/`
unchanged; only the emitter is v1.

#### 1.3 `src/tck/report.py` — two lines

`from .requirements import REGISTRY, Tier` (`:34`) and the loop `for req_id in sorted(REGISTRY)`
(`:130-131`). Everything else — `Status`, `STATUS_PRIORITY`, `worse_status`, `TestOutcome`,
`RequirementResult`, `aggregate_status`, `Verdict`, `compute_verdict`, `current_tck_version`,
`Report.to_dict` — is pure data plumbing. Note `RequirementResult` (`:92-113`) carries
`tier/capability/text/citation` as plain values, so it needs no knowledge of where they came from.

`Report.protocol_version: int` (`:196`) and `schema_revision: str` (`:197`) are **per-run scalars**.
That is a design commitment: a single run reports exactly one protocol version. Changing this to a
list or moving it per-requirement is the load-bearing change the combined-run option forces (§2.4).

#### 1.4 `src/tck/validation.py` — generic algorithm, singleton schema

The only v1 import is `from .protocol import load_schema` (`:29`). But four `@lru_cache`s
(`:65 _def_validator`, `:93 _request_and_notification_method_defs`, `:116 _response_method_defs`,
`:315 _allowed_root_properties`) are keyed on a def-name or nothing at all — they assume one schema
per process. Loading two schemas in one process would silently return v1 validators for v2 def
names with the same name. This is a *correctness* hazard, not an ergonomic one, and it is the
strongest single argument for one version per process (§2.4).

The algorithm itself depends on five structural facts about the schema, all documented in
`src/tck/validation.py:1-18` and `src/tck/schema/v1/VENDORED.md:25-28`: the top-level `anyOf` of
`Agent`/`Client`/`ProtocolLevel`; the `Request`/`Response`/`Notification` split; the `x-method` and
`x-side` annotations; `AgentResponse`'s `anyOf` with a `result`-bearing branch (`:125-128`); and
`CancelRequestNotification` (`:110`). **[v2-FACT: does the v2 schema keep all five?]** If yes,
`validation.py` moves to `common/` unchanged except for taking a schema accessor instead of
importing one. If no, duplicate it — a branching validator would be exactly the "shared module that
branches on protocol version internally" the architecture rule forbids.

`_response_schema_permits_null` (`:152-160`) encodes a documented *v1 docs bug* (Discrepancy 3), and
`find_unknown_root_keys` (`:364-376`) exists only because the vendored v1 schema has zero
`additionalProperties: false`. Both are v1 workarounds living in an otherwise generic module; if v2's
schema is stricter, carrying them into `common/` would be cargo-culting.

#### 1.5 `src/tck/__init__.py` (CLI) — three lines

`conformance_dir` (`:108`, used again at `:117` as `--rootdir`), `"-p", "tck.plugin"` (`:112-113`).
Everything else — every `--tck-*` passthrough, `-rs`, `-k`, `-v`, `--version`, the `--` REMAINDER
handling — is version-agnostic and would be shared verbatim. There is currently **no** option that
could select a version; adding one is the routing decision (owned by the negotiation researcher, per
`.agents/state.md`).

#### 1.6 `src/tck/requirements.py` — a clean 62/818 split

Lines 16-59 (imports, `SPEC_REVISION`, `Tier`, `Requirement`, `_cite`) plus 885-893 (`get`) are
machinery; 62-880 is v1 data; 882 (`REGISTRY = {…}`) is the glue. The `Requirement.__post_init__`
invariant (`:51-55`) is generic. One wrinkle: `capability` is documented as "a JSON path under the
`initialize` result" (`:39-41`) — that description is v1-flavoured but the field is just a string,
and the codebase already abuses it for documentation-only values (`"inferred:modes"`,
`"inferred:authMethods"`), so it needs no change.

---

### 2. Import graph and hard couplings

#### 2.1 Current graph (arrows = "imports")

```
                        pyproject [project.scripts] acp-tck = "tck:main"
                                        |
                                        v
    tck/__main__.py  ------------>  tck/__init__.py (CLI)
                                        |  spawns pytest.main() on
                                        |  tck/conformance  with  -p tck.plugin
                                        v
                                   tck/plugin.py
                            /        |        |         \
                           v         v        v          v
              tck/harness/    tck/protocol   tck/report   tck/requirements
                   |                |            |               |
              process.py       schema/v1/*.json  +--------------->+  (REGISTRY, Tier)
              transcript.py         ^                              |
                                    |                              v
                              tck/validation.py <------------------+ (SPEC_REVISION <- SCHEMA_REVISION)
                                    ^
                                    |
   tck/conformance/test_*.py  ------+---> tck/conformance/_helpers.py
              |                               |         |        |
              +-------------------------------+         v        v
                                                 tck.plugin   tck.harness
                                                 (current_auth_method_id,
                                                  current_initialize_auth_methods,
                                                  register_active_process)
```

Self-tests:

```
tests/conftest.py        -> tck.harness
tests/test_harness.py    -> tck.harness            + tests/fixtures/agents/*
tests/test_validation.py -> tck.protocol, tck.validation, tck.harness + fixtures
tests/test_plugin.py     -> tck.plugin (pure fn only)
tests/test_report.py     -> tck.report, tck.requirements
tests/test_registry.py   -> tck.requirements, tck.protocol, tck.conformance (pkgutil walk), test_cli
tests/test_cli.py        -> subprocess `python -m tck` + fixtures
tests/fixtures/agents/*  -> tests/fixtures/agents/_base.py   (31 of 38)
```

Two notable asymmetries:

- **`_helpers.py` imports the plugin** (`src/tck/conformance/_helpers.py:14`). The conformance suite
  and the plugin are mutually entangled: the plugin provides fixtures to the suite, and the suite
  reaches back into the plugin for three contextvar accessors. A `common/plugin.py` would still be
  imported by `v1/conformance/_helpers.py` — that direction is fine (version package → common), but
  it means `common/plugin.py` must export those three accessors as a stable surface.
- **`tests/test_registry.py:76` imports `tck.conformance` and walks it with `pkgutil`** to find every
  `@pytest.mark.requirement` id. This is the only place that ties a *registry* to a *suite directory*
  programmatically, and it must become per-version (walk `tck.v1.conformance` against
  `tck.v1.requirements.REGISTRY`).

#### 2.2 The four hard couplings, restated as cut lines

| Cut | Today | What the split needs |
|---|---|---|
| **C1 — registry ownership** | `REGISTRY` is a module global read at `plugin.py:188,685`, `report.py:130`, `test_report.py`/`test_registry.py` | Either (a) `build_requirement_results(tests_by_id, registry)` + a plugin-level "active registry", or (b) a `VersionSpec` dataclass in `common/` carrying `registry`, `protocol_version`, `schema_revision`, `schema_dir`, stashed on `config` by a per-version plugin shim. (b) is fewer touch points. |
| **C2 — the initialize handshake** | `plugin.py:309-339` hardcodes v1 handshake params and result parsing | The handshake is version-specific behaviour living in a version-agnostic module. Move the *request* to the version package (a `handshake(agent) -> InitializeOutcome` callable on `VersionSpec`), keep the caching/stashing/autouse machinery in `common/`. |
| **C3 — schema singleton** | `protocol.SCHEMA_DIR` (`:24`) + four `@lru_cache`s in `validation.py` | Either one schema per process (cheap: keep per-version `protocol.py` modules, each with its own `lru_cache`d loaders, which are *distinct function objects* and therefore safe even if both are imported), or convert the caches to be keyed on `(schema_id, def_name)`. The former is strictly simpler. |
| **C4 — `PROTOCOL_VERSION` literal leakage** | 3 literal `1`s in `test_authentication.py`, 2 deliberate in `test_initialize.py`, 14 in `tests/test_harness.py` | Grep the literal, not the symbol, when moving. |

#### 2.3 What the autouse `agent_initialize_result` fixture actually gates

It is worth spelling out how much rides on `plugin.py:309-339`, because it is the one fixture that
cannot be trivially parametrized:

- `_tck_capability_gate` (`:371-385`) — every `@pytest.mark.capability` skip/fail decision.
- `_tck_auth_method_context` (`:283-295`) — populates `_INIT_AUTH_METHODS`, which
  `_helpers.skip_if_auth_gated` (`:102`) uses to decide whether a `-32000` is excusable.
- `_build_report` (`:599-604`) — `agent_info` / `agent_capabilities` in the JSON report.

It is `scope="session", autouse=True`, so **there is exactly one per pytest session**. In a combined
v1+v2 run there would have to be two, and every capability marker would need to say which one it
means. That is a real API change to the marker, not a config tweak.

#### 2.4 One suite per invocation vs. both in one process

**Option A — one version's suite per CLI invocation** (CLI points pytest at `tck/v1/conformance` or
`tck/v2/conformance`; exactly one plugin module loaded).

*Pros*
- `Report.protocol_version` (`report.py:196`) stays a scalar → **v1's JSON report stays byte-identical**,
  and `scripts/cross-check-summary.py` + `docs/cross-check.md` + the CI assertion
  (`--expect-only-mandatory-fail ACP-INIT-003`, `AGENTS.md:311-327`) keep working untouched.
- `Verdict.conformant` (`report.py:149`) keeps its current, honest meaning: "this agent conforms to
  *this* protocol version". A v1-only agent run against the v1 suite is CONFORMANT; today's
  four-status model would score it NOT CONFORMANT in a combined run purely because every v2
  MANDATORY requirement FAILed, which is a false accusation.
- Requirement ids need no namespacing: `ACP-INIT-001` can mean different things in two registries
  that never coexist in one report. (Namespacing is still *advisable* for humans — see §5 decision D3
  — but it is not forced.)
- C3 dissolves: one schema per process, so the existing `@lru_cache` design needs no change.
- C2 dissolves: one handshake per session, so the fixture keeps `scope="session", autouse=True`.
- `pytest_addoption` is registered once. **This matters concretely**: if both `tck.v1.plugin` and
  `tck.v2.plugin` defined `--tck-agent-cmd`, pytest/argparse would raise a duplicate-option error at
  startup. (Standard pytest/argparse behaviour, not verified experimentally in this repo — flagged as
  a well-founded expectation, not a measured fact.) Under Option A there is either one plugin module
  with a version selector, or two thin shims of which only one is ever loaded.

*Cons*
- Two runs, two reports, two exit codes to test a dual-version agent; no combined verdict.
- Requires a routing decision: auto-detect (probe `initialize` and pick), an explicit
  `--protocol-version {1,2}` flag, or sub-commands. **Out of scope for this report** — owned by
  `acp-v2-version-negotiation.md`.
- `tests/test_cli.py` roughly doubles in length (a v2 mirror of every end-to-end verdict assertion).

**Option B — both suites in one pytest session.**

*Pros*
- One command, one report, one artefact.
- Could express genuinely cross-version requirements (e.g. "an agent advertising v2 must still
  negotiate down to v1 correctly") — which today's `test_initialize.py:59-107` already gestures at
  with its two-handshake `latest_supported` probe.

*Cons* (each is a concrete code change, not a preference)
- `Report.protocol_version: int` must become plural or move per-requirement → **v1 report JSON is no
  longer byte-identical**, breaking the zero-behaviour-change goal and the CI baseline.
- `Verdict` must become per-version; `compute_verdict` (`report.py:168-183`) and the exit-code rule
  (`plugin.py:638-639`) both assume one bool.
- Requirement ids must be globally unique across versions → either rename all 56 v1 ids (churning
  every citation in `.agents/research/*.md`, `tests/test_cli.py:26-95`, `docs/cross-check.md`) or
  introduce a compound `(version, id)` key throughout `report.py`.
- Two session-scoped `agent_initialize_result` fixtures + a version-aware `capability` marker.
- The `validation.py` `lru_cache` hazard (C3) becomes live.
- A single-version agent produces a wall of FAIL/NOT_TESTED for the other version, and the terminal
  summary's "no MANDATORY requirement passed" hint (`plugin.py:734-742`) fires misleadingly.

**Recommendation: Option A.** The deciding argument is not ergonomics but semantics: the TCK's
verdict model (`.agents/plan.md` "Decided deliverable shape", four-status verdict) is defined
relative to *a* protocol version. Running both at once forces a new verdict model, which is exactly
the kind of shared abstraction the architecture rule warns against. Option A also happens to be the
only option compatible with "keep `acp-tck` v1 output byte-identical".

#### 2.5 Which pytest mechanisms are shared vs. version-aware (under Option A)

| Mechanism | Location | Shared as-is? |
|---|---|---|
| `--tck-*` options | `plugin.py:55-142` | **Shared.** Register once. |
| `requirement` marker | `plugin.py:169-172`, validated `:188` | Marker itself shared; the *validation* against `REGISTRY` needs the active registry. |
| `capability` marker | `plugin.py:173-179`, `:371-385` | Shared mechanism; the dotted paths are v1 data living in test files. **[v2-FACT]** on whether the path root still exists. |
| async support + watchdog | `plugin.py:210-229` | **Shared.** |
| `agent_launch`, `cancel_prompt_text` | `plugin.py:235-252` | **Shared.** |
| `_tck_auth_method_context` | `plugin.py:283-295` | Shared mechanism; depends on `agent_initialize_result` and on `authMethods` existing. **[v2-FACT]** |
| `agent_initialize_result` | `plugin.py:309-339` | **Version-aware** (C2). |
| process tracking + diagnostics | `plugin.py:388-474`, `:542-552` | **Shared.** |
| `_TestState` / `pytest_runtest_makereport` | `plugin.py:484-552` | **Shared.** |
| `pytest_sessionstart`/`sessionfinish` + exit override | `plugin.py:563,620-639` | **Shared** mechanism; `_build_report` needs the version spec. |
| `pytest_terminal_summary` | `plugin.py:663-751` | **Shared** except the `REGISTRY.items()` iteration (`:685`). |
| `-p tck.plugin` | `__init__.py:112-113` | Either keep one module name + a selector option, or two shims loaded exclusively. Never both at once (duplicate `addoption`). |
| `[tool.pytest.ini_options] markers` | `pyproject.toml:30-33` | Shared; wording mentions `tck.requirements.REGISTRY` and would need a text edit. |

---

### 3. Self-tests and fixtures

#### 3.1 Classification

| File | Tests generic machinery | Tests v1 protocol content |
|---|---|---|
| `tests/test_plugin.py` (58) | **All of it.** `capability_is_supported` against synthetic dicts. Keys like `"agentCapabilities.loadSession"` are only strings. → `tests/common/` | — |
| `tests/test_cross_check_summary.py` (142) | **All of it.** | — |
| `tests/test_harness.py` (310) | The *behaviours* under test are generic (id echo, oversize lines, stderr capture, close ladder, timeouts, exit detection) | Every case is driven with `{"protocolVersion": 1}` and v1 methods (`:30,287,293,303`). |
| `tests/test_report.py` (272) | Aggregation, verdict rule, JSON round-trip | Test data is sampled from the live v1 `REGISTRY` (`:82,101,123,183,229`). |
| `tests/test_validation.py` (268) | `validate_agent_*` contract, `find_unknown_root_keys` | Every payload and `$def` name is v1 (`ContentBlock`, `SessionNotification`, `LoadSessionResponse`, `currentModeId` vs `modeId` at `:91-119`). |
| `tests/test_registry.py` (132) | Id-shape and invariant checks (`:27-72`) are reusable | `:53-62` pins every citation to the one `SCHEMA_REVISION`; `:75-131` cross-checks a specific suite package and a specific `test_cli.py`. |
| `tests/test_cli.py` (949) | `_run_cli`, `_table_statuses` (`:116-173`) are reusable helpers | The four id sets (`:26-95`) and ~45 verdict assertions are entirely v1. |

The practical shape: **`tests/test_plugin.py` and `tests/test_cross_check_summary.py` move to a
common self-test directory unchanged; `test_harness.py`, `test_report.py`, `test_validation.py`
test common code but need a v1 fixture/registry to do it; `test_registry.py` and `test_cli.py` are
v1 suites that will be mirrored for v2.** A reasonable landing: `tests/common/` (harness, report
aggregation, plugin helpers, cross-check summary), `tests/v1/` (registry, CLI, validation),
`tests/v2/` later. `tests/conftest.py:15`'s single `FIXTURES_DIR` becomes per-version (or takes a
version argument).

`tests/test_registry.py:105-131` deserves special attention. It cross-checks `test_cli.py`'s four
hand-written tier sets against `REGISTRY`, and its docstring explicitly rejects deriving them
("this test cross-checks the two independently-written sources instead of collapsing them into
one"). That design intent should be preserved per version — meaning a v2 suite gets its own
`test_cli_v2.py` id sets and its own cross-check, not a shared parametrized one.

#### 3.2 The fixture-agent family — parametrized `_base.py` vs. parallel `_base_v2.py`

State of play: 35 of the 39 fixture scripts import `_base` directly, and
`asks_permission_closable.py` gets there transitively via `asks_permission.py` — so 36 of 39 ride on
one shared core. Only `exits_immediately.py` (9 LOC) and `never_responds.py` (17 LOC) are truly
protocol-free; `dies_on_bad_json.py` (53 LOC) is hand-rolled but still v1. Only three
scripts mention `protocolVersion` at all outside `_base.py`
(`echoes_any_version.py`, `supports_v1_and_v2.py`, `version_mismatch_errors.py`) — because
`_base.py:18,177` owns it for everyone else.

`_base.py`'s v1 surface is narrow and well-localised:
- `PROTOCOL_VERSION = 1` (`:18`) — one line.
- `_VALID_CONTENT_BLOCK_TYPES` + `_content_block_error` (`:23-47`) — v1 `ContentBlock` shapes.
- `_handle_request`'s dispatch table (`:128-163`) — 12 v1 method names.
- The per-method handlers (`:171-360`) — v1 result shapes.

**Recommendation, flagged as [v2-FACT]-dependent:**

- **If v2 is a superset/extension of v1's method inventory and `initialize` shape** — same method
  names (`initialize`, `session/new`, `session/prompt`, `session/cancel`, `session/update`), same
  params field names, additive capability/field changes — then **parametrize `_base.py`**:
  `ConformingAgent(protocol_version=2, …)` plus a handful of `if self._protocol_version >= 2`
  branches in the result builders. Roughly 31 defect fixtures stay as-is and gain a v2 sibling by
  passing one kwarg. Cost: a few version branches in one 428-line file.
- **If v2 renames methods, restructures the prompt-turn lifecycle, or changes the content-block
  union** — then **write a parallel `_base_v2.py`**. A 428-line fixture with two dispatch tables and
  two result-shape families would violate the stated architecture rule ("a small honest duplication
  that keeps each version simple beats a shared module that branches on protocol version
  internally"), and every defect fixture's diff-against-conforming would become harder to read,
  which is precisely what makes these fixtures useful.

**The fact that decides it:** compare v2's `meta.json` `agentMethods`/`clientMethods` maps and the
`InitializeRequest`/`InitializeResponse` `$def`s against v1's. If `agentMethods` is a superset with
identical wire names for the v1 subset, and `session/prompt`'s params keep `sessionId` + `prompt:
ContentBlock[]`, parametrize. Otherwise fork. (The `acp-v2-status-and-delta-inventory.md` researcher
owns this.)

A third, orthogonal fixture need **[v2-FACT]**: if the routing decision is auto-detect, the fixture
catalogue needs at least one *dual-version* agent (a v2-capable agent that also negotiates v1) and
one *version-refusing* agent, to self-test the router. `supports_v1_and_v2.py` (42 LOC) is the
existing prototype for the first — it advertises `protocolVersion: 2` support and negotiates down —
but it does not actually *speak* a different protocol; it just returns a different integer.

---

### 4. A2A TCK: how it handles multiple protocol versions — **INSPIRATION ONLY, NOT AN ACP SOURCE OF TRUTH**

Inspected at `a2a-tck` @ `263b9cfaf16a554bdfb166a7ba5b67716e946349` (2026-09-01), read-only.

**It does not support multiple spec versions.** There is no `tests/v1/`-style split, no
`--spec-version` flag, and no version field in its requirement model. What it does instead:

- **Single-revision, overwrite-in-place vendoring.** `a2a-tck:specification/` holds exactly one
  `a2a.json` / `a2a.proto` / `specification.md`, plus `a2a-tck:specification/version.json:1-14`
  recording `branch`, `commitHash`, `downloadTime`, `sourceUrl`.
  `a2a-tck:scripts/update_spec.sh:68-71` curls the new files straight over the old ones; `--org` /
  `--branch` (`:10-18`) choose *which* revision replaces the current one, never an additional one.
  The validator fixture hardcodes the single schema path
  (`a2a-tck:tests/compatibility/conftest.py:171-175`). Its documented drift-check script
  (`a2a-tck:docs/SPEC_UPDATE_WORKFLOW.md:20-45`) references a `check_spec_changes.py` that no longer
  exists — the doc is stale. (This repo's `.agents/research/spec-drift-check.md` is the healthier
  analogue.)
- **No version in the registry.** `RequirementSpec`
  (`a2a-tck:tck/requirements/base.py:86-104`) has no version-like field;
  `a2a-tck:tck/requirements/registry.py:29-49` is a flat concat of 11 family lists with a
  duplicate-id guard only.
- **CLI routes by fixed test path + markers**, never by version:
  `a2a-tck:run_tck.py:34-70` always runs `tests/compatibility/`, filtered by `-m must|should|may`
  and `--transport`.
- **A vestigial, unwired `spec_version` in the report.**
  `a2a-tck:tck/reporting/json_formatter.py:23-25,42` emits `summary.spec_version` and
  `console_formatter.py:42-44,68-69` prints it, but the pytest wiring constructs both formatters
  with only `sut_url` (`a2a-tck:tests/compatibility/conftest.py:373,388`), so it is always `""` in
  real runs and exercised only in unit tests. *Design lesson for us: a version field that nothing
  populates is worse than none.*
- The only version concept it models is the *protocol's own* `A2A-Version` header, and it models it
  as requirements under test (`a2a-tck:tck/requirements/versioning.py:24-91`), with the TCK client
  itself pinned to one constant (`a2a-tck:tck/transport/_helpers.py:13-14`).

**The useful analogy is its transport axis, not its (nonexistent) version axis.** A2A supports three
bindings (gRPC / JSON-RPC / HTTP+JSON) via: a `BaseTransportClient` ABC
(`a2a-tck:tck/transport/base.py`) behind a name→class factory
(`a2a-tck:tck/transport/manager.py:19-25`); shared validators plus per-binding subpackages
`a2a-tck:tck/validators/{grpc,http_json,jsonrpc}/`; per-binding test directories
`a2a-tck:tests/compatibility/{grpc,jsonrpc,http_json}` alongside shared `core_operations/` and
`agent_card/`; per-binding markers (`a2a-tck:pyproject.toml:52-62`); axis discovery from the SUT's
own agent card (`a2a-tck:tests/compatibility/conftest.py:109-165`, map at `:27`) narrowed by
`--transport`; and a report keyed by both `per_requirement[id].transports` and `per_transport`
(`a2a-tck:tck/reporting/json_formatter.py:48-66`).

Two design ideas worth stealing (**labelled as A2A-derived ideas, not ACP requirements**):
1. **Discover the axis from the SUT, then let the CLI narrow it.** Their agent-card discovery maps
   cleanly onto "probe `initialize` to learn which ACP versions the agent supports, then let
   `--protocol-version` narrow it". This is the strongest argument for auto-detect routing — but the
   routing decision belongs to `acp-v2-version-negotiation.md`, not here.
2. **Shared-core + per-axis subpackage layout** (`validators/{shared,grpc,jsonrpc}`,
   `tests/compatibility/{shared,grpc,jsonrpc}`) is structurally the `common/`+`v1/`+`v2/` shape we
   are proposing, and it worked for them across three quite different wire formats.

One anti-pattern to avoid: they have **no** `pytest_generate_tests` parametrization over transport
(zero grep hits); the axis is hardcoded per test or looped over in-test
(`a2a-tck:tests/compatibility/core_operations/test_data_model.py:115`), and their result collector
has to recover `(requirement_id, transport)` from callspec params, markers, *or crashed-frame
locals* (`a2a-tck:tests/compatibility/conftest.py:213-284`). That is what leaving the axis implicit
costs. Our equivalent: make the version explicit in the plugin's config stash, never inferred.

Caveat the subagent correctly raised: A2A's transport axis is a runtime-negotiated per-SUT property,
whereas an ACP v1/v2 axis is a protocol-revision property negotiated in `initialize`. The
"discover-from-SUT / filter-via-CLI / key-the-report-by-axis" shape transfers; the
"hardcode-the-axis-per-test" shape does not.

---

### 5. Recommended migration plan — **RECOMMENDATION, not a finding**

#### 5.0 Decisions that must be made BEFORE the mechanical move

Each of these changes *where files land*, so deciding them after the move means moving twice.

| # | Decision | Options | My recommendation & why |
|---|---|---|---|
| **D1** | Does `REGISTRY` become a per-version *instance* or does `Requirement` stay a shared class with per-version registries? | (a) `common/requirements.py` holds `Tier`+`Requirement`+`get(registry, id)`; `v1/requirements.py` holds `REGISTRY`. (b) A `VersionSpec` dataclass in `common/` bundling registry + protocol_version + schema_revision + schema_dir + handshake callable. | **(b), built on (a).** `VersionSpec` collapses P1/P2/P4/P8/P9/P10 into a single stash lookup in `plugin.py`, instead of six separate injections. One new ~15-line dataclass. |
| **D2** | Is `Tier` shared? | shared / per-version | **Shared.** It is four names with no protocol content (`requirements.py:28-32`), and `report.py`/`plugin.py` iterate it (`report.py:170`, `plugin.py:557`). Forking it would force a generic `TierT` type parameter — exactly the "unclear generic parameters" the rule forbids. Same for `Status`, `Verdict`, `TestOutcome`, `RequirementResult`. |
| **D3** | Are requirement ids namespaced per version? | `ACP-INIT-001` in both registries / `ACP-V2-INIT-001` / a `version` field on `Requirement` | **Namespace the ids** (`ACP-V2-*`) even though Option A does not force it. Reason: reports, `docs/cross-check.md`, and `.agents/research/*.md` citations are read by humans across both versions, and A2A's unwired `spec_version` (§4) shows that a field nothing looks at does not help. **Gotcha, verified by running the regex:** `ACP-V2-INIT-001` does **not** match `_ID_PATTERN` (`tests/test_registry.py:18`, `^ACP-[A-Z]+(?:-[A-Z]+)*-\d{3}$`) because `V2` contains a digit; `ACP-TWO-INIT-001` does. Either widen the pattern or pick a digit-free prefix. |
| **D4** | Does the report carry a version per run or per requirement? | per-run scalar (today, `report.py:196-197`) / per-requirement | **Per run.** Follows directly from Option A, and keeps v1's JSON byte-identical. |
| **D5** | One suite per invocation, or both in one process? | A / B | **A** (§2.4). Must be recorded in `.agents/plan.md` before any code moves. |
| **D6** | Does `validation.py` move to `common/` (taking a schema accessor) or duplicate per version? | shared / duplicated | **Depends on [v2-FACT]** (§1.4). Decide after `acp-v2-status-and-delta-inventory.md` lands. Default to *duplicate* if any of the five structural assumptions changes. |
| **D7** | Are `tck.harness` / `tck.protocol` / `tck.requirements` a public API worth shims for? | shims / clean break | **Clean break.** `README.md` documents no importable API (its only mention is prose at `:105`); `AGENTS.md:459-664` documents these modules for *contributors*, not consumers; the distributed surface is the `acp-tck` console script (`pyproject.toml:18-19`). Adding shims would create exactly the ambiguity ("is `tck.protocol` v1 or v2?") the split exists to remove. |
| **D8** | Do `--tck-*` option names stay identical across versions? | yes / versioned | **Yes**, and there must be exactly one module registering them (§2.4, duplicate-`addoption` hazard). |

#### 5.1 Ordered, mechanical, zero-behaviour-change steps (v1 only; v2 is a separate slice)

Invariant for every step: `uv run pytest` green, and
`uv run acp-tck --cancel-prompt __hang__ --auth-method tck -- python tests/fixtures/agents/conforming_full.py`
still exits 0 with `VERDICT: CONFORMANT` and a byte-identical `--report-json` (modulo timestamps).
Capture a baseline report *before* step 1 and diff after each step.

1. **Create empty packages.** `src/tck/common/__init__.py`, `src/tck/v1/__init__.py`. No moves yet.
   Commit. (Proves the build backend, `[tool.uv.build-backend] module-name = "tck"`
   (`pyproject.toml:25-26`), picks up subpackages — it should, but verify before moving anything.)
2. **Move the harness** (no inbound version coupling at all): `git mv src/tck/harness
   src/tck/common/harness`. Update 8 import sites: `plugin.py:29`, `conformance/_helpers.py:13`,
   `conformance/test_transport.py:21`, `test_jsonrpc.py:20`, `test_extensibility.py:10` (+ any other
   `from tck.harness import`), `tests/conftest.py:13`, `tests/test_harness.py`,
   `tests/test_validation.py:12`. Commit.
3. **Split `requirements.py`.** `src/tck/common/requirements.py` gets `Tier`, `Requirement`, `_cite`
   is *not* moved (it closes over `SPEC_REVISION`) — instead `common` exposes
   `make_cite(revision)`. `src/tck/v1/requirements.py` gets `SPEC_REVISION`, `_DECLARATIONS`,
   `REGISTRY`, `get`. Update `report.py:34`, `plugin.py:40`, `tests/test_report.py:24`,
   `tests/test_registry.py:14-16`. Commit.
4. **Introduce `VersionSpec`** in `src/tck/common/version.py` (D1b): `protocol_version`,
   `schema_revision`, `schema_dir`, `registry`, `initialize_params()`, `conformance_package`.
   Instantiate it as `tck.v1.SPEC`. Nothing consumes it yet. Commit.
5. **Move `protocol.py` + `schema/v1/` → `src/tck/v1/`.** `SCHEMA_DIR` becomes
   `Path(__file__).parent / "schema"` (or keep the `v1` leaf for continuity with `VENDORED.md`).
   Update `validation.py:29`, `requirements.py`'s revision import, `plugin.py:30`, the six
   conformance importers, `tests/test_registry.py:15`, `tests/test_validation.py:11`. Commit.
6. **Decide D6 and place `validation.py` accordingly.** If shared: move to
   `src/tck/common/validation.py`, change `from .protocol import load_schema` to a module-level
   injected accessor or an explicit `schema` argument threaded through the four `lru_cache`d
   helpers; if duplicated: `git mv` to `src/tck/v1/validation.py` and revisit when v2 lands. Commit.
7. **Move `report.py` → `src/tck/common/report.py`** and change
   `build_requirement_results(tests_by_id)` → `build_requirement_results(tests_by_id, registry)`.
   Update `plugin.py:596`, `tests/test_report.py`. Commit.
8. **Split `plugin.py`.** `src/tck/common/plugin.py` keeps ~735 lines, reading a `VersionSpec` from
   `config.stash[VERSION_SPEC_KEY]`. `src/tck/v1/plugin.py` is a ~10-line shim:
   `from tck.common.plugin import *` plus a `pytest_configure` that stashes `tck.v1.SPEC` (and, if
   D2 says so, moves the v1 handshake body here). Resolve P1–P10 (§1.2) one at a time. Commit.
   *This is the highest-risk step; do it alone, and diff the baseline report immediately.*
9. **Move the suite:** `git mv src/tck/conformance src/tck/v1/conformance`. Update
   `src/tck/__init__.py:108,117` (the `conformance_dir`) and `:112-113` (`-p tck.v1.plugin`), and
   `tests/test_registry.py:76`'s `import tck.conformance`. Commit.
10. **Reorganise `tests/`:** `tests/common/` (`test_harness.py`, `test_report.py`,
    `test_plugin.py`, `test_cross_check_summary.py`), `tests/v1/` (`test_registry.py`,
    `test_cli.py`, `test_validation.py`), `tests/fixtures/agents/v1/`. Update `tests/conftest.py:15`
    and `tests/test_registry.py:115`'s `import test_cli`. Commit.
11. **Docs and config:** `AGENTS.md` (see 5.2), `README.md:105`, `pyproject.toml:4` (description
    says "ACP v1 agents") and `:30-33` (marker help text), `src/tck/v1/schema/VENDORED.md` paths,
    `scripts/cross-check.sh` if any path moved. Commit.

Rollback safety: every step is a `git mv` + import rewrite with the full suite as the gate. Steps
2–5, 7, 9–11 are purely mechanical; steps 6 and 8 carry design content and should be reviewed.

#### 5.2 `AGENTS.md` sections that must change

`AGENTS.md` is 49 kB and heavily path-specific. Sections requiring edits, by heading line:

| Heading | Line | Change |
|---|---|---|
| `# acp-tck` (intro) | `:1` | "currently ACP-v1-only" → describes the v1/v2 split |
| `## Layout` | `:26` | Full rewrite of the tree — this is the largest single edit |
| `## Running the TCK against an agent` | `:241` | Add the version-routing option once D5/routing is decided |
| `## Running the repo's own tests` | `:300` | New `tests/common` + `tests/v1` layout |
| `## CI` | `:311` | Paths in `.github/workflows/ci.yml` |
| `## Cross-checking against upstream agents` | `:328` | v1-pinned; note it stays v1 until v2 SDKs exist |
| `## How to add a requirement + test` | `:381` | Must now say *which version's* registry and suite |
| `## Tiers and statuses` | `:408` | Mostly unchanged if D2 = shared `Tier` |
| `## Reporting (tck.report, --report-json)` | `:423` | Unchanged if D4 = per-run scalar; note which module now owns it |
| `## Harness API (tck.harness)` | `:459` | Rename to `tck.common.harness` |
| `## Fixture agent catalogue` | `:507` | New fixture directory layout |
| `## Mock-client prompt driver (_helpers.run_prompt)` | `:548` | Now `tck.v1.conformance._helpers` |
| `## Vendored schema (tck/schema/v1/)` | `:606` | New path; add the v2 vendoring procedure |
| `` ## `tck.protocol` `` | `:620` | → `tck.v1.protocol` |
| `` ## `tck.validation` `` | `:632` | Depends on D6 |
| `## Conventions` | `:665` | "Protocol scope is ACP **v1 only**" is now false |

#### 5.3 What the first `v2/` skeleton needs

Once the v1 move is green, the minimum viable `src/tck/v2/`:

1. `src/tck/v2/schema/{schema,meta}.json` + `VENDORED.md` — vendored at a pinned v2 commit
   **[blocked on `acp-v2-status-and-delta-inventory.md` for the upstream path and hash, and on
   whether v2's schema is stable or draft]**.
2. `src/tck/v2/protocol.py` — `PROTOCOL_VERSION = 2`, its own `SCHEMA_REVISION`, its own error
   codes / stop reasons **[v2-FACT]**, and the same `load_schema`/`load_meta`/method-inventory
   derivation (copy from v1; it is ~50 lines of generic schema walking, and copying keeps each
   version readable).
3. `src/tck/v2/requirements.py` — `SPEC_REVISION` + an initially *small* `_DECLARATIONS`
   (negotiation only), so `tests/…/test_registry.py`'s "every id is referenced by a test"
   invariant can hold from day one.
4. `src/tck/v2/__init__.py` exporting `SPEC: VersionSpec`.
5. `src/tck/v2/plugin.py` — the same ~10-line shim as v1's.
6. `src/tck/v2/conformance/` with `__init__.py`, an empty `conftest.py`, `_helpers.py` (fork or
   parametrize per §3.2), and `test_initialize.py` as the first suite
   **[blocked on `acp-v2-version-negotiation.md`]**.
7. CLI routing in `src/tck/__init__.py` **[blocked on the routing decision]**.
8. A v2 fixture family under `tests/fixtures/agents/v2/` (§3.2).
9. A v2 mirror of `tests/v1/test_cli.py`'s id sets + the `test_registry` cross-check.

---

## Testability notes (how to verify the move changed nothing)

- **Golden report diff.** Before step 1, run
  `uv run acp-tck --cancel-prompt __hang__ --auth-method tck --report-json /tmp/base.json -- python tests/fixtures/agents/conforming_full.py`
  and the same against `conforming.py`. After each step, re-run and `diff` after stripping
  `started_at`/`finished_at`/`duration_s` (`src/tck/report.py:201-202`, `:69`). Every other key —
  including `protocol_version`, `schema_revision`, and all 56 requirement entries — must be
  identical. This is a stronger gate than `uv run pytest`, because it catches a registry that lost
  an entry or a tier that silently changed.
- **Exit-code matrix.** `tests/test_cli.py` already asserts exit codes for ~45 fixtures; a green run
  of that file is the single best regression signal for step 8 (the plugin split).
- **The two registry cross-checks are the safety net for step 3/9.**
  `tests/test_registry.py:93-102` (two-way marker/registry check) will fail loudly if the `pkgutil`
  walk points at the wrong package after the suite moves, and `:105-131` catches a tier drifting.
- **What is NOT observable from the self-tests:** whether `-p tck.v1.plugin` and `-p tck.v2.plugin`
  can coexist (nothing loads two plugins today), and whether two schemas in one process alias
  through `validation.py`'s caches. If Option B is ever revisited, both need a deliberate
  experiment, not an assumption.
- **A conforming split vs. a non-conforming one:** a conforming split leaves `common/` with *zero*
  occurrences of `protocolVersion`, `session/`, `initialize`, a version integer, or a schema path —
  that is a grep-able invariant worth adding as a meta-test
  (`rg -n 'protocolVersion|session/|"initialize"' src/tck/common/` must return nothing but
  docstrings). I recommend adding it as a real test in step 8.

---

## Discrepancies

1. **`AGENTS.md` / `README.md` / `pyproject.toml` all assert v1-only in prose.**
   `AGENTS.md:669` ("Protocol scope is ACP **v1 only**; v2/draft surfaces are out of scope"),
   `README.md:105`, `pyproject.toml:4` ("…ACP v1 agents"). These are not code conflicts, but they
   are three separate places the same fact is stated and they will drift if only one is updated.
   `.agents/plan.md:44-45` states the same thing a fourth time. Recommend consolidating to one
   normative statement in `AGENTS.md` with the others pointing at it.
2. **`src/tck/protocol.py:18-20` promises "start here" as the single place to change for v2, but the
   constant is read from 7 modules and the literal `1` is hardcoded in 19 more places** (§1.1). The
   docstring overstates the containment. Worth correcting during the move so the next reader is not
   misled.
3. **`Requirement.capability` is documented as "a JSON path under the `initialize` result"
   (`src/tck/requirements.py:39-41`) but is already used for non-paths** (`"inferred:modes"`,
   `"inferred:configOptions"`, `"inferred:authMethods"` — see `AGENTS.md:36-44`). Not a v1/v2
   conflict, but it means the field's contract is looser than its docstring, which matters if a v2
   registry wants a different gating encoding.
4. **No conflict found between the code and `.agents/plan.md`'s "Decided deliverable shape"** — the
   implementation matches the decisions recorded there.

---

## Open questions (for the orchestrator to route elsewhere)

1. **[owned by `acp-v2-version-negotiation.md`]** CLI routing: auto-detect via a probe `initialize`,
   an explicit `--protocol-version`, or sub-commands? This report recommends one suite per
   invocation but deliberately does not choose the selector.
2. **[owned by `acp-v2-status-and-delta-inventory.md`]** The five schema-structure facts that decide
   D6 (`validation.py` shared vs. duplicated): does v2 keep the `Agent`/`Client`/`ProtocolLevel`
   top-level `anyOf`, the `Request`/`Response`/`Notification` split, `x-method`/`x-side`, the
   `result`-bearing `AgentResponse` branch, and `CancelRequestNotification`?
3. **[owned by `acp-v2-status-and-delta-inventory.md`]** The method-inventory + `initialize`-shape
   fact that decides parametrized `_base.py` vs. `_base_v2.py` (§3.2).
4. **[owned by `acp-v2-status-and-delta-inventory.md`]** Does v2 still advertise capabilities as a
   nested object under the `initialize` result (deciding whether the `capability` marker and
   `capability_is_supported` stay in `common/` unchanged)?
5. **[owned by `reference-sdks-v2-status.md`]** Whether `scripts/cross-check.sh` gets a v2 arm at
   all, which decides whether `docs/cross-check.md` and the CI baseline assertion need a version
   dimension.
6. **Not owned by anyone yet:** should `Requirement` ids be namespaced (D3), and if so what prefix —
   `ACP-V2-…` does **not** match the existing `_ID_PATTERN` (`tests/test_registry.py:18`) because of
   the digit. Needs an explicit choice.
7. **Not owned by anyone yet:** whether the v1 `--report-json` schema should gain a forward-
   compatible marker now (e.g. always-present `protocol_version`, which it already has) so
   downstream consumers can distinguish reports — arguably already solved, but worth confirming
   against `docs/cross-check.md`'s consumers.
