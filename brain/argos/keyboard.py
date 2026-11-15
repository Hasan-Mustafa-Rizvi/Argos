"""The hidden demo button: single keys in the terminal that started the brain.

Works the same in a Windows console, in a terminal on the Pi, and over SSH. It reads on its
own thread, so it never waits on the camera or audio threads, and they never wait on it.

- Windows: `msvcrt` reads one key at a time without Enter.
- Linux over SSH or on a local terminal: stdin is put in cbreak mode (keys arrive without
  Enter, Ctrl+C still works) and restored on exit.
- No terminal (a service started at boot, or input piped in): lines are read, and the first
  character of each line is the key. At end of input the keyboard simply stops.

The stop key (space, or x) stops the wheels. The brain hands it to the wheels directly, on
this thread, never through its queue, and it holds until the brain is started again. The
wheels arm only when a real terminal is attached (`attached()`), so the stop key is always
at hand when they can move.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable
from typing import TextIO

log = logging.getLogger("argos.keyboard")

KEYS = {
    "f": "start a check: fall",
    "h": "start a check: call for help",
    "s": "start a check: stillness",
    "m": "start a check: manual",
    "y": "answer \"I'm fine\"",
    "p": "pat",
    "a": "acknowledge the alert (recorded as Demo)",
    " ": "stop the wheels until restart",
    "x": "stop the wheels until restart",
    "q": "quit",
    "?": "show these keys",
}


def help_text() -> str:
    shown = {key: meaning for key, meaning in KEYS.items() if key != "x"}
    names = {" ": "space or x"}
    return "Keys:  " + "   ".join(f"{names.get(key, key)} {meaning}"
                                  for key, meaning in shown.items())


def attached(stream: TextIO | None = None) -> bool:
    """A person's keyboard, in a real terminal: not a service, not piped input."""
    stream = stream or sys.stdin
    try:
        return stream is not None and stream.isatty()
    except (AttributeError, ValueError, OSError):
        return False


class Keyboard:
    def __init__(self, on_key: Callable[[str], None], stream: TextIO | None = None) -> None:
        self.on_key = on_key
        self.stream = stream or sys.stdin
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._restore: Callable[[], None] | None = None
        self._esc = ""  # where we are in a terminal escape sequence ("" when not in one)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="argos-keyboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._restore:
            self._restore()
            self._restore = None

    def _deliver(self, char: str) -> None:
        key = char.lower()
        if key in KEYS:
            self.on_key(key)

    def _feed(self, data: str) -> None:
        """Characters from a terminal, with its escape sequences dropped whole.

        Arrow and function keys, and a terminal's own reports, arrive as ESC and a few
        characters. Taken one by one they were keys: on the Pi the brain quit on its own, and
        an up arrow (ESC [ A) would acknowledge, Home (ESC [ H) start a check, F1 (ESC O P)
        stand a check down. A sequence may be split across reads, so the state is kept."""
        for char in data:
            state = self._esc
            if state == "":
                if char == "\x1b":
                    self._esc = "esc"
                else:
                    self._deliver(char)
            elif state == "esc":
                self._esc = {"[": "csi", "O": "ss3", "P": "str", "]": "str", "X": "str",
                             "^": "str", "_": "str"}.get(char, "")
            elif state == "csi":
                if "\x40" <= char <= "\x7e":
                    self._esc = ""
            elif state == "ss3":
                self._esc = ""
            elif state == "str":
                if char == "\x07":
                    self._esc = ""
                elif char == "\x1b":
                    self._esc = "str-esc"
            else:  # "str-esc": ESC \ ends the string
                self._esc = "" if char == "\\" else "str"

    def _idle(self) -> None:
        """Nothing more arrived: a lone ESC was the Escape key, not a sequence."""
        if self._esc == "esc":
            self._esc = ""

    def _run(self) -> None:
        try:
            if os.name == "nt" and self.stream is sys.stdin and sys.stdin.isatty():
                self._run_windows()
            elif self.stream.isatty() and os.name != "nt":
                self._run_posix_tty()
            else:
                self._run_lines()
        except Exception as exc:
            log.warning("keyboard stopped: %s", exc)

    def _run_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):  # arrow and function keys come in two parts
                    msvcrt.getwch()
                    continue
                self._deliver(char)
            else:
                self._stop.wait(0.05)

    def _run_posix_tty(self) -> None:
        import select
        import termios
        import tty

        fd = self.stream.fileno()
        saved = termios.tcgetattr(fd)
        self._restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        tty.setcbreak(fd)
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    data = os.read(fd, 32).decode("utf-8", "ignore")
                    if not data:
                        return
                    self._feed(data)
                else:
                    self._idle()
        finally:
            if self._restore:
                self._restore()
                self._restore = None

    def _run_lines(self) -> None:
        for line in self.stream:
            if self._stop.is_set():
                return
            line = line.strip()
            if line:
                self._deliver(line[0])
        log.info("keyboard: end of input; keys are off")
