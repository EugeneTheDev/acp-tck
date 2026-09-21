# TCK run against `claude-agent-acp` (Claude ACP wrapper)

**Verdict: NOT CONFORMANT** — but *zero* MANDATORY failures. Two CAPABILITY failures and two
ADVISORY failures, all in session management / extensibility.

## Run details

- Agent: `node /Users/eugene/Documents/JetBrains/projects/claude-agent-acp/dist/index.js`
  (`@agentclientprotocol/claude-agent-acp` 0.79.0, branch `main` at `d421f56`
  "chore(main): release 0.79.0 (#1142)", rebuilt with `npm run build`)
- Command:
  ```
  uv run acp-tck --agent-cwd /tmp/acp-tck-wd-claude --timeout 90 --test-timeout 300 \
    --report-json .agents/reports/claude-agent-acp.json -- \
    node /Users/eugene/Documents/JetBrains/projects/claude-agent-acp/dist/index.js
  ```
- Date: 2026-09-21, 10:14–10:15 UTC (76 s). TCK 0.1.0, protocol v1, schema
  `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`.
- Report: `.agents/reports/claude-agent-acp.json`
- Build note: `npm run build` (`tsc`) reports **7 pre-existing type errors** against the
  installed `@anthropic-ai/claude-agent-sdk` (`SDKAPIRetryMessage.no_response`,
  `defaultToNo`/`suppressAlwaysAllowRule`/`mcpServer` on the permission-callback options,
  `verification_required`/`cloud_credential_error` on `SDKAssistantMessageError`). `tsc` still
  emits, and the emitted `dist/` is what was tested — but the build is not clean.
- The adapter was already authenticated (`_auth/status_update` →
  `{"kind":"api_key","label":"Anthropic API key","detail":"apiKeyHelper"}`) and advertises
  `authMethods: []`, so no `--auth-method` was needed. Prompt turns hit the real model.

## Score

| Tier | PASS | FAIL | SKIPPED | NOT_TESTED |
|---|---|---|---|---|
| MANDATORY | 21 | **0** | 0 | 0 |
| CAPABILITY | 15 | **2** | 2 | 0 |
| ADVISORY | 10 | **2** | 0 | 0 |
| INFORMATIONAL | 4 | 0 | 0 | 0 |

`blocked_by_auth: false`.

## Failures

### `session/delete` — both failures

- **ACP-DELETE-001 (CAPABILITY, FAIL)** — `session/new` immediately followed by
  `session/delete` on the returned id:
  ```
  {"code":-32603,"message":"Internal error",
   "data":{"details":"Session 9b36a6b1-4af2-4348-89bd-7f271fe0ef18 not found in any project directory"}}
  ```
  A session that was created but has not yet taken a turn has no transcript file on disk, so
  delete can't find it. `sessionCapabilities.delete` is advertised unconditionally, so this is
  a real CAPABILITY failure. (`session/resume` and `session/load` do *not* have this problem
  here — ACP-RESUME-001 and ACP-LOAD-001/003 all PASS, which is where the Codex wrapper also
  fails.)

- **ACP-DELETE-002 (ADVISORY, FAIL)** — `session/delete {"sessionId":"tck-never-created-session"}`:
  ```
  {"code":-32603,"message":"Internal error","data":{"details":"Invalid sessionId: tck-never-created-session"}}
  ```
  The spec's SHOULD is that deleting an unknown/already-deleted session succeeds silently.
  Two sub-issues: ACP session ids are opaque strings (this one is being validated as a UUID),
  and a not-found delete should be a no-op returning `{}`.

### `session/update` arrives after the `session/load` response

