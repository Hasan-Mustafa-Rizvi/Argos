"""Argos's voice: three fixed lines, spoken with ElevenLabs, cached on disk.

Each line is fetched once (raw 16-bit mono PCM at 16 kHz, `pcm_16000`) and kept in
`ARGOS_CACHE_DIR/voice`, outside the repo's tracked files, so a demo with no network still
speaks. Cached audio is of Argos's fixed lines only: never of the person.

Through the robot's speaker when the robot is attached, otherwise the machine's own.
With no key, no network and nothing cached, the line is logged, the sensor board beeps if it
has a buzzer, and the brain carries on. Speaking marks the gate so the ears do not listen.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from argos import text
from argos.clock import Clock

log = logging.getLogger("argos.voice")

RATE = 16000
FORMAT = "pcm_16000"
LINES = {
    "ask": text.ASK_LINE,
    "stood_down": "Okay. I'm glad you're alright. I'm right here.",
    "escalate": "I'm letting your family know now. Help is coming.",
}
TAIL_S = 0.4  # keep the ears closed a little after the line ends (room echo)


class TextToSpeech(Protocol):
    def synthesize(self, line: str) -> bytes: ...


class VoiceRefused(RuntimeError):
    """ElevenLabs answered with an error status."""

    def __init__(self, status: int) -> None:
        super().__init__(f"ElevenLabs answered HTTP {status}")
        self.status = status


class ElevenLabs:
    """POST /v1/text-to-speech/{voice_id}?output_format=pcm_16000 with the `xi-api-key`
    header. Plain HTTP: one request, no SDK that reads the key at import time."""

    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, api_key: str, voice_id: str, model: str, timeout_s: float = 15.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.voice_id = voice_id
        self.model = model
        self._client = httpx.Client(headers={"xi-api-key": api_key}, timeout=timeout_s,
                                    transport=transport)

    def synthesize(self, line: str) -> bytes:
        response = self._client.post(
            self.URL.format(voice_id=self.voice_id),
            params={"output_format": FORMAT},
            json={"text": line, "model_id": self.model},
        )
        if response.status_code != 200:
            raise VoiceRefused(response.status_code)
        if len(response.content) < 2:
            raise RuntimeError("ElevenLabs sent no audio")
        return response.content


class Speaker(Protocol):
    def play(self, pcm: bytes, rate: int) -> None: ...


class SoundDeviceSpeaker:
    def __init__(self, device: int | str | None) -> None:
        self.device = device

    def play(self, pcm: bytes, rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2")
        sd.play(samples, samplerate=rate, device=self.device, blocking=True)


class Voice:
    def __init__(
        self,
        clock: Clock,
        cache_dir: Path,
        tts: TextToSpeech | None,
        speaker: Speaker | None,
        cache_key: str = "",
        gate: Any = None,
        beep: Callable[[int], bool] = lambda ms: False,
        threaded: bool = True,
    ) -> None:
        self.clock = clock
        self.cache_dir = cache_dir
        self.tts = tts
        self.speaker = speaker
        self.cache_key = cache_key
        self.gate = gate
        self.beep = beep
        self.threaded = threaded
        self._memory: dict[str, bytes] = {}
        self._jobs: queue.Queue[tuple[str, Callable[[], None] | None,
                                      Callable[[bool], None] | None]] = queue.Queue()
        self._warned: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if threaded:
            self._thread = threading.Thread(target=self._run, name="argos-voice", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------ audio

    def _path(self, line: str) -> Path:
        digest = hashlib.sha256(f"{self.cache_key}|{FORMAT}|{line}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{digest}.pcm"

    def cache_path(self, key: str) -> Path:
        """Where the line `key` is kept on disk once fetched."""
        return self._path(LINES[key])

    def audio(self, key: str) -> bytes | None:
        """The line's audio: from memory, from the disk cache, or fetched once and cached."""
        line = LINES[key]
        if key in self._memory:
            return self._memory[key]
        path = self._path(line)
        if path.exists():
            data = path.read_bytes()
            self._memory[key] = data
            return data
        if self.tts is None:
            return None
        try:
            data = self.tts.synthesize(line)
        except Exception as exc:
            self._warn(f"fetch-{key}", f"could not fetch the line {line!r} ({exc})")
            return None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            self._warn("cache", f"voice cache not writable ({exc}); keeping lines in memory")
        self._memory[key] = data
        return data

    def prefetch(self) -> None:
        """Fetch every line now, on the voice thread, so the first check speaks at once."""
        for key in LINES:
            self._jobs.put((f"fetch:{key}", None, None))

    # ------------------------------------------------------------------ speaking

    def say(self, key: str, on_done: Callable[[], None] | None = None,
            on_spoken: Callable[[bool], None] | None = None) -> str:
        """Queue a line. `on_spoken` is told whether it was really spoken (False when there
        was no audio or no speaker and a beep went out instead, or nothing), then `on_done`
        runs. Returns the line's text, which is what goes into the `asked` event."""
        if self.threaded:
            self._jobs.put((key, on_done, on_spoken))
        else:
            self._speak(key, on_done, on_spoken)
        return LINES[key]

    def _speak(self, key: str, on_done: Callable[[], None] | None,
               on_spoken: Callable[[bool], None] | None = None) -> None:
        spoken = False
        try:
            pcm = self.audio(key)
            if pcm and self.speaker is not None:
                seconds = len(pcm) / 2 / RATE
                if self.gate is not None:
                    self.gate.speaking_until = self.clock.now() + seconds + TAIL_S + 1.0
                try:
                    self.speaker.play(pcm, RATE)
                    spoken = True
                except Exception as exc:
                    self._warn("speaker", f"speaker failed ({exc})")
                    self.beep(300)
                finally:
                    if self.gate is not None:
                        self.gate.speaking_until = self.clock.now() + TAIL_S
            else:
                why = "no speaker" if pcm else "no voice key, no network, and nothing cached"
                self._warn(f"silent-{key}", f"cannot speak {LINES[key]!r}: {why}")
                self.beep(300)
        finally:
            if on_spoken is not None:
                on_spoken(spoken)
            if on_done is not None:
                on_done()

    def _warn(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning("%s; carrying on", message)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                key, on_done, on_spoken = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            if key.startswith("fetch:"):
                self.audio(key.removeprefix("fetch:"))
                continue
            self._speak(key, on_done, on_spoken)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
