# Has the upstream ACP spec changed, between the vendored revision and current HEAD, in a way that affects v1 wire format, normative v1 docs, or TCK-asserted requirements?

**Sources checked:** `agent-client-protocol` (spec repo, source of truth) @ `d3c1dd78c5f25afbc37a755ebd1982b43dd97069`, 2026-09-18 15:03:35 +0000 (pulled `--ff-only`, checkout clean, pull succeeded) — vendored baseline `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`. TCK side: `src/tck/requirements.py`, `src/tck/schema/v1/VENDORED.md`.
**Confidence:** high — byte-level `git diff --quiet` on the vendored artifacts plus line-by-line re-verification of every cited docs line that moved.

## Answer

**No wire-format drift.** The entire `schema/v1/` directory is byte-identical between `6d08f412` and HEAD — `schema.json`, `meta.json`, `schema.unstable.json`, `meta.unstable.json`, `CHANGELOG.md`, `Cargo.toml` and `src/` all unchanged (`git diff 6d08f412..HEAD --stat -- schema/v1` is empty). **Re-vendoring is not needed.**

Normative v1 documentation did change, but only in the direction of *correcting docs to match the already-vendored schema*. Three of the five docs bugs the TCK research relied on were fixed upstream (`current_mode_update.currentModeId`, the `session/load` `null` → `{}` example, the over-broad `_meta` universality claim); two remain (the `error.mdx` stub, the incomplete "Optional Methods" list in `overview.mdx`), and the `initialization.mdx` vs `content.mdx` baseline-content-types discrepancy is untouched. No TCK requirement lost its basis; two were strengthened. **Six requirements need citation line-number bumps** (all in `extensibility.mdx`, `file-system.mdx`, `terminals.mdx`), and two need *wording* updates because they describe a docs bug that no longer exists.

## 1. Commits since the vendored revision

`git rev-list --count 6d08f412..HEAD` → **5**.

| Commit | Subject | Touches v1? |
|---|---|---|
| `d89c8d3` | `docs: correct empty response examples (#2176)` | yes — v1 docs |
| `b96b439` | `fix(docs): align protocol guides and schema references (#2177)` | yes — v1 docs |
| `ac82df6` | `fix(rust): accept null for defaultable payloads (#2178)` | Rust crate only, no schema output change |
| `7e87dc2` | `chore(agent-client-protocol-schema): release v1.9.1 (#2179)` | version bump / CHANGELOG |
| `d3c1dd7` | `docs: update registry agents (#2180)` | no (`docs/get-started/registry.mdx`) |

Note on `ac82df6`: it introduces a `default_on_null!` macro in `agent-client-protocol-schema/src/serde_util.rs` so that all-optional ("defaultable") payloads deserialize from JSON `null` as well as `{}`. This is *receiver-side leniency in the Rust representation only*; the generated JSON Schema is unchanged, which is why `schema/v1/schema.json` is byte-identical. It is the reference-side counterpart of `d89c8d3`: docs now show `{}`, receivers must still tolerate `null`.

## 2. Diff of the v1 surface

`git diff 6d08f412..HEAD --stat -- schema/v1 docs/protocol/v1` — 17 files, all under `docs/protocol/v1` (9 stable + 8 `draft/` mirrors of the same edits):

Byte-wise verdict on the vendored artifacts (`git diff --quiet`):

- `schema/v1/schema.json` — **UNCHANGED**
- `schema/v1/meta.json` — **UNCHANGED**
- `schema/v1/schema.unstable.json` — **UNCHANGED** (informational)
- in fact the whole `schema/v1/` tree is unchanged.

Per-file summary of the stable v1 docs (the `docs/protocol/v1/draft/*` files received the identical edits; draft = v1 + unstable feature flags, informational for the TCK):

