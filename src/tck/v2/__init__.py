"""`tck.v2`: the ACP v2 (Draft) package -- protocol constants, vendored schema, requirement
registry, schema validation, the v2 pytest plugin shim, and the v2 conformance suite.

Exports `SPEC`, the `tck.common.version.VersionSpec` instance that `tck.v2.plugin` stashes for
`tck.common.plugin` to read (mirrors `tck.v1.__init__`).
"""

from __future__ import annotations

from typing import Any

from ..common.version import VersionSpec
from .protocol import PROTOCOL_VERSION, SCHEMA_DIR, SCHEMA_REVISION
from .requirements import REGISTRY


def _initialize_params() -> dict[str, Any]:
    """`params` for v2's `initialize` request: unlike v1, `info` is required on *both* sides,
    and the capabilities field is named `capabilities` (not `clientCapabilities`)."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "info": {"name": "acp-tck", "version": _tck_version()},
        "capabilities": {},
    }


def _tck_version() -> str:
    from ..common.report import current_tck_version

    return current_tck_version()


SPEC = VersionSpec(
    protocol_version=PROTOCOL_VERSION,
    schema_revision=SCHEMA_REVISION,
    schema_dir=SCHEMA_DIR,
    registry=REGISTRY,
    initialize_params=_initialize_params,
    conformance_package="tck.v2.conformance",
    agent_info_field="info",
    agent_capabilities_field="capabilities",
)
