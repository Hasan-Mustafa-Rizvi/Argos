"""A whole run of the call agent on fakes: backend, Chert, LiveKit, voice and models."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from argos_call import config
from argos_call.backend import MemoryBackend, new_id
from argos_call.calling import Caller
from argos_call.clock import FakeClock, iso
from argos_call.escalate import Escalator
from argos_call.redact import Redactor, install
from argos_call.state import Handled, Seconds
from argos_call.watch import Watcher
from tests.fakes import (
    FakeAgent,
    FakeAnswers,
    FakeChertServer,
    FakeLiveView,
    FakePhrases,
    FakeRooms,
    FakeSpeech,
    chert_api,
    env,
    talking_feed,
)

BASE = datetime(2026, 11, 15, 19, 0, 0, tzinfo=UTC)
DEVICE = "a0000000-0000-4000-8000-000000000001"


def escalated_incident(backend: MemoryBackend, at: datetime, started_at: datetime | None = None,
                       summary: str = "A person is lying on the floor by the sofa.",
                       snapshot: bytes | None = None) -> str:
    incident_id = new_id()
    path = f"incidents/{incident_id}/snapshot.jpg" if snapshot else None
    if snapshot:
        backend.files[path] = snapshot  # type: ignore[index]
    backend.incidents[incident_id] = {
        "id": incident_id, "device_id": DEVICE, "trigger": "fall", "status": "escalated",
        "started_at": iso(started_at or at - timedelta(seconds=12)), "summary": summary,
        "snapshot_path": path}
    backend.events.append({"id": new_id(), "device_id": DEVICE, "incident_id": incident_id,
                           "at": iso(at), "kind": "escalated",
                           "text": "No answer after 10 seconds. Argos is calling for help.",
                           "detail": {}})
    return incident_id


@dataclass
class Run:
    tmp: Path
    server: FakeChertServer
    backend: MemoryBackend
    clock: FakeClock
    redactor: Redactor
    logs: io.StringIO
    settings: config.Settings
    rooms: FakeRooms
    escalator: Escalator | None = None
    watcher: Watcher | None = None
    caller: Caller | None = None
    phrases: Any = None
    answers: Any = None
    speech: Any = None
    lives: list[FakeLiveView] = field(default_factory=list)

    def build(self, demo: bool = False, live: bool = True, feed_bursts: int = 6) -> None:
        handled = Handled(self.settings.state_dir)
        seconds = Seconds(self.settings.state_dir)
        chert = chert_api(self.server, self.redactor)
        real, _ = self.settings.can_call_for_real()

        def say(message: str) -> None:
            logging.getLogger("argos_call").info("%s", message)

        def live_view(on_jpeg: Any) -> FakeLiveView:
            viewer = FakeLiveView(on_jpeg, self.clock)
            self.lives.append(viewer)
            return viewer

        self.caller = Caller(
            self.settings, self.backend, chert, self.rooms, self.speech, self.clock, seconds,
            say, self.redactor, lambda picture, identity: FakeAgent(identity),
            phrases=self.phrases, answers=self.answers,
            live_view=live_view if live else None, line_id="line-1", demo=demo,
            feed=talking_feed(feed_bursts)) if real else None
        self.escalator = Escalator(self.settings, self.backend, chert, handled, seconds,
                                   self.clock, say, self.redactor,
                                   place_call=self.caller.place if self.caller else None,
                                   demo=demo, line_id="line-1")
        self.watcher = Watcher(self.backend, self.escalator, handled, DEVICE, self.clock, 1.5,
                               say, self.redactor)

    def once(self) -> int:
        assert self.watcher is not None
        return asyncio.run(self.watcher.once())

    def files(self) -> dict[str, str]:
        return {p.name: p.read_text(encoding="utf-8") for p in self.tmp.iterdir() if p.is_file()}

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        rows = [e for e in self.backend.events if e["kind"] != "escalated"]
        return [e for e in rows if kind is None or e["kind"] == kind]

    def everything_written(self) -> str:
        """Every log line, every record and every state file, as one text."""
        return "\n".join([self.logs.getvalue(), json.dumps(self.backend.events),
                          json.dumps(self.backend.incidents), *self.files().values()])


def make_run(tmp_path: Path, server: FakeChertServer | None = None, now: datetime = BASE,
             phrases: Any = "default", answers: Any = "default", speech: Any = None,
             **overrides: str | None) -> Run:
    redactor = Redactor()
    logs = io.StringIO()
    install(redactor, logging.INFO, stream=logs)
    settings = config.from_env(env(tmp_path, **overrides), redactor)
    clock = FakeClock(base=now)
    return Run(tmp=tmp_path, server=server or FakeChertServer(ready_after_polls=2),
               backend=MemoryBackend(), clock=clock, redactor=redactor, logs=logs,
               settings=settings, rooms=FakeRooms(redactor),
               phrases=FakePhrases() if phrases == "default" else phrases,
               answers=FakeAnswers() if answers == "default" else answers,
               speech=speech or FakeSpeech())
