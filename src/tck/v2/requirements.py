"""ACP v2 (Draft) requirement registry.

## Id-reuse convention

A v1 id is reused bare only when the v2 requirement is truly the *same* one -- same text and
tier, only the citation moving to v2 sources. A changed tier, a changed capability-gate
encoding (e.g. v1's boolean `agentCapabilities.*` flags vs. v2's object-marker
`capabilities.*` paths), or a genuinely different wire shape/rule all count as a different
requirement and get a fresh `2xx` id instead of reusing the v1 number. v1 and v2 keep fully
separate `REGISTRY` dicts, so the same id string can (and does, e.g. `ACP-SESSION-001`/`002`)
carry a different tier per version without conflict.

Every requirement about a method in the `capabilities.session` seven-method baseline
(`session/new`, `session/list`, `session/resume`, `session/close`, `session/prompt`,
`session/cancel`, `session/update`) is `Tier.CAPABILITY`, `capability="capabilities.session"`,
never `Tier.MANDATORY`, regardless of the underlying spec obligation's own MUST-strength
wording -- only `initialize` itself is unconditionally required in v2; the whole session
surface is opt-in via that one capability marker. This applies throughout below and is not
repeated per row.

## `ACP-INIT-001`/`ACP-INIT-201`/`ACP-INIT-202`/`ACP-INIT-203` (version negotiation)

- `ACP-INIT-001` (reused from v1, narrowed): `initialize` succeeds with a non-error result.
  Schema/shape validation of the result moved to `ACP-SCHEMA-001`, so this row alone never
  SKIPs on a version mismatch -- a MUST-succeed handshake applies even to an agent that
  honestly negotiates down to a version other than 2.
- `ACP-INIT-201` (new, not a reuse of v1's `ACP-INIT-002`): v2's negotiation rule
  (initialization.mdx:92-96) is a two-branch rule -- "if the Agent supports the requested
  version, respond with the same version; otherwise, respond with its own latest supported
  version" -- unlike v1's single-branch echo, since a v2-requesting client can legitimately be
  answered with a *lower* version by an agent that doesn't support v2 yet.
- `ACP-INIT-003` (reused from v1): the unsupported-version (`65535`) probe -- the agent must
  answer with its own latest supported version, never echoing the unsupported request
  (`.agents/research/acp-v2-version-negotiation.md` requirement 10, case row `N > M`). Distinct
  from `ACP-INIT-201`'s own internal 65535 probe: the two ids assert different consequences of
  the same rule (mirroring v1's `ACP-INIT-002`/`003` split), so a fixture that unconditionally
  echoes the requested version correctly fails both.
- `ACP-INIT-202` (new): requesting `protocolVersion: 1` against a v2-only/dual agent must still
  produce a successful result whose value is `1` or `2`, never a JSON-RPC error
  (`.agents/research/acp-v2-version-negotiation.md` requirement 10, case row `N < min(S)`).
  Kept MANDATORY (the report flags this as debatable since both reference SDKs' strict v2
  endpoints violate the MUST by construction) to honor the spec's unambiguous text -- same
  posture already taken for `ACP-INIT-003`.
- `ACP-INIT-203` (new): `info` is REQUIRED in the v2 `initialize` result (v1's `agentInfo` was
  ADVISORY) -- a genuine tier promotion, so it gets its own id rather than reusing v1's
  `ACP-INIT-004`.
- `ACP-INIT-204` (new): every v2 capability marker is object-encoded, never boolean. A
  dedicated diagnostic id for report legibility even though the same defect also trips
  `ACP-SCHEMA-001`'s general schema validation -- kept as a separate row per
  `.agents/research/acp-v2-initialize-capabilities-baseline.md` §7.
- `ACP-SCHEMA-001` (reused from v1): every agent message validates against the schema,
  re-cited to v2's schema. Scoped to the `initialize` exchange only until the v2 prompt driver
  extends it to session traffic.

## Version-mismatch-aware v2-shape rows

`ACP-INIT-203`, `ACP-INIT-204`, and `ACP-SCHEMA-001` all judge the *shape* of the `initialize`
result against v2-only rules. An agent that honestly negotiates down to a version other than 2
never claimed a v2-shaped result, so each of these three tests calls
`tck.v2.conformance._helpers.skip_if_version_mismatch(init_result)` right after obtaining its
own `initialize` result, SKIPping with a `VERSION-MISMATCH:`-prefixed message (which forces the
run `Verdict.blocked_by_version_mismatch`, NOT CONFORMANT regardless -- see
`tck.common.report`/`tck.common.plugin`) instead of FAILing. `ACP-INIT-001` and the
negotiation-outcome rows (`ACP-INIT-003`/`201`/`202`) never call this helper -- they judge only
the negotiation outcome, not the result's shape, and an honest downgrade is not itself a
negotiation defect.

This is distinct from `tck.common.plugin`'s `_tck_capability_gate` autouse fixture, which only
gates `@pytest.mark.capability(...)` tests sharing the session-scoped `agent_initialize_result`
fixture: every test in `test_initialize.py` spawns its own process and sends its own
`initialize`, so there is no shared fixture to gate on and the check must be called explicitly.

## `ACP-SESSION-001`/`002`, prompt-turn core (`ACP-PROMPT-20x`, `ACP-STATE-20x`)

- `ACP-SESSION-001`/`002` (reused from v1): `session/new` succeeds with a unique, non-empty
  `sessionId` / two calls return distinct ids, re-cited to v2's contract (`cwd`-only required
  param, `mcpServers` optional unlike v1). `Tier.CAPABILITY` here vs. v1's MANDATORY, since v2's
  session surface is opt-in.

`session/prompt` itself is one of the seven session-baseline methods, so all rows below are
`Tier.CAPABILITY`, `capability="capabilities.session"` too, each with the test's own
`@pytest.mark.capability("capabilities.session")` marker for the SKIP.

- `ACP-PROMPT-205` (new id, not a reuse of v1's `ACP-PROMPT-002`): every `session/update`
  validates and carries the prompted `sessionId` -- same requirement text as v1's
  `ACP-PROMPT-002`, re-cited to v2's `UpdateSessionNotification` envelope and 17-variant
  `SessionUpdate` union (`.agents/research/acp-v2-prompt-lifecycle.md` requirement U1), but a
  changed tier (CAPABILITY not MANDATORY) makes it a different requirement needing a fresh id.
  Vacuous pass if the agent emits no updates during the turn.
- `ACP-PROMPT-201` (new): the `session/prompt` response is an object with a non-empty string
  `messageId` -- the acceptance-receipt shape that replaces v1's turn-result response entirely
  (`stopReason` moved to `ACP-STATE-203`).
- `ACP-PROMPT-203` (new): the agent echoes the inserted user message -- a `user_message` update
  (with `content`) or at least one `user_message_chunk` -- carrying the same `messageId` as the
  `session/prompt` response, for the prompted session.
- `ACP-STATE-201` (new): if a turn-ending idle `state_update` (one carrying a `stopReason`) is
  observed for the prompted session, a `state_update {state: "running"}` for that session must
  have been observed earlier in the same turn. Gated on the idle being seen at all -- SKIPs as
  "no turn-ending idle observed" only when the turn never reached one; an idle that *does* carry
  a `stopReason` but was never preceded by `running` FAILs (this is the defect the row exists to
  catch). Different SKIP gate from `ACP-STATE-202`/`203` below, whose gate is `running` itself
  not being observed (`.agents/research/acp-v2-prompt-lifecycle.md` requirement row
  `ACP-STATE-201`, inference §4 point 3).
- `ACP-STATE-202` (new): after an accepted prompt for a session that showed `running`, an idle
  `state_update` for that session arrives within the turn's `--timeout` budget. SKIPs as "no
  foreground work observed" when `running` was never observed at all -- the spec does not say
  whether a zero-work prompt must emit idle (open question, not guessed at).
- `ACP-STATE-203` (new): the idle `state_update` that terminates an observed `running` turn
  carries a `stopReason`, and the value is one of the five defined constants or `_`-prefixed
  (`tck.v2.protocol.is_valid_open_enum_value`). Folds in the prompt-lifecycle report's separate
  `ACP-STATE-204` value-legality row into one combined "terminating idle carries a *valid*
  `stopReason`" check; a future split into separate presence/legality ids is possible if a
  defect fixture ever needs the finer diagnostic. Same "no foreground work observed" SKIP gate
  as `ACP-STATE-202`.

Not registered: `ACP-PROMPT-202` (acceptance-before-idle ordering, race-prone) and
`ACP-PROMPT-204` (distinct `messageId`s across turns -- see `ACP-PATCH-203` instead, which
covers the same ground); `ACP-STATE-205` (state value legality alone, folded into
`ACP-STATE-203`); `ACP-STATE-206`/`207` (permission-driven state transitions; post-idle update
recording); `ACP-MSG-201` (fully covered by `ACP-PROMPT-205`'s schema validation).

## Prompt content, permissions, client-capability rules (`ACP-PROMPTCAP-00x`, `ACP-PERM-201`,
## `ACP-CLIENTCAP-20x`, informational prompt probes)

All rows below are only observable during a `session/prompt` turn, so all but `ACP-PROMPT-003`
and the two INFORMATIONAL rows are `Tier.CAPABILITY`, `capability="capabilities.session"`. The
ADVISORY/INFORMATIONAL rows keep `capability=None` on the `Requirement` itself
(`Requirement.__post_init__` forbids a capability path off `Tier.CAPABILITY`), but their tests
still carry the `@pytest.mark.capability("capabilities.session")` marker for the SKIP --
`tck.common.plugin._tck_capability_gate` reads only the pytest marker, independent of the
registered tier.

- `ACP-PROMPTCAP-001`/`002`/`003` (reused from v1): a prompt containing an
  `image`/`audio`/`resource` block alongside text is accepted and the turn reaches idle without
  a JSON-RPC error, re-cited to v2's content-block shapes. Gate encoding changes from v1's
  boolean `agentCapabilities.promptCapabilities.*` to v2's object-marker
  `capabilities.session.prompt.image`/`.audio`/`.embeddedContext` paths -- a gate-encoding
  change alone doesn't force a new id, only a changed text/tier does. Assertion target moves
  from v1's "valid `stopReason` in the response" to v2's acceptance receipt, which `run_prompt`'s
  own turn-end predicate only returns once the turn has reached idle.
- `ACP-PROMPT-003` (reused from v1, unchanged tier): a prompt of `text` + `resource_link` is
  accepted and the turn completes (ADVISORY). The v1/v2 doc conflict between
  initialization.mdx:203 ("MUST support `text` and `resource_link`") and content.mdx:33 ("MUST
  support text[-only]") survives verbatim into v2.
- `ACP-PERM-201` (new, no v1 counterpart): any `session/request_permission` the agent sends
  during a turn validates (`sessionId`, non-empty `title`, `options` with >=1 entry, each
  carrying `optionId`/`name`/`kind`), and once the client answers with a `selected` outcome the
  turn still reaches idle. SKIPs "no permission request observed" when the agent's turn never
  sends one -- sending it is only MAY (`prompt-lifecycle.mdx:369`), so there's nothing to
  validate for an agent that never asks.
- `ACP-CLIENTCAP-201` (new, no v1 counterpart): with a mock client advertising no
  `capabilities.elicitation.*` mode, no `elicitation/create` request is observed during a
  prompt turn (MUST NOT).
- `ACP-CLIENTCAP-202` (new): every agent->client request/notification method observed during a
  prompt turn is a member of v2's client method inventory (`CLIENT_METHODS`), a bidirectional
  protocol-level method (`PROTOCOL_METHODS`, e.g. `$/cancel_request`), or `_`-prefixed. Collapses
  v1's three separate `ACP-CLIENTCAP-001/002/003` fs/terminal/elicitation rows into one, since v2
  has no `fs/*`/`terminal/*` methods at all -- calling one is just calling an undefined method,
  indistinguishable from any other made-up non-`_` name. `elicitation/create`'s own
  capability-gated negative is `ACP-CLIENTCAP-201` above, not duplicated here (an unadvertised
  elicitation call is still a *defined* method, so it would otherwise trivially pass this check).
- `ACP-INFO-CONCURRENT-201` (new, INFORMATIONAL): records, never asserts on, what the agent does
  when a second `session/prompt` for the same session arrives before the first reaches its
  terminating idle -- concurrency is explicitly out of scope of the v2 design
  (`docs/rfds/v2/prompt.mdx:86`).
- `ACP-INFO-UNKNOWNSESSION-001` (reused from v1, INFORMATIONAL): records the agent's response to
  `session/prompt` with a never-created `sessionId`, never asserting on it -- v2's `error.mdx`
  is still "Documentation coming soon", same spec silence as v1.

Not added: `ACP-INFO-V2UNKNOWNUPDATE-001` (an unknown non-`_`-prefixed `sessionUpdate`
discriminator is a MANDATORY FAIL under `ACP-ENUM-20x` below, not merely an INFORMATIONAL
probe).

## Cancellation (`ACP-CANCEL-20x`, `ACP-INFO-CANCEL-20x`)

Source: `.agents/research/acp-v2-cancellation-and-batching.md`. `session/cancel` is
wire-identical to v1 (a notification, `{sessionId}` + optional `_meta`), but confirmation moved
from the (now purely an acceptance receipt) `session/prompt` response to a later idle
`state_update` carrying `stopReason: "cancelled"` -- every v1 `ACP-CANCEL-00x` id that named the
*response* is retired without reuse, and the whole family gets fresh `2xx` ids.

- `ACP-CANCEL-201..203`, `205..208` are `Tier.CAPABILITY`, `capability="capabilities.session"`
  (session-baseline rule) -- v1's closest analogues (`ACP-CANCEL-001`/`002`) were MANDATORY.
- `ACP-CANCEL-204` ("stop LLM requests / abort tool calls as soon as possible") is
  `Tier.INFORMATIONAL`, `capability=None` -- not because the wording is weaker (it is a real
  SHOULD), but because it is **unobservable** from a client-only TCK: nothing on the wire
  distinguishes "stopped as soon as possible" from "stopped eventually". Its test unconditionally
  records the observation and skips -- never asserts. The id itself keeps the `ACP-CANCEL-`
  prefix rather than moving to `ACP-INFO-` (renumbering it would contradict "never renumber" once
  assigned), but its *tier* is `Tier.INFORMATIONAL` rather than `Tier.ADVISORY`: a row that can
  never be judged -- always SKIPped, never PASS/FAIL -- belongs in the record-only tier, not the
  SHOULD tier.
- `ACP-CANCEL-208` (`session/close` on a session with foreground work MUST cancel it first) is
  the cancel-side-effect of `session/close`; `ACP-CLOSE-202` below is a deliberate re-mint of the
  exact same evidence via a second `@pytest.mark.requirement(...)` id on the same test, not a
  distinct probe (precedent: `ACP-CANCEL-201`/`207` similarly share one test).
- `ACP-INFO-CANCEL-201`/`202` are `Tier.INFORMATIONAL`, `capability=None` (unknown-`sessionId`/
  no-foreground-work behavior, and whether the agent sends its own `$/cancel_request` for
  pending requests -- both spec-silent or MAY-at-best).

## Transport/JSON-RPC (`ACP-TRANSPORT-002/201/203`, `ACP-JSONRPC-001..005`)

Connection-level, not session-scoped, so `Tier.MANDATORY`/`Tier.ADVISORY` directly, never
`Tier.CAPABILITY` -- these rows hold before any session exists.

- `ACP-TRANSPORT-201` (framing, new id): v1's `ACP-TRANSPORT-001` says "every line is a single
  JSON-RPC message"; v2 additionally permits a non-empty batch array on that line, a genuinely
  different rule needing a fresh id (`001` stays v1's).
- `ACP-TRANSPORT-002` (stdout is valid UTF-8, reused bare): byte-identical meaning to v1 --
  batching doesn't change what "valid UTF-8" means.
- `ACP-TRANSPORT-203` (no embedded newlines, including for a serialized batch array; new): v1
  had no id for this at all.
- `ACP-JSONRPC-001..005` (id echo, result-xor-error, notification silence, unknown-method code,
  connection survives an error) are each reused bare, unchanged in meaning from their v1
  counterparts -- only the evidence-gathering probe widens to also exercise a batch. The batch
  half of that widened evidence for `-001`/`-003`/`-005` is gathered in `test_batch.py`, not
  `test_jsonrpc.py`: the two files jointly bind each id via separate
  `@pytest.mark.requirement(...)` markers -- `test_jsonrpc.py`'s own probes stay single-message.
  `-002`/`-004` have no batch-specific angle (the disjoint-result/error shape and the
  unknown-method code do not change inside a batch entry), so their evidence stays entirely in
  `test_jsonrpc.py`.

## Batching (`ACP-BATCH-201..208`, `ACP-INFO-BATCH-201/202`)

- `ACP-BATCH-201`/`202` (empty-array -> single `-32600` object; notification-only batch -> no
  output) are `Tier.MANDATORY` -- real MUSTs, kept MANDATORY even knowing the Python SDK's
  reference agent crashes on any array line at all (an expected, already-documented cross-check
  baseline deviation, not a reason to weaken the tier). `ACP-BATCH-201`'s own text notes the
  RFC-2119 force it cites is on the *sender* side of `transports.mdx`'s prose; the *receiver*
  rule tested here is still MANDATORY because it is JSON-RPC 2.0 §6's own base envelope rule
  (see `ACP-BATCH-201`'s `text=` for the full rationale), unlike `203` below which is ACP's own
  unqualified prose and stays ADVISORY.
- `ACP-BATCH-203` (per-entry `-32600` for an invalid batch entry) is `Tier.ADVISORY` -- the
  report's own text carries no RFC-2119 keyword ("produces"), consistent with the v1
  `ACP-JSONRPC-005` precedent that unhedged-but-keyword-free ACP prose does not get MANDATORY.
  Its probe uses three non-object entries (`[17, true, null]`), never a batched unknown-method
  call: relying on `_tck/does_not_exist` getting an error reply would make this test depend on
  `ACP-JSONRPC-004`'s own SHOULD, not the per-entry rule.
- `ACP-BATCH-204` (one reply array, SHOULD) is `Tier.ADVISORY`. `ACP-BATCH-205` (order-
  independent, id-matched) is folded into the *same test* as `204` via a multi-id
  `@pytest.mark.requirement(...)` marker rather than a separate test function: both are evidenced
  by the exact same two-request-batch probe, and both are `Tier.ADVISORY` (never the sole cause
  of a failing verdict), so a single shared PASS/FAIL cannot misrepresent either id's own status
  the way it would for a MANDATORY/CAPABILITY pairing. The probe batches two `session/list`
  calls, never `session/new`: `session/new` is exactly the lifecycle-sensitive kind of call
  `ACP-BATCH-208` says SHOULD NOT be batched, so using it here would make `204`/`205`'s own
  evidence-gathering contradict `208`'s rule.
- `ACP-BATCH-206`/`207`/`208` (receiver MAY process concurrently; agent MAY spontaneously batch;
  clients/agents SHOULD NOT batch lifecycle messages) are `Tier.INFORMATIONAL`, `capability=None`,
  each with an always-skip, record-only test -- same unobservable-from-a-client-TCK reasoning as
  `ACP-CANCEL-204` above: `206` has no legitimate ordering assertion (the report says so
  directly), `207` cannot be forced (the TCK cannot make an agent choose to batch), and `208` is
  about what the *TCK itself* would do as a sender, not a property of the agent under test at
  all. Retiered from `Tier.ADVISORY`: a row that can never be judged -- always SKIPped, never
  PASS/FAIL -- belongs in the record-only tier, not the SHOULD tier.
- `ACP-INFO-BATCH-201`/`202` are `Tier.INFORMATIONAL`, `capability=None` (invalid-JSON-batch-line
  error code, and call/response batch-kind mixing) -- both SDK-disagreement/schema-only rows.

## Session management (`ACP-SESSION-203`, `ACP-RESUME-20x`, `ACP-LIST-20x`, `ACP-CLOSE-201/202`,
## `ACP-DELETE-20x`, `ACP-ADDDIRS-20x`, `ACP-MCP-201/202`, `ACP-CONFIG-20x`)

Source: `.agents/research/acp-v2-session-management.md`. `delete`/`additionalDirectories`/
`mcp.{stdio,http}` are each their own optional capability, gated on their own path.

- `ACP-SESSION-203` (new): `mcpServers` omitted vs. `mcpServers: []` on `session/new` are
  equivalent (the field is optional in v2, unlike v1's required-even-if-empty shape).
- `ACP-RESUME-201..205` re-mint v1's `ACP-LOAD-001/002`/`ACP-RESUME-001/002` (retired below): the
  capability gate changed from `agentCapabilities.sessionCapabilities.{resume,load}` to a
  baseline-mandatory method, and `session/resume` unifies v1's `session/load` + `session/resume`
  behind one `replayFrom` cursor. **Obtaining a legally resumable session id** has no
  spec-guaranteed route, so `_helpers.obtain_resumable_session` tries, in order: (1) resuming
  the session just created on this connection, (2) `session/list` then resuming its first entry,
  (3) `session/close` then resume -- recording each route's error. `-32601` from
  `session/resume` itself is a **FAIL** of `ACP-RESUME-201` (the method is baseline-mandatory);
  any other error from all three routes is a **SKIP** with the recorded errors (never a FAIL on
  `-32602`/`-32002`, which the spec doesn't authorize interpreting). `ACP-RESUME-206`
  (schema-covered `messageId` presence) is not registered -- a pure duplicate of validation the
  tests already run via `validate_agent_response`.
- `ACP-LIST-201..204` re-mint v1's `ACP-LIST-001/002` (list is now baseline, not
  `sessionCapabilities.list`). `ACP-LIST-205..208` (ADVISORY/INFORMATIONAL: `updatedAt` format,
  sessionId uniqueness, invalid-cursor handling, new/closed-session list visibility) are not
  registered -- no MANDATORY/CAPABILITY payoff to justify the fixture support they'd need.
- `ACP-CLOSE-201` re-mints v1's `ACP-CLOSE-001` (close is now baseline) and covers only
  `session/close`'s own contract (response shape) on a session with no foreground work.
  `ACP-CLOSE-202` is the cancellation side effect of `session/close` on in-flight foreground
  work, and is a deliberate documented duplicate of the evidence `ACP-CANCEL-208` already
  gathers -- both are satisfied by the same `run_prompt(..., on_action=<session/close>)` probe in
  `test_cancel.py`, marked `@pytest.mark.requirement("ACP-CANCEL-208", "ACP-CLOSE-202")`.
- `ACP-DELETE-201`/`202` re-mint v1's `ACP-DELETE-001`/half of `-002` ("no longer listed"), both
  `Tier.CAPABILITY`, `capability="capabilities.session.delete"`. `ACP-DELETE-203` is the
  ADVISORY, `capability=None` "silent double-delete" half, a verbatim re-cite of v1's
  `ACP-DELETE-002` -- its test still carries the capability marker purely for the SKIP gate.
- `ACP-ADDDIRS-201` re-mints v1's `ACP-ADDDIRS-001` (same requirement, new capability path).
  `ACP-ADDDIRS-202` is new: v1 had no `session/resume` carrier statement for
  `additionalDirectories` at all.
- `ACP-MCP-201`/`202`: `Tier.INFORMATIONAL`, not `Tier.CAPABILITY` -- a connect failure against a
  harmless stdio/http entry is the agent's own business ("Agents SHOULD connect" has no
  client-observable surface in stable v2), so FAILing `session/new` outright for it isn't
  provably non-conformant. This tiering is a judgment call (the source report's candidate table
  defaults to CAPABILITY; its prose twice recommends INFORMATIONAL instead -- taken here).
  `capability=None` per the `Tier.INFORMATIONAL` invariant; each test still carries
  `@pytest.mark.capability("capabilities.session.mcp.stdio"/"...http")` for the SKIP gate.
  `ACP-MCP-203` (custom/unknown transport type) is not registered.
- `ACP-CONFIG-201..204,206` mirror v1's `inferred:` pattern (`ACP-MODES-001`/`ACP-CONFIG-001/002`
  precedent): `Tier.CAPABILITY`, `capability="inferred:configOptions"` -- a documentation-only
  string satisfying `Requirement.__post_init__`'s invariant but not looked up by
  `@pytest.mark.capability(...)`; the tests instead `pytest.skip(...)` manually when
  `session/new`'s result carries no `configOptions`, since v2 has no `initialize`-result marker
  for this. `ACP-CONFIG-201`/`202` supersede v1's `ACP-CONFIG-001`/`002` (field renamed `id` ->
  `configId`; same requirement, new citation). `203`/`204`/`206` are new (resume carrier, the
  derived `currentValue` membership check, `config_option_update`'s completeness rule).
  `ACP-CONFIG-205` (ADVISORY: set-value reflection) is not registered -- the report itself flags
  it as optional ("an agent may legitimately reflect a dependent adjustment").

### v1 ids retired by this area (no v2 successor under the old id)

`ACP-LOAD-001/002/003`, `ACP-RESUME-001/002`, `ACP-LIST-001/002`, `ACP-CLOSE-002` (rewritten, not
re-cited -- v2's `PromptResponse` has no `stopReason` to resolve with), `ACP-MODES-001/002`,
`ACP-CONFIG-003` (v2 has no `clientCapabilities.session.configOptions.boolean` gate at all).

## Authentication (`ACP-AUTH-201..207`)

v2 renames v1's `authenticate`/`logout` to `auth/login`/`auth/logout` and drops v1's separate
`agentCapabilities.auth.logout` marker entirely: v2's `AgentAuthCapabilities` says outright
"This object does not advertise support for `auth/login` or `auth/logout`. Those methods are
advertised by a non-empty `authMethods` list in the `initialize` response". `AuthMethod` also
gains a schema-REQUIRED `type` discriminator (`terminal`/`agent`/open `other`) -- v1 let `type`
default to "agent" when absent; v2 does not.

- `ACP-AUTH-201` (ADVISORY, re-cites v1's `ACP-AUTH-001`): `authMethods[*].methodId` values are
  unique. Same requirement, only the field renamed (`id` -> `methodId`).
- `ACP-AUTH-202` (MANDATORY, new id): no `type: "terminal"` entry may be advertised unless the
  client advertised terminal-auth support. Same underlying MUST as v1's `ACP-AUTH-002`, but the
  gate's wire encoding changed from a top-level boolean (`clientCapabilities.auth.terminal`) to
  an object-marker path (`capabilities.auth.terminal`) -- a genuine shape change, hence a new id.
  Tested against a second, dedicated connection that advertises `capabilities.auth.terminal: {}`
  (the default connection's `authMethods` is the negative control; the dedicated connection also
  backs `ACP-AUTH-207` below).
- `ACP-AUTH-203` (CAPABILITY, `capability="inferred:authMethods"`, replaces v1's `ACP-AUTH-004`):
  `auth/logout` returns a non-error, schema-valid result. v2 has no logout capability marker at
  all, so support is inferred from a non-empty `authMethods`. Because calling `auth/logout` for
  real may revoke the operator's own credentials, this test additionally requires
  `--allow-logout` and SKIPs with `"auth/logout not exercised: pass --allow-logout (it may
  revoke the operator's credentials)"` otherwise.
- `ACP-AUTH-204` (CAPABILITY, `capability="inferred:authMethods"`, re-cites v1's `ACP-AUTH-003`):
  given `--auth-method <id>` naming a non-`terminal`, advertised `methodId`, `auth/login` does
  not answer `-32601` and a subsequent `session/new` does not fail with `-32000`. Same gating as
  v1's `ACP-AUTH-003`.
- `ACP-AUTH-205` (ADVISORY, re-cites v1's `ACP-AUTH-005`): `session/new` must not fail with
  `-32000` when `authMethods` is empty or absent.
- `ACP-AUTH-206` (MANDATORY, new -- v1's `type` had no closed/open enum rule): every
  `authMethods[*].type` is a defined discriminator value (`"agent"`, `"terminal"`) or
  `_`-prefixed (`tck.v2.protocol.is_valid_open_enum_value`).
- `ACP-AUTH-207` (MANDATORY, new -- v1's terminal descriptor had no `args`/`env` fields):
  conditional on at least one `type: "terminal"` entry appearing in `authMethods` on the
  connection that advertised `capabilities.auth.terminal: {}` (else SKIP). When one appears,
  every terminal descriptor's `args` (if present) is an array of strings, `env` (if present) is
  an array of well-formed `EnvVariable` objects, and `env` entries' `name`s are unique within
  that descriptor.

### v1 ids retired or replaced

`ACP-AUTH-004` is retired outright (replaced in spirit by `ACP-AUTH-203`'s `inferred:
authMethods` pattern, which additionally requires `--allow-logout`). `ACP-AUTH-001`/`003`/`005`
are re-cited under new ids (`ACP-AUTH-201`/`204`/`205`) rather than reusing the v1 number, same
convention as elsewhere in this file (a fresh `2xx` block per v2 area even for individually
unchanged requirements). `ACP-AUTH-002` is replaced by `ACP-AUTH-202` (new id) since the gate's
wire encoding changed, not just its citation.

## Patch/upsert semantics, open enums, extensibility/hygiene (`ACP-PATCH-20x`, `ACP-ENUM-20x`,
## `ACP-META-201`, `ACP-EXT-20x`, and v1 re-cites)

Source: `.agents/research/acp-v2-patches-enums-extensibility.md`. Rows the report itself scores
ADVISORY keep `Tier.ADVISORY, capability=None` on the registry (not promoted to CAPABILITY) --
the corresponding test function alone carries `@pytest.mark.capability("capabilities.session")`
to decide the SKIP.

### `ACP-PATCH-20x`: keyed upsert/patch semantics

- `ACP-PATCH-201` (CAPABILITY): every message-kind `session/update`
  (`*_message_chunk`/`*_message`/`*_thought_chunk`/`*_thought`) carries a non-empty `messageId`.
- `ACP-PATCH-202` is not registered -- duplicates `ACP-PROMPT-201` (acceptance receipt shape)
  combined with `ACP-PROMPT-203` (response echoes the same `messageId` the turn's updates used).
- `ACP-PATCH-203` (CAPABILITY): two separate prompts on the same session receive distinct
  `messageId` values.
- `ACP-PATCH-204` (CAPABILITY): every `tool_call_update` and `tool_call_content_chunk` carries a
  non-empty `toolCallId`; a content chunk additionally carries `content`. No separate tool-call
  "create" message exists in v2 -- an update for a previously-unseen `toolCallId` *is* the
  create.
- `ACP-PATCH-205` (CAPABILITY): every `plan_update.plan` carries a non-empty `planId`.
- `ACP-PATCH-206` (CAPABILITY): `terminal_update.cwd`, when present, is an absolute path, and a
  given `terminalId` is never observed with two different `cwd` values across the run (upsert-
  by-key implies `cwd` is set-once).
- `ACP-PATCH-207` (CAPABILITY): terminal output bytes (`terminal_output_chunk.data` and
  `terminal_update.output.data`) decode as standalone valid base64, independent of any other
  chunk.
- `ACP-PATCH-208` (ADVISORY, test capability-gated): the first observed `tool_call_update` for a
  given `toolCallId` carries a non-empty `title`, and `name` (if ever set) never changes across
  subsequent updates for that id.
- `ACP-PATCH-209` (ADVISORY, test capability-gated): when a `session/request_permission` is
  observed mid-turn, `"requires_action"` appears among the turn's `state_update.state` values
  before it, and `"running"` reappears after the permission request is answered.

### `ACP-ENUM-20x`: open-enum emitter rules

v2's schema leaves every scalar enum and tagged-union discriminator open except
`ElicitationSchemaType` and the JSON-RPC `jsonrpc` literal, but prose still binds the *emitter*:
every emitted value must be a defined constant or `_`-prefixed
(`tck.v2.protocol.is_valid_open_enum_value`).

- `ACP-ENUM-201` (CAPABILITY): a curated, non-exhaustive subset of sites carrying dedicated
  per-site MUST prose -- `tool_call_update.kind`/`.status` (`ToolKind`/`ToolCallStatus`) and plan
  entries' `priority`/`status` (`PlanEntryPriority`/`PlanEntryStatus`) -- are each a defined
  constant or `_`-prefixed. Classifying prose strength at every one of the schema's ~30 enum
  sites individually is out of scope; this subset is the highest-value one to automate.
- `ACP-ENUM-202` (ADVISORY, test capability-gated): three sites with no dedicated prose --
  `session/update`'s own `sessionUpdate` discriminator, `state_update.state`, and tool-call
  content blocks' `type` -- are each a defined constant or `_`-prefixed.
- `ACP-ENUM-203` (ADVISORY, test capability-gated): receiver-tolerance direction -- answering
  `session/request_permission` with a `_`-prefixed, non-standard `outcome` value must not make
  the agent answer the prompt itself with `-32602` or otherwise fail to reach a terminating idle.
  Only survival is checked; how the agent treats the value internally is untestable.

The re-worded v1 `ACP-PROMPT-001` ("the idle's `stopReason` is a defined constant or
`_`-prefixed") is not re-registered -- it duplicates `ACP-STATE-203`, which already combines
"carries a `stopReason`" with this value-legality check.

### Extensibility/hygiene: v1 ids re-cited unchanged

Same requirement in v2, only re-cited (the underlying `$def`s/docs are byte-identical or the
rule is version-agnostic): `ACP-EXT-001` (MANDATORY -- a `_`-prefixed custom method still gets
*some* response), `ACP-META-001` (ADVISORY -- `_meta` on `session/prompt` is still accepted),
`ACP-ERROR-001` (ADVISORY -- error `message` non-empty, single-line), `ACP-SHUTDOWN-001`
(ADVISORY -- prompt exit on stdin EOF), `ACP-SCHEMA-002` (ADVISORY -- no unknown root-level
keys; the v2 "other"-branch carve-out is implemented in
`tck.v2.validation.find_unknown_root_keys`), `ACP-STDERR-001`/`ACP-INFO-PARSE-001`/
`ACP-INFO-INVALIDREQ-001` (INFORMATIONAL -- report-only, never asserted). All connection-level,
`capability=None`, tiers unchanged from v1.

### New hygiene rows

- `ACP-META-201` (ADVISORY, new): every `_meta` value emitted anywhere in the transcript is a
  JSON object or `null` -- never a string/array/number.
- `ACP-EXT-201` (ADVISORY, new): an unrecognized `_`-prefixed notification produces no response
  and no crash (SHOULD-ignore).
- `ACP-EXT-202` (ADVISORY, new): vendor extensions are advertised under `initialize` result
  `capabilities._meta`, not as an unrecognized root key of `capabilities` itself.
- `ACP-EXT-203` (INFORMATIONAL, new): behaviour on receiving an unrecognized `$/`-prefixed
  protocol-level notification is recorded, never asserted (the spec explicitly permits ignoring
  it).

All four new hygiene rows are connection-level, `capability=None`.
"""