| File | Change | Bearing on TCK |
|---|---|---|
| `extensibility.mdx` (+4 lines at the top) | The `_meta` paragraph was rewritten: "All types in the protocol include a `_meta` field" → "Object types that **define** a `_meta` field … Not every protocol type defines `_meta`; for example, the `Error` object does not." (`docs/protocol/v1/extensibility.mdx:10-14`) | Corrects an over-broad claim. Shifts all later citations by **+4**. |
| `file-system.mdx` | "…checking the Client Capabilities field in the `initialize` **response**" → "…in the Client's `initialize` **request**", and the example envelope changed from `result` to `method`/`params` (`:10`, `:12-17`). Also the `fs/write_text_file` empty response example `"result": null` → `"result": {}` (`:115`). | Factual correction; confirms the TCK's model (the mock client sends `clientCapabilities` in its own `initialize` request). Shifts `:28` → `:29`. |
| `terminals.mdx` | Same `initialize` response→request correction (`:10`, `:12-17`). | Shifts `:25` → `:26`. |
| `prompt-turn.mdx` | `sessionId` and `prompt` `ParamField`s marked `required` (`:86`, `:89`). Net line count unchanged (349→349). | Strengthens the `session/prompt` param contract; no cited line moved. |
| `session-modes.mdx` | `current_mode_update` example: `"modeId": "code"` → `"currentModeId": "code"` (`:118`). Permission-request example's `content` entry rewrapped as `{"type":"content","content":{...}}` (`:144-148`). | **Docs bug fixed.** See §4. |
| `session-setup.mdx` | `session/load` empty response example `"result": null` → `"result": {}` (`:184`). | **Docs bug fixed.** See §4. |
| `session-config-options.mdx` | `options` retyped `ConfigOptionValue[]` → `ConfigOptionValue[] \| ConfigOptionGroup[]`, plus a new "Grouped Select Options" section documenting `ConfigOptionGroup` (`group`/`name`/`options`, optional `_meta`) and stating values and groups are never mixed in one array. | Documents shape that was **already** in the vendored schema (`$defs.SessionConfigSelectGroup`, `schema/v1/schema.json:3147,3175`). ACP-CONFIG-001 already says "flat or grouped shape" — no change needed. |
| `tool-calls.mdx` | `switch_mode` added to the documented `ToolKind` list; `rawInput`/`rawOutput` retyped `object` → `unknown` with "omission and `null` are equivalent"; `ToolCallLocation.line` retyped `number` → `integer \| null`. | All three already matched the vendored schema (`ToolKind` contains `switch_mode`; `ToolCall.rawInput` has no `type` constraint; `ToolCallLocation.line` is `["integer","null"]`). Docs-only alignment. |
| `schema.mdx` (+117 lines) | Generated reference page; the schema generator (`schema-generator/src/main.rs`, +370 lines) now renders `anyOf` alternatives, so the `Elicitation` request-context alternatives (`Session` with `sessionId`/`toolCallId`, `Request` with `requestId`) are now shown. | Rendering completeness only — `schema.json` did not change, so nothing new on the wire. Not cited by the TCK. |

Cited v1 docs files that are **unchanged**: `overview.mdx`, `initialization.mdx`, `content.mdx`, `elicitation.mdx`, `transports.mdx`, `session-list.mdx`, `session-delete.mdx`, `error.mdx`.

Out of scope but noted: `docs/protocol/v2/**` changed substantially (new generated `schema.mdx`, `session-config-options`, `tool-calls`, `authentication`, `extensibility`, `migration`, `session-delete`, `session-setup`). None of it is v1 and none of it is cited by the TCK.

## 3. Re-check of every TCK requirement whose cited docs file changed

All normative statements still exist; none were removed. Line numbers below are HEAD.

