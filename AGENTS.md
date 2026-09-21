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
`_`-prefixed) -- gated behind `--protocol-version 2`; default remains v1 -- and is expected to
grow in later slices. Everything below is v1-specific unless a section says otherwise.

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
                          (V2-2a), and (V2-2b) prompt content capabilities, the permission-
                          request flow, and the agent -> client method rules. v2 is Draft (schema version
                          `2.0.0-alpha.5` at the vendored pin) and expected to churn -- coverage
                          here is still well short of v1 parity and expected to grow in
                          follow-up slices (session lifecycle beyond `session/new`, the
                          `session/prompt` turn/update lifecycle, auth, ...). Mirrors `v1/`'s
                          shape but is its own, undiluted implementation -- nothing under `v2/`
                          imports from `v1/` (`.agents/research/common-v1-v2-split-analysis.md`
                          D6: honest duplication, not shared version-specific machinery).
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
    requirements.py         `SPEC_REVISION`, `_DECLARATIONS`, `REGISTRY`, `get()` -- 24
                          requirements (nine from V2-1b, six V2-2a prompt-turn ids, and nine
                          V2-2b additions: `ACP-PROMPTCAP-001/002/003` (reused v1 ids, re-cited
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
                          probes, `ACP-INFO-CONCURRENT-001`/`ACP-INFO-UNKNOWNSESSION-001`, mirroring
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
      test_informational.py   (V2-2b) ACP-INFO-CONCURRENT-001/ACP-INFO-UNKNOWNSESSION-001 --
                            report-only probes (`record_property`, never asserted on) for
                            concurrent-prompt and unknown-`sessionId` behaviour the v2 spec is
                            silent on; still FAILs if the prerequisite handshake itself fails.

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
    test_registry.py         `tck.v2.requirements.REGISTRY` invariants (all 24 ids: the nine
                          from V2-1b, V2-2a's six prompt-turn ids, and V2-2b's nine
                          `ACP-PROMPTCAP-001/002/003`/`ACP-PROMPT-003`/`ACP-PERM-201`/
                          `ACP-CLIENTCAP-201/202`/`ACP-INFO-CONCURRENT-001`/
                          `ACP-INFO-UNKNOWNSESSION-001`) + two-way check against
                          `tck.v2.conformance` markers
    test_cli.py               end-to-end: run `python -m tck --protocol-version 2 --
                            <fixture>` as a subprocess; routing checks (`--help`, and that the
                            default/`--protocol-version 1` path still runs the v1 suite
                            unchanged); the v2 conforming fixture PASSing every id it exercises
                            (V2-2b's `ACP-PROMPTCAP-001/002/003`/`ACP-PERM-201` SKIP against the
                            plain `conforming.py` fixture, since it neither advertises prompt
                            content capabilities nor ever asks permission); `conforming_full.py`
                            (V2-2b) PASSing literally every one of the 24 ids; one test per
                            defect fixture asserting its exact FAIL set (V2-2a adds eight: the
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
                            uses), and the positive control `calls_custom_method.py`; V2-2a's
                            `no_idle_after_running.py`/`update_wrong_session.py` self-tests were
                            also updated to include V2-2b's new run-prompt-dependent ids
                            (`ACP-CLIENTCAP-201/202`, `ACP-PERM-201`, `ACP-PROMPT-003`) in their
                            expected FAIL sets, since those fixtures break `run_prompt`'s
                            turn-completion detection for every test that depends on it, not
                            just the six V2-2a ids); and the version-mismatch scenario (the v1
                            conforming fixture run under `--protocol-version 2`: the
                            negotiation-outcome ids -- `ACP-INIT-001`/`003`/`201`/`202` -- PASS
                            normally against the honestly-downgraded-to-`1` response, while every
                            other MANDATORY/
                            CAPABILITY id -- computed as `(_MANDATORY_IDS | _CAPABILITY_IDS) -
                            _NEGOTIATION_IDS`, which now also covers V2-2a's six prompt-turn ids
                            -- SKIPs with the `VERSION-MISMATCH:` marker; zero FAILs anywhere, yet
                            `verdict.blocked_by_version_mismatch` is `true` and exit code is 1)
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
                          turn completion).
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
                          every one of the 24 registered ids; the intended "everything works"
                          fixture for a full-suite smoke run (`test_v2_conforming_full_agent_
                          passes_everything`)
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
`session/prompt` turn/`state_update` lifecycle, and (V2-2b) prompt content capabilities, the
permission flow, and the agent -> client method rules -- 24 requirements in all -- see
`src/tck/v2/`'s entry in "Layout" above); it is expected to grow in follow-up slices.

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
agent advertises no `authMethods` at all.

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
fixture) runs in well under a minute. Harness unit tests use short (≤2s) per-call timeouts and
`asyncio.run(...)` directly -- there is no `pytest-asyncio` dependency. The conformance suite's
own async tests are run the same way, via `tck.common.plugin`'s `pytest_pyfunc_call` hook.

