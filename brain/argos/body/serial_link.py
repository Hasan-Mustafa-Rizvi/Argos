"""The optional sensor board on the serial link of contract section 2.

USB serial, 115200 baud, UTF-8, one JSON object per line, at most 256 bytes a line.
`SERIAL_PORT` is anything pyserial's `serial_for_url` opens: `COM5`, `/dev/ttyUSB0`, or
`socket://127.0.0.1:7777` for the pretend board (`tools/pretend_board.py`), since Windows has
no pseudo-terminals.

- `ping` is sent on connecting: `hello` is otherwise sent only at boot, and opening a port
  can reset the board.
- `state` is sent on every state change, and again after a reconnect.
- A `pat` event is an answer. `tipped` becomes a `device_tipped` event. Telemetry feeds
  `readings`.
- Three seconds without a line means the board is disconnected. The brain keeps running and
  the port is reopened every two seconds until the board answers again.
- Lines and fields this code does not know are ignored.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol

from argos.body.base import Connected, Disconnected, Emit, Pat, Telemetry, Tipped, Upright
from argos.clock import Clock

log = logging.getLogger("argos.board")

BAUD = 115200
MAX_LINE = 256
SILENCE_S = 3.0
REOPEN_S = 2.0
STATES = ("calm", "checking", "alert")


# --------------------------------------------------------------------------- the wire format


def parse_line(raw: bytes | str) -> dict[str, Any] | None:
    """One line from the board, or None if it is not a message this brain can use."""
    if isinstance(raw, bytes):
        if len(raw.rstrip(b"\r\n")) > MAX_LINE:
            return None
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    line = raw.strip()
    if not line or len(line.encode("utf-8")) > MAX_LINE:
        return None
    try:
        message = json.loads(line)
    except ValueError:
        return None
    if not isinstance(message, dict) or not isinstance(message.get("t"), str):
        return None
    return message


def encode(command: dict[str, Any]) -> bytes:
    data = json.dumps(command, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_LINE:
        raise ValueError("command longer than 256 bytes")
    return data + b"\n"


def cmd_state(state: str) -> dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    return {"cmd": "state", "state": state}


def cmd_head(deg: float) -> dict[str, Any]:
    return {"cmd": "head", "deg": int(round(min(60.0, max(-60.0, deg))))}


def cmd_tail(on: bool) -> dict[str, Any]:
    return {"cmd": "tail", "on": bool(on)}


def cmd_buzz(ms: int) -> dict[str, Any]:
    return {"cmd": "buzz", "ms": int(min(2000, max(1, ms)))}


def cmd_ping() -> dict[str, Any]:
    return {"cmd": "ping"}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# --------------------------------------------------------------------------- the board


class Port(Protocol):
    in_waiting: int

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes) -> int | None: ...

    def close(self) -> None: ...


def open_port(url: str) -> Port:
    import serial  # pyserial

    return serial.serial_for_url(url, baudrate=BAUD, timeout=0.05, write_timeout=0.5)


class SensorBoard:
    name = "board"

    def __init__(
        self,
        url: str,
        clock: Clock,
        opener: Callable[[str], Port] = open_port,
        threaded: bool = True,
    ) -> None:
        self.url = url
        self.clock = clock
        self.opener = opener
        self.threaded = threaded
        self.connected = False
        self.board_caps: list[str] = []
        self.board_fw: str | None = None
        self._port: Port | None = None
        self._buffer = b""
        self._last_rx = 0.0
        self._next_open = 0.0
        self._state = "calm"
        self._warned_open = False
        self._emit: Emit = lambda event: None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ Body

    def start(self, emit: Emit) -> None:
        self._emit = emit
        if not self.threaded:
            self.poll(self.clock.now())
        else:  # opening a port can take seconds; the board's own thread does it
            self._thread = threading.Thread(target=self._run, name="argos-board", daemon=True)
            self._thread.start()

    def show_state(self, state: str, look_yaw_deg: float | None = None) -> None:
        with self._lock:
            self._state = state
            self._send(cmd_state(state))
            if look_yaw_deg is not None and "head" in self.board_caps and state == "checking":
                self._send(cmd_head(look_yaw_deg))

    def stood_down(self) -> None:
        self.show_state("calm")

    def beep(self, ms: int) -> bool:
        with self._lock:
            if not self.connected or "buzzer" not in self.board_caps:
                return False
            return self._send(cmd_buzz(ms))

    def caps(self) -> list[str]:
        return list(self.board_caps) if self.connected else []

    def fw(self) -> str | None:
        return self.board_fw if self.connected else None

    def moving_until(self) -> float:
        return 0.0

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._close()

    # ------------------------------------------------------------------ loop

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll(self.clock.now())
            except Exception:
                log.exception("sensor board loop error")
            self._stop.wait(0.02)

    def poll(self, now: float) -> None:
        """Open the port if needed, read what has arrived, and watch for silence."""
        with self._lock:
            if self._port is None:
                if now >= self._next_open:
                    self._open(now)
                return
            try:
                waiting = self._port.in_waiting
                chunk = self._port.read(waiting or 1)
            except Exception as exc:
                self._drop(now, f"read failed: {type(exc).__name__}")
                return
            if chunk:
                self._buffer += chunk
                self._take_lines(now)
            # A board just opened may be rebooting (opening the port can reset it): give it a
            # little longer to say its first line.
            limit = SILENCE_S if self.connected else SILENCE_S + 3.0
            if now - self._last_rx > limit:
                self._drop(now, f"no line for {SILENCE_S:g} s")

    def _take_lines(self, now: float) -> None:
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            self._last_rx = now
            message = parse_line(raw)
            if message is not None:
                self._handle(message)
        if len(self._buffer) > 4 * MAX_LINE:  # no newline in sight: garbage, drop it
            self._buffer = b""

    def _handle(self, message: dict[str, Any]) -> None:
        kind = message["t"]
        if not self.connected:
            self.connected = True
            log.info("sensor board connected on %s", self.url)
            self._send(cmd_state(self._state))
            self._emit(Connected(self.name))
        if kind == "hello":
            caps = message.get("caps")
            fw = message.get("fw")
            self.board_caps = [c for c in caps if isinstance(c, str)] if isinstance(caps,
                                                                                   list) else []
            self.board_fw = fw if isinstance(fw, str) else None
            self._emit(Connected(self.name))
        elif kind == "telemetry":
            touch = message.get("touch")
            self._emit(
                Telemetry(
                    self.name,
                    _number(message.get("temp_c")),
                    _number(message.get("tilt_deg")),
                    touch if isinstance(touch, bool) else None,
                )
            )
        elif kind == "event":
            event = message.get("kind")
            if event == "pat":
                self._emit(Pat(self.name))
            elif event == "tipped":
                self._emit(Tipped(self.name))
            elif event == "upright":
                self._emit(Upright(self.name))
        elif kind == "err":
            log.info("sensor board says: %s", str(message.get("msg", ""))[:120])

    def _send(self, command: dict[str, Any]) -> bool:
        if self._port is None:
            return False
        try:
            self._port.write(encode(command))
            return True
        except Exception as exc:
            self._drop(self.clock.now(), f"write failed: {type(exc).__name__}")
            return False

    def _open(self, now: float) -> None:
        self._next_open = now + REOPEN_S
        try:
            self._port = self.opener(self.url)
        except Exception as exc:
            if not self._warned_open:
                log.warning("sensor board: cannot open %s (%s); carrying on without it and "
                            "retrying", self.url, type(exc).__name__)
                self._warned_open = True
            return
        self._warned_open = False
        self._buffer = b""
        self._last_rx = now
        self._send(cmd_ping())

    def _close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
        self._port = None

    def _drop(self, now: float, reason: str) -> None:
        was_connected = self.connected
        self._close()
        self.connected = False
        self._next_open = now + REOPEN_S
        if was_connected:
            log.warning("sensor board disconnected (%s); carrying on without it", reason)
            self._emit(Disconnected(self.name))
