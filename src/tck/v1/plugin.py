"""`tck.v1.plugin`: the pytest plugin for the ACP v1 conformance suite.

A thin shim over `tck.common.plugin`: copies every hook/fixture into this module's namespace via
`vars()`, not `import *`, so underscore-named autouse fixtures (`_tck_capability_gate`, ...)
aren't skipped -- pytest discovers a plugin's hooks/fixtures via `dir()`/`vars()` on the module
itself, not via re-exports. Then overrides `pytest_configure` to stash `tck.v1.SPEC` in
`config.stash[VERSION_SPEC_KEY]` before delegating to `tck.common.plugin.pytest_configure`,
since every other common hook reads that stash.

Always load via `-p tck.v1.plugin`, never `tck.common.plugin` directly.

Footgun: copied functions keep `__globals__` pointing at `tck.common.plugin`, so only a function
pytest resolves by name as a hook (like `pytest_configure`) can actually be overridden here --
redefining a plain helper (e.g. `_build_report`) would silently do nothing, since every copied
hook still calls the original.
"""

from __future__ import annotations

import pytest

from ..common import plugin as _common_plugin
from ..common.plugin import VERSION_SPEC_KEY
from . import SPEC

globals().update(
    {name: value for name, value in vars(_common_plugin).items() if not name.startswith("__")}
)


def pytest_configure(config: pytest.Config) -> None:
    config.stash[VERSION_SPEC_KEY] = SPEC
    _common_plugin.pytest_configure(config)
