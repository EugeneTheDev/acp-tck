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
    not) happen before the timeout -- and, for parity with `AgentExited`, whatever stderr had
    been captured by then (usually the most useful place a stuck agent explains itself).
    """

    def __init__(
        self, message: str, transcript: list[TranscriptEntry], *, stderr: str = ""
    ) -> None:
        super().__init__(message)
        self.transcript = list(transcript)
        self.stderr = stderr


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
    """Default per-read deadline used when a `timeout` argument is omitted. Also used as the
    deadline for `send_raw`'s `drain()` call."""
    max_line_bytes: int = 64 * 1024 * 1024
    """Buffer limit passed as `asyncio.create_subprocess_exec(limit=...)`. asyncio's own default
    (64 KiB) is far too small for real ACP traffic -- a `session/update` tool-call diff, an
    embedded image content block, or `fs/write_text_file` params routinely exceed it -- and
    `StreamReader.readline()` discards the buffered bytes and raises a bare `ValueError` when a
    line exceeds the limit. This default is generous enough that hitting it at all is itself
    informative; tests that want to exercise the oversize path on purpose lower it explicitly."""
    close_grace: float = 2.0
    """Passed as `AgentProcess.close()`'s `grace` argument on teardown (`__aexit__`). Each stage
    of the close ladder (stdin-close wait, post-SIGTERM wait, post-SIGKILL wait) budgets up to
    this many seconds, so a real agent gets a fair chance to shut down cleanly -- but a fixture
    that deliberately never exits (e.g. `never_responds.py`) pays the full amount just to prove
    that. Lowered via `--tck-close-grace` for self-tests that only care about a hang being
    caught, not about giving a real agent a generous shutdown window."""


