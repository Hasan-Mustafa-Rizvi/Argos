"""Time, through one object, so tests can set it and never sleep."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta


def iso(stamp: datetime) -> str:
    """ISO 8601 in UTC with milliseconds, as the brain writes it."""
    stamp = stamp.astimezone(UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{stamp.microsecond // 1000:03d}Z"


def parse_iso(value: str | None) -> datetime | None:
    """A timestamp from a record, or None if it cannot be read."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


class Clock:
    """`now()` is monotonic seconds for timing. `wall()` is the time of day for records."""

    def now(self) -> float:
        return time.monotonic()

    def wall(self) -> datetime:
        return datetime.now(UTC)

    def iso(self) -> str:
        return iso(self.wall())

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


class FakeClock(Clock):
    """Moves only when told to, or when someone sleeps on it. Wall time is a fixed base plus
    `now()`."""

    def __init__(self, base: datetime | None = None, start: float = 0.0) -> None:
        self._t = start
        self._base = base or datetime(2026, 11, 15, 19, 0, 0, tzinfo=UTC)
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def wall(self) -> datetime:
        return self._base + timedelta(seconds=self.now())

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._t += max(0.0, seconds)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)
