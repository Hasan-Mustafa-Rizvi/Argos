"""Time. The brain reads both clocks through one object so tests can move time by hand."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta


def iso(stamp: datetime) -> str:
    """ISO 8601 in UTC with milliseconds, as the fixture writes it."""
    stamp = stamp.astimezone(UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{stamp.microsecond // 1000:03d}Z"


class Clock:
    """`now()` is monotonic seconds for timing. `iso()` is the wall time for records."""

    def now(self) -> float:
        return time.monotonic()

    def iso(self) -> str:
        return iso(datetime.now(UTC))

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


class FakeClock(Clock):
    """A clock that moves only when told to. Wall time is a fixed base plus `now()`."""

    def __init__(self, base: datetime | None = None, start: float = 0.0) -> None:
        self._t = start
        self._base = base or datetime(2026, 11, 15, 19, 0, 0, tzinfo=UTC)
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def iso(self) -> str:
        return iso(self._base + timedelta(seconds=self.now()))

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._t += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(max(0.0, seconds))
