"""Unit tests for `tck.common.version.VersionSpec`'s `agent_info_field`/`agent_capabilities_field`
mechanism: `tck.common.plugin._build_report` reads the `initialize` result's
agent-identity/capabilities keys via these two field names rather than
hard-coding v1's `agentInfo`/`agentCapabilities`, so v2's rename (`info`/`capabilities`) is
plumbed through without `common/` importing anything version-specific. End-to-end coverage of the
full JSON report for a real v2 run lives in `tests/v2/test_cli.py`; this file isolates the
mechanism itself against both real `SPEC` instances, without needing a live pytest run.
"""

from __future__ import annotations

from tck.common.version import VersionSpec
from tck.v1 import SPEC as V1_SPEC
from tck.v2 import SPEC as V2_SPEC


def test_version_spec_defaults_to_v1s_field_names() -> None:
    """A version package that doesn't pass `agent_info_field`/`agent_capabilities_field` at all
    (as `tck.v1.SPEC`'s construction call does not) defaults to v1's own field names."""
    spec = VersionSpec(
        protocol_version=1,
        schema_revision="deadbeef",
        schema_dir=V1_SPEC.schema_dir,
        registry={},
        initialize_params=lambda: {},
        conformance_package="tck.v1.conformance",
    )
    assert spec.agent_info_field == "agentInfo"
    assert spec.agent_capabilities_field == "agentCapabilities"


def test_v1_spec_reads_agentinfo_and_agentcapabilities() -> None:
    assert V1_SPEC.agent_info_field == "agentInfo"
    assert V1_SPEC.agent_capabilities_field == "agentCapabilities"


def test_v2_spec_reads_info_and_capabilities() -> None:
    assert V2_SPEC.agent_info_field == "info"
    assert V2_SPEC.agent_capabilities_field == "capabilities"


def _extract_agent_info_and_capabilities(spec: VersionSpec, result: dict) -> tuple[object, object]:
    """Mirrors the two lines in `tck.common.plugin._build_report` that read these fields off a
    cached `initialize` result."""
    return result.get(spec.agent_info_field), result.get(spec.agent_capabilities_field)


def test_report_extraction_reads_the_v1_shaped_keys_for_v1() -> None:
    result = {
        "agentInfo": {"name": "some-v1-agent", "version": "1.2.3"},
        "agentCapabilities": {"loadSession": True},
        # v2's keys, present but must NOT be picked up under the v1 spec:
        "info": {"name": "wrong"},
        "capabilities": {"session": {}},
    }
    info, capabilities = _extract_agent_info_and_capabilities(V1_SPEC, result)
    assert info == {"name": "some-v1-agent", "version": "1.2.3"}
    assert capabilities == {"loadSession": True}


def test_report_extraction_reads_the_v2_shaped_keys_for_v2() -> None:
    result = {
        # v1's keys, present but must NOT be picked up under the v2 spec:
        "agentInfo": {"name": "wrong"},
        "agentCapabilities": {"loadSession": True},
        "info": {"name": "some-v2-agent", "version": "0.0.0"},
        "capabilities": {"session": {}},
    }
    info, capabilities = _extract_agent_info_and_capabilities(V2_SPEC, result)
    assert info == {"name": "some-v2-agent", "version": "0.0.0"}
    assert capabilities == {"session": {}}
