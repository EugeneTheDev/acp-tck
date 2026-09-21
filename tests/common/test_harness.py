"""Unit tests for `tck.common.harness` against the fixture agents in `tests/fixtures/agents/`.

Nothing here is an ACP conformance test -- it exercises the harness itself (framing,
transcripts, timeouts, termination) using deliberately conforming and non-conforming fixture
agents as stand-ins for a real agent under test.
"""

from __future__ import annotations

import asyncio

import pytest

from tck.common.harness import AgentExited, AgentProcess, AgentTimeout, Direction

from conftest import agent_launch


def run(coro):
    return asyncio.run(coro)


# --- initialize round-trip, id handling ---


def test_initialize_round_trip() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            req_id = await agent.send_request(
                "initialize", {"protocolVersion": 1, "clientCapabilities": {}}
            )
            entry = await agent.wait_for_response(req_id)
            assert entry.parsed["result"]["protocolVersion"] == 1
            assert entry.parsed["result"]["agentInfo"]["name"] == "tck-fixture-conforming"

    run(scenario())


def test_initialize_echoes_string_and_int_ids() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            int_id = await agent.send_request("initialize", {"protocolVersion": 1}, id=42)
            assert int_id == 42
            entry = await agent.wait_for_response(int_id)
            assert entry.parsed["id"] == 42

            str_id = await agent.send_request("initialize", {"protocolVersion": 1}, id="req-abc")
            assert str_id == "req-abc"
            entry = await agent.wait_for_response(str_id)
            assert entry.parsed["id"] == "req-abc"

    run(scenario())


def test_auto_increment_ids_are_unique_ints() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            first = await agent.send_request("initialize", {"protocolVersion": 1})
            second = await agent.send_request("initialize", {"protocolVersion": 1})
            assert isinstance(first, int) and isinstance(second, int)
            assert first != second

    run(scenario())


def test_unknown_method_returns_method_not_found() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            req_id = await agent.send_request("_tck/does_not_exist", {})
            entry = await agent.wait_for_response(req_id)
            assert entry.parsed["error"]["code"] == -32601

    run(scenario())


def test_malformed_raw_bytes_are_accepted_and_recorded() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            await agent.send_raw(b"not-json-at-all{{{")
            # The harness must not crash, and the connection must still work afterwards.
            req_id = await agent.send_request("initialize", {"protocolVersion": 1})
            entry = await agent.wait_for_response(req_id)
            assert entry.parsed["result"]["protocolVersion"] == 1

            sent_malformed = [
                e
                for e in agent.transcript
                if e.direction == Direction.SENT and e.raw == b"not-json-at-all{{{"
            ]
            assert len(sent_malformed) == 1

    run(scenario())


# --- transcript recording of non-conforming output ---


def test_banner_on_stdout_is_recorded_as_parse_error() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("banner_on_stdout.py")) as agent:
            first_entry = await agent.read_line()
            assert first_entry.direction == Direction.RECEIVED
            assert first_entry.parse_error is not None
            assert first_entry.text is not None
            assert "banner_on_stdout" in first_entry.text

            # The agent still behaves conformingly afterwards.
            req_id = await agent.send_request("initialize", {"protocolVersion": 1})
            entry = await agent.wait_for_response(req_id)
            assert entry.parsed["result"]["protocolVersion"] == 1

            # Nothing was dropped: both lines are in the full transcript, in order.
            received = [e for e in agent.transcript if e.direction == Direction.RECEIVED]
            assert received[0] is first_entry
            assert received[1].parsed["result"]["protocolVersion"] == 1

    run(scenario())


# --- timeouts and exits ---


def test_never_responds_raises_agent_timeout_with_transcript() -> None:
    async def scenario() -> None:
        # `never_responds.py` never exits on its own (SIGTERM/SIGKILL required), so teardown
        # would otherwise pay the full default 2s stdin-close grace period every run just to
        # prove the timeout fired; this test only cares that it fired (review-slices-5-6.md
        # item 10/S11 runtime, same fix as test_cli.py's watchdog self-test).
        async with AgentProcess(agent_launch("never_responds.py", close_grace=0.2)) as agent:
            req_id = await agent.send_request("initialize", {"protocolVersion": 1})
            with pytest.raises(AgentTimeout) as excinfo:
                await agent.wait_for_response(req_id, timeout=0.5)
            sent = [e for e in excinfo.value.transcript if e.direction == Direction.SENT]
            assert len(sent) == 1
            assert sent[0].parsed["method"] == "initialize"

    run(scenario())


def test_exits_immediately_raises_agent_exited_with_exit_code() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("exits_immediately.py")) as agent:
            with pytest.raises(AgentExited) as excinfo:
                await agent.read_line(timeout=2.0)
            assert excinfo.value.exit_code == 0

    run(scenario())


