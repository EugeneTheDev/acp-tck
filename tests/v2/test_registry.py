"""Meta-tests over `tck.v2.requirements.REGISTRY`: shape invariants, plus a two-way check against
every `@pytest.mark.requirement(...)` used under `src/tck/v2/conformance/` (import the modules
and inspect `pytestmark` directly -- no grep). Mirrors `tests/v1/test_registry.py`, scaled down
to this skeleton slice's two-requirement registry.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

from tck.common.requirements import Tier
from tck.v2.protocol import SCHEMA_REVISION
from tck.v2 import requirements as req_module
from tck.v2.requirements import REGISTRY

_ID_PATTERN = re.compile(r"^ACP-[A-Z]+(?:-[A-Z]+)*-\d{3}$")
_SPEC_REVISION_PATTERN = re.compile(r"@ [0-9a-f]{40}$")


def test_ids_are_unique_and_well_formed():
    ids = list(REGISTRY)
    assert len(ids) == len(set(ids)), "duplicate requirement ids in REGISTRY"
    for req_id, requirement in REGISTRY.items():
        assert req_id == requirement.id
        assert _ID_PATTERN.match(req_id), f"{req_id!r} does not match ACP-<AREA>-<NNN>"


def test_registry_has_exactly_the_two_skeleton_requirements():
    """This slice's registry is deliberately minimal (see `tck.v2.requirements`'s module
    docstring): only the `initialize` handshake is covered so far."""
    assert set(REGISTRY) == {"ACP-INIT-001", "ACP-INIT-201"}


def test_capability_field_set_iff_capability_tier():
    for requirement in REGISTRY.values():
        if requirement.tier is Tier.CAPABILITY:
            assert requirement.capability, f"{requirement.id} is CAPABILITY but has no capability path"
        else:
            assert requirement.capability is None, (
                f"{requirement.id} is tier {requirement.tier.value}, not CAPABILITY, but has "
                f"capability={requirement.capability!r}"
            )


def test_text_and_citation_are_non_empty():
    for requirement in REGISTRY.values():
        assert requirement.text.strip(), f"{requirement.id} has empty text"
        assert requirement.citation.strip(), f"{requirement.id} has empty citation"
        assert requirement.source_report.strip(), f"{requirement.id} has empty source_report"


def test_citation_mentions_a_spec_revision_hash():
    for requirement in REGISTRY.values():
        assert _SPEC_REVISION_PATTERN.search(requirement.citation), (
            f"{requirement.id}'s citation does not end in '@ <40-hex-char spec revision>': "
            f"{requirement.citation!r}"
        )
        assert SCHEMA_REVISION in requirement.citation, (
            f"{requirement.id}'s citation is not pinned to tck.v2.protocol.SCHEMA_REVISION: "
            f"{requirement.citation!r}"
        )


def test_get_raises_helpful_key_error_for_unknown_id():
    with pytest.raises(KeyError, match="not a registered requirement id"):
        req_module.get("ACP-NOPE-999")


def test_get_returns_the_registered_requirement():
    any_id = next(iter(REGISTRY))
    assert req_module.get(any_id) is REGISTRY[any_id]


def _requirement_ids_used_in_conformance_tests() -> set[str]:
    import tck.v2.conformance as conformance_pkg

    used: set[str] = set()
    for module_info in pkgutil.iter_modules(conformance_pkg.__path__, conformance_pkg.__name__ + "."):
        leaf_name = module_info.name.rsplit(".", 1)[-1]
        if not leaf_name.startswith("test_"):
            continue
        module = importlib.import_module(module_info.name)
        for name, obj in vars(module).items():
            if not name.startswith("test_") or not callable(obj):
                continue
            for mark in getattr(obj, "pytestmark", []):
                if mark.name == "requirement":
                    used.update(mark.args)
    return used


def test_every_requirement_marker_id_exists_in_the_registry():
    used_ids = _requirement_ids_used_in_conformance_tests()
    unknown = used_ids - set(REGISTRY)
    assert not unknown, f"@pytest.mark.requirement id(s) not in REGISTRY: {sorted(unknown)}"


def test_every_registry_id_is_referenced_by_at_least_one_test():
    used_ids = _requirement_ids_used_in_conformance_tests()
    missing = set(REGISTRY) - used_ids
    assert not missing, f"REGISTRY id(s) with no @pytest.mark.requirement anywhere: {sorted(missing)}"
