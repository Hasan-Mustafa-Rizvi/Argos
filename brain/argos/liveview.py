"""The live view of contract section 6: frames to the private broadcast topic, never stored.

Only when `ARGOS_LIVE_VIEW=1`. A missing value means off, and then this module is not even
started.

Each frame goes out as one Supabase Realtime broadcast over its own HTTP API, as a private
message, with the secret key:

    POST {SUPABASE_URL}/realtime/v1/api/broadcast/view%3A<device id>/events/frame?private=true
    apikey: <key>            (and Authorization: Bearer <key> for a legacy JWT key)
    body: {"seq": 0, "at": "...", "w": 320, "h": 240, "jpeg": "<base64>"}

This path sends a message over the socket and stores nothing. It never goes through the
database (`realtime.send()` or any SQL), which would keep the message in a table. The
single-message endpoint is used, not the batch one, because it answers 403 when a private
message is refused, where the batch endpoint reports success either way.

Sending never slows detection: the live view reads the camera's latest frame on its own
thread, and hands it to a sender with room for one frame. If the network is slow, frames
are dropped, never queued.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from argos import images
from argos.clock import Clock
from argos.store import auth_headers

log = logging.getLogger("argos.liveview")

MAX_SIDE = 480
MAX_BYTES = 100_000
MAX_FPS = 8.0
QUALITIES = (70, 55, 40, 30)


def topic(device_id: str) -> str:
    return f"view:{device_id}"


def encode_frame(image: Any, seq: int, at: str, max_side: int = MAX_SIDE) -> dict[str, Any] | None:
    """The `frame` message, or None if no quality fits under 100 KB."""
    small = images.scaled(image, max_side)
    height, width = small.shape[:2]
    for quality in QUALITIES:
        data = images.jpeg(small, max_side=max_side, quality=quality)
        message = {"seq": seq, "at": at, "w": int(width), "h": int(height),
                   "jpeg": base64.b64encode(data).decode("ascii")}
        if len(json.dumps(message, separators=(",", ":")).encode()) < MAX_BYTES:
            return message
    return None


class Broadcaster:
    def __init__(self, url: str, key: str, device_id: str, timeout_s: float = 2.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.path = f"/realtime/v1/api/broadcast/{quote(topic(device_id), safe='')}/events/frame"
        self._client = httpx.Client(base_url=url, headers=auth_headers(key), timeout=timeout_s,
                                    transport=transport)
        self._warned = False
        self.last_error = ""  # why the last frame was not sent, for `--check`

    def send(self, message: dict[str, Any]) -> bool:
        try:
            response = self._client.post(self.path, params={"private": "true"}, json=message)
        except httpx.HTTPError as exc:
            self.last_error = type(exc).__name__
            self._warn(self.last_error)
            return False
        if response.status_code >= 300:
            self.last_error = f"HTTP {response.status_code}"
            self._warn(self.last_error)
            return False
        self._warned = False
        self.last_error = ""
        return True

    def _warn(self, reason: str) -> None:
        if not self._warned:
            log.warning("live view frame not sent (%s); frames are dropped until it works",
                        reason)
            self._warned = True

    def close(self) -> None:
        self._client.close()


class LiveView:
    def __init__(self, frames: Callable[[], Any], send: Callable[[dict[str, Any]], bool],
                 clock: Clock, fps: float = 4.0) -> None:
        self.frames = frames
        self.send = send
        self.clock = clock
        self.period = 1.0 / min(MAX_FPS, max(0.5, fps))
        self.seq = 0
        self.dropped = 0
        self.sent = 0
        self._slot: Any = None
        self._slot_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._last_t = -1.0
        self._threads: list[threading.Thread] = []

    def offer(self, frame: Any) -> bool:
        """Hand a frame to the sender without waiting. False if one is already waiting (this
        one is dropped)."""
        with self._slot_lock:
            if self._slot is not None:
                self.dropped += 1
                return False
            self._slot = frame
        self._wake.set()
        return True

    def send_waiting(self) -> bool:
        """Encode and send the waiting frame, if any. Public so tests can drive it."""
        with self._slot_lock:
            frame, self._slot = self._slot, None
        self._wake.clear()
        if frame is None:
            return False
        message = encode_frame(images.image_of(frame), self.seq, frame.at)
        if message is None:
            self.dropped += 1
            return False
        if self.send(message):
            self.seq += 1
            self.sent += 1
            return True
        self.dropped += 1
        return False

    def tick(self) -> None:
        frame = self.frames()
        if frame is not None and frame.t > self._last_t:
            self._last_t = frame.t
            self.offer(frame)

    def start(self) -> None:
        log.info("live view on: %.1f frames a second to the private topic", 1 / self.period)
        for target, name in ((self._produce, "argos-live"), (self._consume, "argos-live-send")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=2.0)

    def _produce(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.period)

    def _consume(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(1.0)
            try:
                self.send_waiting()
            except Exception:
                log.exception("live view send error")
