"""Every pose and movement of the robot, in one place, to tune by eye.

Units: head angles in degrees, head height `z` in millimetres, antennas in radians.
The values are sent to the Reachy Mini daemon as `head_pose` {x, y, z, roll, pitch, yaw} in
metres and radians, and `antennas` as two joint angles, in the order the daemon reports them.

Conventions to confirm on the real robot (they could not be checked without one):
- `yaw` positive turns the head to the robot's left.
- `pitch` negative tilts the head up.
- Antennas: (0, 0) is straight up. The daemon's own start pose is (-0.17, +0.17), and its
  sleep pose (-3.05, +3.05) folds them down, so (-a, +a) with a growing lowers both
  symmetrically. (+a, -a) tips them the other way.

The movements are slow on purpose. The robot sits in someone's room all day.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Pose:
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    z: float = 0.0
    antennas: tuple[float, float] = (-0.45, 0.45)


@dataclass(frozen=True)
class Move:
    pose: Pose
    duration: float
    hold: float = 0.0  # seconds to wait after the move ends before the next one


@dataclass(frozen=True)
class Limits:
    """Our own limits, well inside the robot's (pitch and roll 40 deg, yaw 180 deg, and at
    most 65 deg between head and body yaw). The body never turns: body yaw is always 0."""

    pitch: tuple[float, float] = (-25.0, 25.0)
    roll: tuple[float, float] = (-15.0, 15.0)
    yaw: tuple[float, float] = (-50.0, 50.0)
    z: tuple[float, float] = (-5.0, 15.0)
    antenna: tuple[float, float] = (-1.2, 1.2)
    min_duration_s: float = 0.5
    max_head_deg_per_s: float = 60.0
    max_head_mm_per_s: float = 20.0
    max_antenna_rad_per_s: float = 2.5


LIMITS = Limits()


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return min(bounds[1], max(bounds[0], float(value)))


def clamp(pose: Pose, limits: Limits = LIMITS) -> Pose:
    return Pose(
        pitch=_clamp(pose.pitch, limits.pitch),
        roll=_clamp(pose.roll, limits.roll),
        yaw=_clamp(pose.yaw, limits.yaw),
        z=_clamp(pose.z, limits.z),
        antennas=(_clamp(pose.antennas[0], limits.antenna),
                  _clamp(pose.antennas[1], limits.antenna)),
    )


def safe_duration(start: Pose, end: Pose, wanted: float, limits: Limits = LIMITS) -> float:
    """At least `wanted`, at least the minimum, and long enough to stay under every speed
    limit."""
    head = max(abs(end.pitch - start.pitch), abs(end.roll - start.roll), abs(end.yaw - start.yaw))
    antenna = max(abs(end.antennas[0] - start.antennas[0]),
                  abs(end.antennas[1] - start.antennas[1]))
    return max(
        wanted,
        limits.min_duration_s,
        head / limits.max_head_deg_per_s,
        abs(end.z - start.z) / limits.max_head_mm_per_s,
        antenna / limits.max_antenna_rad_per_s,
    )


def within(pose: Pose, limits: Limits = LIMITS) -> bool:
    return pose == clamp(pose, limits)


# ---------------------------------------------------------------- calm

REST = Pose()

# Now and then, a small slow sign of life: a slight head tilt and an antenna lift, and back.
CALM_LIFE = (
    Move(Pose(roll=5.0, pitch=-3.0, antennas=(-0.25, 0.65)), 2.0, hold=0.8),
    Move(REST, 2.0),
)
CALM_LIFE_EVERY_S = (25.0, 50.0)

# ---------------------------------------------------------------- checking

# Faces the person (yaw filled in when known), lifts its head a little, antennas straight up.
# Held until the check ends.
CHECKING = Pose(pitch=-8.0, z=8.0, antennas=(0.0, 0.0))
CHECKING_MOVE_S = 1.0


def checking(look_yaw_deg: float | None) -> Pose:
    return replace(CHECKING, yaw=look_yaw_deg or 0.0)


# ---------------------------------------------------------------- alert

# Head up, antennas sweeping wide and back, again and again. Big enough to read across a
# room, slow enough not to look frantic.
_ALERT_HEAD = dict(pitch=-12.0, z=12.0)
ALERT_CYCLE = (
    Move(Pose(**_ALERT_HEAD, roll=-6.0, antennas=(-1.1, 1.1)), 0.9),
    Move(Pose(**_ALERT_HEAD, roll=6.0, antennas=(0.35, -0.35)), 0.9),
    Move(Pose(**_ALERT_HEAD, roll=-6.0, antennas=(-1.1, 1.1)), 0.9),
    Move(Pose(**_ALERT_HEAD, roll=0.0, antennas=(0.0, 0.0)), 0.9, hold=0.8),
)

# ---------------------------------------------------------------- standing down

# A small nod and a wiggle, then rest.
STOOD_DOWN = (
    Move(Pose(pitch=8.0, antennas=(-0.15, 0.6)), 0.6),
    Move(Pose(pitch=-4.0, antennas=(-0.6, 0.15)), 0.6),
    Move(REST, 1.2),
)

# ---------------------------------------------------------------- the antenna as a pat

# A press or a pull moves an antenna away from where the motor is holding it. Read as a pat
# only while the robot holds still in `checking`.
ANTENNA_PAT_RAD = 0.35
ANTENNA_PAT_HOLD_S = 0.15
ANTENNA_PAT_COOLDOWN_S = 1.5
SETTLE_S = 0.3
