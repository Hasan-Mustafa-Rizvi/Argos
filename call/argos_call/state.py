"""The two files this program keeps, and nothing else:

- `seconds.json`: FaceTime seconds used, added after every call, across runs. A real call is
  refused once 30 minutes are used, unless it is started as the judged demo.
- `handled.json`: incidents already texted or called. Written to disk before a request goes
  out, so a restart, or the same record arriving again, can never text or call twice.

Both hold ids, counts, times and outcomes. Never a number, a key, a token, a picture, a sound
or a word that was said.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("argos_call.state")


def _read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        # A damaged file must not be taken as "nothing handled": refuse to guess.
        raise StateError(f"{path.name} cannot be read ({type(exc).__name__}); fix or remove "
                         "it by hand before running again") from None
    return data if isinstance(data, dict) else default


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)


class StateError(Exception):
    pass


class Seconds:
    """FaceTime seconds used, kept across runs."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / "seconds.json"
        self._lock = threading.Lock()

    def used(self) -> float:
        with self._lock:
            return float(_read(self.path, {}).get("seconds_used", 0.0))

    def add(self, seconds: float, at: str, kind: str, call_id: str | None) -> float:
        with self._lock:
            data = _read(self.path, {"seconds_used": 0.0, "calls": []})
            total = float(data.get("seconds_used", 0.0)) + max(0.0, round(seconds, 1))
            calls = list(data.get("calls") or [])
            calls.append({"at": at, "seconds": round(seconds, 1), "kind": kind,
                          "call_id": call_id or ""})
            _write(self.path, {"seconds_used": round(total, 1), "calls": calls})
            return total

    def refuse(self, budget_s: float, demo: bool) -> str | None:
        """Why a real call must not go out now, or None."""
        used = self.used()
        if used >= budget_s and not demo:
            return (f"{used / 60:.1f} of the trial's minutes are used and the limit for tests "
                    f"is {budget_s / 60:.0f}; start with --demo for the judged demo")
        return None


class Handled:
    """Incidents already handled. One text and one call per incident, ever."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / "handled.json"
        self._lock = threading.Lock()

    def get(self, incident_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = _read(self.path, {}).get(incident_id)
            return dict(entry) if isinstance(entry, dict) else None

    def mark(self, incident_id: str, **fields: Any) -> dict[str, Any]:
        """Add or update an incident's entry, on disk, before anything goes out."""
        with self._lock:
            data = _read(self.path, {})
            entry = dict(data.get(incident_id) or {})
            entry.update(fields)
            data[incident_id] = entry
            _write(self.path, data)
            return entry

    def claim(self, incident_id: str, step: str, at: str) -> bool:
        """True exactly once per incident and step ("text" or "call"): the step is written as
        started before the caller sends anything. False if it was ever started before."""
        with self._lock:
            data = _read(self.path, {})
            entry = dict(data.get(incident_id) or {})
            if step in entry:
                return False
            entry[step] = {"started_at": at, "outcome": "started"}
            data[incident_id] = entry
            _write(self.path, data)
            return True

    def finish(self, incident_id: str, step: str, outcome: str, **extra: Any) -> None:
        with self._lock:
            data = _read(self.path, {})
            entry = dict(data.get(incident_id) or {})
            record = dict(entry.get(step) or {})
            record.update(outcome=outcome, **extra)
            entry[step] = record
            data[incident_id] = entry
            _write(self.path, data)
