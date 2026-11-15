"""The call agent's commands. Run from `call/`.

    python -m argos_call check              settings, the Chert line, open calls, seconds used
    python -m argos_call run                watch the backend; text and call on an escalation
    python -m argos_call run --demo         the same, for the judged demo (past the 30 minutes)
    python -m argos_call run --fake         one made-up escalation, local, then stop
    python -m argos_call rehearse           the call's conversation in a LiveKit room, no call
    python -m argos_call rehearse --browser the same, and you talk to it from your browser
    python -m argos_call ring               stage 1: one test call (60 s at most)
    python -m argos_call ring --audio       the same, FaceTime Audio

Every command honours ARGOS_DRY_RUN: anything but 0 means nothing real goes out, and in
dry-run the Chert client is not even made.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from typing import Any

from argos_call import config, lines, session
from argos_call.backend import MemoryBackend, Supabase
from argos_call.chert import ChertAPI, ChertError, is_terminal
from argos_call.clock import Clock
from argos_call.picture import Picture
from argos_call.redact import Redactor, install
from argos_call.state import Handled, Seconds

log = logging.getLogger("argos_call")

TEST_LINE = ("Hello, this is Argos, the companion dog. This is a short test call from the "
             "Argos team, and it ends now. Goodbye.")
TRIGGERS = ("fall", "help_call", "stillness", "manual")
FIXED_SUMMARY = {
    "fall": "Argos saw someone on the floor, and nobody answered when it asked if they were "
            "okay.",
    "help_call": "Argos heard a call for help, and nobody answered when it asked if they were "
                 "okay.",
    "stillness": "Argos saw someone who had not moved for a long time, and nobody answered "
                 "when it asked if they were okay.",
    "manual": "A check was started by hand, and nobody answered when Argos asked if they were "
              "okay.",
}


def say(message: str) -> None:
    log.info("%s", message)


class OneLine:
    """Stage 1's conversation: one sentence, then the call ends."""

    def __init__(self, pcm: bytes) -> None:
        self.pcm = pcm
        self.spoken = 0

    async def run(self, agent: Any) -> None:
        self.spoken += 1
        await agent.say(self.pcm)
        await asyncio.sleep(1.5)

    async def closing(self, agent: Any) -> None:
        return None


def _startup(args: argparse.Namespace) -> tuple[config.Settings, Redactor]:
    redactor = Redactor()
    install(redactor, logging.DEBUG if args.verbose else logging.INFO)
    settings = config.from_env(config.read_env(), redactor)
    for line in settings.describe():
        say(line)
    for line in settings.missing():
        log.warning("%s", line)
    return settings, redactor


async def _line(api: ChertAPI, settings: config.Settings) -> dict[str, Any] | None:
    try:
        found = await api.lines()
    except ChertError as exc:
        log.error("could not read the project's lines: %s", api.redactor.mask(exc))
        return None
    line, note = lines.choose(found, settings.chert_line_id)
    say(note)
    if line is not None:
        for text in lines.describe(line):
            say(text)
        if lines.busy(line):
            say("the line looks busy right now: a call request will wait in Chert's queue")
    return line


def _ears(settings: config.Settings) -> tuple[Any, Any]:
    """The offline phrase list (if the model is there) and Gemini (if there is a key)."""
    phrases = answers = None
    try:
        from argos_call.hearing import Phrases

        phrases = Phrases(settings.vosk_model)
        say("hearing: the offline phrase list is on")
    except Exception as exc:
        log.warning("hearing: no offline phrase list (%s); run python tools/fetch_models.py",
                    type(exc).__name__)
    if settings.gemini_configured:
        from argos_call.answers import Answers, sdk_generate

        answers = Answers(sdk_generate(settings.gemini_api_key, settings.gemini_model))
        say(f"hearing: Gemini {settings.gemini_model} answers questions")
    return phrases, answers


# ---------------------------------------------------------------------- check


async def check(args: argparse.Namespace) -> int:
    settings, redactor = _startup(args)
    seconds = Seconds(settings.state_dir)
    say(f"seconds used so far: {seconds.used():.0f} ({seconds.used() / 60:.1f} of 50 minutes)")
    if not settings.chert_api_key:
        return 0
    api = ChertAPI(settings.chert_base, settings.chert_api_key, settings.chert_project_id,
                   redactor)
    try:
        await _line(api, settings)
        try:
            calls = await api.calls()
        except ChertError as exc:
            log.error("could not list calls: %s", redactor.mask(exc))
            calls = []
        open_calls = [c for c in calls if not is_terminal(c)]
        say(f"calls on record: {len(calls)}, still open: {len(open_calls)}")
    finally:
        await api.aclose()
    return 0


# ---------------------------------------------------------------------- run


