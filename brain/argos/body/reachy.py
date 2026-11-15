"""The Reachy Mini Lite body, driven through the robot's own daemon on the same machine.

The daemon (`reachy-mini-daemon`, from Pollen Robotics' `reachy-mini` package) owns the motors
and serves a documented HTTP API on http://127.0.0.1:8000 (it listens on 127.0.0.1 only,
unless it is the wireless version). This driver uses these calls:

    GET  /api/daemon/status                 is the robot there, which robot, its motors
    GET  /api/motors/status                 {"mode": "enabled" | "disabled" | ...}
    POST /api/motors/set_mode/enabled       hold position
    POST /api/move/goto                     move head and antennas over a duration
    GET  /api/state/full?...                where the head and antennas are, and where they
                                            were told to be

What the daemon reports for the head, from its source (reachy_mini, daemon/app/routers/
state.py and backend/): `head_pose` is worked out from the six head motors by its kinematics
at every step of its 50 Hz control loop; `target_head_pose` is the last pose it was told.
Both are {x, y, z, roll, pitch, yaw} in metres and radians. Asking for the target before any
has been set fails with HTTP 500 (an assertion in the daemon). That is not a lost robot, and
it is read again without it (`pose_reading`).

It does not import the robot's Python package. That package pulls PyGObject, which has no
wheel on Linux and must be compiled on the Pi; talking HTTP keeps the brain's own install
compiler-free. Start the daemon with `--no-media` so it leaves the camera and audio to the
brain (see README).

Movement runs on its own thread, so a slow robot never slows the brain.

A pat (rule 3 of the task: a pat is never invented). A press on an antenna, or on the head
(`press.py`), counts during a check, and only while the robot holds still: never during a
move of the head or of the wheels, or for PAT_QUIET_S after (`body_moving_until` is the
whole body's, wheels included).
"""

from __future__ import annotations

import logging
import math
import random
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from argos.body import poses
from argos.body.base import Connected, Disconnected, Emit, Pat
from argos.body.poses import Move, Pose
from argos.body.press import HeadPose, HeadPress, head_diff
from argos.clock import Clock

log = logging.getLogger("argos.robot")

ROBOT_CAPS = ["head", "antennas", "camera", "voice"]
RECONNECT_S = 10.0
TICK_S = 0.05
STATE_PATH = "/api/state/full"


class RobotUnavailable(Exception):
    """The daemon could not be reached, or (as `RobotRefused`) refused the request."""


