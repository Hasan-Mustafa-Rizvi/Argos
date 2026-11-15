"""Stage 4: what the agent does once the bridge is ready.

In this order of importance; each works without the ones after it:

1. Speak: who it is and why it called, from the incident. Made before dialling.
2. Show: the live view while frames arrive, else the stored snapshot, else the card, and it
   says which one is on screen.
3. Acknowledge: when the person says they have it, the agent says what it heard, makes the
   dashboard's acknowledgement under "<label>, by FaceTime", says whether that worked or was
   already done, says goodbye, and the call ends. It never writes the `acknowledged` event.
4. Answer: questions are answered from the incident, the timeline and what the camera shows
   now, through Gemini, within rule 6.
5. See: not built. Chert's caller capture can include the FaceTime window's own picture of
   our video (the dog's camera, which may show the person at home), so a model could "see a
   person" who is not the caller. See the README.

Every fixed line is synthesised before dialling and kept in memory. What the person says is
heard in memory and dropped; it is never logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from argos_call import incident as words
from argos_call.answers import UNKNOWN, Answers, instructions
from argos_call.backend import Backend, BackendError
from argos_call.clock import Clock
from argos_call.hearing import TAIL_S, Phrases, Utterances, feed_from_track
from argos_call.incident import Incident
from argos_call.picture import Screen
from argos_call.redact import Redactor
from argos_call.voice import Speech, VoiceError, seconds

log = logging.getLogger("argos_call.conversation")

LISTEN_S = 20.0


def fixed_lines(incident: Incident, contact_label: str) -> dict[str, str]:
    return {
        "greeting": words.greeting(incident),
        "picture_live": words.picture_line("live", incident),
        "picture_snapshot": words.picture_line("snapshot", incident),
        "summary": words.summary_line(incident),
        "ask": words.ASK,
        "ask_again": words.ASK_AGAIN,
        "heard_ack": words.HEARD_ACK,
        "ack_done": words.ACK_DONE,
        "already": words.ALREADY,
        "ack_failed": words.ACK_FAILED,
        "not_sure": words.NOT_SURE,
        "closing": words.closing(incident),
        "goodbye_silent": words.GOODBYE_SILENT,
        "unknown": UNKNOWN,
    }


class Lines:
    """The call's fixed lines as audio, in memory."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = {name: text for name, text in texts.items() if text}
        self.audio: dict[str, bytes] = {}

    async def prepare(self, speech: Speech, at_once: int = 3) -> list[str]:
        """Synthesise every line. Returns the names that failed."""
        gate = asyncio.Semaphore(at_once)
        failed: list[str] = []

        async def one(name: str, text: str) -> None:
            async with gate:
                try:
                    self.audio[name] = await speech.synthesize(text)
                except VoiceError as exc:
                    failed.append(name)
                    log.warning("line %r not made (%s)", name, exc)

        await asyncio.gather(*(one(n, t) for n, t in self.texts.items()))
        return failed

    def get(self, name: str) -> bytes:
        return self.audio.get(name, b"")


