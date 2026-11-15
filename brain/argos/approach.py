"""The approach: during a check, Argos turns toward the person and comes a little closer, so
that it asks from beside them and its camera has a better view.

When it starts. Only when the wheels are on and ready, after "Are you okay?" has finished
playing, once per check, never on a check resumed after a restart, never in a scripted run,
and not within ARGOS_APPROACH_REST_S of the end of the last approach (the brain checks those;
the wheels check the rest). The wait for an answer is not touched: the check escalates
exactly when it would without wheels.

How it steers. First the head is turned level and straight ahead and held there, so that
where the person is in the picture is where they are from the base. Then, in a loop:

1. Look: a pose from a frame captured after the body last stopped, less than half a second
   old. None within LOOK_WAIT_S: stop.
2. Nobody in that look: stop. It never searches.
3. Close enough: stop. The outline of their body points touches the bottom edge or a side
   edge of the picture, or too few of their body points can be seen to trust. From 200 mm
   above the floor a person lying down is a low band across the picture and a standing one
   overfills it quickly, so size alone is not used; the motor-time cap is the real limit.
4. In the left or right third of the picture: a short turn burst that way. In the middle
   third: a short burst forward.
5. A quiet gap of GAP_S, so an answer can be heard, then look again.

Turning on four fixed wheels scrubs, and at low power on carpet the base may not turn at all.
A turn that does not move the person in the picture counts as stalled; after STALL_LIMIT of
them the approach stops and says to raise ARGOS_WHEELS_TURN_POWER. It never raises power by
itself. A second change of turning direction also stops it, so it cannot hunt.

It ends, and the base stops at once: at ARGOS_APPROACH_MAX_S after it began, however far it
got; on any of the stops above; when the check ends; on the stop key; when the brain stops.

Ears: the listener is muted through each burst and half a second after (`wheels.py`), and the
gaps let an answer through. `deaf_s_max()` is the most of a check's wait that can be lost.
Eyes: the camera holds frames back while the body moves, and every look must come from a
frame captured after it stopped. Nothing new is recorded: an approach is not an event.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from argos.body.wheels import EARS_TAIL_S, FRESH_S, MOTOR_ON_CAP_S, Wheels
from argos.clock import Clock

log = logging.getLogger("argos.approach")

TURN_BURST_S = 0.25
FORWARD_BURST_S = 0.35
GAP_S = 1.5
SETTLE_S = 0.3  # after the head's move, before looking
LOOK_WAIT_S = 1.5
EDGE = 0.04  # a share of the picture: this close to an edge is touching it
MIN_POINTS = 6  # of the 13 body points the brain tracks
STALL_SHIFT = 0.03  # a share of the picture's width
STALL_LIMIT = 2
REVERSAL_LIMIT = 1


def deaf_s_max(approach_max_s: float) -> float:
    """The most seconds of a check's wait that one approach can keep the ears shut: every
    burst that fits, each with its half second after, within the motor-time cap."""
    shortest_cycle = TURN_BURST_S + GAP_S
    bursts = int(approach_max_s // shortest_cycle) + 1
    motor = min(MOTOR_ON_CAP_S, bursts * FORWARD_BURST_S)
    return motor + bursts * EARS_TAIL_S


def decide(pose: Any, edge: float = EDGE, min_points: int = MIN_POINTS) -> tuple[str, int, str]:
    """From one person's pose: ("close", 0, why), ("turn", +1 left / -1 right, why) or
    ("forward", 0, why)."""
    points = [p for name in pose.points if (p := pose.visible(name))]
    if len(points) < min_points:
        return "close", 0, "too few of their body points can be seen to trust"
    box = pose.box()
    width, height = pose.width, pose.height
    if box is None:
        return "close", 0, "too few of their body points can be seen to trust"
    left, _, right, bottom = box
    if bottom >= height * (1 - edge):
        return "close", 0, "they reach the bottom edge of the picture"
    if left <= width * edge or right >= width * (1 - edge):
        return "close", 0, "they reach a side edge of the picture"
    middle = (left + right) / 2
    if middle < width / 3:
        return "turn", +1, "they are in the left third of the picture"
    if middle > width * 2 / 3:
        return "turn", -1, "they are in the right third of the picture"
    return "forward", 0, "they are in the middle third of the picture"


class Approach:
    """Stepped by the brain's thread, with the brain's clock. See the module's notes."""

    def __init__(
        self,
        wheels: Wheels,
        look: Callable[[], Any],
        face_forward: Callable[[], bool],
        moved_until: Callable[[], float],
        clock: Clock,
        max_s: float,
        min_score: float = 0.5,
        needs_head: bool = True,
        on_end: Callable[[str], None] | None = None,
    ) -> None:
        self.wheels = wheels
        self.look = look
        self.face_forward = face_forward
        self.moved_until = moved_until
        self.clock = clock
        self.max_s = max_s
        self.min_score = min_score
        self.needs_head = needs_head
        self.on_end = on_end or (lambda reason: None)
        self.incident_id: str | None = None
        self.last_reason = ""
        self.bursts = 0
        self._phase = "idle"
        self._started = 0.0
        self._until = 0.0
        self._last_turn = 0
        self._turn_from: float | None = None
        self._stalls = 0
        self._reversals = 0

    @property
    def active(self) -> bool:
        return self.incident_id is not None

    def start(self, incident_id: str) -> str | None:
        """Begin, after the question. Returns why not, or None."""
        refusal = self.wheels.begin(incident_id)
        if refusal is not None:
            return refusal
        if not self.face_forward() and self.needs_head:
            self.wheels.end("the head is not there to point the camera")
            return "the robot's head is not attached, so where the camera points is not known"
        now = self.clock.now()
        self.incident_id = incident_id
        self.bursts = 0
        self._started = now
        self._phase = "facing"
        self._last_turn = 0
        self._turn_from = None
        self._stalls = 0
        self._reversals = 0
        log.info("approach: begun; the head turns level and straight ahead")
        return None

    def cancel(self, reason: str) -> None:
        if self.active:
            self._finish(reason)

    def step(self, now: float) -> None:
        if not self.active:
            return
        if now >= self._started + self.max_s:
            self._finish("the time limit for an approach")
            return
        # Each phase may hand over to the next in the same step.
        if self._phase == "facing" and now >= self.moved_until() + SETTLE_S:
            self._phase, self._until = "looking", now + LOOK_WAIT_S
        if self._phase == "bursting" and now >= self.wheels.moving_until():
            self._phase, self._until = "gap", self.wheels.moving_until() + GAP_S
        if self._phase == "gap" and now >= self._until:
            self._phase, self._until = "looking", now + LOOK_WAIT_S
        if self._phase == "looking":
            self._look(now)

    def _fresh(self, look: Any, now: float) -> bool:
        if look is None:
            return False
        after = max(self.wheels.last_burst_end, self.moved_until())
        return look.t > after and now - look.t < FRESH_S

    def _look(self, now: float) -> None:
        look = self.look()
        if not self._fresh(look, now):
            if now >= self._until:
                self._finish("no fresh look from the camera")
            return
        pose = look.pose
        if pose is None or pose.score < self.min_score:
            self._finish("the person is not in view")
            return
        what, direction, why = decide(pose)
        if what == "close":
            self._finish(f"close enough: {why}")
            return
        middle = (pose.box()[0] + pose.box()[2]) / 2 / pose.width
        if what == "turn":
            if self._turn_from is not None and abs(middle - self._turn_from) < STALL_SHIFT:
                self._stalls += 1
                if self._stalls >= STALL_LIMIT:
                    self._finish("the base did not turn (raise ARGOS_WHEELS_TURN_POWER after "
                                 "a wheel test)")
                    return
            if self._last_turn and direction != self._last_turn:
                self._reversals += 1
                if self._reversals > REVERSAL_LIMIT:
                    self._finish("it could not settle on the person")
                    return
            refusal = self.wheels.turn(direction, TURN_BURST_S)
            self._last_turn, self._turn_from = direction, middle
        else:
            refusal = self.wheels.forward(FORWARD_BURST_S)
            self._turn_from = None
        if refusal is not None:
            self._finish(refusal)
            return
        self.bursts += 1
        log.info("approach: %s; %s", why, "turning" if what == "turn" else "forward")
        self._phase = "bursting"

    def _finish(self, reason: str) -> None:
        self.wheels.end(f"the approach ended: {reason}")
        log.info("approach: ended (%s) after %d bursts, %.2f s of motor time", reason,
                 self.bursts, self.wheels.motor_s)
        self.incident_id = None
        self._phase = "idle"
        self.last_reason = reason
        self.on_end(reason)
