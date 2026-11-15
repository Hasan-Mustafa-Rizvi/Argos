"""The brain: one thread owns the state machine. Everything else talks to it through `post()`.

Senses, keys, the body and background jobs post inputs. The brain thread applies them to the
machine, records what happened, and tells the body, the voice and the ears. Nothing on this
thread waits on the network: records go through the writer queue, and network jobs (the
Gemini check, the summary, the snapshot, polling for an acknowledgement) run on a runner.

Rule 1 lives here: a frame from the camera is held in memory from the moment of a trigger and
dropped the moment the check stands down. Only an escalation hands it on, to become the
snapshot.

The wheels' approach (`approach.py`) is stepped here too, when the wheels are on. It starts
only after the question has been asked, never changes how long the brain waits for an
answer, and is ended the moment the check ends. The stop key goes to the wheels directly,
from the keyboard's thread, not through this queue.

A pat from the body is dropped if any part of the body moved within the last half second
(rule 3 of the task: the brain's own movement is never read as a press). The robot driver
already holds back; this is the second line.
"""

from __future__ import annotations

import logging
import math
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from argos import text
from argos.approach import Approach
from argos.body.base import (
    BodyEvent,
    BodyHub,
    Connected,
    Disconnected,
    Pat,
    Telemetry,
    Tipped,
    Upright,
)
from argos.body.poses import PAT_QUIET_S
from argos.body.wheels import Wheels
from argos.clock import Clock
from argos.config import Settings
from argos.escalation import Escalator
from argos.machine import (
    Acknowledged,
    Asked,
    Effect,
    Escalated,
    Ignored,
    Machine,
    Opened,
    State,
    StoodDown,
)
from argos.records import Recorder
from argos.script import ScriptPlayer, Step
from argos.store import Store, StoreRejected, StoreUnavailable
from argos.writer import RecordWriter

log = logging.getLogger("argos.brain")

HEARTBEAT_S = 5.0
CAMERA_TRIGGERS = ("fall", "stillness")
STOP_KEYS = (" ", "x")

# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class TriggerIn:
    trigger: str
    confidence: float | None = None
    source: str = "keyboard"
    frame: Any = None  # the camera frame the detector judged, if any


@dataclass(frozen=True)
class AnswerIn:
    by: str  # "voice" or "pat"
    said: str | None = None
    source: str = "keyboard"


@dataclass(frozen=True)
class HeardIn:
    """A phrase from the fixed list that is not a clear yes ("no", "help"), heard during a
    check. Recorded, and stands nothing down."""

    said: str


@dataclass(frozen=True)
class AckIn:
    by: str
    at: str | None = None
    local: bool = True


@dataclass(frozen=True)
class AskedIn:
    incident_id: str
    spoken: bool = True  # False: no voice, and at most a beep went out


@dataclass(frozen=True)
class ConfidenceIn:
    incident_id: str
    value: float


@dataclass(frozen=True)
class ReportIn:
    incident_id: str
    summary: str | None
    snapshot_path: str | None


@dataclass(frozen=True)
class BodyIn:
    event: BodyEvent


@dataclass(frozen=True)
class QuitIn:
    pass


Input = (
    TriggerIn | AnswerIn | HeardIn | AckIn | AskedIn | ConfidenceIn | ReportIn | BodyIn | QuitIn
)

# --------------------------------------------------------------------------- collaborators


class Runner(Protocol):
    def submit(self, job: Callable[[], None], name: str) -> None: ...


class ThreadRunner:
    def submit(self, job: Callable[[], None], name: str) -> None:
        def wrapped() -> None:
            try:
                job()
            except Exception:
                log.exception("background job %s failed", name)

        threading.Thread(target=wrapped, name=f"argos-{name}", daemon=True).start()


class InlineRunner:
    """Runs each job at once, on the caller's thread. For tests."""

    def submit(self, job: Callable[[], None], name: str) -> None:
        job()


def call_with_timeout(job: Callable[[], Any], timeout_s: float) -> Any:
    """`job()`'s result, or None if it raised or did not finish in time. A job that hangs is
    left behind on a daemon thread; nobody waits for it."""
    result: list[Any] = []

    def run() -> None:
        try:
            result.append(job())
        except Exception as exc:
            log.warning("%s failed: %s", getattr(job, "__name__", "job"), exc)

    thread = threading.Thread(target=run, name="argos-timed", daemon=True)
    thread.start()
    thread.join(timeout_s)
    return result[0] if result else None


