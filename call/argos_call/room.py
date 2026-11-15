"""The LiveKit side: our room, our agent in it, and the token for Chert's bridge.

- The room is made by us before the call, with short empty and departure timeouts, so even a
  crash frees it soon. It is deleted when the call ends.
- The agent holds exactly one audio track, unmuted, and keeps it fed: speech when there is
  something to say, silence otherwise. It holds one video track and feeds it frames at one
  fixed size, from before the call is requested until it leaves.
- The bridge gets its own identity and a token for this one room: join, publish, subscribe,
  and an explicit 30 minute lifetime (LiveKit's default of six hours is more than Chert takes).
- What arrives from the bridge (the person's voice and camera) is handed to whoever asked for
  it, in memory. Nothing here writes to disk.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Callable
from typing import Any

from livekit import api, rtc

from argos_call.picture import Picture
from argos_call.redact import Redactor

log = logging.getLogger("argos_call.room")

SAMPLE_RATE = 24000
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
SILENCE = bytes(SAMPLES_PER_FRAME * 2)
VIDEO_FPS = 10


class Rooms:
    """Create and delete rooms, and mint tokens. The secret stays in this object."""

    def __init__(self, url: str, key: str, secret: str, redactor: Redactor) -> None:
        self.url = url
        self._key = key
        self._secret = secret
        self._redactor = redactor
        self._api: api.LiveKitAPI | None = None

    def _client(self) -> api.LiveKitAPI:
        if self._api is None:
            self._api = api.LiveKitAPI(self.url, self._key, self._secret)
        return self._api

    async def create(self, name: str) -> None:
        await self._client().room.create_room(api.CreateRoomRequest(
            name=name, empty_timeout=60, departure_timeout=20, max_participants=4))

    async def delete(self, name: str) -> None:
        try:
            await self._client().room.delete_room(api.DeleteRoomRequest(room=name))
        except Exception as exc:  # already gone, or the network is down: it times out anyway
            log.info("room %s not deleted (%s); it closes itself when empty",
                     name, type(exc).__name__)

    def token(self, identity: str, room: str, ttl: datetime.timedelta, name: str = "") -> str:
        grants = api.VideoGrants(room_join=True, room=room, can_publish=True,
                                 can_subscribe=True, can_publish_data=True)
        jwt = (api.AccessToken(self._key, self._secret)
               .with_identity(identity)
               .with_name(name or identity)
               .with_grants(grants)
               .with_ttl(ttl)
               .to_jwt())
        self._redactor.add_secret(jwt)
        return jwt

    async def aclose(self) -> None:
        if self._api is not None:
            await self._api.aclose()
            self._api = None


class Agent:
    """Our participant: one audio track that always flows, one video track that always flows,
    and handlers for the bridge's tracks."""

    def __init__(self, picture: Picture, identity: str) -> None:
        self.picture = picture
        self.identity = identity
        self.room = rtc.Room()
        self._audio = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=200)
        self._video = rtc.VideoSource(picture.width, picture.height)
        self._speech: asyncio.Queue[tuple[bytes, asyncio.Future[None]]] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()
        self._interrupt = False
        self.speaking = False
        self.on_remote_audio: Callable[[rtc.Track, rtc.RemoteParticipant], Any] | None = None
        self.on_remote_video: Callable[[rtc.Track, rtc.RemoteParticipant], Any] | None = None
        self.on_participant: Callable[[rtc.RemoteParticipant, bool], Any] | None = None
        self.remote_tracks: dict[str, str] = {}

    async def join(self, url: str, token: str) -> None:
        self.room.on("track_subscribed", self._track_subscribed)
        self.room.on("participant_connected", lambda p: self._participant(p, True))
        self.room.on("participant_disconnected", lambda p: self._participant(p, False))
        self._tasks.append(asyncio.create_task(self._feed_video(), name="argos-video"))
        await self.room.connect(url, token, rtc.RoomOptions(auto_subscribe=True))
        audio = rtc.LocalAudioTrack.create_audio_track("argos-voice", self._audio)
        video = rtc.LocalVideoTrack.create_video_track("argos-camera", self._video)
        self._tasks.append(asyncio.create_task(self._feed_audio(), name="argos-audio"))
        await self.room.local_participant.publish_track(
            audio, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        await self.room.local_participant.publish_track(
            video, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA))

    # ------------------------------------------------------------------ speaking

    async def say(self, pcm: bytes) -> None:
        """Queue 16-bit mono PCM at 24 kHz and wait until it has gone out."""
        if not pcm:
            return
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        await self._speech.put((pcm, done))
        await done

    def interrupt(self) -> None:
        """Stop the current line at the next frame."""
        self._interrupt = True

    async def _feed_audio(self) -> None:
        """The one audio track: speech when queued, silence otherwise, every 20 ms."""
        while not self._stop.is_set():
            try:
                pcm, done = self._speech.get_nowait()
            except asyncio.QueueEmpty:
                await self._audio.capture_frame(rtc.AudioFrame(SILENCE, SAMPLE_RATE, 1,
                                                               SAMPLES_PER_FRAME))
                continue
            self.speaking = True
            self._interrupt = False
            self._audio.clear_queue()  # drop queued silence so the line starts at once
            try:
                step = len(SILENCE)
                for start in range(0, len(pcm), step):
                    if self._interrupt or self._stop.is_set():
                        self._audio.clear_queue()
                        break
                    chunk = pcm[start:start + step]
                    if len(chunk) < step:
                        chunk = chunk + bytes(step - len(chunk))
                    await self._audio.capture_frame(
                        rtc.AudioFrame(chunk, SAMPLE_RATE, 1, SAMPLES_PER_FRAME))
                await self._audio.wait_for_playout()
            finally:
                self.speaking = False
                if not done.done():
                    done.set_result(None)

    # ------------------------------------------------------------------ video

    async def _feed_video(self) -> None:
        period = 1.0 / VIDEO_FPS
        while not self._stop.is_set():
            frame = rtc.VideoFrame(self.picture.width, self.picture.height,
                                   rtc.VideoBufferType.RGBA, self.picture.rgba())
            self._video.capture_frame(frame)
            await asyncio.sleep(period)

    # ------------------------------------------------------------------ the bridge's tracks

    def _participant(self, participant: rtc.RemoteParticipant, joined: bool) -> None:
        if self.on_participant is not None:
            self.on_participant(participant, joined)

    def _track_subscribed(self, track: rtc.Track, publication: rtc.RemoteTrackPublication,
                          participant: rtc.RemoteParticipant) -> None:
        self.remote_tracks[publication.name or track.sid] = (
            "audio" if track.kind == rtc.TrackKind.KIND_AUDIO else "video")
        if track.kind == rtc.TrackKind.KIND_AUDIO and self.on_remote_audio is not None:
            self.on_remote_audio(track, participant)
        elif track.kind == rtc.TrackKind.KIND_VIDEO and self.on_remote_video is not None:
            self.on_remote_video(track, participant)

    # ------------------------------------------------------------------ leaving

    async def leave(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        while not self._speech.empty():
            _, done = self._speech.get_nowait()
            if not done.done():
                done.set_result(None)
        try:
            await self.room.disconnect()
        except Exception as exc:
            log.info("leaving the room: %s", type(exc).__name__)
        for source in (self._audio, self._video):
            try:
                await source.aclose()
            except Exception:
                pass