| Requirement | Old citation | New line(s) | Status |
|---|---|---|---|
| ACP-JSONRPC-004 | `extensibility.mdx:80-92` | **`extensibility.mdx:84-96`** | Intact — "If the receiving end doesn't recognize the custom method name, it **should** respond with the standard 'Method not found' error" + `-32601` example. Still lower-case "should" → ADVISORY tier remains correct. |
| ACP-JSONRPC-005 | `extensibility.mdx:80-92` | **`:84-96`** | Intact (same block). |
| ACP-EXT-001 | `extensibility.mdx:43,52,65,109` | **`:47,56,69,113`** | Intact — `:47` `_`-prefix reservation, `:56` custom requests **MAY**, `:69` "implementations **MUST** respond accordingly with the provided `id`", `:113` "**SHOULD** ignore unrecognized notifications". MUST-vs-SHOULD split the requirement relies on is unchanged. |
| ACP-META-001 | `extensibility.mdx:10,33-37,39` | **`:10-14, 37-41, 43`** | **Basis narrowed but the requirement survives.** The universal "all types include `_meta`" claim at `:10` is gone; `_meta` is now only guaranteed on types that define it, and `Error` is called out as one that does not. ACP-META-001 only sends `_meta` on `session/prompt`, and `PromptRequest._meta` exists in the vendored schema, so the test is unaffected. The `traceparent`/`tracestate`/`baggage` SHOULD-reserved list (`:37-41`) and the root-field **MUST NOT** (`:43`) are verbatim intact. Recommend re-citing `:10-14` rather than `:10`. |
| ACP-SCHEMA-002 | `extensibility.mdx:39` | **`:43`** | Intact verbatim: "Implementations **MUST NOT** add any custom fields at the root of a type that's part of the specification." |
| ACP-CLIENTCAP-001 | `file-system.mdx:10,28` | **`:10,29`** | Intact. `:10` still the **MUST** verify-capability sentence (wording corrected to "the Client's `initialize` request"); `:29` still "If `readTextFile` or `writeTextFile` is `false` or not present, the Agent **MUST NOT** attempt to call the corresponding filesystem method." **Slightly strengthened**: the corrected wording makes it explicit that the capability lives in the client's own request, which is exactly how the TCK provokes the negative (mock client sends `clientCapabilities: {}`). |
| ACP-CLIENTCAP-002 | `terminals.mdx:10,25` | **`:10,26`** | Intact, same correction. `:26` still "If `terminal` is `false` or not present, the Agent **MUST NOT** attempt to call any terminal methods." |
| ACP-PROMPT-001 | `prompt-turn.mdx:217` | **`:217`** (unmoved) | Intact: "the Agent **MUST** respond to the original `session/prompt` request with a `StopReason`". |
| ACP-CANCEL-001 | `prompt-turn.mdx:332,339` | **`:332,339`** (unmoved) | Intact: `:332` "**MUST** respond … with the `cancelled` stop reason"; `:339` "Agents **MUST** catch these errors and return the semantically meaningful `cancelled` stop reason". |
| ACP-CANCEL-002 / ACP-CLOSE-002 | `prompt-turn.mdx:343` | **`:343`** (unmoved) | Intact: "**MAY** send `session/update` … after `session/cancel`, but it **MUST** ensure that it does so before responding to the `session/prompt` request." |
| ACP-LOAD-003 | `session-setup.mdx:180-186` | **`:180-186`** (unmoved) | **Strengthened.** The example now literally reads `"result": {}`. The requirement's own text already claims "the docs' historical `null` example was corrected upstream to `{}`" — as of HEAD that claim is true at the cited lines (at `6d08f412` the cited lines still showed `null`). Keeping it ADVISORY remains right: `ac82df6` makes the Rust reference accept `null` for defaultable payloads, so `null` is tolerated even though `{}` is what the docs show. |
| ACP-LOAD-001 / ACP-LOAD-002 | `session-setup.mdx:104,108-186` / `:134,178` | unmoved | Intact (file net line count 545→545; only `:184` changed). |
| ACP-SESSION-001/002, ACP-RESUME-001/002, ACP-CLOSE-001, ACP-ADDDIRS-001 | `session-setup.mdx:71,243,295-308,315-344` | unmoved | Intact. |
| ACP-MODES-002 | `session-modes.mdx:117-119 (docs bug)` | **`:117-119`** (unmoved) | **Basis changed: the docs bug is fixed.** `:118` now reads `"currentModeId": "code"`. The assertion (a `current_mode_update` must carry `currentModeId`) is unchanged and now supported by *both* docs and schema. The requirement's text ("the docs' `modeId` example … is a confirmed docs bug; the schema wins") is now stale and should be reworded. |
| ACP-MODES-001 | `session-modes.mdx` (no line) | n/a | Intact. |
| ACP-CONFIG-001/002/003 | `schema/v1/schema.json:*` only | n/a | Schema byte-identical → citations valid as-is. The new `session-config-options.mdx` "Grouped Select Options" section is a useful *additional* citation for ACP-CONFIG-001's "flat or grouped shape" clause (`docs/protocol/v1/session-config-options.mdx:126-152`). |

