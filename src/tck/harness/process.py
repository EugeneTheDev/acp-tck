"""A raw, asyncio-based NDJSON stdio client for driving an ACP agent subprocess.

Deliberately hand-rolled rather than built on the ACP Python SDK: the SDK's typed layer
cannot emit malformed traffic (wrong `jsonrpc`, missing `params`, non-JSON bytes, ...) and its
transport silently drops lines that fail to parse. This harness records everything, in both
directions, and never crashes on bad input -- crashing on bad input is what a conformance
suite is here to test *for*, not something it should be vulnerable to itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .transcript import Direction, TranscriptEntry


class AgentTimeout(Exception):
    """No matching line arrived from the agent within the deadline.

    Carries the transcript recorded so far so the caller can report exactly what did (or did
    not) happen before the timeout.
    """

    def __init__(self, message: str, transcript: list[TranscriptEntry]) -> None:
        super().__init__(message)
        self.transcript = list(transcript)


class AgentExited(Exception):
    """The agent's stdout hit EOF (process exited or closed stdout) while reading a line."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None,
        stderr: str,
        transcript: list[TranscriptEntry],
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr
        self.transcript = list(transcript)


@dataclass
class AgentLaunch:
    """Configuration for spawning the agent under test."""

    command: list[str]
    cwd: Path | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)
    """Applied on top of the inherited `os.environ` (Rust-SDK style: inherit, then overlay)."""
    startup_timeout: float = 5.0
    """Deadline for the first read after spawn; not enforced by this class itself, callers use
    it as the default `timeout` for their first `read_line`/`wait_for_*` call."""
    default_timeout: float = 5.0
    """Default per-read deadline used when a `timeout` argument is omitted."""


class AgentProcess:
    """Async context manager wrapping one agent subprocess over stdio.

    On POSIX the child is started in its own process group (`start_new_session=True`) so
    `close()` can terminate the whole group -- agents launched via wrapper scripts (`npx`,
    `uvx`, shell wrappers) do not always forward signals or exit reliably on stdin EOF.
    """

    def __init__(self, launch: AgentLaunch) -> None:
        self._launch = launch
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self.transcript: list[TranscriptEntry] = []
        self._pending: list[TranscriptEntry] = []
        self._stderr_chunks: list[bytes] = []
        self._stderr_task: asyncio.Task[None] | None = None
        self.exit_code: int | None = None
        self.exited_on_stdin_close: bool = False
        self._closed = False

    async def __aenter__(self) -> "AgentProcess":
        env = dict(os.environ)
        env.update(self._launch.env_overrides)
        self._process = await asyncio.create_subprocess_exec(
            *self._launch.command,
            cwd=str(self._launch.cwd) if self._launch.cwd is not None else None,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def _drain_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        while True:
            chunk = await self._process.stderr.read(4096)
            if not chunk:
                return
            self._stderr_chunks.append(chunk)

    def stderr_text(self) -> str:
        """Everything read from the agent's stderr so far (drained continuously in the
        background, so the child never blocks writing to it)."""
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def _record(self, direction: Direction, raw: bytes) -> TranscriptEntry:
        entry = TranscriptEntry.build(direction, raw, time.monotonic())
        self.transcript.append(entry)
        return entry

    # --- sending ---

    async def send_raw(self, line: bytes | str) -> None:
        """Write exactly `line` plus a single `\\n` to stdin. The caller controls everything,
        including deliberately malformed bytes -- this method never validates `line`."""
        assert self._process is not None and self._process.stdin is not None
        raw = line.encode("utf-8") if isinstance(line, str) else line
        self._record(Direction.SENT, raw)
        self._process.stdin.write(raw + b"\n")
        await self._process.stdin.drain()

    async def send_message(self, obj: dict[str, Any]) -> None:
        await self.send_raw(json.dumps(obj, separators=(",", ":")))

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None, *, id: Any = None
    ) -> Any:
        """Send a JSON-RPC request. Returns the `id` used: an auto-incrementing int unless
        `id` is given explicitly (which may be a string)."""
        if id is None:
            id = self._next_id
            self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": id, "method": method}
        if params is not None:
            message["params"] = params
        await self.send_message(message)
        return id

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self.send_message(message)

    # --- reading ---

    async def read_line(self, timeout: float | None = None) -> TranscriptEntry:
        """Read and record the next stdout line. Raises `AgentTimeout` if none arrives within
        the deadline, or `AgentExited` on EOF."""
        assert self._process is not None and self._process.stdout is not None
        deadline = timeout if timeout is not None else self._launch.default_timeout
        try:
            raw = await asyncio.wait_for(self._process.stdout.readline(), timeout=deadline)
        except asyncio.TimeoutError as exc:
            raise AgentTimeout(f"no stdout line within {deadline}s", self.transcript) from exc
        if raw == b"":
            exit_code = await self._wait_exit_after_eof()
            raise AgentExited(
                f"agent process exited while waiting for a line (exit_code={exit_code})",
                exit_code=exit_code,
                stderr=self.stderr_text(),
                transcript=self.transcript,
            )
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        entry = self._record(Direction.RECEIVED, raw)
        self._pending.append(entry)
        return entry

    async def _wait_exit_after_eof(self) -> int | None:
        assert self._process is not None
        try:
            return await asyncio.wait_for(self._process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            return None

    async def wait_for_message(
        self, predicate: Callable[[TranscriptEntry], bool], timeout: float | None = None
    ) -> TranscriptEntry:
        """Read lines until one satisfies `predicate`, or the overall deadline expires.

        Every line read while waiting is recorded in `transcript` and, unless it is the
        matched line, left in the `pending()` buffer for the caller to drain."""
        budget = timeout if timeout is not None else self._launch.default_timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AgentTimeout(f"no matching message within {budget}s", self.transcript)
            entry = await self.read_line(timeout=remaining)
            if predicate(entry):
                with contextlib.suppress(ValueError):
                    self._pending.remove(entry)
                return entry

    async def wait_for_response(self, id: Any, timeout: float | None = None) -> TranscriptEntry:
        """Read lines until the response whose `id` matches arrives."""
        return await self.wait_for_message(lambda entry: entry.matches_id(id), timeout=timeout)

    def pending(self) -> list[TranscriptEntry]:
        """Drain and return lines that arrived while waiting for something else (notifications,
        agent-to-client requests, ...) and were not themselves the awaited message."""
        drained = list(self._pending)
        self._pending.clear()
        return drained

    # --- teardown ---

    async def close(self, grace: float = 2.0) -> None:
        """Close stdin, wait `grace`; if still alive, SIGTERM the process group and wait
        `grace` again; if still alive, SIGKILL. Records `exit_code` and
        `exited_on_stdin_close`."""
        if self._process is None or self._closed:
            return
        self._closed = True
        proc = self._process

        if proc.stdin is not None and not proc.stdin.is_closing():
            with contextlib.suppress(Exception):
                proc.stdin.close()

        exited_on_stdin_close = await self._wait(proc, grace)
        self.exited_on_stdin_close = exited_on_stdin_close

        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            if not await self._wait(proc, grace):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()

        self.exit_code = proc.returncode

        if self._stderr_task is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._stderr_task, timeout=grace)

    @staticmethod
    async def _wait(proc: asyncio.subprocess.Process, timeout: float) -> bool:
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
