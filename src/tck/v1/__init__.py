"""The ACP v1 conformance suite package: protocol constants, vendored schema, requirement
registry, schema validation, and the conformance tests themselves.

Exports `SPEC`, the `tck.common.version.VersionSpec` instance that `tck.v1.plugin` stashes for
`tck.common.plugin` to read.
"""

from __future__ import annotations

from typing import Any

from ..common.version import VersionSpec
from .protocol import PROTOCOL_VERSION, SCHEMA_DIR, SCHEMA_REVISION
from .requirements import REGISTRY


def _initialize_params() -> dict[str, Any]:
    return {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {}}


SPEC = VersionSpec(
    protocol_version=PROTOCOL_VERSION,
    schema_revision=SCHEMA_REVISION,
    schema_dir=SCHEMA_DIR,
    registry=REGISTRY,
    initialize_params=_initialize_params,
    conformance_package="tck.v1.conformance",
)
