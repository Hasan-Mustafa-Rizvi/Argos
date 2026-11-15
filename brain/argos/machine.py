"""The state machine of contract section 1. No I/O: time is passed in, effects are returned.

            trigger
    calm ──────────────▶ checking ── answer or pat ──▶ calm        incident: stood_down
                             │
                             └── no answer in CHECK_TIMEOUT_S ──▶ alert   incident: escalated
                                                                     │
                                                         acknowledged ──▶ calm

Rules this module keeps:

- The wait starts when "Are you okay?" has been asked, not when the trigger fired. If the
  question is never reported as asked (no voice, a stuck speaker), it counts as asked
  `ask_grace_s` after the trigger, so a check can never hang open.
- A trigger during an open check or an alert opens no second incident. It does not extend
  the wait or restart the question either. It is returned as `Ignored`, which the brain
  writes to its local log only.
- In `alert`, an answer or a pat changes nothing. Only an acknowledgement ends an alert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class State(StrEnum):
    CALM = "calm"
    CHECKING = "checking"
    ALERT = "alert"


TRIGGERS = ("fall", "help_call", "stillness", "manual")
STOOD_DOWN_BY = ("voice", "pat")


@dataclass
class Check:
    """The open incident."""

    incident_id: str
    trigger: str
    confidence: float | None
    opened_at: float
    asked_at: float | None = None


@dataclass(frozen=True)
class Opened:
    check: Check


@dataclass(frozen=True)
class Asked:
    incident_id: str
    late: bool = False


@dataclass(frozen=True)
class StoodDown:
    incident_id: str
    by: str
    said: str | None


@dataclass(frozen=True)
class Escalated:
    incident_id: str
    trigger: str


@dataclass(frozen=True)
class Acknowledged:
    incident_id: str
    by: str
    at: str | None
    local: bool


@dataclass(frozen=True)
class Ignored:
    what: str
    reason: str
    detail: dict = field(default_factory=dict)


Effect = Opened | Asked | StoodDown | Escalated | Acknowledged | Ignored


class Machine:
    def __init__(self, timeout_s: float, ask_grace_s: float = 8.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.timeout_s = timeout_s
        self.ask_grace_s = ask_grace_s
        self.state = State.CALM
        self.check: Check | None = None

    # ------------------------------------------------------------------ queries

    @property
    def deadline(self) -> float | None:
        """When the open check escalates, or None while the question is not yet asked."""
        if self.state is State.CHECKING and self.check and self.check.asked_at is not None:
            return self.check.asked_at + self.timeout_s
        return None

    @property
    def incident_id(self) -> str | None:
        return self.check.incident_id if self.check else None

    # ------------------------------------------------------------------ inputs

    def trigger(
        self, trigger: str, confidence: float | None, incident_id: str, now: float
    ) -> list[Effect]:
        if trigger not in TRIGGERS:
            return [Ignored("trigger", "unknown trigger", {"trigger": trigger})]
        if self.state is not State.CALM:
            return [
                Ignored(
                    "trigger",
                    f"a {self.state.value} incident is already open",
                    {"trigger": trigger, "incident_id": self.incident_id},
                )
            ]
        if trigger == "manual":
            confidence = None
        elif confidence is not None:
            confidence = min(1.0, max(0.0, float(confidence)))
        self.check = Check(incident_id, trigger, confidence, opened_at=now)
        self.state = State.CHECKING
        return [Opened(self.check)]

    def asked(self, incident_id: str, now: float) -> list[Effect]:
        check = self.check
        if self.state is not State.CHECKING or not check or check.incident_id != incident_id:
            return []
        if check.asked_at is not None:
            return []
        check.asked_at = now
        return [Asked(incident_id)]

    def answer(self, by: str, said: str | None, now: float) -> list[Effect]:
        if by not in STOOD_DOWN_BY:
            return [Ignored("answer", "unknown answer kind", {"by": by})]
        if self.state is not State.CHECKING or not self.check:
            return [Ignored("answer", f"no open check ({self.state.value})", {"by": by})]
        incident_id = self.check.incident_id
        self.state = State.CALM
        self.check = None
        return [StoodDown(incident_id, by, said if by == "voice" else None)]

    def tick(self, now: float) -> list[Effect]:
        check = self.check
        if self.state is not State.CHECKING or not check:
            return []
        effects: list[Effect] = []
        if check.asked_at is None and now >= check.opened_at + self.ask_grace_s:
            check.asked_at = check.opened_at + self.ask_grace_s
            effects.append(Asked(check.incident_id, late=True))
        deadline = self.deadline
        if deadline is not None and now >= deadline:
            self.state = State.ALERT
            effects.append(Escalated(check.incident_id, check.trigger))
        return effects

    def acknowledge(self, by: str, at: str | None, local: bool, now: float) -> list[Effect]:
        if self.state is not State.ALERT or not self.check:
            return [Ignored("acknowledge", f"no alert ({self.state.value})", {"by": by})]
        incident_id = self.check.incident_id
        self.state = State.CALM
        self.check = None
        return [Acknowledged(incident_id, by, at, local)]

    # ------------------------------------------------------------------ start-up

    def resume_alert(self, incident_id: str, trigger: str, confidence: float | None) -> None:
        """An escalated incident nobody acknowledged is still an alert."""
        self.check = Check(incident_id, trigger, confidence, opened_at=0.0, asked_at=0.0)
        self.state = State.ALERT

    def resume_check(
        self, incident_id: str, trigger: str, confidence: float | None, now: float
    ) -> list[Effect]:
        """Reopen an interrupted check: ask again and wait again, in the same incident."""
        self.check = Check(incident_id, trigger, confidence, opened_at=now)
        self.state = State.CHECKING
        return [Opened(self.check)]
