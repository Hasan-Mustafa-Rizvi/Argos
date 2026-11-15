"""The backend (Supabase), with the secret key, which stays on this machine.

Reads: escalated incidents for the device, an incident's `escalated` event (its age), its
timeline, the device's person label, and the one stored snapshot (into memory).

Writes, and only these:

- events on an incident (`message_sent`, `call_placed`, `call_answered`, `call_failed`),
  inserted the way the brain inserts them: a new uuid, `on_conflict=id`, ignore duplicates;
- the acknowledgement the dashboard makes (contract section 4): one update of `status`,
  `acknowledged_by` and `acknowledged_at`, filtered to the incident and to `escalated`.

The call agent never writes the `acknowledged` event and never touches the device: the brain
sees the change and does both.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from argos_call.redact import Redactor

log = logging.getLogger("argos_call.backend")

INCIDENT_COLUMNS = "id,device_id,trigger,status,started_at,summary,snapshot_path"


def auth_headers(key: str) -> dict[str, str]:
    """As the brain does: a new secret key (sb_secret_...) goes on `apikey` only; a legacy
    service-role JWT also goes on `Authorization`, which Storage reads."""
    headers = {"apikey": key}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class BackendError(Exception):
    """The backend could not be reached or refused. The message is masked."""


class Backend(Protocol):
    async def escalated(self, device_id: str) -> list[dict[str, Any]]: ...

    async def incident(self, incident_id: str) -> dict[str, Any] | None: ...

    async def escalated_at(self, incident_id: str) -> str | None: ...

    async def timeline(self, incident_id: str) -> list[dict[str, Any]]: ...

    async def person_label(self, device_id: str) -> str | None: ...

    async def snapshot(self, path: str) -> bytes | None: ...

    async def add_event(self, row: dict[str, Any]) -> None: ...

    async def acknowledge(self, incident_id: str, by: str, at: str) -> bool: ...


class Supabase:
    def __init__(self, url: str, key: str, redactor: Redactor, timeout_s: float = 6.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.redactor = redactor
        self._client = httpx.AsyncClient(
            base_url=url, headers={**auth_headers(key), "User-Agent": "argos-call"},
            timeout=timeout_s, follow_redirects=False, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendError(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = str(body.get("message") or body.get("error") or "")
            except ValueError:
                pass
            raise BackendError(self.redactor.mask(
                f"{method} {path}: HTTP {response.status_code} {detail}".strip())[:240])
        return response

    async def _rows(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = await self._send("GET", f"/rest/v1/{table}", params=params)
        data = response.json()
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    async def escalated(self, device_id: str) -> list[dict[str, Any]]:
        return await self._rows("incidents", {
            "device_id": f"eq.{device_id}", "status": "eq.escalated",
            "select": INCIDENT_COLUMNS, "order": "started_at.desc", "limit": "5"})

    async def incident(self, incident_id: str) -> dict[str, Any] | None:
        rows = await self._rows("incidents", {"id": f"eq.{incident_id}",
                                              "select": INCIDENT_COLUMNS})
        return rows[0] if rows else None

    async def escalated_at(self, incident_id: str) -> str | None:
        rows = await self._rows("events", {
            "incident_id": f"eq.{incident_id}", "kind": "eq.escalated", "select": "at",
            "order": "at.asc", "limit": "1"})
        return str(rows[0]["at"]) if rows and rows[0].get("at") else None

    async def timeline(self, incident_id: str) -> list[dict[str, Any]]:
        return await self._rows("events", {
            "incident_id": f"eq.{incident_id}", "select": "at,kind,text",
            "order": "at.asc", "limit": "50"})

    async def person_label(self, device_id: str) -> str | None:
        rows = await self._rows("devices", {"id": f"eq.{device_id}", "select": "person_label"})
        return str(rows[0].get("person_label") or "") or None if rows else None

    async def snapshot(self, path: str) -> bytes | None:
        """The stored snapshot, into memory only."""
        response = await self._send("GET", f"/storage/v1/object/snapshots/{quote(path)}")
        return response.content or None

    async def add_event(self, row: dict[str, Any]) -> None:
        await self._send("POST", "/rest/v1/events", params={"on_conflict": "id"}, json=row,
                         headers={"Prefer": "return=minimal,resolution=ignore-duplicates"})

    async def acknowledge(self, incident_id: str, by: str, at: str) -> bool:
        """The dashboard's acknowledgement. True if this update made it; False if no row came
        back, meaning someone acknowledged it first."""
        response = await self._send(
            "PATCH", "/rest/v1/incidents",
            params={"id": f"eq.{incident_id}", "status": "eq.escalated", "select": "id"},
            json={"status": "acknowledged", "acknowledged_by": by, "acknowledged_at": at},
            headers={"Prefer": "return=representation"})
        data = response.json()
        return isinstance(data, list) and len(data) > 0


class MemoryBackend:
    """For the made-up escalation and for tests: incidents and events in memory, with the
    backend's own rule on the acknowledgement (only an `escalated` row is changed)."""

    def __init__(self) -> None:
        self.incidents: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.person = "Eleni"
        self.updates: list[dict[str, Any]] = []
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise BackendError("memory backend set to fail")

    async def escalated(self, device_id: str) -> list[dict[str, Any]]:
        self._check()
        rows = [dict(r) for r in self.incidents.values()
                if r.get("device_id") == device_id and r.get("status") == "escalated"]
        return sorted(rows, key=lambda r: str(r.get("started_at")), reverse=True)[:5]

    async def incident(self, incident_id: str) -> dict[str, Any] | None:
        self._check()
        row = self.incidents.get(incident_id)
        return dict(row) if row else None

    async def escalated_at(self, incident_id: str) -> str | None:
        self._check()
        times = sorted(str(e["at"]) for e in self.events
                       if e.get("incident_id") == incident_id and e.get("kind") == "escalated")
        return times[0] if times else None

    async def timeline(self, incident_id: str) -> list[dict[str, Any]]:
        self._check()
        rows = [{"at": e["at"], "kind": e["kind"], "text": e["text"]} for e in self.events
                if e.get("incident_id") == incident_id]
        return sorted(rows, key=lambda r: str(r["at"]))

    async def person_label(self, device_id: str) -> str | None:
        self._check()
        return self.person

    async def snapshot(self, path: str) -> bytes | None:
        self._check()
        return self.files.get(path)

    async def add_event(self, row: dict[str, Any]) -> None:
        self._check()
        if not any(e.get("id") == row.get("id") for e in self.events):
            self.events.append(dict(row))

    async def acknowledge(self, incident_id: str, by: str, at: str) -> bool:
        self._check()
        patch = {"status": "acknowledged", "acknowledged_by": by, "acknowledged_at": at}
        self.updates.append({"incident_id": incident_id, "filter_status": "escalated",
                             "patch": dict(patch)})
        row = self.incidents.get(incident_id)
        if row is None or row.get("status") != "escalated":
            return False
        row.update(patch)
        return True


def new_id() -> str:
    return str(uuid.uuid4())
