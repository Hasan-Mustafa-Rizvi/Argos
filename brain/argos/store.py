"""The backend, behind one small interface.

`SupabaseStore` talks to Supabase over plain HTTP: PostgREST for rows, Storage for the one
snapshot. `MemoryStore` keeps tables in memory; tests use it as the fake backend.

Every write is shaped so it can never undo a change the dashboard made:

- An insert is `INSERT ... ON CONFLICT DO NOTHING` (`resolution=ignore-duplicates`), so a
  retried insert can never overwrite a row that exists.
- An update names only the columns that changed, and carries a filter on the status the
  brain expects, so a late write cannot move an incident backwards.
"""

from __future__ import annotations

import copy
import logging
import threading
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import quote

import httpx

log = logging.getLogger("argos.store")

# Primary keys, for ignore-duplicates inserts.
PRIMARY_KEYS = {
    "devices": ("id",),
    "incidents": ("id",),
    "events": ("id",),
    "readings": ("device_id", "at"),
}

Filters = Mapping[str, str]
"""PostgREST filters, such as {"id": "eq.<uuid>", "status": "in.(escalated,acknowledged)"}."""


class StoreUnavailable(Exception):
    """The backend could not be reached, timed out, or failed on its side. Retry later."""


class StoreRejected(Exception):
    """The backend refused the request. Retrying the same request will not help."""


class Store(Protocol):
    def insert(self, table: str, rows: list[dict[str, Any]]) -> None: ...

    def update(self, table: str, filters: Filters, patch: dict[str, Any]) -> int: ...

    def select(
        self, table: str, filters: Filters, columns: str, order: str | None = None
    ) -> list[dict[str, Any]]: ...

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...


def auth_headers(key: str) -> dict[str, str]:
    """A new secret key (sb_secret_...) goes on `apikey` only. A legacy service-role JWT also
    goes on `Authorization`, which Storage reads."""
    headers = {"apikey": key}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class SupabaseStore:
    def __init__(
        self,
        url: str,
        key: str,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=url,
            headers={**auth_headers(key), "User-Agent": "argos-brain"},
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            # The message names the error type and the URL, never a header or a key.
            raise StoreUnavailable(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code >= 500 or response.status_code in (408, 429):
            raise StoreUnavailable(f"{method} {path}: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise StoreRejected(f"{method} {path}: HTTP {response.status_code} {_brief(response)}")
        return response

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        conflict = ",".join(PRIMARY_KEYS.get(table, ("id",)))
        self._send(
            "POST",
            f"/rest/v1/{table}",
            params={"on_conflict": conflict},
            json=rows if len(rows) != 1 else rows[0],
            headers={"Prefer": "return=minimal,resolution=ignore-duplicates"},
        )

    def update(self, table: str, filters: Filters, patch: dict[str, Any]) -> int:
        response = self._send(
            "PATCH",
            f"/rest/v1/{table}",
            params=dict(filters),
            json=patch,
            headers={"Prefer": "return=minimal,count=exact"},
        )
        return _matched(response)

    def select(
        self, table: str, filters: Filters, columns: str, order: str | None = None
    ) -> list[dict[str, Any]]:
        params = {**filters, "select": columns}
        if order:
            params["order"] = order
        response = self._send("GET", f"/rest/v1/{table}", params=params)
        data = response.json()
        return data if isinstance(data, list) else []

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        self._send(
            "POST",
            f"/storage/v1/object/{quote(bucket)}/{quote(path)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )


def _matched(response: httpx.Response) -> int:
    """Rows matched by a PATCH, from `Content-Range: */1` or `0-0/1`. -1 if not reported."""
    content_range = response.headers.get("content-range", "")
    total = content_range.rsplit("/", 1)[-1]
    return int(total) if total.isdigit() else -1


def _brief(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or "")[:200]
    return ""


# --------------------------------------------------------------------------- memory


def _matches(row: Mapping[str, Any], filters: Filters) -> bool:
    for column, rule in filters.items():
        op, _, value = rule.partition(".")
        current = row.get(column)
        current_text = "null" if current is None else str(current)
        if op == "eq" and current_text != value:
            return False
        if op == "in" and current_text not in value.strip("()").split(","):
            return False
        if op == "is" and value == "null" and current is not None:
            return False
    return True


class MemoryStore:
    """Tables in memory, with the same rules as the real backend. Used as the fake in tests.

    `ops` lists every write in order. `fail` makes every call raise `StoreUnavailable`.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {name: [] for name in PRIMARY_KEYS}
        self.files: dict[str, bytes] = {}
        self.ops: list[dict[str, Any]] = []
        self.fail = False
        self.lock = threading.Lock()

    def _check(self) -> None:
        if self.fail:
            raise StoreUnavailable("memory store set to fail")

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        with self.lock:
            self._check()
            keys = PRIMARY_KEYS.get(table, ("id",))
            existing = self.tables.setdefault(table, [])
            for row in rows:
                key = tuple(row.get(k) for k in keys)
                if any(tuple(other.get(k) for k in keys) == key for other in existing):
                    continue
                if table == "incidents":
                    _check_privacy(row)
                existing.append(copy.deepcopy(row))
                self.ops.append({"table": table, "op": "insert", "row": copy.deepcopy(row)})

    def update(self, table: str, filters: Filters, patch: dict[str, Any]) -> int:
        with self.lock:
            self._check()
            matched = 0
            for row in self.tables.setdefault(table, []):
                if _matches(row, filters):
                    candidate = {**row, **patch}
                    if table == "incidents":
                        _check_privacy(candidate)
                    row.update(copy.deepcopy(patch))
                    matched += 1
            self.ops.append(
                {
                    "table": table,
                    "op": "update",
                    "filters": dict(filters),
                    "patch": copy.deepcopy(patch),
                    "matched": matched,
                }
            )
            return matched

    def select(
        self, table: str, filters: Filters, columns: str, order: str | None = None
    ) -> list[dict[str, Any]]:
        with self.lock:
            self._check()
            rows = [row for row in self.tables.get(table, []) if _matches(row, filters)]
            if order:
                column, _, direction = order.partition(".")
                rows.sort(key=lambda r: str(r.get(column)), reverse=direction == "desc")
            names = [c.strip() for c in columns.split(",")]
            return [{name: copy.deepcopy(row.get(name)) for name in names} for row in rows]

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        with self.lock:
            self._check()
            self.files[f"{bucket}/{path}"] = bytes(data)
            self.ops.append({"table": f"storage:{bucket}", "op": "upload", "path": path})

    def row(self, table: str, row_id: str) -> dict[str, Any] | None:
        with self.lock:
            for row in self.tables.get(table, []):
                if row.get("id") == row_id:
                    return copy.deepcopy(row)
        return None


def _check_privacy(row: Mapping[str, Any]) -> None:
    """The backend's own check: nothing about what Argos saw unless the check failed."""
    if (row.get("summary") is not None or row.get("snapshot_path") is not None) and row.get(
        "status"
    ) not in ("escalated", "acknowledged"):
        raise StoreRejected("nothing_stored_unless_escalated")
