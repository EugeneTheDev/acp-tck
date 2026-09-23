#!/usr/bin/env python3
"""Conforming fixture that advertises every capability the suite exercises and asks for
permission on every turn: `capabilities.session.prompt.{image,audio,embeddedContext}`,
`session.delete`/`additionalDirectories`/`mcp: {stdio, http}`, plus one `select`-type
`configOptions` entry (`_base.ConformingAgent`'s `config_options` param), one `type: "agent"`
auth method (`methodId: "tck"`), and `emit_rich_turn_updates=True`. Built on
`AsksPermissionAgent`, so every turn also exercises the permission-request shape. Must PASS every
CAPABILITY/INFORMATIONAL id its advertised capabilities gate (see `tests/v2/test_cli.py` for the
exact set).

The `tck` auth method correctly implements `auth/login`/`auth/logout` via
`_base.ConformingAgent`, but does not set `require_auth`, so `session/new` never actually gates
on it -- the `--auth-method`/`--allow-logout`-gated AUTH ids SKIP rather than FAIL when those
flags are omitted. ACP-AUTH-207 SKIPs regardless of flags: this fixture advertises no
`type: "terminal"` method at all.

`emit_rich_turn_updates=True` makes every turn also emit a two-chunk agent message, a
`tool_call_update` create+patch pair, a `plan_update`, and one `terminal_update` +
`terminal_output_chunk` pair (see `_base.ConformingAgent._send_rich_turn_updates`) -- this is what
lets the update-shape/enum tests PASS here instead of SKIPping "no <variant> observed".

`terminal_auth_method` gives ACP-AUTH-207's dedicated `capabilities.auth.terminal: {}`
connection a well-formed `type: "terminal"` descriptor to see (ACP-AUTH-202 still PASSes: the
default connection this fixture also answers under advertises no `auth.terminal` capability, so
the descriptor never appears there).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _base import AsksPermissionAgent  # noqa: E402


def main() -> None:
    AsksPermissionAgent(
        capabilities={
            "session": {
                "prompt": {"image": {}, "audio": {}, "embeddedContext": {}},
                "delete": {},
                "additionalDirectories": {},
                "mcp": {"stdio": {}, "http": {}},
            },
        },
        config_options=[
            {
                "configId": "verbosity",
                "name": "Verbosity",
                "type": "select",
                "currentValue": "normal",
                "options": [
                    {"value": "quiet", "name": "Quiet"},
                    {"value": "normal", "name": "Normal"},
                    {"value": "verbose", "name": "Verbose"},
                ],
            },
        ],
        auth_methods=[
            {"methodId": "tck", "type": "agent", "name": "TCK"},
        ],
        terminal_auth_method={
            "methodId": "term",
            "type": "terminal",
            "name": "Terminal Login",
            "args": ["--login"],
            "env": [{"name": "TCK_TERMINAL_AUTH", "value": "1"}],
        },
        emit_rich_turn_updates=True,
    ).run()


if __name__ == "__main__":
    main()
