"""An escalated incident, and every sentence this part says or writes about it.

Rule 6: say only what the incident says. Every spoken line is built here from the incident's
own fields: the trigger, the time it escalated, the stored summary, and which picture is on
screen. Nothing here diagnoses, says anyone is hurt or fine, or adds a detail. The only advice
is to call emergency services if the person thinks it is needed.

No sentence uses a pronoun for the person watched, and none contains an em or en dash.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_DASHES = re.compile(r"\s*[‒–—―−﹘﹣－]+\s*")


def clean(value: str) -> str:
    """No em or en dash (or look-alike) reaches a record or the voice."""
    text = _DASHES.sub(", ", value)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip().strip(",").strip()


@dataclass
class Incident:
    id: str
    trigger: str
    escalated_at: datetime
    person: str = ""
    summary: str = ""
    snapshot_path: str = ""
    made_up: bool = False

    @property
    def who(self) -> str:
        return clean(self.person) if self.person else "the person I watch over"

    @property
    def time(self) -> str:
        return clock_time(self.escalated_at)


def clock_time(stamp: datetime) -> str:
    """"3:41 PM", in this machine's time zone."""
    return stamp.astimezone().strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------- the voice


def noticed(incident: Incident) -> str:
    who = incident.who
    return {
        "fall": "I saw what looked like a fall",
        "help_call": "I heard what sounded like a call for help",
        "stillness": f"I noticed that {who} had not moved for a long time",
        "manual": "a check was started by hand",
    }.get(incident.trigger, "something made me start a check")


def greeting(incident: Incident) -> str:
    test = "This is a test, about a made-up alert. " if incident.made_up else ""
    return clean(f"{test}This is Argos, the companion dog watching over {incident.who}. "
                 f"At {incident.time} {noticed(incident)}. "
                 f"I asked if {incident.who} was okay and got no answer.")


def picture_line(kind: str, incident: Incident) -> str:
    if kind == "live":
        return "You are seeing my camera now."
    if kind == "snapshot":
        return f"This is the picture I took at {incident.time}."
    return ""


def summary_line(incident: Incident) -> str:
    return clean(f"Here is what I wrote down: {incident.summary}") if incident.summary else ""


ASK = ("If you are on your way, say: I'm on my way. You can also ask me what I saw. "
       "If you think it is needed, call emergency services.")
ASK_AGAIN = "Are you still there? If you are on your way, say: I'm on my way."
HEARD_ACK = "I heard that you are on your way."
NOT_SURE = "Sorry, I did not catch that. If you are on your way, say: I'm on my way."
ALREADY = "Someone has already acknowledged this alert. Thank you. Goodbye."
ACK_FAILED = ("I could not mark the alert as acknowledged. Please acknowledge it on the "
              "dashboard. Goodbye.")
NO_ANSWERS = "I can only tell you what I saw. " + ASK
GOODBYE_SILENT = "I will hang up now. The alert is still open on the dashboard. Goodbye."


ACK_DONE = "Thank you. I have marked the alert as acknowledged on the dashboard. Goodbye."


def closing(incident: Incident) -> str:
    return clean(f"I have to hang up now. To repeat: at {incident.time} {noticed(incident)}, "
                 f"and {incident.who} did not answer when I asked. Goodbye.")


def text_message(incident: Incident) -> str:
    """The iMessage, in two sentences: who is watched, what Argos noticed and when, and that
    it is calling now. A made-up alert says it is a test."""
    test = "Test, made-up alert. " if incident.made_up else ""
    return clean(f"{test}Argos here, watching over {incident.who}: at {incident.time} "
                 f"{noticed(incident)}, and {incident.who} did not answer when I asked. "
                 "I am calling you on FaceTime now.")


# ---------------------------------------------------------------------- the records


def ack_label(contact_label: str) -> str:
    """Contract section 4: the contact's label followed by ", by FaceTime"."""
    return clean(f"{contact_label}, by FaceTime")


def message_sent(to: str, dry_run: bool) -> str:
    if dry_run:
        return clean(f"Dry run: a text to {to} would be sent now. No text was sent.")
    return clean(f"Argos texted {to}.")


def call_placed(to: str, dry_run: bool) -> str:
    if dry_run:
        return clean(f"Dry run: a FaceTime call to {to} would be placed now. No call was made.")
    return clean(f"Argos is calling {to} on FaceTime.")


def call_answered(to: str) -> str:
    return clean(f"{to} answered the FaceTime call.")


def call_failed(to: str, reason: str) -> str:
    return clean(f"The FaceTime call to {to} did not go through: {reason}.")
