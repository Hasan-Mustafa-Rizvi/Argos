"""The scripted run: the story of `contract/fixtures/demo_scenario.jsonl`, played live.

It drives the state machine with the same triggers at the same moments, so a live dashboard
shows the same two incidents as the replay. It copies no rows: the brain records everything
as it would in a real run. The escalation is not scripted. It happens because nobody
answers the second check within `CHECK_TIMEOUT_S`.

The steps are read from the fixture when it is there, so the run follows the fixture if the
fixture changes. `BUILT_IN` is the same story, used when the brain runs without the repo.

The fixture's confidence numbers stand in for the detector's score, and its answer is played
as heard speech. The acknowledgement is recorded with the label "Demo", because nobody's
daughter pressed it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from argos.config import BRAIN_DIR

log = logging.getLogger("argos.script")

FIXTURE = BRAIN_DIR.parent / "contract" / "fixtures" / "demo_scenario.jsonl"


@dataclass(frozen=True)
class Step:
    at_s: float
    action: str  # "trigger", "answer" or "ack"
    trigger: str | None = None
    confidence: float | None = None
    by: str | None = None
    said: str | None = None


BUILT_IN = (
    Step(12.0, "trigger", trigger="help_call", confidence=0.84),
    Step(17.0, "answer", by="voice", said="I'm fine, I just dropped my book."),
    Step(38.0, "trigger", trigger="fall", confidence=0.91),
    Step(70.0, "ack"),
)
BUILT_IN_LENGTH_S = 90.0


def from_fixture(path: Path = FIXTURE) -> tuple[tuple[Step, ...], float]:
    """The steps and the length of the run, read from the fixture."""
    steps: list[Step] = []
    length_ms = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            at = entry["offset_ms"] / 1000.0
            length_ms = max(length_ms, entry["offset_ms"])
            row = entry["row"]
            if entry["table"] == "incidents" and entry["op"] == "insert":
                steps.append(Step(at, "trigger", trigger=row["trigger"],
                                  confidence=row.get("confidence")))
            elif entry["table"] == "events" and row["kind"] == "heard":
                steps.append(Step(at, "answer", by="voice", said=row["detail"].get("said")))
            elif entry["table"] == "events" and row["kind"] == "pat":
                steps.append(Step(at, "answer", by="pat"))
            elif entry["table"] == "events" and row["kind"] == "acknowledged":
                steps.append(Step(at, "ack"))
    return tuple(steps), length_ms / 1000.0


def load(path: Path = FIXTURE) -> tuple[tuple[Step, ...], float]:
    try:
        return from_fixture(path)
    except (OSError, ValueError, KeyError) as exc:
        log.info("fixture not readable (%s); using the built-in script", exc)
        return BUILT_IN, BUILT_IN_LENGTH_S


class ScriptPlayer:
    def __init__(self, steps: tuple[Step, ...], length_s: float, loop: bool = False) -> None:
        self.steps = steps
        self.length_s = length_s
        self.loop = loop
        self._start: float | None = None
        self._next = 0
        self.finished = False

    def start(self, now: float) -> None:
        self._start = now
        self._next = 0
        self.finished = False

    def due(self, now: float) -> list[Step]:
        if self._start is None or self.finished:
            return []
        elapsed = now - self._start
        due: list[Step] = []
        while self._next < len(self.steps) and self.steps[self._next].at_s <= elapsed:
            due.append(self.steps[self._next])
            self._next += 1
        if self._next >= len(self.steps) and elapsed >= self.length_s:
            if self.loop:
                self.start(self._start + self.length_s)
            else:
                self.finished = True
                log.info("scripted run finished; the brain keeps running")
        return due
