"""Fakes for Chert, LiveKit, the backend and the models. No test touches the network."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx

from argos_call.chert import ChertAPI
from argos_call.redact import Redactor

FAKE_NUMBER = "+15559876543"
FAKE_CHERT_KEY = "ftk_FAKEKEY_1234567890abcdefghij"
FAKE_LIVEKIT_SECRET = "lk-secret-FAKE-0123456789abcdefghij"
FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJicmlkZ2UtZmFrZSJ9.c2lnbmF0dXJlLWZha2UtdG9rZW4"
FAKE_SUPABASE_KEY = "sb_secret_FAKE_0123456789abcdef"
FAKE_GEMINI_KEY = "AIzaFAKE0123456789abcdefghijklmnop"
FAKE_ELEVEN_KEY = "sk_fakeeleven0123456789abcdef"


class FakeChertServer:
    """Chert's FaceTime API as an httpx transport.

    `busy` answers every create with 409 line_in_use. `queue_then_ready` answers 202 with a
    receipt that turns ready after a few reads. `echo_secrets` repeats the request (number,
    key and token included) inside every error body, so tests fail unless the client masks.
    """

    def __init__(self, ready_after_polls: int = 2, busy: bool = False,
                 queue_then_ready: bool = False, refuse: str | None = None,
                 echo_secrets: bool = False, end_after_polls: int | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.ready_after_polls = ready_after_polls
        self.busy = busy
        self.queue_then_ready = queue_then_ready
        self.queue_reads = 0
        self.refuse = refuse
        self.echo_secrets = echo_secrets
        self.end_after_polls = end_after_polls
        self.event_polls = 0
        self.ended = False
        self.created: dict[str, dict[str, Any]] = {}
        self.ready_twice = False
        self.messages: list[dict[str, Any]] = []
        self.refuse_message: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}") if request.content else {}
        self.requests.append({"method": request.method, "path": request.url.path,
                              "key": request.headers.get("idempotency-key"),
                              "auth": request.headers.get("authorization"), "body": body})
        path = request.url.path.removeprefix("/api")
        if request.method == "POST" and path == "/v1/calls":
            return self._create(body, request.headers.get("idempotency-key") or "")
        if request.method == "POST" and path == "/v1/shared-messages":
            if self.refuse_message:
                return self._error(403, "recipient_not_eligible", self.refuse_message, body)
            self.messages.append(body)
            return httpx.Response(201, json={"data": {"id": f"msg-{len(self.messages)}"}})
        if request.method == "GET" and path.startswith("/v1/calls/queue/"):
            self.queue_reads += 1
            state = "ready" if self.queue_reads >= 2 else "waiting"
            return httpx.Response(200, json={"data": {"id": "q-1", "state": state}})
        if request.method == "GET" and path.endswith("/events"):
            self.event_polls += 1
            events = [{"type": "call.allocated"}, {"type": "ringing"}]
            if self.event_polls >= self.ready_after_polls:
                events.append({"type": "bridge_ready"})
                if self.ready_twice:
                    events.append({"type": "bridge_ready"})
            if self.end_after_polls is not None and self.event_polls >= self.end_after_polls:
                events.append({"type": "call.ended"})
            return httpx.Response(200, json={"data": {"items": events}})
        if request.method == "POST" and path.endswith("/end"):
            self.ended = True
            return httpx.Response(202, json={"data": {"status": "ending"}})
        if request.method == "GET" and path.startswith("/v1/calls/"):
            status = "ended" if self.ended else "active"
            record = {"id": "call-1", "status": status}
            if self.echo_secrets:
                sent = next(iter(self.created.values()), {})
                record.update(destination=sent.get("destination"),
                              terminal_reason=f"ended for {sent.get('destination')}",
                              token_used=sent.get("participant_token"))
            return httpx.Response(200, json={"data": record})
        if request.method == "GET" and path == "/v1/calls":
            return httpx.Response(200, json={"data": {"items": []}})
        if request.method == "GET" and path == "/v1/lines":
            return httpx.Response(200, json={"data": {"items": [
                {"id": "line-1", "display_name": "Test line", "status": "available",
                 "availability": "available"}]}})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "nope"}})

    def _error(self, status: int, code: str, message: str, body: dict[str, Any]) -> httpx.Response:
        if self.echo_secrets:
            message = f"{message}; you sent {json.dumps(body)} with {FAKE_CHERT_KEY}"
        return httpx.Response(status, json={"error": {"code": code, "message": message}})

    def _create(self, body: dict[str, Any], key: str) -> httpx.Response:
        if self.refuse:
            return self._error(422, "video_not_enabled", self.refuse, body)
        if self.busy:
            return self._error(409, "line_in_use", "The line is in a call", body)
        if self.queue_then_ready and self.queue_reads < 2:
            return httpx.Response(202, json={"data": {"queued": True, "queue_id": "q-1",
                                                      "state": "waiting"}})
        self.created.setdefault(key, body)
        return httpx.Response(201, json={"data": {"id": "call-1", "status": "allocated"}})

    def calls_created(self) -> int:
        return len(self.created)

    def creates(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["path"].endswith("/v1/calls")
                and r["method"] == "POST"]


def chert_api(server: FakeChertServer, redactor: Redactor | None = None) -> ChertAPI:
    return ChertAPI("https://facetime.trychert.com/api", FAKE_CHERT_KEY, "project-1",
                    redactor or Redactor(), transport=httpx.MockTransport(server.handler))


class FakeRooms:
    url = "wss://fake.livekit.cloud"

    def __init__(self, redactor: Redactor | None = None) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.tokens: list[tuple[str, str]] = []
        self.redactor = redactor

    async def create(self, name: str) -> None:
        self.created.append(name)

    async def delete(self, name: str) -> None:
        self.deleted.append(name)

    def token(self, identity: str, room: str, ttl: Any, name: str = "") -> str:
        self.tokens.append((identity, room))
        if self.redactor is not None:  # as the real one does with every token it mints
            self.redactor.add_secret(FAKE_TOKEN)
        return FAKE_TOKEN

    async def aclose(self) -> None:
        return None


class FakeAgent:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.on_participant: Callable[..., Any] | None = None
        self.on_remote_audio: Callable[..., Any] | None = None
        self.on_remote_video: Callable[..., Any] | None = None
        self.said: list[bytes] = []
        self.joined = False
        self.left = False
        self.speaking = False

    async def join(self, url: str, token: str) -> None:
        self.joined = True
        if self.on_remote_audio is not None:  # the bridge's audio track arrives
            self.on_remote_audio(object(), object())

    async def say(self, pcm: bytes) -> None:
        self.said.append(pcm)
        await asyncio.sleep(0)

    def interrupt(self) -> None:
        return None

    async def leave(self) -> None:
        self.left = True


class Crash(Exception):
    pass


# --------------------------------------------------------------------------- stage 4 fakes

MARKER_PHRASE = "MARKER-PHRASE-7f3a"
MARKER_FRAME_TEXT = b"MARKER-FRAME-91c2"


def marker_jpeg() -> bytes:
    """A real JPEG with a marker in its comment segment."""
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 200, 30)).save(out, "JPEG", comment=MARKER_FRAME_TEXT)
    return out.getvalue()


class FakeSpeech:
    """Returns 0.2 s of silence for any line; remembers nothing but a count."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.count = 0

    async def synthesize(self, line: str) -> bytes:
        from argos_call.voice import VoiceError

        if self.fail:
            raise VoiceError("ElevenLabs answered HTTP 401")
        self.count += 1
        return bytes(9600)

    async def synthesize_at(self, line: str, rate: int) -> bytes:
        return await self.synthesize(line)

    async def aclose(self) -> None:
        return None


