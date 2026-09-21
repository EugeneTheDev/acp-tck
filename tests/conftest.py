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


def agent_launch(script_name: str, **overrides: object) -> AgentLaunch:
    """Build an `AgentLaunch` for `tests/fixtures/agents/v1/<script_name>`, run with the same
    interpreter pytest is running under."""
    kwargs: dict[str, object] = {
        "command": [sys.executable, str(FIXTURES_DIR / script_name)],
        "startup_timeout": 2.0,
        "default_timeout": 2.0,
    }
    kwargs.update(overrides)
    return AgentLaunch(**kwargs)  # type: ignore[arg-type]
