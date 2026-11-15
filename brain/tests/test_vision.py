"""Detectors, faked one layer under our logic: body points instead of a camera and a model."""

from __future__ import annotations

import random
from typing import Any

from argos.brain import TriggerIn
from argos.clock import FakeClock
from argos.machine import State
from argos.senses.camera import Camera, Frame
from argos.senses.vision import FallDetector, PersonPose, StillnessTracker, Vision
from tests.conftest import make_rig

FPS = 8
DT = 1.0 / FPS

STANDING = {
    "nose": (320, 80), "left_shoulder": (290, 140), "right_shoulder": (350, 140),
    "left_elbow": (280, 200), "right_elbow": (360, 200), "left_wrist": (275, 250),
    "right_wrist": (365, 250), "left_hip": (300, 260), "right_hip": (340, 260),
    "left_knee": (300, 340), "right_knee": (340, 340), "left_ankle": (300, 420),
    "right_ankle": (340, 420),
}
LYING = {
    "nose": (100, 400), "left_shoulder": (160, 390), "right_shoulder": (160, 410),
    "left_elbow": (200, 380), "right_elbow": (200, 420), "left_wrist": (240, 375),
    "right_wrist": (240, 425), "left_hip": (280, 390), "right_hip": (280, 410),
    "left_knee": (360, 395), "right_knee": (360, 405), "left_ankle": (440, 395),
    "right_ankle": (440, 405),
}
# Bending over to pick something up: torso far from upright, legs straight, body still tall.
BENDING = {
    **STANDING, "nose": (420, 250), "left_shoulder": (370, 240), "right_shoulder": (390, 250),
    "left_elbow": (390, 290), "right_elbow": (405, 295), "left_wrist": (400, 330),
    "right_wrist": (410, 335),
}


def pose(points: dict[str, tuple[float, float]], jitter: float = 0.0, shift: float = 0.0,
         rng: random.Random | None = None, visibility: float = 0.9) -> PersonPose:
    rng = rng or random.Random(0)
    return PersonPose(
        {name: (x + shift + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter),
                visibility) for name, (x, y) in points.items()},
        640, 480,
    )


def feed_fall(detector: FallDetector, poses: list[PersonPose | None],
              start: float = 0.0) -> list[float]:
    fired = []
    for index, item in enumerate(poses):
        result = detector.update(item, start + index * DT)
        if result is not None:
            fired.append(result)
    return fired


def test_lying_for_the_hold_time_is_a_fall_once() -> None:
    detector = FallDetector(hold_s=2.0)
    rng = random.Random(1)
    fired = feed_fall(detector, [pose(LYING, 2, rng=rng) for _ in range(FPS * 6)])
    assert len(fired) == 1
    assert 0.5 <= fired[0] <= 1.0


def test_lying_briefly_is_not_a_fall() -> None:
    detector = FallDetector(hold_s=2.0)
    poses = [pose(STANDING)] * 8 + [pose(LYING)] * 10 + [pose(STANDING)] * 20
    assert feed_fall(detector, poses) == []


def test_standing_sitting_and_bending_are_not_falls() -> None:
    detector = FallDetector(hold_s=2.0)
    poses = [pose(STANDING, 2)] * 40 + [pose(BENDING, 2)] * 40
    assert feed_fall(detector, poses) == []


def test_empty_room_triggers_nothing() -> None:
    assert feed_fall(FallDetector(), [None] * 200) == []
    still = StillnessTracker(stillness_s=5)
    assert [still.update(None, i * DT) for i in range(400)] == [None] * 400
    assert not still.present and still.still_s(50.0) == 0


def test_getting_up_rearms_the_fall() -> None:
    detector = FallDetector(hold_s=2.0)
    poses = [pose(LYING)] * 24 + [pose(STANDING)] * 24 + [pose(LYING)] * 24
    assert len(feed_fall(detector, poses)) == 2


def test_low_visibility_is_not_a_fall() -> None:
    detector = FallDetector(hold_s=2.0, min_score=0.5)
    assert feed_fall(detector, [pose(LYING, visibility=0.3)] * 40) == []


def test_stillness_past_the_threshold_fires_once() -> None:
    tracker = StillnessTracker(stillness_s=10, move=0.04)
    rng = random.Random(2)
    fired = []
    for i in range(FPS * 20):
        result = tracker.update(pose(STANDING, jitter=1.5, rng=rng), i * DT)
        if result is not None:
            fired.append((i * DT, result))
    assert len(fired) == 1
    assert 10.0 <= fired[0][0] <= 10.5
    assert tracker.present and tracker.still_s(20 * 1.0) >= 19


