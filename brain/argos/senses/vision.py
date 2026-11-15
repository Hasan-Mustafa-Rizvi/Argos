"""Seeing: person present, seconds still, and the `fall` and `stillness` triggers.

Method. One pose model (MediaPipe Pose Landmarker, lite) gives body points for one person.
Two small, plain rules sit on top of it:

- **Fall: a person lying down, for a while.** The torso (shoulders to hips) is far from
  upright AND the body is wider than it is tall, in most frames over `ARGOS_FALL_HOLD_S`
  (2 s). Bending to pick something up tilts the torso but keeps the body tall, and does not
  last. It fires once per time on the floor, never again until the person has got up.
- **Stillness.** Body points are compared with where they were at the last movement, as a
  share of body size, so slow drift adds up and pose jitter does not. `still_s` counts from
  the last movement. It fires once per still spell, when `still_s` reaches
  `ARGOS_STILLNESS_S`.

Both only fire while Argos is calm and a cooldown has passed since the last check ended, so
a person who has just said "I'm fine" is not asked again a second later.

The model runs on a frame at a time, at `ARGOS_DETECT_FPS` (8), on frames scaled to at most
480 pixels wide. It is skipped while the robot's head moves. On a Raspberry Pi 5 this is well
inside one CPU core; on a laptop it is a few milliseconds a frame.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from argos.clock import Clock

log = logging.getLogger("argos.vision")

# MediaPipe pose landmark indices.
POINTS = {
    "nose": 0, "left_shoulder": 11, "right_shoulder": 12, "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16, "left_hip": 23, "right_hip": 24, "left_knee": 25,
    "right_knee": 26, "left_ankle": 27, "right_ankle": 28,
}
VISIBLE = 0.5
ABSENT_AFTER_S = 2.0


@dataclass(frozen=True)
class PersonPose:
    """Body points in pixels (x right, y down) with visibility 0..1, and the frame size."""

    points: dict[str, tuple[float, float, float]]
    width: int
    height: int

    def visible(self, name: str) -> tuple[float, float] | None:
        point = self.points.get(name)
        if point is None or point[2] < VISIBLE:
            return None
        return point[0], point[1]

    @property
    def score(self) -> float:
        core = [self.points[n][2] for n in ("left_shoulder", "right_shoulder", "left_hip",
                                            "right_hip") if n in self.points]
        return sum(core) / len(core) if core else 0.0

    def _mid(self, a: str, b: str) -> tuple[float, float] | None:
        pa, pb = self.visible(a), self.visible(b)
        if pa and pb:
            return (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        return pa or pb

    def torso_angle_deg(self) -> float | None:
        """0 is upright, 90 is lying flat."""
        shoulders = self._mid("left_shoulder", "right_shoulder")
        hips = self._mid("left_hip", "right_hip")
        if not shoulders or not hips:
            return None
        dx, dy = hips[0] - shoulders[0], hips[1] - shoulders[1]
        if dx == 0 and dy == 0:
            return None
        return math.degrees(math.atan2(abs(dx), abs(dy)))

    def box(self) -> tuple[float, float, float, float] | None:
        """Left, top, right, bottom of the visible points."""
        points = [p for name in self.points if (p := self.visible(name))]
        if len(points) < 4:
            return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)

    def size(self) -> float:
        box = self.box()
        if not box:
            return 0.0
        return math.hypot(box[2] - box[0], box[3] - box[1])

    def center_x(self) -> float | None:
        box = self.box()
        return (box[0] + box[2]) / 2 if box else None


class PoseEstimator(Protocol):
    def estimate(self, image: Any, t_ms: int) -> PersonPose | None: ...


class MediaPipePose:
    """MediaPipe Pose Landmarker (Tasks API), lite model, video mode, one person."""

    def __init__(self, model_path: Path, max_width: int = 480) -> None:
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        if not model_path.exists():
            raise FileNotFoundError(f"pose model not found at {model_path} "
                                    "(run: python tools/fetch_models.py)")
        options = mp_vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._max_width = max_width
        self._last_ms = -1

    def estimate(self, image: Any, t_ms: int) -> PersonPose | None:
        import cv2
        import mediapipe as mp

        if t_ms <= self._last_ms:
            t_ms = self._last_ms + 1
        self._last_ms = t_ms
        height, width = image.shape[:2]
        if width > self._max_width:
            scale = self._max_width / width
            image = cv2.resize(image, (self._max_width, int(height * scale)))
            height, width = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = self._landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), t_ms
        )
        if not result.pose_landmarks:
            return None
        marks = result.pose_landmarks[0]
        points = {
            name: (marks[index].x * width, marks[index].y * height,
                   float(marks[index].visibility or 0.0))
            for name, index in POINTS.items()
        }
        return PersonPose(points, width, height)

    def close(self) -> None:
        self._landmarker.close()


# --------------------------------------------------------------------------- the two rules


class FallDetector:
    def __init__(self, angle_deg: float = 60.0, hold_s: float = 2.0, min_score: float = 0.5,
                 share: float = 0.8) -> None:
        self.angle_deg = angle_deg
        self.hold_s = hold_s
        self.min_score = min_score
        self.share = share
        self._window: deque[tuple[float, bool, float]] = deque()
        self._fired = False

    def lying(self, pose: PersonPose) -> tuple[bool, float]:
        """Whether this pose looks like a person lying down, and how sure (0..1)."""
        if pose.score < self.min_score:
            return False, 0.0
        angle = pose.torso_angle_deg()
        box = pose.box()
        if angle is None or box is None:
            return False, 0.0
        wide = (box[2] - box[0]) >= (box[3] - box[1])
        if angle < self.angle_deg or not wide:
            return False, 0.0
        tilt = min(1.0, 0.5 + 0.5 * (angle - self.angle_deg) / max(1.0, 90.0 - self.angle_deg))
        return True, tilt * pose.score

    def update(self, pose: PersonPose | None, now: float) -> float | None:
        """The confidence when a fall is detected now, else None."""
        if pose is not None:
            lying, score = self.lying(pose)
            self._window.append((now, lying, score))
        while self._window and now - self._window[0][0] > self.hold_s:
            self._window.popleft()
        if not self._window:
            return None
        flags = [lying for _, lying, _ in self._window]
        share = sum(flags) / len(flags)
        span = now - self._window[0][0]
        if self._fired:
            if share < 0.2:  # got up: the next time on the floor counts again
                self._fired = False
            return None
        if share >= self.share and span >= self.hold_s * 0.9 and len(flags) >= 3:
            self._fired = True
            scores = [s for _, lying, s in self._window if lying]
            return round(sum(scores) / len(scores), 2)
        return None


class StillnessTracker:
    def __init__(self, stillness_s: float = 60.0, move: float = 0.04,
                 min_score: float = 0.5) -> None:
        self.stillness_s = stillness_s
        self.move = move
        self.min_score = min_score
        self.present = False
        self._last_seen = -math.inf
        self._still_since: float | None = None
        self._reference: PersonPose | None = None
        self._fired = False
        self._scores: deque[float] = deque(maxlen=50)

    def still_s(self, now: float) -> int:
        if not self.present or self._still_since is None:
            return 0
        return int(now - self._still_since)

    def _moved(self, pose: PersonPose) -> bool:
        reference = self._reference
        if reference is None:
            return True
        size = max(pose.size(), reference.size(), 1.0)
        shifts = []
        for name in POINTS:
            a, b = pose.visible(name), reference.visible(name)
            if a and b:
                shifts.append(math.hypot(a[0] - b[0], a[1] - b[1]) / size)
        if len(shifts) < 4:
            return True
        return sum(shifts) / len(shifts) > self.move

    def update(self, pose: PersonPose | None, now: float) -> float | None:
        """The confidence when stillness passes the threshold now, else None."""
        if pose is None or pose.score < self.min_score:
            if now - self._last_seen > ABSENT_AFTER_S:
                self.present = False
                self._still_since = None
                self._reference = None
                self._fired = False
            return None
        self.present = True
        self._last_seen = now
        self._scores.append(pose.score)
        if self._moved(pose):
            self._reference = pose
            self._still_since = now
            self._fired = False
            return None
        if not self._fired and self.still_s(now) >= self.stillness_s:
            self._fired = True
            return round(sum(self._scores) / len(self._scores), 2)
        return None


# --------------------------------------------------------------------------- the loop


class Vision:
    """Runs the pose model on the camera's still frames and posts triggers to the brain."""

    def __init__(
        self,
        frames: Any,
        estimator: PoseEstimator | None,
        clock: Clock,
        fall: FallDetector,
        still: StillnessTracker,
        fps: float = 8.0,
        hfov_deg: float = 70.0,
    ) -> None:
        self.frames = frames
        self.estimator = estimator
        self.clock = clock
        self.fall = fall
        self.still = still
        self.period = 1.0 / fps
        self.hfov_deg = hfov_deg
        self.on_trigger: Callable[[str, float, Any], None] = lambda kind, conf, frame: None
        self.can_trigger: Callable[[], bool] = lambda: True
        self._last_t = -1.0
        self._bearing: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # The brain reads these.

    def reading(self) -> tuple[bool, int]:
        with self._lock:
            return self.still.present, self.still.still_s(self.clock.now())

    def bearing_deg(self) -> float | None:
        """Where the person is, in degrees from straight ahead, positive to the left."""
        with self._lock:
            return self._bearing if self.still.present else None

    # One step, for the thread and for tests.

    def process(self, frame: Any, pose: PersonPose | None) -> None:
        now = self.clock.now()
        with self._lock:
            fell = self.fall.update(pose, now)
            stilled = self.still.update(pose, now)
            if pose is not None and (cx := pose.center_x()) is not None:
                self._bearing = (0.5 - cx / pose.width) * self.hfov_deg
        if not self.can_trigger():
            return
        if fell is not None:
            log.info("fall seen (%.2f)", fell)
            self.on_trigger("fall", fell, frame)
        elif stilled is not None:
            log.info("stillness passed %g s (%.2f)", self.still.stillness_s, stilled)
            self.on_trigger("stillness", stilled, frame)

    def step(self) -> None:
        frame = self.frames.latest() if self.frames else None
        if frame is None or frame.t <= self._last_t:
            return
        self._last_t = frame.t
        pose = None
        if self.estimator is not None:
            try:
                pose = self.estimator.estimate(frame.image, int(frame.t * 1000))
            except Exception as exc:
                log.warning("pose model failed on a frame: %s", exc)
        self.process(frame, pose)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="argos-vision", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            started = self.clock.now()
            try:
                self.step()
            except Exception:
                log.exception("vision loop error")
            self._stop.wait(max(0.0, self.period - (self.clock.now() - started)))