def test_send_raw_translates_broken_pipe_into_agent_exited() -> None:
    """S1 (review-slices-7.md): `dies_on_bad_json.py` answers `initialize` normally, then exits
    the instant it reads a line that is not valid JSON at all -- without replying, without
    draining anything further. A second write after that (here, a bare `send_raw` of another
    line) lands on a stdin pipe whose reader is already gone, so the OS raises
    `BrokenPipeError`/`OSError` on the write or the following `drain()`. Before the S1 fix this
    propagated as a bare `OSError`/`BrokenPipeError` with a real traceback; `send_raw` must catch
    it and raise `AgentExited` (carrying the exit code and captured stderr) instead."""

    async def scenario() -> None:
        async with AgentProcess(agent_launch("dies_on_bad_json.py")) as agent:
            init_id = await agent.send_request("initialize", {"protocolVersion": 1})
            await agent.wait_for_response(init_id, timeout=2.0)

            await agent.send_raw(b"{not valid json at all")
            # Give the fixture a moment to actually exit before hammering its stdin.
            for _ in range(40):
                if agent._process is not None and agent._process.returncode is not None:
                    break
                await asyncio.sleep(0.05)

            with pytest.raises(AgentExited) as excinfo:
                for _ in range(20):
                    await agent.send_raw(b'{"jsonrpc": "2.0", "id": 999, "method": "ping"}')
            assert excinfo.value.exit_code == 1

    run(scenario())


def test_stderr_chatter_captures_stderr() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("stderr_chatter.py")) as agent:
            req_id = await agent.send_request("initialize", {"protocolVersion": 1})
            await agent.wait_for_response(req_id)
            # Give the background stderr drain a moment to catch up.
            for _ in range(20):
                if agent.stderr_text():
                    break
                await asyncio.sleep(0.05)
            assert "stderr_chatter received" in agent.stderr_text()

    run(scenario())


# --- line-limit handling (review B1) ---


def test_large_line_under_generous_default_limit_is_read_whole() -> None:
    """A ~2 MB line is comfortably under the harness's 64 MiB default `max_line_bytes`, so it
    must come back whole, with no oversize marker, and the connection stays usable."""

    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            req_id = await agent.send_request("_tck/big", {"size": 2_000_000})
            entry = await agent.wait_for_response(req_id)
            assert entry.oversize is False
            assert len(entry.parsed["result"]["value"]) == 2_000_000

            # Connection still usable afterwards.
            init_id = await agent.send_request("initialize", {"protocolVersion": 1})
            init_entry = await agent.wait_for_response(init_id)
            assert init_entry.parsed["result"]["protocolVersion"] == 1

    run(scenario())


def test_line_beyond_lowered_limit_is_recovered_whole_and_marked_oversize() -> None:
    """With `max_line_bytes` deliberately lowered for the test, a line bigger than that limit
    must still come back with every byte intact (never truncated, never dropped) -- only marked
    `oversize=True` -- and the connection must remain usable for later requests."""

    async def scenario() -> None:
        launch = agent_launch("conforming.py", max_line_bytes=64 * 1024)
        async with AgentProcess(launch) as agent:
            req_id = await agent.send_request("_tck/big", {"size": 500_000})
            entry = await agent.wait_for_response(req_id)
            assert entry.oversize is True
            assert len(entry.parsed["result"]["value"]) == 500_000

            init_id = await agent.send_request("initialize", {"protocolVersion": 1})
            init_entry = await agent.wait_for_response(init_id)
            assert init_entry.oversize is False
            assert init_entry.parsed["result"]["protocolVersion"] == 1

    run(scenario())


# --- close() termination ladder ---


def test_close_on_conforming_agent_exits_cleanly_on_stdin_close() -> None:
    async def scenario() -> None:
        agent = AgentProcess(agent_launch("conforming.py"))
        async with agent:
            req_id = await agent.send_request("initialize", {"protocolVersion": 1})
            await agent.wait_for_response(req_id)
        assert agent.exited_on_stdin_close is True
        assert agent.exit_code == 0

    run(scenario())


def test_close_on_never_responds_kills_process() -> None:
    async def scenario() -> None:
        agent = AgentProcess(agent_launch("never_responds.py"))
        async with agent as a:
            await a.close(grace=0.3)
        assert agent.exited_on_stdin_close is False
        assert agent.exit_code is not None

    run(scenario())


# --- env override propagation ---


def test_env_override_is_visible_to_child() -> None:
    async def scenario() -> None:
        launch = agent_launch("conforming.py", env_overrides={"TCK_TEST_VAR": "hello-tck"})
        async with AgentProcess(launch) as agent:
            req_id = await agent.send_request("_tck/env", {"name": "TCK_TEST_VAR"})
            entry = await agent.wait_for_response(req_id)
            assert entry.parsed["result"]["value"] == "hello-tck"

    run(scenario())


# --- cancel flow ---


def test_cancel_flow_with_hang_prompt() -> None:
    async def scenario() -> None:
        async with AgentProcess(agent_launch("conforming.py")) as agent:
            init_id = await agent.send_request("initialize", {"protocolVersion": 1})
            await agent.wait_for_response(init_id)

            new_id = await agent.send_request(
                "session/new", {"cwd": "/tmp", "mcpServers": []}
            )
            new_entry = await agent.wait_for_response(new_id)
            session_id = new_entry.parsed["result"]["sessionId"]

            prompt_id = await agent.send_request(
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": "__hang__"}]},
            )

            # The update must arrive before we even ask for cancellation.
            update_entry = await agent.wait_for_message(
                lambda e: isinstance(e.parsed, dict) and e.parsed.get("method") == "session/update"
            )
            update_index = agent.transcript.index(update_entry)

            await agent.send_notification("session/cancel", {"sessionId": session_id})
            response_entry = await agent.wait_for_response(prompt_id)
            response_index = agent.transcript.index(response_entry)

            assert response_entry.parsed["result"]["stopReason"] == "cancelled"
            assert update_index < response_index

    run(scenario())
