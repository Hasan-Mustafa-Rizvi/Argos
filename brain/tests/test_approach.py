"""The approach: turning toward the person and coming a little closer during a check. Driven
on a fake clock, with pretend motors that keep every command and the time it came."""

from __future__ import annotations

from typing import Any

import pytest

from argos import DEVICE_ID
from argos.approach import (
    FORWARD_BURST_S,
    GAP_S,
    STALL_LIMIT,
    TURN_BURST_S,
    Approach,
    deaf_s_max,
    decide,
)
from argos.body.base import BodyHub
from argos.body.wheels import EARS_TAIL_S, MOTOR_ON_CAP_S, FakeMotors, Wheels
from argos.brain import AnswerIn, TriggerIn
from argos.clock import FakeClock
from argos.machine import State
from argos.script import ScriptPlayer, Step
from argos.senses.camera import Camera
from argos.senses.hearing import Listener
from argos.senses.vision import FallDetector, Look, PersonPose, StillnessTracker, Vision
from tests.conftest import make_rig, seeded_store
from tests.test_hearing_voice import FakeRecognizer, NullSource
from tests.test_vision import STANDING, ScriptedEstimator


def person(x: float = 320.0, bottom: float = 300.0, visibility: float = 0.95,
           hidden: int = 0) -> PersonPose:
    """The standing person of the vision tests, centred at `x`, lowest point at `bottom`.
    `hidden` hides that many points from the feet up (out of the picture, close by)."""
    dx, dy = x - 320.0, bottom - 420.0
    names = list(STANDING)
    points = {}
    for index, name in enumerate(names):
        px, py = STANDING[name]
        seen = 0.1 if index >= len(names) - hidden else visibility
        points[name] = (px + dx, py + dy, seen)
    return PersonPose(points, 640, 480)


class Scene:
    """What the camera sees. Each turn to the left moves the person right in the picture by
    `turn_px` (and the other way), each burst forward lowers them by `forward_px`."""

    def __init__(self, clock: FakeClock, x: float = 320.0, bottom: float = 300.0,
                 turn_px: float = 120.0, forward_px: float = 0.0) -> None:
        self.clock = clock
        self.x = x
        self.bottom = bottom
        self.turn_px = turn_px
        self.forward_px = forward_px
        self.visible = True
        self.hidden = 0
        self.seen_drives = 0

    def follow(self, motors: FakeMotors) -> None:
        for _, _, left, right, _ in motors.drives()[self.seen_drives:]:
            if left < 0 < right:
                self.x += self.turn_px
            elif right < 0 < left:
                self.x -= self.turn_px
            elif left > 0 and right > 0:
                self.bottom += self.forward_px
        self.seen_drives = len(motors.drives())

    def look(self) -> Look:
        pose = person(self.x, self.bottom, hidden=self.hidden) if self.visible else None
        return Look(self.clock.now() - 0.05, pose)

    def reading(self) -> tuple[bool, int]:
        return self.visible, 0

    def bearing_deg(self) -> float | None:
        return 0.0


class LateVoice:
    """A voice whose question takes as long as the test says."""

    def __init__(self) -> None:
        self.waiting: list[Any] = []

    def say(self, key: str, on_done: Any = None, on_spoken: Any = None) -> str:
        if key == "ask":
            self.waiting.append(on_spoken)
        return key

    def finish(self) -> None:
        for on_spoken in self.waiting:
            on_spoken(True)
        self.waiting.clear()


def rig_with_wheels(scene_kwargs: dict[str, Any] | None = None, **rig_kwargs: Any) -> Any:
    rig = make_rig(**{k: v for k, v in rig_kwargs.items() if k not in ("wheels", "vision")})
    clock = rig.clock
    motors = FakeMotors(clock)
    wheels = Wheels(motors, clock, 0.25, 0.3, pretend=True, threaded=False)
    scene = Scene(clock, **(scene_kwargs or {}))
    rig = make_rig(wheels=wheels, bodies=[wheels], vision=scene, **{
        k: v for k, v in rig_kwargs.items() if k not in ("wheels", "vision")})
    wheels.clock = rig.clock
    motors.clock = rig.clock
    scene.clock = rig.clock
    rig.motors, rig.wheels, rig.scene = motors, wheels, scene
    return rig