class AgentProcess:
    """Async context manager wrapping one agent subprocess over stdio.

    On POSIX the child is started in its own process group (`start_new_session=True`) so
    `close()` can terminate the whole group -- agents launched via wrapper scripts (`npx`,
    `uvx`, shell wrappers) do not always forward signals or exit reliably on stdin EOF.
    """

    _STDERR_CAP_BYTES = 64 * 1024
    """Bounded tail kept of the agent's stderr (Rust-SDK style) -- a chatty agent under a long
    `--timeout` must not grow this without bound."""

    def __init__(self, launch: AgentLaunch) -> None:
        self._launch = launch
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self.transcript: list[TranscriptEntry] = []
        self._pending: list[TranscriptEntry] = []
        self._stderr_buffer = bytearray()
        self._stderr_truncated_bytes = 0
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
            limit=self._launch.max_line_bytes,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close(grace=self._launch.close_grace)

    async def _drain_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        while True:
            chunk = await self._process.stderr.read(4096)
            if not chunk:
                return
            self._stderr_buffer.extend(chunk)
            overflow = len(self._stderr_buffer) - self._STDERR_CAP_BYTES
            if overflow > 0:
                self._stderr_truncated_bytes += overflow
                del self._stderr_buffer[:overflow]

    def stderr_text(self) -> str:
        """Everything read from the agent's stderr so far (drained continuously in the
        background, so the child never blocks writing to it), tailed to the last
        `_STDERR_CAP_BYTES`."""
        text = bytes(self._stderr_buffer).decode("utf-8", errors="replace")
        if self._stderr_truncated_bytes:
            return f"...[truncated {self._stderr_truncated_bytes} earlier byte(s)]...\n{text}"
        return text

    def _record(self, direction: Direction, raw: bytes, *, oversize: bool = False) -> TranscriptEntry:
        entry = TranscriptEntry.build(direction, raw, time.monotonic(), oversize=oversize)
        self.transcript.append(entry)
        return entry

    # --- sending ---

    async def send_raw(self, line: bytes | str) -> None:
        """Write exactly `line` plus a single `\\n` to stdin. The caller controls everything,
        including deliberately malformed bytes -- this method never validates `line`.

        `drain()` is given a deadline (`default_timeout`): an agent that has stopped reading
        stdin must not be able to hang the whole run forever. If the agent has already exited,
        `write()`/`drain()` raise a plain `OSError` (`ConnectionResetError`/`BrokenPipeError` on
        POSIX) -- that is translated into `AgentExited` here so every caller sees the same "the
        agent is gone" exception it already handles for a closed stdout, instead of a raw
        asyncio traceback."""
        assert self._process is not None and self._process.stdin is not None
        raw = line.encode("utf-8") if isinstance(line, str) else line
        self._record(Direction.SENT, raw)
        try:
            self._process.stdin.write(raw + b"\n")
            await asyncio.wait_for(self._process.stdin.drain(), timeout=self._launch.default_timeout)
        except asyncio.TimeoutError as exc:
            raise AgentTimeout(
                f"stdin drain did not complete within {self._launch.default_timeout}s "
                "(the agent may have stopped reading stdin)",
                self.transcript,
                stderr=self.stderr_text(),
            ) from exc
        except OSError as exc:
            exit_code = await self._wait_exit_after_eof()
            raise AgentExited(
                f"agent process exited while writing to stdin ({exc})",
                exit_code=exit_code,
                stderr=self.stderr_text(),
                transcript=self.transcript,
            ) from exc

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

    async def _read_raw_line(self) -> tuple[bytes, bool]:
        """Read one line off stdout as raw bytes (without the trailing `\\n`), tolerating a line
        that overruns the stream's buffer limit.

        `StreamReader.readline()` turns a `LimitOverrunError` into a bare `ValueError` and
        discards the buffered bytes -- this harness must never lose bytes just because a line is
        large. Instead it recovers the buffered bytes with `readexactly` and keeps reading
        (marking the result `oversize=True`) until the real separator or EOF, so the full line is
        still captured.

        Returns `(raw, oversize)`. `raw == b"" and not oversize` means true EOF.
        """
        assert self._process is not None and self._process.stdout is not None
        stream = self._process.stdout
        chunks = bytearray()
        oversize = False
        max_total = max(self._launch.max_line_bytes * 4, 16 * 1024 * 1024)
        while True:
            try:
                piece = await stream.readuntil(b"\n")
                chunks.extend(piece)
                break
            except asyncio.IncompleteReadError as exc:
                chunks.extend(exc.partial)
                break  # EOF -- whatever we got (possibly nothing) is the last partial line
            except asyncio.LimitOverrunError as exc:
                oversize = True
                chunks.extend(await stream.readexactly(exc.consumed))
                if len(chunks) >= max_total:
                    # Defensive cap: an agent that never terminates a line must not be able to
                    # grow this buffer without bound. Return what we have; the next read picks
                    # up wherever the stream is, which will look like garbage -- an oversize
                    # line this large is already a severe conformance failure either way.
                    break
        if chunks.endswith(b"\n"):
            del chunks[-1:]
        return bytes(chunks), oversize

    async def read_line(self, timeout: float | None = None) -> TranscriptEntry:
        """Read and record the next stdout line. Raises `AgentTimeout` if none arrives within
        the deadline, or `AgentExited` on EOF. A line that exceeds the stream's buffer limit is
        never dropped -- see `_read_raw_line` -- it comes back as a normal entry with
        `oversize=True`."""
        assert self._process is not None and self._process.stdout is not None
        deadline = timeout if timeout is not None else self._launch.default_timeout
        try:
            raw, oversize = await asyncio.wait_for(self._read_raw_line(), timeout=deadline)
        except asyncio.TimeoutError as exc:
            raise AgentTimeout(
                f"no stdout line within {deadline}s", self.transcript, stderr=self.stderr_text()
            ) from exc
        if raw == b"" and not oversize:
            exit_code = await self._wait_exit_after_eof()
            raise AgentExited(
                f"agent process exited while waiting for a line (exit_code={exit_code})",
                exit_code=exit_code,
                stderr=self.stderr_text(),
                transcript=self.transcript,
            )
        entry = self._record(Direction.RECEIVED, raw, oversize=oversize)
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
                raise AgentTimeout(
                    f"no matching message within {budget}s", self.transcript, stderr=self.stderr_text()
                )
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
        """Shutdown ladder: close stdin, then (if still alive) SIGTERM the process group, then
        SIGKILL. Each rung is capped at `grace` and skipped once the process has already
        exited, so a stdout-holding agent (the npx/uvx wrapper case) doesn't burn roughly
        2x`grace` before SIGTERM is even sent. Records `exit_code` and `exited_on_stdin_close`.

        Each rung first drains any already-buffered stdout (a short fixed deadline, not a
        second `grace` budget), so late output -- including a trailing partial line -- still
        lands in `transcript`. This never fails on lateness, only records it; judging whether
        it's conforming is the caller's job."""
        if self._process is None or self._closed:
            return
        self._closed = True
        proc = self._process

        if proc.stdin is not None and not proc.stdin.is_closing():
            with contextlib.suppress(Exception):
                proc.stdin.close()

        exited_on_stdin_close = await self._close_stage(proc, grace)
        self.exited_on_stdin_close = exited_on_stdin_close

        if not exited_on_stdin_close:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            if not await self._close_stage(proc, grace):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                await self._close_stage(proc, grace)

        self.exit_code = proc.returncode

        if self._stderr_task is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._stderr_task, timeout=grace)

    async def _close_stage(self, proc: asyncio.subprocess.Process, grace: float) -> bool:
        """One rung of the shutdown ladder: pick up whatever stdout is already sitting in the
        pipe (a short, fixed deadline -- just enough to catch already-buffered bytes, not a
        second full `grace` budget), then give the process the *entire* `grace` budget to exit
        on its own. Returns whether it did."""
        await self._drain_remaining_stdout(min(grace, 0.25))
        return await self._wait(proc, grace)

    async def _drain_remaining_stdout(self, timeout: float) -> None:
        """Read and record whatever is sitting in (or soon arrives on) stdout, until EOF or
        `timeout` elapses. Never raises -- a timeout here just means "nothing more showed up in
        time", which is a normal outcome, not a failure."""
        if self._process is None or self._process.stdout is None:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            try:
                raw, oversize = await asyncio.wait_for(self._read_raw_line(), timeout=remaining)
            except asyncio.TimeoutError:
                return
            if raw == b"" and not oversize:
                return  # EOF
            self._record(Direction.RECEIVED, raw, oversize=oversize)

    @staticmethod
    async def _wait(proc: asyncio.subprocess.Process, timeout: float) -> bool:
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
