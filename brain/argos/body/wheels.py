"""The wheels, in the brain: the layer that owns the motors.

The approach (`argos/approach.py`) decides which way to go. This layer decides whether a burst
may happen at all, and it keeps rule 1 of the task whatever the layer above asks:

- It exists only when the wheels are switched on (`ARGOS_WHEELS=1`, or `fake` for a pretend
  base), a keyboard is attached, and the run is not scripted. It is ready only once its
  motors (the guard process, `guard_client.py`) have answered.
- A burst happens only inside an approach begun for the check that is open right now
  (`open_check()` names it; nothing in calm or alert), and only toward a person the camera
  sees at that moment: the newest look must hold a person, come from a frame captured after
  the body last moved (wheels and head alike), and be less than FRESH_S old.
- Power is capped at MAX_POWER whatever the setting or the caller asks, and each burst at
  MAX_BURST_S. In one approach the motors run at most MOTOR_ON_CAP_S in total: a constant
  that no setting raises. One approach per check, and never two within MIN_APPROACH_GAP_S.
- It stops at once on `halt()`, on any change of state to calm or alert, on the stop key
  (`latch()`, which acts straight away from the keyboard's thread and holds until the brain
  is started again), and on `stop()` when the brain stops.
- It reports its movement through `moving_until()`, so the camera holds frames back and no
  pat is taken during a burst or for half a second after (through the BodyHub). It mutes the
  ears through each burst and EARS_TAIL_S after, on the gate's own `motors_until` field, so
  it never fights the voice's `speaking_until`.

Behind it, the guard caps power and burst length again and stops by itself if the brain goes
quiet or dies (`guard.py`).
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable
from typing import Any, Protocol

from argos.body.base import Emit
from argos.body.guard import HEARTBEAT_TIMEOUT_S, MAX_BURST_S, MAX_POWER
from argos.clock import Clock

log = logging.getLogger("argos.wheels")

# The total time the motors may run in one approach. No setting raises it.
MOTOR_ON_CAP_S = 1.2
# A look at the person must be younger than this to steer by.
FRESH_S = 0.5
# The ears stay shut this long after each burst.
EARS_TAIL_S = 0.5
# Shorter than this is not worth a burst.
MIN_BURST_S = 0.1
# A floor under ARGOS_APPROACH_REST_S, kept here too.
MIN_APPROACH_GAP_S = 30.0
# At full power on a fresh 12 V pack the base would move about this fast (the team's figure).
TOP_SPEED_M_S = 2.0


def worst_case_m() -> float:
    """The furthest one approach could take the base: every second of motor time at the cap,
    on fresh cells, on a hard floor, in a straight line."""
    return MOTOR_ON_CAP_S * MAX_POWER * TOP_SPEED_M_S


class Motors(Protocol):
    """What the wheels drive: the guard process, or a pretend set for tests and laptops."""

    name: str

    def start(self) -> str | None: ...  # None when ready, else why not

    def drive(self, left: float, right: float, seconds: float) -> bool: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def alive(self) -> bool: ...


class FakeMotors:
    """Motors that move nothing. They keep every command, with the clock's time, for tests,
    and log each burst, for watching the approach on a laptop (`ARGOS_WHEELS=fake`)."""

    name = "pretend"

    def __init__(self, clock: Clock, fail_start: str | None = None) -> None:
        self.clock = clock
        self.fail_start = fail_start
        self.commands: list[tuple[str, float, float, float, float]] = []
        self.running_until = 0.0
        self.closed = False

    def start(self) -> str | None:
        return self.fail_start

    def drive(self, left: float, right: float, seconds: float) -> bool:
        now = self.clock.now()
        self.commands.append(("drive", now, left, right, seconds))
        self.running_until = now + seconds
        log.info("pretend wheels: left %+.2f, right %+.2f for %.2f s", left, right, seconds)
        return True

    def stop(self) -> None:
        now = self.clock.now()
        self.commands.append(("stop", now, 0.0, 0.0, 0.0))
        self.running_until = min(self.running_until, now)

    def close(self) -> None:
        self.stop()
        self.closed = True

    def alive(self) -> bool:
        return not self.closed

    def running(self, at: float | None = None) -> bool:
        at = self.clock.now() if at is None else at
        return at < self.running_until

    def drives(self) -> list[tuple[str, float, float, float, float]]:
        return [c for c in self.commands if c[0] == "drive"]


def _shape(power: float, invert: bool) -> float:
    try:
        power = float(power)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(power):
        return 0.0
    power = max(-MAX_POWER, min(MAX_POWER, power))
    return -power if invert else power


class Wheels:
    """The base, as one more body in the hub. See the module's notes for the rules."""

    name = "wheels"

    def __init__(
        self,
        motors: Motors,
        clock: Clock,
        power: float,
        turn_power: float,
        invert_left: bool = False,
        invert_right: bool = False,
        pretend: bool = False,
        threaded: bool = True,
    ) -> None:
        self.motors = motors
        self.clock = clock
        self.power = min(MAX_POWER, max(0.0, power))
        self.turn_power = min(MAX_POWER, max(0.0, turn_power))
        self.invert_left = invert_left
        self.invert_right = invert_right
        self.pretend = pretend
        self.threaded = threaded
        # Set by the brain: the open check's id (None in calm or alert), the newest look, the
        # whole body's movement, the ears' gate.
        self.open_check: Callable[[], str | None] = lambda: None
        self.look: Callable[[], Any] = lambda: None
        self.moved_until: Callable[[], float] = self.moving_until
        self.gate: Any = None
        self.ready = False
        self.latched = False
        self.broken: str | None = None
        self._lock = threading.RLock()
        self._approach: str | None = None
        self._began: set[str] = set()
        self._last_begin = -math.inf
        self._motor_s = 0.0
        self._moving_until = 0.0
        self._last_burst_end = -math.inf
        self._stopped = False

    # ------------------------------------------------------------------ Body

    def start(self, emit: Emit) -> None:
        if self.threaded:  # starting the guard can take a second; never on the brain's thread
            threading.Thread(target=self._start_motors, name="argos-wheels", daemon=True).start()
        else:
            self._start_motors()

    def _start_motors(self) -> None:
        try:
            reason = self.motors.start()
        except Exception as exc:  # anything at all: the brain carries on without wheels
            reason = f"{type(exc).__name__}: {exc}"
        with self._lock:
            if self._stopped:
                return
            if reason:
                self.broken = reason
                log.warning("wheels: switched on, but %s. Running without wheels.", reason)
                return
            self.ready = True
        log.info("wheels: ready (%s); power capped at %.2f; they stop on the space or x key",
                 self.motors.name, MAX_POWER)

    def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
        if state != "checking":
            self.end(f"the state is now {state}")

    def stood_down(self) -> None:
        self.end("the check stood down")

    def beep(self, ms: int) -> bool:
        return False

    def caps(self) -> list[str]:
        return []

    def fw(self) -> str | None:
        return None

    def moving_until(self) -> float:
        return self._moving_until

    def stop(self) -> None:
        """The brain is stopping, for whatever reason: stop, and let the pins go."""
        with self._lock:
            self._stopped = True
            self.halt("the brain is stopping")
            self._approach = None
            self.ready = False
        try:
            self.motors.close()
        except Exception as exc:
            log.warning("wheels: closing the motors: %s", exc)

    # ------------------------------------------------------------------ for the approach

    @property
    def last_burst_end(self) -> float:
        return self._last_burst_end

    @property
    def motor_s(self) -> float:
        """Motor time used in the current (or last) approach."""
        return self._motor_s

    def begin(self, incident_id: str) -> str | None:
        """Open an approach for this check. Returns why not, or None."""
        with self._lock:
            now = self.clock.now()
            if self.latched:
                return "the stop key was pressed"
            if not self.ready:
                return self.broken or "the wheels are not ready"
            check = self.open_check()
            if check is None:
                return "no check is open"
            if check != incident_id:
                return "that check is not the one open"
            if incident_id in self._began:
                return "this check has had its approach"
            if now - self._last_begin < MIN_APPROACH_GAP_S:
                return "too soon after the last approach"
            self._approach = incident_id
            self._began.add(incident_id)
            self._last_begin = now
            self._motor_s = 0.0
            return None

    def end(self, reason: str) -> None:
        """Close the approach, stopping the base at once."""
        with self._lock:
            self.halt(reason)
            self._approach = None

    def forward(self, seconds: float) -> str | None:
        return self.burst(self.power, self.power, seconds)

    def turn(self, direction: int, seconds: float) -> str | None:
        """direction +1 turns to the robot's left (counter-clockwise from above), -1 to its
        right. Tank steering: one side back, the other forward."""
        power = self.turn_power if direction > 0 else -self.turn_power
        return self.burst(-power, power, seconds)

    def burst(self, left: float, right: float, seconds: float) -> str | None:
        """One short burst, if every rule allows it. Returns why not, or None."""
        with self._lock:
            now = self.clock.now()
            refusal = self._refusal(now)
            if refusal is not None:
                self.halt(refusal)
                return refusal
            seconds = min(float(seconds), MAX_BURST_S, MOTOR_ON_CAP_S - self._motor_s)
            if not seconds >= MIN_BURST_S:
                self.halt("the motor time for this approach is used up")
                return "the motor time for this approach is used up"
            left = _shape(left, self.invert_left)
            right = _shape(right, self.invert_right)
            try:
                sent = self.motors.drive(left, right, seconds)
            except Exception as exc:
                sent = False
                log.warning("wheels: the motors failed (%s)", exc)
            if not sent:
                self.broken = "the motors stopped answering"
                self.ready = False
                self.halt(self.broken)
                return self.broken
            self._motor_s += seconds
            self._moving_until = now + seconds
            self._last_burst_end = now + seconds
            if self.gate is not None:
                self.gate.motors_until = max(getattr(self.gate, "motors_until", 0.0),
                                             now + seconds + EARS_TAIL_S)
            return None

    def _refusal(self, now: float) -> str | None:
        if self.latched:
            return "the stop key was pressed"
        if not self.ready or not self.motors.alive():
            return self.broken or "the wheels are not ready"
        if self._approach is None:
            return "no approach is open"
        check = self.open_check()
        if check is None:
            return "no check is open"
        if check != self._approach:
            return "the approach was for another check"
        look = self.look()
        if look is None or getattr(look, "pose", None) is None:
            return "nobody is in view"
        if look.t <= max(self._last_burst_end, self.moved_until()):
            return "no fresh look since the body last moved"
        if now - look.t >= FRESH_S:
            return "the newest look is too old"
        return None

    def halt(self, reason: str) -> None:
        """Stop the motors now. Safe to call at any time, from any thread."""
        with self._lock:
            now = self.clock.now()
            moving = now < self._moving_until
            try:
                self.motors.stop()
            except Exception as exc:
                log.warning("wheels: stop failed (%s); the guard stops by itself within %g s",
                            exc, HEARTBEAT_TIMEOUT_S)
            if moving:
                self._moving_until = now
                self._last_burst_end = now
                if self.gate is not None:
                    self.gate.motors_until = now + EARS_TAIL_S
                log.info("wheels stopped: %s", reason)

    def latch(self) -> None:
        """The stop key. Called straight from the keyboard's thread, not through the brain's
        queue. The wheels stay off until the brain is started again."""
        self.latched = True
        with self._lock:
            self.halt("the stop key")
            self._approach = None
        log.warning("stop key: the wheels are off until the brain is started again")