Every requirement citing only `schema/v1/schema.json`, `agent-client-protocol-schema/src/{rpc,v1/error}.rs`, `transports.mdx`, `overview.mdx`, `initialization.mdx`, `content.mdx`, `elicitation.mdx`, `session-list.mdx`, or `session-delete.mdx` is unaffected: those paths are unchanged (the two `.rs` files cited — `rpc.rs:12-39,245-289` and `v1/error.rs` — sit outside the `default_on_null!` refactor; `rpc.rs` gained 5 lines, so re-verify `rpc.rs:245-289` if that citation is ever tightened).

**Nothing was weakened or removed.** Net effect: two requirements strengthened (ACP-LOAD-003, ACP-MODES-002 — both now have docs *and* schema agreeing), one narrowed in scope without losing its basis (ACP-META-001).

## 4. Status of the docs bugs the TCK research relied on

| Bug the research relied on | Status at HEAD | Evidence |
|---|---|---|
| `current_mode_update` shows `modeId`, schema says `currentModeId` | **FIXED** (`d89c8d3`/`b96b439`) | `docs/protocol/v1/session-modes.mdx:118` now `"currentModeId": "code"` |
| `session/load` empty response shown as `null` instead of `{}` | **FIXED** (`d89c8d3`) | `docs/protocol/v1/session-setup.mdx:184` now `"result": {}`; same fix applied to `fs/write_text_file` at `docs/protocol/v1/file-system.mdx:115` |
| `error.mdx` is a stub | **NOT FIXED** | `docs/protocol/v1/error.mdx` is still 6 lines ending in "_Documentation coming soon_", unchanged since `6d08f412`. Also: ACP-INFO-UNKNOWNSESSION-001 cites `docs/error.mdx`, a path that **does not exist** at either revision — the real path is `docs/protocol/v1/error.mdx`. Pre-existing typo, not drift. |
| `initialization.mdx:204` baseline content types (text + `resource_link`) vs `content.mdx:31` (text only) | **NOT FIXED / untouched** | Both files byte-identical to `6d08f412`. ACP-PROMPT-003's ADVISORY tier and its "treated as advisory until upstream resolves the discrepancy" rationale still hold exactly as written. |
| "Optional Methods" list in `overview.mdx` is incomplete | **NOT FIXED** | `docs/protocol/v1/overview.mdx` unchanged. Its agent-method list is still `initialize`, `authenticate`, `session/new`, `session/prompt`, `session/load`, `logout`, `session/set_mode`, `session/cancel` — still omitting `session/resume`, `session/list`, `session/delete`, `session/close`, `session/set_config_option`, all of which exist in the vendored schema and are covered by the TCK. |
| (bonus) `extensibility.mdx` claimed *all* protocol types carry `_meta` | **FIXED** | `docs/protocol/v1/extensibility.mdx:10-14` now scopes the claim and names `Error` as an exception |

## 5. Recommendation

**Do not re-vendor.** `schema/v1/schema.json` and `schema/v1/meta.json` are byte-identical to the vendored copies, so `src/tck/schema/v1/*` and `SCHEMA_REVISION` = `6d08f412…` remain accurate for wire purposes. Bumping `SCHEMA_REVISION` to `d3c1dd7` would be a *citation* refresh, not a schema refresh — and it must be done as one atomic change with the line-number edits below, because `_cite()` stamps every citation with `SPEC_REVISION` globally. Either leave the whole registry at `6d08f412` (every citation is then still exactly correct, which is the cheapest correct state) or move all of it to `d3c1dd7` together with these edits:

Citation line updates needed if bumping to `d3c1dd7`:

