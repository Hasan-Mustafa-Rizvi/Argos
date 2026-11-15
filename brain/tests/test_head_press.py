"""Rule 3: a pat is never invented. The head press, the antenna press, and the brain's own
movement (the head's or the wheels') never read as a press."""

from __future__ import annotations

import math
import random
from typing import Any

import httpx

from argos.body import poses
from argos.body.base import BodyHub, Pat
from argos.body.press import HeadDiff, HeadPose, HeadPress
from argos.body.reachy import ReachyClient, Reading, RobotBody
from argos.brain import BodyIn, TriggerIn
from argos.clock import FakeClock
from argos.machine import State
from tests.conftest import make_rig
from tests.test_robot import FakeReachy

COMMANDED = HeadPose(0.0, 0.0, 0.008, 0.0, 0.0, 0.0)


class HeadReachy(FakeReachy):
    """The fake daemon, with a head: it sags 1.5 mm and 1 degree under its own weight, wobbles
    by `noise` millimetres, and is pushed down by `press_mm`."""

    def __init__(self, noise_mm: float = 0.2, refuse: bool = False) -> None:
        super().__init__()
        self.noise_mm = noise_mm
        self.press_mm = 0.0
        self.refuse = refuse
        self.rng = random.Random(3)
        self.readings = 0

    def pose_reading(self) -> Reading:
        self.readings += 1

        def wobble() -> float:
            return self.rng.uniform(-self.noise_mm, self.noise_mm) / 1000.0

        measured = HeadPose(wobble(), wobble(), 0.008 - 0.0015 + wobble() - self.press_mm / 1000,
                            0.0, math.radians(-1.0), 0.0)
        if self.refuse:
            return Reading(self.antennas(), None, measured, True)
        return Reading(self.antennas(), (measured, COMMANDED), measured)


def make(noise_mm: float = 0.2, refuse: bool = False,
         others: float = 0.0) -> tuple[RobotBody, HeadReachy, FakeClock, list[Any], dict]:
    clock = FakeClock()
    client = HeadReachy(noise_mm, refuse)
    body = RobotBody(client, clock, rng=random.Random(1), threaded=False,  # type: ignore[arg-type]
                     head_press=HeadPress(mm=5.0, deg=5.0, hold_s=0.5))
    wheels = {"until": others}
    body.body_moving_until = lambda: max(body.moving_until(), wheels["until"])
    events: list[Any] = []
    body.start(events.append)
    return body, client, clock, events, wheels


def run(body: RobotBody, clock: FakeClock, seconds: float, dt: float = 0.05) -> None:
    for _ in range(int(round(seconds / dt))):
        clock.advance(dt)
        body.update(clock.now())


def pats(events: list[Any]) -> list[Pat]:
    return [e for e in events if isinstance(e, Pat)]


def waiting(body: RobotBody, clock: FakeClock) -> None:
    """Into a check, and past the head's move and its quiet half second."""
    body.show_state("checking", 0.0)
    run(body, clock, 2.5)


# --------------------------------------------------------------------------- the detector alone


def diff(mm_z: float, deg_pitch: float = -1.0, jitter: float = 0.0,
         rng: random.Random | None = None) -> HeadDiff:
    rng = rng or random.Random(0)
    j = lambda: rng.uniform(-jitter, jitter)  # noqa: E731
    return HeadDiff((j(), j(), mm_z + j()), (j(), deg_pitch + j(), j()))


def test_noise_at_rest_is_never_a_press() -> None:
    press = HeadPress(5.0, 5.0, 0.5)
    rng = random.Random(1)
    fired = [press.update(i * 0.1, diff(-1.5, jitter=0.6, rng=rng)) for i in range(3000)]
    assert not any(fired)
    assert press.rest is not None


