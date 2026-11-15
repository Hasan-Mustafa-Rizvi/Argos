"""One camera, opened once, read on its own thread, shared by everyone who needs a frame.

Frames live in memory only. Nothing here writes a frame to disk or to a log.

Which camera (`ARGOS_CAMERA`):
- `auto`: on Linux, the robot's camera, found by the names the robot's own software looks
  for ("Reachy", "Arducam_12MP", "imx708"); it is a plain USB camera once the robot's daemon
  runs with `--no-media`. Else device 0. On Windows, device 0: with the robot plugged into a
  laptop, set the robot camera's number (often 1).
- `off`: no camera.
- a number (`0`, `1`): that device index. A path (`/dev/video2`): that device.
- `name:<text>`: on Linux, the first video device whose name contains the text.

On Windows the camera is opened through DirectShow, which opens much faster than the default
backend. Opening can still take seconds, so it happens on the camera's own thread and the
brain does not wait. A camera another program holds fails to open: that is logged once, and
the camera is tried again every 15 seconds.

Frames taken while the robot's head is moving (and for a short settle time after) are not
handed out as still frames, so detection and the snapshot never use a blurred frame.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from argos.clock import Clock

log = logging.getLogger("argos.camera")

SETTLE_S = 0.3
STALE_S = 2.0
RETRY_S = 15.0
ROBOT_CAMERA_NAMES = ("Reachy", "Arducam_12MP", "imx708")


@dataclass(frozen=True)
class Frame:
    image: Any  # numpy array, height x width x 3, BGR, uint8
    t: float  # monotonic capture time
    at: str  # ISO capture time


def find_linux_camera(name_part: str) -> str | None:
    base = Path("/sys/class/video4linux")
    if not base.exists():
        return None
    for device in sorted(base.iterdir()):
        try:
            name = (device / "name").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if name_part.lower() in name.lower():
            return f"/dev/{device.name}"
    return None


def resolve(spec: str) -> int | str | None:
    """The device to open, from the ARGOS_CAMERA value."""
    spec = spec.strip()
    if spec.lower() == "off":
        return None
    if spec.lower() in ("", "auto"):
        if sys.platform.startswith("linux"):
            # The names the robot's own software looks for, in its order.
            for name in ROBOT_CAMERA_NAMES:
                if found := find_linux_camera(name):
                    return found
        return 0
    if spec.lower().startswith("name:"):
        return find_linux_camera(spec[5:]) if sys.platform.startswith("linux") else None
    if spec.isdigit():
        return int(spec)
    return spec


def open_capture(device: int | str, width: int, height: int) -> Any:
    import cv2

    if os.name == "nt" and isinstance(device, int):
        capture = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    elif sys.platform.startswith("linux"):
        capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    else:
        capture = cv2.VideoCapture(device)
    if not capture.isOpened():
        capture.release()
        raise OSError(f"camera {device!r} did not open (missing, or held by another program)")
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


class Camera:
    def __init__(
        self,
        device: int | str,
        clock: Clock,
        width: int = 640,
        height: int = 480,
        moving_until: Callable[[], float] = lambda: 0.0,
        opener: Callable[[int | str, int, int], Any] = open_capture,
    ) -> None:
        self.device = device
        self.clock = clock
        self.width = width
        self.height = height
        self.moving_until = moving_until
        self.opener = opener
        self._lock = threading.Lock()
        self._latest: Frame | None = None
        self._still: Frame | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._warned = False
        self.opened = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="argos-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def latest(self) -> Frame | None:
        """The newest frame taken while the head was still. For detection and the snapshot."""
        with self._lock:
            frame = self._still
        if frame is None or self.clock.now() - frame.t > STALE_S:
            return None
        return frame

    def latest_any(self) -> Frame | None:
        """The newest frame, moving or not. For the live view, which is only for looking."""
        with self._lock:
            frame = self._latest
        if frame is None or self.clock.now() - frame.t > STALE_S:
            return None
        return frame

    def put(self, image: Any) -> None:
        """Store a captured image as the newest frame. The capture thread calls this."""
        now = self.clock.now()
        frame = Frame(image, now, self.clock.iso())
        still = now >= self.moving_until() + SETTLE_S
        with self._lock:
            self._latest = frame
            if still:
                self._still = frame

    def _run(self) -> None:
        capture = None
        while not self._stop.is_set():
            if capture is None:
                try:
                    capture = self.opener(self.device, self.width, self.height)
                except Exception as exc:
                    if not self._warned:
                        log.warning("no camera: %s. Carrying on without it; retrying every "
                                    "%d s.", exc, RETRY_S)
                        self._warned = True
                    self._stop.wait(RETRY_S)
                    continue
                self.opened = True
                self._warned = False
                log.info("camera %r open", self.device)
            ok, image = capture.read()
            if not ok or image is None:
                log.warning("camera %r stopped giving frames; reopening", self.device)
                capture.release()
                capture = None
                self.opened = False
                self._stop.wait(1.0)
                continue
            self.put(image)
        if capture is not None:
            capture.release()
