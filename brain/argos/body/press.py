"""The head press: a hand pressing the robot's head, read from its motors.

The robot's daemon reports two head poses: where the head was told to be (the commanded
pose) and where it is (worked out from its six motors). While the head holds still the two
differ by a steady amount, from the head's own weight and the motors' small error, plus a
little wobble. A hand pressing the head moves it away from that resting difference.

So, after every move and half a second of settling, this module first learns the resting
difference over a short moment, and only once that has held steady does it sense anything.
A press is then a change from rest of at least ARGOS_HEAD_PAT_MM millimetres, or of at
least ARGOS_HEAD_PAT_DEG degrees in any angle, held for ARGOS_HEAD_PAT_HOLD_S.

Rule 3 of the task: a pat is never invented. Missing a real press is the safe mistake; a
false one silences a real alert.

- Nothing is sensed during a move of the head or of the wheels, or for half a second after.
  The robot driver calls `reset()` whenever that window is open, so a hold can never start
  before a move and finish after it, and rest is learned again after every move.
- Rest must itself be steady (every reading within half a threshold of the average) before
  it is taken. A head still settling, or already being pressed, is not rest.
- A press must be held. A knock is shorter than the hold, and is not a pat.

Units. The daemon reports metres and radians; this module works in millimetres and degrees.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class HeadPose:
    """A head pose as the daemon reports it: metres, and radians (roll, pitch, yaw)."""

    x: float
    y: float
    z: float
    roll: float
    pitch: float
    yaw: float


@dataclass(frozen=True)
class HeadDiff:
    """Measured minus commanded: millimetres (x, y, z) and degrees (roll, pitch, yaw)."""

    mm: tuple[float, float, float]
    deg: tuple[float, float, float]


def _angle(a: float, b: float) -> float:
    """a - b in degrees, wrapped to -180..180."""
    return math.degrees(math.remainder(a - b, math.tau))


def head_diff(measured: HeadPose, commanded: HeadPose) -> HeadDiff:
    return HeadDiff(
        mm=((measured.x - commanded.x) * 1000.0, (measured.y - commanded.y) * 1000.0,
            (measured.z - commanded.z) * 1000.0),
        deg=(_angle(measured.roll, commanded.roll), _angle(measured.pitch, commanded.pitch),
             _angle(measured.yaw, commanded.yaw)),
    )


def size(diff: HeadDiff, base: HeadDiff | None = None) -> tuple[float, float]:
    """How far `diff` is from `base` (or from nothing): millimetres of distance, and the
    largest angle in degrees."""
    bmm = base.mm if base else (0.0, 0.0, 0.0)
    bdeg = base.deg if base else (0.0, 0.0, 0.0)
    distance = math.dist(diff.mm, bmm)
    angle = max(abs(a - b) for a, b in zip(diff.deg, bdeg, strict=True))
    return distance, angle


def mean(diffs: list[HeadDiff]) -> HeadDiff:
    count = len(diffs)
    return HeadDiff(
        mm=tuple(sum(d.mm[i] for d in diffs) / count for i in range(3)),  # type: ignore[arg-type]
        deg=tuple(sum(d.deg[i] for d in diffs) / count for i in range(3)),  # type: ignore[arg-type]
    )


class HeadPress:
    """Feed it the head's difference about ten times a second while the head holds still; it
    says True once for each press that was held long enough."""

    def __init__(self, mm: float = 5.0, deg: float = 5.0, hold_s: float = 0.5,
                 rest_s: float = 0.3) -> None:
        self.mm = mm
        self.deg = deg
        self.hold_s = hold_s
        self.rest_s = rest_s
        self.rest: HeadDiff | None = None
        self._samples: deque[tuple[float, HeadDiff]] = deque()
        self._since: float | None = None

    def reset(self) -> None:
        """Forget rest and any hold: the head or the base moved, or the state changed."""
        self.rest = None
        self._samples.clear()
        self._since = None

    def update(self, now: float, diff: HeadDiff | None) -> bool:
        """One reading. True when a held press is complete."""
        if diff is None:
            self._since = None
            return False
        if self.rest is None:
            self._learn(now, diff)
            return False
        distance, angle = size(diff, self.rest)
        if distance < self.mm and angle < self.deg:
            self._since = None
            return False
        if self._since is None:
            self._since = now
            return False
        if now - self._since >= self.hold_s:
            self._since = None
            return True
        return False

    def _learn(self, now: float, diff: HeadDiff) -> None:
        self._samples.append((now, diff))
        while now - self._samples[0][0] > self.rest_s * 3:
            self._samples.popleft()
        if len(self._samples) < 3 or now - self._samples[0][0] < self.rest_s:
            return
        average = mean([d for _, d in self._samples])
        steady = all(
            dist <= self.mm / 2 and ang <= self.deg / 2
            for dist, ang in (size(d, average) for _, d in self._samples)
        )
        if steady:
            self.rest = average
            self._samples.clear()
        else:
            self._samples.popleft()
