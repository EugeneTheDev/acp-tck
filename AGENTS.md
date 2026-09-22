# acp-tck

A Test Compatibility Kit for the [Agent Client Protocol](https://agentclientprotocol.com) (ACP).
It launches an agent implementation as a stdio subprocess and drives it through the protocol to
check conformance -- initialize, session lifecycle, prompt turns, cancellation, error handling,
and transport hygiene -- reporting which requirements pass, fail, are not applicable, or were
never exercised.

The codebase is split into a version-agnostic core and one package per protocol version:
`src/tck/common/` (harness, report model, requirement-tier vocabulary, the pytest plugin's
version-agnostic core, and the `VersionSpec` glue between them) and `src/tck/v1/` (ACP v1's
protocol constants, vendored schema, requirement registry, schema validation, the v1 pytest
plugin shim, and the v1 conformance suite itself -- see "Layout" below). `src/tck/v2/` is the
same shape for ACP v2 (Draft): its own protocol constants, vendored schema, requirement
registry, schema validation, plugin shim, and conformance suite, sharing only the
version-agnostic `common/` core with v1 -- nothing under `v2/` imports from `v1/` or vice versa.
This split exists so `v2/` could be added without duplicating or forking the harness, report
model, or plugin machinery. v2 support now covers the `initialize` handshake, the `session/new`
baseline, (V2-2a) the mock-client prompt driver plus the core prompt-turn requirements
(`session/prompt`'s acceptance-receipt response shape, the user-message echo, and the
`running`/idle `state_update` turn-completion machinery), and (V2-2b) prompt content
capabilities (`image`/`audio`/`embeddedContext`, all object-marker-gated under
`capabilities.session.prompt.*`), the permission-request flow (`session/request_permission`),
and the agent -> client method rules (`elicitation/create` MUST NOT be called unadvertised;
every agent -> client method during a turn MUST be a defined v2 client/protocol method or
`_`-prefixed), and (V2-3) cancellation (`session/cancel`'s wire shape is unchanged from v1, but
confirmation moves to a separate terminating idle `state_update{stopReason:"cancelled"}`
notification rather than the prompt response itself), stdio transport hygiene widened for
batching (every stdout line is a JSON-RPC 2.0 object *or* a non-empty array of them), the
JSON-RPC envelope, and JSON-RPC 2.0 batching (v2 §6: empty-array/notification-only/mixed-entry
batch handling, response-array matching by id, and three record-only MAY probes), and (V2-4)
session management: `session/resume` (including replay-ordering rules for `{"type": "start"}`),
`session/list`, `session/close`/`session/delete`, `additionalDirectories`, MCP server config
(`stdio`/`http`), and `session/set_config_option` -- all `Tier.CAPABILITY` (or `INFORMATIONAL`
for the two MCP rows, unobservable without a real MCP server) and gated on the corresponding
`capabilities.session.*` marker (`configOptions` support is *inferred* from `session/new`'s own
result, like v1's `modes`/`configOptions`, not a separate capability marker), and (V2-5)
authentication: `authMethods` uniqueness (ADVISORY), the terminal-method client-capability gate
(MANDATORY -- v1's boolean `clientCapabilities.auth.terminal` becomes a nested object marker
`capabilities.auth.terminal` in v2, so this is a new id rather than a literal reuse of v1's),
`auth/login`/`auth/logout` (v2's renames of v1's `authenticate`/`logout`; login is
`Tier.CAPABILITY` mirroring v1's `authenticate` test, logout is `Tier.CAPABILITY` but replaces
v1's outright -- v2 drops the separate `agentCapabilities.auth.logout` marker entirely, so
support is inferred from `authMethods` alone, and calling it for real is gated behind a
dedicated `--allow-logout` opt-in since it may revoke the operator's own credentials), the
no-`authMethods` case (ADVISORY, re-cites v1), and two new-in-v2 MANDATORY rows: the open-enum
`type` rule on `authMethods[*].type` (`type` is a required discriminator in v2, unlike v1 where
it defaulted to `"agent"`) and the terminal auth method descriptor's `args`/`env` shape
(`env` names MUST be unique), and (V2-6) keyed upsert/patch semantics for message/tool-call/
plan/terminal updates, the open-enum emitter rule (`tck.v2.protocol.is_valid_open_enum_value`:
a value must be a defined constant or `_`-prefixed) at both a curated MUST-cited subset of
sites and the receiver-tolerance direction, and extensibility/`_meta`/schema-hygiene rows
re-cited from v1 (`ACP-EXT-001` MANDATORY; `ACP-META-001`/`ACP-ERROR-001`/`ACP-SHUTDOWN-001`/
`ACP-SCHEMA-002`/`ACP-STDERR-001`/`ACP-INFO-PARSE-001`/`ACP-INFO-INVALIDREQ-001` ADVISORY/
INFORMATIONAL) alongside three new-in-v2 hygiene rows (`ACP-META-201`, `ACP-EXT-201`,
`ACP-EXT-202`, `ACP-EXT-203`) -- gated behind `--protocol-version 2`; default remains v1 -- and is
expected to grow in later slices. Everything below is v1-specific unless a section says
otherwise.

Slices so far add an installable CLI (`acp-tck`), a requirement registry, a pytest plugin,
transport/`initialize` conformance tests, mandatory session/prompt/cancel conformance tests, full
reporting (a JSON report via `--report-json`, the four-status verdict, and a verdict-based exit
code), capability-conditional session-method tests: `session/load`, `session/resume`,
`session/list`, `session/delete`, `session/close`, and `additionalDirectories`, each gated on the
`initialize` result advertising the relevant capability, and (slice 6b) session modes/config
options (support *inferred* from `session/new`'s own response, not an `initialize` marker),
prompt content capabilities (`image`/`audio`/`embeddedContext`), and the authentication surface
(`authMethods`, `authenticate`, `logout`, plus a `--auth-method` option so the TCK can drive a
real authenticate handshake before `session/new`), and (slice 7) MANDATORY client-capability
negative tests (`fs`/`terminal`/`elicitation` MUST NOT be called unadvertised), the extensibility/
`_meta`/schema-hygiene ADVISORY family (`ACP-EXT-001` MANDATORY, `ACP-META-001`/`ACP-ERROR-001`/
`ACP-SHUTDOWN-001`/`ACP-SCHEMA-002` ADVISORY), and an INFORMATIONAL tier of report-only probes
(`ACP-STDERR-001`, `ACP-INFO-PARSE-001`, `ACP-INFO-INVALIDREQ-001`, `ACP-INFO-UNKNOWNSESSION-001`)
that never assert on the probed behaviour itself -- but still FAIL if the prerequisite handshake
they ride on top of fails -- for behaviour the spec is silent on or SDKs disagree about.

## Layout

```
src/tck/
  __init__.py            `acp-tck` console-script entry point (`main()`); argparse CLI, runs
                          the packaged v1 conformance suite (`tck.v1.conformance`) via
                          `pytest.main(...)`, loading `tck.v1.plugin` explicitly
  __main__.py            `python -m tck` -- same as the console script (used by the self-tests
                          so they don't depend on the console script being on PATH)
  common/                 version-agnostic core, shared by every protocol version's package
    __init__.py
    requirements.py        `Tier`, `Requirement`, `make_cite(revision)` -- the shared vocabulary
                          a version's own `requirements.py` builds its `REGISTRY` from.
                          Requirements gated by *inferred* support (no `initialize`-result
                          marker -- e.g. `modes`/`configOptions`, only observable in
                          `session/new`'s own response) use a documentation-only
                          `capability="inferred:modes"`/`"inferred:configOptions"` string that
                          satisfies `Requirement.__post_init__`'s invariant but is not looked up
                          by `@pytest.mark.capability(...)`/`_tck_capability_gate` -- those tests
                          instead `pytest.skip(...)` manually when the field is absent.
    version.py             `VersionSpec` -- the one object a version package (`tck.v1`) hands to
                          `tck.common.plugin` to make it version-agnostic: `protocol_version`,
                          `schema_revision`, `schema_dir`, `registry`, `initialize_params`
                          (callable), `conformance_package`. Stashed via
                          `pytest.StashKey[VersionSpec]()` (`VERSION_SPEC_KEY`, defined in
                          `plugin.py`) so `tck.common.plugin` never imports a specific version.
    plugin.py               `tck.common.plugin`: the version-agnostic pytest plugin core --
                          `--tck-*` options (including `--tck-report-json`, `--tck-auth-method`),
                          `requirement`/`capability` markers, async test support, fixtures, the
                          per-test result collector, the terminal summary table, JSON report
                          writing, and the verdict-based exit code. Reads
                          `config.stash[VERSION_SPEC_KEY]` for the active registry/protocol
                          version/schema revision -- never loaded directly (see `tck.v1.plugin`
                          below). Also holds the `_AUTH_METHOD` contextvar and
                          `current_auth_method_id()` accessor (mirrors `_ACTIVE_PROCESSES`),
                          set per-test by the autouse `_tck_auth_method_context` fixture from
                          `--tck-auth-method`; `_build_report()` scans skip messages for the
                          literal `"AUTH-GATED:"` marker to compute `Verdict.blocked_by_auth`,
                          and (V2-1b) for the literal `"VERSION-MISMATCH:"` marker to compute
                          `Verdict.blocked_by_version_mismatch` -- emitted by
                          `_tck_capability_gate` itself (not a per-version helper) whenever the
                          cached `initialize` result's negotiated `protocolVersion` doesn't
                          match the active `VersionSpec.protocol_version`, before it even checks
                          whether the marked capability path is advertised.
    report.py              the report model: `Status`, `TestOutcome`, `RequirementResult`,
                          `Verdict` (including `blocked_by_auth: bool` and, since V2-1b,
                          `blocked_by_version_mismatch: bool`), `Report` -- pure data +
                          aggregation, no pytest dependency; `build_requirement_results(...)`
                          takes the active version's `registry` as an explicit argument
    harness/
      __init__.py           public API re-exports
      process.py            AgentProcess, AgentLaunch, AgentTimeout, AgentExited
      transcript.py          TranscriptEntry, Direction
  v1/                     the ACP v1 package: protocol constants, vendored schema, requirement
                          registry, schema validation, the v1 pytest plugin shim, and the v1
                          conformance suite
    __init__.py             exports `SPEC`, the `tck.common.version.VersionSpec` instance
                          (`protocol_version=1`, this package's `SCHEMA_REVISION`/`SCHEMA_DIR`/
                          `REGISTRY`, an `initialize_params()` returning v1's handshake params,
                          `conformance_package="tck.v1.conformance"`) that `tck.v1.plugin`
                          stashes for `tck.common.plugin` to read
    protocol.py            PROTOCOL_VERSION (`1`), SCHEMA_REVISION, SCHEMA_DIR, error codes,
                          StopReason values, method inventories
    requirements.py        `SPEC_REVISION`, `_DECLARATIONS`, `REGISTRY`, `get()` -- v1's
                          concrete requirement registry, built from `tck.common.requirements`'s
                          `Tier`/`Requirement`/`make_cite(SCHEMA_REVISION)`
    validation.py          schema validation for agent-authored JSON-RPC messages, against v1's
                          vendored schema (duplicated per version rather than shared -- see
                          `.agents/research/common-v1-v2-split-analysis.md` D6)
    plugin.py               `tck.v1.plugin`: a thin shim over `tck.common.plugin` -- copies
                          every hook/fixture from `tck.common.plugin`'s namespace (via
                          `vars()`/`globals().update(...)`, not `from ... import *`, so
                          underscore-named autouse fixtures like `_tck_capability_gate` are not
                          silently dropped -- pytest discovers a plugin's hooks/fixtures via
                          `dir()`/`vars()` on the plugin module object itself), then overrides
                          `pytest_configure` to stash `tck.v1.SPEC` in
                          `config.stash[VERSION_SPEC_KEY]` before delegating to
                          `tck.common.plugin.pytest_configure`. Always load this shim, never
                          `tck.common.plugin` directly (`-p tck.v1.plugin`). Footgun: the copied
                          functions keep `__globals__` pointing at `tck.common.plugin`'s own
                          namespace, so only a function pytest resolves by name as a hook (like
                          `pytest_configure`) can actually be overridden here -- redefining a
                          plain helper such as `_build_report` in this shim would silently have
                          no effect.
    schema/
      schema.json            vendored ACP v1 JSON Schema (verbatim, do not hand-edit)
      meta.json               vendored method-name tables (verbatim, do not hand-edit)
      VENDORED.md             source repo, commit hash, date, refresh procedure
    conformance/            the v1 conformance suite itself, shipped inside the wheel
      __init__.py
      conftest.py            intentionally empty: `-p tck.v1.plugin` is always passed explicitly
      _helpers.py             `connected_agent()`, `new_session()`, `run_prompt()`/`PromptTurn` --
                            spawn + optional initialize + auto-close, plus the mock-client prompt
                            driver used by every session/prompt/cancel test
      test_transport.py       ACP-TRANSPORT-001/002 (framing, UTF-8)
      test_jsonrpc.py         ACP-JSONRPC-001..005 (id echo, result-xor-error, notifications, ...)
      test_initialize.py      ACP-INIT-001..004, ACP-SCHEMA-001 (handshake + full-exchange schema).
                            ACP-INIT-003's unsupported-version (65535) probe params carry a
                            v2-shaped `info` object alongside the v1 fields, in addition to
                            `protocolVersion`/`clientCapabilities` -- so a dual-version protocol
                            *router* agent (which selects v2 for any requested version >= 2 and
                            validates the params as a v2 `InitializeRequest`, whose `info` is
                            REQUIRED) doesn't spuriously reject the probe with `-32602` for a
                            params-shape reason unrelated to version negotiation (slice V2-0b;
                            see `router_requires_info.py` below)
      test_session.py         ACP-SESSION-001/002 (session/new sessionId, uniqueness)
      test_prompt.py          ACP-PROMPT-001..003 (stop reason, update validity, resource_link)
      test_cancel.py           ACP-CANCEL-001/002 (cancelled stop reason, no update after response)
      test_session_capabilities.py  ACP-LOAD-001..003, ACP-RESUME-001/002, ACP-LIST-001/002,
                            ACP-DELETE-001/002, ACP-CLOSE-001/002, ACP-ADDDIRS-001 --
                            capability-conditional `session/load`/`resume`/`list`/`delete`/`close`
                            and `additionalDirectories`, each gated by
                            `@pytest.mark.capability(...)` on the corresponding
                            `agentCapabilities`/`sessionCapabilities` path
      test_session_config.py  ACP-MODES-001/002, ACP-CONFIG-001/002/003 -- session `modes`/
                            `configOptions` (support inferred from `session/new`'s own response,
                            manually skipped when absent -- see `requirements.py` note above) and
                            the Req 33 negative control (no `type: "boolean"` config option
                            without `clientCapabilities.session.configOptions.boolean`)
      test_prompt_capabilities.py  ACP-PROMPTCAP-001/002/003 -- `image`/`audio`/`embeddedContext`
                            prompt content blocks, each a boolean
                            `agentCapabilities.promptCapabilities.*` gate
      test_authentication.py  ACP-AUTH-001..005 -- `authMethods` shape/uniqueness, the Req 23
                            terminal-method client-capability gate, the `authenticate` ->
                            `session/new` flow (only when `--tck-auth-method` was given; narrowed
                            to AUTH-C4's "no -32000", not full success -- ACP-SESSION-001 owns
                            general `session/new` health), `logout` (gated on the
                            `agentCapabilities.auth.logout` object marker), and AUTH-A1/
                            ACP-AUTH-005 (ADVISORY): with no `authMethods` advertised,
                            `session/new` must not fail with `-32000` -- enforced via
                            `skip_if_auth_gated` only excusing that error when `authMethods` is
                            non-empty
      test_client_capabilities.py  ACP-CLIENTCAP-001..003 (MANDATORY) -- three separate tests
                            (one per id, sharing a helper) each asserting one of
                            `fs/*`/`terminal/*`/`elicitation/create` is never observed during a
                            prompt turn run against a mock client that advertises
                            `clientCapabilities: {}` (Reqs 29, 30, 32); split from a single
                            combined test so a fixture that only calls one unadvertised surface
                            fails only that id, not all three (review-slices-5-6.md item 9)
      test_extensibility.py  ACP-EXT-001 (MANDATORY -- Req 42's MUST-respond-to-custom-methods,
                            distinct from ACP-JSONRPC-004's general SHOULD about the `-32601`
                            code), ACP-META-001 (ADVISORY -- `_meta` on `session/prompt` is
                            accepted), ACP-SCHEMA-002 (ADVISORY -- no unknown root-level keys on
                            any agent-authored request/notification `params` or response
                            `result`, via `validation.find_unknown_root_keys`)
      test_diagnostics.py    ACP-ERROR-001 (ADVISORY -- error `message` non-empty, no embedded
                            newline), ACP-SHUTDOWN-001 (ADVISORY -- `exited_on_stdin_close` after
                            an ordinary close), ACP-STDERR-001 (INFORMATIONAL -- records stderr
                            byte count; never asserts on the count itself)
      test_informational.py  ACP-INFO-PARSE-001/INVALIDREQ-001/UNKNOWNSESSION-001 (INFORMATIONAL --
                            malformed-JSON-line, structurally-invalid-request, and
                            unknown-`sessionId` behaviour, each recorded via `record_property`
                            and never asserted on directly; still FAILs if the prerequisite
                            handshake itself fails; the probed behaviour is silent in the spec
                            and real SDKs disagree; "silent" is concluded via a short
                            `quiet_period()`, never the full `--tck-timeout`)
  v2/                     the ACP v2 (Draft) package: protocol constants, vendored schema,
                          requirement registry, schema validation, the v2 pytest plugin shim,
                          and a conformance suite covering the `initialize` handshake, the
                          `session/new` baseline (slice V2-1b), the core prompt-turn lifecycle
                          (V2-2a), (V2-2b) prompt content capabilities, the permission-
                          request flow, and the agent -> client method rules, and (V2-3)
                          cancellation, stdio transport hygiene (batch-aware), the JSON-RPC
                          envelope, and JSON-RPC 2.0 batching. v2 is Draft (schema version
                          `2.0.0-alpha.5` at the vendored pin) and expected to churn -- coverage
                          here is still well short of v1 parity and expected to grow in
                          follow-up slices (session lifecycle beyond `session/new`, auth, ...).
                          Mirrors `v1/`'s shape but is its own, undiluted implementation --
                          nothing under `v2/` imports from `v1/`
                          (`.agents/research/common-v1-v2-split-analysis.md` D6: honest
                          duplication, not shared version-specific machinery).
    __init__.py             exports `SPEC` (`protocol_version=2`, this package's
                          `SCHEMA_REVISION`/`SCHEMA_DIR`/`REGISTRY`, an `initialize_params()`
                          returning v2's handshake params -- `{"protocolVersion", "info",
                          "capabilities"}`, renamed from v1's `{"protocolVersion",
                          "clientCapabilities"}` -- `conformance_package="tck.v2.conformance"`)
                          that `tck.v2.plugin` stashes for `tck.common.plugin` to read. Passes
                          `agent_info_field="info"`/`agent_capabilities_field="capabilities"`
                          to `VersionSpec` (see its docstring below) since v2 renamed both
                          `initialize`-result keys from v1's `agentInfo`/`agentCapabilities`.
    protocol.py             PROTOCOL_VERSION (`2`), SCHEMA_REVISION, SCHEMA_DIR, error codes
                          (unchanged from v1), `StopReason` values plus
                          `is_valid_open_enum_value(value, defined)` (v2's open-enum
                          extensibility rule: a defined constant, or a string beginning with
                          `_`), method inventories derived from `meta.json`/`x-side`/`x-method`
                          like v1's -- plus `PROTOCOL_METHODS` (the bidirectional
                          `$/cancel_request` notification, same as v1's own `PROTOCOL_METHODS`)
                          and `KNOWN_METHODS` (the union of all three): a new convenience union
                          v1 never needed, not a consequence of v2 having a branch v1 lacks --
                          v1's schema has the same three top-level branches
                          (`Agent`/`Client`/`ProtocolLevel`)
    requirements.py         `SPEC_REVISION`, `_DECLARATIONS`, `REGISTRY`, `get()` -- 52
                          requirements (nine from V2-1b, six V2-2a prompt-turn ids, nine
                          V2-2b additions, and 24 V2-3 additions covering cancellation
                          (`ACP-CANCEL-201..208`, `Tier.CAPABILITY` on `capabilities.session`
                          except `ACP-CANCEL-204` which is ADVISORY/record-only-unobservable, and
                          `ACP-INFO-CANCEL-201/202` INFORMATIONAL), stdio transport
                          (`ACP-TRANSPORT-002` MANDATORY, reused bare from v1 since UTF-8
                          validity is unaffected by batching; `ACP-TRANSPORT-201`/`203`
                          MANDATORY, fresh ids under D3 since 201's "object or non-empty batch
                          array" framing rule genuinely changed meaning and 203 -- no embedded
                          newlines -- has no v1 analogue at all), the JSON-RPC envelope
                          (`ACP-JSONRPC-001..005`, all reused bare from v1 under D3 -- the wire
                          assertion itself is unchanged, only the evidence-gathering probe widens
                          to cover batches -- `001..003` MANDATORY, `004`/`005` ADVISORY), and
                          JSON-RPC 2.0 batching
                          (`ACP-BATCH-201/202` MANDATORY, `203..205` ADVISORY, `206..208`
                          ADVISORY record-only MAY probes never actually judged, and
                          `ACP-INFO-BATCH-201/202` INFORMATIONAL) -- see the module's "Slice
                          V2-3" docstring for the full per-id tiering rationale and D3
                          reuse-vs-fresh-id decisions. V2-2b's nine additions:
                          `ACP-PROMPTCAP-001/002/003` (reused v1 ids, re-cited
                          to v2's `capabilities.session.prompt.{image,audio,embeddedContext}`
                          object markers), `ACP-PROMPT-003` (ADVISORY, reused from v1 --
                          `resource_link` MUST-accept vs. `content.mdx`'s text-only MUST, the
                          same unresolved doc conflict v1 already carries), `ACP-PERM-201` (new,
                          `Tier.CAPABILITY` on `capabilities.session` -- a `session/
                          request_permission` observed mid-turn must use a valid shape/outcome),
                          `ACP-CLIENTCAP-201` (new -- `elicitation/create` MUST NOT be called
                          when unadvertised), `ACP-CLIENTCAP-202` (new -- every agent -> client
                          method observed during a turn MUST be a defined v2 client/protocol
                          method or `_`-prefixed), and two new INFORMATIONAL prompt-lifecycle
                          probes, `ACP-INFO-CONCURRENT-201`/`ACP-INFO-UNKNOWNSESSION-001`, mirroring
                          v1's informational tier but re-probed against the v2 prompt-turn shape
                          -- see the module's docstring for the full id-namespacing rationale).
                          `ACP-INIT-001` (reused from v1 -- "`initialize` succeeds"
                          is truly the same requirement, only the citation's spec location
                          changes; narrowed to *only* the non-error-result check, since judging
                          a v1-shaped result against v2 schema rules would mischaracterize an
                          honestly-negotiated-down agent as broken -- schema/shape validation
                          moved entirely to `ACP-SCHEMA-001`), `ACP-INIT-201` (a new id, not
                          `ACP-INIT-002`: v1's `ACP-INIT-002` text is a single-branch "v1
                          requested, v1 returned" equality that only makes sense for a v1-only
                          TCK, whereas v2's negotiation rule is a genuine two-branch "same
                          version if supported, else the agent's own latest" rule), `ACP-INIT-003`
                          (reused from v1 -- the unsupported-version-65535-still-succeeds rule is
                          the same requirement re-cited to v2's case table row `N > M`),
                          `ACP-INIT-202` (new id -- the `N < min(S)` downgrade-must-still-succeed
                          case v1 has no counterpart for, since v1 has only one defined version)
                          -- `ACP-INIT-001`/`003`/`201`/`202` all judge only the negotiation
                          *outcome*, never the result's shape, so they are judged normally (PASS
                          on an honest downgrade) regardless of the negotiated version;
                          `ACP-INIT-203` (new id -- `info` is REQUIRED and well-formed, unlike
                          v1's optional `agentInfo`), `ACP-INIT-204` (new id -- `capabilities`,
                          when present, is an object whose known keys are themselves object
                          markers, never booleans), `ACP-SCHEMA-001` (reused from v1 -- full
                          agent-message schema validity; V2-1b scoped this to the `initialize`
                          exchange only, V2-2a extends the same test to also drive one
                          `session/new` + `session/prompt` turn -- gated on the agent having
                          advertised `capabilities.session` at all -- through `test_initialize.
                          py`'s own `run_prompt` call, so the schema check covers the update
                          stream and the prompt response too) -- these three judge the result's
                          v2-only *shape*, so
                          each calls `_helpers.skip_if_version_mismatch(...)` explicitly and
                          SKIPs with the `VERSION-MISMATCH:` marker whenever the agent negotiated
                          down to a version other than 2, rather than FAILing an agent that
                          simply doesn't speak v2 yet (see the module's "Version-mismatch-aware
                          v2-shape rows" docstring section); `ACP-SESSION-001`/`ACP-SESSION-002`
                          (reused from v1, but `Tier.CAPABILITY` here and gated on
                          `capabilities.session` -- v1's session surface is unconditional, v2's
                          is opt-in; version-mismatch-SKIPped too, via the generic
                          `_tck_capability_gate` autouse fixture) -- see the module's docstring
                          for the full id-namespacing reasoning, an instance of `.agents/plan.md`
                          decision D3
    validation.py           schema validation for agent-authored JSON-RPC messages against v2's
                          vendored schema, mirroring `tck.v1.validation`'s API
                          (`validate_agent_message`/`validate_agent_response`/
                          `find_unknown_root_keys`) but with three v2-specific differences (see
                          the module's docstring): (1) batch dispatch -- a top-level JSON array
                          is a valid message (each element validated, index-prefixed), an empty
                          array is itself an issue; (2) no `null`-result special case (unlike
                          v1's `session/load` docs/schema mismatch -- no v2 response `$def` is
                          nullable); (3) `find_unknown_root_keys` skips the unknown-key check
                          entirely for an object that matches a discriminated union's open
                          `"other"` fallback branch (e.g. a custom/future `AuthMethod` whose
                          `type` doesn't match any named branch) instead of flagging that
                          branch's intentionally-unenumerated extra fields
    plugin.py               `tck.v2.plugin`: the same thin-shim pattern as `tck.v1.plugin`,
                          stashing `tck.v2.SPEC` instead. Always load this shim (`-p
                          tck.v2.plugin`), never `tck.common.plugin` directly.
    schema/
      schema.json            vendored ACP v2 (Draft) JSON Schema (verbatim, do not hand-edit)
      meta.json               vendored method-name tables (verbatim, do not hand-edit)
      VENDORED.md             source repo, commit hash (`8f76d6c8cf...`), date, refresh
                            procedure -- notes v2 is Draft and expected to be re-vendored often
    conformance/            the v2 conformance suite, shipped inside the wheel
      __init__.py
      conftest.py            intentionally empty, same reasoning as v1's
      _helpers.py             `connected_agent()`, `new_session()` (omits `mcpServers`
                            entirely, unlike v1's `new_session` which sends an empty list --
                            v2's `session/new` params require only `cwd`),
                            `skip_if_version_mismatch(init_result)` (`pytest.skip`s with the
                            `VERSION-MISMATCH: ...` marker unless `init_result`'s negotiated
                            `protocolVersion` equals this suite's own `PROTOCOL_VERSION` (2);
                            called explicitly, not via an autouse fixture, by every v2-shape
                            test in `test_initialize.py` that has its own fresh process and
                            therefore isn't covered by `_tck_capability_gate`'s inline check),
                            and (V2-2a) the v2 mock-client prompt driver -- `run_prompt()`/
                            `PromptTurn`/`cancel_race_peek()` -- see the dedicated "v2
                            mock-client prompt driver" section below for the full v1-vs-v2
                            contrast. `connected_agent` auto-authenticates via v2's renamed
                            `auth/login` (not v1's `authenticate`) when `--tck-auth-method` was
                            given; there is still no `skip_if_auth_gated`/`quiet_period`
                            counterpart yet -- no v2 auth-flow requirement exists this slice.
                            (V2-2b) `run_prompt`'s existing permission-answering/
                            client-request-recording logic (answers `session/request_permission`
                            with the first option, or `cancelled` post-cancel; records any other
                            agent -> client request on `PromptTurn.client_requests_seen`, since
                            the mock client advertises `capabilities: {}`) needed no changes --
                            it already covers everything `ACP-PERM-201`/`ACP-CLIENTCAP-201/202`
                            need.
      test_initialize.py      ACP-INIT-001, ACP-INIT-003, ACP-INIT-201..204, ACP-SCHEMA-001 --
                            `ACP-INIT-001` (`test_initialize_succeeds`) asserts only that
                            `initialize` returns a non-error result; `ACP-INIT-003`/`ACP-INIT-201`/
                            `ACP-INIT-202` verify the two-branch version-negotiation rule holds,
                            the unsupported-version-65535 probe still succeeds, and a downgrade
                            request (`protocolVersion: 1`) still succeeds (all verified via fresh
                            processes: request `PROTOCOL_VERSION`, and request an absurd version
                            `65535` no agent implements, to establish the agent's true
                            own-latest-supported value as a reference point -- same technique
                            v1's `ACP-INIT-003` uses) -- these four judge only the negotiation
                            *outcome*, so they PASS normally even when the agent honestly
                            negotiates down to a version other than 2; `ACP-INIT-203` (`info` is
                            required and well-formed), `ACP-INIT-204` (`capabilities`'s known
                            keys, if present, are objects not booleans), and `ACP-SCHEMA-001`
                            (the whole `initialize` exchange validates against the v2 schema;
                            V2-2a additionally drives one `session/new` + `session/prompt` turn
                            via `run_prompt` -- gated on `capabilities.session` being present in
                            the `initialize` result -- and validates every `session/update`/the
                            prompt response too, closer now to v1's `ACP-SCHEMA-001` counterpart
                            which always drives a full turn) each judge the
                            result's v2-only *shape*, so each calls
                            `_helpers.skip_if_version_mismatch(msg["result"])` and SKIPs with the
                            `VERSION-MISMATCH:` marker whenever the negotiated `protocolVersion`
                            isn't 2 -- judging a v1-shaped result against v2 shape rules would
                            mischaracterize an agent that simply doesn't speak v2 as broken
      test_session.py         ACP-SESSION-001/002, both gated
                            `@pytest.mark.capability("capabilities.session")`: `session/new`
                            returns a non-empty string `sessionId` and its response validates
                            against the v2 schema; two `session/new` calls on one connection
                            return distinct ids. Note: the request-side `capabilities` field is
                            typed `ClientCapabilities` (only `auth`/`elicitation` -- no
                            `session` key at all), so unlike a naive v1-style
                            `connected_agent(..., capabilities=...)` call, these tests rely
                            solely on the marker to gate on the *agent's* advertised
                            `capabilities.session` in its `initialize` *response*, independent
                            of anything the client itself requests.
      test_prompt.py           (V2-2a) ACP-PROMPT-201, ACP-PROMPT-203, ACP-STATE-201..203,
                            ACP-PROMPT-205 -- six tests, one per id, all `Tier.CAPABILITY`
                            (`capability="capabilities.session"`, matching ACP-SESSION-001/002 --
                            `session/prompt` is part of the seven-method baseline an agent
                            commits to by advertising `capabilities.session` at all; corrected
                            from an initial MANDATORY tier, see `requirements.py`'s module
                            docstring) and `@pytest.mark.capability("capabilities.session")`-
                            gated, driving a single short (`"hi"`) `run_prompt` turn each: the
                            `session/prompt` response is an acceptance receipt with a non-empty
                            string `messageId` (`ACP-PROMPT-201`); a `user_message`/
                            `user_message_chunk` update echoes that same `messageId`
                            (`ACP-PROMPT-203`, SKIPs if `ACP-PROMPT-201` already found no usable
                            `messageId` to check the echo against); a turn-ending idle is always
                            preceded by `running` for that session (`ACP-STATE-201`, SKIPs as "no
                            turn-ending idle observed" only when the turn never reached a
                            stop-reason-bearing idle at all -- a turn-ending idle with no
                            preceding `running` FAILs this row rather than SKIPping it, unlike
                            the next two); an idle follows an observed `running` within the
                            turn's own `--timeout` (`ACP-STATE-202`) and that idle's `stopReason`
                            is a defined constant or a valid `_`-prefixed extension
                            (`ACP-STATE-203`) -- both SKIP as "no foreground work observed" when
                            `running` itself was never observed; every `session/update` for the
                            turn validates against the v2 schema and carries the prompted
                            session's own `sessionId` (`ACP-PROMPT-205` -- same check as v1's
                            `ACP-PROMPT-002` but a fresh id, since a `Tier.MANDATORY` ->
                            `Tier.CAPABILITY` change is a changed requirement under D3;
                            vacuously PASSing if the turn sent no updates at all). (V2-2b)
                            `ACP-PROMPT-003` also lives here: an ADVISORY `resource_link` content
                            block, alongside `text`, must be accepted (not rejected) in a prompt.
      test_prompt_capabilities.py  (V2-2b) ACP-PROMPTCAP-001/002/003 -- one test per
                            `image`/`audio`/`embeddedContext` content block, each gated
                            `@pytest.mark.capability("capabilities.session.prompt.<name>")`:
                            sends a prompt containing that content-block type and asserts the
                            agent accepts it (no JSON-RPC error) rather than rejecting it despite
                            having advertised support.
      test_permission.py      (V2-2b) ACP-PERM-201 (`Tier.CAPABILITY` on `capabilities.session`):
                            drives a turn and, if (and only if) `run_prompt`'s mock client
                            observed a `session/request_permission` request during it, asserts
                            its shape (a non-empty `options` list, each with a `optionId`) --
                            SKIPs with "no permission request observed during this turn" for any
                            fixture/agent whose turn never asks for permission at all (`text`-only
                            prompts to `conforming.py`, for instance).
      test_client_capabilities.py  (V2-2b) ACP-CLIENTCAP-201/202: one test asserting
                            `elicitation/create` is never observed in
                            `PromptTurn.client_requests_seen` (the mock client always advertises
                            `capabilities: {}}`, so any occurrence is unadvertised) and a second
                            asserting every method actually observed there is either a defined
                            v2 client/protocol method (`tck.v2.protocol.CLIENT_METHODS` union
                            `PROTOCOL_METHODS`) or `_`-prefixed (the open-enum extensibility
                            rule) -- v2 has no `fs/*`/`terminal/*` client surface at all, so a
                            v1-shaped probe using those method names is exactly what
                            `ACP-CLIENTCAP-202` exists to catch.
      test_informational.py   (V2-2b) ACP-INFO-CONCURRENT-201/ACP-INFO-UNKNOWNSESSION-001 --
                            report-only probes (`record_property`, never asserted on) for
                            concurrent-prompt and unknown-`sessionId` behaviour the v2 spec is
                            silent on; still FAILs if the prerequisite handshake itself fails.
      test_cancel.py           (V2-3) ACP-CANCEL-201..208, ACP-INFO-CANCEL-201/202. v2 moves
                            cancel confirmation off the prompt response entirely: `session/
                            cancel`'s own wire shape is unchanged from v1, but the turn now
                            resolves via a separate terminating idle `state_update{stopReason:
                            "cancelled"}` notification (`ACP-CANCEL-201`, `Tier.CAPABILITY` on
                            `capabilities.session`, mirroring V2-2a's prompt-turn tiering
                            rationale). `ACP-CANCEL-202`: no further `state_update` for that
                            session after the cancelled idle -- SKIPs with "prerequisite not
                            met" whenever `ACP-CANCEL-201` itself didn't observe a `cancelled`
                            idle to check "after" (own race-window/prerequisite handling, same
                            shape as v1's `test_cancel.py`). `ACP-CANCEL-203`: cancellation must
                            not surface as a generic JSON-RPC error either on the prompt response
                            or the cancel notification's own (nonexistent) response.
                            `ACP-CANCEL-204` (ADVISORY, always SKIPped): "as soon as possible"
                            promptness has no wire-level signal a client-only TCK can check.
                            `ACP-CANCEL-205`: `session/cancel` itself, being a notification,
                            receives no direct JSON-RPC response. `ACP-CANCEL-206`: a
                            `session/cancel` carrying `_meta` is still accepted and honoured.
                            `ACP-CANCEL-207`: `session/close` on a session with in-flight work
                            also resolves that work via a `cancelled` idle. `ACP-CANCEL-208`:
                            behaviour when there is no foreground work to cancel (e.g. cancelling
                            an idle session) is at least well-formed, never a generic error.
                            Every CAPABILITY-tier test here shares v1's own "cancel race" honesty
                            discipline (`cancel_race_peek`/`quiet_period`, ported from
                            `tck.v1.conformance._helpers`, not imported from it -- D6): SKIPs
                            rather than judges whenever the turn resolves before `session/cancel`
                            could be sent, or resolves with a valid non-cancelled `stopReason`
                            inside the race window. `ACP-INFO-CANCEL-201/202` (INFORMATIONAL,
                            `record_property`-only): cancelling a session with no foreground work,
                            and cancelling mid-permission-request, respectively.
      test_transport.py       (V2-3) ACP-TRANSPORT-002, ACP-TRANSPORT-201, ACP-TRANSPORT-203 --
                            batch-aware counterpart of v1's `test_transport.py` (D6).
                            `ACP-TRANSPORT-201`: every stdout line is exactly one JSON-RPC 2.0
                            object *or* a non-empty array of them (widened from v1's
                            single-object-only rule, hence a fresh id rather than a reused
                            `ACP-TRANSPORT-001` under D3 -- the meaning genuinely changed).
                            `ACP-TRANSPORT-002`: UTF-8 decoding, unaffected by batching, so this
                            reuses v1's own id bare -- the meaning did not change.
                            `ACP-TRANSPORT-203`: no embedded literal newlines (a batch array is
                            itself one line too) -- new to v2, no v1 analogue to reuse.
                            `_drive_full_exchange` does its own manual `initialize` and calls
                            `skip_if_version_mismatch` before ever touching `session/new`/
                            `run_prompt`, on the same connection -- not because framing/UTF-8/
                            newline rules are themselves v2-only, but so a version-mismatched
                            agent (which will never emit the `running`/`idle` pair `run_prompt`
                            waits on) SKIPs cleanly instead of hanging until `--tck-timeout` and
                            FAILing every row here (see the module's docstring for the exact
                            `AgentTimeout` this fixed). Consequence for
                            `tests/v2/test_cli.py`: unlike `ACP-JSONRPC-001..005`, these three
                            ids are *not* in `_VERSION_TOLERANT_IDS` -- they SKIP, not PASS,
                            against an honestly-downgrading v1 agent forced under
                            `--protocol-version 2`.
      test_jsonrpc.py          (V2-3) ACP-JSONRPC-001..005 (MANDATORY 001..003, ADVISORY
                            004/005) -- v2's JSON-RPC envelope rules (id echo, result-xor-error,
                            notification handling, `-32601` on unknown methods, connection
                            survives an error) are each byte-identical in *meaning* to their v1
                            counterparts of the same number, so every one of them reuses its v1
                            id bare under D3 -- only the evidence-gathering probe widens to also
                            cover a batch-delivered response/notification/erroneous-batch. None
                            of these tests drives a v2-shaped `session/prompt` turn or calls
                            `skip_if_version_mismatch`, so they judge an agent's ordinary
                            handshake/notification traffic the same way regardless of negotiated
                            version -- the reason they PASS (not SKIP) against a v1 agent forced
                            under `--protocol-version 2`.
      test_batch.py            (V2-3) ACP-BATCH-201..208, ACP-INFO-BATCH-201/202 -- JSON-RPC 2.0
                            batching (v2 §6). New to v2 -- v1 has no batching at all, so none of
                            these ids reuse a v1 number (D3 does not apply). `ACP-BATCH-201`
                            (MANDATORY): an empty batch array `[]` gets exactly one top-level
                            `-32600`/`id: null` Invalid Request object, never silence and never a
                            per-entry response. `ACP-BATCH-202` (MANDATORY): a notification-only
                            batch produces no output at all. `ACP-BATCH-203` (ADVISORY): a batch
                            mixing one structurally invalid entry with one well-formed sibling
                            gets a per-entry `-32600`/`id: null` for the invalid one without
                            blocking the valid sibling's own reply. `ACP-BATCH-204`/`205`
                            (ADVISORY, shared test -- identical wire evidence, neither the sole
                            cause of a failing verdict): a batch containing at least one request
                            gets back one array of the corresponding response objects, matched by
                            `id` rather than array position (`205`'s "any order" MAY is exactly
                            why the test matches by id). `ACP-BATCH-206..208` (ADVISORY,
                            record-only, always SKIPped): concurrent-processing order is
                            unobservable from a client-side TCK, an agent can't be forced to
                            spontaneously emit its own batch, and lifecycle-batching restraint is
                            a sender property a receiver-only TCK can't probe. `ACP-INFO-
                            BATCH-201/202` (INFORMATIONAL): a malformed top-level JSON-array-shaped
                            line, and a batch mixing a call-shaped and a response-shaped entry,
                            respectively -- both silent on the spec, `record_property`-only.
                            Every test here calls `skip_if_version_mismatch` on its own manual
                            `initialize` (own local `_v2_only_agent` helper, not promoted to
                            `_helpers.py`), same reasoning as `test_transport.py` above; each
                            probe also uses its own fresh connection, since a batch line is
                            exactly the kind of traffic that could crash a less battle-tested
                            agent implementation, and isolating each probe means one crash can't
                            cascade into or pollute a sibling assertion.

      test_session_capabilities.py  (V2-4) ACP-SESSION-203, ACP-RESUME-201..205, ACP-LIST-201..204,
                            ACP-CLOSE-201, ACP-DELETE-201..203, ACP-ADDDIRS-201/202,
                            ACP-MCP-201/202 -- v2 session management, all `Tier.CAPABILITY` (MCP's
                            two rows `Tier.INFORMATIONAL` -- unobservable without a real MCP
                            server to point the agent at) and gated on the matching
                            `capabilities.session.*` marker. `ACP-SESSION-203` (`session/new`
                            still returns a fresh, unique `sessionId` when `capabilities.session`
                            is advertised -- v1's `ACP-SESSION-001`/`002` reused verbatim would
                            not be gated at all, since v1's session surface is unconditional).
                            `ACP-RESUME-201` (`session/resume` succeeds for a resumable id).
                            `ACP-RESUME-202` (MUST reply only after any requested replay, unlike
                            v1's `session/load`, which docs additionally require to reply *before*
                            replaying -- v2 inverts the order). `ACP-RESUME-203` (MUST NOT replay
                            when `replayFrom` is omitted/`null`). `ACP-RESUME-204`/`205` (replayed
                            `{"type": "start"}` history preserves the original `user_message`'s
                            `messageId` and ordering relative to the agent's own updates --
                            ordering only, never that history exists at all, per
                            `.agents/plan.md`'s binding decision). A resumable session id is
                            obtained via a shared `_session_with_history` helper that tries three
                            routes in order (a fresh `session/new` plus one plain prompt turn; a
                            `session/new` immediately followed by `session/resume` on that same
                            id, if the first route's prompt hangs; a raw `session/resume` on a
                            synthesized id) and `pytest.skip`s "no resumable session obtainable"
                            if all three fail -- unless the agent rejected the attempt with
                            `-32601` (method not found), which FAILs instead of skipping, since a
                            capability-advertising agent that doesn't implement the method at all
                            is a real defect, not an unlucky race. `ACP-LIST-201..204`
                            (`session/list` returns exactly the sessions created under the query
                            `cwd`, `[]` -- never an error -- when none match, a `nextCursor` that
                            is either absent or itself resolves via a second call, and each
                            entry's shape). `ACP-CLOSE-201` (`session/close` succeeds for an idle
                            session). `ACP-CLOSE-202` is *not* its own test here: slice V2-4
                            re-mints it onto `test_cancel.py`'s existing
                            `test_close_cancels_foreground_work` (`ACP-CANCEL-208`) as a second,
                            deliberate `@pytest.mark.requirement(...)` id on the exact same wire
                            evidence -- `session/close` MUST cancel foreground work first is the
                            same assertion under two numbers (v1's `ACP-CLOSE-002` precedent).
                            `ACP-DELETE-201` (`session/delete` succeeds for an existing
                            session). `ACP-DELETE-202` (the deleted session no longer appears in
                            a subsequent `session/list` -- SKIPs if the session was never observed
                            in `session/list` to begin with, nothing to compare against).
                            `ACP-DELETE-203` (ADVISORY: deleting an already-deleted or
                            never-created sessionId SHOULD succeed silently, not error). All
                            three gated on `capabilities.session.delete`. `ACP-ADDDIRS-201`/`202`
                            (`additionalDirectories` accepted on `session/new`; the agent must
                            not error solely because the directory doesn't exist locally, per the
                            spec's own wording). `ACP-MCP-201`/`202` (INFORMATIONAL: `stdio`- and
                            `http`-shaped `mcpServers` entries on `session/new` are accepted
                            without error -- gated on `capabilities.session.mcp.stdio`/`http`
                            purely to decide whether to run the probe at all, not to score a
                            capability failure, since the TCK cannot start a real MCP server to
                            observe the agent actually using it).
      test_session_config.py  (V2-4) ACP-CONFIG-201..204, ACP-CONFIG-206 -- session
                            `configOptions`, support *inferred* from `session/new`'s own result
                            (mirrors v1's `modes`/`configOptions` inference; no separate
                            `capabilities` marker exists for it) via `capability=
                            "inferred:configOptions"`, a documentation-only string not looked up
                            by the autouse capability gate -- each test instead opens its own
                            connection through a local `_v2_only_agent` async context manager
                            (one manual `initialize` plus `skip_if_version_mismatch`, mirroring
                            `test_batch.py`'s pattern) and `pytest.skip`s manually when
                            `session/new`'s result carries no `configOptions` at all. `ACP-
                            CONFIG-201` (shape: each entry's `id`/`type`/current value are
                            well-formed). `ACP-CONFIG-202` (`session/set_config_option` MUST
                            return the *complete* updated `configOptions` list, not just the
                            changed entry). `ACP-CONFIG-203`/`204` (setting a `select`-typed
                            option to one of its own listed values succeeds; setting it to a
                            value outside that list is rejected). `ACP-CONFIG-206` (a
                            `currentConfigOptionsUpdate` notification, if the agent chooses to
                            send one on its own initiative, validates against the v2 schema).
      test_authentication.py  (V2-5) ACP-AUTH-201..207 -- `authMethods` shape, the terminal-
                            method client-capability gate, the `auth/login`/`auth/logout`/
                            `session/new` flow, and the open-enum `type` rule. A local
                            `_initialized_agent` async context manager (one manual `initialize`,
                            optionally with a `capabilities` override, plus
                            `skip_if_version_mismatch`) is used throughout since most of these
                            tests need to inspect the `initialize` result itself. `ACP-AUTH-201`
                            (ADVISORY; re-cites v1's `ACP-AUTH-001`, field renamed `id` ->
                            `methodId`). `ACP-AUTH-206` (MANDATORY, new in v2: every
                            `authMethods[*].type` is `"agent"`, `"terminal"`, or `_`-prefixed --
                            `type` is a required discriminator in v2, unlike v1 where it defaulted
                            to `"agent"`). `ACP-AUTH-202` (MANDATORY, new id -- NOT a reuse of v1's
                            `ACP-AUTH-002`, since the wire encoding changed: v1's gate was the
                            top-level boolean `clientCapabilities.auth.terminal`, v2's is the
                            nested object marker `capabilities.auth.terminal`; asserted on the
                            default connection, which never advertises it). `ACP-AUTH-207`
                            (MANDATORY, new in v2 -- no v1 analogue: on a *second*, dedicated
                            connection that does advertise `capabilities.auth.terminal: {}`,
                            every `type: "terminal"` entry's `args`/`env` shape is valid and
                            `env` names are unique; SKIPs if no terminal entry appears at all).
                            `ACP-AUTH-204` (CAPABILITY, `capability="inferred:authMethods"` --
                            mirrors v1's `ACP-AUTH-003` exactly, method renamed `authenticate` ->
                            `auth/login`; needs `--tck-auth-method`, SKIPs otherwise since the TCK
                            cannot guess a valid `methodId`). `ACP-AUTH-205` (ADVISORY; re-cites
                            v1's `ACP-AUTH-005`/AUTH-A1: no `authMethods` at all means
                            `session/new` must not fail `-32000`). `ACP-AUTH-203` (CAPABILITY,
                            `capability="inferred:authMethods"` -- replaces v1's `ACP-AUTH-004`
                            outright, since v2 drops the separate `agentCapabilities.auth.logout`
                            marker entirely and infers support from `authMethods` alone; runs ONLY
                            with `--allow-logout`/`--tck-allow-logout`, since actually calling
                            `auth/logout` may revoke the operator's own credentials -- SKIPs with
                            reason `"auth/logout not exercised: pass --allow-logout (it may revoke
                            the operator's credentials)"` otherwise).
      test_patches.py          (V2-6) ACP-PATCH-201, ACP-PATCH-203..209 -- keyed upsert/patch
                            semantics (`.agents/research/acp-v2-patches-enums-extensibility.md`
                            "Patch/upsert -- new family"). `ACP-PATCH-202` is deliberately not
                            registered: it duplicates `ACP-PROMPT-201` + `ACP-PROMPT-203`
                            combined (D3). `ACP-PATCH-201/203/204/205/206/207` are
                            `Tier.CAPABILITY`/`capabilities.session` (session-baseline tiering
                            rule); `ACP-PATCH-208/209` stay `Tier.ADVISORY`/`capability=None`,
                            with only the test itself capability-gated. `ACP-PATCH-201`: every
                            message-kind update carries a non-empty string `messageId`.
                            `ACP-PATCH-203`: two prompts on one session never cross-contaminate
                            message ids. `ACP-PATCH-204/205/206/207`: `tool_call_update`/
                            `plan_update`/`terminal_update`/`terminal_output_chunk` each carry
                            their own required key (`toolCallId`/`planId`/absolute `cwd`/output
                            bytes), each SKIPping "no `<variant>` observed" rather than PASSing
                            or FAILing on evidence that was never produced -- neither `testy` nor
                            `echo_agent` yet exercises tool calls/plans/terminals over v2 (report
                            D5), so these only PASS for real against `conforming_full.py` (opted
                            into `emit_rich_turn_updates=True`) and its defect fixtures.
                            `ACP-PATCH-208`: the first observed `tool_call_update` for a given
                            `toolCallId` is a create (not a bare patch). `ACP-PATCH-209`: a
                            `requires_action`/`running` state_update pair brackets a
                            `session/request_permission` round-trip.
      test_enums.py            (V2-6) ACP-ENUM-201..203 -- open-enum emitter rules
                            (`.agents/research/acp-v2-patches-enums-extensibility.md` "Open
                            enums -- new family", B.1/B.2/B.5), enforced via
                            `tck.v2.protocol.is_valid_open_enum_value` (a defined constant OR
                            `_`-prefixed) since the schema itself accepts any string at these
                            sites. The re-worded v1 `ACP-PROMPT-001` is deliberately not
                            re-registered: already fully covered by `ACP-STATE-203` (D3).
                            `ACP-ENUM-201` (`Tier.CAPABILITY`/`capabilities.session`, promoted
                            from the report's MANDATORY): a curated subset of dedicated-prose
                            sites -- `ToolKind`, `ToolCallStatus`, `PlanEntryPriority`/
                            `PlanEntryStatus`. `ACP-ENUM-202` (`Tier.ADVISORY`,
                            `capability=None`, test capability-gated): three no-dedicated-prose
                            sites -- `SessionUpdate.sessionUpdate`, `StateUpdate.state`,
                            `ToolCallContent.type`. `ACP-ENUM-203` (same tier/gating):
                            receiver-tolerance direction -- the client sends a `_`-prefixed
                            permission-outcome value and the agent must not crash or `-32602`;
                            drives its own minimal hand-rolled turn (no hook in `run_prompt()`
                            for a non-standard outcome), and unwraps JSON-RPC batch-array lines
                            the same way `_helpers.run_prompt` does, so a spontaneously-batching
                            but otherwise conformant agent doesn't spuriously FAIL just because
                            its terminating idle arrived inside a batch.
      test_extensibility.py  (V2-6) `ACP-EXT-001`/`ACP-META-001` (re-cited from v1 unchanged,
                            `capability=None` on the registry; `ACP-META-001`'s own test still
                            carries `@pytest.mark.capability("capabilities.session")` since it
                            drives a real turn), `ACP-SCHEMA-002` (re-cited, v2 carve-out already
                            in `tck.v2.validation.find_unknown_root_keys`; its own test is also
                            capability-gated, since it sweeps a full `session/new` +
                            `session/prompt` exchange), and the new hygiene rows `ACP-META-201`
                            (ADVISORY, capability-gated test, not promoted: every `_meta` value
                            anywhere in the transcript is an object or `null`), `ACP-EXT-201`
                            (ADVISORY: an unrecognized `_`-prefixed notification produces no
                            response), `ACP-EXT-202` (ADVISORY: vendor extensions live under
                            `capabilities._meta`, not a new root key of `capabilities` itself --
                            checked via a *nested* `find_unknown_root_keys` against the
                            `AgentCapabilities` `$def`), `ACP-EXT-203` (INFORMATIONAL,
                            `record_property`-only: behaviour on an unrecognized `$/`-prefixed
                            protocol notification, which the spec says the agent is free to
                            ignore). `ACP-EXT-001`/`ACP-EXT-201`/`ACP-EXT-203` need only one
                            ordinary custom-method/notification exchange -- no `session/new`,
                            no `capabilities` shape -- so `tests/v2/test_cli.py`'s
                            `_VERSION_TOLERANT_IDS` includes all three: they PASS, not SKIP,
                            against a v1 agent forced under `--protocol-version 2`.
                            `ACP-EXT-202` reads `result.capabilities` (the v2 field name)
                            directly and is NOT in that set: a v1-negotiated result has no such
                            key at all (v1 uses `agentCapabilities` instead), so it genuinely
                            `pytest.skip(...)`s on its own -- not via the `VERSION-MISMATCH:`
                            marker, but still a skip.
      test_diagnostics.py    (V2-6) `ACP-ERROR-001`/`ACP-SHUTDOWN-001`/`ACP-STDERR-001`
                            (re-cited from v1 unchanged: `Error` `$def` is byte-identical, v2
                            still has no dedicated shutdown method, and the spec has nothing to
                            say about stderr in either version). All connection-level,
                            `capability=None`, no capability marker on the test either -- each
                            succeeds at the wire level regardless of negotiated version (v1's
                            `conforming.py` implements `session/new` unconditionally), so all
                            three are also in `_VERSION_TOLERANT_IDS`.
      test_informational.py   (V2-6 extends V2-2b) adds `ACP-INFO-PARSE-001`/
                            `ACP-INFO-INVALIDREQ-001` (re-cited from v1 unchanged -- version-
                            agnostic transport-level probes with nothing v2-specific to revisit)
                            alongside the existing `ACP-INFO-CONCURRENT-201`/
                            `ACP-INFO-UNKNOWNSESSION-001`. The two new probes carry no
                            capability marker either (their shared `_probe_connection_usable_
                            after` helper swallows a `session/new` failure -- including a
                            version-mismatch/capability-unsupported one -- into an "unusable"
                            behaviour string rather than letting it propagate, then only ever
                            `record_property(...)`s it, never asserts), so both are also in
                            `_VERSION_TOLERANT_IDS`.

tests/
  conftest.py              agent_launch() helper for spawning fixture agents under
                          `tests/fixtures/agents/v1/` (harness unit tests); a directory-scoped
                          conftest, so it applies to both `tests/common/` and `tests/v1/` below
  common/                 unit tests for the version-agnostic core
    test_harness.py         unit tests for `tck.common.harness`, run against the v1 fixtures below
    test_report.py          `tck.common.report` unit tests: aggregation, verdict rule, JSON
                          round-trip
    test_plugin.py          unit tests for `tck.common.plugin` helpers (e.g.
                          `capability_is_supported`)
    test_cross_check_summary.py  unit tests for `scripts/cross-check-summary.py`
  v1/                     unit tests specific to the v1 package
    test_validation.py      unit tests for `tck.v1.protocol` / `tck.v1.validation`
    test_registry.py         `tck.v1.requirements.REGISTRY` invariants + two-way check against
                          `tck.v1.conformance` markers
    test_cli.py               end-to-end: run `python -m tck -- <fixture>` as a subprocess,
                            including `--report-json` output and exit codes
  v2/                     unit tests specific to the v2 (Draft) package; a `tests/v2/__init__.py`
                          (empty) is required alongside this directory so pytest's import-mode
                          module naming (`v2.test_cli`, etc.) doesn't collide with `tests/v1/`'s
                          same-named modules
    test_validation.py      unit tests for `tck.v2.validation`'s three v2-specific behaviors:
                          batch root dispatch, no `null` special case for responses, and the
                          `find_unknown_root_keys` open-fallback carve-out
    test_registry.py         `tck.v2.requirements.REGISTRY` invariants (all 106 ids: the nine
                          from V2-1b, V2-2a's six prompt-turn ids, V2-2b's nine
                          `ACP-PROMPTCAP-001/002/003`/`ACP-PROMPT-003`/`ACP-PERM-201`/
                          `ACP-CLIENTCAP-201/202`/`ACP-INFO-CONCURRENT-201`/
                          `ACP-INFO-UNKNOWNSESSION-001`, V2-3's 24 cancellation/transport/
                          JSON-RPC/batching ids, V2-4's 24 session-management ids --
                          `ACP-SESSION-203`, `ACP-RESUME-201..205`, `ACP-LIST-201..204`,
                          `ACP-CLOSE-201/202`, `ACP-DELETE-201..203`, `ACP-ADDDIRS-201/202`,
                          `ACP-MCP-201/202`, `ACP-CONFIG-201..204`/`206` --, V2-5's seven
                          `ACP-AUTH-201..207`, and V2-6's 23 patch/enum/extensibility ids: 15 new
                          (`ACP-PATCH-201`/`203..209`, `ACP-ENUM-201..203`, `ACP-META-201`,
                          `ACP-EXT-201..203`) plus eight bare re-cites from v1
                          (`ACP-EXT-001`, `ACP-META-001`, `ACP-ERROR-001`, `ACP-SHUTDOWN-001`,
                          `ACP-SCHEMA-002`, `ACP-STDERR-001`, `ACP-INFO-PARSE-001`,
                          `ACP-INFO-INVALIDREQ-001`)) + two-way check against
                          `tck.v2.conformance` markers
    test_cli.py               end-to-end: run `python -m tck --protocol-version 2 --
                            <fixture>` as a subprocess; routing checks (`--help`, and that the
                            default/`--protocol-version 1` path still runs the v1 suite
                            unchanged); the v2 conforming fixture PASSing every id it exercises
                            (V2-2b's `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201` SKIP against the
                            plain `conforming.py` fixture, since it neither advertises prompt
                            content capabilities nor ever asks permission; V2-3's
                            `_CANCEL_RACE_SKIP_IDS` also legitimately SKIP without a
                            `--cancel-prompt` override, since `conforming.py`'s short turns
                            resolve before the TCK can act on `session/cancel`); `conforming_
                            full.py` (V2-2b, extended by V2-4 with every session-management
                            capability, and by V2-6 with `emit_rich_turn_updates=True` plus every
                            auth/logout capability) PASSing literally every one of the 106 ids
                            when run with `--cancel-prompt
                            __hang__` (V2-3's cancellation tests need a
                            turn that is still in flight when `session/cancel` lands, exactly
                            like v1's own `--cancel-prompt` convention); one test per defect
                            fixture asserting its exact FAIL set (V2-2a adds eight: the
                            single-defect `bad_stop_reason.py`/`vendor_stop_reason.py`/
                            `no_running_update.py`/`no_idle_after_running.py`/
                            `idle_before_running.py`/`echo_wrong_message_id.py`/
                            `missing_message_id.py`/`update_wrong_session.py` fixtures under
                            `fixtures/agents/v2/`, run with a short `--tck-timeout` where the
                            fixture is designed to hang until it -- see the fixture catalogue
                            below; V2-2b adds four more: `rejects_image_when_advertised.py`,
                            `calls_elicitation_unadvertised.py`, `calls_fs_unadvertised.py`
                            (whose defect also cascades into `ACP-SCHEMA-001`, since
                            `fs/read_text_file` isn't a known v2 method at all -- the same
                            documented defect-cascades-into-schema pattern `ACP-INIT-204` already
                            uses), and the positive control `calls_custom_method.py`; V2-3 adds
                            five more: `cancel_no_idle.py`, `cancel_returns_error.py`,
                            `cancel_wrong_stop_reason.py`, `rejects_batch.py`, and `crashes_on_
                            batch.py`; V2-4 adds seven more, each a single-defect variant of
                            `conforming_full.py`'s session-management surface:
                            `resume_replays_when_not_asked.py` (FAILs only `ACP-RESUME-203`),
                            `resume_responds_before_replay.py` (FAILs only `ACP-RESUME-202`;
                            `ACP-RESUME-204` SKIPs -- no replayed update ever arrives before the
                            response for it to inspect), `resume_replay_missing_message_id.py`
                            (FAILs only `ACP-RESUME-204`), `list_errors_when_empty.py` (FAILs only
                            `ACP-LIST-202` -- `session/list` errors instead of returning `[]` when
                            no session matches the query `cwd`), `close_no_cancel_idle.py` (FAILs
                            `ACP-CANCEL-208` and `ACP-CLOSE-202` together, since both are bound to
                            the same test -- `session/close` does not cancel the in-flight turn
                            first), `advertises_delete_but_errors.py` (advertises
                            `capabilities.session.delete` but always errors on `session/delete` --
                            FAILs `ACP-DELETE-201`/`202`/`203`, a `Tier.CAPABILITY` FAIL that
                            flips the verdict to NOT CONFORMANT), and `config_partial_list.py`
                            (FAILs only `ACP-CONFIG-202` -- `session/set_config_option` returns
                            only the changed entry instead of the complete `configOptions` list));
                            every single-defect fixture whose defect applies to
                            *every* prompt (not just one targeted scenario) was found, by running
                            each self-test in isolation and reading its printed per-id table
                            rather than by reasoning from the fixture's own docstring alone, to
                            cascade into every other test that also drives a `run_prompt` turn on
                            the same connection -- `bad_stop_reason.py`/`vendor_stop_reason.py`/
                            `no_idle_after_running.py`/`idle_before_running.py`/`update_wrong_
                            session.py`'s self-tests were all widened accordingly once V2-3 added
                            new call sites (cancellation/transport tests) onto the same shared
                            `run_prompt` codepath V2-2a/V2-2b's tests already used; V2-4 widened
                            the same fixtures' self-tests a second time, since `ACP-RESUME-
                            202..205`'s own tests each obtain a resumable session via
                            `_session_with_history`, which itself drives an ordinary `run_prompt`
                            turn first -- so any fixture whose defect breaks *every* prompt turn
                            (`no_idle_after_running.py`, `update_wrong_session.py`,
                            `cancel_no_idle.py`, `cancel_returns_error.py`,
                            `cancel_wrong_stop_reason.py`) FAILs those four RESUME ids too, on top
                            of whatever it already failed; `ACP-CLOSE-202` is dual-bound to the
                            exact same test as `ACP-CANCEL-208` (see `test_cancel.py` above), so
                            it FAILs/PASSes in lockstep with it everywhere; and
                            `echo_wrong_message_id.py`'s wrong-`messageId` defect is not just a
                            cascade artifact but a second, independent manifestation of the same
                            underlying bug: the corrupted id is what gets stored and later
                            replayed by `session/resume`, so `ACP-RESUME-204`'s own check
                            genuinely fails too, not merely because a prerequisite turn broke; two
                            further unanticipated cross-family cascades worth calling out
                            specifically (both pre-existing, from V2-3):
                            `vendor_stop_reason.py` additionally SKIPs (not PASSes) `ACP-CANCEL-
                            202`, since that id's own test requires the `ACP-CANCEL-201`
                            prerequisite (`stopReason: "cancelled"`) to have actually happened
                            before it can check "no further update after it" -- which never
                            occurs when every turn ends with the vendor-prefixed `"_tck/
                            throttled"` instead; `idle_before_running.py` additionally FAILs
                            (ADVISORY, so the verdict stays CONFORMANT) `ACP-BATCH-204`/`205`,
                            because its `_handle_new_session` override fires its unsolicited
                            ready-idle notification as an immediate side effect of handling
                            `session/new` even when `session/new` arrives inside a batch, so that
                            notification line lands on stdout ahead of the batch's own combined
                            response array; and the version-mismatch scenario (the v1 conforming
                            fixture run under `--protocol-version 2`: the negotiation-outcome ids
                            -- `ACP-INIT-001`/`003`/`201`/`202` -- plus V2-3's five `ACP-JSONRPC-
                            001..005` ids (together, `_VERSION_TOLERANT_IDS`) PASS normally
                            against the honestly-downgraded-to-`1` response, since none of their
                            own tests ever drives a v2-shaped `session/prompt` turn or calls
                            `skip_if_version_mismatch` itself; every other id, including V2-3's
                            `ACP-TRANSPORT-201`/`002`/`203` -- which *do* call `skip_if_version_mismatch`
                            themselves, specifically to avoid hanging on `run_prompt` against a
                            mismatched agent, so they SKIP rather than PASS here despite also
                            being connection-level rows -- SKIPs with the `VERSION-MISMATCH:`
                            marker; `ACP-CANCEL-204`/`ACP-BATCH-206..208` SKIP too but for their
                            own unconditional record-only reason, not the version mismatch, so
                            they carry no `VERSION-MISMATCH:` marker in their own message; zero
                            FAILs anywhere, yet `verdict.blocked_by_version_mismatch` is `true`
                            and exit code is 1; V2-6 widens `_VERSION_TOLERANT_IDS` further with
                            `ACP-EXT-001`/`ACP-EXT-201`/`ACP-EXT-203` -- each probes only an
                            ordinary custom-method/notification exchange, never `session/new`'s
                            or `capabilities`'s own shape -- plus `ACP-ERROR-001`/
                            `ACP-SHUTDOWN-001`/`ACP-STDERR-001`/`ACP-INFO-PARSE-001`/
                            `ACP-INFO-INVALIDREQ-001`, all re-cited from v1 unchanged and
                            carrying no capability marker at all, whose own `session/new` calls
                            (or, for the latter two, their `_probe_connection_usable_after`
                            helper's graceful fallback) succeed at the wire level regardless of
                            negotiated version; `ACP-EXT-202` is deliberately NOT included --
                            it reads `result.capabilities` (the v2 field name) directly, which a
                            v1-negotiated result simply doesn't have, so it genuinely
                            `pytest.skip(...)`s on its own instead, a real skip without the
                            `VERSION-MISMATCH:` marker text); V2-6 adds ten more defect/positive-
                            control fixtures, one test each: `tool_call_update_missing_id.py`
                            (FAILs only `ACP-PATCH-204`, cascades into `ACP-SCHEMA-001`),
                            `plan_missing_plan_id.py` (FAILs only `ACP-PATCH-205`, cascades into
                            `ACP-SCHEMA-001`), `message_chunk_missing_message_id.py` (FAILs only
                            `ACP-PATCH-201`, cascades into `ACP-SCHEMA-001`),
                            `unprefixed_custom_session_update.py` (FAILs only `ACP-ENUM-202`;
                            schema-valid on its own, so no `ACP-SCHEMA-001` cascade),
                            `prefixed_custom_session_update.py` (positive control: PASSes
                            `ACP-ENUM-202` via a `_`-prefixed custom `sessionUpdate` value),
                            `custom_method_no_response.py` (FAILs only `ACP-EXT-001`),
                            `error_message_with_newline.py` (FAILs only `ACP-ERROR-001`),
                            `never_exits_on_stdin_close.py` (FAILs only `ACP-SHUTDOWN-001`; its
                            self-test keeps `--close-grace` small to avoid waiting out the
                            default grace period at every rung of the shutdown ladder), and
                            `unknown_root_key.py` (FAILs only `ACP-SCHEMA-002`; leaves
                            `capabilities` itself untouched, so `ACP-EXT-202` is unaffected); the
                            first three fixtures each override `_send_rich_turn_updates` outright
                            (rather than opting in via `emit_rich_turn_updates=True`) so their one
                            targeted defect doesn't drag in unrelated `ACP-PATCH-*`/`ACP-ENUM-201`
                            evidence, and each fixture's self-test asserts the remaining
                            rich-turn-update ids SKIP "no `<variant>` observed" rather than PASS
                            on borrowed evidence
  fixtures/agents/v1/
    _base.py               shared ConformingAgent core (not a standalone script); optionally
                          takes a `capabilities` dict merged into `agentCapabilities`, and
                          implements `session/load` (replays stored history before responding),
                          `session/resume` (no replay), `session/list` (filtered by `cwd`),
                          `session/delete`/`session/close` (remove the session; close also
                          resolves an in-flight prompt as `cancelled`). Also (slice 6b) accepts
                          `modes`, `config_options`, `auth_methods`, `require_auth`,
                          `emit_mode_update`, `mode_update_field` (default `"currentModeId"`,
                          overridable by defect fixtures), and implements
                          `session/set_mode`/`session/set_config_option`/`authenticate`/
                          `logout`, plus filters `type: "boolean"` config options out of
                          `session/new`'s result unless the client advertised
                          `clientCapabilities.session.configOptions.boolean` (Req 33).
    conforming.py          deterministic, offline, conforming ACP v1 agent; advertises
                          `agentCapabilities: {}`, so every capability-conditional test SKIPs
    conforming_full.py     conforming.py plus `loadSession: true`, every `sessionCapabilities`
                          marker (`list`/`delete`/`resume`/`close`/`additionalDirectories`),
                          `promptCapabilities: {image, audio, embeddedContext}`, two `modes`, a
                          select and a boolean `configOptions` entry, an `authMethods` entry
                          (id `"tck"`), and `auth: {logout: {}}` -- all correctly implemented via
                          `_base.py` -- drives every CAPABILITY-tier requirement in this slice to
                          PASS when run with `--auth-method tck` (see "Running" below)
    banner_on_stdout.py     conforming + prints a non-ACP banner line to stdout first
    stderr_chatter.py      conforming + logs every received message to stderr
    never_responds.py      reads stdin forever, never writes anything
    exits_immediately.py   exits 0 without reading stdin
    wrong_id_echo.py       mangles every response id (violates ACP-JSONRPC-001)
    version_mismatch_errors.py  errors instead of succeeding on a version mismatch (ACP-INIT-003)
    echoes_any_version.py  echoes the client's requested `protocolVersion` verbatim, including
                          for the unsupported 65535 request -- the strengthened ACP-INIT-003
                          false-negative pattern also present in `testy`/`examples/echo_agent.py`
    router_requires_info.py  models a dual-version ACP v1/v2 protocol *router* (slice V2-0b):
                          selects v2 for any requested version >= 2 (including the ACP-INIT-003
                          probe's 65535) and validates the params as a v2 `InitializeRequest`,
                          whose `info` is REQUIRED -- errors `-32602` naming the missing field
                          if absent, otherwise answers `protocolVersion: 2`; behaves as an
                          ordinary v1 agent for a `protocolVersion: 1` request. Self-test canary
                          for ACP-INIT-003's probe carrying `info`: FAILed INIT-003 (spurious
                          `-32602`, NOT CONFORMANT) before the fix, PASSes after
    result_and_error.py    initialize response carries both result and error (ACP-JSONRPC-002)
    answers_notifications.py  replies to the session/cancel notification (ACP-JSONRPC-003)
    unknown_method_no_error.py  unknown methods succeed instead of -32601 (ACP-JSONRPC-004 only)
    hangs_until_cancel.py  conforming, but every prompt (any text) withholds its response until
                          `session/cancel`; self-test-only, drives ACP-CANCEL-001/002
                          deterministically since the conformance suite itself must not rely on
                          `conforming.py`'s `__hang__` sentinel
    cancel_returns_error.py  cancelled turn resolves with a JSON-RPC error, not `cancelled`
                          (ACP-CANCEL-001)
    cancel_wrong_stop_reason.py  cancelled turn resolves with `stopReason: "end_turn"` instead of
                          `"cancelled"` (ACP-CANCEL-001)
    update_after_response.py  cancelled turn resolves correctly, then sends one more
                          `session/update` afterwards (ACP-CANCEL-002)
    bad_stop_reason.py     non-`__hang__` prompts resolve with `stopReason: "done"`, not a valid
                          StopReason (ACP-PROMPT-001, ACP-SCHEMA-001, cascades into ACP-CANCEL-001)
    duplicate_session_id.py  `session/new` always returns the same sessionId (ACP-SESSION-002)
    update_wrong_session.py  every `session/update` carries `sessionId: "other"`
                          (ACP-PROMPT-002, cascades into ACP-CANCEL-002)
    asks_permission.py    conforming, but sends `session/request_permission` mid-turn and only
                          resolves once the client answers -- the only self-test fixture that
                          exercises `_helpers.run_prompt`'s permission-answering path
    garbage_after_response.py  conforming for the whole exchange, then -- after stdin closes --
                          writes one line of non-JSON garbage to stdout before exiting
                          (ACP-TRANSPORT-001; only catchable via `AgentProcess.close()`'s
                          post-close stdout drain)
    invalid_utf8.py       writes one line of invalid UTF-8 bytes to stdout, otherwise conforming;
                          the dedicated negative control for ACP-TRANSPORT-002 (it also FAILs
                          ACP-TRANSPORT-001, since a line that isn't decodable text isn't valid
                          JSON either -- see `banner_on_stdout.py` below for the complementary
                          fixture that FAILs 001 but PASSes 002)
    load_replays_after_response.py  advertises `loadSession`; answers `session/load` before
                          replaying stored history instead of after (ACP-LOAD-002 only --
                          ACP-LOAD-001 still PASSes)
    resume_replays_history.py  advertises `sessionCapabilities.resume`; replays stored history
                          before answering `session/resume`, which resume MUST NOT do
                          (ACP-RESUME-002 only -- ACP-RESUME-001 still PASSes)
    load_returns_null.py  advertises `loadSession`, replays correctly, but answers
                          `session/load` with a literal `null` instead of `{}` -- fails only the
                          ADVISORY ACP-LOAD-003 (ACP-LOAD-001/002 still PASS: mandatory schema
                          validation tolerates `null` here)
    advertises_load_but_errors.py  advertises `loadSession: true` but always errors on
                          `session/load` -- a CAPABILITY-tier FAIL (ACP-LOAD-001), which flips
                          the overall verdict to NOT CONFORMANT
    mode_update_uses_modeId.py  conforming_full.py, but its `current_mode_update` carries the
                          docs-bug field name `modeId` instead of the schema's `currentModeId`
                          (ACP-MODES-002 only)
    config_partial_list.py  conforming_full.py, but `session/set_config_option` returns only the
                          changed entry instead of the complete `configOptions` list
                          (ACP-CONFIG-002 only)
    boolean_option_unadvertised.py  conforming_full.py, but always includes its `type: "boolean"`
                          config option in `session/new`'s result even when the client didn't
                          advertise `clientCapabilities.session.configOptions.boolean` (ACP-CONFIG-003,
                          MANDATORY -- flips the verdict to NOT CONFORMANT)
    terminal_auth_unadvertised.py  conforming_full.py, but advertises an
                          `authMethods[*].type == "terminal"` entry regardless of whether the
                          client advertised `clientCapabilities.auth.terminal` (ACP-AUTH-002,
                          MANDATORY -- flips the verdict to NOT CONFORMANT)
    gated_by_auth.py       conforming_full.py, but `session/new` always errors with
                          `-32000` (`AUTHENTICATION_REQUIRED`) unless the client has
                          successfully called `authenticate` first with the advertised
                          `"tck"` method id -- self-test-only fixture for
                          `--auth-method`/`Verdict.blocked_by_auth`
    calls_fs_unadvertised.py  `SendsClientRequestAgent` subclass (shared base added to `_base.py`
                          for slice 7): sends `fs/read_text_file` mid-turn regardless of
                          advertised client capabilities (ACP-CLIENTCAP-001, MANDATORY)
    calls_terminal_unadvertised.py  same shape, `terminal/create` (ACP-CLIENTCAP-002, MANDATORY)
    calls_elicitation_unadvertised.py  same shape, `elicitation/create` (ACP-CLIENTCAP-003,
                          MANDATORY)
    noisy_stderr_and_parse_error_reply.py  conforming, but logs every raw line to stderr and
                          replies `{"id": null, "error": {"code": -32700, ...}}` to malformed
                          JSON instead of silently swallowing it -- self-test-only fixture that
                          deterministically exercises ACP-STDERR-001's/ACP-INFO-PARSE-001's
                          non-default branches (see `tests/v1/test_cli.py`)
  fixtures/agents/v2/
    _base.py               a fresh, standalone `ConformingAgent` for v2 (does not import
                          `fixtures/agents/v1/_base.py` -- honest duplication, same reasoning as
                          `tck.v2.validation` not sharing code with `tck.v1.validation`);
                          handles `initialize` (honestly negotiates
                          `protocolVersion`/`info`/`capabilities`) and the full
                          `capabilities.session` baseline (`.agents/research/
                          acp-v2-session-management.md` B1: advertising `session`, even as `{}`,
                          commits the agent to all of `session/new`, `session/list`,
                          `session/resume`, `session/close`, `session/prompt`, `session/cancel`,
                          `session/update`) -- `session/new` (unique `sess-NNNN` ids),
                          `session/list` (filtered by `cwd`), `session/resume` (no replay, no
                          history retained), `session/close` (forgets the session),
                          `session/cancel` (no-op notification), and a minimal but
                          wire-correct `session/prompt` turn (`{messageId}` receipt, then
                          `user_message`/`state_update{running}`/`agent_message_chunk`/
                          `state_update{idle, stopReason:"end_turn"}` updates). `session/new`
                          and the full `session/prompt` turn are now both exercised
                          (`ACP-SESSION-001/002`, and V2-2a's `ACP-PROMPT-201`/`203`,
                          `ACP-STATE-201..203`, `ACP-PROMPT-205`); `session/list`/`resume`/
                          `close` still await a follow-up slice's session-capability tests.
                          V2-2a splits `_handle_prompt`'s five-step sequence into small,
                          individually overridable hooks -- `_reply_to_prompt`,
                          `_send_user_message_update`, `_send_running_update`, `_stop_reason`,
                          `_send_idle_update` -- purely so each single-defect fixture below can
                          override exactly one step; `ConformingAgent`'s own observable
                          behavior is unchanged. V2-2b adds four more hooks on top -- `method is
                          None` messages (responses to something the agent itself sent) now
                          route to a new `_handle_response` no-op hook instead of being silently
                          dropped; `_handle_prompt` calls a new `_prompt_rejection(prompt)` hook
                          first (return `(code, message)` to reject the prompt outright with a
                          JSON-RPC error instead of accepting it) and, once accepted, a new
                          `_mid_turn_action(session_id)` hook after the running update (return
                          `True` to defer the turn's completion to that action, `False` -- the
                          default -- to finish immediately); the old inline chunk+idle-send tail
                          is now `_finish_turn(session_id, stop_reason=None)`, called only when
                          `_mid_turn_action` returned `False`. All four default to preserving
                          `ConformingAgent`'s exact prior behavior. Two new subclasses build on
                          these: `AsksPermissionAgent` (overrides `_mid_turn_action` to send
                          `session/request_permission` and defer `_finish_turn` until the
                          client's answer arrives, via the new `_handle_response` hook) and
                          `SendsClientRequestAgent` (overrides `_mid_turn_action` to fire a
                          configurable agent -> client request -- `_client_request_method()`/
                          `_client_request_params(session_id)` -- and forget it, never deferring
                          turn completion). V2-3 adds top-level batch dispatch (a top-level JSON
                          array read off stdin is split into its entries, each entry-dispatched
                          normally, non-empty-request-bearing results collected into one
                          combined response array written back as a single line -- overridable
                          via `_handle_batch(items)` for the batch-defect fixtures below) and a
                          `_stop_reason() == "__hang__"`-triggered hang: a prompt whose text is
                          exactly `__hang__` withholds its turn-ending idle until `session/
                          cancel` arrives for that session, then resolves with a `cancelled`
                          idle -- the v2 analogue of v1's `conforming.py` hang sentinel, needed
                          so `--cancel-prompt __hang__` can make V2-3's cancellation tests
                          deterministic against `conforming_full.py`. V2-4 adds session
                          management: `session/resume` now actually replays a per-session history
                          recorded as updates are sent (`{"type": "start"}` only, per R2/R3, and
                          accepting any `sessionId` -- even one this process never created -- so
                          every route `_helpers.obtain_resumable_session` tries succeeds);
                          `session/delete` (no cancellation side effect, unlike `session/close`;
                          an unknown id still succeeds silently); and `session/set_config_option`
                          plus `configOptions` on `session/new`/`session/resume`'s own result
                          (replies with the complete updated list, never just the changed entry).
                          `additionalDirectories`/`mcpServers` need no new handling at all --
                          `_handle_new_session`/`_handle_resume_session` already ignore every
                          `params` key besides `cwd`/`sessionId`, so both are already "accepted"
                          in the sense the corresponding tests check. V2-5 adds authentication:
                          an `auth_methods`/`require_auth` constructor pair (mirrors v1's
                          `_base.py`), `auth/login`/`auth/logout` handlers (login succeeds iff
                          `methodId` matches one of `auth_methods`, flipping `self._authenticated`;
                          logout unconditionally flips it back and always succeeds), and
                          `_handle_new_session` now errors with `-32000` when `require_auth` is
                          set and the connection is not yet authenticated. `authMethods` is
                          included in `initialize`'s result iff the constructor was given a
                          non-`None` list (an empty list is distinct from omitting the key
                          entirely, matching the schema's "optional array" framing).
    conforming.py          advertises `capabilities: {"session": {}}` so `ACP-SESSION-001/002`
                          PASS rather than SKIP; otherwise a trivial entry point, mirrors
                          `fixtures/agents/v1/conforming.py`
    echoes_any_version.py  echoes the client's requested `protocolVersion` verbatim, including
                          for the unsupported 65535 request -- the v2 counterpart of v1's
                          fixture of the same name; FAILs exactly `ACP-INIT-003`/`ACP-INIT-201`
    v2_only_errors_on_v1.py  errors instead of answering `2` when asked for `protocolVersion: 1`
                          -- FAILs exactly `ACP-INIT-202` (the `N < min(S)`
                          downgrade-must-still-succeed rule)
    missing_info.py        omits the required `info` field from the `initialize` result --
                          FAILs `ACP-INIT-203` and `ACP-SCHEMA-001` only; `ACP-INIT-001` still
                          PASSes (it asserts only a non-error result, never the result's shape)
    boolean_session_capability.py  advertises `capabilities: {"session": true}` (a boolean
                          instead of an object marker) -- FAILs `ACP-INIT-204` and
                          `ACP-SCHEMA-001` only; `ACP-INIT-001` still PASSes (same reason);
                          `ACP-SESSION-001/002` still PASS since the underlying `session/new`
                          handler works fine and `capability_is_supported` treats `true` as
                          advertised
    duplicate_session_id.py  `session/new` always returns the same `sessionId` -- FAILs exactly
                          the CAPABILITY `ACP-SESSION-002` (mirrors v1's fixture of the same
                          name)
    bad_stop_reason.py     the turn-ending idle's `stopReason` is `"done"` -- not one of the
                          five defined constants and not `_`-prefixed. FAILs exactly
                          `ACP-STATE-203`; `ACP-STATE-201`/`202` and every `ACP-PROMPT-*` id are
                          unaffected (both `running` and a stop-reason-bearing idle are still
                          observed, just with an illegal value)
    vendor_stop_reason.py  the turn-ending idle's `stopReason` is `"_tck/throttled"` -- a
                          `_`-prefixed extension value, legal per the open-enum rule. PASSes
                          every V2-2a id; the positive control paired with
                          `bad_stop_reason.py`'s negative one
    no_running_update.py   skips `state_update {state: "running"}` entirely and jumps straight
                          to a turn-ending idle. FAILs exactly `ACP-STATE-201` (its gate is the
                          idle, not `running` -- see `tck.v2.requirements`'s `ACP-STATE-201`
                          docstring); `ACP-STATE-202`/`203` SKIP as "no foreground work
                          observed" since `running_seen` is never set
    no_idle_after_running.py  replies, sends `running` and a content chunk, then goes silent
                          forever -- no turn-ending idle ever arrives. Large, honest cascade:
                          every test that calls `run_prompt` (all six V2-2a ids, plus
                          `ACP-SCHEMA-001`'s prompt-turn extension in `test_initialize.py`, and
                          -- as of V2-2b -- `ACP-CLIENTCAP-201/202`, `ACP-PERM-201`, and the
                          ADVISORY `ACP-PROMPT-003`, since each drives its own independent
                          `run_prompt` turn too) independently hits `AgentTimeout` and FAILs; run
                          with a short `--tck-timeout` in `tests/v2/test_cli.py` to keep the
                          self-test fast, each test bounded by its own timeout, never hanging the
                          suite
    idle_before_running.py  sends an unsolicited "session-ready" `state_update {state: "idle"}`
                          (no `stopReason`) right after `session/new`, before any
                          `session/prompt` is ever issued -- the legal initial-ready-idle
                          pattern (`.agents/research/acp-v2-prompt-lifecycle.md` §4 point 2).
                          PASSes every V2-2a id: `run_prompt`'s turn-end predicate correctly
                          never mistakes this pre-prompt idle for the turn's own terminator
    echo_wrong_message_id.py  the `user_message` update echoing the inserted prompt carries a
                          different `messageId` than the `session/prompt` response returned.
                          FAILs exactly `ACP-PROMPT-203`; every other V2-2a id is unaffected
    missing_message_id.py  the `session/prompt` response is `{}` -- no `messageId` at all.
                          FAILs `ACP-PROMPT-201` and `ACP-SCHEMA-001`'s prompt-turn extension;
                          `ACP-PROMPT-203` SKIPs (nothing valid to check the echo against, see
                          `ACP-PROMPT-201` for the precise diagnostic instead); `ACP-STATE-*`
                          and `ACP-PROMPT-205` are unaffected
    update_wrong_session.py  every `session/update` notification carries `sessionId: "other"`
                          instead of the session the prompt was actually sent for. Same large
                          cascade as `no_idle_after_running.py` -- `run_prompt`'s turn-end
                          predicate only recognizes an idle/running update as this turn's own
                          when its `sessionId` matches, so with every update misattributed, all
                          six V2-2a tests plus `ACP-SCHEMA-001`'s prompt-turn extension and (as of
                          V2-2b) `ACP-CLIENTCAP-201/202`/`ACP-PERM-201`/`ACP-PROMPT-003`
                          independently `AgentTimeout`, indistinguishable from an agent that
                          never responds to the prompted session at all
    conforming_full.py     (V2-2b) `AsksPermissionAgent`, advertising every V2-2b capability
                          marker (`capabilities.session.prompt.{image,audio,embeddedContext}`)
                          on top of the plain `capabilities.session` baseline -- PASSes literally
                          every registered id; the intended "everything works" fixture for a
                          full-suite smoke run (`test_v2_conforming_full_agent_passes_everything`).
                          Slice V2-4 extends it with the full session-management surface: `delete:
                          {}`, `additionalDirectories: {}`, `mcp: {stdio: {}, http: {}}` markers,
                          real `session/resume` replay (retaining and replaying stored history
                          for `{"type": "start"}`, answering only after replay finishes, per
                          `ACP-RESUME-202`'s ordering rule), `session/list` returning `[]` (never
                          an error) when no session matches the query `cwd`, and a `configOptions`
                          entry on `session/new` plus a working `session/set_config_option` that
                          returns the complete list. V2-5 adds one `type: "agent"` authMethods
                          entry (`methodId: "tck"`), correctly implementing `auth/login`/
                          `auth/logout` -- PASSes all 83 registered ids when run with
                          `--cancel-prompt __hang__ --auth-method tck --allow-logout`, except
                          `ACP-AUTH-207` (MANDATORY but SKIPs: it needs a `type: "terminal"`
                          entry to appear on a connection that advertises `capabilities.auth.
                          terminal`, and this fixture advertises no terminal method at all -- a
                          SKIPped MANDATORY id does not affect `verdict.conformant`, only a FAIL
                          or NOT_TESTED one does, so the run is still CONFORMANT). Without
                          `--allow-logout`, `ACP-AUTH-203` additionally SKIPs (its own,
                          separately documented opt-in) but the run stays CONFORMANT either way
    asks_permission.py     (V2-2b) `AsksPermissionAgent` advertising only the plain
                          `capabilities.session` baseline (no prompt-content markers) --
                          isolates `ACP-PERM-201` PASSing while `ACP-PROMPTCAP-001/002/003` SKIP
                          (not advertised); every other id unaffected
    rejects_image_when_advertised.py  (V2-2b) advertises all three prompt-content markers, but
                          `_prompt_rejection` errors out any prompt containing an `image` content
                          block instead of accepting it as advertised. FAILs exactly
                          `ACP-PROMPTCAP-001`; `ACP-PROMPTCAP-002/003` still PASS (audio/
                          resource blocks are accepted normally, and both capabilities are
                          advertised so those tests actually run instead of SKIPping)
    calls_elicitation_unadvertised.py  (V2-2b) `SendsClientRequestAgent` sending
                          `elicitation/create` mid-turn regardless of the client's advertised
                          capabilities (the mock client always advertises `capabilities: {}}`, so
                          this is always unadvertised). FAILs exactly `ACP-CLIENTCAP-201`;
                          `ACP-CLIENTCAP-202` is unaffected since `elicitation/create` is itself
                          a defined v2 client method
    calls_fs_unadvertised.py  (V2-2b) `SendsClientRequestAgent` sending `fs/read_text_file`
                          mid-turn -- a v1-shaped method name that does not exist as a v2 client
                          method at all (`fs/*`/`terminal/*` were removed in v2). FAILs
                          `ACP-CLIENTCAP-202` and, as an expected cascade, `ACP-SCHEMA-001` too
                          (the schema validator flags the unknown method name); `ACP-CLIENTCAP-201`
                          is unaffected
    calls_custom_method.py  (V2-2b) `SendsClientRequestAgent` sending a `_`-prefixed custom
                          method (`_tck/ping`) mid-turn -- legal per the open-enum rule. Positive
                          control paired with `calls_fs_unadvertised.py`: PASSes every id it can
                          (advertises only the plain `capabilities.session` baseline, so
                          `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201` still SKIP)
    cancel_no_idle.py      (V2-3) `conforming_full.py`, but hangs on *every* prompt (not just
                          the dedicated cancel-test one) and silently ignores `session/cancel`
                          entirely -- no terminating idle, no error, ever. `session/close` is
                          unaffected (still inherits `ConformingAgent`'s own default handler,
                          which resolves a hanging session via `_finish_turn(..., "cancelled")`),
                          isolating `session/cancel`'s own defect from `ACP-CANCEL-208`'s
                          close-triggered path. FAILs every id whose own test drives a turn
                          through `run_prompt` at all -- an uncaught `AgentTimeout` -- the same
                          broad cascade shape as `no_idle_after_running.py`/`update_wrong_
                          session.py` above: `ACP-SCHEMA-001`, `ACP-TRANSPORT-201/002/203`,
                          `ACP-CANCEL-201/202/203/205/206/207`, `ACP-CLIENTCAP-201/202`,
                          `ACP-PERM-201`, `ACP-PROMPT-201/203/205`, `ACP-STATE-201/202/203`, the
                          ADVISORY `ACP-CANCEL-204`/`ACP-PROMPT-003`, and INFORMATIONAL
                          `ACP-INFO-CANCEL-202`. `ACP-CANCEL-208` is the one exception: `session/
                          close` still rescues the hanging turn via the inherited default
                          handler, so it PASSes
    cancel_returns_error.py  (V2-3) `conforming_full.py`, but withholds `session/prompt`'s own
                          acceptance receipt entirely for *every* turn (no `user_message`/
                          `running` update either), not just the dedicated cancel-test one,
                          until `session/cancel` arrives -- then answers the *original*
                          `session/prompt` request with a JSON-RPC error instead of ever sending
                          a terminating idle. Every id whose own test drives an ordinary
                          (non-cancelling) `run_prompt` turn never gets that far and FAILs with a
                          timeout: `ACP-SCHEMA-001`, `ACP-TRANSPORT-201/002/203`,
                          `ACP-CLIENTCAP-201/202`, `ACP-PERM-201`, `ACP-PROMPT-201/203/205`,
                          `ACP-STATE-201/202/203`, and the ADVISORY `ACP-PROMPT-003`. On top of
                          that cascade, cancelling itself FAILs `ACP-CANCEL-203` (surfaced as a
                          generic JSON-RPC error) and `ACP-CANCEL-208` (a `session/close` sent
                          instead has nothing registered to rescue either -- `_handle_prompt`
                          never adds the session to `_hanging_sessions`, so the original
                          `session/prompt` is simply never answered and `run_prompt` itself times
                          out). `ACP-CANCEL-201/202/206/207` SKIP, deferring to `ACP-CANCEL-203`
                          -- the turn never reaches a terminating idle at all
    cancel_wrong_stop_reason.py  (V2-3) `conforming_full.py`, but hangs on *every* prompt (not
                          just the dedicated cancel-test one); on cancel it finishes the turn
                          with `stopReason: "end_turn"` instead of `"cancelled"` -- after a
                          deliberate 1.2s delay (needs `--timeout 2` for the self-test) to clear
                          the TCK's own "was this actually exercised" race window, since
                          `"end_turn"` is itself a valid `StopReason` and an instant reply would
                          make the cancel-specific ids SKIP instead of FAIL, hiding the defect.
                          Every id whose own test drives an ordinary `run_prompt` turn FAILs with
                          a timeout, the same cascade shape as `cancel_no_idle.py` above:
                          `ACP-SCHEMA-001`, `ACP-TRANSPORT-201/002/203`, `ACP-CLIENTCAP-201/202`,
                          `ACP-PERM-201`, `ACP-PROMPT-201/203/205`, `ACP-STATE-201/202/203`, the
                          ADVISORY `ACP-PROMPT-003`. For the cancel scenario itself, resolving
                          with `"end_turn"` FAILs `ACP-CANCEL-201`/`203`/`207` and `ACP-CANCEL-206`
                          (the `_meta`-carrying cancel scenario hits the same overridden handler).
                          `ACP-CANCEL-202`/`208` SKIP/PASS respectively, deferring to the rows
                          above -- `208`'s own test drives cancellation via `session/close`, not
                          `session/cancel`, which hits the base `ConformingAgent`'s unmodified
                          close handling (this fixture only overrides `_handle_cancel`), so it
                          still resolves correctly and PASSes despite the defect
    rejects_batch.py       (V2-3) `conforming_full.py`, but every non-empty batch array is
                          handled as if it were the empty-batch case: a single `-32600`
                          `Invalid Request` object is written back instead of per-entry
                          dispatch. Coincidentally still satisfies `ACP-BATCH-201` (the true
                          empty-batch case is answered correctly), but FAILs `ACP-BATCH-202`
                          (entries are never dispatched), `ACP-BATCH-203` (a notification-only
                          batch must produce no output, but this always emits the `-32600`), and
                          the shared `ACP-BATCH-204`/`205` test (the batched `session/new` never
                          gets its own result). None of `test_transport.py`/`test_jsonrpc.py`/
                          `test_cancel.py` is affected -- none of those tests ever sends a batch
    crashes_on_batch.py    (V2-3) `conforming_full.py`, but exits the moment it sees any
                          batch-shaped (top-level JSON array) line on stdin -- otherwise fully
                          conforming, including for every non-batch single-message exchange.
                          FAILs every requirement whose own test actually sends a batch line:
                          `ACP-BATCH-201/202/203`, the shared `ACP-BATCH-204`/`205` test, and
                          `ACP-INFO-BATCH-201/202` (INFORMATIONAL, but the handshake inside
                          `test_batch.py`'s own `_v2_only_agent` still succeeds -- only the batch
                          probe itself kills the process, so these become `AgentExited` FAILs
                          rather than a recorded behaviour). `ACP-BATCH-206/207/208` are
                          unaffected -- unconditional record-only SKIPs that never send anything.
                          Every other id in this slice (`ACP-TRANSPORT-*`, `ACP-JSONRPC-*`, and
                          everything cancellation-related) is unaffected, since none of those
                          tests ever sends a batch-shaped line -- the acceptance-criteria example
                          of a fixture that fails *only* batch rows
    banner_on_stdout.py    (V2-3) conforming, but prints a human banner line to stdout before
                          the agent's own `run()` loop ever touches stdout (v2's
                          `ConformingAgent` has no `on_start` hook, unlike v1's, so the banner is
                          printed directly in `main()`). Violates `ACP-TRANSPORT-201`; the banner
                          also shows up in the full-exchange schema scan, so `ACP-SCHEMA-001`
                          fails the same way. Plain ASCII, so `ACP-TRANSPORT-002` still PASSes --
                          the complementary fixture to `invalid_utf8.py` below
    invalid_utf8.py        (V2-3) writes one line of invalid UTF-8 bytes to stdout before
                          behaving like a conforming agent -- the dedicated negative control for
                          `ACP-TRANSPORT-002`. A line that isn't decodable text isn't valid JSON
                          either, so it also fails `ACP-TRANSPORT-201` and `ACP-SCHEMA-001`
    garbage_after_response.py  (V2-3) conforming for the whole exchange, then -- after stdin
                          closes -- writes one line of plain-text (ASCII) garbage to stdout
                          before exiting. Only catchable via `AgentProcess.close()`'s post-close
                          stdout drain. Fails `ACP-TRANSPORT-201` (not valid JSON) and
                          `ACP-SCHEMA-001` (the drained garbage line is still on
                          `agent.transcript` when the schema scan runs, after
                          `connected_agent`'s `__aexit__`); `ACP-TRANSPORT-002` still PASSes
    wrong_id_echo.py       (V2-3) mangles every response id (adds 1 to integer ids, appends a
                          suffix to string ids) instead of echoing the request id verbatim.
                          Violates `ACP-JSONRPC-001`; breaking id correlation for every
                          request/response pair cascades into nearly every other requirement, so
                          its self-test scopes the run to `-k jsonrpc` (mirroring v1's own
                          precedent) rather than paying an unscoped run's cost -- scoped, it
                          fails `ACP-JSONRPC-001/002/003`, `ACP-TRANSPORT-201` (incidentally
                          selected: `test_stdout_is_clean_ndjson_jsonrpc_or_batch` matches the
                          `-k jsonrpc` substring), and the ADVISORY `ACP-JSONRPC-004/005`
    answers_notifications.py  (V2-3) unconditionally replies to the `session/cancel`
                          notification with a bogus response (`{"id": null, "result": null}`)
                          instead of never responding to it -- v2's `_base.py` has no generic
                          notification hook like v1's; `session/cancel` is the only notification
                          method `ConformingAgent._handle` recognizes at all, so this overrides
                          `_handle_cancel` directly (never calling `super()`, so no `__hang__`
                          prompt is ever legitimately cancelled either). Violates
                          `ACP-JSONRPC-003` only
    result_and_error.py    (V2-3) the `initialize` response illegally carries both `result` and
                          `error`. Violates `ACP-JSONRPC-002` and, via the same envelope check,
                          `ACP-SCHEMA-001`. `ACP-INIT-001` still PASSes: it only asserts
                          `"result" in msg`, true regardless of `error`'s illegal presence
    unknown_method_no_error.py  (V2-3) replies to unknown methods with an empty success result
                          instead of `-32601` -- fails only the ADVISORY `ACP-JSONRPC-004` plus
                          the two batched-unknown-method ADVISORY checks (`ACP-BATCH-204`/`205`,
                          which also expect `-32601` for the unknown call inside a mixed batch);
                          verdict stays CONFORMANT
    emits_batch_updates.py  (V2-3) positive control: `conforming_full.py`'s capabilities/
                          permission behavior, but every pair of `session/update` notifications
                          a turn naturally sends back-to-back is delivered as one JSON-RPC batch
                          array line instead of two separate lines (`ACP-BATCH-207`, ADVISORY,
                          explicitly permits this). Must PASS every requirement
                          `conforming_full.py` itself PASSes (run with `--cancel-prompt
                          __hang__`) -- proving spontaneous batching of an agent's own
                          notifications is conformant and does not break anything the TCK
                          checks. Exercising this fixture found and fixed two genuine TCK bugs:
                          `test_initialize.py`'s `ACP-SCHEMA-001` scan and `test_cancel.py`'s
                          `ACP-CANCEL-205` scan both previously assumed every received line was a
                          single object and either hard-failed (`assert isinstance(msg, dict)`)
                          or raised `ValueError` (`list.index` on a synthetic per-batch-item
                          entry that is never literally `in` `agent.transcript`) when a line was
                          a spontaneous batch array instead
    resume_replays_when_not_asked.py  (V2-4) `session/resume` replays the session's full retained
                          history unconditionally, even when `replayFrom` is omitted/`null`.
                          FAILs exactly `ACP-RESUME-203`; `ACP-RESUME-201`/`202`/`204`/`205` are
                          unaffected -- this fixture answers the `{"type": "start"}` scenarios
                          identically to `ConformingAgent`, since it always replays regardless
    resume_responds_before_replay.py  (V2-4) `session/resume` with `replayFrom: {"type":
                          "start"}` replies before replaying the session's retained history,
                          reversing R2's required order. FAILs exactly `ACP-RESUME-202`.
                          `ACP-RESUME-204` legitimately SKIPs rather than FAILs: the helper reads
                          only up to the response, before the trailing replay notifications still
                          queued in the pipe, so it correctly reports "not replayed at all" from
                          its own vantage point instead of fabricating a verdict from data it
                          never observed. `ACP-RESUME-201`/`203` are unaffected
    resume_replay_missing_message_id.py  (V2-4) `session/resume` replays history correctly
                          (before responding), but strips `messageId` from every replayed
                          update. FAILs exactly `ACP-RESUME-204`; `ACP-RESUME-201`/`202`/`203`
                          don't inspect `messageId` and are unaffected
    list_errors_when_empty.py  (V2-4) `session/list` returns a JSON-RPC error instead of
                          `{"sessions": []}` whenever the (possibly `cwd`-filtered) result would
                          be empty. FAILs exactly `ACP-LIST-202`, the only test that filters to a
                          guaranteed-empty result; `ACP-LIST-201`/`203`/`204` all list at least
                          one present session and never hit the empty branch
    close_no_cancel_idle.py  (V2-4) `session/close` on a session with a still-hanging `__hang__`
                          prompt replies to the close normally, but resolves the hanging turn
                          with `stopReason: "end_turn"` instead of `"cancelled"` -- after a
                          deliberate 1.2s sleep past the TCK's cancel-race window, so the
                          deviation can't be mistaken for an honest race and SKIPped. Requires
                          `--cancel-prompt __hang__` to actually exercise (every other prompt
                          finishes normally on its own). FAILs exactly `ACP-CANCEL-208`/
                          `ACP-CLOSE-202` (dual-bound to the same test); every other id,
                          including `ACP-CLOSE-201` (closing an already-idle session), is
                          unaffected
    advertises_delete_but_errors.py  (V2-4) advertises `capabilities.session.delete: {}` but
                          `session/delete` always errors regardless of sessionId. FAILs
                          `ACP-DELETE-201`/`202`/`203` -- `201`/`202` are `Tier.CAPABILITY`, so
                          this flips the verdict to NOT CONFORMANT. Mirrors v1's
                          `advertises_load_but_errors.py`
    config_partial_list.py  (V2-4) `session/set_config_option` returns only the changed entry
                          instead of the complete `configOptions` list; advertises a second,
                          unrelated `boolean` option (`debug_mode`) alongside the usual `select`
                          `verbosity` one so a "partial" reply is actually distinguishable from a
                          "complete" one. FAILs exactly `ACP-CONFIG-202`; `ACP-CONFIG-201`/`203`/
                          `204`/`206` are unaffected. Mirrors v1's `config_partial_list.py`
    gated_by_auth.py       (V2-5) advertises one `type: "agent"` authMethods entry (`methodId:
                          "tck"`) and always errors `session/new` with `-32000` until `auth/
                          login` has succeeded with that methodId. Without `--auth-method`,
                          every session-dependent test SKIPs with the `AUTH-GATED:` marker,
                          forcing `verdict.blocked_by_auth == true` (exit code 1) despite zero
                          FAILs; with `--auth-method tck`, `connected_agent`'s auto-login step
                          authenticates before anything else and the run is fully CONFORMANT.
                          v2 port of v1's `gated_by_auth.py` (method renamed `authenticate` ->
                          `auth/login`)
    terminal_auth_unadvertised.py  (V2-5) advertises a `type: "terminal"` authMethods entry
                          unconditionally, even to a connection that never advertised
                          `capabilities.auth.terminal` -- FAILs exactly `ACP-AUTH-202`. No
                          `args`/`env` fields, so it can't also trip `ACP-AUTH-207`. v2 port of
                          v1's fixture of the same name (field renamed `id` -> `methodId`)
    duplicate_method_id.py  (V2-5) advertises two authMethods entries sharing the same
                          `methodId` -- FAILs exactly the ADVISORY `ACP-AUTH-201`; the verdict
                          stays CONFORMANT (an ADVISORY FAIL never flips it). No v1 analogue
    custom_auth_type_unprefixed.py  (V2-5) advertises an authMethods entry whose `type` is
                          `"sso"` -- neither a defined value nor `_`-prefixed -- FAILs exactly
                          `ACP-AUTH-206` (MANDATORY, new in v2: no v1 analogue, since v1 had no
                          open-enum rule on this field at all)
    advertises_auth_but_logout_errors.py  (V2-5) implements `auth/login` normally but always
                          errors on `auth/logout`. FAILs `ACP-AUTH-203` only when run with
                          `--auth-method tck --allow-logout` (both required to actually exercise
                          `auth/logout` at all); without `--allow-logout` it SKIPs like any other
                          agent, since the TCK never calls the destructive method. No v1 analogue
                          (v1's logout test had no opt-in gate)
    terminal_env_duplicate_names.py  (V2-5) advertises its `type: "terminal"` authMethods entry
                          only to a connection that itself advertised `capabilities.auth.
                          terminal` (so it never also trips `ACP-AUTH-202`); that entry's `env`
                          array has two entries sharing the same `name`, violating "Names MUST be
                          unique" -- FAILs exactly `ACP-AUTH-207` (MANDATORY, new in v2 -- no v1
                          analogue: v1's terminal descriptor had no `args`/`env` fields at all)
    tool_call_update_missing_id.py  (V2-6) `conforming_full.py` plus `emit_rich_turn_updates=
                          True`, but overrides `_send_rich_turn_updates` outright to send only a
                          `tool_call_update` with no `toolCallId` at all. FAILs exactly
                          `ACP-PATCH-204`; cascades into `ACP-SCHEMA-001` (`ToolCallUpdate`
                          requires `toolCallId`). No message chunk or plan update is sent, so
                          `ACP-PATCH-201/203/205/208/209` and `ACP-ENUM-201/202` all SKIP "no
                          `<variant>` observed" rather than PASS on borrowed evidence
    plan_missing_plan_id.py  (V2-6) same shape, but sends a `plan_update` whose `plan` object has
                          no `planId`. FAILs exactly `ACP-PATCH-205`; cascades into
                          `ACP-SCHEMA-001` (`PlanItems` requires `planId`). `ACP-ENUM-201` still
                          PASSes (the plan entry's `priority`/`status` are correctly shaped, even
                          though the surrounding `plan` object is missing its id)
    message_chunk_missing_message_id.py  (V2-6) same shape, but sends an `agent_message_chunk`
                          with no `messageId`. FAILs exactly `ACP-PATCH-201` (checks *every*
                          message-kind update observed, so this one extra malformed chunk is
                          enough on its own, even though the turn's own `user_message`/closing
                          `agent_message_chunk` are correctly shaped); cascades into
                          `ACP-SCHEMA-001` (`ContentChunk` requires `messageId`)
    unprefixed_custom_session_update.py  (V2-6) `conforming_full.py`, but sends one extra
                          `session/update` whose `sessionUpdate` discriminator is an unrecognized,
                          non-`_`-prefixed value (`"surprise"`). FAILs exactly `ACP-ENUM-202`;
                          schema-valid on its own (the vendored schema's `SessionUpdate` `other`
                          branch only requires `sessionUpdate` to be a string), so no
                          `ACP-SCHEMA-001` cascade -- a purely prose-level violation
    prefixed_custom_session_update.py  (V2-6) positive control: same shape, but the extra
                          `session/update`'s `sessionUpdate` value is `_`-prefixed
                          (`"_tck_custom_update"`) -- legal per the open-enum rule. PASSes
                          `ACP-ENUM-202`, paired with `unprefixed_custom_session_update.py`'s
                          negative control at the same site
    custom_method_no_response.py  (V2-6) `conforming_full.py`, but silently swallows every
                          `_`-prefixed custom method request instead of responding at all (every
                          other method still dispatches normally via `super()`). FAILs exactly
                          `ACP-EXT-001`
    error_message_with_newline.py  (V2-6) `conforming_full.py`, but the `-32601` error message
                          for an unrecognized method carries an embedded newline. FAILs exactly
                          `ACP-ERROR-001`; every other error path and method is unaffected
    never_exits_on_stdin_close.py  (V2-6) `conforming_full.py`, but never exits once stdin
                          closes -- needs SIGTERM/SIGKILL to terminate. FAILs exactly
                          `ACP-SHUTDOWN-001`. Self-test-only; its own `test_cli.py` entry keeps
                          `--close-grace` small so the self-test doesn't wait out the default
                          grace period at every rung of the shutdown ladder
    unknown_root_key.py    (V2-6) `conforming_full.py`, but the `initialize` result carries an
                          unrecognized root-level key (`"unknownRootKey"`) alongside the normal
                          `protocolVersion`/`capabilities`/`info`. FAILs exactly `ACP-SCHEMA-002`
                          (only caught by `tck.v2.validation.find_unknown_root_keys`, since the
                          vendored schema never sets `additionalProperties: false`); leaves
                          `capabilities` itself untouched, so `ACP-EXT-202` is unaffected
    noisy_stderr_and_parse_error_reply.py  (V2-6) `conforming_full.py`, but logs every raw line
                          received to stderr and replies to a malformed (non-JSON) stdin line
                          with an explicit `-32700` instead of silently swallowing it. v2 twin of
                          v1's fixture of the same name; self-test-only, deterministically
                          exercises `ACP-STDERR-001`'s/`ACP-INFO-PARSE-001`'s non-default
                          branches -- never FAILs anything, since neither is asserted on
```

## Running the TCK against an agent

```
uv run acp-tck -- python tests/fixtures/agents/v1/conforming.py
```

Options: `--agent-cwd DIR`, `--agent-env KEY=VAL` (repeatable), `--timeout S` (per-response
deadline, default 30), `--startup-timeout S` (default 30), `--test-timeout S` (per-test
wall-clock watchdog, default 120 -- plugin: `--tck-test-timeout`; wraps the whole async test
body in `asyncio.wait_for(...)`, so a test hangs for at most this long even if every individual
read/write inside it uses a much larger `--timeout`; on expiry the test `FAIL`s with a message
naming the watchdog, and the agent process is still closed normally so transcript/stderr
diagnostics are still attached), `--cancel-prompt TEXT` (see below), `--report-json PATH` (see
"Reporting" below), `--close-grace S` (plugin: `--tck-close-grace`, default 2.0 -- grace period
budgeted at each stage of the agent-process shutdown ladder on teardown: stdin-close wait,
post-SIGTERM wait, post-SIGKILL wait; lower it only to speed up a fixture/test that deliberately
never exits on its own, a real agent under test should not normally need this changed), `-k EXPR`,
`-v`, `--version`, `--help`. Everything after `--` is the agent's own command line.

`--protocol-version {1,2}` (default `1`) picks which protocol-version package's conformance
suite and plugin shim to run: `1` -> `src/tck/v1/conformance` with `-p tck.v1.plugin` (unchanged
default behavior), `2` -> `src/tck/v2/conformance` with `-p tck.v2.plugin`. v2 is Draft and its
registry is still well short of v1 parity (`initialize`, `session/new`, (V2-2a) the core
`session/prompt` turn/`state_update` lifecycle, (V2-2b) prompt content capabilities, the
permission flow, and the agent -> client method rules, and (V2-3) cancellation, stdio
transport, the JSON-RPC envelope, and batching -- 52 requirements in all -- see `src/tck/v2/`'s
entry in "Layout" above); it is expected to grow in follow-up slices.

If the agent under test never actually negotiates the requested `--protocol-version` (e.g. a
v1-only agent run under `--protocol-version 2`, which honestly negotiates down per the
two-branch rule instead of erroring), every requirement that judges the *result's shape*
against v2-only rules -- `ACP-INIT-203`/`ACP-INIT-204`/`ACP-SCHEMA-001`, plus any
`@pytest.mark.capability(...)`-gated requirement such as `ACP-SESSION-001`/`002`, (V2-2a)
`ACP-PROMPT-201`/`203`/`ACP-STATE-201..203`/`ACP-PROMPT-205`, and (V2-2b)
`ACP-PROMPTCAP-001/002/003`/`ACP-PROMPT-003`/`ACP-PERM-201`/`ACP-CLIENTCAP-201/202` (the latter
two, plus `ACP-PROMPT-003`, also carry this same marker even though their own `Requirement`
tier is ADVISORY/CAPABILITY respectively -- the version-mismatch gate is marker-driven, not
tier-driven; see `tck.common.plugin`'s `_tck_capability_gate`) -- SKIPs with a
message prefixed `"VERSION-MISMATCH:"` instead of either passing or failing, because a v1-shaped
result cannot be fairly judged against v2 shape rules: FAILing it would mischaracterize an agent
that simply doesn't speak v2 as broken. The run is still forced NOT CONFORMANT
(`Verdict.blocked_by_version_mismatch`) even though no MANDATORY/CAPABILITY requirement actually
failed -- because those requirements were never actually exercised against the version this run
targets. The requirements that judge only the negotiation *outcome* --  `ACP-INIT-001` (a
non-error result), `ACP-INIT-003`/`ACP-INIT-201`/`ACP-INIT-202` (the two-branch rule itself,
including the unsupported-version and downgrade cases) -- are never gated this way: they are
judged normally against whatever the agent actually returned, and PASS on an honest downgrade,
since they *are* what determines whether a mismatch occurred in the first place.

```
uv run acp-tck --protocol-version 2 -- python tests/fixtures/agents/v2/conforming.py
```

**Exit code** is the four-status verdict, not pytest's own per-test exit code: `0` iff
`verdict.conformant` (no `MANDATORY` `FAIL`/`NOT_TESTED`, no `CAPABILITY` `FAIL` -- see
"Reporting" below), `1` otherwise (this includes an agent that fails to start or never responds
at all: every `MANDATORY` requirement ends up `FAIL` or `NOT_TESTED`, the run still completes and
still writes a report, and the terminal summary prints a hint to check `--agent-cwd`/timeouts/
stderr). `acp-tck` with no command after `--` is a usage error (exit `2`, from `argparse`), not a
verdict. Mechanism: `tck.common.plugin`'s `pytest_sessionfinish` overwrites `session.exitstatus`, but
only when pytest itself completed a normal run (`ExitCode.OK`/`TESTS_FAILED`) -- `--collect-only`,
usage errors, and interrupted runs keep pytest's own exit code.

`--cancel-prompt TEXT` (plugin: `--tck-cancel-prompt`) sets the prompt text the cancellation
tests (ACP-CANCEL-001/002) send -- every other prompt test keeps its own short, deterministic
text. Default is a long free-form writing prompt, chosen to keep a real agent busy long enough
for `session/cancel` to land while the turn is still in flight. If ACP-CANCEL-001/002 report
SKIPPED with reason "cancellation not exercised", it means exactly that -- the turn finished
before, or too soon after, `session/cancel` was sent for the TCK to tell whether the agent
actually reacted to it -- not that the agent failed conformance. Passing a longer or slower
`--cancel-prompt` (and, if needed, a larger `--timeout`) may let a fast agent's turn stay in
flight long enough to exercise the requirement for real.

`--auth-method ID` (plugin: `--tck-auth-method`) tells the harness to send an `authenticate`
request with this `methodId` right after a successful `initialize`, before any session-dependent
test runs (`connected_agent(..., handshake=True)`, the default). Needed for any agent whose
`session/new` gates behind authentication: without it, session-dependent tests SKIP with a
message prefixed `"AUTH-GATED:"`, and the run is forced NOT CONFORMANT
(`Verdict.blocked_by_auth`) even if no MANDATORY/CAPABILITY requirement otherwise failed --
because those requirements were never actually exercised. `ACP-AUTH-003` itself additionally
SKIPs outright whenever `--auth-method` is omitted (it can't guess a valid method id) or the
agent advertises no `authMethods` at all. `--auth-method` also works with `--protocol-version 2`
(plugin: same `--tck-auth-method`), where it drives v2's renamed `auth/login` instead --
`ACP-AUTH-204` is v2's `ACP-AUTH-003` counterpart and follows the exact same SKIP rules.

`--allow-logout` (plugin: `--tck-allow-logout`) opts in to actually calling v2's `auth/logout`
against the agent under test (`ACP-AUTH-203`). It is off by default -- unlike `--auth-method`,
which only ever *reads* the agent's state, a real `auth/logout` call may revoke the operator's
own credentials for whatever account the agent is authenticated as, so the TCK never calls it
uninvited. Without this flag, `ACP-AUTH-203` SKIPs with reason `"auth/logout not exercised: pass
--allow-logout (it may revoke the operator's credentials)"` instead of exercising the method; a
SKIPped `Tier.CAPABILITY` requirement does not affect `verdict.conformant` (only a *failed*
capability check does), so omitting `--allow-logout` never by itself makes a run NOT CONFORMANT.
Has no effect under `--protocol-version 1`: v1's logout test (`ACP-AUTH-004`) is gated purely by
the `agentCapabilities.auth.logout` capability marker and has no `--allow-logout`-style opt-in of
its own. v2 has no equivalent capability marker at all (support is inferred from `authMethods`
being non-empty), so `--allow-logout` is v2's only gate on whether `auth/logout` is ever called
for real.

You can also run the suite directly with plain pytest, e.g. to add pytest's own flags:

```
uv run pytest src/tck/v1/conformance -p tck.v1.plugin --tck-agent-cmd 'python tests/fixtures/agents/v1/conforming.py'
```

`tck.v1.plugin` is deliberately **not** auto-registered via a `pytest11` entry point (see
`.agents/plan.md` "Decided deliverable shape") -- it must always be loaded with `-p tck.v1.plugin`,
which both invocations above do.

## Running the repo's own tests

```
uv run pytest
```

The whole suite (harness unit tests + registry meta-tests + end-to-end CLI tests against every
fixture, for both the v1 and v2 conformance suites) takes a bit under 5 minutes (~293s measured
across three consecutive runs). Most of that time is `tests/v2/test_cli.py`'s end-to-end CLI
invocations, each of which spawns a real `python -m tck` subprocess (itself spawning a fixture
agent subprocess) and, for the fixtures with the broadest defect cascades, waits out one or more
`--tck-timeout`-bounded hangs; most of those self-tests scope their run with `-k` to just the
conformance-suite module(s) that own the id(s) they assert on (mirroring `tests/v1/test_cli.py`'s
existing precedent), deselecting everything else (`NOT_TESTED`) rather than re-verifying it --
`-k`-scoped runs necessarily flip the printed/JSON verdict to NOT CONFORMANT (see
`tests/v1/test_cli.py::test_hangs_until_cancel_agent_passes_cancel_requirements`'s docstring), so
those self-tests check only the specific per-id statuses they care about, not the overall
verdict/exit code. A handful of positive controls (`conforming.py`, `conforming_full.py` with
`--cancel-prompt __hang__`, `emits_batch_updates.py`, the version-mismatch scenario, and one
crash-style fixture) and defect fixtures whose own assertions require every id to have actually
run (e.g. checking the full registry's status table, or a `--report-json` verdict) are
deliberately left as full, unscoped runs. Harness unit tests use short (≤2s) per-call timeouts
and `asyncio.run(...)` directly -- there is no `pytest-asyncio` dependency. The conformance
suite's own async tests are run the same way, via `tck.common.plugin`'s `pytest_pyfunc_call`
hook.

## CI

`.github/workflows/ci.yml` runs on every push to `main`, every pull request, and on manual
`workflow_dispatch`. Two jobs:

- **`test`** -- `astral-sh/setup-uv` (cached), `uv python install 3.14`, `uv sync --locked`,
  `uv run pytest -q`. This is the required, blocking job.
- **`cross-check`** -- `needs: test`, `continue-on-error: true` (informational only). Clones
  `rust-sdk`/`python-sdk` as sibling checkouts pinned to the SHAs recorded in
  `docs/cross-check.md`, builds `testy` with `Swatinem/rust-cache` caching cargo, runs
  `scripts/cross-check.sh` (v1 legs plus, since slice V2-7, the two v2 legs -- `testy` built
  with the `unstable_protocol_v2` feature into an isolated `--target-dir`, and the
  repo-authored `scripts/cross-check/python_v2_agent.py` against the Python SDK's
  `acp.experimental.v2` runtime), uploads all four `--report-json` reports as one artifact,
  then runs `scripts/cross-check-summary.py` with `--expect-only-mandatory-fail ACP-INIT-003`
  (the v1 baseline) plus two `--expect LABEL=ID,...` overrides for the v2 legs to assert
  neither scorecard has drifted from the documented baseline in `docs/cross-check.md` (v1: both
  upstream agents FAIL only `ACP-INIT-003`; v2: `testy_v2` is fully clean, `python_v2_agent`
  FAILs exactly its documented five ids -- see "Cross-checking against upstream agents" below).
  Its own exit code does not fail the workflow -- read the uploaded reports and the summary
  step's output when it goes red.

## Cross-checking against upstream agents

`scripts/cross-check.sh` runs the packaged conformance suite against independently implemented
agents to sanity-check the TCK's own plumbing (framing, id correlation, schema wiring, timeouts)
against implementations this repo did not write -- for v1, the Rust SDK's `testy` fixture and
the Python SDK's `examples/echo_agent.py`; for v2 (added in slice V2-7), `testy` again (built
with the `unstable_protocol_v2` feature, routing to its native v2 agent) and a small,
repo-authored v2 agent, `scripts/cross-check/python_v2_agent.py`, built on the Python SDK's
`acp.experimental.v2` runtime -- there is no upstream v2 example agent yet (see
`.agents/research/reference-sdks-v2-status.md`). It is **not** part of `uv run pytest`: it needs
a Rust toolchain and local checkouts of both SDKs, so it is a manual/CI step, run on demand.

**Prerequisites:**

- A Rust toolchain (`cargo`, `rustc >= 1.88`) on `PATH`, new enough for the rust-sdk revision's
  `unstable_protocol_v2` cargo feature if the v2 legs are enabled (the default).
- Local checkouts of `agentclientprotocol/rust-sdk` and `agentclientprotocol/python-sdk` --
  by default the paths recorded in `.agents/skills/check-rust-sdk/.repo` and
  `.agents/skills/check-python-sdk/.repo`; override with the `ACP_RUST_SDK` / `ACP_PYTHON_SDK`
  environment variables to point at any other checkout.
- `uv` (already required for everything else in this repo).

**Running:**

```
scripts/cross-check.sh
```

Set `ACP_CROSS_CHECK_V2=0` to skip both v2 legs and run only the v1 comparison (e.g. if the
local Rust toolchain lacks the `unstable_protocol_v2` feature, or to keep a quick v1-only smoke
run).

`OUT_DIR` (default `scratch/cross-check/`, gitignored) controls where the `--report-json`
reports land (`testy.json`/`echo_agent.json` for v1, `testy-v2.json`/`python-v2.json` for v2).
The script:

1. builds `testy` with `cargo build -p agent-client-protocol-test --bin testy
   --no-default-features` (strict-v1 build; the default `unstable` feature adds a non-v1
   `mcpCapabilities.acp` field) inside `$ACP_RUST_SDK` -- this is the only write the script
   makes outside `$OUT_DIR`, and it only ever touches that checkout's own `target/`;
2. runs `acp-tck --cancel-prompt wait_for_cancel --report-json "$OUT_DIR/testy.json" --
   target/debug/testy` (the `wait_for_cancel` prompt is required for `testy`'s cancel scenario
   to actually hang long enough for `session/cancel` to land -- see
   `.agents/research/testy-cross-check.md` §2.1);
3. runs the same against `uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python
   "$ACP_PYTHON_SDK/examples/echo_agent.py"` -- pinned explicitly, because `echo_agent.py`'s own
   unpinned PEP 723 header would otherwise resolve the latest *stable* release, which has a
   known prompt-deserialization bug (fixed on `main`/`1.0.0rc1`; see
   `.agents/research/testy-cross-check.md` §3.3);
4. (v2, unless `ACP_CROSS_CHECK_V2=0`) builds `testy` again with `--no-default-features
   --features unstable_protocol_v2`, into an **isolated** `--target-dir` (`$OUT_DIR/target-v2`)
   rather than the checkout's own `target/` -- reusing the v1 leg's binary/directory for a
   dual-feature build was tried and found to silently change the v1 leg's own `ACP-INIT-003`
   result (see `docs/cross-check.md` "Why the v2 Rust build uses a separate `--target-dir`" for
   the full explanation), so the two builds are kept fully separate;
5. (v2) runs `acp-tck --protocol-version 2 --cancel-prompt wait_for_cancel --report-json
   "$OUT_DIR/testy-v2.json" -- <the v2 testy binary>`, then the same against
   `uv run --no-project --with 'agent-client-protocol==1.0.0rc2' python
   scripts/cross-check/python_v2_agent.py`;
6. prints a compact per-requirement comparison table (via `scripts/cross-check-summary.py`,
   stdlib only, extended in slice V2-7 to accept more than two `--report PATH LABEL` pairs and
   per-report `--expect LABEL=ID,...` overrides) plus every agent's verdict line and exit code.

The script itself always exits `0` if it ran to completion -- every agent's own verdict is data
to read, not the script's success/failure. **Expected result** (see `docs/cross-check.md` for
the full tables, explanations, and date of the last run):

- v1: both `testy` and `echo_agent` are NOT CONFORMANT, solely because of the deliberately
  strengthened `ACP-INIT-003` (both echo the client's unsupported requested version verbatim)
  and the ADVISORY `ACP-INIT-004` (neither sets `agentInfo`); `echo_agent`'s cancel tests are
  permanently SKIPPED (it has no cancellation handling at all).
- v2: `testy_v2` (native Rust v2 agent) is fully **CONFORMANT** -- zero FAILs. `python_v2_agent`
  is NOT CONFORMANT, FAILing exactly `ACP-BATCH-201`/`ACP-BATCH-202` (MANDATORY) plus
  `ACP-INIT-003`/`ACP-INIT-201`/`ACP-INIT-202` (MANDATORY): the upstream Python SDK's v2
  transport has no JSON-RPC batch support at all (an uncaught `AttributeError` crashes the
  process on any batch array) and its native v2 `Agent` rejects any `protocolVersion != 2` with
  a strict `-32602`, instead of negotiating down/up per the spec's rule -- both pre-existing,
  documented upstream SDK limitations (`.agents/research/acp-v2-cancellation-and-batching.md`
  §B, `.agents/research/reference-sdks-v2-status.md`), not TCK bugs.

Any *other* deviation from either documented baseline is worth investigating -- it means either
a TCK bug or a genuine, newly-observed upstream behaviour; `docs/cross-check.md` is where that
investigation is recorded.

## How to add a requirement + test

This describes adding to the v1 suite; a future version's suite follows the same shape under its
own package (`src/tck/v2/`, ...).

1. Add a `Requirement(...)` entry to `_DECLARATIONS` in `src/tck/v1/requirements.py`: pick an id
   (`ACP-<AREA>-<NNN>`), a `Tier` (from `tck.common.requirements`), and cite the exact
   `research/*.md` line(s) that back it -- these reports are the specification, not memory of
   the protocol.
2. Write a test under `src/tck/v1/conformance/`, marked `@pytest.mark.requirement("ACP-…")` with
   a docstring starting with the id(s). Use `connected_agent()` from `_helpers.py` to spawn the
   agent; `async def` tests work without any extra setup.
3. If the requirement only applies when the agent advertises a capability, add
   `@pytest.mark.capability("agentCapabilities.some.path")` too -- the test is skipped with
   reason "capability ... not advertised" (or "initialize failed") otherwise. By default this
   checks for an *object marker*: supported iff the path resolves to a present, non-`null`
   value (an empty object still counts -- e.g. `"loadSession": {}`). For a plain boolean gate
   (supported iff the value is exactly `true`, e.g. `"loadSession": false` must NOT count as
   advertised), pass `boolean=True`: `@pytest.mark.capability("agentCapabilities.loadSession",
   boolean=True)`. See `capability_is_supported()` in `src/tck/common/plugin.py` and its unit
   tests in `tests/common/test_plugin.py` for both encodings.
4. If the test needs to send a custom/probe method the agent isn't expected to recognize (e.g.
   an "unknown method" negative control), prefix it with `_` (`_tck/does_not_exist`, `_tck/big`,
   ...) -- Req 42 / the extensibility rule requires custom methods to be `_`-prefixed, and the
   TCK holds itself to the same rule so its own probe traffic can never collide with a real,
   spec-defined method name.
5. Run `uv run pytest` -- `tests/v1/test_registry.py` fails if the new id isn't referenced by a
   test, or if a test references an id that isn't registered.
6. Consider adding a non-conforming fixture under `tests/fixtures/agents/v1/` that trips only the
   new requirement, and assert on it in `tests/v1/test_cli.py`.

## Tiers and statuses

Tiers (`tck.common.requirements.Tier`, shared across protocol versions): `MANDATORY` (MUST),
`CAPABILITY` (only applies when the agent advertises the capability), `ADVISORY` (SHOULD;
reported, never the sole cause of a failing verdict), `INFORMATIONAL` (spec silent / SDKs
disagree; reported only, never affects the verdict).

Statuses (`tck.common.report.Status`): `PASS`, `FAIL`, `SKIPPED`, `NOT_TESTED`. A test only ever produces
the first three; `NOT_TESTED` is the aggregated status of a registered id that no test bound to
during the run (a dead agent that never gets past `initialize` cannot score 100% by starving
every other requirement of a record). A test that *errors* -- a setup/teardown exception, or a
harness `AgentExited`/`AgentTimeout` propagating out of the test body -- is `FAIL`, not a separate
status; the exception text becomes the outcome's `message`. Aggregating several tests bound to
the same requirement: any `FAIL` wins; else any `PASS`; else any `SKIPPED`; no records at all ->
`NOT_TESTED`. The terminal summary prints this aggregated status per id, grouped by tier.

## Reporting (`tck.common.report`, `--report-json`)

`--report-json PATH` (plugin: `--tck-report-json`) writes the full run as JSON at
`pytest_sessionfinish`, in addition to the terminal summary. Top-level keys: `tck_version`,
`protocol_version` (from the active version's `VersionSpec.protocol_version`, e.g.
`tck.v1.protocol.PROTOCOL_VERSION`), `schema_revision` (from `VersionSpec.schema_revision`, e.g.
`tck.v1.protocol.SCHEMA_REVISION` -- the single source of truth; `tck.v1.requirements.
SPEC_REVISION` reads from it too), `agent_command` (the launched command, as a list),
`agent_info` / `agent_capabilities` (from the cached `initialize` result, or `null` if it never
succeeded), `started_at` / `finished_at` (ISO 8601 UTC), `requirements`, `verdict`.

`requirements` has one entry per id in the active version's registry (e.g.
`tck.v1.requirements.REGISTRY`) -- including ids no test ever ran (`status: "NOT_TESTED"`,
`tests: []`) -- each carrying its `tier`/`capability`/`text`/
`citation` plus every bound test's outcome (`nodeid`, `status`, `message`, `duration_s`,
`properties` -- `record_property(...)` values such as `acp_tck_cancel_race_ms` -- and, for `FAIL`
outcomes only, `transcript` (`[{"dir": "sent"|"received", "t": <monotonic ts>, "raw": <line>},
...]`, each entry's own `raw` capped at 4 kB with a `"...[truncated N byte(s)]..."` marker, and
the whole list capped at 400 entries -- first/last 200 with a gap marker in between, since the
handshake/setup and the failure itself are almost always what matters and a chatty middle is
safest to elide; review-slices-5-6.md S8) and `stderr` (truncated to the last 20 kB).

`verdict` is `{"conformant": bool, "blocked_by_auth": bool, "blocked_by_version_mismatch": bool,
"tier_counts": {tier: {status: count}}}`. `conformant` is computed from `MANDATORY`- and
`CAPABILITY`-tier requirements, plus `blocked_by_auth`/`blocked_by_version_mismatch`: `true` iff
no `MANDATORY` `FAIL`, no `MANDATORY` `NOT_TESTED`, no `CAPABILITY` `FAIL`, and neither flag is
set. A `CAPABILITY` `SKIPPED`/`NOT_TESTED` (not advertised, or simply never exercised) does not
affect it -- only a *failed* capability check does, since the agent advertised it and it must
then work. `ADVISORY`/`INFORMATIONAL` never affect it.
`blocked_by_auth` is `true` whenever any test was `SKIPPED` with a message containing the
literal marker `"AUTH-GATED:"` (a substring match, not a prefix -- the recorded message is
`str(report.longrepr)`, which for a skip wraps the reason in a `(path, lineno, "Skipped: ...")`
repr, so a prefix check would never match; see `common/plugin.py`'s `_AUTH_GATED_MARKER` and
review-slices-5-6.md N18) -- i.e. the agent requires authentication before `session/new` and no
`--auth-method` was given, so session-dependent requirements were never actually exercised and
the run cannot be honestly scored conformant regardless of how many other checks passed.
`blocked_by_version_mismatch` (v2 only so far; always `false` for a v1 run) is `true` by the same
substring-match mechanism against the marker `"VERSION-MISMATCH:"` -- emitted from two places:
`_tck_capability_gate` (`common/plugin.py`) for capability-gated requirements (e.g.
`ACP-SESSION-001`/`002`) whenever the cached `initialize` result's `protocolVersion` doesn't
match this run's target, and `tck.v2.conformance._helpers.skip_if_version_mismatch(...)` for the
v2-shape requirements in `test_initialize.py` (`ACP-INIT-203`/`204`/`ACP-SCHEMA-001`) that have
their own fresh `initialize` call and so aren't covered by the capability-gate fixture. Either
way the meaning is the same: the agent under test never actually negotiated the protocol version
this run is checking, so any version-dependent requirement it would otherwise skip as "not
advertised" is instead flagged as never having been meaningfully exercised at all. See
`src/tck/common/report.py` for the full model (`Status`,
`TestOutcome`, `RequirementResult`, `Verdict`, `Report`) and `tests/common/test_report.py` for
the aggregation rules exercised against synthetic data.

## Harness API (`tck.common.harness`)

Raw, hand-rolled asyncio NDJSON stdio client -- deliberately not built on the ACP Python SDK,
whose typed layer cannot emit malformed traffic and whose transport silently drops
non-conforming lines. This harness never drops or crashes on anything the agent sends; it
records it.

- `AgentLaunch(command, cwd=None, env_overrides={}, startup_timeout=5.0, default_timeout=5.0,
  max_line_bytes=64*1024*1024)` -- launch configuration. `env_overrides` is applied on top of
  the inherited `os.environ`. `max_line_bytes` is passed as `create_subprocess_exec(limit=...)`
  (the `StreamReader` buffer size) *and* is the line-reassembly threshold below: a single
  oversized stdout line is never truncated or dropped, only flagged (see `read_line` below).
- `AgentProcess(launch)` -- async context manager; spawns the subprocess in its own process
  group (POSIX) so the whole group can be terminated.
  - `send_raw(bytes | str)` -- writes exactly the given bytes plus `\n`; use this for
    deliberately malformed traffic. `drain()` is bounded by `launch.default_timeout`; a stuck
    write (e.g. an agent that never reads stdin, filling the pipe buffer) raises `AgentTimeout`
    instead of hanging the test forever.
  - `send_message(dict)` -- compact `json.dumps` plus `\n`.
  - `send_request(method, params=None, *, id=None) -> id` -- auto-increments an int id unless
    one is given (string ids allowed).
  - `send_notification(method, params=None)`.
  - `read_line(timeout=None) -> TranscriptEntry` -- next stdout line, raw bytes plus best-effort
    UTF-8/JSON decoding. Byte-lossless even past `max_line_bytes`: internally loops
    `StreamReader.readuntil(b"\n")`, and on `LimitOverrunError` consumes exactly the buffered
    bytes via `readexactly` and keeps looping rather than following `readline()`'s own behavior
    of silently discarding them -- the resulting `TranscriptEntry.oversize` is `True` whenever
    this happened, `False` otherwise. Raises `AgentTimeout` (carries the transcript so far) or
    `AgentExited` (carries exit code, `stderr_text()`, and the transcript).
  - `wait_for_response(id, timeout=None)` / `wait_for_message(predicate, timeout=None)` -- read
    until a match; every other line read along the way stays in `transcript` and is available
    via `pending()`.
  - `transcript: list[TranscriptEntry]` -- everything sent and received, in order, both
    directions, malformed lines included.
  - `stderr_text()` -- everything captured from stderr so far (drained continuously in the
    background so the child never blocks on it, bounded to the last 64 kB with a "truncated N
    earlier byte(s)" prefix once exceeded).
  - `close(grace=2.0)` -- close stdin, wait; SIGTERM the process group, wait; SIGKILL. Sets
    `exit_code` and `exited_on_stdin_close`. At each stage of that ladder, drains and records
    whatever the agent has already written to stdout since the last line any test read --
    including a partial final line with no trailing newline -- so output written after the last
    `read_line`/`wait_for_*` call (e.g. garbage flushed only once stdin hits EOF) still lands in
    `transcript` and is still checked by ACP-TRANSPORT-001/002. Never raises on lateness; each
    drain stage has its own short deadline carved out of `grace`.
- `TranscriptEntry` -- `direction`, `raw`, `timestamp`, `text`/`text_error`,
  `parsed`/`parse_error`, `oversize` (see `read_line` above). Decode/parse failures are recorded
  as fields, never raised.

## Fixture agent catalogue

All fixtures are pure Python, stdlib only, deterministic, offline, ~50 lines:

- `conforming.py` -- handles `initialize`, `session/new`, `session/prompt`, `session/cancel`,
  and a harness-only `_tck/env` method (echoes an env var, for testing env-override
  propagation). A prompt whose text is exactly `__hang__` withholds its response until
  `session/cancel` arrives, to make the cancel flow testable. Unknown methods get `-32601`.
- `banner_on_stdout.py` -- conforming, but prints a human banner to stdout first (violates the
  "stdout is ACP-only" transport rule).
- `stderr_chatter.py` -- conforming, logs to stderr on every message received.
- `never_responds.py` -- reads stdin forever, never writes; does not exit on stdin EOF.
- `exits_immediately.py` -- exits 0 without reading anything.
- `rejects_second_initialize.py` -- conforming, but a second `initialize` on the same connection
  gets `-32600` instead of a normal handshake response; self-test proving no test in the suite
  itself ever sends a second `initialize`.
- `supports_v1_and_v2.py` -- advertises `protocolVersion: 2` support; correctly negotiates down
  to `1` for a client that only sends `protocolVersion: 1`. Self-test for ACP-INIT-003's
  `version != 65535 and version >= latest_supported` rule (PASS case, paired with
  `echoes_any_version.py`'s FAIL case).
- `router_requires_info.py` -- models the reference SDKs' dual-version ACP v1/v2 protocol
  *router* (`.agents/research/acp-v2-version-negotiation.md`, "Router trap for the TCK"): a
  request for exactly `protocolVersion: 1` gets an ordinary v1 handshake, but anything `>= 2`
  (including ACP-INIT-003's 65535 probe) is routed to v2, whose `InitializeRequest.info` is
  REQUIRED -- a missing/malformed `info` gets `-32602` naming the missing field, a valid one
  gets back `protocolVersion: 2`. Self-test canary for slice V2-0b: before ACP-INIT-003's probe
  carried an `info` object, this fixture reproduced the spurious `-32602` a real router agent
  gives for a params-shape reason unrelated to negotiation, FAILing ACP-INIT-003 and flipping
  the whole run NOT CONFORMANT; it PASSes after the fix.
- `asks_permission_closable.py` -- `asks_permission.py` plus `sessionCapabilities.close`;
  delays its permission request past `run_prompt`'s peek window so `session/close` deterministically
  wins the race, then replies to `session/close` before resolving the pending permission request
  as cancelled. Self-test for ACP-CLOSE-002 against a conforming, permission-asking agent, and
  (via `test_cancel.py`) for the otherwise-dead "cancelled" permission-outcome branch in
  `run_prompt` (review-slices-5-6.md S3, S10a).

See the layout listing above for the slice-4 defect fixtures (`hangs_until_cancel.py`,
`cancel_returns_error.py`, `cancel_wrong_stop_reason.py`, `update_after_response.py`,
`bad_stop_reason.py`, `duplicate_session_id.py`, `update_wrong_session.py`).

`cancel_wrong_stop_reason.py` sleeps 1.2s after receiving `session/cancel` before replying with
its (wrong) `stopReason: "end_turn"` -- an instant reply would land inside `test_cancel.py`'s
1.0s race window and, since `"end_turn"` is itself a valid `StopReason`, would make the cancel
test SKIP ("cancellation not exercised") instead of catching the defect. None of the other
fixtures need this: `cancel_returns_error.py`'s JSON-RPC error FAILs regardless of timing, and
`bad_stop_reason.py`/`update_wrong_session.py`/`conforming.py` etc. don't hang on the cancel
tests' prompt text at all (only the literal `__hang__` text triggers a hang in `conforming.py`
and `bad_stop_reason.py`), so `session/cancel` always loses the race against their immediate
reply and ACP-CANCEL-001/002 SKIP for them too -- see `tests/v1/test_cli.py`'s `_CANCEL_IDS` note.

## Mock-client prompt driver (`_helpers.run_prompt`)

`test_session.py`/`test_prompt.py`/`test_cancel.py`/`test_session_capabilities.py` drive
`session/prompt` through `run_prompt(agent, session_id, blocks, *, on_cancel=False,
on_action=None, cancel_wait=0.5, timeout)` (`_helpers.py`), which acts as a minimal ACP client
for whatever the agent under test sends during the turn:

- `session/request_permission` is answered `{"outcome": {"outcome": "selected", "optionId":
  <first option's optionId>}}`, or `{"outcome": {"outcome": "cancelled"}}` once
  `session/cancel` has actually been sent for this turn.
- any other agent -> client request (`fs/*`, `terminal/*`, `elicitation/create`, ...) gets
  `-32601` (the mock client advertises `clientCapabilities: {}`), and is recorded on
  `PromptTurn.client_requests_seen` for later negative tests to use.
- `session/update` notifications are recorded, in order, as `(transcript_index, entry)` pairs.

It returns a `PromptTurn(response_entry, updates, client_requests_seen, cancelled_at_index,
action_response, action_sent_at_index)`. `cancelled_at_index` is `None` unless `on_cancel=True`
**and** `session/cancel` was actually sent before the prompt resolved -- see the race note below.

`on_action`, if given, is a zero-argument async callable fired at the same trigger point as
`on_cancel` (first update, or `cancel_wait` elapsed) instead of/alongside sending
`session/cancel` -- used by ACP-CLOSE-002 to send `session/close` mid-turn. Its response lands on
`PromptTurn.action_response`/`action_sent_at_index` (mirroring `cancelled_at_index`), both `None`
if `on_action` was not given or never fired. If the prompt's own response arrives before the
action's response -- a valid ordering the spec makes no claim against -- `run_prompt` does one
short peek read (the same window `cancel_race_peek` gives an update's immediate response) for the
action's response before returning, so an agent that replies to the action *after* resolving the
pending prompt doesn't lose that response to an early return (a real bug found and fixed via
`conforming_full.py`'s ACP-CLOSE-002 self-test, review-slices-5-6.md S3).

If `on_cancel=True`, `run_prompt` sends `session/cancel` for `session_id` as soon as either the
first `session/update` arrives or `cancel_wait` seconds elapse, whichever is first. This has an
inherent race for a real (or fixture) agent that replies immediately after its last update: by
the time the TCK has read that update, the agent may have *already* written its response to the
pipe, before the TCK ever decides to send cancel. `run_prompt` mitigates the most common case with
a short non-blocking-ish look for the response right after an update and before committing to
cancel -- if the response is already there, it is returned with `cancelled_at_index=None`, i.e.
as an honest race rather than a false "cancel preceded the response". This peek window and the
skip window below are not fixed constants: `_helpers.cancel_race_peek(timeout)` and
`_helpers.quiet_period(timeout)` derive both from whatever `--timeout` (`agent_launch.
default_timeout`) is in effect for the run, so a larger `--timeout` against a slower real agent
widens both windows instead of leaving them pinned to defaults tuned for the fast, offline
fixtures.

`test_cancel.py` (ACP-CANCEL-001/002) never turns an unavoidable race into a PASS or FAIL --
claiming a requirement was exercised when it was not is dishonest. It `pytest.skip("cancellation
not exercised: ...")` in two situations (`.agents/plan.md` "Cancel tests and the race"): (1)
`cancelled_at_index is None` -- the response was read before `session/cancel` could be sent at
all; (2) `session/cancel` was sent, but the response arrives with a valid, non-`cancelled` stop
reason within `quiet_period(agent_launch.default_timeout)` (measured off the transcript's
monotonic timestamps between the cancel notification and the response) -- the agent may simply
have finished on its own before reading the notification. The elapsed milliseconds are recorded
via `record_property("acp_tck_cancel_race_ms", ...)`. Outside those two situations the
requirement is judged normally: `stopReason: "cancelled"` PASSes; a JSON-RPC error, or a
non-`cancelled` stop reason arriving outside the race window, FAILs. The cancel tests use
`--cancel-prompt` text (see above) instead of the short text other prompt tests use, specifically
to make situations (1)/(2) less likely against a real agent.

## v2 mock-client prompt driver (`tck.v2.conformance._helpers.run_prompt`)

`src/tck/v2/conformance/test_prompt.py` and (for its own prompt-turn extension of
`ACP-SCHEMA-001`) `test_initialize.py` drive `session/prompt` through
`run_prompt(agent, session_id, blocks, *, on_cancel=False, on_action=None, cancel_wait=0.5,
extra_params=None, timeout)` -- the v2 counterpart of v1's `_helpers.run_prompt` above, deliberately
a separate, non-shared implementation (`.agents/plan.md` D6: "honest duplication, not shared
machinery") because the v2 turn-end contract is fundamentally different from v1's.

**The v1-vs-v2 inversion.** In v1, the `session/prompt` response *is* the turn's result: it
carries `stopReason` directly, and the response arriving is itself the turn-end signal. In v2,
the response is only an acceptance receipt sent at insertion time (`{messageId}`, no
`stopReason` at all) -- the turn's actual outcome is learned entirely from a later
`session/update` notification carrying `{sessionUpdate: "state_update", state: "idle", ...}`
(`.agents/research/acp-v2-prompt-lifecycle.md` §4). `run_prompt`'s turn-end predicate is
therefore `response_entry is not None and (ended_by_error or idle_update is not None)` -- both
halves must be true; a bare acceptance receipt with no terminating idle yet is not a finished
turn.

**Turn-end predicate for the idle itself** (research §4 "Mock-client prompt driver design
note", point 3): a `state_update {state: "idle"}` observed for `session_id` only counts as the
turn's terminator if it carries a `stopReason`, *or* a `state_update {state: "running"}` for
`session_id` was observed earlier in the same call. This deliberately excludes the legal
"session-ready idle" a spec-conforming agent may send with no preceding prompt at all (e.g.
right after `session/new` -- observed live in the Python SDK's own v2 test agent, and exercised
by the self-test fixture `idle_before_running.py`) from ever being mistaken for a turn's end. A
bare idle matching neither condition is simply recorded like any other update, and reading
continues (bounded by `timeout` as always).

**Tolerating an initial ready-idle sent before `session/prompt`.** Unlike v1's `run_prompt`,
this does **not** drain `agent.pending()` before sending the request -- doing so would make a
ready-idle the caller's own earlier reads left buffered there appear to be part of *this*
turn's `updates`, which would not be accurate. Any such notification stays in `agent.pending()`
for the caller to inspect directly if it cares.

While waiting, `run_prompt` acts as a minimal mock ACP client exactly like v1's: every
`session/update` is recorded (`updates`, `(transcript_index, entry)` pairs, in arrival order,
regardless of which `sessionId` it carries -- a mismatched one is `ACP-PROMPT-205`'s evidence,
not the driver's business to filter out); `session/request_permission` is answered
`{"outcome": {"outcome": "selected", "optionId": <first option's optionId>}}`, or
`{"outcome": {"outcome": "cancelled"}}` once `session/cancel` has actually been sent for this
turn; any other agent -> client request gets `-32601` (the mock client advertises
`capabilities: {}`) and is recorded on `PromptTurn.client_requests_seen`.

It returns a `PromptTurn(response_entry, message_id, running_seen, idle_update, stop_reason,
updates, client_requests_seen, cancelled_at_index, action_response, action_sent_at_index)`.
`message_id` is the response's `result.messageId` if present and a string, else `None`.
`running_seen`/`idle_update`/`stop_reason` capture the `state_update` machinery described above.
`on_cancel`/`on_action`/`cancel_wait`/`extra_params` mirror v1's `run_prompt` exactly, including
the same cancel-race mitigation via `cancel_race_peek(timeout)` -- built for a later slice
(cancellation / `session/close` mid-turn); no test in V2-2a exercises them yet. V2-2b is the
first slice to actually exercise the permission-answering path (`ACP-PERM-201`, via
`AsksPermissionAgent`) and `client_requests_seen` (`ACP-CLIENTCAP-201/202`) -- both already
worked correctly with zero changes to `run_prompt`/`_helpers.py` itself.

Every wait inside `run_prompt` is bounded by `timeout`, so a non-conforming agent that never
reaches either terminator (e.g. `no_idle_after_running.py`, `update_wrong_session.py`) produces
an honest `AgentTimeout` -- a FAIL for whatever the caller was asserting -- never a hang; see
those fixtures' entries in the catalogue above for the exact, documented cascade this produces
across all six V2-2a ids plus `ACP-SCHEMA-001`'s prompt-turn extension.

## Vendored schema (`tck/v1/schema/`)

`schema.json` and `meta.json` are verbatim copies of the ACP v1 JSON Schema from the spec
repo (`https://github.com/zed-industries/agent-client-protocol`); the commit hash, vendor
date, and exact copy commands live in `src/tck/v1/schema/VENDORED.md`. Refresh procedure is
documented there. Do not hand-edit either JSON file.

The vendored schema's top level (`schema.json:4-119`) is `anyOf` of three side-annotated
envelopes -- `Agent`, `Client`, `ProtocolLevel` -- each split into `Request` / `Response` /
`Notification` branches. Every method-specific params/response `$def` carries `x-side`
(which side implements the method) and `x-method` (its wire name); `tck.v1.protocol` and
`tck.v1.validation` derive their method-name tables from these annotations plus `meta.json`
rather than hand-copying a table from docs, so a schema refresh mostly self-updates them.
`tck.v2` vendors its own schema under its own package (`src/tck/v2/schema/`) the same way; a
future v3 effort would do likewise.

## `tck.v1.protocol`

`PROTOCOL_VERSION = 1`. JSON-RPC/ACP error code constants (`PARSE_ERROR`, `INVALID_REQUEST`,
`METHOD_NOT_FOUND`, `INVALID_PARAMS`, `INTERNAL_ERROR`, `REQUEST_CANCELLED`,
`AUTHENTICATION_REQUIRED`, `RESOURCE_NOT_FOUND`). `StopReason` constants and the `STOP_REASONS`
frozenset. Method inventories, all derived from `meta.json`/`schema.json` at import time:
`AGENT_METHODS` (client -> agent, requests and notifications), `CLIENT_METHODS` (agent ->
client), `AGENT_NOTIFICATIONS` / `CLIENT_NOTIFICATIONS` (the notification-only subsets of each,
cross-derived from `schema.json`'s `AgentNotification`/`ClientNotification` `$def`s since
`meta.json` itself does not separate requests from notifications). `tck.v2` has its own
`tck.v2.protocol` module built the same way (this module is not shared -- see
`src/tck/common/version.py`'s `VersionSpec`, which is how `tck.common.plugin` learns the active
version's protocol number/schema revision without importing a specific version's module).

## `tck.v1.validation`

Validates JSON-RPC messages the **agent under test** writes to stdout against v1's vendored
schema (never messages the TCK's own mock client writes -- there is no `validate_client_*`
yet). `ValidationIssue(path, message, schema_path)` -- `path`/`schema_path` are JSON pointers;
never raises, always returns issues. Duplicated per protocol version rather than shared (see
`.agents/research/common-v1-v2-split-analysis.md` D6) -- `tck.v2.validation` is its own module,
not a parametrization of this one.

- `validate_agent_message(msg: dict) -> list[ValidationIssue]` -- dispatches on shape: a
  request/notification (`method` present) is checked against that method's params schema; a
  response (`method` absent) only gets the JSON-RPC envelope check (`jsonrpc`, `id` type,
  `result` XOR `error`, error object shape) -- use `validate_agent_response` for the `result`
  payload, since picking the right response schema requires knowing which request it answers.
- `validate_agent_response(method: str, msg: dict) -> list[ValidationIssue]` -- envelope check
  plus `result` validated against `method`'s response schema (or `error` against the shared
  `Error` schema).
- Documented spec quirk (protocol-surface report, Discrepancy 3): `session/load`'s response
  docs show `null` where the schema types an all-optional object. The vendored schema does
  **not** itself accept `null` there (checked: `LoadSessionResponse` is `type: "object"`, no
  `"null"` in an outer `anyOf`), so `validate_agent_response` special-cases it -- `null` is
  accepted whenever the target response schema is an object type with zero required fields.
- The vendored schema never sets `additionalProperties: false` anywhere (checked: zero
  occurrences), so it cannot reject an unknown root field on a spec type even though the
  spec's prose (`extensibility.mdx`) says implementations MUST NOT add one; `validate_agent_message`/
  `validate_agent_response` do not flag this (see
  `tests/v1/test_validation.py::test_unknown_root_field_is_permitted_by_the_vendored_schema`).
- `find_unknown_root_keys(def_name, obj) -> list[str]` (slice 7, backs ACP-SCHEMA-002) is the
  hand-written check that fills that gap: `_allowed_root_properties(def_name)` walks
  `allOf`/`anyOf`/`oneOf`/`$ref` to resolve the full property-name union a `$def`'s composition
  permits (always including `_meta`), and `find_unknown_root_keys` flags any root key of `obj`
  outside that set. Returns `[]` -- nothing to flag -- for a non-dict `obj`, or when the `$def`
  resolves no `properties` anywhere (e.g. a bare scalar/array union like `RequestId`) since
  there is nothing meaningful to compare keys against in that case.

## Conventions

- Dependency management is `uv` only, with exact pins (`==`), never bare `pip` or hand-edited
  `pyproject.toml` dependency entries.
- ACP **v1** (`src/tck/v1/`) is the default and complete suite; ACP **v2** (Draft, `src/tck/v2/`)
  is a skeleton behind `--protocol-version 2`, growing slice by slice. The codebase is structured
  (`src/tck/common/` + one package per version) so each version's package adds its own protocol/
  validation/requirements/conformance modules without forking the harness, report model, or
  pytest plugin core -- see "Layout" above.
- `.agents/` is the orchestrator's workbench. `.agents/research/*.md` are read-only inputs --
  they are the specification this code implements; do not edit them.
- Licensed under Apache-2.0 (`LICENSE`); `pyproject.toml`'s `license`/`license-files` (PEP 639) are the source of truth -- do not add a `License ::` classifier alongside them.
