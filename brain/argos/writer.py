"""Ordered, non-blocking writes to the backend, and what happens when the network fails.

The brain never waits on the network: it hands each write to this queue and moves on. One
worker thread sends them in the order they were made.

When a write cannot reach the backend:

- Incident and event writes are kept, in order, and sent when the backend is back. Order
  matters: an incident's insert must land before its updates. Nothing is dropped, so after an
  outage the dashboard shows each incident as it really ended.
- Device writes are merged into one: only the latest `state`, `last_seen_at`, `caps` and `fw`
  matter, and the merged write goes last, so the device ends up showing its state as it is now.
- Readings are kept for the last hour at most (720 rows) and sent as one batch.
- The worker tries again every few seconds, not in a tight loop.

A write the backend refuses outright (a 4xx answer) is logged and dropped, so one bad row can
never block the rest.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from argos.store import Filters, Store, StoreRejected, StoreUnavailable

log = logging.getLogger("argos.writer")

MAX_READINGS = 720
MAX_PENDING = 10_000


@dataclass
class Write:
    table: str
    op: str  # "insert" or "update"
    rows: list[dict[str, Any]] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    patch: dict[str, Any] = field(default_factory=dict)
    merge_key: str | None = None
    on_done: Callable[[int], None] | None = None


class RecordWriter:
    def __init__(
        self,
        store: Store | None,
        threaded: bool = True,
        retry_s: float = 5.0,
        note: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.threaded = threaded
        self.retry_s = retry_s
        self._note = note or (lambda message: None)
        self._pending: deque[Write] = deque()
        self._cond = threading.Condition()
        self._closing = False
        self._online = True
        self._thread: threading.Thread | None = None
        if store is not None and threaded:
            self._thread = threading.Thread(target=self._run, name="argos-writer", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------ public

    @property
    def online(self) -> bool:
        return self._online

    @property
    def pending(self) -> int:
        with self._cond:
            return len(self._pending)

    def insert(self, table: str, row: dict[str, Any]) -> None:
        self._submit(Write(table, "insert", rows=[row]))

    def update(
        self,
        table: str,
        filters: Filters,
        patch: dict[str, Any],
        merge_key: str | None = None,
        on_done: Callable[[int], None] | None = None,
    ) -> None:
        self._submit(
            Write(table, "update", filters=dict(filters), patch=dict(patch), merge_key=merge_key,
                  on_done=on_done)
        )

    def flush(self, timeout_s: float = 5.0) -> bool:
        """Wait until every pending write is sent. False if some are still waiting."""
        if self.store is None:
            return True
        if not self.threaded:
            self._drain()
            return not self._pending
        with self._cond:
            self._cond.notify_all()
            return self._cond.wait_for(lambda: not self._pending, timeout=timeout_s)

    def close(self, timeout_s: float = 3.0) -> None:
        self.flush(timeout_s)
        with self._cond:
            self._closing = True
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._pending:
            log.warning("%d writes were not sent before stopping; the local log has them",
                        len(self._pending))

    # ------------------------------------------------------------------ queue

    def _submit(self, write: Write) -> None:
        if self.store is None:
            return
        with self._cond:
            if write.merge_key:
                for queued in list(self._pending):
                    if queued.merge_key == write.merge_key and queued is not self._in_flight():
                        self._pending.remove(queued)
                        write.patch = {**queued.patch, **write.patch}
                        break
            if write.table == "readings":
                self._limit_readings()
            if len(self._pending) >= MAX_PENDING:
                dropped = self._pending.popleft()
                log.error("write queue full; dropped the oldest %s %s", dropped.op, dropped.table)
            self._pending.append(write)
            self._cond.notify_all()
        if not self.threaded:
            self._drain()

    def _in_flight(self) -> Write | None:
        return self._pending[0] if self._pending and self._sending else None

    _sending = False

    def _limit_readings(self) -> None:
        if self._sending:  # a batch is in flight; trim on the next write instead
            return
        readings = [w for w in self._pending if w.table == "readings"]
        while len(readings) >= MAX_READINGS:
            oldest = readings.pop(0)
            if oldest is not self._in_flight():
                self._pending.remove(oldest)

    def _next_batch(self) -> Write | None:
        """The head of the queue. Consecutive readings are merged into one batch insert."""
        if not self._pending:
            return None
        head = self._pending[0]
        if head.table != "readings" or head.op != "insert":
            return head
        batch = Write("readings", "insert")
        for write in self._pending:
            if write.table != "readings" or write.op != "insert":
                break
            batch.rows.extend(write.rows)
        return batch

    def _send(self, write: Write) -> int:
        assert self.store is not None
        if write.op == "insert":
            self.store.insert(write.table, write.rows)
            return len(write.rows)
        return self.store.update(write.table, write.filters, write.patch)

    def _done(self, write: Write, matched: int) -> None:
        """Remove the sent write (or the readings merged into a batch) from the queue."""
        if write.table == "readings" and write.op == "insert" and len(write.rows) >= 1:
            count = len(write.rows)
            while count > 0 and self._pending and self._pending[0].table == "readings":
                count -= len(self._pending.popleft().rows)
        elif self._pending and self._pending[0] is write:
            self._pending.popleft()
        if write.on_done:
            try:
                write.on_done(matched)
            except Exception:  # a callback must never stop the writer
                log.exception("write callback failed")

    def _set_online(self, online: bool, reason: str = "") -> None:
        if online == self._online:
            return
        self._online = online
        if online:
            message = "backend reachable again; sending what was waiting"
        else:
            message = f"backend unreachable ({reason}); writes are kept and retried"
        log.warning(message)
        self._note(message)

    def _attempt(self) -> bool:
        """Send the head of the queue. True if it left the queue, False if it must wait."""
        with self._cond:
            write = self._next_batch()
            if write is None:
                return False
            self._sending = True
        try:
            matched = self._send(write)
        except StoreUnavailable as exc:
            with self._cond:
                self._sending = False
            self._set_online(False, str(exc))
            return False
        except StoreRejected as exc:
            log.error("backend refused a write to %s and it was dropped: %s", write.table, exc)
            self._note(f"backend refused a write to {write.table}: {exc}")
            matched = -1
        except Exception:
            log.exception("unexpected error writing to %s; the write was dropped", write.table)
            matched = -1
        with self._cond:
            self._sending = False
            self._done(write, matched)
            self._cond.notify_all()
        self._set_online(True)
        return True

    def _drain(self) -> None:
        while self._pending and self._attempt():
            pass

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending or self._closing)
                if self._closing and not self._pending:
                    return
            if not self._attempt():
                with self._cond:
                    if self._closing:
                        return
                    self._cond.wait(timeout=self.retry_s)