class FakePhrases:
    """The offline phrase list: acknowledges whatever `ack_on` says."""

    def __init__(self, ack_on: Callable[[int], bool] = lambda n: n >= 2) -> None:
        self.calls = 0
        self.ack_on = ack_on

    def acknowledges(self, pcm: bytes) -> bool:
        self.calls += 1
        return self.ack_on(self.calls)


class FakeAnswers:
    """Gemini: a question first (with the marker phrase in the reply), then an
    acknowledgement."""

    def __init__(self) -> None:
        self.calls = 0
        self.cameras: list[bytes | None] = []

    async def understand(self, pcm: bytes, system: str, camera_jpeg: bytes | None = None):
        from argos_call.answers import Understood

        self.calls += 1
        self.cameras.append(camera_jpeg)
        if self.calls == 1:
            return Understood("question", f"I can tell you this: {MARKER_PHRASE}.")
        return Understood("acknowledge", "")


def speech_burst() -> bytes:
    """1 s of loud audio and 1 s of quiet, 16 kHz mono, as the person would sound."""
    import math
    import struct

    loud = [int(8000 * math.sin(2 * math.pi * 220 * i / 16000)) for i in range(16000)]
    return struct.pack(f"<{len(loud)}h", *loud) + bytes(32000)


def talking_feed(bursts: int = 6):
    """A stand-in for the bridge's audio: like a person, it says one thing each time the
    agent has finished talking (and never before the agent has spoken)."""

    async def feed(track: object, ears) -> None:
        said = 0
        answered_to = None
        while said < bursts:
            await asyncio.sleep(0)
            finished = ears.quiet_until
            if (0 < finished != float("inf") and finished != answered_to
                    and ears.now() >= finished and ears.out.empty()):
                ears.push(speech_burst())
                said += 1
                answered_to = finished

    return feed


class FakeLiveView:
    """Delivers marker frames, again and again, from start until stop, like the brain."""

    def __init__(self, on_jpeg: Callable[[bytes], None], clock: Any = None) -> None:
        self.on_jpeg = on_jpeg
        self.clock = clock
        self.started = False
        self.stopped = False
        self.sent = 0
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.started = True
        frame = marker_jpeg()

        async def keep_sending() -> None:
            while True:  # four frames a second, on the run's clock
                self.on_jpeg(frame)
                self.sent += 1
                if self.clock is not None:
                    await self.clock.sleep(0.25)
                else:
                    await asyncio.sleep(0)

        self.on_jpeg(frame)
        self._task = asyncio.create_task(keep_sending())

    async def stop(self) -> None:
        self.stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


def env(tmp_path, **overrides: str | None) -> dict[str, str]:
    """A plain settings mapping (no .env.local is read), state files in `tmp_path`. An
    override of None removes the setting."""
    base: dict[str, str | None] = {
        "ARGOS_DRY_RUN": "0",
        "CHERT_API_KEY": FAKE_CHERT_KEY,
        "CHERT_PROJECT_ID": "project-1",
        "CHERT_LINE_ID": "line-1",
        "CONTACT_FACETIME_TO": FAKE_NUMBER,
        "CONTACT_LABEL": "Daughter",
        "LIVEKIT_URL": "wss://fake.livekit.cloud",
        "LIVEKIT_API_KEY": "APIfakekey123",
        "LIVEKIT_API_SECRET": FAKE_LIVEKIT_SECRET,
        "ELEVENLABS_API_KEY": FAKE_ELEVEN_KEY,
        "ELEVENLABS_VOICE_ID": "voice-1234567",
        "GEMINI_API_KEY": FAKE_GEMINI_KEY,
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": FAKE_SUPABASE_KEY,
        "ARGOS_CALL_STATE_DIR": str(tmp_path),
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}
