# Vendored files

`schema.json` and `meta.json` in this directory are verbatim copies of the ACP v2 JSON Schema,
vendored from the spec's source-of-truth repository. Do not hand-edit them.

**v2 is Draft** (schema version `2.0.0-alpha.5` as of the commit below) -- unlike `tck/v1/schema/`,
this directory should be expected to churn: field shapes, capability markers, and even method
inventories may still change upstream before v2 stabilizes.

- **Source repo:** https://github.com/agentclientprotocol/agent-client-protocol
  (local read-only checkout used for the copy: the path configured by the
  `check-specification` skill, `.agents/skills/check-specification/.repo`)
- **Commit:** `8f76d6c8cf379a0f8a7fe2bbee6007fb2a53a84e`
- **Date vendored:** 2026-09-21
- **Copy commands used:**

  ```
  cp <spec-repo>/schema/v2/schema.json src/tck/v2/schema/schema.json
  cp <spec-repo>/schema/v2/meta.json   src/tck/v2/schema/meta.json
  ```

  Only `schema/v2/schema.json`/`meta.json` are vendored -- never `schema/v2/schema.unstable.json`
  (an even-less-stable superset the spec repo carries alongside the Draft schema).

## Refreshing

1. Confirm the spec repo checkout's current HEAD: `git -C <spec-repo> rev-parse HEAD`.
2. Re-run the two `cp` commands above with the new checkout path.
3. Update the commit hash and date in this file, and `SCHEMA_REVISION` in
   `src/tck/v2/protocol.py`.
4. Re-run `uv run pytest` -- `tests/v2/test_validation.py` will catch any shape the new schema
   changed that `src/tck/v2/protocol.py` / `src/tck/v2/validation.py` assumed.
5. If method names, `x-side`/`x-method` annotations, the top-level `anyOf` branch layout (`Agent`
   / `Client` / `AgentBatchCall` / `AgentBatchResponse` / `ClientBatchCall` / `ClientBatchResponse`
   / `ProtocolLevel`), or the open-enum `"other"` fallback branch shape (e.g. `StopReason`)
   changed, re-check `src/tck/v2/protocol.py` and `src/tck/v2/validation.py` by hand -- both parse
   the schema structurally, not just by value.
