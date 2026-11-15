"""How the agent hears the person on the call. Everything stays in memory.

1. `Utterances` cuts the person's audio (`facetime-remote-audio`, 16 kHz mono) into what they
   said, one stretch of speech at a time, with a plain energy gate. Nothing is heard while
   Argos itself is talking (and for a moment after), so it never hears its own voice.
2. `Phrases` (Vosk, offline, the same model and method the brain uses) can only ever return
   one of a fixed list of acknowledgement phrases, or nothing. It needs no key and no network,
   so "I'm on my way" is heard even with no Gemini key.
3. `Gemini` (in `answers.py`) is given the same stretch of audio when a key is set, to catch
   other ways of saying it and to answer questions.

An utterance is dropped as soon as it has been heard. No audio, and no word the person said,
is ever logged, written to disk or put in a record.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import struct
import wave
from array import array
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("argos_call.hearing")

RATE = 16000
FRAME_S = 0.02
START_FRAMES = 4          # 80 ms above the gate starts speech
END_SILENCE_S = 0.8       # this much quiet ends it
MIN_SPEECH_S = 0.35
MAX_SPEECH_S = 12.0
TAIL_S = 0.6              # keep the ears closed this long after Argos stops talking
MIN_LEVEL = 450.0         # RMS on 16-bit samples, a floor for the gate

# First person only. A fragment such as "on the way" or "coming now" can come out of a
# question ("is help on the way?"), and a question must never acknowledge.
ACK_PHRASES = (
    "i'm on my way", "i am on my way", "on my way", "i'm coming", "i am coming",
    "acknowledge", "acknowledged", "i acknowledge", "i'll take it from here",
    "i will take it from here", "i've got it", "i'll be right there", "i will be right there",
    "i'm heading over",
)
GRAMMAR = [*ACK_PHRASES, "[unk]"]


def rms(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def wav(pcm: bytes, rate: int = RATE) -> bytes:
    """16-bit mono PCM wrapped as a WAV file, in memory."""
    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return out.getvalue()


def is_ack(phrase: str) -> bool:
    phrase = " ".join(phrase.lower().replace("’", "'").split())
    return bool(phrase) and phrase != "[unk]" and any(p in phrase for p in ACK_PHRASES)


class Utterances:
    """Speech in, whole utterances out. `quiet_until` is set by whoever speaks for Argos."""

    def __init__(self, now: Callable[[], float]) -> None:
        self.now = now
        self.quiet_until = 0.0
        self.noise = MIN_LEVEL / 3
        self._frames: list[bytes] = []
        self._loud = 0
        self._quiet_s = 0.0
        self._speaking = False
        self._pending = b""
        self.out: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4)
        self.peak = 0.0  # loudest frame heard, as a number only, to tune the gate
        self.frames = 0

    def _gate(self) -> float:
        return max(MIN_LEVEL, self.noise * 3.0)

    def _reset(self) -> None:
        self._frames = []
        self._loud = 0
        self._quiet_s = 0.0
        self._speaking = False

    def push(self, pcm: bytes) -> None:
        """Feed 16 kHz mono 16-bit audio, any length."""
        data = self._pending + pcm
        step = int(RATE * FRAME_S) * 2
        cut = len(data) - len(data) % step
        self._pending = data[cut:]
        for start in range(0, cut, step):
            self._frame(data[start:start + step])

    def _frame(self, frame: bytes) -> None:
        if self.now() < self.quiet_until:
            self._reset()
            return
        level = rms(frame)
        self.peak = max(self.peak, level)
        self.frames += 1
        loud = level >= self._gate()
        if not self._speaking:
            if loud:
                self._loud += 1
                self._frames.append(frame)
                if self._loud >= START_FRAMES:
                    self._speaking = True
                    self._quiet_s = 0.0
            else:
                self._loud = 0
                self._frames = []
                self.noise = 0.95 * self.noise + 0.05 * level
            return
        self._frames.append(frame)
        self._quiet_s = 0.0 if loud else self._quiet_s + FRAME_S
        length = len(self._frames) * FRAME_S
        if self._quiet_s >= END_SILENCE_S or length >= MAX_SPEECH_S:
            speech = b"".join(self._frames)
            self._reset()
            if length - self._quiet_s >= MIN_SPEECH_S:
                try:
                    self.out.put_nowait(speech)
                except asyncio.QueueFull:  # an old one is waiting: keep the newest
                    try:
                        self.out.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    self.out.put_nowait(speech)


class Phrases:
    """Vosk with a fixed grammar: an acknowledgement phrase, or nothing."""

    def __init__(self, model_dir: Path) -> None:
        import vosk

        if not model_dir.exists():
            raise FileNotFoundError(f"speech model not found at {model_dir} "
                                    "(run: python tools/fetch_models.py)")
        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self._model = vosk.Model(str(model_dir))

    def hear(self, pcm: bytes) -> str:
        recognizer = self._vosk.KaldiRecognizer(self._model, RATE, json.dumps(GRAMMAR))
        recognizer.AcceptWaveform(pcm)
        result = json.loads(recognizer.FinalResult())
        return str(result.get("text") or "").strip()

    def acknowledges(self, pcm: bytes) -> bool:
        return is_ack(self.hear(pcm))


async def feed_from_track(track: object, utterances: Utterances) -> None:
    """Read a LiveKit audio track at 16 kHz mono into the utterance cutter, until it ends."""
    from livekit import rtc

    stream = rtc.AudioStream.from_track(track=track, sample_rate=RATE, num_channels=1)
    try:
        async for event in stream:
            utterances.push(bytes(event.frame.data.cast("B")))
    finally:
        await stream.aclose()


def pcm_le(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)
