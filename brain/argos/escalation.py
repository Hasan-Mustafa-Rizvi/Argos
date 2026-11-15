"""Escalation: telling family. One interface, three implementations.

- `DryRunEscalator` records what would be sent, with `"dry_run": true`, and sends nothing.
- `CallAgentEscalator`, with `ARGOS_CALL_AGENT=1`: the call agent (`call/`) learns of the
  escalation from the backend, places the call and writes the `call_placed`,
  `call_answered`, `call_failed` and `message_sent` events itself (contract section 3). The
  brain then writes none of those, nor `email_sent`, and places nothing.
- `RealSender` is a stub that raises. Real sending from the brain is not built.

Nothing real leaves by default: `ARGOS_DRY_RUN` missing, `1` or anything else means dry-run.
`ARGOS_DRY_RUN=0` is the only value that asks for real sending, and in this build it is
answered plainly (real sending is not built) and the brain stays in dry-run.

Neither class reads a phone number or an email address. Records carry the contact's label.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from argos import text
from argos.config import Settings
from argos.records import Recorder

log = logging.getLogger("argos.escalation")

NOT_BUILT = (
    "ARGOS_DRY_RUN=0 is set, but real calling and email are not built yet. "
    "Staying in dry-run: nothing will be sent."
)


class Escalator(Protocol):
    dry_run: bool

    def escalate(self, incident_id: str) -> None: ...


class DryRunEscalator:
    dry_run = True

    def __init__(self, recorder: Recorder, contact_label: str) -> None:
        self.recorder = recorder
        self.contact_label = contact_label

    def escalate(self, incident_id: str) -> None:
        to = self.contact_label
        log.info("dry run: would call and email %s now; nothing is sent", to)
        self.recorder.event(
            "call_placed",
            text.call_placed_dry_run(to),
            {"channel": "facetime", "to": to, "dry_run": True},
            incident_id,
        )
        self.recorder.event(
            "email_sent",
            text.email_sent_dry_run(to),
            {"to": to, "dry_run": True},
            incident_id,
        )


CALL_EVENTS = ("call_placed", "call_answered", "call_failed", "message_sent", "email_sent")


class CallAgentEscalator:
    """The call agent places the call and records it. The brain records nothing here."""

    dry_run = True  # the brain itself never sends anything

    def __init__(self, recorder: Recorder) -> None:
        self.recorder = recorder

    def escalate(self, incident_id: str) -> None:
        log.info("escalated: the call agent places the call and records it (ARGOS_CALL_AGENT=1)")


class RealSender:
    """Placeholder for the real FaceTime call and email. Not built in this task."""

    dry_run = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def escalate(self, incident_id: str) -> None:
        raise NotImplementedError("Real sending is not built yet.")


def make_escalator(
    settings: Settings,
    recorder: Recorder,
    real_sender: Callable[..., Escalator] = RealSender,
) -> Escalator:
    """The call agent's, with ARGOS_CALL_AGENT=1; otherwise always the dry-run in this build.
    `real_sender` is never called; it is a parameter so a test can prove that."""
    if settings.call_agent:
        return CallAgentEscalator(recorder)
    if settings.dry_run_off_requested:
        log.warning(NOT_BUILT)
        recorder.note(NOT_BUILT)
    return DryRunEscalator(recorder, settings.contact_label)
