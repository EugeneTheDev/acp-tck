---
name: check-a2a-tck
description: Check the A2A (Agent2Agent) TCK, the project this ACP TCK was inspired by, for ideas on TCK structure, test organization, and implementation approach. Use for inspiration and comparison only, never as an authoritative guide for how this project must implement anything, and never as a source of truth for ACP protocol behavior.
---

# Check the A2A TCK

This ACP TCK project was inspired by the [A2A (Agent2Agent) TCK](https://github.com/a2aproject/a2a-tck). Use the local A2A TCK checkout to see how a sibling protocol's TCK approached similar problems: test harness structure, SUT (system-under-test) drivers, scenario/category organization, reporting, and conformance-level conventions.

This is a different protocol (A2A, not ACP) and a different project with its own conventions and history. Treat everything found here as inspiration and prior art, not a specification for this project:

- Do not treat A2A TCK design choices as requirements this project must mirror.
- Do not use A2A TCK behavior as evidence of ACP protocol behavior; use the `check-specification` skill for that.
- Do not use A2A TCK implementation as a reference implementation to match line-for-line; use `check-rust-sdk` or `check-python-sdk` when Rust/Python SDK behavior is the question.
- When proposing an approach based on what's found here, say explicitly that it comes from A2A TCK and explain why it might or might not fit ACP's TCK, rather than porting it silently.

## Locate the repository

The `.repo` file next to this `SKILL.md` is gitignored and contains one absolute path to a local clone of the A2A TCK repository. Read and trim that path before doing any research.

If `.repo` does not exist, explicitly ask the user for permission to clone the repository and for their preferred clone location. Do not clone it until permission is granted. If the user grants permission without choosing a location, clone the repository as `a2a-tck` beside the current ACP TCK checkout. After cloning, write the clone's absolute path to `.repo`.

If `.repo` exists but its value does not identify a usable Git checkout, report the problem and ask the user whether to correct the path or create a clone. Do not silently replace an existing checkout.

## Refresh before research

Before exploring or searching the local A2A TCK checkout, update it:

```bash
git -C "<absolute path read from .repo>" pull --ff-only
```

Run this on every use of the skill, even if the checkout was used recently. If the pull fails, report the failure and do not describe the checkout as current. Do not discard local changes, reset branches, or otherwise repair the checkout without the user's authorization.

After the pull succeeds, read the checkout's applicable `AGENTS.md` or other agent-guidance files before researching it, including more specific guidance in subdirectories you inspect.

## Search the checkout

If the `context-search` skill is available, combine it with this skill when the relevant file, behavior, or subsystem is not already known. Run its semantic search from the A2A TCK checkout and follow its search-and-inspect workflow. Prefer this semantic bootstrap to broad keyword grepping.

If `context-search` is unavailable, fails, or returns no useful result, continue with other exploration approaches such as `rg --files`, focused `rg` queries, directory inspection, and direct file reads. A semantic-search miss must not block the research. When the relevant file or symbol is already known, navigate to it directly instead of invoking semantic search.

## Draw ideas, not requirements

When answering a question with this skill:

- Describe what A2A TCK does and where (concrete repository-relative files and lines), so the user can judge fit themselves.
- Note what is specific to A2A's protocol semantics or SUT model versus what is a general TCK-design idea that could translate to ACP.
- Prefer surfacing options and tradeoffs over recommending a single "correct" port of the A2A approach.
- If this project's current approach already differs from A2A TCK's, do not treat that difference as a defect to fix — surface it only if the user is asking for a comparison.
