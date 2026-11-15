"""Listening: a call for help in calm, and a clear yes during a check.

Method: Vosk, offline, with a fixed list of phrases (a grammar). The recogniser can only ever
return one of those phrases or "unknown", so other speech in the room is never turned into
text at all, let alone stored. It runs with no network, on the Pi's processor, from a 40 MB
model. In a loud hall it will often miss; the pat and the keyboard cover that.

- Calm: "help", "help me" and the like start a `help_call` check, if the recogniser is
  confident enough (`ARGOS_HELP_MIN_CONF`).
- During a check: only a clear yes ("I'm fine", "I'm okay", "yes") stands it down. "No",
  "help" or "I'm not okay" are recorded as heard and change nothing.
- Nothing is heard while Argos speaks: the voice marks the time it is talking, and audio
  from that time is thrown away with the recogniser's state, so Argos never hears its own
  question. The same while the wheels run and for half a second after: they mark it on a
  field of their own (`motors_until`), so neither can cut the other's quiet short.
- Only the matched phrase is ever passed on. Unknown speech is dropped without a trace.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from argos.clock import Clock

log = logging.getLogger("argos.hearing")

RATE = 16000

YES = (
    "yes", "yeah", "yep", "i'm fine", "i am fine", "i'm okay", "i am okay", "i'm ok",
    "i'm alright", "i'm all right", "i'm good", "yes i'm fine", "yes i'm okay", "i'm fine thanks",
)
HELP = ("help", "help me", "help help", "somebody help", "someone help", "please help",
        "please help me", "argos help")
NO = ("no", "not okay", "i'm not okay", "i'm not fine", "not fine", "no i'm not okay")
GRAMMAR = [*YES, *HELP, *NO, "[unk]"]


def classify(phrase: str) -> str | None:
    """"yes", "help", "no", or None for anything that is not one of our phrases."""
    phrase = " ".join(phrase.lower().split())
    if not phrase or phrase == "[unk]":
        return None
    words = phrase.split()
    if "help" in words:
        return "help"
    if "no" in words or "not" in words:
        return "no"
    if phrase in YES:
        return "yes"
    return None


def pretty(phrase: str) -> str:
    """"i'm fine" -> "I'm fine"."""
    words = [("I" + w[1:]) if w in ("i", "i'm") else w for w in phrase.lower().split()]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


class Recognizer(Protocol):
    def accept(self, pcm: bytes) -> tuple[str, float] | None: ...

    def reset(self) -> None: ...


class VoskRecognizer:
    def __init__(self, model_dir: Path) -> None:
        import vosk

        if not model_dir.exists():
            raise FileNotFoundError(f"speech model not found at {model_dir} "
                                    "(run: python tools/fetch_models.py)")
        vosk.SetLogLevel(-1)
        self._model = vosk.Model(str(model_dir))
        self._vosk = vosk
        self._make()

    def _make(self) -> None:
        self._rec = self._vosk.KaldiRecognizer(self._model, RATE, json.dumps(GRAMMAR))
        self._rec.SetWords(True)

    def accept(self, pcm: bytes) -> tuple[str, float] | None:
        if not self._rec.AcceptWaveform(pcm):
            return None
        result = json.loads(self._rec.Result())
        phrase = result.get("text", "").strip()
        if not phrase:
            return None
        words = result.get("result") or []
        confs = [float(w.get("conf", 0.0)) for w in words]
        return phrase, (sum(confs) / len(confs) if confs else 0.0)

    def reset(self) -> None:
        self._rec.Reset()


class AudioSource(Protocol):
    def read(self, timeout: float) -> bytes | None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


def pick_device(spec: str, kind: str, robot: bool) -> int | str | None:
    """`auto`: the robot's audio card when the robot is attached, else the system default.
    A number is a device index; any other text is part of a device name."""
    import sounddevice as sd

    spec = spec.strip()
    if spec.isdigit():
        return int(spec)
    wanted = spec if spec.lower() not in ("", "auto") else ("Reachy Mini Audio" if robot else "")
    if not wanted:
        return None
    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    for index, device in enumerate(sd.query_devices()):
        if wanted.lower() in str(device["name"]).lower() and device[channels] > 0:
            return index
    if spec.lower() not in ("", "auto"):
        log.warning("no %s audio device named %r; using the default", kind, spec)
    return None


class Microphone:
    """16 kHz mono 16-bit audio from a microphone, a quarter second at a time."""

    def __init__(self, device: int | str | None) -> None:
        self.device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=40)
        self._stream: Any = None
        self._rate = RATE

    def start(self) -> None:
        import numpy as np
        import sounddevice as sd

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            data = bytes(indata)
            if self._rate != RATE:
                samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
                count = int(len(samples) * RATE / self._rate)
                positions = np.linspace(0, len(samples) - 1, count)
                data = np.interp(positions, np.arange(len(samples)), samples).astype(
                    "<i2").tobytes()
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                pass  # the recogniser fell behind: drop audio, never block the sound card

        try:
            self._stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                             blocksize=RATE // 4, device=self.device,
                                             callback=callback)
        except Exception:
            info = sd.query_devices(self.device, "input")
            self._rate = int(info["default_samplerate"])
            self._stream = sd.RawInputStream(samplerate=self._rate, channels=1, dtype="int16",
                                             blocksize=self._rate // 4, device=self.device,
                                             callback=callback)
        self._stream.start()

    def read(self, timeout: float) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class Listener:
    def __init__(
        self,
        source: AudioSource,
        recognizer: Recognizer,
        gate: Any,
        clock: Clock,
        help_min_conf: float = 0.6,
    ) -> None:
        self.source = source
        self.recognizer = recognizer
        self.gate = gate
        self.clock = clock
        self.help_min_conf = help_min_conf
        self.on_help: Callable[[float], None] = lambda conf: None
        self.on_yes: Callable[[str], None] = lambda said: None
        self.on_other: Callable[[str], None] = lambda said: None
        self._was_muted = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def muted(self) -> bool:
        now = self.clock.now()
        return (self.gate.mode == "off" or now < getattr(self.gate, "speaking_until", 0.0)
                or now < getattr(self.gate, "motors_until", 0.0))

    def feed(self, pcm: bytes) -> None:
        """One chunk of audio. Public so tests can drive it."""
        if self.muted():
            if not self._was_muted:
                self.recognizer.reset()  # forget anything half-heard before Argos spoke
            self._was_muted = True
            return
        if self._was_muted:
            self.recognizer.reset()
            self._was_muted = False
        result = self.recognizer.accept(pcm)
        if result is not None:
            self.heard(*result)

    def heard(self, phrase: str, conf: float) -> None:
        kind = classify(phrase)
        if kind is None:
            return  # not one of ours: dropped, never logged
        mode = self.gate.mode
        if mode == "help" and kind == "help":
            if conf >= self.help_min_conf:
                log.info("heard a call for help (%.2f)", conf)
                self.on_help(conf)
        elif mode == "answer":
            if kind == "yes":
                self.on_yes(pretty(phrase))
            else:
                self.on_other(pretty(phrase))

    def start(self) -> None:
        self.source.start()
        self._thread = threading.Thread(target=self._run, name="argos-listen", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.source.stop()

    def _run(self) -> None:
        while not self._stop.is_set():
            chunk = self.source.read(0.5)
            if chunk:
                try:
                    self.feed(chunk)
                except Exception:
                    log.exception("listening error")
