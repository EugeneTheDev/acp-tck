# Vendored files

`schema.json` and `meta.json` in this directory are verbatim copies of the ACP v1 JSON
Schema, vendored from the spec's source-of-truth repository. Do not hand-edit them.

- **Source repo:** https://github.com/zed-industries/agent-client-protocol
  (local read-only checkout used for the copy: the path configured by the
  `check-specification` skill, `.agents/skills/check-specification/.repo`)
- **Commit:** `6d08f412a7a1370d3cc9a124e3be3d6acf92641e`
- **Date vendored:** 2026-09-18
- **Copy commands used:**

  ```
  cp <spec-repo>/schema/v1/schema.json src/tck/v1/schema/schema.json
  cp <spec-repo>/schema/v1/meta.json   src/tck/v1/schema/meta.json
  ```

## Refreshing

1. Confirm the spec repo checkout's current HEAD: `git -C <spec-repo> rev-parse HEAD`.
2. Re-run the two `cp` commands above with the new checkout path.
3. Update the commit hash and date in this file.
4. Re-run `uv run pytest` — `tests/v1/test_validation.py` will catch any shape the new schema
   changed that `src/tck/v1/protocol.py` / `src/tck/v1/validation.py` assumed.
5. If method names, `x-side`/`x-method` annotations, or the top-level `anyOf` branch layout
   (`Agent` / `Client` / `ProtocolLevel`) changed shape, re-check `src/tck/v1/protocol.py` and
   `src/tck/v1/validation.py` by hand — both parse the schema structurally, not just by value.