class Talk:
    def __init__(
        self,
        incident: Incident,
        lines: Lines,
        screen: Screen,
        backend: Backend,
        contact_label: str,
        clock: Clock,
        report: Callable[[str], None],
        redactor: Redactor,
        phrases: Phrases | None = None,
        answers: Answers | None = None,
        speech: Speech | None = None,
        timeline: list[str] | None = None,
        listen_s: float = LISTEN_S,
        feed: Callable[[Any, Utterances], Any] = feed_from_track,
    ) -> None:
        self.incident = incident
        self.lines = lines
        self.screen = screen
        self.backend = backend
        self.contact_label = contact_label
        self.clock = clock
        self.report = report
        self.redactor = redactor
        self.phrases = phrases
        self.answers = answers
        self.speech = speech
        self.timeline = timeline or []
        self.listen_s = listen_s
        self.feed = feed
        self.ears = Utterances(clock.now)
        self.hearing_track = False
        self.acknowledged = ""  # "", "done", "already" or "failed"
        self.greetings = 0
        self._feeds: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------ wiring

    def on_remote_audio(self, track: Any, participant: Any) -> None:
        """The person's voice (`facetime-remote-audio`) reaches the ears, in memory."""
        if self.hearing_track:
            return
        self.hearing_track = True
        self.report("hearing the person's audio")
        self._feeds.append(asyncio.create_task(self.feed(track, self.ears)))

    def on_remote_video(self, track: Any, participant: Any) -> None:
        # Step 5 is not built: the person's camera is not read at all.
        return None

    async def stop(self) -> None:
        if self.ears.frames:
            self.report(f"the person's audio: loudest {self.ears.peak:.0f} RMS, "
                        f"speech gate {max(450.0, self.ears.noise * 3):.0f}, "
                        f"{self.ears.frames * 0.02:.0f} s heard while Argos was quiet")
        for task in self._feeds:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._feeds.clear()

    # ------------------------------------------------------------------ speaking

    async def _speak(self, agent: Any, pcm: bytes) -> None:
        if not pcm:
            return
        self.ears.quiet_until = float("inf")
        try:
            await agent.say(pcm)
        finally:
            self.ears.quiet_until = self.clock.now() + TAIL_S

    async def say_line(self, agent: Any, name: str) -> None:
        await self._speak(agent, self.lines.get(name))

    # ------------------------------------------------------------------ the call

    async def run(self, agent: Any) -> None:
        self.greetings += 1
        await self.say_line(agent, "greeting")
        on_screen = self.screen.kind
        if on_screen in ("live", "snapshot"):
            await self.say_line(agent, f"picture_{on_screen}")
            self.report(f"on screen: {self.screen.describe()}")
        await self.say_line(agent, "summary")
        await self.say_line(agent, "ask")
        misses = 0
        while True:
            pcm = await self._next_utterance()
            if pcm is None:
                misses += 1
                if misses == 1:
                    await self.say_line(agent, "ask_again")
                    continue
                self.report("no reply heard; saying goodbye")
                await self.say_line(agent, "goodbye_silent")
                return
            misses = 0
            intent, reply = await self.understand(pcm)
            self.report(f"heard {seconds_16k(pcm):.1f} s of speech: {intent}")
            if intent == "acknowledge":
                await self.acknowledge(agent)
                return
            if reply:
                await self._answer(agent, reply)
            else:
                await self.say_line(agent, "not_sure")

    async def _next_utterance(self) -> bytes | None:
        """What the person says next, or None after `listen_s` of nothing, on the program's
        clock."""
        deadline = self.clock.now() + self.listen_s
        while self.clock.now() < deadline:
            try:
                return self.ears.out.get_nowait()
            except asyncio.QueueEmpty:
                await self.clock.sleep(0.1)
        return None

    async def closing(self, agent: Any) -> None:
        self.report("near the limit: saying it has to hang up")
        await self.say_line(agent, "closing")

    # ------------------------------------------------------------------ understanding

    async def understand(self, pcm: bytes) -> tuple[str, str]:
        """("acknowledge" | "question" | "other", reply). Offline phrases first, then Gemini
        when there is a key; a question that Gemini understood is never taken as an
        acknowledgement."""
        heard_ack = False
        if self.phrases is not None:
            try:
                # Inline: a grammar decode of a few seconds of speech takes 20 to 40 ms.
                heard_ack = self.phrases.acknowledges(pcm)
            except Exception as exc:
                log.warning("the phrase list could not run (%s)", type(exc).__name__)
        if self.answers is not None:
            system = self._instructions()
            understood = await self.answers.understand(pcm, system, self.screen.latest_live)
            if understood.intent == "error":
                return ("acknowledge", "") if heard_ack else ("other", "")
            return understood.intent, understood.reply
        return ("acknowledge", "") if heard_ack else ("other", "")

    def _instructions(self) -> str:
        return instructions(self.incident, self.timeline, self.screen.describe(),
                            self.contact_label, words.noticed(self.incident))

    async def _answer(self, agent: Any, reply: str) -> None:
        if self.speech is None:
            await self.say_line(agent, "unknown")
            return
        try:
            pcm = await self.speech.synthesize(reply)
        except VoiceError:
            await self.say_line(agent, "unknown")
            return
        self.report(f"answering ({seconds(pcm):.1f} s of speech)")
        await self._speak(agent, pcm)

    # ------------------------------------------------------------------ acknowledging

    async def acknowledge(self, agent: Any) -> None:
        await self.say_line(agent, "heard_ack")
        label = words.ack_label(self.contact_label)
        try:
            made = await self.backend.acknowledge(self.incident.id, label, self.clock.iso())
        except BackendError as exc:
            self.acknowledged = "failed"
            self.report(f"the acknowledgement was not made ({self.redactor.mask(exc)})")
            await self.say_line(agent, "ack_failed")
            return
        if made:
            self.acknowledged = "done"
            self.report(f"acknowledged as {label!r}; the brain records it and calms the dog")
            await self.say_line(agent, "ack_done")
        else:
            self.acknowledged = "already"
            self.report("no row came back: someone had already acknowledged it")
            await self.say_line(agent, "already")


def seconds_16k(pcm: bytes) -> float:
    return len(pcm) / 2 / 16000
