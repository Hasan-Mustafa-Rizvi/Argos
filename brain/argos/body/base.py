"""One interface for every body, and a hub that drives any combination of them.

Any mix may be present: none, the robot, the sensor board, or both. A body that fails is
logged and the others carry on.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("argos.body")

TELEMETRY_STALE_S = 3.0


@dataclass(frozen=True)
class Pat:
    source: str


@dataclass(frozen=True)
class Tipped:
    source: str


@dataclass(frozen=True)
class Upright:
    source: str


@dataclass(frozen=True)
class Telemetry:
    source: str
    temp_c: float | None
    tilt_deg: float | None
    touch: bool | None


@dataclass(frozen=True)
class Connected:
    source: str


@dataclass(frozen=True)
class Disconnected:
    source: str


BodyEvent = Pat | Tipped | Upright | Telemetry | Connected | Disconnected
Emit = Callable[[BodyEvent], None]


class Body(Protocol):
    name: str

    def start(self, emit: Emit) -> None: ...

    def show_state(self, state: str, look_yaw_deg: float | None = None) -> None: ...

    def stood_down(self) -> None: ...

    def beep(self, ms: int) -> bool: ...

    def caps(self) -> list[str]: ...

    def fw(self) -> str | None: ...

    def moving_until(self) -> float: ...

    def stop(self) -> None: ...


class BodyHub:
    """Forwards each command to every body and merges what they report."""

    def __init__(self, bodies: list[Body], now: Callable[[], float]) -> None:
        self.bodies = list(bodies)
        self._now = now
        self._lock = threading.Lock()
        self._telemetry: tuple[float, Telemetry] | None = None
        self._emit: Emit = lambda event: None
        # A body that senses a pat must know when any part moves, the wheels included.
        for body in self.bodies:
            if hasattr(body, "body_moving_until"):
                body.body_moving_until = self.moving_until  # type: ignore[attr-defined]

    def start(self, emit: Emit) -> None:
        self._emit = emit
        for body in self.bodies:
            self._safely(body, "start", lambda b=body: b.start(self._on_event))
        if not self.bodies:
            log.info("no body attached: running with none")

    def _on_event(self, event: BodyEvent) -> None:
        if isinstance(event, Telemetry):
            with self._lock:
                self._telemetry = (self._now(), event)
        self._emit(event)

    def _safely(self, body: Body, what: str, call: Callable[[], object]) -> object:
        try:
            return call()
        except Exception as exc:
            log.error("%s: %s failed: %s", body.name, what, exc)
            return None

    def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
        for body in self.bodies:
            self._safely(body, "show_state", lambda b=body: b.show_state(state, look_yaw_deg))

    def stood_down(self) -> None:
        for body in self.bodies:
            self._safely(body, "stood_down", body.stood_down)

    def beep(self, ms: int) -> bool:
        beeped = False
        for body in self.bodies:
            beeped = bool(self._safely(body, "beep", lambda b=body: b.beep(ms))) or beeped
        return beeped

    def caps(self) -> list[str]:
        merged: list[str] = []
        for body in self.bodies:
            for cap in self._safely(body, "caps", body.caps) or []:
                if cap not in merged:
                    merged.append(cap)
        return merged

    def fw(self) -> str | None:
        for body in self.bodies:
            value = self._safely(body, "fw", body.fw)
            if value:
                return str(value)
        return None

    def moving_until(self) -> float:
        """When the last movement of any part ends: the robot's head, the wheels. The camera
        holds frames back and no pat is taken until a little after this."""
        times = [self._safely(body, "moving_until", body.moving_until) for body in self.bodies]
        return max([t for t in times if isinstance(t, (int, float))], default=0.0)

    def face_forward(self) -> bool:
        """Head level and straight ahead, for the approach. True if a body will do it. A body
        without a head simply does not have the method."""
        done = False
        for body in self.bodies:
            method = getattr(body, "face_forward", None)
            if method is not None:
                done = bool(self._safely(body, "face_forward", method)) or done
        return done

    def sensors(self) -> tuple[float | None, float | None]:
        """Latest temperature and tilt, or None when no fresh telemetry has arrived."""
        with self._lock:
            if not self._telemetry:
                return None, None
            at, telemetry = self._telemetry
        if self._now() - at > TELEMETRY_STALE_S:
            return None, None
        return telemetry.temp_c, telemetry.tilt_deg

    def stop(self) -> None:
        for body in self.bodies:
            self._safely(body, "stop", body.stop)
