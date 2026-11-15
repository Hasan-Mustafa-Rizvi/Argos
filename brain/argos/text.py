"""Every sentence the brain writes into a record, in one place.

The shapes follow `contract/fixtures/demo_scenario.jsonl`. No sentence contains an em dash or
an en dash: `clean()` removes any that arrive from outside (a label, a Gemini summary).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Dash-like characters that are not a plain hyphen: figure dash, en dash, em dash, horizontal
# bar, minus sign, small and full-width em dashes.
_DASHES = re.compile(r"\s*[‒–—―−﹘﹣－]+\s*")


def clean(value: str) -> str:
    """Replace any em or en dash (and their look-alikes) with a comma, tidy the spacing."""
    text = _DASHES.sub(", ", value)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip().strip(",").strip()


def clean_value(value: object) -> object:
    """`clean()` applied to every string inside a row, a detail or a list."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    return value


@dataclass(frozen=True)
class Person:
    """How sentences name the person. Read from `devices.person_label`, never from code."""

    label: str | None = None

    @property
    def subject(self) -> str:
        return clean(self.label) if self.label else "The person"

    @property
    def object(self) -> str:
        return clean(self.label) if self.label else "the person"


ASK_LINE = "Are you okay?"
KEYBOARD_ANSWER = "I'm fine"
DEMO_LABEL = "Demo"

_TRIGGER_TEXT = {
    "fall": "Argos saw someone on the floor.",
    "help_call": "Argos heard a call for help.",
    "stillness": "Argos noticed {person} has not moved for a long time.",
    "manual": "A check on {person} was started by hand.",
}

_SUMMARY_TEXT = {
    "fall": "Argos saw someone on the floor, and nobody answered when it asked if they were okay.",
    "help_call": "Argos heard a call for help, and nobody answered when it asked if they "
    "were okay.",
    "stillness": "Argos saw someone who had not moved for a long time, and nobody answered "
    "when it asked if they were okay.",
    "manual": "A check was started by hand, and nobody answered when Argos asked if they "
    "were okay.",
}


def device_online() -> str:
    return "Argos is online."


def trigger(kind: str, person: Person) -> str:
    return _TRIGGER_TEXT.get(kind, "Argos started a check.").format(person=person.object)


def asked(said: str) -> str:
    return f"Argos asked: {said}"


def heard(person: Person, said: str) -> str:
    return f"{person.subject} answered: {said}"


def pat(person: Person) -> str:
    return f"{person.subject} gave Argos a pat."


def stood_down(person: Person, by: str) -> str:
    if by == "pat":
        return f"Argos stood down. {person.subject} gave it a pat."
    return f"Argos stood down. {person.subject} answered."


def escalated(timeout_s: float) -> str:
    return f"No answer after {timeout_s:g} seconds. Argos is calling for help."


def call_placed_dry_run(to: str) -> str:
    return f"Dry run: a FaceTime call to {to} would be placed now. No call was made."


def email_sent_dry_run(to: str) -> str:
    return f"Dry run: a backup email to {to} would be sent now. No email was sent."


def acknowledged(by: str) -> str:
    return f"{by} acknowledged. Help is on the way."


def device_tipped() -> str:
    return "Argos was knocked over."


def fixed_summary(kind: str) -> str:
    return _SUMMARY_TEXT.get(kind, "A check failed: nobody answered when Argos asked.")
