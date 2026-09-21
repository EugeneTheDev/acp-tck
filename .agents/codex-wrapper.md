# TCK run against `codex-acp` (OpenAI Codex ACP wrapper)

**Verdict: NOT CONFORMANT** — but *zero* MANDATORY failures. Every failure is in the
CAPABILITY tier (3) plus ADVISORY (3).

## Run details

- Agent: `node /Users/eugene/Documents/JetBrains/projects/codex-acp/dist/index.js`
  (`@agentclientprotocol/codex-acp` 1.12.0, built from local `main` with `npm run build`)
- Command:
  ```
  uv run acp-tck --agent-cwd /tmp/acp-tck-wd --timeout 90 --test-timeout 300 \
    --report-json .agents/reports/codex-acp.json -- \
    node /Users/eugene/Documents/JetBrains/projects/codex-acp/dist/index.js
  ```
- Date: 2026-09-21, 09:56–09:59 UTC (212 s). TCK 0.1.0, protocol v1, schema
  `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`.
- Report: `.agents/reports/codex-acp.json`
- The adapter was already authenticated (it emitted
  `_auth/status_update {"kind":"gateway","label":"Custom model gateway","detail":"wire"}`),
  so `session/new` was not auth-gated and `--auth-method` was **not** passed (see SKIPs below).
  Prompt turns hit the real model (`gpt-5.6-sol[high]`).

## Score

| Tier | PASS | FAIL | SKIPPED | NOT_TESTED |
|---|---|---|---|---|
| MANDATORY | 21 | **0** | 0 | 0 |
| CAPABILITY | 13 | **3** | 3 | 0 |
| ADVISORY | 8 | **3** | 1 | 0 |
| INFORMATIONAL | 4 | 0 | 0 | 0 |

`blocked_by_auth: false`.

## Failures

### Root cause A — a freshly created session has no persisted "rollout"

Three failures share one bug: Codex only persists a thread's rollout file after the first
turn. Any session-management method invoked on a session that was created but never prompted
fails with `-32603 Internal error / "no rollout found for thread id <uuid>"`.

- **ACP-DELETE-001 (CAPABILITY, FAIL)** — `session/new` then `session/delete` on that id:
  `{"code":-32603,"message":"Internal error","data":{"details":"no rollout found for thread id 01a0c367-9f6b-…"}}`
- **ACP-RESUME-001 (CAPABILITY, FAIL)** — `session/new` then `session/resume` with the same
  id + `cwd`: same `no rollout found` error.
- **ACP-LOAD-003 (ADVISORY, FAIL)** — `session/new` then `session/load`: same error. (This
  test never got as far as its real assertion — `{}` vs `null`.)

Corroboration that this is the mechanism, not a general breakage: `ACP-LOAD-001` and
`ACP-LIST-001/002` **PASS**, and those tests run a prompt turn before the
`session/load`. So load/resume/delete work fine on a session that has taken at least one turn.
`sessionCapabilities.{resume,delete}` and `loadSession: true` are advertised unconditionally,
so per the TCK's CAPABILITY rule these count as real failures.

### Root cause B — `session/delete` rejects an unknown session id

- **ACP-DELETE-002 (ADVISORY, FAIL)** — `session/delete {"sessionId":"tck-never-created-session"}`
  returns
  `-32603 … "invalid session id: invalid character: expected an optional prefix of \`urn:uuid:\` followed by [0-9a-fA-F-], found \`t\` at 1"`.
  The spec's SHOULD is that deleting an unknown/already-deleted session succeeds silently. Two
  sub-issues: the id is parsed as a UUID (ACP session ids are opaque strings), and a
  not-found delete errors instead of no-op'ing.

### Root cause C — a `session/update` arrives *after* the `session/load` response

- **ACP-LOAD-002 (CAPABILITY, FAIL)** — the replay itself is correctly ordered (all history
  updates precede the response), but ~immediately *after* the `session/load` result the
  adapter emits one more notification for that session:
  ```
  <-- {"jsonrpc":"2.0","id":4,"result":{"models":{…}}}
  <-- {"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"01a0c367-4335-…",
        "update":{"sessionUpdate":"session_info_update","title":"Simple hello greeting"}}}
  ```
  It looks like an async title-generation callback racing the load reply rather than part of
  the replay — but the requirement is "nothing for this session after the load response".

### Root cause D — non-`_meta` extension fields at the root of spec result types

- **ACP-SCHEMA-002 (ADVISORY, FAIL)** — `unknown root-level key(s) found (Req 41):`
  - `session/new result: ['models']`
  - `session/prompt result: ['usage']`

  Neither `NewSessionResponse.models` nor `PromptResponse.usage` exists in the vendored v1
  schema (vendored 2026-09-18, three days before this run, so this is not TCK staleness).
  Req 41 says custom data belongs under `_meta`. Note the adapter *does* use `_meta` correctly
  elsewhere (`_meta.quota`, `_meta.codex`, `_meta.jetbrains.air`, …) — these two look like
  fields from a newer/unstable ACP revision leaking into a v1 session.

## Skips (not failures, but worth knowing)

- **ACP-AUTH-003** — no `--auth-method` given. I deliberately did not drive a real
  `authenticate` handshake (`api-key`/`chat-gpt`) so the run wouldn't touch your local Codex
  credentials. Re-run with `--auth-method api-key` (plus a key in the env) to cover it.
- **ACP-AUTH-005** — N/A, the agent advertises `authMethods`.
- **ACP-PROMPTCAP-002** — `promptCapabilities.audio` not advertised (correctly skipped).
- **ACP-CLOSE-002** — "prompt turn completed before `session/close` could be sent": an
  unavoidable race, the turn finished too fast. A longer prompt could exercise it.

## Things that passed and are worth calling out

- Every MANDATORY requirement, including the strengthened **ACP-INIT-003** (version
  negotiation) that both upstream SDK agents fail, and **ACP-INIT-004** (`agentInfo`), which
  neither upstream agent sets.
- All three MANDATORY client-capability negative tests (`fs`/`terminal`/`elicitation` never
  called unadvertised) and the cancellation pair (ACP-CANCEL-001/002) — the cancel turn
  genuinely resolved with `stopReason: "cancelled"`, not a skip.
- Modes, config options (including the Req 33 boolean gate), `additionalDirectories`, image and
  embeddedContext prompt content, `_meta` on `session/prompt`, logout.
- INFORMATIONAL probes all behave well: `-32700` with `id: null` for malformed JSON, `-32600`
  for a structurally invalid request, connection stays usable after both; 671 bytes of stderr.
  Unknown-`sessionId` is answered `-32603` (spec is silent here; `-32602` would read better).

## Suggested fixes, highest value first

1. Make `session/load`/`resume`/`delete` work on a session that has not yet taken a turn
   (persist the rollout at `session/new`, or treat a known-but-empty thread as loadable).
   Clears 3 of the 6 failures, 2 of them CAPABILITY — i.e. this alone plus #2 flips the verdict.
2. Suppress (or emit before the response) the post-`session/load` `session_info_update`.
3. `session/delete` on an unknown id: return `{}` instead of erroring, and don't UUID-validate
   opaque session ids.
4. Move `NewSessionResponse.models` and `PromptResponse.usage` under `_meta` for v1 clients.
