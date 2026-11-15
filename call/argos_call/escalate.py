"""Stage 3: an escalated incident gets one text, then one call. Ever.

Rule 1. `ARGOS_DRY_RUN` missing, `1`, or anything but `0` means dry-run: the text and the call
are logged, neither goes out, nothing at all is sent to Chert, and the events are recorded
with `"dry_run": true`.

Rule 3. The guarantee is the handled list on disk: before the text is sent, and before the
call is requested, the incident's step is written as started. A restart, or the same record
arriving three times, finds it there and does nothing. Chert's idempotency key is one per
attempt (the incident id plus a counter) and is reused only to send that same attempt again.
An incident that escalated more than two minutes ago is ignored: never call about old news.

Events, shaped as contract section 3, written on the incident the way the brain writes its
own: `message_sent`, `call_placed`, `call_answered`, `call_failed`. A refused text is logged
locally and writes no event. A made-up incident's events stay in memory and are printed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from argos_call import config
from argos_call import incident as words
from argos_call.backend import Backend, BackendError, new_id
from argos_call.chert import ChertAPI
from argos_call.clock import Clock, parse_iso
from argos_call.incident import Incident
from argos_call.redact import Redactor
from argos_call.state import Handled, Seconds

log = logging.getLogger("argos_call.escalate")

MAX_AGE_S = 120.0
REPORT_WAIT_S = 12.0

Report = Callable[[str], None]


class Events:
    def __init__(self, backend: Backend, device_id: str, clock: Clock, report: Report,
                 redactor: Redactor) -> None:
        self.backend = backend
        self.device_id = device_id
        self.clock = clock
        self.report = report
        self.redactor = redactor
        self.written: list[dict[str, Any]] = []

    async def add(self, incident: Incident, kind: str, text: str,
                  detail: dict[str, Any]) -> None:
        row = {"id": new_id(), "device_id": self.device_id, "incident_id": incident.id,
               "at": self.clock.iso(), "kind": kind, "text": words.clean(text),
               "detail": detail}
        self.written.append(row)
        where = "in memory (made-up incident)" if incident.made_up else "on the incident"
        self.report(f"event {kind} {where}: {row['text']} {json.dumps(detail)}")
        try:
            await self.backend.add_event(row)
        except BackendError as exc:
            log.warning("the %s event was not written (%s)", kind, self.redactor.mask(exc))


@dataclass
class CallOutcome:
    placed: bool
    answered: bool
    reason: str


PlaceCall = Callable[[Incident, Events], Awaitable[CallOutcome]]


def plain_reason(outcome: str, reason: str, answered: bool, ended_by: str) -> str:
    """A short reason for `call_failed`, in plain words. Carries no number, key or token."""
    if outcome == "busy":
        return "the line was busy" + (", even after waiting two minutes"
                                      if "two minutes" in reason else "")
    if outcome == "refused":
        return f"Chert refused the call ({reason[:120]})" if reason else "Chert refused the call"
    if outcome == "uncertain":
        return "Chert did not answer the request"
    if outcome == "placed" and not answered:
        return "nobody answered"
    if ended_by == "error":
        return "the call agent hit an error"
    return reason[:120] or "the call did not connect"


class Escalator:
    def __init__(self, settings: config.Settings, backend: Backend, chert: ChertAPI | None,
                 handled: Handled, seconds: Seconds, clock: Clock, report: Report,
                 redactor: Redactor, place_call: PlaceCall | None = None,
                 demo: bool = False, line_id: str = "") -> None:
        self.settings = settings
        self.backend = backend
        self.chert = chert
        self.handled = handled
        self.seconds = seconds
        self.clock = clock
        self.report = report
        self.redactor = redactor
        self.place_call = place_call
        self.demo = demo
        self.line_id = line_id or settings.chert_line_id
        self.events = Events(backend, settings.device_id, clock, report, redactor)

    def age_s(self, incident: Incident) -> float:
        return (self.clock.wall() - incident.escalated_at).total_seconds()

    async def handle(self, incident: Incident) -> None:
        age = self.age_s(incident)
        if age > MAX_AGE_S:
            if self.handled.get(incident.id) is None:
                self.report(f"incident {incident.id[:8]} escalated {age / 60:.1f} minutes ago: "
                            "old news, not texting or calling")
                self.handled.mark(incident.id, ignored="old", seen_at=self.clock.iso())
            return
        self.report(f"incident {incident.id[:8]} escalated {age:.0f} s ago ({incident.trigger})")
        await self._text(incident)
        await self._call(incident)

    # ------------------------------------------------------------------ the text

    async def _text(self, incident: Incident) -> None:
        if not self.handled.claim(incident.id, "text", self.clock.iso()):
            self.report("already texted about this incident; not again")
            return
        to = self.settings.contact_label
        message = words.text_message(incident)
        if self.settings.dry_run or self.chert is None or not self.settings.chert_configured:
            self.report(f"dry-run: would text {to} over iMessage: {message!r}")
            await self.events.add(incident, "message_sent", words.message_sent(to, True),
                                  {"channel": "imessage", "to": to, "dry_run": True})
            self.handled.finish(incident.id, "text", "dry_run")
            return
        sent = await self.chert.send_message(self.line_id, self.settings.contact_facetime_to,
                                             message, f"argos-{incident.id}-text-1")
        if sent.ok:
            self.report(f"texted {to} over iMessage")
            await self.events.add(incident, "message_sent", words.message_sent(to, False),
                                  {"channel": "imessage", "to": to, "dry_run": False})
            self.handled.finish(incident.id, "text", "sent")
        else:
            reason = self.redactor.mask(sent.reason)
            self.report(f"the text to {to} was refused ({reason}); no event is written; "
                        "going on to the call")
            self.handled.finish(incident.id, "text", "refused", reason=reason[:160])

    # ------------------------------------------------------------------ the call

    async def _call(self, incident: Incident) -> None:
        if not self.handled.claim(incident.id, "call", self.clock.iso()):
            self.report("already called about this incident; not again")
            return
        to = self.settings.contact_label
        real, why = self.settings.can_call_for_real()
        if not real or self.chert is None or self.place_call is None:
            self.report(f"dry-run: would call {to} on FaceTime Video now ({why or 'no caller'})")
            self.report(f"dry-run: the agent would open with: {words.greeting(incident)!r}")
            await self.events.add(incident, "call_placed", words.call_placed(to, True),
                                  {"channel": "facetime", "to": to, "dry_run": True})
            self.handled.finish(incident.id, "call", "dry_run")
            return
        refusal = self.seconds.refuse(config.BUDGET_S, self.demo)
        if refusal:
            self.report(f"not calling: {refusal}")
            await self.events.add(incident, "call_failed",
                                  words.call_failed(to, "the test minutes are used up"),
                                  {"to": to, "reason": "the test minutes are used up"})
            self.handled.finish(incident.id, "call", "refused_budget")
            return
        try:
            outcome = await self.place_call(incident, self.events)
        except asyncio.CancelledError:
            self.handled.finish(incident.id, "call", "stopped")
            raise
        except Exception as exc:
            log.error("the call failed on an error (%s)", type(exc).__name__)
            outcome = CallOutcome(False, False, "the call agent hit an error")
        if not outcome.placed or not outcome.answered:
            await self.events.add(incident, "call_failed", words.call_failed(to, outcome.reason),
                                  {"to": to, "reason": outcome.reason})
        self.handled.finish(incident.id, "call",
                            "answered" if outcome.answered else
                            ("placed" if outcome.placed else "failed"),
                            reason=outcome.reason)


async def incident_from(row: dict[str, Any], backend: Backend, person: str,
                        first_seen_s: float, clock: Clock, wait_s: float = 5.0
                        ) -> Incident | None:
    """An `Incident` from an escalated row. Its age comes from its `escalated` event. If that
    event is not visible yet, wait a few seconds for it; after that, use the incident's start,
    which is earlier than the escalation and so never makes old news look new."""
    at_text = await backend.escalated_at(str(row["id"]))
    stamp = parse_iso(at_text)
    if stamp is None:
        if clock.now() - first_seen_s < wait_s:
            return None
        stamp = parse_iso(str(row.get("started_at") or ""))
        if stamp is None:
            return None
    return Incident(id=str(row["id"]), trigger=str(row.get("trigger") or ""),
                    escalated_at=stamp, person=person, summary=str(row.get("summary") or ""),
                    snapshot_path=str(row.get("snapshot_path") or ""),
                    made_up=row.get("made_up") is True)


async def wait_for_report(incident: Incident, backend: Backend, clock: Clock,
                          wait_s: float = REPORT_WAIT_S) -> Incident:
    """The brain writes the summary and the snapshot a few seconds after the escalation. Wait
    up to 12 seconds from the escalation for both, then go ahead with what there is."""
    while not (incident.summary and incident.snapshot_path):
        if (clock.wall() - incident.escalated_at).total_seconds() >= wait_s:
            break
        await clock.sleep(1.0)
        try:
            row = await backend.incident(incident.id)
        except BackendError:
            continue
        if row:
            incident.summary = str(row.get("summary") or "") or incident.summary
            incident.snapshot_path = str(row.get("snapshot_path") or "") or incident.snapshot_path
    return incident
