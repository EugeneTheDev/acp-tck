#!/usr/bin/env python3
"""Non-conforming fixture: `session/set_config_option` returns only the changed entry instead of
the complete `configOptions` list. Advertises the same `select`-type `verbosity` option as
`conforming_full.py` *plus* a second, unrelated `boolean` option (`debug_mode`) -- a single
config option would make a "partial" reply indistinguishable from a "complete" one, since the
one changed entry would trivially be the whole list.

FAILs exactly `ACP-CONFIG-202` (the complete-list check: setting `verbosity` drops `debug_mode`
from the response). `ACP-CONFIG-201`/`203`/`204` (shape validity on `session/new`/
`session/resume`, and the select `currentValue` membership check) and `ACP-CONFIG-206` (vacuous
unless a `config_option_update` is separately observed, which this fixture never sends) are
unaffected. Mirrors v1's `config_partial_list.py`.
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _base import ConformingAgent  # noqa: E402

_VERBOSITY_OPTION = {
    "configId": "verbosity",
    "name": "Verbosity",
    "type": "select",
    "currentValue": "normal",
    "options": [
        {"value": "quiet", "name": "Quiet"},
        {"value": "normal", "name": "Normal"},
        {"value": "verbose", "name": "Verbose"},
    ],
}

_DEBUG_MODE_OPTION = {
    "configId": "debug_mode",
    "name": "Debug mode",
    "type": "boolean",
    "currentValue": False,
}


class ConfigPartialListAgent(ConformingAgent):
    def _handle_set_config_option(self, msg_id: Any, params: dict[str, Any]) -> None:
        config_id = params.get("configId")
        value = params.get("value")
        for option in self._config_options:
            if option.get("configId") == config_id:
                option["currentValue"] = value
                self._reply(msg_id, {"configOptions": [dict(option)]})
                return
        self._error(msg_id, -32602, "Invalid params: unknown configId")


def main() -> None:
    ConfigPartialListAgent(
        capabilities={"session": {}},
        config_options=[dict(_VERBOSITY_OPTION), dict(_DEBUG_MODE_OPTION)],
    ).run()


if __name__ == "__main__":
    main()
