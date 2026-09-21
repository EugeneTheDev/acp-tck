"""Prompt content capabilities: `image`, `audio`, `embeddedContext`
(ACP-PROMPTCAP-001/002/003).

Each is a boolean gate under `agentCapabilities.promptCapabilities` (`_tck_capability_gate`,
`boolean=True`). Per the research's "must NOT" list, this module does not test rejection of an
*unadvertised* content type -- agent-side behavior for that case is undefined by the spec.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pytest

from tck.v1.protocol import STOP_REASONS

from ._helpers import connected_agent, new_session, run_prompt


def _tiny_png_base64() -> str:
    """A minimal valid 1x1 white PNG, built at runtime (not a hardcoded blob) so the bytes are
    self-evidently a real, decodable PNG rather than an opaque fixture nobody can verify."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, truecolor
    raw_scanline = b"\x00" + b"\xff\xff\xff"  # filter byte + one white RGB pixel
    idat = zlib.compress(raw_scanline)
    png_bytes = signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
    return base64.b64encode(png_bytes).decode("ascii")


def _tiny_wav_base64() -> str:
    """A minimal valid 8-sample, mono, 8-bit PCM WAV file, built at runtime."""
    samples = bytes([128] * 8)  # silence
    data_chunk = b"data" + struct.pack("<I", len(samples)) + samples
    fmt_chunk = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
    riff_body = b"WAVE" + fmt_chunk + data_chunk
    wav_bytes = b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body
    return base64.b64encode(wav_bytes).decode("ascii")


@pytest.mark.requirement("ACP-PROMPTCAP-001")
@pytest.mark.capability("agentCapabilities.promptCapabilities.image", boolean=True)
async def test_prompt_with_image_block_resolves(agent_launch, tmp_path):
    """ACP-PROMPTCAP-001."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        blocks = [
            {"type": "text", "text": "describe this image"},
            {"type": "image", "data": _tiny_png_base64(), "mimeType": "image/png"},
        ]
        turn = await run_prompt(agent, session_id, blocks, timeout=agent_launch.default_timeout)
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/prompt with an image block did not succeed: {turn.response_entry.text!r}"
        )
        stop_reason = msg["result"].get("stopReason")
        assert stop_reason in STOP_REASONS, f"unexpected stopReason: {stop_reason!r}"


@pytest.mark.requirement("ACP-PROMPTCAP-002")
@pytest.mark.capability("agentCapabilities.promptCapabilities.audio", boolean=True)
async def test_prompt_with_audio_block_resolves(agent_launch, tmp_path):
    """ACP-PROMPTCAP-002."""
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        blocks = [
            {"type": "text", "text": "describe this audio"},
            {"type": "audio", "data": _tiny_wav_base64(), "mimeType": "audio/wav"},
        ]
        turn = await run_prompt(agent, session_id, blocks, timeout=agent_launch.default_timeout)
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/prompt with an audio block did not succeed: {turn.response_entry.text!r}"
        )
        stop_reason = msg["result"].get("stopReason")
        assert stop_reason in STOP_REASONS, f"unexpected stopReason: {stop_reason!r}"


@pytest.mark.requirement("ACP-PROMPTCAP-003")
@pytest.mark.capability("agentCapabilities.promptCapabilities.embeddedContext", boolean=True)
async def test_prompt_with_embedded_resource_block_resolves(agent_launch, tmp_path):
    """ACP-PROMPTCAP-003."""
    resource_path = tmp_path / "context.txt"
    resource_path.write_text("some embedded context")
    async with connected_agent(agent_launch) as agent:
        session_id = await new_session(agent, tmp_path, timeout=agent_launch.default_timeout)
        blocks = [
            {"type": "text", "text": "use this context"},
            {
                "type": "resource",
                "resource": {
                    "uri": resource_path.as_uri(),
                    "text": "some embedded context",
                    "mimeType": "text/plain",
                },
            },
        ]
        turn = await run_prompt(agent, session_id, blocks, timeout=agent_launch.default_timeout)
        msg = turn.response_entry.parsed
        assert isinstance(msg, dict) and isinstance(msg.get("result"), dict), (
            f"session/prompt with a resource block did not succeed: {turn.response_entry.text!r}"
        )
        stop_reason = msg["result"].get("stopReason")
        assert stop_reason in STOP_REASONS, f"unexpected stopReason: {stop_reason!r}"