def made_up(kind: str, clock: Clock, device_id: str) -> tuple[MemoryBackend, str]:
    """A made-up escalation, in memory only: an incident and its `escalated` event."""
    from argos_call.backend import new_id

    backend = MemoryBackend()
    incident_id = str(uuid.uuid4())
    now = clock.iso()
    backend.incidents[incident_id] = {
        "id": incident_id, "device_id": device_id, "trigger": kind, "status": "escalated",
        "started_at": now, "summary": FIXED_SUMMARY[kind], "snapshot_path": None,
        "made_up": True}
    backend.events.append({"id": new_id(), "device_id": device_id, "incident_id": incident_id,
                           "at": now, "kind": "escalated",
                           "text": "No answer after 10 seconds. Argos is calling for help.",
                           "detail": {}})
    return backend, incident_id


async def run(args: argparse.Namespace) -> int:
    from argos_call.escalate import Escalator
    from argos_call.watch import Watcher

    settings, redactor = _startup(args)
    clock = Clock()
    handled = Handled(settings.state_dir)
    seconds = Seconds(settings.state_dir)
    say(f"seconds used so far: {seconds.used():.0f} ({seconds.used() / 60:.1f} of 50 minutes)")
    supabase: Supabase | None = None
    if args.fake:
        backend: Any
        backend, incident_id = made_up(args.fake, clock, settings.device_id)
        say(f"made-up escalation {incident_id[:8]} ({args.fake}): local only, the database "
            "is not touched")
    elif settings.backend_configured:
        supabase = backend = Supabase(settings.supabase_url, settings.supabase_key, redactor)
    else:
        log.error("no backend settings: nothing to watch. Use --fake for a made-up escalation")
        return 2
    real, why = settings.can_call_for_real()
    chert = caller = rooms = speech = None
    line_id = settings.chert_line_id
    try:
        if real:
            from argos_call.calling import Caller
            from argos_call.liveview import LiveView
            from argos_call.room import Agent, Rooms
            from argos_call.voice import ElevenLabs

            chert = ChertAPI(settings.chert_base, settings.chert_api_key,
                             settings.chert_project_id, redactor)
            await session.end_stale_calls(chert, say)
            line = await _line(chert, settings)
            if line is not None:
                line_id = str(line.get("id"))
            rooms = Rooms(settings.livekit_url, settings.livekit_api_key,
                          settings.livekit_api_secret, redactor)
            speech = ElevenLabs(settings.elevenlabs_api_key, settings.elevenlabs_voice_id,
                                settings.elevenlabs_model)
            phrases, answers = _ears(settings)

            def live_view(on_jpeg: Any) -> Any:
                if supabase is None:
                    return None
                return LiveView(settings.supabase_url, settings.supabase_key,
                                settings.device_id, on_jpeg, clock)

            caller = Caller(settings, backend, chert, rooms, speech, clock, seconds, say,
                            redactor, lambda picture, identity: Agent(picture, identity),
                            phrases=phrases, answers=answers,
                            live_view=live_view if supabase is not None else None,
                            line_id=line_id, demo=args.demo, picture=Picture())
            say("REAL: an escalation will be texted and called"
                + (" (judged demo: past the 30 minute limit)" if args.demo else ""))
        else:
            say(f"dry-run: {why}. Escalations are logged and recorded with dry_run true; "
                "nothing is sent")
        escalator = Escalator(settings, backend, chert, handled, seconds, clock, say, redactor,
                              place_call=caller.place if caller is not None else None,
                              demo=args.demo, line_id=line_id)
        watcher = Watcher(backend, escalator, handled, settings.device_id, clock,
                          settings.poll_s, say, redactor)
        if args.fake:
            for _ in range(3):
                if await watcher.once():
                    break
                await clock.sleep(settings.poll_s)
            say(f"made-up escalation done. events, kept in memory: "
                f"{[e['kind'] for e in escalator.events.written]}")
            return 0
        await watcher.run()
        return 0
    finally:
        for client in (chert, speech, rooms, supabase):
            if client is not None:
                await client.aclose()


# ---------------------------------------------------------------------- rehearse


async def rehearse_command(args: argparse.Namespace) -> int:
    settings, redactor = _startup(args)
    if not (settings.livekit_configured and settings.voice_configured):
        log.error("rehearse needs the LIVEKIT_ settings and the ELEVENLABS_ settings")
        return 2
    from argos_call.rehearse import rehearse
    from argos_call.voice import ElevenLabs

    speech = ElevenLabs(settings.elevenlabs_api_key, settings.elevenlabs_voice_id,
                        settings.elevenlabs_model)
    phrases, answers = _ears(settings)
    try:
        return await rehearse(settings, redactor, speech, phrases, answers, say,
                              browser=args.browser)
    finally:
        await speech.aclose()


# ---------------------------------------------------------------------- ring (stage 1)


