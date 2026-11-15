"""The robot's body language, against a fake daemon client and against no robot at all."""

from __future__ import annotations

import json
import random
from typing import Any

import httpx

from argos.body import poses
from argos.body.base import Pat
from argos.body.poses import Pose
from argos.body.reachy import ReachyClient, RobotBody, RobotUnavailable
from argos.clock import FakeClock


class FakeReachy:
    base_url = "http://fake-daemon"

    def __init__(self, present: bool = True) -> None:
        self.present = present
        self.gotos: list[tuple[Pose, float]] = []
        self.antenna_reading: tuple[list[float], list[float]] = ([0.0, 0.0], [0.0, 0.0])

    def status(self) -> dict[str, Any]:
        if not self.present:
            raise RobotUnavailable("connection refused")
        return {"state": "running", "version": "fake"}

    def enable_motors(self) -> None:
        if not self.present:
            raise RobotUnavailable("connection refused")

    def goto(self, pose: Pose, duration: float) -> None:
        if not self.present:
            raise RobotUnavailable("connection refused")
        self.gotos.append((pose, duration))

    def antennas(self) -> tuple[list[float], list[float]]:
        return self.antenna_reading

    def close(self) -> None:
        pass


def make(present: bool = True) -> tuple[RobotBody, FakeReachy, FakeClock, list[Any]]:
    clock = FakeClock()
    client = FakeReachy(present)
    body = RobotBody(client, clock, rng=random.Random(1), threaded=False)  # type: ignore[arg-type]
    events: list[Any] = []
    body.start(events.append)
    return body, client, clock, events


def run(body: RobotBody, clock: FakeClock, seconds: float, dt: float = 0.05) -> None:
    for _ in range(int(round(seconds / dt))):
        clock.advance(dt)
        body.update(clock.now())


def test_each_state_change_sends_its_movement_once() -> None:
    body, client, clock, _ = make()
    run(body, clock, 2.0)
    client.gotos.clear()
    body.show_state("checking", look_yaw_deg=20.0)
    run(body, clock, 6.0)
    assert len(client.gotos) == 1
    pose, _ = client.gotos[0]
    assert pose == poses.clamp(poses.checking(20.0))

    client.gotos.clear()
    body.show_state("alert")
    body.update(clock.now())
    assert client.gotos[0][0] == poses.clamp(poses.ALERT_CYCLE[0].pose)


def test_alert_repeats_until_the_state_changes() -> None:
    body, client, clock, _ = make()
    body.show_state("alert")
    run(body, clock, 12.0)
    first = [p for p, _ in client.gotos if p == poses.clamp(poses.ALERT_CYCLE[0].pose)]
    assert len(first) >= 2
    client.gotos.clear()
    body.show_state("calm")
    run(body, clock, 3.0)
    assert client.gotos[0][0] == poses.REST
    assert len(client.gotos) == 1


def test_calm_shows_a_sign_of_life_now_and_then() -> None:
    body, client, clock, _ = make()
    run(body, clock, 3.0)
    client.gotos.clear()
    run(body, clock, 20.0)
    assert client.gotos == []  # quiet most of the time
    run(body, clock, 40.0)
    assert any(p == poses.CALM_LIFE[0].pose for p, _ in client.gotos)


def test_standing_down_is_a_short_friendly_move_then_rest() -> None:
    body, client, clock, _ = make()
    body.show_state("checking")
    run(body, clock, 2.0)
    client.gotos.clear()
    body.stood_down()
    run(body, clock, 4.0)
    sent = [p for p, _ in client.gotos]
    assert sent == [poses.clamp(m.pose) for m in poses.STOOD_DOWN]


def test_nothing_commanded_outside_the_limits() -> None:
    body, client, clock, _ = make()
    rng = random.Random(7)
    for _ in range(60):
        state = rng.choice(["calm", "checking", "alert"])
        body.show_state(state, look_yaw_deg=rng.uniform(-400, 400))
        if rng.random() < 0.2:
            body.stood_down()
        run(body, clock, rng.uniform(0.1, 3.0))
    assert len(client.gotos) > 50
    previous = poses.REST
    for pose, duration in client.gotos:
        assert poses.within(pose)
        assert duration >= poses.LIMITS.min_duration_s
        assert duration >= poses.safe_duration(previous, pose, 0.0) - 1e-9
        previous = pose


def test_stopping_returns_to_rest() -> None:
    body, client, clock, _ = make()
    body.show_state("alert")
    run(body, clock, 2.0)
    body.stop()
    assert client.gotos[-1][0] == poses.REST


def test_antenna_press_during_check_is_a_pat() -> None:
    body, client, clock, events = make()
    body.show_state("checking")
    run(body, clock, 2.0)
    client.antenna_reading = ([0.5, 0.0], [0.0, 0.0])  # pushed half a radian
    run(body, clock, 0.5)
    assert [e for e in events if isinstance(e, Pat)] == [Pat("robot antenna")]


def test_antenna_press_outside_a_check_is_not_a_pat() -> None:
    body, client, clock, events = make()
    body.show_state("alert")
    client.antenna_reading = ([0.8, 0.0], [0.0, 0.0])
    run(body, clock, 5.0)
    assert not any(isinstance(e, Pat) for e in events)


def test_no_robot_sends_nothing_and_fails_nothing() -> None:
    body, client, clock, events = make(present=False)
    assert not body.attached
    assert body.caps() == []
    body.show_state("checking", 10)
    run(body, clock, 3.0)
    body.stood_down()
    body.stop()
    assert client.gotos == []


def test_robot_found_later_is_used() -> None:
    body, client, clock, _ = make(present=False)
    client.present = True
    run(body, clock, 11.0)
    assert body.attached
    assert body.caps() == ["head", "antennas", "camera", "voice"]


def test_http_client_speaks_the_daemon_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/state/full":
            return httpx.Response(200, json={"antennas_position": [0.1, -0.1],
                                             "target_antennas_position": [0.0, 0.0]})
        if request.url.path == "/api/daemon/status":
            return httpx.Response(200, json={"state": "running", "version": "1.14.0"})
        return httpx.Response(200, json={"uuid": "x"})

    client = ReachyClient("http://localhost:8000", transport=httpx.MockTransport(handler))
    client.goto(Pose(pitch=-8.0, yaw=20.0, z=8.0, antennas=(0.0, 0.0)), 1.0)
    body = json.loads(seen[-1].content)
    assert seen[-1].url.path == "/api/move/goto"
    assert body["duration"] == 1.0 and body["body_yaw"] == 0.0
    assert abs(body["head_pose"]["yaw"] - 0.349066) < 1e-5
    assert abs(body["head_pose"]["z"] - 0.008) < 1e-9
    assert client.antennas() == ([0.1, -0.1], [0.0, 0.0])
    assert client.status()["version"] == "1.14.0"
