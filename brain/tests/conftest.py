"""Shared fakes. No test needs a key, a camera, a microphone, a port, a robot or a network."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from argos import DEVICE_ID
from argos.body.base import Body, BodyHub
from argos.brain import Brain, InlineRunner
from argos.clock import FakeClock
from argos.config import Settings
from argos.escalation import make_escalator
from argos.locallog import MemoryLog
from argos.records import Recorder
from argos.store import MemoryStore
from argos.writer import RecordWriter

# Marker strings stand in for contact values. They are not phone numbers or addresses.
FACETIME_MARKER = "MARKER-FACETIME-VALUE"
EMAIL_MARKER = "MARKER-EMAIL-VALUE"

BASE_ENV = {
    "SUPABASE_URL": "http://backend.invalid",
    "SUPABASE_SERVICE_ROLE_KEY": "MARKER-KEY",
    "CONTACT_LABEL": "Daughter",
    "CHECK_TIMEOUT_S": "10",
}


def seeded_store(person_label: str = "Eleni") -> MemoryStore:
    store = MemoryStore()
    store.tables["devices"].append(
        {"id": DEVICE_ID, "name": "Argos", "person_label": person_label, "state": "calm",
         "last_seen_at": None, "fw": None, "caps": []}
    )
    return store


@dataclass
class Rig:
    brain: Brain
    clock: FakeClock
    store: MemoryStore
    log: MemoryLog
    writer: RecordWriter
    settings: Settings
    sent: list[Any] = field(default_factory=list)

    def run_for(self, seconds: float, dt: float = 0.1) -> None:
        steps = int(round(seconds / dt))
        for _ in range(steps):
            self.clock.advance(dt)
            self.brain.step()

    def step(self) -> None:
        self.brain.step()

    def incident(self, incident_id: str | None = None) -> dict[str, Any]:
        rows = self.store.tables["incidents"]
        if incident_id is None:
            return rows[-1]
        return next(r for r in rows if r["id"] == incident_id)

    def event_kinds(self) -> list[str]:
        return [e["kind"] for e in self.store.tables["events"]]

    def everything_written(self) -> str:
        """Every byte that went to the store or the local log, as text."""
        parts = [json.dumps(self.store.tables, default=str), json.dumps(self.store.ops,
                                                                         default=str)]
        parts.extend(self.log.lines)
        parts.extend(repr(k) for k in self.store.files)
        return "\n".join(parts)


def make_rig(
    env: dict[str, str] | None = None,
    store: MemoryStore | None = None,
    bodies: list[Body] | None = None,
    runner: Any = None,
    use_store_for_reads: bool = True,
    **brain_kwargs: Any,
) -> Rig:
    settings = Settings.from_env({**BASE_ENV, **(env or {})})
    clock = FakeClock()
    store = store if store is not None else seeded_store()
    log = MemoryLog()
    writer = RecordWriter(store, threaded=False)
    recorder = Recorder(settings.device_id, clock, writer, log)
    escalator = brain_kwargs.pop("escalator", None) or make_escalator(settings, recorder)
    hub = BodyHub(bodies or [], clock.now)
    brain = Brain(
        settings, clock, recorder, writer, hub, escalator, runner or InlineRunner(),
        store=store if use_store_for_reads else None, **brain_kwargs,
    )
    return Rig(brain, clock, store, log, writer, settings)


@pytest.fixture
def rig() -> Iterator[Rig]:
    rig = make_rig()
    rig.brain.start()
    yield rig


@pytest.fixture
def rig_factory() -> Callable[..., Rig]:
    return make_rig