def run(rig: Any, seconds: float, dt: float = 0.05) -> None:
    for _ in range(int(round(seconds / dt))):
        rig.clock.advance(dt)
        rig.brain.step()
        rig.scene.follow(rig.motors)


def open_check(rig: Any, trigger: str = "fall") -> str:
    rig.brain.start()
    rig.brain.post(TriggerIn(trigger, 0.9))
    rig.step()
    assert rig.brain.state is State.CHECKING
    return rig.brain.machine.incident_id


def drives(rig: Any) -> list[tuple[str, float, float, float, float]]:
    return rig.motors.drives()


# --------------------------------------------------------------------------- steering


@pytest.mark.parametrize(("pose", "what", "direction"), [
    (person(x=100), "turn", +1),
    (person(x=540), "turn", -1),
    (person(x=320, bottom=300), "forward", 0),
    (person(x=320, bottom=470), "close", 0),
    (person(x=60), "close", 0),  # reaches the left edge
    (person(x=320, hidden=9), "close", 0),  # only 4 of 13 points seen
])
def test_which_way_from_where_the_person_is(pose: PersonPose, what: str, direction: int) -> None:
    got, way, _ = decide(pose)
    assert (got, way) == (what, direction)


def test_person_in_the_left_third_turns_that_way() -> None:
    rig = rig_with_wheels({"x": 100})
    open_check(rig)
    run(rig, 1.0)
    first = drives(rig)[0]
    assert first[2] < 0 < first[3]  # left side back, right forward: a turn to the left
    assert first[4] == pytest.approx(TURN_BURST_S)


def test_person_in_the_right_third_turns_that_way() -> None:
    rig = rig_with_wheels({"x": 540})
    open_check(rig)
    run(rig, 1.0)
    first = drives(rig)[0]
    assert first[3] < 0 < first[2]


def test_person_in_the_middle_and_far_brings_it_forward() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    run(rig, 1.0)
    first = drives(rig)[0]
    assert first[2] > 0 and first[3] > 0
    assert first[4] == pytest.approx(FORWARD_BURST_S)


def test_turns_until_centred_then_comes_forward_until_close() -> None:
    rig = rig_with_wheels({"x": 100, "bottom": 330, "turn_px": 130, "forward_px": 90})
    open_check(rig)
    run(rig, 8.0)
    kinds = ["turn" if d[2] < 0 < d[3] else "forward" for d in drives(rig)]
    assert kinds[:2] == ["turn", "forward"]
    assert not rig.brain.approach.active
    assert rig.brain.approach.last_reason.startswith("close enough")


def test_touching_the_bottom_edge_stops_without_moving() -> None:
    rig = rig_with_wheels({"bottom": 470})
    open_check(rig)
    run(rig, 3.0)
    assert drives(rig) == []
    assert "bottom edge" in rig.brain.approach.last_reason


def test_too_few_body_points_to_trust_stops_without_moving() -> None:
    rig = rig_with_wheels()
    rig.scene.hidden = 8  # only the head, shoulders and elbows: 5 of 13 points
    open_check(rig)
    run(rig, 3.0)
    assert drives(rig) == []
    assert "too few" in rig.brain.approach.last_reason


def test_a_person_lost_from_view_stops_it_and_it_never_searches() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    run(rig, 0.5)
    assert len(drives(rig)) == 1
    rig.scene.visible = False
    run(rig, 8.0)
    assert len(drives(rig)) == 1  # no turn to look for them
    assert rig.brain.approach.last_reason == "the person is not in view"
    assert rig.motors.commands[-1][0] == "stop"


def test_a_turn_that_does_not_move_the_person_stops_it() -> None:
    rig = rig_with_wheels({"x": 100, "turn_px": 0.0})  # stuck on carpet
    open_check(rig)
    run(rig, 8.0)
    assert len(drives(rig)) == STALL_LIMIT
    assert "did not turn" in rig.brain.approach.last_reason


def test_it_does_not_hunt_from_side_to_side() -> None:
    rig = rig_with_wheels({"x": 100, "turn_px": 440.0})  # each turn overshoots to the far side
    open_check(rig)
    run(rig, 8.0)
    assert len(drives(rig)) == 2  # left, right, and then it gives up
    assert "could not settle" in rig.brain.approach.last_reason


