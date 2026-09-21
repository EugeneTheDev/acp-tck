"""Shared test helpers.

Tests drive the harness with plain `asyncio.run(...)` rather than the `pytest-asyncio`
plugin -- this repo has exactly one place async code is exercised (the harness itself), so a
bare `asyncio.run` per test keeps the dependency list smaller without giving up anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tck.common.harness import AgentLaunch

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "agents" / "v1"
FIXTURES_DIR_V2 = Path(__file__).parent / "fixtures" / "agents" / "v2"

_FIXTURES_DIR_BY_VERSION = {"v1": FIXTURES_DIR, "v2": FIXTURES_DIR_V2}


def agent_launch(script_name: str, *, version: str = "v1", **overrides: object) -> AgentLaunch:
    """Build an `AgentLaunch` for `tests/fixtures/agents/<version>/<script_name>`, run with the
    same interpreter pytest is running under. `version` defaults to `"v1"` so every existing
    call site (none of which pass it) keeps building a v1 fixture's `AgentLaunch` exactly as
    before; pass `version="v2"` for a `tests/fixtures/agents/v2/<script_name>` fixture."""
    fixtures_dir = _FIXTURES_DIR_BY_VERSION[version]
    kwargs: dict[str, object] = {
        "command": [sys.executable, str(fixtures_dir / script_name)],
        "startup_timeout": 2.0,
        "default_timeout": 2.0,
    }
    kwargs.update(overrides)
    return AgentLaunch(**kwargs)  # type: ignore[arg-type]