def test_a_held_press_is_a_press_once_per_hold() -> None:
    press = HeadPress(5.0, 5.0, 0.5)
    for i in range(10):
        press.update(i * 0.1, diff(-1.5))
    fired = [press.update(1.0 + i * 0.1, diff(-9.0)) for i in range(8)]
    assert fired.count(True) == 1
    assert fired.index(True) == 5  # held for the full half second first


def test_a_brief_knock_is_not_a_press() -> None:
    press = HeadPress(5.0, 5.0, 0.5)
    for i in range(10):
        press.update(i * 0.1, diff(-1.5))
    knock = [press.update(1.0 + i * 0.1, diff(-12.0)) for i in range(3)]  # 0.2 s
    after = [press.update(1.3 + i * 0.1, diff(-1.5)) for i in range(20)]
    assert not any(knock + after)


def test_rest_is_not_learned_while_the_head_is_unsteady() -> None:
    press = HeadPress(5.0, 5.0, 0.5)
    for i in range(50):  # swinging 6 mm either way: never steady
        press.update(i * 0.1, diff(-1.5 + (6.0 if i % 2 else -6.0)))
    assert press.rest is None
    assert not press.update(5.1, diff(-20.0))


def test_a_tilt_counts_like_a_push() -> None:
    press = HeadPress(5.0, 5.0, 0.5)
    for i in range(10):
        press.update(i * 0.1, diff(-1.5))
    fired = [press.update(1.0 + i * 0.1, diff(-1.5, deg_pitch=-8.0)) for i in range(8)]
    assert True in fired


# --------------------------------------------------------------------------- the robot


def test_a_held_press_while_waiting_is_a_pat() -> None:
    body, client, clock, events, _ = make()
    waiting(body, clock)
    run(body, clock, 1.0)  # rest is learned
    client.press_mm = 8.0
    run(body, clock, 1.0)
    assert pats(events) == [Pat("robot head")]


def test_a_brief_knock_on_the_head_is_not_a_pat() -> None:
    body, client, clock, events, _ = make()
    waiting(body, clock)
    run(body, clock, 1.0)
    client.press_mm = 12.0
    run(body, clock, 0.2)
    client.press_mm = 0.0
    run(body, clock, 3.0)
    assert pats(events) == []


def test_noise_at_rest_is_not_a_pat() -> None:
    body, client, clock, events, _ = make(noise_mm=1.0)
    waiting(body, clock)
    run(body, clock, 60.0)
    assert pats(events) == []
    assert client.readings > 300


def test_a_head_move_is_never_a_pat_during_or_just_after() -> None:
    body, client, clock, events, _ = make()
    waiting(body, clock)
    run(body, clock, 1.0)
    # The brain turns the head: while it moves, the measured pose lags far behind.
    assert body.face_forward()
    client.press_mm = 15.0
    end = body.moving_until()
    while clock.now() < end + poses.PAT_QUIET_S - 0.01:
        run(body, clock, 0.05)
    assert pats(events) == []
    client.press_mm = 0.0  # it has settled
    run(body, clock, 5.0)
    assert pats(events) == []


def test_a_wheel_burst_is_never_a_pat_during_or_just_after() -> None:
    body, client, clock, events, wheels = make()
    waiting(body, clock)
    run(body, clock, 1.0)
    for _ in range(5):  # five bursts, each jolting the head hard while it runs
        wheels["until"] = clock.now() + 0.35
        client.press_mm = 10.0
        run(body, clock, 0.35 + poses.PAT_QUIET_S - 0.05)
        assert pats(events) == []
        client.press_mm = 0.0
        run(body, clock, 1.5)
    assert pats(events) == []


def test_a_press_cannot_start_before_a_burst_and_finish_after_it() -> None:
    body, client, clock, events, wheels = make()
    waiting(body, clock)
    run(body, clock, 1.0)
    client.press_mm = 8.0
    run(body, clock, 0.3)  # pressed, not yet long enough
    wheels["until"] = clock.now() + 0.3  # a burst
    run(body, clock, 0.3 + poses.PAT_QUIET_S + 0.2)  # still pressed after the quiet window
    assert pats(events) == []  # rest was learned again; the old hold did not carry over


