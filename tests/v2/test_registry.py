"""Meta-tests over `tck.v2.requirements.REGISTRY`: shape invariants, plus a two-way check against
every `@pytest.mark.requirement(...)` used under `src/tck/v2/conformance/` (import the modules
and inspect `pytestmark` directly -- no grep). Mirrors `tests/v1/test_registry.py`.

Slice V2-1b expanded the registry from the two-requirement `initialize`-handshake skeleton to the
full `initialize`/`session/new` baseline covered so far (see `tck.v2.requirements`'s module
docstring for the id-namespacing decisions).
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


def test_registry_has_exactly_the_v2_1b_requirements():
    """This slice's registry covers the `initialize` handshake plus the `session/new` baseline
    (see `tck.v2.requirements`'s module docstring for the full id-namespacing rationale)."""
    assert set(REGISTRY) == {
        "ACP-INIT-001",
        "ACP-INIT-003",
        "ACP-INIT-201",
        "ACP-INIT-202",
        "ACP-INIT-203",
        "ACP-INIT-204",
        "ACP-SCHEMA-001",
        "ACP-SESSION-001",
        "ACP-SESSION-002",
    }


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


def test_cli_selftest_tier_sets_match_the_registry():
    """v2 twin of `tests/v1/test_registry.py::test_cli_selftest_tier_sets_match_the_registry`
    (review-v2-slices-0-1a.md finding 8): `tests/v2/test_cli.py` hand-maintains
    `_MANDATORY_IDS`/`_CAPABILITY_IDS`, which must mirror `REGISTRY`'s own `Tier` field exactly
    -- otherwise a tier misclassification could go unnoticed. `tests/v2` is a package (unlike
    `tests/v1`), so the sibling module is imported as `v2.test_cli`, not the bare `test_cli` v1
    uses -- see `AGENTS.md`'s `tests/v2/__init__.py` layout note."""
    import v2.test_cli as test_cli

    by_tier: dict[Tier, set[str]] = {tier: set() for tier in Tier}
    for req_id, requirement in REGISTRY.items():
        by_tier[requirement.tier].add(req_id)

    assert test_cli._MANDATORY_IDS == by_tier[Tier.MANDATORY], (
        test_cli._MANDATORY_IDS ^ by_tier[Tier.MANDATORY]
    )
    assert test_cli._CAPABILITY_IDS == by_tier[Tier.CAPABILITY], (
        test_cli._CAPABILITY_IDS ^ by_tier[Tier.CAPABILITY]
    )
