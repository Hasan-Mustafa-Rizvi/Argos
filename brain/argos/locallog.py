"""The local record log: one JSON object per line, UTF-8, `\\n` line endings on every platform.

It holds exactly what the brain recorded (the same rows and changes it sends to the backend)
plus short notes about the backend coming and going. So a run with no network keeps
everything that matters to the demo. It never holds an image, a frame, audio, a key or a
contact value, and `summary` or `snapshot_path` only in a change made after the incident
escalated, exactly as in the backend.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

log = logging.getLogger("argos.locallog")


class LocalLog:
    def __init__(self, directory: Path | None) -> None:
        self.directory = directory
        self._lock = threading.Lock()
        self._handle: TextIO | None = None
        self._day = ""
        self._failed = False

    def _open(self, day: str) -> TextIO | None:
        if self.directory is None or self._failed:
            return None
        if self._handle is not None and day == self._day:
            return self._handle
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self._handle is not None:
                self._handle.close()
            path = self.directory / f"records-{day}.jsonl"
            self._handle = path.open("a", encoding="utf-8", newline="\n")
            self._day = day
        except OSError as exc:
            log.error("cannot open the local log in %s: %s; continuing without it",
                      self.directory, exc)
            self._failed = True
            self._handle = None
        return self._handle

    def write(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            handle = self._open(datetime.now(UTC).strftime("%Y-%m-%d"))
            if handle is None:
                return
            try:
                handle.write(line + "\n")
                handle.flush()
            except OSError as exc:
                log.error("local log write failed: %s", exc)

    def note(self, at: str, message: str) -> None:
        self.write({"at": at, "note": message})

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None


class MemoryLog(LocalLog):
    """Keeps lines in memory. Tests read `lines` to see exactly what would be on disk."""

    def __init__(self) -> None:
        super().__init__(None)
        self.lines: list[str] = []

    def write(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))

    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.lines]
