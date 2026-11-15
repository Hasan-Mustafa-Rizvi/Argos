"""The call's conversation in a real LiveKit room, with no FaceTime call and no minutes used.

Two participants join a fresh room: our agent, exactly as on a call, and a stand-in for
Chert's bridge that publishes a track named `facetime-remote-audio`. The stand-in speaks a
few lines (made with the same ElevenLabs voice) and waits for the agent to finish each answer
before speaking again. The incident is made up; its acknowledgement goes to memory.

With `--browser`, there is no stand-in: the default browser opens LiveKit's Meet page in the
same room, so a person can talk to the agent with a microphone. The token goes to the browser
only and is never printed.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import webbrowser
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from livekit import rtc

from argos_call.backend import MemoryBackend
from argos_call.clock import Clock
from argos_call.conversation import Lines, Talk, fixed_lines
from argos_call.incident import Incident
from argos_call.picture import Picture, Screen
from argos_call.redact import Redactor
from argos_call.room import Agent, Rooms
from argos_call.session import AGENT_TOKEN_TTL

log = logging.getLogger("argos_call.rehearse")

CALLER_LINES = ("Hello? What happened?", "Is she breathing?", "Okay. I'm on my way.")
CALLER_RATE = 16000


async def _caller(rooms: Rooms, room: str, agent: Agent, speech: Any, report: Any) -> None:
    """The stand-in for the bridge: speaks when the agent has been quiet for a moment."""
    audio = {line: await speech.synthesize_at(line, CALLER_RATE) for line in CALLER_LINES}
    caller = rtc.Room()
    source = rtc.AudioSource(CALLER_RATE, 1)
    token = rooms.token("chert-bridge-rehearsal", room, timedelta(minutes=10))
    await caller.connect(rooms.url, token)
    track = rtc.LocalAudioTrack.create_audio_track("facetime-remote-audio", source)
    await caller.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    frame = CALLER_RATE // 50 * 2
    silence = bytes(frame)

    async def quiet_for(seconds: float) -> None:
        quiet = 0.0
        while quiet < seconds:
            await source.capture_frame(rtc.AudioFrame(silence, CALLER_RATE, 1, frame // 2))
            quiet = 0.0 if agent.speaking else quiet + 0.02

    async def answer_heard(limit_s: float = 12.0) -> None:
        """Like a person: wait for the agent to start answering, then to finish."""
        waited = 0.0
        while not agent.speaking and waited < limit_s:
            await source.capture_frame(rtc.AudioFrame(silence, CALLER_RATE, 1, frame // 2))
            waited += 0.02
        await quiet_for(1.2)

    try:
        await quiet_for(1.5)
        for line in CALLER_LINES:
            report(f"stand-in caller says: {line!r}")
            pcm = audio[line]
            for start in range(0, len(pcm), frame):
                chunk = pcm[start:start + frame].ljust(frame, b"\x00")
                await source.capture_frame(rtc.AudioFrame(chunk, CALLER_RATE, 1, frame // 2))
            await answer_heard()
        await quiet_for(30.0)
    finally:
        await caller.disconnect()


async def rehearse(settings: Any, redactor: Redactor, speech: Any, phrases: Any, answers: Any,
                   report: Any, browser: bool = False) -> int:
    clock = Clock()
    backend = MemoryBackend()
    incident = Incident(id=str(uuid.uuid4()), trigger="fall", escalated_at=clock.wall(),
                        person=backend.person, made_up=True,
                        summary="A person is lying on the floor next to the sofa in the "
                                "living room.")
    backend.incidents[incident.id] = {"id": incident.id, "device_id": settings.device_id,
                                      "status": "escalated", "trigger": "fall"}
    picture = Picture()
    screen = Screen(picture, incident.time, clock.now)
    lines = Lines(fixed_lines(incident, settings.contact_label))
    failed = await lines.prepare(speech)
    report(f"lines made in memory: {len(lines.audio)}" + (f"; failed: {failed}" if failed else ""))
    talk = Talk(incident, lines, screen, backend, settings.contact_label, clock, report,
                redactor, phrases=phrases, answers=answers, speech=speech,
                timeline=["Argos saw someone on the floor.", "Argos asked: Are you okay?",
                          "No answer after 10 seconds. Argos is calling for help."],
                listen_s=25.0 if browser else 20.0)
    rooms = Rooms(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret,
                  redactor)
    room = f"argos-rehearsal-{uuid.uuid4().hex[:8]}"
    agent = Agent(picture, "argos-agent-rehearsal")
    agent.on_remote_audio = talk.on_remote_audio
    caller_task: asyncio.Task[None] | None = None
    try:
        await rooms.create(room)
        await agent.join(rooms.url, rooms.token(agent.identity, room, AGENT_TOKEN_TTL))
        report(f"room {room}: agent in, audio and video flowing")
        if browser:
            token = rooms.token("rehearsal-person", room, timedelta(minutes=15))
            webbrowser.open("https://meet.livekit.io/custom?" + urlencode(
                {"liveKitUrl": rooms.url, "token": token}))
            report("opened LiveKit Meet in your browser; join with your microphone. The agent "
                   "starts talking when someone's audio reaches it")
            while not talk.hearing_track:
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)
        else:
            caller_task = asyncio.create_task(_caller(rooms, room, agent, speech, report))
            while not talk.hearing_track:
                await asyncio.sleep(0.2)
        await asyncio.wait_for(talk.run(agent), timeout=180)
        report(f"rehearsal over. acknowledgement: {talk.acknowledged or 'none'}; backend "
               f"updates: {backend.updates}")
        return 0 if talk.acknowledged == "done" else 1
    finally:
        if caller_task is not None:
            caller_task.cancel()
            try:
                await caller_task
            except (asyncio.CancelledError, Exception):
                pass
        await talk.stop()
        await agent.leave()
        await rooms.delete(room)
        await rooms.aclose()