class Voice(Protocol):
    def say(self, key: str, on_done: Callable[[], None] | None = None,
            on_spoken: Callable[[bool], None] | None = None) -> str: ...


class Vision(Protocol):
    def reading(self) -> tuple[bool, int]: ...

    def bearing_deg(self) -> float | None: ...


class Frames(Protocol):
    def latest(self) -> Any: ...


class Judge(Protocol):
    def check(self, frame: Any) -> float | None: ...

    def summary(self, frame: Any, trigger: str) -> str | None: ...


class Gate:
    """What the ears should listen for. Set by the brain, read by the listener."""

    def __init__(self) -> None:
        self.mode = "help"  # "help" in calm, "answer" during an asked check, "off" otherwise
        self.speaking_until = 0.0  # set by the voice: nothing is heard until then
        self.motors_until = 0.0  # set by the wheels, a field of their own: deaf until then


# --------------------------------------------------------------------------- the brain


class Brain:
    def __init__(
        self,
        settings: Settings,
        clock: Clock,
        recorder: Recorder,
        writer: RecordWriter,
        bodies: BodyHub,
        escalator: Escalator,
        runner: Runner,
        store: Store | None = None,
        voice: Voice | None = None,
        vision: Vision | None = None,
        frames: Frames | None = None,
        judge: Judge | None = None,
        uploader: Callable[[str, Any], str | None] | None = None,
        script: ScriptPlayer | None = None,
        wheels: Wheels | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.recorder = recorder
        self.writer = writer
        self.bodies = bodies
        self.escalator = escalator
        self.runner = runner
        self.store = store
        self.voice = voice
        self.vision = vision
        self.frames = frames
        self.judge = judge
        self.uploader = uploader
        self.script = script
        self.machine = Machine(settings.check_timeout_s)
        self.gate = Gate()
        self.held_frame: Any = None
        self.quit = threading.Event()
        self._inputs: queue.SimpleQueue[Input] = queue.SimpleQueue()
        self._next_heartbeat = 0.0
        self._next_ack_poll = 0.0
        self._ack_polling = False
        self._caps: list[str] | None = None
        self._fw: str | None = None
        self._started = False
        self._stopped = False
        self._calm_since = -math.inf
        self._ask_spoken: dict[str, bool] = {}
        self._resumed_incident: str | None = None
        self._last_approach_end = -math.inf
        self.wheels = wheels
        self.approach: Approach | None = None
        if wheels is not None:
            look = getattr(vision, "look", None) or (lambda: None)
            wheels.open_check = lambda: (self.machine.incident_id
                                         if self.machine.state is State.CHECKING else None)
            wheels.look = look
            wheels.moved_until = bodies.moving_until
            wheels.gate = self.gate
            self.approach = Approach(
                wheels, look, bodies.face_forward, bodies.moving_until, clock,
                max_s=settings.approach_max_s, min_score=settings.person_min_score,
                needs_head=not wheels.pretend, on_end=self._approach_ended,
            )

    # ------------------------------------------------------------------ inputs

    def post(self, item: Input) -> None:
        """Thread-safe. Anyone may post; only the brain thread acts."""
        self._inputs.put(item)

    def key(self, key: str) -> None:
        """The keyboard's keys, turned into inputs."""
        triggers = {"f": "fall", "h": "help_call", "s": "stillness", "m": "manual"}
        if key in triggers:
            self.post(TriggerIn(triggers[key], None, source="keyboard"))
        elif key == "y":
            self.post(AnswerIn("voice", text.KEYBOARD_ANSWER, source="keyboard"))
        elif key == "p":
            self.post(AnswerIn("pat", source="keyboard"))
        elif key == "a":
            self.post(AckIn(text.DEMO_LABEL, local=True))
        elif key == "q":
            self.post(QuitIn())
        elif key in STOP_KEYS:
            self.stop_wheels()
        elif key == "?":
            from argos.keyboard import help_text

            print(help_text(), flush=True)

    def stop_wheels(self) -> None:
        """The stop key: straight to the wheels, on the keyboard's own thread, not through the
        queue. It latches until the brain is started again."""
        if self.wheels is not None:
            self.wheels.latch()
        else:
            log.info("stop key: there are no wheels to stop")

    @property
    def state(self) -> State:
        return self.machine.state

    def can_trigger(self) -> bool:
        """For the detectors: calm, and the cooldown since the last check has passed, so a
        person who has just answered is not asked again at once."""
        return (self.machine.state is State.CALM
                and self.clock.now() >= self._calm_since + self.settings.trigger_cooldown_s)

    # ------------------------------------------------------------------ start and stop

    def start(self) -> None:
        now = self.clock.now()
        for line in self.settings.describe():
            log.info(line)
        self.bodies.start(lambda event: self.post(BodyIn(event)))
        self._read_person()
        resumed = self._find_open_incidents()
        self._caps, self._fw = self.bodies.caps(), self.bodies.fw()
        stamp = self.clock.iso()
        self.recorder.device(state=self.machine.state.value, last_seen_at=stamp, caps=self._caps,
                             fw=self._fw)
        self.recorder.event("device_online", text.device_online())
        self._reading()
        self._next_heartbeat = now + HEARTBEAT_S
        if resumed is not None:
            self._apply(resumed, now)
        self._show_body()
        if self.script:
            self.script.start(now)
        self._started = True

    def stop(self) -> None:
        """For any reason at all: the wheels stop first, then the rest. Safe to call twice."""
        if self._stopped:
            return
        self._stopped = True
        if self.approach is not None:
            self.approach.cancel("the brain is stopping")
        if self.wheels is not None:
            self.wheels.halt("the brain is stopping")
        self.bodies.stop()
        self.writer.close()

    def run(self) -> None:
        """The main loop. Returns when `q` is pressed or `quit` is set."""
        if not self._started:
            self.start()
        try:
            while not self.quit.is_set():
                self.step()
                self.quit.wait(0.05)
        finally:
            self.stop()

    def _read_person(self) -> None:
        if self.store is None:
            log.info("no backend: sentences will say 'the person'")
            return
        try:
            rows = self.store.select(
                "devices", {"id": f"eq.{self.settings.device_id}"}, "person_label"
            )
        except (StoreUnavailable, StoreRejected) as exc:
            log.warning("could not read the person's label (%s); sentences will say "
                        "'the person'", exc)
            return
        if rows and rows[0].get("person_label"):
            self.recorder.person = text.Person(str(rows[0]["person_label"]))
        else:
            log.warning("the device row was not found in the backend; sentences will say "
                        "'the person'")

    def _find_open_incidents(self) -> list[Effect] | None:
        """An incident left open by an earlier run.

        - Escalated and unacknowledged: still an alert. The brain starts in `alert` for it and
          waits for an acknowledgement. Nothing is re-sent.
        - Checking: there is no status for an interrupted check, so the brain finishes it
          honestly: it asks again and waits again, in the same incident. An answer stands it
          down; silence escalates it. Asking once too often is the safe mistake.
        Only the newest open incident is resumed. Any older one is left as it is, and logged.
        """
        if self.store is None:
            return None
        try:
            rows = self.store.select(
                "incidents",
                {"device_id": f"eq.{self.settings.device_id}",
                 "status": "in.(checking,escalated)"},
                "id,trigger,status,confidence,started_at",
                order="started_at.desc",
            )
        except (StoreUnavailable, StoreRejected) as exc:
            log.warning("could not look for open incidents (%s)", exc)
            return None
        if not rows:
            return None
        newest, older = rows[0], rows[1:]
        for row in older:
            log.warning("an older open incident %s (%s) is left as it is", row.get("id"),
                        row.get("status"))
        incident_id, trigger = str(newest["id"]), str(newest["trigger"])
        confidence = newest.get("confidence")
        if newest["status"] == "escalated":
            log.warning("incident %s escalated in an earlier run and is not acknowledged: "
                        "starting in alert", incident_id)
            self.recorder.note(f"resumed alert for incident {incident_id}")
            self.recorder.mark_escalated(incident_id)
            self.machine.resume_alert(incident_id, trigger, confidence)
            self.gate.mode = "off"
            return []
        log.warning("incident %s was still checking when the brain last stopped: asking again",
                    incident_id)
        self.recorder.note(f"resumed check for incident {incident_id}")
        self._resumed_incident = incident_id  # no approach on a resumed check
        return [_Resumed(self.machine.resume_check(incident_id, trigger, confidence,
                                                   self.clock.now()))]

    # ------------------------------------------------------------------ the loop

    def step(self) -> None:
        now = self.clock.now()
        if self.script:
            for step in self.script.due(now):
                self.post(self._scripted(step))
        while True:
            try:
                item = self._inputs.get_nowait()
            except queue.Empty:
                break
            self._handle(item, self.clock.now())
        now = self.clock.now()
        self._apply(self.machine.tick(now), now)
        if self.approach is not None:
            try:
                self.approach.step(now)
            except Exception:  # the wheels must never stop a check
                log.exception("the approach failed; the wheels are stopped")
                self._end_approach("it failed")
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + HEARTBEAT_S
            self.recorder.device(last_seen_at=self.clock.iso())
            self._reading()
        if self.machine.state is State.ALERT and now >= self._next_ack_poll:
            self._next_ack_poll = now + self.settings.ack_poll_s
            self._poll_ack()

    def _scripted(self, step: Step) -> Input:
        if step.action == "trigger":
            return TriggerIn(step.trigger or "manual", step.confidence, source="script")
        if step.action == "answer":
            return AnswerIn(step.by or "voice", step.said, source="script")
        return AckIn(text.DEMO_LABEL, local=True)

    def _handle(self, item: Input, now: float) -> None:
        if isinstance(item, TriggerIn):
            incident_id = self.recorder.make_id()
            effects = self.machine.trigger(item.trigger, item.confidence, incident_id, now)
            if any(isinstance(e, Opened) for e in effects):
                self._hold_frame(item.frame)
            self._apply(effects, now)
        elif isinstance(item, AnswerIn):
            if item.by == "pat" and self.machine.state is State.CHECKING:
                self.recorder.event("pat", text.pat(self.recorder.person), {},
                                    self.machine.incident_id)
            self._apply(self.machine.answer(item.by, item.said, now), now)
        elif isinstance(item, HeardIn):
            if self.machine.state is State.CHECKING:
                self.recorder.event("heard", text.heard(self.recorder.person, item.said),
                                    {"said": item.said}, self.machine.incident_id)
        elif isinstance(item, AckIn):
            self._apply(self.machine.acknowledge(item.by, item.at, item.local, now), now)
        elif isinstance(item, AskedIn):
            self._ask_spoken[item.incident_id] = item.spoken
            self._apply(self.machine.asked(item.incident_id, now), now)
            self._ask_spoken.pop(item.incident_id, None)
        elif isinstance(item, ConfidenceIn):
            self.recorder.incident_confidence(item.incident_id, item.value)
        elif isinstance(item, ReportIn):
            self.recorder.incident_report(item.incident_id, item.summary, item.snapshot_path)
        elif isinstance(item, BodyIn):
            self._body_event(item.event, now)
        elif isinstance(item, QuitIn):
            log.info("quit")
            self.quit.set()

    # ------------------------------------------------------------------ effects

    def _apply(self, effects: list[Effect] | list[Any], now: float) -> None:
        for effect in effects:
            if isinstance(effect, _Resumed):
                for inner in effect.effects:
                    self._on_opened(inner.check, now, resumed=True)
            elif isinstance(effect, Opened):
                self._on_opened(effect.check, now)
            elif isinstance(effect, Asked):
                self._on_asked(effect)
            elif isinstance(effect, StoodDown):
                self._on_stood_down(effect)
            elif isinstance(effect, Escalated):
                self._on_escalated(effect)
            elif isinstance(effect, Acknowledged):
                self._on_acknowledged(effect)
            elif isinstance(effect, Ignored):
                log.info("ignored %s: %s", effect.what, effect.reason)
                self.recorder.note(f"ignored {effect.what}: {effect.reason}")

    def _on_opened(self, check: Any, now: float, resumed: bool = False) -> None:
        stamp = self.clock.iso()
        if not resumed:
            self.recorder.incident_opened(check.incident_id, check.trigger, check.confidence,
                                          stamp)
            self.recorder.device(state="checking", last_seen_at=stamp)
            self.recorder.event(
                "trigger",
                text.trigger(check.trigger, self.recorder.person),
                {"trigger": check.trigger, "confidence": check.confidence},
                check.incident_id,
                at=stamp,
            )
        else:
            self.recorder.device(state="checking", last_seen_at=stamp)
            if self.held_frame is None:
                self._hold_frame(None)
        log.info("check %s: %s", check.incident_id, check.trigger)
        self.gate.mode = "off"
        self._show_body()
        if (self.judge is not None and check.trigger in CAMERA_TRIGGERS
                and self.held_frame is not None):
            self._start_gemini_check(check.incident_id, self.held_frame)
        incident_id = check.incident_id
        if self.voice is None:
            self.bodies.beep(300)  # the sensor board's buzzer, if there is one
            self.post(AskedIn(incident_id, spoken=False))
        else:
            self.voice.say("ask", on_spoken=lambda spoken: self.post(AskedIn(incident_id,
                                                                             spoken)))

    def _on_asked(self, effect: Asked) -> None:
        if effect.late:
            log.warning("the question was not reported as spoken in time; the wait starts now")
        said = text.ASK_LINE
        detail: dict[str, Any] = {"said": said}
        # Contract section 3: "spoken": false when the line did not play (no voice; a beep at
        # most). A question never reported as played counts as not spoken.
        if effect.late or not self._ask_spoken.get(effect.incident_id, False):
            detail["spoken"] = False
        self.recorder.event("asked", text.asked(said), detail, effect.incident_id)
        self.gate.mode = "answer"
        if not effect.late:
            self._maybe_approach(effect.incident_id)

    # ------------------------------------------------------------------ the approach

    def _maybe_approach(self, incident_id: str) -> None:
        """After the question: turn toward the person and come a little closer, if every rule
        allows it. It never changes the wait for an answer."""
        if self.approach is None:
            return
        why = None
        if self.script is not None:
            why = "this is a scripted run"
        elif incident_id == self._resumed_incident:
            why = "this check was resumed after a restart"
        elif self.clock.now() < self._last_approach_end + self.settings.approach_rest_s:
            why = "the last approach was too recent"
        if why is None:
            why = self.approach.start(incident_id)
        if why is not None:
            log.info("no approach: %s", why)

    def _approach_ended(self, reason: str) -> None:
        self._last_approach_end = self.clock.now()
        if self.machine.state is State.CHECKING:
            self._show_body()  # face the person again, from where the base now is

    def _end_approach(self, reason: str) -> None:
        if self.approach is not None:
            self.approach.cancel(reason)
        if self.wheels is not None:
            self.wheels.halt(reason)

    def _on_stood_down(self, effect: StoodDown) -> None:
        self._end_approach("the check stood down")
        stamp = self.clock.iso()
        person = self.recorder.person
        if effect.by == "voice":
            said = effect.said or text.KEYBOARD_ANSWER
            self.recorder.event("heard", text.heard(person, said), {"said": said},
                                effect.incident_id, at=stamp)
        self.recorder.event("stood_down", text.stood_down(person, effect.by), {"by": effect.by},
                            effect.incident_id, at=stamp)
        self.recorder.incident_stood_down(effect.incident_id, effect.by, stamp)
        self.recorder.device(state="calm", last_seen_at=stamp)
        self.held_frame = None  # rule 1: dropped the moment the check stands down
        self.gate.mode = "help"
        self._calm_since = self.clock.now()
        log.info("stood down by %s", effect.by)
        self.bodies.stood_down()
        if self.voice is not None:
            self.voice.say("stood_down")

    def _on_escalated(self, effect: Escalated) -> None:
        self._end_approach("the check escalated")
        stamp = self.clock.iso()
        incident_id = effect.incident_id
        self.recorder.event("escalated", text.escalated(self.settings.check_timeout_s), {},
                            incident_id, at=stamp)
        self.recorder.incident_escalated(incident_id)
        self.recorder.device(state="alert", last_seen_at=stamp)
        self.gate.mode = "off"
        log.warning("escalated incident %s", incident_id)
        self._show_body()
        try:
            self.escalator.escalate(incident_id)
        except Exception:
            log.exception("escalation failed; the dashboard still shows the alert")
        if self.voice is not None:
            self.voice.say("escalate")
        frame, self.held_frame = self.held_frame, None
        self.runner.submit(lambda: self._follow_up(incident_id, effect.trigger, frame),
                           "follow-up")
        self._next_ack_poll = self.clock.now() + self.settings.ack_poll_s

    def _on_acknowledged(self, effect: Acknowledged) -> None:
        self._end_approach("the alert was acknowledged")
        stamp = self.clock.iso()
        by = effect.by if not effect.local else text.DEMO_LABEL
        at = effect.at or stamp
        self.recorder.event("acknowledged", text.acknowledged(by), {"by": by},
                            effect.incident_id, at=at)
        if effect.local:
            self.recorder.incident_acknowledged_locally(effect.incident_id, by, stamp)
        else:
            self.recorder.incident_ended_after_acknowledgement(effect.incident_id, at)
        self.recorder.device(state="calm", last_seen_at=stamp)
        self.held_frame = None
        self.gate.mode = "help"
        self._calm_since = self.clock.now()
        log.info("acknowledged by %s", by)
        self._show_body()

    # ------------------------------------------------------------------ helpers

    def _show_body(self) -> None:
        look = None
        if self.machine.state is State.CHECKING and self.vision is not None:
            look = self.vision.bearing_deg()
        self.bodies.show_state(self.machine.state.value, look)

    def _hold_frame(self, frame: Any) -> None:
        """Rule 1: one frame, in memory only, from the moment of the trigger."""
        if frame is None and self.frames is not None:
            frame = self.frames.latest()
        self.held_frame = frame

    def _reading(self) -> None:
        temp_c, tilt_deg = self.bodies.sensors()
        present, still_s = (False, 0)
        if self.vision is not None:
            present, still_s = self.vision.reading()
        self.recorder.reading(temp_c, tilt_deg, present, still_s)

    def _body_event(self, event: BodyEvent, now: float) -> None:
        if isinstance(event, Pat):
            if now < self.bodies.moving_until() + PAT_QUIET_S:
                log.info("a pat from %s came while the body was moving, or just after: "
                         "ignored", event.source)
                return
            if self.machine.state is State.CHECKING:
                self._handle(AnswerIn("pat", source=event.source), now)
            else:
                log.info("pat from %s (no open check)", event.source)
        elif isinstance(event, Tipped):
            self.recorder.event("device_tipped", text.device_tipped(), {},
                                self.machine.incident_id)
        elif isinstance(event, Upright):
            log.info("set upright again")
        elif isinstance(event, (Connected, Disconnected)):
            if self.approach is not None and self.approach.active:
                self._end_approach(f"the {event.source} came or went")
            caps, fw = self.bodies.caps(), self.bodies.fw()
            if caps != self._caps or fw != self._fw:
                self._caps, self._fw = caps, fw
                self.recorder.device(caps=caps, fw=fw)
            if isinstance(event, Connected):
                self._show_body()
        elif isinstance(event, Telemetry):
            pass

    def _start_gemini_check(self, incident_id: str, frame: Any) -> None:
        judge = self.judge
        assert judge is not None
        timeout = self.settings.gemini_timeout_s

        def job() -> None:
            value = call_with_timeout(lambda: judge.check(frame), timeout)
            if value is not None:
                self.post(ConfidenceIn(incident_id, float(value)))

        self.runner.submit(job, "gemini-check")

    def _follow_up(self, incident_id: str, trigger: str, frame: Any) -> None:
        """After escalation, on its own: the summary and the snapshot, each with a time limit
        and no retry. Then one write with whatever arrived."""
        results: dict[str, Any] = {}

        def summary() -> None:
            if self.judge is not None and frame is not None:
                results["summary"] = call_with_timeout(
                    lambda: self.judge.summary(frame, trigger), self.settings.summary_timeout_s
                )

        def snapshot() -> None:
            if self.uploader is not None and frame is not None:
                results["snapshot"] = call_with_timeout(
                    lambda: self.uploader(incident_id, frame), self.settings.snapshot_timeout_s
                )

        jobs = [threading.Thread(target=summary, daemon=True),
                threading.Thread(target=snapshot, daemon=True)]
        for job in jobs:
            job.start()
        limit = max(self.settings.summary_timeout_s, self.settings.snapshot_timeout_s) + 1.0
        for job in jobs:
            job.join(limit)
        written = results.get("summary")
        summary_text = text.clean(written) if written else text.fixed_summary(trigger)
        self.post(ReportIn(incident_id, summary_text, results.get("snapshot")))

    def _poll_ack(self) -> None:
        if self.store is None or self._ack_polling:
            return
        incident_id = self.machine.incident_id
        if incident_id is None:
            return
        store = self.store
        self._ack_polling = True

        def job() -> None:
            try:
                rows = store.select("incidents", {"id": f"eq.{incident_id}"},
                                    "status,acknowledged_by,acknowledged_at")
            except (StoreUnavailable, StoreRejected):
                return
            finally:
                self._ack_polling = False
            if rows and rows[0].get("status") == "acknowledged":
                by = rows[0].get("acknowledged_by") or "Family"
                self.post(AckIn(str(by), rows[0].get("acknowledged_at"), local=False))

        self.runner.submit(job, "ack-poll")


@dataclass(frozen=True)
class _Resumed:
    effects: list[Effect]
