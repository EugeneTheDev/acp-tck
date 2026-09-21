"""`tck.v1.plugin`: the pytest plugin for the ACP v1 conformance suite.

A thin shim over `tck.common.plugin` (see that module's docstring): it copies every hook and
fixture from `tck.common.plugin`'s namespace into its own -- including underscore-named autouse
fixtures (`_tck_capability_gate`, ...) that a plain `from ... import *` would silently skip,
since pytest discovers a plugin's hooks/fixtures via `dir()`/`vars()` on the plugin module
object itself, not on whatever re-exports are importable from it. It then overrides
`pytest_configure` to stash `tck.v1.SPEC` in `config.stash[VERSION_SPEC_KEY]` *before*
delegating to `tck.common.plugin.pytest_configure` -- every other common hook that reads the
stash (`pytest_collection_modifyitems`, `agent_initialize_result`, `pytest_sessionfinish`,
`pytest_terminal_summary`, ...) only ever runs after this has set it.

Always load this module, never `tck.common.plugin` directly (`-p tck.v1.plugin`, as done by the
`acp-tck` CLI and by hand when running `pytest src/tck/v1/conformance -p tck.v1.plugin ...`).
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
