"""Gemini (fake client), escalation that does not wait, the snapshot, and the live view."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from argos import text
from argos.brain import ThreadRunner, TriggerIn
from argos.clock import FakeClock
from argos.config import Settings
from argos.gemini import GeminiJudge, first_sentences
from argos.liveview import Broadcaster, LiveView, encode_frame
from argos.machine import State
from argos.senses import _live_view
from argos.senses.camera import Frame
from argos.snapshot import make_uploader
from argos.store import StoreUnavailable
from tests.conftest import BASE_ENV, make_rig


def image(width: int = 640, height: int = 480, noisy: bool = False) -> np.ndarray:
    if noisy:
        return np.random.default_rng(3).integers(0, 255, (height, width, 3), dtype=np.uint8)
    picture = np.zeros((height, width, 3), dtype=np.uint8)
    picture[:, : width // 2] = (40, 90, 160)
    return picture


class OneFrame:
    def __init__(self) -> None:
        self.frame = Frame(image(), 0.0, "2026-11-15T19:00:00.000Z")

    def latest(self) -> Frame:
        return self.frame


class FakeGenerate:
    """Stands in for the Gemini client, one level under GeminiJudge."""

    def __init__(self, score: Any = 0.7, summary: str = "A person is on the floor.",
                 fail: bool = False, hang: threading.Event | None = None) -> None:
        self.score = score
        self.summary_text = summary
        self.fail = fail
        self.hang = hang
        self.calls: list[str] = []

    def __call__(self, prompt: str, jpeg: bytes, schema: dict[str, Any] | None) -> str:
        assert jpeg[:2] == b"\xff\xd8"
        self.calls.append("check" if schema else "summary")
        if self.hang is not None:
            self.hang.wait(10)
        if self.fail:
            raise RuntimeError("Gemini unreachable")
        if schema:
            return json.dumps({"score": self.score})
        return self.summary_text


def confidence_writes(rig: Any) -> list[dict[str, Any]]:
    return [op["patch"] for op in rig.store.ops
            if op["table"] == "incidents" and op["op"] == "update" and "confidence" in
            op["patch"]]


def wait_for(condition: Any, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)


# --------------------------------------------------------------------------- Gemini


def test_check_starts_before_gemini_answers_then_updates_confidence_only() -> None:
    release = threading.Event()
    generate = FakeGenerate(score=0.95, hang=release)
    rig = make_rig(frames=OneFrame(), judge=GeminiJudge(generate), runner=ThreadRunner())
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.6, source="camera"))
    rig.step()
    assert rig.brain.state is State.CHECKING
    assert rig.incident()["confidence"] == 0.6  # the detector's own score, at once
    assert "asked" in rig.event_kinds()
    release.set()
    wait_for(lambda: generate.calls)
    time.sleep(0.05)
    rig.step()
    assert confidence_writes(rig) == [{"confidence": 0.95}]
    assert rig.incident()["status"] == "checking"


def test_a_low_answer_does_not_cancel_the_check() -> None:
    rig = make_rig(frames=OneFrame(), judge=GeminiJudge(FakeGenerate(score=0.02)))
    rig.brain.start()
    rig.brain.post(TriggerIn("stillness", 0.7, source="camera"))
    rig.step()
    rig.step()
    assert confidence_writes(rig) == [{"confidence": 0.02}]
    assert rig.brain.state is State.CHECKING
    rig.run_for(10.1)
    assert rig.brain.state is State.ALERT


@pytest.mark.parametrize("trouble", ["fail", "garbage", "hang"])
def test_failure_or_timeout_changes_nothing(trouble: str) -> None:
    hang = threading.Event() if trouble == "hang" else None
    generate = FakeGenerate(score="not a number" if trouble == "garbage" else 0.5,
                            fail=trouble == "fail", hang=hang)
    rig = make_rig(env={"ARGOS_GEMINI_TIMEOUT_S": "1"}, frames=OneFrame(),
                   judge=GeminiJudge(generate))
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.6, source="camera"))
    rig.step()
    rig.step()
    assert confidence_writes(rig) == []
    assert rig.incident()["confidence"] == 0.6
    assert rig.brain.state is State.CHECKING
    if hang:
        hang.set()


def test_help_call_and_manual_are_not_sent_to_gemini() -> None:
    generate = FakeGenerate()
    rig = make_rig(frames=OneFrame(), judge=GeminiJudge(generate))
    rig.brain.start()
    rig.brain.post(TriggerIn("help_call", 0.8, source="microphone"))
    rig.step()
    rig.brain.key("y")
    rig.step()
    rig.run_for(31.0)
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    assert generate.calls == []


def test_summary_comes_from_gemini_without_dashes() -> None:
    generate = FakeGenerate(summary="A person lies by the sofa — face down. They are "
                            "not moving. A third sentence is dropped.")
    rig = make_rig(frames=OneFrame(), judge=GeminiJudge(generate))
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9, source="camera"))
    rig.step()
    rig.run_for(10.2)
    summary = rig.incident()["summary"]
    assert summary == "A person lies by the sofa, face down. They are not moving."


def test_summary_falls_back_to_the_fixed_sentence() -> None:
    rig = make_rig(frames=OneFrame(), judge=GeminiJudge(FakeGenerate(fail=True)))
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9, source="camera"))
    rig.step()
    rig.run_for(10.2)
    assert rig.incident()["summary"] == text.fixed_summary("fall")


def test_first_sentences() -> None:
    assert first_sentences("One. Two! Three?") == "One. Two!"


# --------------------------------------------------------------------------- escalation


def test_escalation_does_not_wait_for_summary_or_upload() -> None:
    hang = threading.Event()

    def hanging_upload(incident_id: str, frame: Any) -> str:
        hang.wait(10)
        return "never"

    rig = make_rig(env={"ARGOS_SUMMARY_TIMEOUT_S": "2", "ARGOS_SNAPSHOT_TIMEOUT_S": "2"},
                   frames=OneFrame(), judge=GeminiJudge(FakeGenerate(hang=hang)),
                   uploader=hanging_upload, runner=ThreadRunner())
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.run_for(9.9)
    started = time.monotonic()
    rig.run_for(0.2)
    assert time.monotonic() - started < 0.5  # the step that escalates did not wait
    assert rig.brain.state is State.ALERT
    assert rig.incident()["status"] == "escalated"
    kinds = rig.event_kinds()
    assert kinds[-3:] == ["escalated", "call_placed", "email_sent"]
    assert rig.store.tables["devices"][0]["state"] == "alert"
    assert rig.incident()["summary"] is None  # still coming, on its own
    wait_for(lambda: False, timeout=2.6)  # the time limits run out
    rig.step()
    assert rig.incident()["summary"] == text.fixed_summary("manual")
    assert rig.incident()["snapshot_path"] is None
    hang.set()


# --------------------------------------------------------------------------- snapshot


def test_no_upload_before_escalation_then_one_jpeg() -> None:
    rig = make_rig(frames=OneFrame())
    rig.brain.uploader = make_uploader(rig.store)
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9, source="camera"))
    rig.step()
    rig.run_for(9.0)
    assert rig.store.files == {}
    rig.run_for(1.2)
    incident = rig.incident()
    path = f"incidents/{incident['id']}/snapshot.jpg"
    assert list(rig.store.files) == [f"snapshots/{path}"]
    assert rig.store.files[f"snapshots/{path}"][:2] == b"\xff\xd8"
    assert incident["snapshot_path"] == path


def test_failed_upload_leaves_snapshot_path_null_and_the_rest_complete() -> None:
    rig = make_rig(frames=OneFrame())

    def failing_upload(incident_id: str, frame: Any) -> str:
        raise StoreUnavailable("storage down")

    rig.brain.uploader = failing_upload
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9, source="camera"))
    rig.step()
    rig.run_for(10.2)
    incident = rig.incident()
    assert incident["snapshot_path"] is None
    assert incident["summary"] == text.fixed_summary("fall")
    assert incident["status"] == "escalated"
    assert rig.event_kinds()[-3:] == ["escalated", "call_placed", "email_sent"]


# --------------------------------------------------------------------------- live view


class FakeCamera:
    def __init__(self, clock: FakeClock, noisy: bool = False) -> None:
        self.clock = clock
        self.picture = image(1280, 720, noisy)

    def latest_any(self) -> Frame:
        return Frame(self.picture, self.clock.now(), self.clock.iso())


@pytest.mark.parametrize("value", [None, "0", "yes", "true"])
def test_live_view_is_off_unless_exactly_one(value: str | None) -> None:
    env = dict(BASE_ENV)
    if value is not None:
        env["ARGOS_LIVE_VIEW"] = value
    settings = Settings.from_env(env)
    assert _live_view(settings, FakeClock(), FakeCamera(FakeClock())) is None


def test_live_view_on_goes_to_the_private_topic_only(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    rig = make_rig()
    rig.brain.start()
    ops_before, log_before = len(rig.store.ops), len(rig.log.lines)
    settings = Settings.from_env({**BASE_ENV, "ARGOS_LIVE_VIEW": "1"})
    assert _live_view(settings, rig.clock, FakeCamera(rig.clock)) is not None
    sender = Broadcaster("https://project.invalid", "sb_secret_MARKER", rig.settings.device_id,
                         transport=httpx.MockTransport(handler))
    live = LiveView(FakeCamera(rig.clock).latest_any, sender.send, rig.clock, fps=4)
    for _ in range(3):
        rig.clock.advance(0.25)
        live.tick()
        live.send_waiting()
    assert live.sent == 3
    for request in seen:
        assert request.url.path == (
            f"/realtime/v1/api/broadcast/view:{rig.settings.device_id}/events/frame")
        assert request.url.raw_path.split(b"?")[0].decode() == (
            f"/realtime/v1/api/broadcast/view%3A{rig.settings.device_id}/events/frame")
        assert request.url.params["private"] == "true"
        assert request.headers["apikey"] == "sb_secret_MARKER"
        assert "authorization" not in request.headers  # a new secret key is not a JWT
    assert [json.loads(r.content)["seq"] for r in seen] == [0, 1, 2]
    assert len(rig.store.ops) == ops_before and len(rig.log.lines) == log_before
    assert list(tmp_path.iterdir()) == []  # nothing on disk
    assert not any("snapshots" in key for key in rig.store.files)


def test_slow_sender_drops_frames_and_never_waits() -> None:
    clock = FakeClock()
    gate = threading.Event()

    def slow_send(message: dict[str, Any]) -> bool:
        gate.wait(5)
        return True

    live = LiveView(FakeCamera(clock).latest_any, slow_send, clock, fps=8)
    sender = threading.Thread(target=live.send_waiting, daemon=True)
    clock.advance(0.1)
    live.tick()
    sender.start()  # stuck sending the first frame
    time.sleep(0.05)
    durations = []
    for _ in range(20):
        clock.advance(0.125)
        started = time.perf_counter()
        live.tick()
        durations.append(time.perf_counter() - started)
    assert max(durations) < 0.05
    assert live.dropped >= 18
    gate.set()
    sender.join(2)


def test_frame_shape() -> None:
    clock = FakeClock()
    for noisy in (False, True):
        sent: list[dict[str, Any]] = []

        def record(message: dict[str, Any], sent: list[dict[str, Any]] = sent) -> bool:
            sent.append(message)
            return True

        live = LiveView(FakeCamera(clock, noisy).latest_any, record, clock, fps=4)
        for _ in range(4):
            clock.advance(0.25)
            live.tick()
            live.send_waiting()
        assert [m["seq"] for m in sent] == [0, 1, 2, 3]
        for message in sent:
            assert set(message) == {"seq", "at", "w", "h", "jpeg"}
            assert max(message["w"], message["h"]) <= 480
            assert len(json.dumps(message).encode()) < 100_000


def test_encode_gives_up_rather_than_exceed_the_limit() -> None:
    huge = np.random.default_rng(1).integers(0, 255, (480, 480, 3), dtype=np.uint8)
    message = encode_frame(huge, 0, "t")
    assert message is None or len(json.dumps(message).encode()) < 100_000


def test_no_frame_written_anywhere_by_the_senses(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """The camera keeps frames in memory: running it leaves the disk untouched."""
    monkeypatch.chdir(tmp_path)
    from argos.senses.camera import Camera

    class FakeCapture:
        def read(self) -> tuple[bool, np.ndarray]:
            time.sleep(0.01)
            return True, image()

        def release(self) -> None: ...

    camera = Camera(0, FakeClock(), opener=lambda d, w, h: FakeCapture())
    camera.start()
    wait_for(lambda: camera.latest_any() is not None)
    camera.stop()
    assert camera.latest_any() is not None
    assert list(tmp_path.iterdir()) == []
    assert not any(name.endswith((".jpg", ".png")) for name in os.listdir(tmp_path))
