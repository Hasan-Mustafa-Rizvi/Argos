"""Builds the rows of contract section 3 and records them: local log first, then the backend.

Rules this module enforces, whatever the caller asks:

- Each row is inserted once. After that only the columns that changed are written.
- Every id is made here (uuid4). The backend makes none.
- `summary` and `snapshot_path` can only be written to an incident this brain has already
  recorded as `escalated` (or found escalated on start). Anything else raises PrivacyError
  and nothing is written, locally or remotely.
- Every string is passed through `text.clean()`: no em dash or en dash reaches a record.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from argos import text
from argos.clock import Clock
from argos.locallog import LocalLog
from argos.writer import RecordWriter

log = logging.getLogger("argos.records")

INCIDENT_COLUMNS = (
    "id", "device_id", "trigger", "status", "confidence", "started_at", "ended_at",
    "stood_down_by", "summary", "snapshot_path", "acknowledged_by", "acknowledged_at",
)
PRIVATE_COLUMNS = ("summary", "snapshot_path")


class PrivacyError(Exception):
    """A summary or a snapshot path was about to be written to an incident that has not
    escalated."""


def new_id() -> str:
    return str(uuid.uuid4())


class Recorder:
    def __init__(
        self,
        device_id: str,
        clock: Clock,
        writer: RecordWriter,
        local_log: LocalLog,
        make_id: Callable[[], str] = new_id,
    ) -> None:
        self.device_id = device_id
        self.clock = clock
        self.writer = writer
        self.local_log = local_log
        self.make_id = make_id
        self.person = text.Person()
        self._escalated: set[str] = set()

    # ------------------------------------------------------------------ plumbing

    def _insert(self, table: str, row: dict[str, Any]) -> None:
        row = text.clean_value(row)  # type: ignore[assignment]
        self.local_log.write({"at": self.clock.iso(), "table": table, "op": "insert", "row": row})
        self.writer.insert(table, row)

    def _update(
        self,
        table: str,
        filters: dict[str, str],
        patch: dict[str, Any],
        merge_key: str | None = None,
        on_done: Callable[[int], None] | None = None,
    ) -> None:
        patch = text.clean_value(patch)  # type: ignore[assignment]
        self.local_log.write(
            {"at": self.clock.iso(), "table": table, "op": "update", "match": filters,
             "patch": patch}
        )
        self.writer.update(table, filters, patch, merge_key=merge_key, on_done=on_done)

    def note(self, message: str) -> None:
        self.local_log.note(self.clock.iso(), message)

    # ------------------------------------------------------------------ devices

    def device(self, on_done: Callable[[int], None] | None = None, **columns: Any) -> None:
        """Change only the given columns of this device's row. The row already exists."""
        allowed = {"state", "last_seen_at", "caps", "fw"}
        patch = {k: v for k, v in columns.items() if k in allowed}
        if patch:
            self._update("devices", {"id": f"eq.{self.device_id}"}, patch, merge_key="device",
                         on_done=on_done)

    # ------------------------------------------------------------------ events

    def event(
        self,
        kind: str,
        sentence: str,
        detail: dict[str, Any] | None = None,
        incident_id: str | None = None,
        at: str | None = None,
    ) -> str:
        event_id = self.make_id()
        self._insert(
            "events",
            {
                "id": event_id,
                "device_id": self.device_id,
                "incident_id": incident_id,
                "at": at or self.clock.iso(),
                "kind": kind,
                "text": sentence,
                "detail": detail or {},
            },
        )
        return event_id

    # ------------------------------------------------------------------ readings

    def reading(
        self,
        temp_c: float | None,
        tilt_deg: float | None,
        person_present: bool,
        still_s: int,
        at: str | None = None,
    ) -> None:
        self._insert(
            "readings",
            {
                "device_id": self.device_id,
                "at": at or self.clock.iso(),
                "temp_c": temp_c,
                "tilt_deg": tilt_deg,
                "person_present": bool(person_present),
                "still_s": int(still_s) if person_present else 0,
            },
        )

    # ------------------------------------------------------------------ incidents

    def incident_opened(
        self, incident_id: str, trigger: str, confidence: float | None, started_at: str
    ) -> None:
        row = {column: None for column in INCIDENT_COLUMNS}
        row.update(
            id=incident_id,
            device_id=self.device_id,
            trigger=trigger,
            status="checking",
            confidence=confidence,
            started_at=started_at,
        )
        self._insert("incidents", row)

    def incident_stood_down(self, incident_id: str, by: str, at: str) -> None:
        self._update(
            "incidents",
            {"id": f"eq.{incident_id}", "status": "eq.checking"},
            {"status": "stood_down", "ended_at": at, "stood_down_by": by},
        )

    def incident_escalated(self, incident_id: str) -> None:
        self._escalated.add(incident_id)
        self._update(
            "incidents",
            {"id": f"eq.{incident_id}", "status": "eq.checking"},
            {"status": "escalated"},
        )

    def mark_escalated(self, incident_id: str) -> None:
        """For an incident found escalated in the backend on start."""
        self._escalated.add(incident_id)

    def incident_confidence(self, incident_id: str, confidence: float) -> None:
        self._update(
            "incidents",
            {"id": f"eq.{incident_id}"},
            {"confidence": min(1.0, max(0.0, float(confidence)))},
        )

    def incident_report(
        self, incident_id: str, summary: str | None, snapshot_path: str | None
    ) -> None:
        """The summary and the snapshot path, after escalation only. Touches only those."""
        if incident_id not in self._escalated:
            raise PrivacyError(f"incident {incident_id} has not escalated")
        patch: dict[str, Any] = {}
        if summary:
            patch["summary"] = summary
        if snapshot_path:
            patch["snapshot_path"] = snapshot_path
        if patch:
            self._update(
                "incidents",
                {"id": f"eq.{incident_id}", "status": "in.(escalated,acknowledged)"},
                patch,
            )

    def incident_acknowledged_locally(self, incident_id: str, by: str, at: str) -> None:
        """A local key acknowledged. The brain writes what the dashboard would have, plus
        `ended_at`, and only if the incident is still escalated."""
        self._update(
            "incidents",
            {"id": f"eq.{incident_id}", "status": "eq.escalated"},
            {"status": "acknowledged", "acknowledged_by": by, "acknowledged_at": at,
             "ended_at": at},
        )

    def incident_ended_after_acknowledgement(self, incident_id: str, at: str) -> None:
        """The dashboard acknowledged. The brain sets `ended_at` to that same instant."""
        self._update(
            "incidents",
            {"id": f"eq.{incident_id}", "status": "eq.acknowledged"},
            {"ended_at": at},
        )