1. ACP-JSONRPC-004: `extensibility.mdx:80-92` → `84-96`
2. ACP-JSONRPC-005: `extensibility.mdx:80-92` → `84-96`
3. ACP-EXT-001: `extensibility.mdx:43,52,65,109` → `47,56,69,113` (also in ACP-EXT-001's prose, which quotes both line sets)
4. ACP-META-001: `extensibility.mdx:10,33-37,39` → `10-14,37-41,43`
5. ACP-SCHEMA-002: `extensibility.mdx:39` → `43`
6. ACP-CLIENTCAP-001: `file-system.mdx:10,28` → `10,29`
7. ACP-CLIENTCAP-002: `terminals.mdx:10,25` → `10,26`

Requirement *text* updates (independent of the revision bump, because they now misdescribe upstream):

8. ACP-MODES-002: drop "the docs' `modeId` example (`session-modes.mdx:117-119`) is a confirmed docs bug; the schema wins" — as of `d89c8d3` the docs show `currentModeId` and agree with the schema. The assertion itself does not change.
9. ACP-LOAD-003: its "corrected upstream to `{}`" wording is now true at the cited lines; consider adding `ac82df6` / `agent-client-protocol-schema/src/serde_util.rs` as the reason `null` must still be tolerated, which is what keeps the tier ADVISORY.
10. ACP-INFO-UNKNOWNSESSION-001: fix the citation path `docs/error.mdx` → `docs/protocol/v1/error.mdx` (still a stub).

Optional citation additions (strictly nice-to-have):

11. ACP-CONFIG-001: add `docs/protocol/v1/session-config-options.mdx:126-152` (new "Grouped Select Options" section) as prose backing for the grouped shape, which until now was cited from the schema only.
12. ACP-PROMPT-001 / the prompt-param contract: `docs/protocol/v1/prompt-turn.mdx:86,89` now mark `sessionId` and `prompt` as `required`, if the TCK ever wants a docs citation for that.

**Nothing new in v1 for the TCK to cover.** No new stable methods, capabilities, fields, or enum values: the schema is byte-identical, so by construction there is no new v1 surface. Everything that *looks* new in the docs (`ConfigOptionGroup`, the `switch_mode` tool kind, `unknown`-typed `rawInput`/`rawOutput`, nullable `ToolCallLocation.line`, elicitation `anyOf` request contexts) was already present in the vendored `schema.json` and is already either covered (ACP-CONFIG-001's grouped shape) or out of the TCK's assertion set. `schema.unstable.json` is likewise unchanged, so there is no drift in the unstable/draft surface either.

## Discrepancies

- **Docs vs. Rust reference on empty responses:** docs now uniformly show `"result": {}` (`session-setup.mdx:184`, `file-system.mdx:115`) while the Rust reference was simultaneously changed to *accept* `null` for defaultable payloads (`ac82df6`, `agent-client-protocol-schema/src/serde_util.rs`). Not a contradiction — `{}` is the prescribed emission, `null` is tolerated on receipt — but it is exactly why ACP-LOAD-003 must stay ADVISORY and must not be promoted to MANDATORY.
- **`initialization.mdx:204` vs `content.mdx:31`** on baseline prompt content types: unresolved upstream, unchanged since `6d08f412`.
- **`overview.mdx` "Optional Methods" vs `schema.json`:** the docs index still omits five agent methods that exist in the schema. Unresolved.
- **Generated `schema.mdx` vs `schema.json`:** `docs/protocol/v1/schema.mdx` changed while `schema.json` did not. Traced to the generator gaining `anyOf` rendering (`schema-generator/src/main.rs`), i.e. the page was previously *under*-reporting the schema. No protocol consequence.

## Open questions

- Project policy question for the orchestrator, not a research gap: whether `SPEC_REVISION`/`SCHEMA_REVISION` should track the docs revision citations are valid against (`d3c1dd7`) or the revision the vendored schema bytes came from (`6d08f412`). They are currently the same symbol (`requirements.py:21-25`), so the two purposes cannot diverge; if citation refreshes are expected to outpace schema refreshes, splitting them is worth considering.
- `agent-client-protocol-schema/src/rpc.rs` gained 5 lines (`ac82df6`). ACP-JSONRPC-001 cites `rpc.rs:12-39,245-289`; I did not re-verify those exact ranges since `rpc.rs` is a reference-representation citation, not a v1 docs/schema citation, and the requirement (id echo) is not in question.
- The `docs/protocol/v1/draft/*` mirrors received the same edits; whether the TCK ever wants to assert anything from the v1 unstable surface is out of scope here.
