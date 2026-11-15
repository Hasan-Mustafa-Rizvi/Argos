"""The Reachy Mini Lite body, driven through the robot's own daemon on the same machine.

The daemon (`reachy-mini-daemon`, from Pollen Robotics' `reachy-mini` package) owns the motors
and serves a documented HTTP API on http://localhost:8000. This driver uses four calls:

    GET  /api/daemon/status                 is the robot there
    POST /api/motors/set_mode/enabled       hold position
    POST /api/move/goto                     move head and antennas over a duration
    GET  /api/state/full?with_target_antenna_positions=true
                                            where the antennas are, and where they are held

It does not import the robot's Python package. That package pulls PyGObject, which has no
wheel on Linux and must be compiled on the Pi; talking HTTP keeps the brain's own install
compiler-free. Start the daemon with `--no-media` so it leaves the camera and audio to the
brain (see README).

Movement runs on its own thread, so a slow robot never slows the brain.
"""

from __future__ import annotations

import logging
import math
import random
import threading
from collections import deque
from typing import Any

import httpx

from argos.body import poses
from argos.body.base import Connected, Disconnected, Emit, Pat
from argos.body.poses import Move, Pose
from argos.clock import Clock

log = logging.getLogger("argos.robot")

ROBOT_CAPS = ["head", "antennas", "camera", "voice"]
RECONNECT_S = 10.0
TICK_S = 0.05


class RobotUnavailable(Exception):
    pass


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
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RobotUnavailable(f"{method} {path}: {type(exc).__name__}") from None
        return response.json() if response.content else None

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/api/daemon/status") or {}

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
            "/api/state/full",
            params={"with_antenna_positions": "true", "with_target_antenna_positions": "true"},
        ) or {}
        present, target = state.get("antennas_position"), state.get("target_antennas_position")
        if not (isinstance(present, list) and isinstance(target, list)):
            return None
        if len(present) != 2 or len(target) != 2:
            return None
        return [float(v) for v in present], [float(v) for v in target]

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
    ) -> None:
        self.client = client
        self.clock = clock
        self.antenna_pat = antenna_pat
        self.rng = rng or random.Random()
        self.threaded = threaded
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
            elif self._state == "checking" and self.antenna_pat:
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

    def _sense_pat(self, now: float) -> None:
        if now < self._moving_until + poses.SETTLE_S or now < self._next_press_poll:
            return
        if now < self._pat_quiet_until:
            return
        self._next_press_poll = now + 0.1
        try:
            reading = self.client.antennas()
        except RobotUnavailable as exc:
            self._lost(now, str(exc))
            return
        if reading is None:
            return
        present, target = reading
        pushed = max(abs(p - t) for p, t in zip(present, target, strict=True))
        if pushed < poses.ANTENNA_PAT_RAD:
            self._press_since = None
            return
        if self._press_since is None:
            self._press_since = now
        elif now - self._press_since >= poses.ANTENNA_PAT_HOLD_S:
            self._press_since = None
            self._pat_quiet_until = now + poses.ANTENNA_PAT_COOLDOWN_S
            log.info("antenna pressed: taken as a pat")
            self._emit(Pat("robot antenna"))

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