class RobotRefused(RobotUnavailable):
    """The daemon answered, but with an error status."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Reading:
    """One look at the head and the antennas."""

    antennas: tuple[list[float], list[float]] | None  # where they are, where they are held
    head: tuple[HeadPose, HeadPose] | None  # where the head is, where it was told to be
    head_measured: HeadPose | None = None
    head_refused: bool = False  # the daemon refused the commanded pose: none set yet


def _head_pose(value: Any) -> HeadPose | None:
    if not isinstance(value, dict):
        return None
    try:
        return HeadPose(*(float(value[key]) for key in ("x", "y", "z", "roll", "pitch", "yaw")))
    except (KeyError, TypeError, ValueError):
        return None


def _antenna_pair(state: dict[str, Any]) -> tuple[list[float], list[float]] | None:
    present, target = state.get("antennas_position"), state.get("target_antennas_position")
    if not (isinstance(present, list) and isinstance(target, list)):
        return None
    if len(present) != 2 or len(target) != 2:
        return None
    try:
        return [float(v) for v in present], [float(v) for v in target]
    except (TypeError, ValueError):
        return None


class ReachyClient:
    """A thin HTTP client for the daemon."""

    def __init__(
        self, base_url: str, timeout_s: float = 1.5, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise RobotUnavailable(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code >= 400:
            raise RobotRefused(f"{method} {path}: HTTP {response.status_code}",
                               response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise RobotRefused(f"{method} {path}: not JSON", response.status_code) from None

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/api/daemon/status") or {}

    def motors_mode(self) -> str | None:
        status = self._call("GET", "/api/motors/status") or {}
        mode = status.get("mode") if isinstance(status, dict) else None
        return str(mode) if mode is not None else None

    def enable_motors(self) -> None:
        self._call("POST", "/api/motors/set_mode/enabled")

    def goto(self, pose: Pose, duration: float) -> None:
        self._call(
            "POST",
            "/api/move/goto",
            json={
                "head_pose": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": pose.z / 1000.0,
                    "roll": math.radians(pose.roll),
                    "pitch": math.radians(pose.pitch),
                    "yaw": math.radians(pose.yaw),
                },
                "antennas": [pose.antennas[0], pose.antennas[1]],
                "body_yaw": 0.0,
                "duration": duration,
            },
        )

    def antennas(self) -> tuple[list[float], list[float]] | None:
        state = self._call(
            "GET",
            STATE_PATH,
            params={"with_antenna_positions": "true", "with_target_antenna_positions": "true"},
        ) or {}
        return _antenna_pair(state)

    def pose_reading(self) -> Reading:
        """The head and the antennas, where they are and where they were told to be, in one
        request."""
        params = {"with_control_mode": "false", "with_body_yaw": "false",
                  "with_head_pose": "true", "with_target_head_pose": "true",
                  "with_antenna_positions": "true", "with_target_antenna_positions": "true"}
        refused = False
        try:
            state = self._call("GET", STATE_PATH, params=params) or {}
        except RobotRefused:
            # Refused until a head pose has been commanded at least once. Not a lost robot:
            # read the rest without it.
            refused = True
            params["with_target_head_pose"] = "false"
            state = self._call("GET", STATE_PATH, params=params) or {}
        if not isinstance(state, dict):
            state = {}
        measured = _head_pose(state.get("head_pose"))
        commanded = _head_pose(state.get("target_head_pose"))
        head = (measured, commanded) if measured is not None and commanded is not None else None
        return Reading(_antenna_pair(state), head, measured, refused)

    def close(self) -> None:
        self._client.close()


class RobotBody:
    name = "robot"

    def __init__(
        self,
        client: ReachyClient,
        clock: Clock,
        antenna_pat: bool = True,
        rng: random.Random | None = None,
        threaded: bool = True,
        head_press: HeadPress | None = None,
    ) -> None:
        self.client = client
        self.clock = clock
        self.antenna_pat = antenna_pat
        self.head_press = head_press
        self.rng = rng or random.Random()
        self.threaded = threaded
        # The whole body's movement, wheels included. The BodyHub sets this to its own.
        self.body_moving_until: Callable[[], float] = self.moving_until
        self.attached = False
        self._emit: Emit = lambda event: None
        self._lock = threading.RLock()
        self._state = "calm"
        self._queue: deque[Move] = deque()
        self._next_at = 0.0
        self._pose = poses.REST
        self._moving_until = 0.0
        self._next_life = 0.0
        self._next_connect = 0.0
        self._press_since: float | None = None
        self._next_press_poll = 0.0
        self._pat_quiet_until = 0.0
        self._warned = False
        self._warned_head = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ Body

    def start(self, emit: Emit) -> None:
        self._emit = emit
        if not self.threaded:
            self._connect(self.clock.now())
        else:  # an absent daemon takes a timeout to notice; the robot's own thread does it
            self._thread = threading.Thread(target=self._run, name="argos-robot", daemon=True)
            self._thread.start()

    def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
        with self._lock:
            self._state = state
            self._press_since = None
            if self.head_press is not None:
                self.head_press.reset()
            now = self.clock.now()
            self._queue.clear()
            if state == "checking":
                self._queue.append(Move(poses.checking(look_yaw_deg), poses.CHECKING_MOVE_S))
            elif state == "alert":
                self._queue.extend(poses.ALERT_CYCLE)
            else:
                self._queue.append(Move(poses.REST, 1.2))
                self._schedule_life(now)
            self._next_at = now

    def stood_down(self) -> None:
        with self._lock:
            self._state = "calm"
            self._queue.clear()
            self._queue.extend(poses.STOOD_DOWN)
            now = self.clock.now()
            self._next_at = now
            self._schedule_life(now)

    def face_forward(self) -> bool:
        """For the approach: the head level and straight ahead, and held there, so that where
        the person is in the picture is where they are from the base. True if the robot is
        attached and will do it."""
        with self._lock:
            if not self.attached:
                return False
            now = self.clock.now()
            target = poses.clamp(poses.APPROACH)
            duration = poses.safe_duration(self._pose, target, poses.APPROACH_MOVE_S)
            self._queue.clear()
            self._queue.append(Move(target, poses.APPROACH_MOVE_S))
            self._next_at = now
            # Counted as moving from now, before the robot's thread sends it, so that nothing
            # looks or senses a pat in between.
            self._moving_until = max(self._moving_until, now + duration + 2 * TICK_S)
            self._press_since = None
            if self.head_press is not None:
                self.head_press.reset()
            return True

    def beep(self, ms: int) -> bool:
        return False

    def caps(self) -> list[str]:
        return list(ROBOT_CAPS) if self.attached else []

    def fw(self) -> str | None:
        return None

    def moving_until(self) -> float:
        return self._moving_until

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        with self._lock:
            if self.attached:
                self._send(Move(poses.REST, 1.5), self.clock.now())
        self.client.close()

    # ------------------------------------------------------------------ loop

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.update(self.clock.now())
            except Exception:
                log.exception("robot loop error")
            self._stop.wait(TICK_S)

    def update(self, now: float) -> None:
        """One step: send the next move when due, keep calm and alert alive, sense a pat."""
        with self._lock:
            if not self.attached:
                if now >= self._next_connect:
                    self._connect(now)
                return
            if self._queue:
                if now >= self._next_at:
                    move = self._queue.popleft()
                    self._send(move, now)
                return
            if self._state == "calm" and now >= self._next_life:
                self._queue.extend(poses.CALM_LIFE)
                self._schedule_life(now)
            elif self._state == "alert" and now >= self._next_at:
                self._queue.extend(poses.ALERT_CYCLE)
            elif self._state == "checking" and (self.antenna_pat or self.head_press is not None):
                self._sense_pat(now)

    def _schedule_life(self, now: float) -> None:
        low, high = poses.CALM_LIFE_EVERY_S
        self._next_life = now + self.rng.uniform(low, high)

    def _send(self, move: Move, now: float) -> None:
        target = poses.clamp(move.pose)
        duration = poses.safe_duration(self._pose, target, move.duration)
        try:
            self.client.goto(target, duration)
        except RobotUnavailable as exc:
            self._lost(now, str(exc))
            return
        self._pose = target
        self._moving_until = now + duration
        self._next_at = now + duration + move.hold

    def _quiet_until(self) -> float:
        """No pat until then: any part of the body moved too recently."""
        moving = max(self._moving_until, self.body_moving_until())
        return moving + poses.PAT_QUIET_S

    def _forget_presses(self) -> None:
        self._press_since = None
        if self.head_press is not None:
            self.head_press.reset()

    def _sense_pat(self, now: float) -> None:
        if now < self._quiet_until():
            self._forget_presses()  # a hold can never span a move
            return
        if now < self._next_press_poll or now < self._pat_quiet_until:
            return
        self._next_press_poll = now + 0.1
        try:
            if self.head_press is not None:
                reading = self.client.pose_reading()
            else:
                reading = Reading(self.client.antennas(), None)
        except RobotRefused as exc:
            if not self._warned_head:
                log.warning("the daemon refused the state request (%s); no pat from the robot "
                            "until it answers", exc)
                self._warned_head = True
            return
        except RobotUnavailable as exc:
            self._lost(now, str(exc))
            return
        if self.clock.now() < self._quiet_until():
            self._forget_presses()  # the wheels started while the reading was on its way
            return
        source = None
        if self.antenna_pat and self._antenna_held(reading, now):
            source = "robot antenna"
        if self.head_press is not None:
            if reading.head is None and not self._warned_head:
                why = ("it refuses the commanded head pose until one is set" if
                       reading.head_refused else "it did not report the head's pose")
                log.warning("no head press reading (%s); the antenna press still works", why)
                self._warned_head = True
            diff = head_diff(*reading.head) if reading.head is not None else None
            if self.head_press.update(now, diff):
                source = source or "robot head"
        if source is not None:
            self._forget_presses()
            self._pat_quiet_until = now + poses.ANTENNA_PAT_COOLDOWN_S
            log.info("%s pressed and held: taken as a pat", source.removeprefix("robot "))
            self._emit(Pat(source))

    def _antenna_held(self, reading: Reading, now: float) -> bool:
        if reading.antennas is None:
            return False
        present, target = reading.antennas
        pushed = max(abs(p - t) for p, t in zip(present, target, strict=True))
        if pushed < poses.ANTENNA_PAT_RAD:
            self._press_since = None
            return False
        if self._press_since is None:
            self._press_since = now
            return False
        if now - self._press_since >= poses.ANTENNA_PAT_HOLD_S:
            self._press_since = None
            return True
        return False

    def _connect(self, now: float) -> None:
        self._next_connect = now + RECONNECT_S
        try:
            status = self.client.status()
            if status.get("state") not in (None, "running"):
                raise RobotUnavailable(f"daemon state is {status.get('state')}")
            self.client.enable_motors()
        except RobotUnavailable as exc:
            if not self._warned:
                log.warning(
                    "no robot: the Reachy Mini daemon is not answering at %s (%s). Running "
                    "without the robot; will keep trying every %d s.",
                    self.client.base_url, exc, RECONNECT_S,
                )
                self._warned = True
            return
        self.attached = True
        self._warned = False
        log.info("robot attached at %s (daemon %s)", self.client.base_url,
                 status.get("version", "unknown version"))
        self._emit(Connected(self.name))
        self.show_state(self._state)

    def _lost(self, now: float, reason: str) -> None:
        log.warning("robot lost (%s); carrying on without it and retrying", reason)
        self.attached = False
        self._next_connect = now + RECONNECT_S
        self._emit(Disconnected(self.name))