def test_movement_resets_stillness() -> None:
    tracker = StillnessTracker(stillness_s=10, move=0.04)
    fired = []
    for i in range(FPS * 30):
        shift = 60.0 if (i // (FPS * 6)) % 2 else 0.0  # moves every 6 seconds
        if tracker.update(pose(STANDING, shift=shift), i * DT) is not None:
            fired.append(i)
    assert fired == []
    assert tracker.still_s(30.0) < 7


def test_still_s_is_zero_when_nobody_is_there() -> None:
    tracker = StillnessTracker(stillness_s=10)
    for i in range(FPS * 5):
        tracker.update(pose(STANDING), i * DT)
    assert tracker.present
    for i in range(FPS * 5, FPS * 8):
        tracker.update(None, i * DT)
    assert not tracker.present and tracker.still_s(8.0) == 0


class ScriptedEstimator:
    def __init__(self, poses: list[PersonPose | None]) -> None:
        self.poses = list(poses)
        self.calls = 0

    def estimate(self, image: Any, t_ms: int) -> PersonPose | None:
        self.calls += 1
        return self.poses.pop(0) if self.poses else None


def test_vision_posts_a_fall_with_its_frame_and_respects_the_brain() -> None:
    clock = FakeClock()
    camera = Camera(0, clock)
    estimator = ScriptedEstimator([pose(LYING)] * 40)
    vision = Vision(camera, estimator, clock, FallDetector(hold_s=2.0), StillnessTracker(),
                    fps=FPS)
    posted: list[tuple[str, float, Any]] = []
    vision.on_trigger = lambda kind, conf, frame: posted.append((kind, conf, frame))
    allowed = {"value": False}
    vision.can_trigger = lambda: allowed["value"]
    for _ in range(30):
        clock.advance(DT)
        camera.put("IMAGE")
        vision.step()
    assert posted == []  # a check is open: detectors stay quiet
    allowed["value"] = True
    detector = FallDetector(hold_s=2.0)
    vision.fall = detector
    for _ in range(30):
        clock.advance(DT)
        camera.put("IMAGE")
        vision.step()
    assert [p[0] for p in posted] == ["fall"]
    assert isinstance(posted[0][2], Frame)


def test_frames_taken_while_the_head_moves_are_skipped() -> None:
    clock = FakeClock()
    moving = {"until": 100.0}
    camera = Camera(0, clock, moving_until=lambda: moving["until"])
    estimator = ScriptedEstimator([pose(STANDING)] * 10)
    vision = Vision(camera, estimator, clock, FallDetector(), StillnessTracker(), fps=FPS)
    clock.advance(1.0)
    camera.put("BLURRED")
    vision.step()
    assert estimator.calls == 0 and camera.latest() is None
    assert camera.latest_any() is not None  # the live view may still show it
    moving["until"] = 0.0
    clock.advance(0.5)
    camera.put("STILL")
    vision.step()
    assert estimator.calls == 1


def test_bearing_points_toward_the_person() -> None:
    clock = FakeClock()
    vision = Vision(None, None, clock, FallDetector(), StillnessTracker(), hfov_deg=70)
    vision.process("F", pose(STANDING, shift=200))  # right side of the image
    assert vision.bearing_deg() is not None and vision.bearing_deg() < -15
    vision.process("F", pose(STANDING, shift=-250))  # left side
    assert vision.bearing_deg() > 15


def test_brain_turns_toward_the_person_and_records_the_reading() -> None:
    class FakeVision:
        def reading(self) -> tuple[bool, int]:
            return True, 42

        def bearing_deg(self) -> float:
            return 25.0

    class RecordingBody:
        name = "recording"

        def __init__(self) -> None:
            self.shown: list[tuple[str, float | None]] = []

        def start(self, emit: Any) -> None: ...

        def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
            self.shown.append((state, look_yaw_deg))

        def stood_down(self) -> None: ...

        def beep(self, ms: int) -> bool:
            return False

        def caps(self) -> list[str]:
            return []

        def fw(self) -> None:
            return None

        def moving_until(self) -> float:
            return 0.0

        def stop(self) -> None: ...

    body = RecordingBody()
    rig = make_rig(bodies=[body], vision=FakeVision())
    rig.brain.start()
    rig.brain.post(TriggerIn("help_call", 0.8, source="microphone"))
    rig.step()
    assert ("checking", 25.0) in body.shown
    reading = rig.store.tables["readings"][-1]
    assert reading["person_present"] is True and reading["still_s"] == 42


def test_cooldown_keeps_detectors_quiet_after_a_check() -> None:
    rig = make_rig(env={"ARGOS_TRIGGER_COOLDOWN_S": "30"})
    rig.brain.start()
    assert rig.brain.can_trigger()
    rig.brain.post(TriggerIn("fall", 0.9, source="camera"))
    rig.step()
    assert not rig.brain.can_trigger()
    rig.brain.key("y")
    rig.step()
    assert rig.brain.state is State.CALM and not rig.brain.can_trigger()
    rig.run_for(30.1)
    assert rig.brain.can_trigger()
