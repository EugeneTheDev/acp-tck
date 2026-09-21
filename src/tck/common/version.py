"""`VersionSpec`: the one object a version package (`tck.v1`, later `tck.v2`) hands to
`tck.common.plugin` to make the plugin version-agnostic.

Before this, `tck.common.plugin` would have needed six separate injections -- the protocol
version, the schema revision, the schema directory, the active registry, the `initialize`
handshake params, and (for self-tests / diagnostics) which conformance package is running --
each read from a version-specific module (`common-v1-v2-split-analysis.md` P1/P2/P4/P8/P9/P10).
`VersionSpec` collapses all of that into a single `config.stash[VERSION_SPEC_KEY]` lookup: each
version package builds exactly one instance (e.g. `tck.v1.SPEC`) and its `plugin.py` shim stashes
it in `pytest_configure`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .requirements import Requirement


@dataclass(frozen=True)
class VersionSpec:
    """Everything `tck.common.plugin` needs to know about one ACP protocol version."""

    protocol_version: int
    schema_revision: str
    schema_dir: Path
    registry: dict[str, Requirement]
    initialize_params: Callable[[], dict[str, Any]]
    """Returns the `params` object for this version's `initialize` request (e.g.
    `{"protocolVersion": 1, "clientCapabilities": {}}` for v1)."""
    conformance_package: str
    """Dotted module path of this version's conformance suite package (e.g.
    `"tck.v1.conformance"`), for self-tests and diagnostics that need to name it."""
    agent_info_field: str = "agentInfo"
    """The `initialize` result key holding the agent's own `Implementation`-shaped info, read by
    `tck.common.plugin._build_report` for the JSON report's `agent_info` field. v1's key is
    `"agentInfo"` (the default, so `tck.v1.SPEC`'s existing construction call -- which does not
    pass this kwarg -- keeps behaving exactly as before); v2 renamed the field to `"info"` and
    passes that explicitly."""
    agent_capabilities_field: str = "agentCapabilities"
    """Like `agent_info_field`, but for the agent's advertised capabilities object. v1's key is
    `"agentCapabilities"` (the default); v2 renamed it to `"capabilities"`."""
