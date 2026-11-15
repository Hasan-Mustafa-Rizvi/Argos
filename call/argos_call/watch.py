"""Stage 2: notice an incident reaching `escalated` for the device.

Polling, every `ARGOS_CALL_POLL_S` seconds (default 1.5): simpler to trust than a live
subscription, and it survives the network coming and going. The backend being unreachable is
logged once and the watching goes on (AGENTS rule 9).

Each escalated incident is passed to the escalator, which applies rule 3 itself. Incidents
already in the handled list are skipped here without another request.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from argos_call.backend import Backend, BackendError
from argos_call.clock import Clock
from argos_call.escalate import Escalator, incident_from
from argos_call.redact import Redactor
from argos_call.state import Handled

log = logging.getLogger("argos_call.watch")


class Watcher:
    def __init__(self, backend: Backend, escalator: Escalator, handled: Handled,
                 device_id: str, clock: Clock, poll_s: float, report: Callable[[str], None],
                 redactor: Redactor) -> None:
        self.backend = backend
        self.escalator = escalator
        self.handled = handled
        self.device_id = device_id
        self.clock = clock
        self.poll_s = poll_s
        self.report = report
        self.redactor = redactor
        self.person = ""
        self._first_seen: dict[str, float] = {}
        self._down = False

    async def once(self) -> int:
        """One look. Returns how many incidents were passed on."""
        try:
            rows = await self.backend.escalated(self.device_id)
            if not self.person:
                self.person = await self.backend.person_label(self.device_id) or ""
        except BackendError as exc:
            if not self._down:
                self.report(f"backend unreachable ({self.redactor.mask(exc)}); still watching")
                self._down = True
            return 0
        if self._down:
            self.report("backend reachable again")
            self._down = False
        passed = 0
        for row in rows:
            incident_id = str(row.get("id") or "")
            if not incident_id or self.handled.get(incident_id) is not None:
                continue
            first = self._first_seen.setdefault(incident_id, self.clock.now())
            try:
                incident = await incident_from(row, self.backend, self.person, first, self.clock)
            except BackendError:
                continue
            if incident is None:
                continue
            await self.escalator.handle(incident)
            passed += 1
        return passed

    async def run(self, stop: asyncio.Event | None = None) -> None:
        self.report(f"watching for escalations every {self.poll_s:g} s")
        while stop is None or not stop.is_set():
            await self.once()
            await self.clock.sleep(self.poll_s)
