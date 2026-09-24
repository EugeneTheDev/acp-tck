# Vendored files

`schema.json`, `schema.unstable.json` and `meta.json` in this directory are verbatim copies of
the ACP v2 JSON Schema, vendored from the spec's source-of-truth repository. Do not hand-edit
them.

**v2 is Draft** (schema version `2.0.0-alpha.5` as of the commit below) -- unlike `tck/v1/schema/`,
this directory should be expected to churn: field shapes, capability markers, and even method
inventories may still change upstream before v2 stabilizes.

`schema.unstable.json` is a further-out-there superset of `schema.json`: it additionally defines
fields still gated behind an individual RFD (e.g. `AgentCapabilities.providers`,
`SessionCapabilities.fork`). It is used for exactly one purpose --
`tck.v2.validation.find_unknown_root_keys` (backing `ACP-EXT-202`/`ACP-SCHEMA-002`) resolves a
root key against it too, so a real RFD-typed field isn't flagged as an undeclared vendor
extension. Nothing validates a message against `schema.unstable.json` wholesale: full jsonschema
validation (`ACP-SCHEMA-001`) stays scoped to `schema.json` only, since that is what the
requirement text demands.

- **Source repo:** https://github.com/agentclientprotocol/agent-client-protocol
  (local read-only checkout used for the copy: the path configured by the
  `check-specification` skill, `.agents/skills/check-specification/.repo`)
- **Commit:** `d8805733cca4ef0d92e5135b50d5bfc2ea4fbdf3`
- **Date vendored:** 2026-09-25
- **Copy commands used:**

  ```
  cp <spec-repo>/schema/v2/schema.json          src/tck/v2/schema/schema.json
  cp <spec-repo>/schema/v2/schema.unstable.json src/tck/v2/schema/schema.unstable.json
  cp <spec-repo>/schema/v2/meta.json             src/tck/v2/schema/meta.json
  ```

  `schema/v2/meta.unstable.json` is still not vendored -- nothing here needs its method
  inventory (only the *field* shapes in `schema.unstable.json` matter to the root-key check
  above); revisit if a future check needs unstable method dispatch too.

## Refreshing

1. Confirm the spec repo checkout's current HEAD: `git -C <spec-repo> rev-parse HEAD`.
2. Re-run the three `cp` commands above with the new checkout path.
3. Update the commit hash and date in this file, and `SCHEMA_REVISION` in
   `src/tck/v2/protocol.py`.
4. Re-run `uv run pytest` -- `tests/v2/test_validation.py` will catch any shape the new schema
   changed that `src/tck/v2/protocol.py` / `src/tck/v2/validation.py` assumed.
5. If method names, `x-side`/`x-method` annotations, the top-level `anyOf` branch layout (`Agent`
   / `Client` / `AgentBatchCall` / `AgentBatchResponse` / `ClientBatchCall` / `ClientBatchResponse`
   / `ProtocolLevel`), or the open-enum `"other"` fallback branch shape (e.g. `StopReason`)
   changed, re-check `src/tck/v2/protocol.py` and `src/tck/v2/validation.py` by hand -- both parse
   the schema structurally, not just by value.