- **ACP-LOAD-002 (CAPABILITY, FAIL)** — the replay before the response is fine, but right
  after the load result the adapter emits one more notification for that session:
  ```
  <-- {"jsonrpc":"2.0","id":4,"result":{"sessionId":"af98c649-…","modes":{…}}}
  <-- {"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"af98c649-…",
        "update":{"sessionUpdate":"available_commands_update","availableCommands":[…]}}}
  ```
  It's the slash-command/skill list, presumably discovered asynchronously — but the
  requirement is "no `session/update` for this session after the `session/load` response".
  Either emit it before the response or defer it out of the load window.

  Side observation (not asserted by any requirement): the replay before the response carried
  only the `user_message_chunk`, not the assistant's reply, even though the session had
  completed a turn. L5 leaves replay fidelity unspecified, so the TCK doesn't flag it — but
  a client reconstructing history would see a one-sided conversation.

### Non-`_meta` root field on a spec result type

- **ACP-SCHEMA-002 (ADVISORY, FAIL)** — `unknown root-level key(s) found (Req 41):
  session/prompt result: ['usage']`. `PromptResponse` in the vendored v1 schema has only
  `stopReason` and `_meta`; Req 41 says custom data goes under `_meta`. The adapter already
  puts equivalent data in `_meta.quota` in the same response, so `usage` is redundant at the
  root. (Same finding as the Codex wrapper, which additionally leaks `models` on
  `session/new`.)

## Skips (not failures)

- **ACP-AUTH-003** — no `--auth-method` given. Moot here: the agent advertises
  `authMethods: []`, so there is no method id to drive. The empty-`authMethods` advisory
  **ACP-AUTH-005** (`session/new` must not fail with `-32000` when nothing is advertised)
  PASSes.
- **ACP-PROMPTCAP-002** — `promptCapabilities.audio` not advertised (correct skip).

## Things that passed and are worth calling out

- Every MANDATORY requirement, including the strengthened **ACP-INIT-003** (version
  negotiation) that both upstream SDK reference agents fail, and **ACP-INIT-004** (`agentInfo`).
- All three MANDATORY client-capability negative tests and both cancellation requirements —
  the cancelled turn genuinely resolved with `stopReason: "cancelled"`.
- `session/load`, `session/resume` (both requirements), `session/list`, `session/close`
  (including the mid-turn **ACP-CLOSE-002**, which the Codex run could only skip on a race),
  `additionalDirectories`, modes, config options (including the Req 33 boolean gate), image and
  embeddedContext content, `_meta` on `session/prompt`, logout.
- INFORMATIONAL probes all clean: `-32700` with `id: null` for malformed JSON, `-32600` for a
  structurally invalid request, connection usable after both; 913 bytes of stderr.
  Unknown-`sessionId` answers `-32603` (spec is silent; `-32602` would read better).

## Suggested fixes, highest value first

1. `session/delete` on a session that hasn't persisted yet: succeed instead of erroring.
   This is the only CAPABILITY failure with a substantive bug behind it.
2. Don't emit `available_commands_update` after the `session/load` response — send it during
   the replay, or after a beat outside the load window.
3. `session/delete` on an unknown id: return `{}`; stop UUID-validating opaque session ids.
4. Drop the root-level `usage` from the `session/prompt` result (it is already mirrored under
   `_meta.quota`).
5. Unrelated to conformance: fix the 7 `tsc` errors so `npm run build` is clean.

## Comparison with the Codex wrapper (`.agents/codex-wrapper.md`)

| | `claude-agent-acp` 0.79.0 | `codex-acp` 1.12.0 |
|---|---|---|
| Verdict | NOT CONFORMANT | NOT CONFORMANT |
| MANDATORY failures | 0 | 0 |
| CAPABILITY failures | 2 (DELETE-001, LOAD-002) | 3 (DELETE-001, RESUME-001, LOAD-002) |
| ADVISORY failures | 2 (DELETE-002, SCHEMA-002) | 3 (DELETE-002, LOAD-003, SCHEMA-002) |
| Shared bugs | pre-turn session not deletable; unknown-id delete errors; late update after `session/load`; root-level `usage` on `session/prompt` | same four |
| Unique to Codex | `session/load`/`resume` also fail pre-turn; root-level `models` on `session/new` | |

Both wrappers fail the same four things. The Codex wrapper's "no rollout found" problem is the
broader version of the Claude wrapper's "not found in any project directory" — Codex extends it
to `load`/`resume`, Claude's only affects `delete`.