# --------------------------------------------------------------------------- the limits


def test_it_ends_at_the_time_limit_and_the_motor_time_cap_holds() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300}, env={"CHECK_TIMEOUT_S": "30"})
    open_check(rig)
    started = rig.clock.now()
    run(rig, 12.0)
    max_s = rig.settings.approach_max_s
    assert all(start < started + max_s for _, start, *_ in drives(rig))
    assert rig.brain.approach.last_reason == "the time limit for an approach"
    assert sum(d[4] for d in drives(rig)) <= MOTOR_ON_CAP_S + 1e-9


def test_the_first_burst_comes_after_the_question_has_finished() -> None:
    voice = LateVoice()
    rig = rig_with_wheels({"x": 320, "bottom": 300}, voice=voice)
    open_check(rig)
    run(rig, 3.0)  # the question is still playing
    assert drives(rig) == []
    asked_at = rig.clock.now()
    voice.finish()
    run(rig, 2.0)
    assert drives(rig) and drives(rig)[0][1] >= asked_at


def escalation_wait(wheels: bool) -> float:
    voice = LateVoice()
    if wheels:
        rig = rig_with_wheels({"x": 320, "bottom": 300}, voice=voice)
    else:
        rig = make_rig(voice=voice)
        rig.scene = Scene(rig.clock)
        rig.motors = FakeMotors(rig.clock)
    open_check(rig)
    run(rig, 1.0)
    voice.finish()
    asked = None
    while rig.brain.state is not State.ALERT:
        run(rig, 0.05)
        if asked is None and rig.brain.machine.deadline is not None:
            asked = rig.brain.machine.deadline - rig.settings.check_timeout_s
    assert asked is not None
    if wheels:
        assert drives(rig), "the approach ran"
    return rig.clock.now() - asked


def test_the_wait_for_an_answer_is_the_same_with_the_wheels_on_and_off() -> None:
    assert escalation_wait(True) == pytest.approx(escalation_wait(False), abs=0.051)
    assert escalation_wait(True) == pytest.approx(10.0, abs=0.051)


# --------------------------------------------------------------------------- when it may not run


def test_never_in_calm_or_alert() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    rig.brain.start()
    run(rig, 5.0)
    assert drives(rig) == []  # calm
    open_check(rig)
    run(rig, 10.5)
    assert rig.brain.state is State.ALERT
    alert_at = rig.clock.now()
    run(rig, 10.0)
    assert all(start < alert_at - 0.4 for _, start, *_ in drives(rig))


def test_no_approach_on_a_check_resumed_after_a_restart() -> None:
    store = seeded_store()
    store.tables["incidents"].append({
        "id": "old-1", "device_id": DEVICE_ID, "trigger": "fall", "status": "checking",
        "confidence": 0.9, "started_at": "2026-11-15T18:00:00.000Z", "ended_at": None,
        "stood_down_by": None, "summary": None, "snapshot_path": None,
        "acknowledged_by": None, "acknowledged_at": None})
    rig = rig_with_wheels({"x": 320, "bottom": 300}, store=store)
    rig.brain.start()
    run(rig, 5.0)
    assert rig.brain.state is State.CHECKING
    assert drives(rig) == []


def test_no_approach_in_a_scripted_run() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300},
                          script=ScriptPlayer((Step(1.0, "trigger", trigger="fall",
                                                    confidence=0.9),), 20.0))
    rig.brain.start()
    run(rig, 8.0)
    assert rig.brain.state is State.CHECKING
    assert drives(rig) == []


def test_no_approach_within_the_rest_period_of_the_last() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300},
                          env={"ARGOS_APPROACH_REST_S": "300", "ARGOS_TRIGGER_COOLDOWN_S": "0"})
    open_check(rig)
    run(rig, 3.0)
    first = len(drives(rig))
    assert first >= 1
    rig.brain.post(AnswerIn("voice", "I'm fine"))
    run(rig, 60.0)
    rig.brain.post(TriggerIn("manual"))
    run(rig, 8.0)
    assert len(drives(rig)) == first  # 60 s later: still resting
    rig.brain.post(AnswerIn("voice", "I'm fine"))
    run(rig, 240.0)
    rig.brain.post(TriggerIn("manual"))
    run(rig, 3.0)
    assert len(drives(rig)) > first  # after 300 s: allowed again


