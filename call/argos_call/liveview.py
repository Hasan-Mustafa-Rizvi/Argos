"""The live view (contract section 6), read during a call and kept nowhere.

The brain broadcasts frames on the private Realtime topic `view:<device id>`, event `frame`.
This joins that topic over Supabase Realtime's websocket with the backend's secret key (the
contract allows the call agent this one reading, during its call), hands each frame's JPEG to
the picture in memory, and leaves when the call ends. It never writes to the channel.

Reader rules from the contract: a frame whose `seq` is lower than the last one shown is
dropped, until the view has stopped (no frame for 5 seconds, counted from arrival); then the
last `seq` is forgotten. Extra fields are ignored.

Protocol: Phoenix channels, JSON, `vsn=1.0.0`, as supabase-js speaks it. Join with
`config.private = true`; a heartbeat every 25 seconds; broadcasts arrive as
`{"event": "broadcast", "payload": {"event": "frame", "payload": {...}}}`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Callable
from typing import Any

from argos_call.clock import Clock

log = logging.getLogger("argos_call.liveview")

STOPPED_AFTER_S = 5.0
HEARTBEAT_S = 25.0


def topic(device_id: str) -> str:
    return f"view:{device_id}"


def socket_url(supabase_url: str, key: str) -> str:
    base = supabase_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/realtime/v1/websocket?apikey={key}&vsn=1.0.0"


class FrameGate:
    """The contract's `seq` rule and the 5 second stop, on the program's clock."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.last_seq: int | None = None
        self.last_arrival: float | None = None

    def stopped(self) -> bool:
        return self.last_arrival is None or (
            self.clock.now() - self.last_arrival >= STOPPED_AFTER_S)

    def accept(self, frame: dict[str, Any]) -> bytes | None:
        """The JPEG to show, or None to drop this frame."""
        try:
            seq = int(frame.get("seq"))  # type: ignore[arg-type]
            jpeg = base64.b64decode(str(frame.get("jpeg") or ""), validate=True)
        except (TypeError, ValueError, binascii.Error):
            return None
        if not jpeg:
            return None
        if self.stopped():
            self.last_seq = None
        if self.last_seq is not None and seq < self.last_seq:
            return None
        self.last_seq = seq
        self.last_arrival = self.clock.now()
        return jpeg


class LiveView:
    def __init__(self, supabase_url: str, key: str, device_id: str,
                 on_jpeg: Callable[[bytes], None], clock: Clock,
                 connect: Callable[..., Any] | None = None) -> None:
        self._url = socket_url(supabase_url, key)
        self.topic = topic(device_id)
        self.on_jpeg = on_jpeg
        self.gate = FrameGate(clock)
        self._connect = connect
        self._task: asyncio.Task[None] | None = None
        self.joined = False
        self.frames = 0
        self.refused = ""

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="argos-liveview")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def receiving(self) -> bool:
        return not self.gate.stopped()

    async def _run(self) -> None:
        connect = self._connect
        if connect is None:
            import websockets

            connect = websockets.connect
        delay = 1.0
        while True:
            try:
                async with connect(self._url, open_timeout=10, max_size=2**20) as socket:
                    delay = 1.0
                    await self._session(socket)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the URL carries the key: name the error type only
                log.info("live view connection dropped (%s); trying again", type(exc).__name__)
            self.joined = False
            await asyncio.sleep(delay)
            delay = min(10.0, delay * 2)

    async def _session(self, socket: Any) -> None:
        join = {"topic": f"realtime:{self.topic}", "event": "phx_join", "ref": "1",
                "join_ref": "1",
                "payload": {"config": {"broadcast": {"ack": False, "self": False},
                                       "presence": {"key": "", "enabled": False},
                                       "postgres_changes": [], "private": True}}}
        await socket.send(json.dumps(join))
        ref = 1
        loop = asyncio.get_running_loop()
        next_beat = loop.time() + HEARTBEAT_S
        while True:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=max(0.1,
                                                                        next_beat - loop.time()))
            except TimeoutError:
                ref += 1
                await socket.send(json.dumps({"topic": "phoenix", "event": "heartbeat",
                                              "payload": {}, "ref": str(ref)}))
                next_beat = loop.time() + HEARTBEAT_S
                continue
            self.handle(raw)

    def handle(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        event = message.get("event")
        payload = message.get("payload") or {}
        if event == "phx_reply" and message.get("ref") == "1":
            if payload.get("status") == "ok":
                if not self.joined:
                    log.info("live view: listening on the private topic")
                self.joined = True
            else:
                reason = (payload.get("response") or {}).get("reason") or "refused"
                self.refused = str(reason)[:100]
                log.warning("live view: the topic refused us (%s); the snapshot is shown",
                            self.refused)
            return
        if event != "broadcast" or payload.get("event") != "frame":
            return
        frame = payload.get("payload")
        if not isinstance(frame, dict):
            return
        jpeg = self.gate.accept(frame)
        if jpeg is not None:
            self.frames += 1
            self.on_jpeg(jpeg)
