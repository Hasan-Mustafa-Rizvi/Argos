"""A real call about an incident: everything stage 4 needs, put together around a `Session`.

Before dialling: wait (up to 12 s from the escalation) for the summary and the snapshot,
fetch the snapshot into memory, start listening for live view frames, and synthesise every
fixed line. Then the session makes the room and the agent, asks Chert for the call, and runs
the conversation once the bridge is ready. Afterwards the live view is left, the ears are
closed, and the room is freed (by the session's `finally`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from argos_call import config
from argos_call import incident as words
from argos_call.backend import Backend, BackendError
from argos_call.chert import ChertAPI
from argos_call.clock import Clock
from argos_call.conversation import Lines, Talk, fixed_lines
from argos_call.escalate import CallOutcome, Events, plain_reason, wait_for_report
from argos_call.incident import Incident
from argos_call.picture import Picture, Screen
from argos_call.redact import Redactor
from argos_call.session import Plan, Session
from argos_call.state import Seconds

log = logging.getLogger("argos_call.calling")


class Caller:
    def __init__(
        self,
        settings: config.Settings,
        backend: Backend,
        chert: ChertAPI,
        rooms: Any,
        speech: Any,
        clock: Clock,
        seconds: Seconds,
        report: Callable[[str], None],
        redactor: Redactor,
        make_agent: Callable[[Picture, str], Any],
        phrases: Any = None,
        answers: Any = None,
        live_view: Callable[[Callable[[bytes], None]], Any] | None = None,
        line_id: str = "",
        demo: bool = False,
        picture: Picture | None = None,
        feed: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self.chert = chert
        self.rooms = rooms
        self.speech = speech
        self.clock = clock
        self.seconds = seconds
        self.report = report
        self.redactor = redactor
        self.make_agent = make_agent
        self.phrases = phrases
        self.answers = answers
        self.live_view = live_view
        self.line_id = line_id or settings.chert_line_id
        self.demo = demo
        self.picture = picture or Picture()
        self.feed = feed
        self.last_talk: Talk | None = None

    async def place(self, incident: Incident, events: Events) -> CallOutcome:
        to = self.settings.contact_label
        incident = await wait_for_report(incident, self.backend, self.clock)
        self.report("summary: " + ("yes" if incident.summary else "none yet") + "; snapshot: "
                    + ("yes" if incident.snapshot_path else "none"))
        screen = Screen(self.picture, incident.time, self.clock.now)
        if incident.snapshot_path:
            try:
                screen.set_snapshot(await self.backend.snapshot(incident.snapshot_path))
            except BackendError as exc:
                self.report(f"the snapshot could not be fetched ({self.redactor.mask(exc)})")
        viewer = self.live_view(screen.live) if self.live_view is not None else None
        if viewer is not None:
            viewer.start()
        timeline: list[str] = []
        try:
            for row in await self.backend.timeline(incident.id):
                stamp = row.get("at")
                when = words.clock_time(_parse(stamp)) if _parse(stamp) else ""
                timeline.append(f"{when}: {row.get('text')}".strip(": "))
        except BackendError:
            pass
        lines = Lines(fixed_lines(incident, to))
        failed = await lines.prepare(self.speech)
        if "greeting" in failed:
            if viewer is not None:
                await viewer.stop()
            return CallOutcome(False, False, "the voice could not be made, so no call was "
                               "placed (a silent call is dropped)")
        extra = {"feed": self.feed} if self.feed is not None else {}
        talk = Talk(incident, lines, screen, self.backend, to, self.clock, self.report,
                    self.redactor, phrases=self.phrases, answers=self.answers,
                    speech=self.speech, timeline=timeline, **extra)
        self.last_talk = talk

        def make(identity: str) -> Any:
            agent = self.make_agent(self.picture, identity)
            agent.on_remote_audio = talk.on_remote_audio
            agent.on_remote_video = talk.on_remote_video
            return agent

        async def answered() -> None:
            await events.add(incident, "call_answered", words.call_answered(to), {"to": to})

        async def placed(call_id: str) -> None:
            await events.add(incident, "call_placed", words.call_placed(to, False),
                             {"channel": "facetime", "to": to, "dry_run": False})

        session = Session(self.chert, self.rooms, make, self.clock, self.seconds, self.report,
                          on_answered=answered, on_placed=placed)
        kind = "demo" if self.demo else ("test" if incident.made_up else "incident")
        limit = config.TEST_LIMIT_S if kind == "test" else config.CALL_LIMIT_S
        plan = Plan(kind=kind, limit_s=limit, attempt_key=f"argos-{incident.id}-call",
                    destination=self.settings.contact_facetime_to, line_id=self.line_id,
                    tries=3)
        ticker = asyncio.create_task(_tick(screen, self.clock))
        try:
            result = await session.run(plan, talk)
        finally:
            ticker.cancel()
            await talk.stop()
            if viewer is not None:
                await viewer.stop()
        if talk.acknowledged:
            self.report(f"acknowledgement on the call: {talk.acknowledged}")
        reason = plain_reason(result.outcome, result.reason, result.answered, result.ended_by)
        return CallOutcome(result.outcome == "placed", result.answered, reason)


async def _tick(screen: Screen, clock: Clock) -> None:
    while True:
        screen.tick()
        await clock.sleep(1.0)


def _parse(value: Any) -> Any:
    from argos_call.clock import parse_iso

    return parse_iso(str(value)) if value else None
