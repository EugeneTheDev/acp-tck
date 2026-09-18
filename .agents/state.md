# State

**Last updated:** 2026-09-18 (session 1, start)
**Last commit pushed:** d57abc8 (add prompt and agent definitions)

## Deliverable shape
Not yet decided. Pending research round 1 (see `plan.md`).

## Implemented and verified
Nothing. Repo contains only `pyproject.toml` skeleton (`requires-python>=3.14`, entry point `acp-tck = "tck:main"`), empty `src/tck/__init__.py`, empty `AGENTS.md`/`README.md`.

## In flight
Research round 1 — four researchers (Opus, general-purpose agents briefed with `.agents/agents/researcher.md`):
1. ACP v1 protocol surface → `.agents/research/acp-v1-protocol-surface.md`
2. Transport + JSON-RPC semantics → `.agents/research/acp-v1-transport-and-jsonrpc.md`
3. A2A TCK structure (inspiration) → `.agents/research/a2a-tck-structure.md`
4. Reference SDKs as harness/fixtures → `.agents/research/reference-sdks-as-harness.md`

## Open questions / blockers
- Deliverable shape must be decided after round 1.

## Next actions
1. Read the four reports; resolve conflicts; re-spawn research where vague.
2. Decide deliverable shape; write it into `state.md` and `plan.md`.
3. Spawn first programmer slice (skeleton + agent launcher + initialize test).