# --------------------------------------------------------------------------- stopping at once


def in_a_burst(rig: Any) -> float:
    for _ in range(100):
        run(rig, 0.05)
        if rig.motors.running():
            return rig.clock.now()
    raise AssertionError("no burst started")


def stopped_at(rig: Any, when: float) -> bool:
    return any(c[0] == "stop" and abs(c[1] - when) < 1e-9 for c in rig.motors.commands) \
        and not rig.motors.running()


def test_the_check_ending_stops_the_base_at_once() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    in_a_burst(rig)
    rig.brain.post(AnswerIn("voice", "I'm fine"))
    rig.step()
    assert stopped_at(rig, rig.clock.now())
    assert rig.brain.state is State.CALM


def test_the_stop_key_stops_the_base_at_once_and_holds() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    in_a_burst(rig)
    rig.brain.key(" ")
    assert stopped_at(rig, rig.clock.now())
    count = len(drives(rig))
    run(rig, 5.0)
    assert len(drives(rig)) == count
    assert rig.brain.state is State.CHECKING  # the check itself goes on


def test_the_brain_stopping_stops_the_base_at_once() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    in_a_burst(rig)
    rig.brain.stop()
    assert stopped_at(rig, rig.clock.now())
    assert rig.motors.closed


def test_coming_close_stops_it_at_the_next_look() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300})
    open_check(rig)
    in_a_burst(rig)
    rig.scene.bottom = 470
    run(rig, 5.0)
    assert len(drives(rig)) == 1
    assert "bottom edge" in rig.brain.approach.last_reason


# --------------------------------------------------------------------------- eyes and ears


def test_with_the_real_camera_and_vision_every_burst_needs_a_fresh_look() -> None:
    from argos.senses.camera import SETTLE_S

    clock = FakeClock(start=10.0)
    motors = FakeMotors(clock)
    wheels = Wheels(motors, clock, 0.25, 0.3, threaded=False)
    hub = BodyHub([wheels], clock.now)
    camera = Camera(0, clock, moving_until=hub.moving_until)
    estimator = ScriptedEstimator([person()] * 80)
    vision = Vision(camera, estimator, clock, FallDetector(), StillnessTracker(),
                    moving_until=hub.moving_until)
    wheels.open_check = lambda: "check-1"
    wheels.look = vision.look
    wheels.moved_until = hub.moving_until
    wheels.start(lambda event: None)
    assert wheels.begin("check-1") is None

    def frame(dt: float = 0.1) -> None:
        clock.advance(dt)
        camera.put("IMAGE")
        vision.step()

    frame()
    assert wheels.forward(0.3) is None
    burst_end = clock.now() + 0.3
    while clock.now() < burst_end + SETTLE_S - 0.05:  # pictures keep coming; none is still
        frame(0.05)
        assert vision.look().t < burst_end  # so the newest look is still from before
    assert wheels.forward(0.3) == "no fresh look since the body last moved"
    frame(0.1)  # settled: a look from after the burst
    assert vision.look().t > burst_end
    assert wheels.forward(0.3) is None
    burst_end = clock.now() + 0.3
    while clock.now() < burst_end + SETTLE_S + 0.05:
        frame(0.05)
    assert vision.look().t > burst_end  # settled after the second burst...
    clock.advance(0.5)  # ...but then no picture for half a second
    assert wheels.forward(0.3) == "the newest look is too old"
    assert len(motors.drives()) == 2