from __future__ import annotations

from ..common.requirements import Requirement, Tier, make_cite
from .protocol import SCHEMA_REVISION

SPEC_REVISION = SCHEMA_REVISION
_cite = make_cite(SPEC_REVISION)

_DECLARATIONS: tuple[Requirement, ...] = (
    Requirement(
        id="ACP-INIT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "`initialize` succeeds with a non-error JSON-RPC result. Judged the same "
            "regardless of the negotiated `protocolVersion` -- unlike `ACP-INIT-203`/"
            "`ACP-INIT-204`/`ACP-SCHEMA-001`, this row does not SKIP on a version mismatch, "
            "since a MUST-succeed handshake applies even to an agent that honestly negotiates "
            "down to a version other than 2. Schema/shape validation of the result -- "
            "including v2-only requirements -- lives in `ACP-SCHEMA-001`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:24,47; schema/v2/schema.json $defs/"
            "InitializeResponse"
        ),
    ),
    Requirement(
        id="ACP-INIT-201",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The result's `protocolVersion` is an integer, and the negotiated value is either "
            "the requested `2`, or -- if the agent does not support `2` -- the agent's own "
            "latest supported version (never something else, and never the literal request "
            "echoed back unconditionally)."
        ),
        citation=_cite("docs/protocol/v2/initialization.mdx:92-96"),
    ),
    Requirement(
        id="ACP-INIT-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "An unsupported-version probe (`protocolVersion: 65535`) still succeeds, and the "
            "returned `protocolVersion` is not the literal unsupported request echoed back -- "
            "it is at least the agent's own latest supported version (as observed from a "
            "reference `protocolVersion: 2` request on the same agent)."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:94 (second clause); "
            "acp-v2-version-negotiation.md requirement 10, case table row `N > M`"
        ),
    ),
    Requirement(
        id="ACP-INIT-202",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A downgrade probe (`protocolVersion: 1`) still succeeds -- never a JSON-RPC error "
            "-- and the returned `protocolVersion` is `1` or `2` (the agent's own latest "
            "supported version when it does not support `1`)."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:94,96; "
            "acp-v2-version-negotiation.md requirement 10, case table row `N < min(S)`"
        ),
    ),
    Requirement(
        id="ACP-INIT-203",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The `initialize` result's `info` is present and is an object with non-empty "
            "string `name` and `version` (`title` optional, may be `null`) -- REQUIRED in v2, "
            "unlike v1's optional `agentInfo`. A v2-only shape requirement: SKIPPED with a "
            "`VERSION-MISMATCH` note whenever the agent honestly negotiated down to a version "
            "other than 2, since it never claimed its result was v2-shaped."
        ),
        citation=_cite(
            "schema/v2/schema.json:3052-3058,3086,3097-3122; "
            "docs/protocol/v2/initialization.mdx:248"
        ),
    ),
    Requirement(
        id="ACP-INIT-204",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "When the `initialize` result's `capabilities` is present, it is an object, and "
            "every known capability marker within it (`session`, `auth`, and their known "
            "nested keys) is either absent/`null` or an object -- never a boolean. There are no "
            "boolean-encoded capabilities anywhere in v2. A v2-only shape requirement: SKIPPED "
            "with a `VERSION-MISMATCH` note whenever the agent honestly negotiated down to a "
            "version other than 2."
        ),
        citation=_cite(
            "docs/protocol/v2/migration.mdx:181; schema/v2/schema.json:3123-3158 "
            "(AgentCapabilities), :3159-3218 (SessionCapabilities) -- all `type: \"object\"`"
        ),
    ),
    Requirement(
        id="ACP-SCHEMA-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every message the agent emits during the `initialize` exchange validates against "
            "the vendored v2 schema. A v2-only shape requirement: SKIPPED with a "
            "`VERSION-MISMATCH` note whenever the agent honestly negotiated down to a version "
            "other than 2, since a v1-shaped result cannot be judged against the v2 schema."
        ),
        citation=_cite("schema/v2/schema.json (top-level anyOf); docs/protocol/v2/initialization.mdx"),
    ),
    Requirement(
        id="ACP-SESSION-001",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/new` with an absolute `cwd` and no `mcpServers` succeeds with a "
            "non-empty string `sessionId`, and the response validates against the v2 schema."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:69; schema/v2/schema.json:6011-6051 "
            "(required:[\"cwd\"]), :3627-3658 (required:[\"sessionId\"])"
        ),
    ),
    Requirement(
        id="ACP-SESSION-002",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text="Two `session/new` calls on one connection return distinct `sessionId`s.",
        citation=_cite("docs/protocol/v2/session-setup.mdx:69,306; schema/v2/schema.json:597"),
    ),
    Requirement(
        id="ACP-PROMPT-205",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every `session/update` notification the agent emits during a `session/prompt` "
            "turn validates against the v2 schema and carries the prompted `sessionId`. "
            "Vacuous pass if the agent emits no updates during the turn. NOT a reuse of v1's "
            "`ACP-PROMPT-002` under D3: the requirement text is the same schema/sessionId "
            "check, but the *tier* differs -- v1 registers it `Tier.MANDATORY` (v1's whole "
            "session surface is unconditional), whereas v2's `session/prompt` only exists once "
            "the agent has advertised the optional `capabilities.session` at all, exactly like "
            "`ACP-SESSION-001`/`002` above, so this row is `Tier.CAPABILITY`. A changed tier is "
            "a changed requirement under D3's reuse rule, so this gets a fresh 2xx id "
            "(`ACP-PROMPT-205`, not the already-reserved `ACP-PROMPT-202`/`204` -- see the "
            "research report's own id table) instead of reusing `ACP-PROMPT-002`."
        ),
        citation=_cite(
            "schema/v2/schema.json:4269 (UpdateSessionNotification, required "
            "[\"sessionId\",\"update\"]), :4300 (SessionUpdate union)"
        ),
    ),
    Requirement(
        id="ACP-PROMPT-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The `session/prompt` result is a non-error object carrying a non-empty string "
            "`messageId` -- the acceptance receipt sent at insertion time, not a turn result "
            "(there is no `stopReason` here at all in v2)."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:124-127; schema/v2/schema.json:4097 "
            "(PromptResponse, required [\"messageId\"]), :4120 (MessageId = string)"
        ),
    ),
    Requirement(
        id="ACP-PROMPT-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The agent reports the inserted user message via a `user_message` update or at "
            "least one `user_message_chunk` update, carrying the same `messageId` as the "
            "`session/prompt` response, for the prompted session -- before or after the "
            "response, no later than the turn-ending idle."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:129; docs/protocol/v2/migration.mdx:261; "
            "schema/v2/schema.json:4767 (UserMessage), :4738 (ContentChunk)"
        ),
    ),
    Requirement(
        id="ACP-STATE-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "If a turn-ending idle `state_update` (one carrying a `stopReason`) is observed "
            "for the prompted session, a `state_update {state: \"running\"}` for that session "
            "was observed earlier in the same turn. SKIPPED as 'no turn-ending idle observed' "
            "only when the turn never reached a stop-reason-bearing idle at all -- unlike "
            "`ACP-STATE-202`/`ACP-STATE-203`, this row's SKIP gate is the idle, not `running`; "
            "a turn-ending idle with no preceding `running` FAILs this row rather than "
            "SKIPping it."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:159,348 (inference); "
            "docs/protocol/v2/migration.mdx:278"
        ),
    ),
    Requirement(
        id="ACP-STATE-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "After an accepted prompt for a session that showed `state_update "
            "{state: \"running\"}`, an idle `state_update` for that session arrives within the "
            "turn's timeout budget. Asserted only when `running` was observed; SKIPPED as 'no "
            "foreground work observed' otherwise."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:348; docs/protocol/v2/migration.mdx:282"
        ),
    ),
    Requirement(
        id="ACP-STATE-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "The idle `state_update` that terminates an observed `running` turn carries a "
            "`stopReason`, and its value is one of the five defined constants (`end_turn`, "
            "`max_tokens`, `max_turn_requests`, `refusal`, `cancelled`) or begins with `_`. "
            "CAPABILITY (gated on `capabilities.session`), scoped to the idle that terminates "
            "an observed `running` turn -- an unscoped 'every idle has a stopReason' check is "
            "forbidden. SKIPPED as 'no foreground work observed' (same gate as "
            "`ACP-STATE-202`) when `running` was never observed."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:348,464-481; schema/v2/schema.json:4904 "
            "(IdleStateUpdate), :4869 (StopReason); docs/protocol/v2/extensibility.mdx:113-118"
        ),
    ),
    Requirement(
        id="ACP-PROMPTCAP-001",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.image",
        text=(
            "A prompt containing an `image` content block alongside text is accepted (a "
            "non-error `session/prompt` result), and the turn reaches idle, when the agent "
            "advertises `capabilities.session.prompt.image`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1194 (ImageContent)"
        ),
    ),
    Requirement(
        id="ACP-PROMPTCAP-002",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.audio",
        text=(
            "A prompt containing an `audio` content block alongside text is accepted (a "
            "non-error `session/prompt` result), and the turn reaches idle, when the agent "
            "advertises `capabilities.session.prompt.audio`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1238 (AudioContent)"
        ),
    ),
    Requirement(
        id="ACP-PROMPTCAP-003",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.prompt.embeddedContext",
        text=(
            "A prompt containing a `resource` (embedded context) content block alongside text "
            "is accepted (a non-error `session/prompt` result), and the turn reaches idle, "
            "when the agent advertises `capabilities.session.prompt.embeddedContext`."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:201-226; schema/v2/schema.json:3219 "
            "(prompt capability markers), :1504 (EmbeddedResource)"
        ),
    ),
    Requirement(
        id="ACP-PROMPT-003",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A prompt of `text` + `resource_link` content blocks is accepted, and the turn "
            "reaches idle -- ADVISORY, since `initialization.mdx:203` ('agents advertising "
            "`session` MUST support `text` and `resource_link`') conflicts with "
            "`content.mdx:33` ('all agents MUST support text content blocks', silent on "
            "`resource_link`); the conflict survives verbatim from v1 into v2."
        ),
        citation=_cite(
            "docs/protocol/v2/initialization.mdx:203; docs/protocol/v2/content.mdx:33; "
            "schema/v2/schema.json:1341 (ResourceLink), :6531 (PromptRequest.prompt)"
        ),
    ),
    Requirement(
        id="ACP-PERM-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Any `session/request_permission` request the agent sends during a turn "
            "validates: `sessionId`, a non-empty string `title`, and a non-empty `options` "
            "array, each option carrying `optionId`/`name`/`kind`. Once the client answers "
            "with a `selected` outcome, the turn still reaches an idle. Vacuous (SKIPPED) when "
            "no permission request was observed during the turn -- sending one is only MAY."
        ),
        citation=_cite(
            "schema/v2/schema.json:545 (RequestPermissionRequest, required "
            "[\"sessionId\",\"title\",\"options\"], options.minItems:1), :1999 "
            "(PermissionOption, required [\"optionId\",\"name\",\"kind\"]); "
            "docs/protocol/v2/tool-calls.mdx:194,233,253"
        ),
    ),
    Requirement(
        id="ACP-CLIENTCAP-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "With a mock client advertising no `capabilities.elicitation.*` mode, no "
            "`elicitation/create` request is observed during a prompt turn."
        ),
        citation=_cite(
            "docs/protocol/v2/elicitation.mdx:54,166; schema/v2/schema.json:5842 "
            "(x-method: elicitation/create)"
        ),
    ),
    Requirement(
        id="ACP-CLIENTCAP-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every agent->client request/notification method observed during a prompt turn "
            "is a member of `CLIENT_METHODS` or `PROTOCOL_METHODS` (e.g. `$/cancel_request`), "
            "or begins with `_`. `fs/*`/`terminal/*` do not exist as v2 methods at all, so "
            "calling either FAILs here as an undefined method (the v2 collapse of v1's "
            "separate `ACP-CLIENTCAP-001/002` rows)."
        ),
        citation=_cite(
            "schema/v2/meta.json:16-21 (agent->client method inventory); "
            "docs/protocol/v2/migration.mdx:53-54,628-637 (fs/terminal removed); "
            "docs/protocol/v2/extensibility.mdx:43,52 (MUST NOT call undefined methods)"
        ),
    ),
    Requirement(
        id="ACP-INFO-CONCURRENT-201",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) what the agent does when a second `session/prompt` for the "
            "same session is sent before the first has reached its terminating idle: accepted, "
            "a JSON-RPC error, or silence. Concurrency is explicitly out of scope of the v2 "
            "design."
        ),
        citation=_cite(
            "docs/rfds/v2/prompt.mdx:86 ('This RFD does not specify queueing, steering, or "
            "whether agents insert new prompts while busy')"
        ),
    ),
    Requirement(
        id="ACP-INFO-UNKNOWNSESSION-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) the agent's response to `session/prompt` with a "
            "`sessionId` it never created -- v2's `error.mdx` is still 'Documentation coming "
            "soon', so the error code (if any) is unspecified."
        ),
        citation=_cite("docs/protocol/v2/error.mdx"),
    ),
    Requirement(
        id="ACP-CANCEL-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "After `session/cancel` for a session with foreground work in flight, the agent "
            "sends a `session/update` whose `update` is `{\"sessionUpdate\": \"state_update\", "
            "\"state\": \"idle\", \"stopReason\": \"cancelled\"}`."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:519,526; docs/protocol/v2/migration.mdx:317; "
            "docs/protocol/v2/schema.mdx:234-240"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every `session/update` the agent sends for the cancelled foreground work precedes "
            "the terminating idle `state_update`. Tested in the weaker, client-observable form "
            "the report itself recommends (no per-update entity tracking): after the idle "
            "`cancelled` update, no further `state_update` for this session arrives within "
            "`quiet_period(...)` unless a new prompt was sent."
        ),
        citation=_cite("docs/protocol/v2/prompt-lifecycle.mdx:530; cf. :497"),
    ),
    Requirement(
        id="ACP-CANCEL-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Cancellation is never surfaced as a generic failure: after `session/cancel`, the "
            "turn does not end with a JSON-RPC error on the `session/prompt` request, nor with "
            "an idle `state_update` whose `stopReason` is a non-`cancelled` known value."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:521-528 (the <Warning> block, :526); "
            "schema/v2/schema.json:4869 (StopReason, cancelled branch description)"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-204",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "On receiving `session/cancel`, the agent SHOULD stop all language model requests "
            "and abort all in-progress tool call invocations as soon as possible. Unobservable "
            "from a client-only TCK (module docstring, 'Slice V2-3' section) -- the test "
            "records the observation and always SKIPs, never asserting on timing. INFORMATIONAL, "
            "not ADVISORY (review-v2-slices-1b-6 finding: a row that can never be judged, only "
            "ever SKIPped, belongs in the record-only tier, not the SHOULD tier)."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:517; docs/protocol/v2/schema.mdx:234-237"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-205",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/cancel` is a notification: the agent MUST NOT send any JSON-RPC response "
            "(result or error) for it."
        ),
        citation=_cite(
            "schema/v2/schema.json:6916 (CancelSessionNotification sits under "
            "AgentNotification), :6944-6966; docs/protocol/v2/overview.mdx:185; "
            "docs/protocol/v2/transports.mdx:66-67"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-206",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/cancel` params are exactly `{sessionId}` (required) plus optional `_meta`; "
            "the agent MUST accept a cancel that carries only `sessionId`, and MUST accept one "
            "that additionally carries `_meta`."
        ),
        citation=_cite(
            "schema/v2/schema.json:6944-6966; docs/protocol/v2/prompt-lifecycle.mdx:503-511"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-207",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "A custom stop reason MUST begin with `_`; an unknown non-`_` stop reason is "
            "reserved for future ACP and is non-conformant today. Applied to the cancellation "
            "assertion itself: the agent may not substitute e.g. `aborted` for `cancelled`."
        ),
        citation=_cite(
            "docs/protocol/v2/prompt-lifecycle.mdx:481; schema/v2/schema.json:4869 (other "
            "branch description)"
        ),
    ),
    Requirement(
        id="ACP-CANCEL-208",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/close` on a session with foreground work in flight MUST cancel that work "
            "as if `session/cancel` had been sent (same idle `cancelled` state_update), then "
            "free resources. Distinct from V2-4's future `CLOSE-201/202` -- see module "
            "docstring. Shares its test and citation with `ACP-CLOSE-202` (the same wire "
            "evidence, bound to both ids via a second `@pytest.mark.requirement(...)` marker) "
            "-- deliberately counted twice, once under each id."
        ),
        citation=_cite("docs/protocol/v2/session-setup.mdx:258"),
    ),
    Requirement(
        id="ACP-INFO-CANCEL-201",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) the agent's behaviour on `session/cancel` for an unknown "
            "`sessionId`, or for a session with no foreground work -- not specified."
        ),
        citation=_cite("docs/protocol/v2/prompt-lifecycle.mdx:499-536 (no normative text found)"),
    ),
    Requirement(
        id="ACP-INFO-CANCEL-202",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) whether the agent sends `$/cancel_request` for its own "
            "pending `session/request_permission`/`elicitation/create` requests when active "
            "work is cancelled -- not required, only illustrated (MAY at best)."
        ),
        citation=_cite(
            "docs/protocol/v2/cancellation.mdx:14,18,60-61 (non-normative diagram)"
        ),
    ),
    Requirement(
        id="ACP-TRANSPORT-201",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every line the agent writes to stdout parses as JSON and is either a single "
            "JSON-RPC 2.0 message object, or a non-empty array whose every element is a "
            "JSON-RPC 2.0 message object (an empty array on stdout is itself non-conformant)."
        ),
        citation=_cite(
            "docs/protocol/v2/transports.mdx:23-24,27; schema/v2/schema.json:82-424 "
            "(AgentBatchCall/AgentBatchResponse, minItems: 1)"
        ),
    ),
    Requirement(
        id="ACP-TRANSPORT-002",
        tier=Tier.MANDATORY,
        capability=None,
        text="The agent's stdout is valid UTF-8.",
        citation=_cite("docs/protocol/v2/transports.mdx:6"),
    ),
    Requirement(
        id="ACP-TRANSPORT-203",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Messages are newline-delimited and MUST NOT contain embedded newlines -- a batch "
            "array is therefore serialised on one line too."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:25"),
    ),
    Requirement(
        id="ACP-JSONRPC-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A response's `id` echoes the request `id` exactly (integer and string ids), "
            "including for responses delivered inside a batch response array."
        ),
        citation=_cite(
            "docs/protocol/v2/transports.mdx:68-69; schema/v2/schema.json:125-288 "
            "(AgentBatchResponse.items -> Result/Error, both required id); "
            "docs/protocol/v2/overview.mdx:189 (JSON-RPC envelope fields, including `id`, "
            "follow the base JSON-RPC 2.0 spec, where id-echo is itself normative)"
        ),
    ),
    Requirement(
        id="ACP-JSONRPC-002",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A response carries exactly one of `result`/`error`; an error object has an "
            "integer `code` and a string `message`."
        ),
        citation=_cite(
            "docs/protocol/v2/overview.mdx:183-184; schema/v2/schema.json:125-288 (disjoint "
            "Result/Error branches)"
        ),
    ),
    Requirement(
        id="ACP-JSONRPC-003",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Notifications never receive a response, success or error -- including a "
            "notification inside a batch."
        ),
        citation=_cite(
            "docs/protocol/v2/overview.mdx:185; docs/protocol/v2/transports.mdx:64-67"
        ),
    ),
    Requirement(
        id="ACP-JSONRPC-004",
        tier=Tier.ADVISORY,
        capability=None,
        text="An unknown method yields `-32601`. Spec wording is still 'should'.",
        citation=_cite("docs/protocol/v2/extensibility.mdx:80-91"),
    ),
    Requirement(
        id="ACP-JSONRPC-005",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "After an erroneous request -- including an invalid or empty batch -- the "
            "connection remains usable."
        ),
        citation=_cite(
            "docs/protocol/v2/overview.mdx:179-185; docs/protocol/v2/extensibility.mdx:80-91"
        ),
    ),
    Requirement(
        id="ACP-BATCH-201",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "An empty array (`[]`) receives a single Invalid Request (`-32600`) response "
            "object with `id: null` -- never a response array. The RFC-2119 force of "
            "`transports.mdx`'s own prose is on the *sender* ('a Batch rpc call SHOULD be "
            "an Array containing at least one item') -- the *receiver* rule tested here is "
            "still treated as MUST because it is JSON-RPC 2.0 §6's own base envelope rule "
            "(adopted wholesale by `overview.mdx`'s 'ACP messages follow JSON-RPC 2.0'), not "
            "a new SHOULD ACP invented -- unlike `ACP-BATCH-203`'s per-entry rule below, which "
            "*is* ACP's own unqualified prose and stays ADVISORY."
        ),
        citation=_cite(
            "docs/protocol/v2/transports.mdx:57-59; schema/v2/schema.json:82,125,289,332 "
            "(minItems: 1 on all four batch envelopes)"
        ),
    ),
    Requirement(
        id="ACP-BATCH-202",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "The agent MUST NOT reply to a notification, including one inside a batch. A "
            "notification-only batch produces no output at all -- never an empty array."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:66-67,70-72"),
    ),
    Requirement(
        id="ACP-BATCH-203",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A non-empty batch containing invalid entries produces a per-entry `-32600` with "
            "`id: null`; the batch does not fail wholesale and valid siblings still run. "
            "Phrased without an RFC-2119 keyword in ACP's own text -- ADVISORY, per the v1 "
            "ACP-JSONRPC-005 precedent."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:73-75"),
    ),
    Requirement(
        id="ACP-BATCH-204",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "The agent SHOULD reply to a batch containing at least one request with one array "
            "of the corresponding response objects, emitted after all batch requests have been "
            "processed."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:62-65"),
    ),
    Requirement(
        id="ACP-BATCH-205",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Responses MAY appear in any order in the array; the sender SHOULD match them to "
            "requests by `id`, never by position."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:68-69"),
    ),
    Requirement(
        id="ACP-BATCH-206",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "The receiver MAY process batch entries concurrently, in any order, with any "
            "parallelism. No ordering assertion is legitimate -- record-only, always SKIPped. "
            "INFORMATIONAL, not ADVISORY (review-v2-slices-1b-6: a row that can never be judged "
            "belongs in the record-only tier)."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:60-61"),
    ),
    Requirement(
        id="ACP-BATCH-207",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "A client or agent MAY send a batch; an agent MAY therefore spontaneously emit a "
            "batch of `session/update` notifications. Cannot be forced by a client-only TCK -- "
            "record-only, always SKIPped. INFORMATIONAL, not ADVISORY (review-v2-slices-1b-6: a "
            "row that can never be judged belongs in the record-only tier)."
        ),
        citation=_cite(
            "docs/protocol/v2/transports.mdx:47-51; schema/v2/schema.json:289-331 "
            "(ClientBatchCall.items)"
        ),
    ),
    Requirement(
        id="ACP-BATCH-208",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Clients and agents SHOULD NOT batch lifecycle-sensitive messages (`initialize`, "
            "`auth/login`, `session/new`, `session/resume`, `session/prompt`). A property of "
            "the sender, not the agent under test as a receiver -- record-only, always SKIPped. "
            "INFORMATIONAL, not ADVISORY (review-v2-slices-1b-6: a row that can never be judged "
            "belongs in the record-only tier)."
        ),
        citation=_cite(
            "docs/protocol/v2/transports.mdx:77-80; docs/protocol/v2/migration.mdx:722"
        ),
    ),
    Requirement(
        id="ACP-INFO-BATCH-201",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) the agent's response to an invalid-JSON batch line -- spec "
            "says a single Parse error (`-32700`) with `id: null`, but SDKs disagree (same "
            "unasserted behaviour as v1's ACP-INFO-PARSE-001)."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:55-56"),
    ),
    Requirement(
        id="ACP-INFO-BATCH-202",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Record (never assert) the agent's response to a call batch containing a "
            "response-shaped entry (or vice versa) -- the schema forbids mixing kinds, but no "
            "prose states this and JSON-RPC 2.0 itself does not either."
        ),
        citation=_cite("schema/v2/schema.json:82-124 vs :125-288"),
    ),
    Requirement(
        id="ACP-SESSION-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/new` is accepted whether `mcpServers` is omitted entirely or sent as `[]` "
            "-- the two forms are equivalent in v2 (unlike v1, where the field was required-"
            "even-if-empty)."
        ),
        citation=_cite(
            "docs/protocol/v2/migration.mdx:598; schema/v2/schema.json:6032-6040,6048"
        ),
    ),
    Requirement(
        id="ACP-RESUME-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/resume` (no `replayFrom`) of a session obtained via the harness's "
            "three-route strategy succeeds with a schema-valid object result. `-32601` FAILs "
            "(B3 makes `session/resume` a baseline-mandatory method); any other error from all "
            "three routes SKIPs -- no route is spec-guaranteed to work."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:83-84; "
            "schema/v2/schema.json:6274-6334,4036-4058"
        ),
    ),
    Requirement(
        id="ACP-RESUME-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "With `replayFrom: {\"type\": \"start\"}`, every `session/update` for the resumed "
            "session arrives before the `session/resume` response, and none arrives within a "
            "quiet period after it. Zero replayed updates is conforming (R5's retention escape "
            "hatch) and is recorded, never FAILed."
        ),
        citation=_cite("docs/protocol/v2/session-setup.mdx:144-145,221-222"),
    ),
    Requirement(
        id="ACP-RESUME-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "With `replayFrom` omitted (or `null`), no conversation-history `session/update` for "
            "the resumed session arrives before the response. Vacuous -- and recorded, never "
            "FAILed on that account -- for an agent that retains no history to replay."
        ),
        citation=_cite("docs/protocol/v2/session-setup.mdx:118-119"),
    ),
    Requirement(
        id="ACP-RESUME-204",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "A retained user message inserted by `session/prompt` replays, if it replays at all, "
            "with the same `messageId` that prompt's response returned. A narrow, conditional "
            "trigger: absence of the message from replay is conforming (R5) and SKIPs this "
            "check rather than FAILing it."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:199-201; docs/protocol/v2/prompt-lifecycle."
            "mdx:153; schema/v2/schema.json:4102"
        ),
    ),
    Requirement(
        id="ACP-RESUME-205",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "During replay, a `*_chunk` update for a `messageId` is preceded, within the same "
            "replay window, by the matching whole-message update (`content: []`) for that id. "
            "Vacuous -- recorded, never FAILed -- for an agent whose replay uses only whole-"
            "message updates."
        ),
        citation=_cite("docs/protocol/v2/session-setup.mdx:208-212"),
    ),
    Requirement(
        id="ACP-LIST-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/list` with `params: {}` succeeds; the result's `sessions` field is "
            "present as an array, and the response validates against the v2 schema."
        ),
        citation=_cite(
            "docs/protocol/v2/session-list.mdx:10,73,108; schema/v2/schema.json:3933-3968"
        ),
    ),
    Requirement(
        id="ACP-LIST-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/list` filtered by a `cwd` no session plausibly uses returns "
            "`sessions: []` -- never `null`, never an error."
        ),
        citation=_cite("docs/protocol/v2/session-list.mdx:145"),
    ),
    Requirement(
        id="ACP-LIST-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "When `session/list` is filtered by a real `cwd`, every returned `SessionInfo.cwd` "
            "equals the requested `cwd` (a per-entry check only; the reverse direction -- that a "
            "session at that `cwd` is returned at all -- is not asserted, since no upstream "
            "statement guarantees a freshly created session appears in `session/list`)."
        ),
        citation=_cite("docs/protocol/v2/session-list.mdx:63-66"),
    ),
    Requirement(
        id="ACP-LIST-204",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text="Every returned `SessionInfo.cwd` is an absolute path.",
        citation=_cite(
            "docs/protocol/v2/session-list.mdx:115-117; docs/protocol/v2/overview.mdx:176"
        ),
    ),
    Requirement(
        id="ACP-CLOSE-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/close` of a live, idle session succeeds with a schema-valid empty-object "
            "result -- `session/close`'s own baseline contract, distinct from the cancellation "
            "side effect `ACP-CLOSE-202`/`ACP-CANCEL-208` covers (see the module docstring)."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:237-239,258-268; schema/v2/schema.json:"
            "6401-6423,4059-4072"
        ),
    ),
    Requirement(
        id="ACP-CLOSE-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`session/close` on a session with foreground work in flight cancels that work as "
            "if `session/cancel` had been sent -- the same idle `state_update` with "
            "`stopReason: \"cancelled\"` evidence `ACP-CANCEL-208` already checks, deliberately "
            "reused verbatim (see the module docstring's id-namespacing decision) rather than "
            "gathered by a second, near-identical probe. `Requirement.capability` and the id are "
            "registered separately from `ACP-CANCEL-208` purely for V2-4's own report legibility."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:258; docs/protocol/v2/prompt-lifecycle.mdx:"
            "519,526"
        ),
    ),
    Requirement(
        id="ACP-DELETE-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.delete",
        text="`session/delete` of an existing session succeeds with an empty-object result.",
        citation=_cite("docs/protocol/v2/session-delete.mdx:35,57,74-86"),
    ),
    Requirement(
        id="ACP-DELETE-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.delete",
        text=(
            "After a successful `session/delete`, the session no longer appears in "
            "`session/list` results. SKIPs when the session was never observed in "
            "`session/list` in the first place (nothing to compare against)."
        ),
        citation=_cite("docs/protocol/v2/session-delete.mdx:90"),
    ),
    Requirement(
        id="ACP-DELETE-203",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Deleting an already-deleted or never-created `sessionId` SHOULD succeed silently, "
            "rather than erroring -- verbatim re-cite of v1's `ACP-DELETE-002`, new capability "
            "path."
        ),
        citation=_cite("docs/protocol/v2/session-delete.mdx:91"),
    ),
    Requirement(
        id="ACP-ADDDIRS-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.additionalDirectories",
        text="`session/new` with an absolute `additionalDirectories` entry is accepted.",
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:274-302; schema/v2/schema.json:6023-6031"
        ),
    ),
    Requirement(
        id="ACP-ADDDIRS-202",
        tier=Tier.CAPABILITY,
        capability="capabilities.session.additionalDirectories",
        text=(
            "`session/resume` with an absolute `additionalDirectories` entry (matching the "
            "session's own `cwd`) is accepted -- a new carrier statement in v2; v1 had no "
            "`session/resume`/`session/load` analogue to this rule at all."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:276-277,300; schema/v2/schema.json:6294-6302"
        ),
    ),
    Requirement(
        id="ACP-MCP-201",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "INFORMATIONAL, not CAPABILITY, despite the underlying `capabilities.session.mcp."
            "stdio` marker (per the source report's own explicit recommendation, flagged to the "
            "orchestrator -- see the module docstring): records whether `session/new` accepts a "
            "well-formed stdio MCP server entry when the marker is advertised. A connect failure "
            "against a harmless, possibly-nonexistent command is the agent's own business "
            "(M6 is only a SHOULD, with no client-observable surface in stable v2) and is not "
            "provably non-conformant, so this never asserts on the outcome."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:336-386,440,465; schema/v2/schema.json:"
            "6176-6214"
        ),
    ),
    Requirement(
        id="ACP-MCP-202",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "INFORMATIONAL, not CAPABILITY, same reasoning as `ACP-MCP-201`: records whether "
            "`session/new` accepts a well-formed http MCP server entry when `capabilities."
            "session.mcp.http` is advertised. Never asserts on the outcome."
        ),
        citation=_cite("docs/protocol/v2/session-setup.mdx:388-436; schema/v2/schema.json:6147-6175"),
    ),
    Requirement(
        id="ACP-CONFIG-201",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "Every `configOptions` entry in `session/new`'s result validates: `configId` and "
            "`name` are present, `type` selects the right shape (`select` requires `currentValue`"
            "+`options`; `boolean` requires `currentValue`), and a `select` entry's `options` is "
            "either a flat `SessionConfigSelectOption[]` or a grouped "
            "`SessionConfigSelectGroup[]`, never mixed. Inferred support, same encoding as v1's "
            "`ACP-MODES-001`/`ACP-CONFIG-001` -- `capability=\"inferred:configOptions\"` is "
            "documentation-only."
        ),
        citation=_cite(
            "schema/v2/schema.json:3659-3932; docs/protocol/v2/session-config-options.mdx:"
            "76-129"
        ),
    ),
    Requirement(
        id="ACP-CONFIG-202",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "`session/set_config_option` responds with the *complete* `configOptions` list -- "
            "every previously-advertised `configId` is present in the response (a superset "
            "check: the dependent-changes note permits the response to also add options or "
            "change other values). Gate is genuinely unstated upstream (C12): SKIP on `-32601` "
            "when no `configOptions` were ever advertised, rather than FAIL."
        ),
        citation=_cite(
            "docs/protocol/v2/session-config-options.mdx:262,307-312; schema/v2/schema.json:"
            "4073-4096"
        ),
    ),
    Requirement(
        id="ACP-CONFIG-203",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "`session/resume`'s `configOptions`, when present, validates the same way as "
            "`ACP-CONFIG-201` -- a new carrier in v2 (v1's `session/load` had no analogous "
            "field)."
        ),
        citation=_cite(
            "docs/protocol/v2/session-setup.mdx:232-233; schema/v2/schema.json:4040-4049"
        ),
    ),
    Requirement(
        id="ACP-CONFIG-204",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "A `select`-type option's `currentValue` is one of its declared `options` values "
            "(flat or grouped) -- derived from C5's always-a-default-value MUST plus the field "
            "descriptions, not itself schema-enforced."
        ),
        citation=_cite(
            "docs/protocol/v2/session-config-options.mdx:99-108,197; schema/v2/schema.json:"
            "3899-3921"
        ),
    ),
    Requirement(
        id="ACP-CONFIG-206",
        tier=Tier.CAPABILITY,
        capability="inferred:configOptions",
        text=(
            "An observed `config_option_update` `session/update` carries the *complete* "
            "configuration state -- its `configId` set is a superset of the last known set. "
            "Conditional and vacuous (recorded, never FAILed) when no such update is ever "
            "observed during a run."
        ),
        citation=_cite(
            "docs/protocol/v2/session-config-options.mdx:314-365; schema/v2/schema.json:"
            "5538-5559"
        ),
    ),
    Requirement(
        id="ACP-AUTH-201",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "`authMethods[*].methodId` values are unique. Re-cites v1's `ACP-AUTH-001`; only "
            "the field name changed (`id` -> `methodId`)."
        ),
        citation=_cite("schema/v2/schema.json:3399-3495 ($defs/AuthMethod, AuthMethodId)"),
    ),
    Requirement(
        id="ACP-AUTH-202",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "No `authMethods[*]` entry with `type: \"terminal\"` is advertised unless the "
            "client advertised `capabilities.auth.terminal: {}` in `initialize`'s params. New "
            "id, not a reuse of v1's `ACP-AUTH-002` -- the client-capability path and its "
            "encoding both changed (v1: top-level boolean `clientCapabilities.auth.terminal`; "
            "v2: nested object marker `capabilities.auth.terminal`)."
        ),
        citation=_cite(
            "schema/v2/schema.json:3522 ($defs/AuthMethodTerminal); schema/v2/schema.json "
            "($defs/AuthCapabilities, $defs/TerminalAuthCapabilities)"
        ),
    ),
    Requirement(
        id="ACP-AUTH-203",
        tier=Tier.CAPABILITY,
        capability="inferred:authMethods",
        text=(
            "`auth/logout` returns a non-error, schema-valid result. Support is inferred from "
            "a non-empty `authMethods` -- v2 has no `agentCapabilities.auth.logout` marker at "
            "all (unlike v1); `capability=\"inferred:authMethods\"` is documentation-only. "
            "Replaces v1's `ACP-AUTH-004` outright. Only actually exercised when "
            "`--allow-logout`/`--tck-allow-logout` is given (destructive: may revoke the "
            "operator's own credentials); SKIPs otherwise."
        ),
        citation=_cite(
            "schema/v2/schema.json:5997-6010 ($defs/LogoutAuthRequest); schema/v2/schema.json "
            "3613-3626 ($defs/LogoutAuthResponse); schema/v2/schema.json ($defs/"
            "AgentAuthCapabilities)"
        ),
    ),
    Requirement(
        id="ACP-AUTH-204",
        tier=Tier.CAPABILITY,
        capability="inferred:authMethods",
        text=(
            "Given `--auth-method <id>` naming a non-`terminal`, advertised `methodId`, "
            "`auth/login` does not answer `-32601` (Method not found), and a subsequent "
            "`session/new` does not fail with `-32000`. Mirrors v1's `ACP-AUTH-003` exactly, "
            "method renamed `authenticate` -> `auth/login`. SKIPs when `--auth-method` was not "
            "given, or the agent advertises no `authMethods`."
        ),
        citation=_cite(
            "schema/v2/schema.json:5974-5996 ($defs/LoginAuthRequest, required: [\"methodId\"]); "
            "schema/v2/schema.json:3599-3612 ($defs/LoginAuthResponse)"
        ),
    ),
    Requirement(
        id="ACP-AUTH-205",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "`session/new` does not fail with `-32000` (AUTHENTICATION_REQUIRED) when "
            "`authMethods` is empty or absent. Re-cites v1's `ACP-AUTH-005`/AUTH-A1; not "
            "promoted."
        ),
        citation=_cite("docs/protocol/v2/schema.mdx:428 (-32000 is a MAY, not a MUST)"),
    ),
    Requirement(
        id="ACP-AUTH-206",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "Every `authMethods[*].type` is one of the schema's defined discriminator values "
            "(`\"agent\"`, `\"terminal\"`) or begins with `_` -- the general open-enum "
            "extensibility rule applied to this field. New in v2: v1's `type` could default to "
            "\"agent\" when absent and had no enum-closure rule at all."
        ),
        citation=_cite(
            "docs/protocol/v2/authentication.mdx:120-122; docs/protocol/v2/extensibility.mdx:"
            "111-121; schema/v2/schema.json:3399-3495 ($defs/AuthMethod)"
        ),
    ),
    Requirement(
        id="ACP-AUTH-207",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "On a connection that advertised `capabilities.auth.terminal: {}`, every "
            "`type: \"terminal\"` entry's `args` (if present) is an array of strings, `env` "
            "(if present) is an array of well-formed `EnvVariable` objects (`name`/`value` "
            "both required strings), and `env` entries' `name`s are unique within that "
            "descriptor. Conditional on at least one terminal entry actually appearing; SKIPs "
            "otherwise. New in v2 -- v1's terminal auth descriptor had no `args`/`env` fields."
        ),
        citation=_cite(
            "schema/v2/schema.json:3522-3552 ($defs/AuthMethodTerminal, \"Names MUST be "
            "unique\"); schema/v2/schema.json ($defs/EnvVariable)"
        ),
    ),
    Requirement(
        id="ACP-PATCH-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every agent-emitted message update/chunk "
            "(`user_message_chunk`/`user_message`/`agent_message_chunk`/`agent_message`/"
            "`agent_thought_chunk`/`agent_thought`) carries a non-empty string `messageId`. "
            "Promoted from the report's MANDATORY per the session-baseline tiering rule."
        ),
        citation=_cite("docs/protocol/v2/prompt-lifecycle.mdx:246; schema/v2/schema.json:4738-4856"),
    ),
    Requirement(
        id="ACP-PATCH-203",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Two `session/prompt`s on the same session receive two distinct `messageId` "
            "values -- the v2 analogue of v1's `duplicate_session_id.py` defect pattern, "
            "applied to message ids instead of session ids. Promoted from the report's "
            "MANDATORY."
        ),
        citation=_cite("docs/protocol/v2/prompt-lifecycle.mdx:151"),
    ),
    Requirement(
        id="ACP-PATCH-204",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every `tool_call_update` carries a non-empty `toolCallId`; every "
            "`tool_call_content_chunk` carries a non-empty `toolCallId` and `content`. There "
            "is no separate tool-call \"create\" message in v2 -- an update for a "
            "previously-unseen `toolCallId` is itself the create, so no create-before-update "
            "ordering is asserted. Promoted from the report's MANDATORY(obs); conditional on "
            "at least one such update being observed during the run, else SKIP."
        ),
        citation=_cite("schema/v2/schema.json:674-758,5040-5110"),
    ),
    Requirement(
        id="ACP-PATCH-205",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every `plan_update.plan` -- including an unknown/`_`-prefixed `type` variant -- "
            "carries a non-empty `planId`. Promoted from the report's MANDATORY(obs); "
            "conditional on at least one `plan_update` being observed, else SKIP."
        ),
        citation=_cite("docs/protocol/v2/agent-plan.mdx:71; schema/v2/schema.json:5199-5278"),
    ),
    Requirement(
        id="ACP-PATCH-206",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "A supplied `terminal_update.cwd`, when present, is an absolute path; a given "
            "`terminalId` is never observed with two different `cwd` values within a session "
            "(upsert-by-key implies `cwd` is set-once). Promoted from the report's "
            "MANDATORY(obs); conditional on at least one `terminal_update` being observed, "
            "else SKIP."
        ),
        citation=_cite("docs/protocol/v2/tool-calls.mdx:405-411,439-440"),
    ),
    Requirement(
        id="ACP-PATCH-207",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "`terminal_output_chunk.data` and `terminal_update.output.data` each decode as "
            "standalone, valid RFC 4648 base64 -- independent of any other chunk. Promoted "
            "from the report's MANDATORY(obs); conditional on at least one such field being "
            "observed, else SKIP."
        ),
        citation=_cite("docs/protocol/v2/tool-calls.mdx:441-446,466-474"),
    ),
    Requirement(
        id="ACP-PATCH-208",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "The first `tool_call_update` observed for a given `toolCallId` includes a "
            "non-empty `title`; `name`, if ever set, does not change across subsequent "
            "updates for the same id. ADVISORY per the report; not promoted -- the "
            "corresponding test is still `@pytest.mark.capability(\"capabilities.session\")`-"
            "gated for its own SKIP."
        ),
        citation=_cite("docs/protocol/v2/tool-calls.mdx:44-52"),
    ),
    Requirement(
        id="ACP-PATCH-209",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "While blocked on a `session/request_permission` response, the agent reports "
            "`state_update.state == \"requires_action\"`, and reports `\"running\"` again "
            "once it resumes. ADVISORY per the report; not promoted -- the corresponding test "
            "is still `@pytest.mark.capability(\"capabilities.session\")`-gated for its own "
            "SKIP."
        ),
        citation=_cite("docs/protocol/v2/prompt-lifecycle.mdx:371"),
    ),
    Requirement(
        id="ACP-ENUM-201",
        tier=Tier.CAPABILITY,
        capability="capabilities.session",
        text=(
            "Every value the agent emits at an open-enum site carrying dedicated per-site "
            "MUST prose -- `tool_call_update.kind`/`.status` (`ToolKind`/`ToolCallStatus`) and "
            "plan entries' `priority`/`status` (`PlanEntryPriority`/`PlanEntryStatus`) -- is a "
            "defined constant or begins with `_`. A curated, non-exhaustive subset of the "
            "report's full B.1/B.2 inventory (classifying every one of the 30 sites "
            "individually is disproportionate for this slice). Promoted from the report's "
            "MANDATORY."
        ),
        citation=_cite(
            "docs/protocol/v2/extensibility.mdx:111-118; "
            "docs/protocol/v2/tool-calls.mdx:75,373; docs/protocol/v2/agent-plan.mdx:88,100"
        ),
    ),
    Requirement(
        id="ACP-ENUM-202",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Same defined-or-`_`-prefixed rule applied at open-enum sites the prose does not "
            "individually restate: `session/update`'s own `sessionUpdate` discriminator, "
            "`state_update.state`, and tool-call content blocks' `type`. ADVISORY per the "
            "report; not promoted -- the corresponding test is still "
            "`@pytest.mark.capability(\"capabilities.session\")`-gated for its own SKIP."
        ),
        citation=_cite(
            "docs/protocol/v2/extensibility.mdx:117,120; schema/v2/schema.json:4560-4575"
        ),
    ),
    Requirement(
        id="ACP-ENUM-203",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A `_`-prefixed value at an open-enum site the client sends (here: "
            "`session/request_permission`'s answered `outcome`) is tolerated by the agent -- "
            "no crash, and the prompt itself is not answered with `-32602`. Untestable how the "
            "agent treats the value internally; only survival is checked. ADVISORY per the "
            "report; not promoted -- the corresponding test is still "
            "`@pytest.mark.capability(\"capabilities.session\")`-gated for its own SKIP."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:115,122"),
    ),
    Requirement(
        id="ACP-EXT-001",
        tier=Tier.MANDATORY,
        capability=None,
        text=(
            "A `_`-prefixed custom method request receives *some* response -- a result, or "
            "an error with any code. Re-cited from v1 unchanged (D3): same requirement, only "
            "the citation moves to v2's extensibility docs. The `-32601` code specifically "
            "remains `ACP-JSONRPC-004`'s separate ADVISORY concern."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:43,52,65,109"),
    ),
    Requirement(
        id="ACP-META-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A `session/prompt` request carrying a `_meta` object is accepted -- the turn "
            "still proceeds normally. Re-cited from v1 unchanged (D3): `PromptRequest._meta` "
            "still exists in v2."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:10,33-37,39"),
    ),
    Requirement(
        id="ACP-META-201",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Every `_meta` value the agent emits, anywhere in the transcript, is a JSON "
            "object or `null` -- never a string/array/number. New in v2; all 106 `_meta` "
            "sites in the schema are typed `[\"object\", \"null\"]`."
        ),
        citation=_cite("schema/v2/schema.json:4289-4295"),
    ),
    Requirement(
        id="ACP-EXT-201",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "An unrecognized `_`-prefixed *notification* sent to the agent produces no "
            "response line and no crash (SHOULD-ignore) -- the v2 analogue of v1's "
            "`answers_notifications.py` defect pattern, generalised from `session/cancel` "
            "specifically to any custom notification."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:109"),
    ),
    Requirement(
        id="ACP-EXT-202",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "Vendor extensions the agent advertises live under `initialize` -> "
            "`result.capabilities._meta`, not as an unrecognized root key of `capabilities` "
            "itself."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:93,126-149"),
    ),
    Requirement(
        id="ACP-EXT-203",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Behaviour on receiving an unrecognized `$/`-prefixed protocol-level notification "
            "is recorded, never asserted -- the spec explicitly says the agent \"is free to "
            "ignore\" it, so there is no conforming/non-conforming distinction to enforce."
        ),
        citation=_cite("schema/v2/schema.json:6967-6990"),
    ),
    Requirement(
        id="ACP-ERROR-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "A JSON-RPC error's `message` is a non-empty, single-line string, and its "
            "optional `data` is well-formed JSON. Re-cited from v1 unchanged (D3): `Error` "
            "`$def` is byte-identical between v1 and v2."
        ),
        citation=_cite("schema/v2/schema.json:4127-4149; docs/protocol/v2/overview.mdx:181-185"),
    ),
    Requirement(
        id="ACP-SHUTDOWN-001",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "The agent exits promptly once stdin closes, without needing SIGTERM/SIGKILL. "
            "Re-cited from v1 unchanged (D3): v2 still defines no dedicated shutdown method "
            "and no stdin-EOF MUST -- only the mermaid step \"Close stdin, terminate "
            "subprocess\"."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx:41"),
    ),
    Requirement(
        id="ACP-SCHEMA-002",
        tier=Tier.ADVISORY,
        capability=None,
        text=(
            "No agent-authored request/notification `params` or response `result` carries an "
            "unrecognized root-level key. Re-cited from v1, with a v2-specific carve-out: "
            "unknown-root-key detection is skipped for any object matched by an `other` "
            "fallback branch, since an unknown/`_`-prefixed variant is by construction not "
            "\"a type that's part of the specification\" -- already implemented in "
            "`tck.v2.validation.find_unknown_root_keys`."
        ),
        citation=_cite("docs/protocol/v2/extensibility.mdx:39,113-120"),
    ),
    Requirement(
        id="ACP-STDERR-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Stderr byte count is recorded for a human reading the report. Re-cited from v1 "
            "unchanged (D3): the spec has nothing to say about stderr in either version."
        ),
        citation=_cite("docs/protocol/v2/transports.mdx"),
    ),
    Requirement(
        id="ACP-INFO-PARSE-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Behaviour on a malformed (non-JSON) stdin line is recorded, never asserted. Re-cited "
            "from v1 unchanged (D3): v2's error.mdx is still \"Documentation coming soon\" on "
            "this exact scenario."
        ),
        citation=_cite("docs/protocol/v2/error.mdx"),
    ),
    Requirement(
        id="ACP-INFO-INVALIDREQ-001",
        tier=Tier.INFORMATIONAL,
        capability=None,
        text=(
            "Behaviour on a structurally-invalid (well-formed JSON, not a valid JSON-RPC "
            "envelope) request line is recorded, never asserted. Re-cited from v1 unchanged "
            "(D3): v2's error.mdx is still \"Documentation coming soon\" on this exact "
            "scenario."
        ),
        citation=_cite("docs/protocol/v2/error.mdx"),
    ),
)


REGISTRY: dict[str, Requirement] = {requirement.id: requirement for requirement in _DECLARATIONS}


def get(requirement_id: str) -> Requirement:
    """Look up a requirement by id, raising a helpful `KeyError` if it is not registered."""
    try:
        return REGISTRY[requirement_id]
    except KeyError:
        raise KeyError(
            f"{requirement_id!r} is not a registered requirement id; known ids: "
            f"{sorted(REGISTRY)}"
        ) from None
