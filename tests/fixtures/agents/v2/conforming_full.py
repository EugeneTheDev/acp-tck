#!/usr/bin/env python3
"""Conforming fixture that advertises every capability the suite exercises and asks for
permission on every turn: `capabilities.session.prompt.{image,audio,embeddedContext}`
(ACP-PROMPTCAP-001/002/003), `session.delete`/`additionalDirectories`/`mcp: {stdio, http}`, plus
one `select`-type `configOptions` entry (`_base.ConformingAgent`'s `config_options` param), one
`type: "agent"` auth method (`methodId: "tck"`), and `emit_rich_turn_updates=True`. Built on
`AsksPermissionAgent`, so every turn also exercises `ACP-PERM-201`'s permission-request shape.

Must PASS every CAPABILITY/INFORMATIONAL id its advertised capabilities gate: PROMPTCAP-001/
002/003 (never rejects any content block type), PROMPT-003 (accepts `resource_link` too),
PERM-201 (every turn asks permission with a well-formed request, and still reaches idle once
answered), CLIENTCAP-201/202 (never calls `elicitation/create` or any undefined method), the two
INFORMATIONAL probes (never assert on their own outcome, but still require the handshake to
succeed), and every new session-management/config/MCP capability id (see `tests/v2/test_cli.py`).

The `tck` auth method correctly implements `auth/login`/`auth/logout` via
`_base.ConformingAgent`, but does not set `require_auth`, so `session/new` never actually gates
on it. Must PASS ACP-AUTH-201/202/205/206 unconditionally, ACP-AUTH-204 when run with
`--auth-method tck`, ACP-AUTH-203 when additionally run with `--allow-logout` (SKIPs, not FAILs,
when either flag is omitted). ACP-AUTH-207 SKIPs regardless of flags: this fixture advertises no
`type: "terminal"` method at all.

`emit_rich_turn_updates=True` makes every turn also emit a two-chunk agent message (one
`messageId`), a `tool_call_update` create+patch pair (one `toolCallId`), and a `plan_update` (one
`planId`) -- see `_base.ConformingAgent._send_rich_turn_updates`. This is what lets the
PATCH-20x/ENUM-201 rows PASS on this fixture instead of SKIPping "no <variant> observed". It also
emits one `terminal_update` + one `terminal_output_chunk` per turn, so `ACP-PATCH-206`/
`ACP-PATCH-207` PASS too instead of SKIPping.

`terminal_auth_method` gives `ACP-AUTH-207`'s dedicated `capabilities.auth.terminal: {}`
connection a well-formed `type: "terminal"` descriptor to see (`ACP-AUTH-202` still PASSes: the
default connection this fixture also answers under advertises no `auth.terminal` capability, so
the descriptor never appears there). Together these bring this fixture to 101/106 PASS (5 SKIP:
`ACP-CANCEL-204`, `ACP-BATCH-206/207/208` -- never exercised by a single driven turn -- and
`ACP-AUTH-205`, which only applies to a connection with *no* `authMethods` at all, the opposite
of this fixture's own).
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