async def ring(args: argparse.Namespace) -> int:
    settings, redactor = _startup(args)
    if not settings.livekit_configured:
        log.error("ring needs LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET")
        return 2
    if not settings.voice_configured:
        log.error("ring needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID: a silent call is "
                  "dropped by Chert")
        return 2
    real, why = settings.can_call_for_real()
    seconds = Seconds(settings.state_dir)
    if real:
        refusal = seconds.refuse(config.BUDGET_S, demo=False)
        if refusal:
            log.error("refusing the call: %s", refusal)
            return 3
    else:
        say(f"dry-run: {why}. The room and the agent are made; no call is requested.")

    from argos_call.room import Agent, Rooms
    from argos_call.voice import ElevenLabs, VoiceError

    clock = Clock()
    picture = Picture()
    picture.show_card("Argos", "Test call, " + clock.wall().astimezone().strftime("%H:%M"))
    voice = ElevenLabs(settings.elevenlabs_api_key, settings.elevenlabs_voice_id,
                       settings.elevenlabs_model)
    rooms = Rooms(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret,
                  redactor)
    api = ChertAPI(settings.chert_base, settings.chert_api_key, settings.chert_project_id,
                   redactor) if real else None
    try:
        try:
            pcm = await voice.synthesize(TEST_LINE)
        except VoiceError as exc:
            log.error("the greeting could not be made: %s", exc)
            return 4
        say(f"greeting ready in memory ({len(pcm) / 2 / 24000:.1f} s of audio)")
        line_id = settings.chert_line_id
        if api is not None:
            await session.end_stale_calls(api, say)
            line = await _line(api, settings)
            if line is None:
                return 5
            line_id = str(line.get("id"))
        plan = session.Plan(kind="test", limit_s=config.TEST_LIMIT_S,
                            attempt_key=f"argos-test-{clock.wall().strftime('%Y%m%d%H%M%S')}",
                            destination=settings.contact_facetime_to, line_id=line_id,
                            video=not args.audio)
        if api is None:
            return await _rehearse_room(plan, rooms, picture, pcm, say)
        talk = OneLine(pcm)
        runner = session.Session(api, rooms, lambda identity: Agent(picture, identity), clock,
                                 seconds, say)
        say(f"calling {settings.contact_label} on FaceTime "
            f"{'Audio' if args.audio else 'Video'}, test call, {config.TEST_LIMIT_S:.0f} s at most")
        result = await runner.run(plan, talk)
        say(f"result: {result.outcome}; answered {result.answered}; bridge ready "
            f"{result.bridge_ready}; greeted {talk.spoken} time(s); ended by "
            f"{result.ended_by or '-'}; {result.reason}")
        say(f"chert events seen: {', '.join(result.chert_events) or 'none'}; statuses: "
            f"{' > '.join(result.statuses) or 'none'}")
        return 0 if result.outcome == "placed" else 6
    finally:
        if api is not None:
            await api.aclose()
        await voice.aclose()
        await rooms.aclose()


async def _rehearse_room(plan: session.Plan, rooms: Any, picture: Picture, pcm: bytes,
                         report: session.Say) -> int:
    """Dry-run of stage 1 on the real LiveKit: room, agent, tracks, greeting. No Chert."""
    from argos_call.room import Agent

    agent = Agent(picture, "argos-agent-rehearsal")
    joined = False
    try:
        await rooms.create(plan.room)
        report(f"room {plan.room} made")
        await agent.join(rooms.url, rooms.token(agent.identity, plan.room,
                                                session.AGENT_TOKEN_TTL))
        joined = True
        report("agent joined; one audio track (silence) and one video track are flowing")
        bridge = rooms.token("chert-bridge-rehearsal", plan.room, session.BRIDGE_TOKEN_TTL)
        report(f"bridge token minted ({len(bridge)} characters, 30 minute lifetime); not sent")
        report("dry-run: would POST /v1/calls with direction outbound, customer_managed, "
               f"destination_type phone, media audio+{'video' if plan.video else 'no video'}, "
               "when_busy queue, the bridge token and the agent identity")
        await asyncio.sleep(2.0)
        report("speaking the greeting into the empty room, to prove the audio path")
        await agent.say(pcm)
        report("greeting went out; leaving")
        return 0
    finally:
        if joined:
            await agent.leave()
        await rooms.delete(plan.room)
        report("room deleted")


# ---------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m argos_call")
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="settings, the line, open calls, seconds used")
    run_parser = commands.add_parser("run", help="watch for escalations; text, then call")
    run_parser.add_argument("--demo", action="store_true",
                            help="the judged demo: allowed past the 30 minute test limit")
    run_parser.add_argument("--fake", nargs="?", const="fall", choices=TRIGGERS,
                            help="raise one made-up escalation locally, then stop")
    rehearse_parser = commands.add_parser("rehearse", help="the conversation, in a LiveKit room")
    rehearse_parser.add_argument("--browser", action="store_true",
                                 help="talk to the agent yourself from the browser")
    ring_parser = commands.add_parser("ring", help="stage 1: one test call, 60 s at most")
    ring_parser.add_argument("--audio", action="store_true", help="FaceTime Audio, not Video")
    args = parser.parse_args(argv)
    handler = {"check": check, "run": run, "rehearse": rehearse_command, "ring": ring}
    try:
        return asyncio.run(handler[args.command](args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