## CI

`.github/workflows/ci.yml` runs on every push to `main`, every pull request, and on manual
`workflow_dispatch`. Two jobs:

- **`test`** -- `astral-sh/setup-uv` (cached), `uv python install 3.14`, `uv sync --locked`,
  `uv run pytest -q`. This is the required, blocking job.
- **`cross-check`** -- `needs: test`, `continue-on-error: true` (informational only). Clones
  `rust-sdk`/`python-sdk` as sibling checkouts pinned to the SHAs recorded in
  `docs/cross-check.md`, builds `testy` with `Swatinem/rust-cache` caching cargo, runs
  `scripts/cross-check.sh`, uploads the two `--report-json` reports as an artifact, then runs
  `scripts/cross-check-summary.py --expect-only-mandatory-fail ACP-INIT-003` to assert the
  scorecard hasn't drifted from the documented baseline (both upstream agents are expected to
  FAIL only `ACP-INIT-003`, per "Cross-checking against upstream agents" below). Its own
  exit code does not fail the workflow -- read the uploaded reports and the summary step's
  output when it goes red.

## Cross-checking against upstream agents

`scripts/cross-check.sh` runs the packaged conformance suite against two independently
implemented agents -- the Rust SDK's `testy` fixture and the Python SDK's
`examples/echo_agent.py` -- to sanity-check the TCK's own plumbing (framing, id correlation,
schema wiring, timeouts) against implementations this repo did not write. It is **not** part of
`uv run pytest`: it needs a Rust toolchain and local checkouts of both SDKs, so it is a manual/CI
step, run on demand. Pinned to ACP v1 for now; it stays that way until v2 reference SDKs exist to
cross-check against.

**Prerequisites:**

- A Rust toolchain (`cargo`, `rustc >= 1.88`) on `PATH`.
- Local checkouts of `agentclientprotocol/rust-sdk` and `agentclientprotocol/python-sdk` --
  by default the paths recorded in `.agents/skills/check-rust-sdk/.repo` and
  `.agents/skills/check-python-sdk/.repo`; override with the `ACP_RUST_SDK` / `ACP_PYTHON_SDK`
  environment variables to point at any other checkout.
- `uv` (already required for everything else in this repo).

**Running:**

```
scripts/cross-check.sh
```

`OUT_DIR` (default `scratch/cross-check/`, gitignored) controls where the two
`--report-json` reports land. The script:

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
4. prints a compact per-requirement comparison table (via `scripts/cross-check-summary.py`,
   stdlib only) plus both verdict lines and exit codes.

The script itself always exits `0` if it ran to completion -- the two agents' own verdicts are
data to read, not the script's success/failure. **Expected result** (see `docs/cross-check.md`
for the full table, explanations, and date of the last run): both agents are NOT CONFORMANT,
solely because of the deliberately strengthened `ACP-INIT-003` (both echo the client's
unsupported requested version verbatim) and the ADVISORY `ACP-INIT-004` (neither sets
`agentInfo`); `echo_agent`'s cancel tests are permanently SKIPPED (it has no cancellation
handling at all). Any *other* deviation from that baseline is worth investigating -- it means
either a TCK bug or a genuine, newly-observed upstream behaviour; `docs/cross-check.md` is where
that investigation is recorded.

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
