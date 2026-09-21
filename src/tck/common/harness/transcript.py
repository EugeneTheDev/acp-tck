"""The transcript entry recorded for every line sent to or read from an agent subprocess.

Kept deliberately dumb: `AgentProcess` never drops a line, even a malformed one, and never
raises while recording it. Decode/parse failures become fields on the entry instead of
exceptions, so a non-conforming agent's garbage output is always available for assertions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Direction(Enum):
    SENT = "sent"
    RECEIVED = "received"


@dataclass(frozen=True)
class TranscriptEntry:
    """One line of raw traffic, in either direction, as observed on the wire."""

    direction: Direction
    raw: bytes
    timestamp: float
    """`time.monotonic()` timestamp of when the line was sent or read."""
    text: str | None
    """UTF-8 decoded text, or `None` if decoding failed (see `text_error`)."""
    text_error: str | None
    """`repr()` of the `UnicodeDecodeError`, if `raw` was not valid UTF-8."""
    parsed: Any
    """The `json.loads` result, or `None` if parsing failed or `text` is `None`."""
    parse_error: str | None
    """`str()` of the `json.JSONDecodeError`, if `text` was not valid JSON."""
    oversize: bool = False
    """True if this line exceeded the harness's stream buffer limit (`AgentLaunch.max_line_bytes`)
    while being read. The full raw bytes are still recovered and recorded -- this harness never
    drops bytes just because a line is unexpectedly large -- but a line this big is itself worth
    flagging separately from an ordinary parse failure."""

    @staticmethod
    def build(
        direction: Direction, raw: bytes, timestamp: float, *, oversize: bool = False
    ) -> "TranscriptEntry":
        text: str | None = None
        text_error: str | None = None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            text_error = repr(exc)

        parsed: Any = None
        parse_error: str | None = None
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                parse_error = str(exc)

        return TranscriptEntry(
            direction=direction,
            raw=raw,
            timestamp=timestamp,
            text=text,
            text_error=text_error,
            parsed=parsed,
            parse_error=parse_error,
            oversize=oversize,
        )

    def matches_id(self, id_value: Any) -> bool:
        """True if this entry is a JSON-RPC response (has `id`, no `method`) for `id_value`."""
        if not isinstance(self.parsed, dict):
            return False
        if "method" in self.parsed:
            return False
        return "id" in self.parsed and self.parsed["id"] == id_value
