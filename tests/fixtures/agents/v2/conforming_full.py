#!/usr/bin/env python3
"""Conforming fixture that advertises every V2-2b-relevant capability and asks for permission on
every turn: `capabilities.session.prompt.{image,audio,embeddedContext}` (ACP-PROMPTCAP-001/002/
003) plus the plain `session: {}` baseline. Built on `AsksPermissionAgent`, so every turn also
exercises `ACP-PERM-201`'s permission-request shape.

Slice V2-4 adds `capabilities.session.delete`/`additionalDirectories`/`mcp: {stdio, http}` and
one `select`-type `configOptions` entry (`_base.ConformingAgent`'s `config_options` param) --
every new V2-4 CAPABILITY/INFORMATIONAL id this fixture's capabilities advertise must PASS (see
`tests/v2/test_cli.py`).

Must PASS every V2-2b id: PROMPTCAP-001/002/003 (this fixture never rejects any content block
type), PROMPT-003 (accepts `resource_link` too), PERM-201 (every turn asks permission with a
well-formed request, and the turn still reaches idle once answered), CLIENTCAP-201/202 (never
calls `elicitation/create` or any undefined method), and the two INFORMATIONAL probes (which
never assert on their own outcome, but still require the handshake itself to succeed).

Slice V2-5 adds one `type: "agent"` auth method (`methodId: "tck"`) -- correctly implements
`auth/login`/`auth/logout` via `_base.ConformingAgent`, but does not set `require_auth`, so
`session/new` never actually gates on it. Must PASS every V2-5 id -- ACP-AUTH-201/202/205/206
unconditionally, ACP-AUTH-204 when run with `--auth-method tck`, ACP-AUTH-203 when additionally
run with `--allow-logout` (SKIPs, not FAILs, when either flag is omitted). ACP-AUTH-207 SKIPs
here regardless of flags: this fixture advertises no `type: "terminal"` method at all.
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
    ).run()


if __name__ == "__main__":
    main()
