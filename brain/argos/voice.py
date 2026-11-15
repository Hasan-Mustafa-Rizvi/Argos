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
import subprocess
import sys
import threading
import time
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


def spread(samples: Any, channels: int) -> Any:
    """Mono samples as `channels` identical channels (at most two).

    The robot's sound card takes stereo only. Given a mono stream, the audio library fills the
    left channel and leaves the right one silent, and the robot's speaker then plays it so
    faintly that nobody heard it on the real robot. The same sound on both channels is heard."""
    import numpy as np

    if channels < 2:
        return samples
    return np.repeat(np.asarray(samples).reshape(-1, 1), 2, axis=1)


class SoundDeviceSpeaker:
    def __init__(self, device: int | str | None) -> None:
        self.device = device

    def play(self, pcm: bytes, rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2")
        try:
            channels = int(sd.query_devices(self.device, "output")["max_output_channels"])
        except Exception:
            channels = 1
        sd.play(spread(samples, channels), samplerate=rate, device=self.device, blocking=True)


PLAYBACK_START_S = 5.0  # starting Python and opening the card, on top of the line itself


class PlaybackFailed(RuntimeError):
    """The playback process did not play the line: it failed, died, or ran out of time."""


class ProcessSpeaker:
    """Plays each line in a process of its own (`argos.playback`), which the brain can afford
    to lose.

    On the real robot the sound card dropped off USB for a second when the head was pressed,
    and opening it then aborted the whole brain from inside PortAudio, beyond any try/except.
    Now that can only end the playback process. It has the line's length plus
    PLAYBACK_START_S to finish, and is killed after that. Anything but a clean exit raises
    PlaybackFailed, and the line counts as not spoken. The brain's own process never opens the
    sound card for this, so it never loads the audio library for it either."""

    def __init__(self, out: str = "auto", robot: bool = False,
                 command: list[str] | None = None,
                 start_s: float = PLAYBACK_START_S) -> None:
        self.command = command or [sys.executable, "-m", "argos.playback", "--out", out,
                                   *(["--robot"] if robot else [])]
        self.start_s = start_s

    def play(self, pcm: bytes, rate: int) -> None:
        from argos.config import BRAIN_DIR

        limit = len(pcm) / 2 / rate + self.start_s
        try:
            process = subprocess.Popen([*self.command, "--rate", str(rate)],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, cwd=BRAIN_DIR)
        except OSError as exc:
            raise PlaybackFailed(f"the playback process did not start ({exc})") from None
        # The sound goes in, and the errors come out, on threads of their own, and the time
        # limit is on wait(): on Windows `communicate()` writes the input with no time limit,
        # so a player that never reads held the brain's voice for as long as it lived.
        errors: list[bytes] = []

        def feed() -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(pcm)
                process.stdin.close()
            except (OSError, ValueError):
                pass  # the player is gone; its exit says the rest

        def drain() -> None:
            try:
                assert process.stderr is not None
                errors.append(process.stderr.read())
            except (OSError, ValueError):
                pass

        for job in (feed, drain):
            threading.Thread(target=job, name="argos-playback-io", daemon=True).start()
        try:
            process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            process.kill()  # anything it started that still holds the pipes is let go
            raise PlaybackFailed(f"not finished within {limit:.1f} s; stopped") from None
        if process.returncode != 0:
            time.sleep(0.05)  # let the last error line arrive
            err = errors[0] if errors else b""
            lines = (err or b"").decode("utf-8", "replace").strip().splitlines()
            why = f": {lines[-1][:160]}" if lines else ""
            raise PlaybackFailed(f"the playback process ended with {process.returncode}{why}")


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
                    # Every time, not once: a line that did not play is worth seeing.
                    log.warning("the line %r was not played (%s); carrying on", key, exc)
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
