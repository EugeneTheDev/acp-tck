# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = [
#     "agent-client-protocol==1.0.0rc2",
# ]
# ///
"""Minimal, conforming ACP v2 agent used to cross-check the TCK's v2 suite against the
upstream Python reference SDK's `acp.experimental.v2` runtime (there is no upstream v2 example
agent to reuse, unlike v1's `examples/echo_agent.py` -- see `.agents/research/reference-sdks-v2-status.md`).

Implements the full 7-method v2 session baseline (`session/new`, `session/list`,
`session/resume`, `session/close`, `session/prompt`, `session/cancel`, plus the
`session/update` notifications a prompt turn sends) rather than just the `new`/`prompt`/`cancel`
subset a literal reading of the task might suggest: advertising `capabilities.session` (even
`{}`) commits an agent to that whole baseline (`.agents/plan.md` "v2 initialize / capabilities /
baseline"), so a stub that only implemented new/prompt/cancel would self-inflict FAILs on the
CAPABILITY-tier ACP-LIST-2xx/ACP-RESUME-2xx/ACP-CLOSE-2xx families instead of leaving them a
clean, honest FAIL/PASS signal about the *reference SDK*.

Deliberately does NOT advertise `capabilities.session.delete` or
`capabilities.session.additionalDirectories` -- those are separately-gated sub-capabilities this
fixture does not implement, so the corresponding tests SKIP (not advertised) rather than FAIL.

Cancellation: a prompt whose sole text block is exactly "wait_for_cancel" withholds its
`idle` state update until `session/cancel` arrives (or a generous internal fallback elapses),
mirroring the v1 fixture catalogue's `__hang__` convention and the `--cancel-prompt
wait_for_cancel` value `scripts/cross-check.sh` already uses for the Rust v2 leg.
"""

import asyncio
from typing import Any
from uuid import uuid4

from acp.experimental.v2 import run_agent
from acp.experimental.v2.interfaces import Client
from acp.experimental.v2.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AudioContentBlock,
    CloseSessionResponse,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    Implementation,
    InitializeResponse,
    ImageContentBlock,
    ListSessionsResponse,
    NewSessionResponse,
    OtherContentBlock,
    AcpMcpServer,
    PromptResponse,
    ResourceContentBlock,
    ResumeSessionResponse,
    RunningSessionStateUpdate,
    SessionCapabilities,
    SessionInfo,
    StdioMcpServer,
    IdleSessionStateUpdate,
    TextContentBlock,
    UserMessageUpdate,
)

# Internal fallback so a `wait_for_cancel` turn can't hang the process forever if
# `session/cancel` never arrives (e.g. the TCK's own watchdog fires first and just kills the
# process anyway) -- well above any --timeout/--test-timeout a real cross-check run would use.
_CANCEL_FALLBACK_SECONDS = 60.0


class V2CrossCheckAgent:
    def __init__(self) -> None:
        self._conn: Client | None = None
        # session_id -> {"cwd": str, "additional_directories": list[str] | None}
        self._sessions: dict[str, dict[str, Any]] = {}
        # session_id -> asyncio.Event, set by cancel_session() for a turn currently in flight
        self._cancel_events: dict[str, asyncio.Event] = {}

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        info: Implementation,
        capabilities: Any = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=protocol_version,
            info=Implementation(name="python-v2-cross-check-agent", version="0.1.0"),
            capabilities=AgentCapabilities(session=SessionCapabilities()),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | AcpMcpServer | StdioMcpServer] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        session_id = uuid4().hex
        self._sessions[session_id] = {"cwd": cwd, "additional_directories": additional_directories}
        return NewSessionResponse(session_id=session_id)

    async def list_sessions(self, cwd: str | None = None, cursor: str | None = None, **kwargs: Any) -> ListSessionsResponse:
        infos = [
            SessionInfo(session_id=sid, cwd=data["cwd"], additional_directories=data.get("additional_directories"))
            for sid, data in self._sessions.items()
            if cwd is None or data["cwd"] == cwd
        ]
        return ListSessionsResponse(sessions=infos)

    async def resume_session(
        self,
        session_id: str,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | AcpMcpServer | StdioMcpServer] | None = None,
        replay_from: Any = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse:
        # No history is retained (no config options either); a resumed session is simply
        # re-registered so later session/prompt or session/close calls against it still work.
        self._sessions[session_id] = {"cwd": cwd, "additional_directories": additional_directories}
        return ResumeSessionResponse()

    async def close_session(self, session_id: str, **kwargs: Any) -> CloseSessionResponse:
        self._sessions.pop(session_id, None)
        event = self._cancel_events.get(session_id)
        if event is not None:
            event.set()
        return CloseSessionResponse()

    async def prompt(
        self,
        session_id: str,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
            | OtherContentBlock
        ],
        **kwargs: Any,
    ) -> PromptResponse:
        message_id = uuid4().hex
        asyncio.create_task(self._run_turn(session_id, message_id, prompt))
        return PromptResponse(message_id=message_id)

    async def cancel_session(self, session_id: str, **kwargs: Any) -> None:
        event = self._cancel_events.get(session_id)
        if event is not None:
            event.set()

    async def _run_turn(self, session_id: str, message_id: str, prompt: list[Any]) -> None:
        assert self._conn is not None
        conn = self._conn

        texts = [block.text for block in prompt if isinstance(block, TextContentBlock)]
        cancel_requested = texts == ["wait_for_cancel"]

        event = asyncio.Event()
        self._cancel_events[session_id] = event
        try:
            # ContentChunk's docstring (and ACP-PROMPT-203) require the agent to echo the
            # inserted user message, identified by the same messageId session/prompt's own
            # response carries, at some point during the turn -- a full-message update (not
            # chunked) is sufficient since the whole prompt is already available up front.
            await conn.session_update(
                session_id=session_id,
                update=UserMessageUpdate(message_id=message_id, content=prompt),
            )
            await conn.session_update(session_id=session_id, update=RunningSessionStateUpdate())

            cancelled = False
            if cancel_requested:
                try:
                    await asyncio.wait_for(event.wait(), timeout=_CANCEL_FALLBACK_SECONDS)
                    cancelled = True
                except asyncio.TimeoutError:
                    cancelled = False
            else:
                for text in texts:
                    if event.is_set():
                        cancelled = True
                        break
                    await conn.session_update(
                        session_id=session_id,
                        update=AgentMessageChunk(message_id=message_id, content=TextContentBlock(text=text)),
                    )
                cancelled = cancelled or event.is_set()

            await conn.session_update(
                session_id=session_id,
                update=IdleSessionStateUpdate(stop_reason="cancelled" if cancelled else "end_turn"),
            )
        finally:
            self._cancel_events.pop(session_id, None)


async def main() -> None:
    await run_agent(V2CrossCheckAgent())


if __name__ == "__main__":
    asyncio.run(main())
