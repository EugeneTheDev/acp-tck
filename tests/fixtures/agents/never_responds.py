#!/usr/bin/env python3
"""Non-conforming fixture: reads stdin forever, never writes anything.

Used to exercise `AgentTimeout` (nothing ever arrives on stdout) and the harness's
close() termination ladder (it does not exit on stdin EOF, so SIGTERM/SIGKILL are needed).
"""

import sys
import time

for _ in sys.stdin:
    pass

# stdin is now closed (EOF), but a conforming shutdown would still require a signal per the
# harness's close() ladder -- this fixture deliberately never exits on its own.
while True:
    time.sleep(3600)
