#!/usr/bin/env python3
"""Non-conforming fixture: exits 0 immediately without reading stdin at all.

Used to exercise `AgentExited` (EOF on stdout because the process is simply gone).
"""

import sys

sys.exit(0)
