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
        self.stops = 0
        self.antenna_reading: tuple[list[float], list[float]] = ([0.0, 0.0], [0.0, 0.0])

    def stop_moves(self) -> int:
        if not self.present:
            raise RobotUnavailable("connection refused")
        self.stops += 1
        return 0

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


# --------------------------------------------------------------------------- one move at a time


class BusyReachy(FakeReachy):
    """Like the real daemon (1.14.0): one move at a time. A goto while a move runs is dropped,
    though the call still succeeds; a move runs a little past its duration; stop_moves ends
    the running move."""

    def __init__(self, clock: FakeClock) -> None:
        super().__init__()
        self.clock = clock
        self.busy_until = 0.0
        self.accepted: list[Pose] = []
        self.dropped = 0

    def stop_moves(self) -> int:
        self.stops += 1
        running = self.clock.now() < self.busy_until
        self.busy_until = 0.0
        return int(running)

    def goto(self, pose: Pose, duration: float) -> None:
        super().goto(pose, duration)
        now = self.clock.now()
        if now < self.busy_until:
            self.dropped += 1
            return
        self.accepted.append(pose)
        self.busy_until = now + duration + 0.05


def busy_body() -> tuple[RobotBody, BusyReachy, FakeClock]:
    clock = FakeClock()
    client = BusyReachy(clock)
    body = RobotBody(client, clock, rng=random.Random(1), threaded=False)  # type: ignore[arg-type]
    body.start(lambda event: None)
    run(body, clock, 0.2)
    return body, client, clock


def test_a_check_during_a_sign_of_life_still_looks_up() -> None:
    """Seen on the real robot: a check started during the calm sign of life kept the head
    where the sign of life put it, because the daemon dropped the check pose."""
    body, client, clock = busy_body()
    body.show_state("calm")
    life = poses.clamp(poses.CALM_LIFE[0].pose)
    for _ in range(2000):
        run(body, clock, 0.05)
        if client.accepted and client.accepted[-1] == life:
            break
    assert client.accepted[-1] == life
    run(body, clock, 0.3)  # well inside the sign of life's move
    body.show_state("checking", 10.0)
    run(body, clock, 0.2)
    assert client.accepted[-1] == poses.clamp(poses.checking(10.0))
    assert client.dropped == 0


def test_every_alert_step_and_the_calm_after_it_reach_the_daemon() -> None:
    """Seen on the real robot: after an acknowledgement the head stayed in the alert pose."""
    body, client, clock = busy_body()
    body.show_state("alert")
    run(body, clock, 6.0)
    body.show_state("calm")
    run(body, clock, 0.2)
    assert client.dropped == 0
    assert client.accepted[-1] == poses.clamp(poses.REST)


def test_a_move_after_a_pause_does_not_stop_anything() -> None:
    body, client, clock = busy_body()
    body.show_state("calm")
    run(body, clock, 3.0)
    stops = client.stops
    body.show_state("checking", 0.0)
    run(body, clock, 0.2)
    assert client.stops == stops


def test_the_client_stops_the_running_moves_and_shrugs_off_refusals() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/move/running":
            return httpx.Response(200, json=[{"uuid": "a"}, {"uuid": "b"}])
        if request.url.path == "/api/move/stop":
            ended = json.loads(request.content)["uuid"] == "b"
            return httpx.Response(500 if ended else 200, json={"message": "ok"})
        return httpx.Response(404)

    client = ReachyClient("http://localhost:8000", transport=httpx.MockTransport(handler))
    assert client.stop_moves() == 1
    assert seen == [("GET", "/api/move/running"), ("POST", "/api/move/stop"),
                    ("POST", "/api/move/stop")]

    old = ReachyClient("http://localhost:8000",
                       transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    assert old.stop_moves() == 0


def test_a_connection_the_daemon_dropped_is_tried_once_more_not_a_lost_robot() -> None:
    """Seen on the Pi: a stop the daemon refused (HTTP 500) made its server close the
    connection, and the next goto on it failed with ReadError: "robot lost" for 10 s."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/move/goto" and calls.count("/api/move/goto") == 1:
            raise httpx.ReadError("connection closed", request=request)
        return httpx.Response(200, json={"uuid": "x"})

    client = ReachyClient("http://localhost:8000", transport=httpx.MockTransport(handler))
    client.goto(Pose(), 1.0)
    assert calls == ["/api/move/goto", "/api/move/goto"]


def test_a_daemon_that_stays_gone_is_still_a_lost_robot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection closed", request=request)

    client = ReachyClient("http://localhost:8000", transport=httpx.MockTransport(handler))
    try:
        client.goto(Pose(), 1.0)
    except RobotUnavailable:
        pass
    else:
        raise AssertionError("a daemon that never answers is a lost robot")


def test_each_stop_goes_on_a_connection_of_its_own() -> None:
    stops: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/move/running":
            return httpx.Response(200, json=[{"uuid": "a"}])
        stops.append(request)
        return httpx.Response(500, text="KeyError: not found")

    client = ReachyClient("http://localhost:8000", transport=httpx.MockTransport(handler))
    assert client.stop_moves() == 0
    assert stops[0].headers.get("connection") == "close"
