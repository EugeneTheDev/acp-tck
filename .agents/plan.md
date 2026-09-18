# Plan

## Done
- (nothing yet)

## In progress — Research round 1 (deliverable shape)
Four parallel researchers, disjoint questions, distinct output files:
1. `research/acp-v1-protocol-surface.md` — full inventory of ACP v1 methods, directions, tiers, capabilities, version negotiation; v1 vs v2 differences flagged.
2. `research/acp-v1-transport-and-jsonrpc.md` — transport (stdio framing), JSON-RPC rules, error codes, unknown-method handling, notification semantics, how agents are launched.
3. `research/a2a-tck-structure.md` — how the A2A TCK is shaped (CLI, SUT config, tiers, reporting, pytest usage); ideas only.
4. `research/reference-sdks-as-harness.md` — can the Python SDK act as the TCK's client side; what example agents exist in Python/Rust SDKs to serve as conforming fixtures for the TCK's own tests.

## Next
- Judge reports; decide deliverable shape (CLI vs library, agent launch config, tiering, reporting); record decision in `state.md`.
- First implementation slice: project skeleton + agent launcher + initialize handshake test.

## Open questions
- Deliverable shape (pending round 1).
