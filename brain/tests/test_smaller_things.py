"""Stage 5: who records the call, and the question that was not spoken."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from argos.brain import TriggerIn
from argos.escalation import CALL_EVENTS, CallAgentEscalator, DryRunEscalator, make_escalator
from argos.machine import State
from argos.voice import Voice
from tests.conftest import make_rig
from tests.test_hearing_voice import FakeSpeaker, FakeTTS


def escalate(rig: Any) -> str:
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9))
    rig.step()
    incident_id = rig.brain.machine.incident_id
    rig.run_for(10.2)
    assert rig.brain.state is State.ALERT
    return incident_id


# --------------------------------------------------------------------------- the call agent


def test_with_the_call_agent_the_brain_records_none_of_the_call_events() -> None:
    rig = make_rig(env={"ARGOS_CALL_AGENT": "1"})
    assert isinstance(rig.brain.escalator, CallAgentEscalator)
    escalate(rig)
    rig.run_for(2.0)
    kinds = rig.event_kinds()
    assert "escalated" in kinds
    assert not set(kinds) & set(CALL_EVENTS)
    assert not any(kind in line for line in rig.log.lines for kind in CALL_EVENTS)
    assert rig.incident()["status"] == "escalated"  # the rest is as before


@pytest.mark.parametrize("value", [None, "0", "yes", "true"])
def test_without_the_call_agent_the_brain_does_as_today(value: str | None) -> None:
    rig = make_rig(env={} if value is None else {"ARGOS_CALL_AGENT": value})
    assert isinstance(rig.brain.escalator, DryRunEscalator)
    escalate(rig)
    sent = [e for e in rig.store.tables["events"] if e["kind"] in CALL_EVENTS]
    assert [e["kind"] for e in sent] == ["call_placed", "email_sent"]
    assert all(e["detail"]["dry_run"] is True for e in sent)


def test_the_call_agent_switch_never_reaches_a_real_sender() -> None:
    calls: list[Any] = []
    rig = make_rig(env={"ARGOS_CALL_AGENT": "1", "ARGOS_DRY_RUN": "0"})
    escalator = make_escalator(rig.settings, rig.brain.recorder,
                               real_sender=lambda *a, **k: calls.append(a))
    escalator.escalate("inc")
    assert calls == []


# --------------------------------------------------------------------------- the question


def asked_detail(rig: Any) -> dict[str, Any]:
    return next(e["detail"] for e in rig.store.tables["events"] if e["kind"] == "asked")


def test_a_spoken_question_has_no_spoken_field(tmp_path: Path) -> None:
    voice = Voice(None, tmp_path, FakeTTS(), FakeSpeaker(), threaded=False)  # type: ignore[arg-type]
    rig = make_rig(voice=voice)
    voice.clock = rig.clock
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert asked_detail(rig) == {"said": "Are you okay?"}


def test_only_a_beep_records_spoken_false(tmp_path: Path) -> None:
    beeps: list[int] = []
    voice = Voice(None, tmp_path, None, FakeSpeaker(),  # type: ignore[arg-type]
                  beep=lambda ms: beeps.append(ms) or True, threaded=False)
    rig = make_rig(voice=voice)
    voice.clock = rig.clock
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert beeps
    assert asked_detail(rig) == {"said": "Are you okay?", "spoken": False}
    asked = next(e for e in rig.store.tables["events"] if e["kind"] == "asked")
    assert asked["text"] == "Argos asked: Are you okay?"


def test_a_speaker_that_fails_records_spoken_false(tmp_path: Path) -> None:
    class Broken:
        def play(self, pcm: bytes, rate: int) -> None:
            raise OSError("no sound card")

    voice = Voice(None, tmp_path, FakeTTS(), Broken(), threaded=False)  # type: ignore[arg-type]
    rig = make_rig(voice=voice)
    voice.clock = rig.clock
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    assert asked_detail(rig)["spoken"] is False


def test_a_run_with_no_voice_does_not_count_as_spoken() -> None:
    beeps: list[int] = []

    class Board:
        name = "board"

        def start(self, emit: Any) -> None: ...

        def show_state(self, state: str, look_yaw_deg: float | None = None) -> None: ...

        def stood_down(self) -> None: ...

        def beep(self, ms: int) -> bool:
            beeps.append(ms)
            return True

        def caps(self) -> list[str]:
            return ["buzzer"]

        def fw(self) -> None:
            return None

        def moving_until(self) -> float:
            return 0.0

        def stop(self) -> None: ...

    rig = make_rig(bodies=[Board()])  # no voice at all
    rig.brain.start()
    rig.brain.post(TriggerIn("help_call", 0.8))
    rig.step()
    rig.step()
    assert asked_detail(rig) == {"said": "Are you okay?", "spoken": False}
    assert beeps == [300]  # the board's buzzer stands in for the question


def test_a_question_never_reported_as_played_counts_as_not_spoken() -> None:
    class Stuck:
        def say(self, key: str, on_done: Any = None, on_spoken: Any = None) -> str:
            return key  # never reports back

    rig = make_rig(voice=Stuck())
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.run_for(8.2)  # the machine's grace for a question never reported
    assert asked_detail(rig) == {"said": "Are you okay?", "spoken": False}
    rig.run_for(10.1)
    assert rig.brain.state is State.ALERT  # it still escalates on time
