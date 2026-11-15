"""Which Chert line to use, and what state it is in, in plain words."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("argos_call.lines")


def choose(lines: list[dict[str, Any]], wanted: str) -> tuple[dict[str, Any] | None, str]:
    """The line to call from, and a note. `CHERT_LINE_ID` if the project has it; otherwise
    the project's only line (the id changes when onboarding gives a new line)."""
    if wanted:
        for line in lines:
            if str(line.get("id")) == wanted:
                return line, "using the line set in CHERT_LINE_ID"
    if len(lines) == 1:
        note = ("CHERT_LINE_ID is not one of the project's lines (onboarding may have given a "
                "new line); using the project's only line. Put its id in CHERT_LINE_ID."
                if wanted else "using the project's only line")
        return lines[0], note
    if not lines:
        return None, ("the project has no line. Get one back with: cd call; npx --yes "
                      "@trychert/facetime@0.1.0-beta.21 onboard (minutes are kept)")
    return None, "the project has several lines; set CHERT_LINE_ID to the one to use"


def describe(line: dict[str, Any]) -> list[str]:
    health = line.get("session_health") or {}
    readiness = health.get("readiness") or {}
    caps = health.get("capabilities") or {}
    out = [
        f"line {line.get('display_name') or '?'}: status {line.get('status')}, "
        f"availability {line.get('availability')}, worker {health.get('status') or '?'}, "
        f"current call {'yes' if line.get('current_call_id') else 'none'}",
        f"  outbound audio {'yes' if caps.get('outbound_audio_protocol') else 'no'}, "
        f"outbound video {'yes' if caps.get('outbound_video_protocol') else 'no'}, "
        f"video ready {readiness.get('video_ready')}, framing {line.get('video_framing')}",
    ]
    return out


def busy(line: dict[str, Any]) -> bool:
    health = line.get("session_health") or {}
    return bool(line.get("current_call_id") or line.get("worker_occupied")
                or str(line.get("availability") or "available") != "available"
                or str(health.get("status") or "accepting") != "accepting")
