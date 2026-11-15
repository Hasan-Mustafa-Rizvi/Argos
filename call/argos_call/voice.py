"""Argos's voice on the call: ElevenLabs, the same voice and model the brain speaks with.

The brain calls ElevenLabs over plain HTTP (`brain/argos/voice.py`) with `ELEVENLABS_VOICE_ID`
and `ELEVENLABS_MODEL` (default `eleven_flash_v2_5`); this does the same, so Argos sounds the
same on the call as in the room. The audio comes back as raw 16-bit mono PCM at 24 kHz, the
rate the agent's track runs at.

Rule 5: what is synthesised stays in memory. Unlike the brain, nothing is cached on disk.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

log = logging.getLogger("argos_call.voice")

FORMAT = "pcm_24000"
RATE = 24000


class Speech(Protocol):
    async def synthesize(self, line: str) -> bytes: ...


class ElevenLabs:
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, api_key: str, voice_id: str, model: str, timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.voice_id = voice_id
        self.model = model
        self._client = httpx.AsyncClient(headers={"xi-api-key": api_key}, timeout=timeout_s,
                                         transport=transport)

    async def synthesize(self, line: str) -> bytes:
        return await self.synthesize_at(line, RATE)

    async def synthesize_at(self, line: str, rate: int) -> bytes:
        try:
            response = await self._client.post(
                self.URL.format(voice_id=self.voice_id),
                params={"output_format": f"pcm_{rate}"},
                json={"text": line, "model_id": self.model},
            )
        except httpx.HTTPError as exc:
            raise VoiceError(f"ElevenLabs did not answer ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise VoiceError(f"ElevenLabs answered HTTP {response.status_code}")
        if len(response.content) < 2:
            raise VoiceError("ElevenLabs sent no audio")
        return response.content[: len(response.content) - len(response.content) % 2]

    async def aclose(self) -> None:
        await self._client.aclose()


class VoiceError(Exception):
    """The line could not be synthesised. The message carries no key."""


def seconds(pcm: bytes) -> float:
    return len(pcm) / 2 / RATE
