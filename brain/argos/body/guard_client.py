"""The brain's side of the wheel guard: it starts the guard process and talks to it.

`GuardMotors` is the wheels' real motors (`wheels.Motors`). It starts
`python -m argos.body.guard` as a child process, waits for it to say it holds the pins, and
from then on sends a heartbeat every HEARTBEAT_S from its own thread. Each drive command
carries its own length, so even a brain that hangs mid-burst cannot keep a motor on past the
burst.

The child gets its own process group, so Ctrl+C or a dropped SSH session reaches the brain,
which stops the guard in order. If the brain is killed outright the guard sees its input
close and stops by itself. If the guard dies while the brain runs, the wheels are off for
the rest of the run, and the pins are driven low once by a fresh `--pins-low` process.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import IO, Any

from argos.body.guard import BRAIN_DIR, HEARTBEAT_S

log = logging.getLogger("argos.guard")

READY_TIMEOUT_S = 8.0


def _child_options() -> dict[str, Any]:
    if os.name == "posix":
        return {"start_new_session": True}
    return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("LG_WD", tempfile.gettempdir())  # lgpio's small files, out of the repo
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def drive_pins_low() -> None:
    """Start a short process that drives the six pins low, and wait for it. It touches
    nothing unless ARGOS_WHEELS=1."""
    try:
        subprocess.run([sys.executable, "-m", "argos.body.guard", "--pins-low"], cwd=BRAIN_DIR,
                       env=_child_env(), timeout=15, check=False)
    except Exception as exc:
        log.error("could not drive the wheel pins low (%s): switch the motor battery off", exc)


class GuardMotors:
    """The motors, through the guard process."""

    name = "guard"

    def __init__(
        self,
        pins: str = "gpio",
        record: Path | None = None,
        launcher: list[str] | None = None,
        ready_timeout_s: float = READY_TIMEOUT_S,
        recover: bool | None = None,
    ) -> None:
        self.pins = pins
        self.record = record
        self.launcher = launcher or [sys.executable, "-m", "argos.body.guard"]
        self.ready_timeout_s = ready_timeout_s
        # Drive the pins low with a fresh process if the guard dies: only for real pins.
        self.recover = (pins == "gpio") if recover is None else recover
        self.info: dict[str, Any] = {}
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._lines: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._ready = False
        self._closing = False
        self._dead = False
        self._refusals: set[str] = set()

    # ------------------------------------------------------------------ Motors

    def start(self) -> str | None:
        command = [*self.launcher, "--pins", self.pins]
        if self.record is not None:
            command += ["--record", str(self.record)]
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    cwd=BRAIN_DIR, env=_child_env(), **_child_options())
        except OSError as exc:
            return f"the guard did not start ({type(exc).__name__})"
        with self._lock:
            self._proc = proc
        assert proc.stdout is not None
        threading.Thread(target=self._read, args=(proc.stdout,), name="argos-guard-read",
                         daemon=True).start()
        try:
            first = self._lines.get(timeout=self.ready_timeout_s)
        except queue.Empty:
            self._kill()
            return f"the guard did not say it was ready within {self.ready_timeout_s:g} s"
        if first is None or not first.get("ready"):
            error = (first or {}).get("error") or "it stopped at once"
            self._kill()
            return f"the guard could not take the pins: {error}"
        self.info = first
        with self._lock:
            closing = self._closing
            if not closing:
                self._ready = True
        if closing:  # the brain stopped while the guard was starting: end it in order
            self._write(proc, {"op": "quit"})
            self._close_process(proc)
            return "the brain is stopping"
        threading.Thread(target=self._beat, name="argos-guard-beat", daemon=True).start()
        return None

    def drive(self, left: float, right: float, seconds: float) -> bool:
        return self._send({"op": "beat"}) and self._send(
            {"op": "drive", "l": round(left, 4), "r": round(right, 4), "s": round(seconds, 4)})

    def stop(self) -> None:
        self._send({"op": "stop"})

    def alive(self) -> bool:
        with self._lock:
            proc = self._proc
            return self._ready and not self._dead and proc is not None and proc.poll() is None

    def close(self) -> None:
        with self._lock:
            self._closing = True
            proc = self._proc
            ready = self._ready
            self._ready = False
        if proc is None:
            return
        if ready:
            self._write(proc, {"op": "stop"})
            self._write(proc, {"op": "quit"})
        self._close_process(proc)

    def _close_process(self, proc: subprocess.Popen[bytes]) -> None:
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            log.warning("the wheel guard did not stop when asked; ending it")
            self._kill()
            if self.recover:
                drive_pins_low()

    # ------------------------------------------------------------------ inside

    def _write(self, proc: subprocess.Popen[bytes], message: dict[str, Any]) -> bool:
        if proc.stdin is None:
            return False
        try:
            proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def _send(self, message: dict[str, Any]) -> bool:
        with self._lock:
            proc = self._proc
            if proc is None or not self._ready or self._dead:
                return False
            if self._write(proc, message):
                return True
        self._died("its input broke")
        return False

    def _beat(self) -> None:
        stop = threading.Event()
        while not stop.wait(HEARTBEAT_S):
            with self._lock:
                if self._closing or self._dead or not self._ready:
                    return
            if not self._send({"op": "beat"}):
                return

    def _read(self, stream: IO[bytes]) -> None:
        for raw in iter(stream.readline, b""):
            try:
                message = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if "ready" in message:
                self._lines.put(message)
            elif "refused" in message:
                reason = str(message["refused"])
                if reason not in self._refusals:
                    self._refusals.add(reason)
                    log.warning("the wheel guard %s", reason)
        self._lines.put(None)
        self._died("it ended")

    def _died(self, how: str) -> None:
        with self._lock:
            if self._dead:
                return
            self._dead = True
            expected = self._closing
            was_ready = self._ready
            self._ready = False
        if expected or not was_ready:
            return
        log.error("the wheel guard stopped unexpectedly (%s): the wheels are off for the rest "
                  "of this run", how)
        if self.recover:
            drive_pins_low()

    def _kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