def test_with_the_real_vision_a_person_lost_stops_the_approach() -> None:
    clock = FakeClock()
    motors = FakeMotors(clock)
    wheels = Wheels(motors, clock, 0.25, 0.3, threaded=False)
    hub = BodyHub([wheels], clock.now)
    camera = Camera(0, clock, moving_until=hub.moving_until)
    estimator = ScriptedEstimator([person()] * 3 + [None] * 50)
    vision = Vision(camera, estimator, clock, FallDetector(), StillnessTracker(),
                    moving_until=hub.moving_until)
    wheels.open_check = lambda: "check-1"
    wheels.look = vision.look
    wheels.moved_until = hub.moving_until
    wheels.start(lambda event: None)
    approach = Approach(wheels, vision.look, lambda: False, hub.moving_until, clock, max_s=6.0,
                        needs_head=False)
    assert approach.start("check-1") is None
    for _ in range(200):
        clock.advance(0.05)
        camera.put("IMAGE")
        vision.step()
        approach.step(clock.now())
    assert not approach.active
    assert approach.last_reason == "the person is not in view"
    assert len(motors.drives()) <= 2  # one burst, maybe two, then nothing: no search


def test_a_camera_move_is_not_the_person_moving() -> None:
    clock = FakeClock()
    moving = {"until": 0.0}
    tracker = StillnessTracker(stillness_s=10, move=0.04)
    vision = Vision(None, None, clock, FallDetector(), tracker,
                    moving_until=lambda: moving["until"])
    for _ in range(40):
        clock.advance(0.125)
        vision.process("F", person(x=320))
    still_before = tracker.still_s(clock.now())
    moving["until"] = clock.now() + 0.3  # a burst: afterwards the person is elsewhere in view
    clock.advance(0.7)
    vision.process("F", person(x=420))
    for _ in range(8):
        clock.advance(0.125)
        vision.process("F", person(x=420))
    assert tracker.still_s(clock.now()) >= still_before + 1


def test_the_ears_are_shut_through_each_burst_and_open_in_the_gaps() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300}, env={"CHECK_TIMEOUT_S": "30"})
    listener = Listener(NullSource(), FakeRecognizer(), rig.brain.gate, rig.clock)
    heard: list[str] = []
    listener.on_yes = heard.append
    open_check(rig)
    burst_at = in_a_burst(rig)
    listener.feed(b"i'm fine|0.9")  # during the burst
    run(rig, FORWARD_BURST_S + EARS_TAIL_S - 0.1)
    listener.feed(b"i'm fine|0.9")  # just after it
    assert heard == []
    run(rig, 0.2)
    assert rig.clock.now() < burst_at + FORWARD_BURST_S + GAP_S  # still in the quiet gap
    listener.feed(b"i'm fine|0.9")
    assert heard == ["I'm fine"]


def test_how_long_the_ears_are_shut_is_bounded() -> None:
    rig = rig_with_wheels({"x": 320, "bottom": 300}, env={"CHECK_TIMEOUT_S": "30"})
    open_check(rig)
    run(rig, 12.0)
    deaf = sum(seconds + EARS_TAIL_S for *_, seconds in drives(rig))
    assert deaf <= deaf_s_max(rig.settings.approach_max_s) + 1e-9
    assert deaf_s_max(6.0) == pytest.approx(3.2)


def test_nothing_new_is_recorded() -> None:
    rig = rig_with_wheels({"x": 100, "bottom": 330, "turn_px": 130, "forward_px": 60})
    open_check(rig)
    run(rig, 8.0)
    rig.brain.post(AnswerIn("voice", "I'm fine"))
    rig.step()
    assert drives(rig)
    assert rig.event_kinds() == ["device_online", "trigger", "asked", "heard", "stood_down"]


def test_the_head_faces_the_person_again_after_the_approach() -> None:
    class Head:
        name = "head"

        def __init__(self) -> None:
            self.shown: list[tuple[str, Any]] = []
            self.faced = 0

        def start(self, emit: Any) -> None: ...

        def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
            self.shown.append((state, look_yaw_deg))

        def face_forward(self) -> bool:
            self.faced += 1
            return True

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

    rig = make_rig()
    motors = FakeMotors(rig.clock)
    wheels = Wheels(motors, rig.clock, 0.25, 0.3, threaded=False)
    head = Head()
    scene = Scene(rig.clock, bottom=470)
    rig = make_rig(wheels=wheels, bodies=[head, wheels], vision=scene)
    wheels.clock = motors.clock = scene.clock = rig.clock
    rig.motors, rig.wheels, rig.scene = motors, wheels, scene
    open_check(rig)
    run(rig, 3.0)
    assert head.faced == 1  # level and straight ahead for the approach
    assert head.shown[-1][0] == "checking"  # then facing the person again
