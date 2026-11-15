"""Listening (faked at the recognised-text layer) and the voice (faked at the HTTP and speaker
layers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from argos.brain import AnswerIn, Gate, HeardIn, TriggerIn
from argos.clock import FakeClock
from argos.machine import State
from argos.senses.hearing import Listener, classify, pretty
from argos.voice import LINES, ElevenLabs, Voice
from tests.conftest import make_rig


class FakeRecognizer:
    """Turns each chunk straight into the text it carries."""

    def __init__(self) -> None:
        self.accepted: list[bytes] = []
        self.resets = 0

    def accept(self, pcm: bytes) -> tuple[str, float] | None:
        self.accepted.append(pcm)
        phrase, _, conf = pcm.decode().partition("|")
        return (phrase, float(conf or 0.9)) if phrase else None

    def reset(self) -> None:
        self.resets += 1


class NullSource:
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def read(self, timeout: float) -> bytes | None:
        return None


def make_listener(mode: str = "help") -> tuple[Listener, FakeRecognizer, Gate, FakeClock,
                                               dict[str, list[Any]]]:
    clock = FakeClock()
    gate = Gate()
    gate.mode = mode
    recognizer = FakeRecognizer()
    listener = Listener(NullSource(), recognizer, gate, clock, help_min_conf=0.6)
    got: dict[str, list[Any]] = {"help": [], "yes": [], "other": []}
    listener.on_help = got["help"].append
    listener.on_yes = got["yes"].append
    listener.on_other = got["other"].append
    return listener, recognizer, gate, clock, got


@pytest.mark.parametrize(
    ("phrase", "kind"),
    [("i'm fine", "yes"), ("yes", "yes"), ("i am okay", "yes"), ("yeah", "yes"),
     ("no", "no"), ("i'm not okay", "no"), ("not fine", "no"), ("help", "help"),
     ("help me", "help"), ("i'm fine help", "help"), ("yes no", "no"), ("[unk]", None),
     ("", None), ("fine", None), ("okay", None)],
)
def test_only_a_clear_yes_is_yes(phrase: str, kind: str | None) -> None:
    assert classify(phrase) == kind


def test_pretty_phrases() -> None:
    assert pretty("i'm fine") == "I'm fine"
    assert pretty("yes i'm okay") == "Yes I'm okay"


def test_call_for_help_in_calm() -> None:
    listener, _, _, _, got = make_listener("help")
    listener.feed(b"help me|0.82")
    listener.feed(b"help|0.3")  # not confident enough
    listener.feed(b"i'm fine|0.9")  # not a check: ignored
    assert got == {"help": [0.82], "yes": [], "other": []}


def test_yes_during_a_check_and_no_does_not_count() -> None:
    listener, _, _, _, got = make_listener("answer")
    listener.feed(b"no|0.9")
    listener.feed(b"help|0.9")
    listener.feed(b"i'm fine|0.9")
    assert got["yes"] == ["I'm fine"]
    assert got["other"] == ["No", "Help"]
    assert got["help"] == []


def test_unknown_speech_is_dropped() -> None:
    listener, _, _, _, got = make_listener("answer")
    listener.feed(b"[unk]|0.9")
    listener.feed(b"|0")
    assert got == {"help": [], "yes": [], "other": []}


def test_nothing_is_heard_while_argos_speaks() -> None:
    listener, recognizer, gate, clock, got = make_listener("answer")
    gate.speaking_until = clock.now() + 2.0
    listener.feed(b"i'm fine|0.9")
    assert recognizer.accepted == [] and got["yes"] == []
    assert recognizer.resets == 1
    clock.advance(2.1)
    listener.feed(b"i'm fine|0.9")
    assert got["yes"] == ["I'm fine"]
    assert recognizer.resets == 2  # state from before is forgotten


def test_heard_answers_drive_the_brain() -> None:
    rig = make_rig()
    rig.brain.start()
    listener, _, _, _, _ = make_listener()
    listener.gate = rig.brain.gate
    listener.on_help = lambda conf: rig.brain.post(TriggerIn("help_call", conf, "microphone"))
    listener.on_yes = lambda said: rig.brain.post(AnswerIn("voice", said, "microphone"))
    listener.on_other = lambda said: rig.brain.post(HeardIn(said))
    listener.feed(b"help|0.84")
    rig.step()
    assert rig.brain.state is State.CHECKING
    assert rig.incident()["confidence"] == 0.84
    listener.feed(b"no|0.9")
    rig.step()
    assert rig.brain.state is State.CHECKING  # "No" stands nothing down
    listener.feed(b"i'm okay|0.9")
    rig.step()
    assert rig.brain.state is State.CALM
    heard = [e["detail"]["said"] for e in rig.store.tables["events"] if e["kind"] == "heard"]
    assert heard == ["No", "I'm okay"]


# --------------------------------------------------------------------------- voice


class FakeTTS:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def synthesize(self, line: str) -> bytes:
        self.calls.append(line)
        if self.fail:
            raise RuntimeError("network down")
        return b"\x01\x00" * 8000  # half a second of near silence


class FakeSpeaker:
    def __init__(self, during: Any = None) -> None:
        self.played: list[int] = []
        self.during = during

    def play(self, pcm: bytes, rate: int) -> None:
        self.played.append(len(pcm))
        if self.during:
            self.during()


def test_a_line_is_fetched_once_and_reused(tmp_path: Path) -> None:
    tts = FakeTTS()
    voice = Voice(FakeClock(), tmp_path, tts, FakeSpeaker(), cache_key="v|m", threaded=False)
    done: list[str] = []
    voice.say("ask", lambda: done.append("ask"))
    voice.say("ask", lambda: done.append("ask"))
    assert tts.calls == [LINES["ask"]]
    assert done == ["ask", "ask"]
    again = Voice(FakeClock(), tmp_path, FakeTTS(), FakeSpeaker(), cache_key="v|m",
                  threaded=False)
    again.say("ask")
    assert again.tts.calls == []  # type: ignore[union-attr]
    assert len(list(tmp_path.iterdir())) == 1


def test_no_key_and_nothing_cached_beeps_and_carries_on(tmp_path: Path) -> None:
    beeps: list[int] = []
    voice = Voice(FakeClock(), tmp_path, None, FakeSpeaker(), beep=lambda ms: beeps.append(ms)
                  or True, threaded=False)
    rig = make_rig(voice=voice)
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert "asked" in rig.event_kinds()
    assert beeps
    rig.run_for(10.1)
    assert rig.brain.state is State.ALERT


def test_failed_fetch_does_not_stop_a_check(tmp_path: Path) -> None:
    voice = Voice(FakeClock(), tmp_path, FakeTTS(fail=True), FakeSpeaker(), threaded=False)
    rig = make_rig(voice=voice)
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert "asked" in rig.event_kinds()


def test_argos_does_not_hear_its_own_question(tmp_path: Path) -> None:
    rig = make_rig()
    listener, recognizer, _, _, _ = make_listener()
    listener.clock = rig.clock
    listener.gate = rig.brain.gate
    listener.on_yes = lambda said: rig.brain.post(AnswerIn("voice", said, "microphone"))
    # While the question plays, the room (and Argos's own voice) is fed to the ears.
    speaker = FakeSpeaker(during=lambda: listener.feed(b"yes|0.95"))
    voice = Voice(rig.clock, tmp_path, FakeTTS(), speaker, gate=rig.brain.gate, threaded=False)
    rig.brain.voice = voice
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert speaker.played
    assert recognizer.accepted == []
    assert rig.brain.state is State.CHECKING


def test_elevenlabs_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"\x00\x01" * 100)

    tts = ElevenLabs("MARKER-KEY", "VOICE", "eleven_flash_v2_5",
                     transport=httpx.MockTransport(handler))
    assert tts.synthesize("Are you okay?") == b"\x00\x01" * 100
    request = seen[0]
    assert request.url.path == "/v1/text-to-speech/VOICE"
    assert request.url.params["output_format"] == "pcm_16000"
    assert request.headers["xi-api-key"] == "MARKER-KEY"
    assert json.loads(request.content) == {"text": "Are you okay?",
                                           "model_id": "eleven_flash_v2_5"}