def test_the_antenna_still_counts_and_either_press_is_a_pat() -> None:
    body, client, clock, events, _ = make()
    waiting(body, clock)
    client.antenna_reading = ([0.5, 0.0], [0.0, 0.0])
    run(body, clock, 0.5)
    assert pats(events) == [Pat("robot antenna")]


def test_a_daemon_that_refuses_the_commanded_pose_is_not_a_lost_robot() -> None:
    body, client, clock, events, _ = make(refuse=True)
    waiting(body, clock)
    client.press_mm = 10.0
    run(body, clock, 3.0)
    assert body.attached
    assert pats(events) == []  # no head press without the commanded pose
    client.antenna_reading = ([0.5, 0.0], [0.0, 0.0])
    run(body, clock, 0.5)
    assert pats(events) == [Pat("robot antenna")]  # the antenna still works


def test_reading_asks_again_without_the_commanded_pose_when_refused() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params.get("with_target_head_pose") == "true":
            return httpx.Response(500, json={"detail": "Internal Server Error"})
        return httpx.Response(200, json={
            "head_pose": {"x": 0, "y": 0, "z": 0.006, "roll": 0, "pitch": 0, "yaw": 0},
            "antennas_position": [0.1, -0.1], "target_antennas_position": [0.0, 0.0]})

    client = ReachyClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
    reading = client.pose_reading()
    assert reading.head is None and reading.head_refused
    assert reading.head_measured is not None and reading.head_measured.z == 0.006
    assert reading.antennas == ([0.1, -0.1], [0.0, 0.0])
    assert len(seen) == 2


def test_the_hub_tells_the_robot_when_the_wheels_move() -> None:
    clock = FakeClock()

    class Base:
        name = "wheels"
        until = 0.0

        def start(self, emit: Any) -> None: ...

        def show_state(self, state: str, look_yaw_deg: float | None = None) -> None: ...

        def stood_down(self) -> None: ...

        def beep(self, ms: int) -> bool:
            return False

        def caps(self) -> list[str]:
            return []

        def fw(self) -> None:
            return None

        def moving_until(self) -> float:
            return self.until

        def stop(self) -> None: ...

    robot = RobotBody(HeadReachy(), clock, threaded=False,  # type: ignore[arg-type]
                      head_press=HeadPress())
    base = Base()
    BodyHub([robot, base], clock.now)  # the hub connects them by itself
    base.until = 42.0
    assert robot.body_moving_until() == 42.0


# --------------------------------------------------------------------------- the brain


def test_the_brain_drops_a_pat_that_comes_while_the_body_moves() -> None:
    class Moving:
        name = "moving"
        until = 0.0

        def start(self, emit: Any) -> None: ...

        def show_state(self, state: str, look_yaw_deg: float | None = None) -> None: ...

        def stood_down(self) -> None: ...

        def beep(self, ms: int) -> bool:
            return False

        def caps(self) -> list[str]:
            return []

        def fw(self) -> None:
            return None

        def moving_until(self) -> float:
            return self.until

        def stop(self) -> None: ...

    body = Moving()
    rig = make_rig(bodies=[body])
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    body.until = rig.clock.now() + 0.3  # a burst
    rig.brain.post(BodyIn(Pat("robot head")))
    rig.step()
    rig.run_for(0.7)  # the burst, and just under half a second after
    rig.brain.post(BodyIn(Pat("robot head")))
    rig.step()
    assert rig.brain.state is State.CHECKING
    assert "pat" not in rig.event_kinds()
    rig.run_for(0.2)
    rig.brain.post(BodyIn(Pat("robot head")))
    rig.step()
    assert rig.brain.state is State.CALM
    assert rig.incident()["stood_down_by"] == "pat"
