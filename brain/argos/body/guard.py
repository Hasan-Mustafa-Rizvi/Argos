"""The wheel guard: a small separate process that owns the six motor pins.

    python -m argos.body.guard [--pins gpio|fake] [--record FILE]
    python -m argos.body.guard --pins-low

Why a separate process. On a Raspberry Pi 5 a pin keeps its last level when the program that
set it dies, and the speed control (PWM) runs inside that program. A brain that crashed in
the middle of a burst could leave a motor running. So the brain never touches a pin: it
starts this guard, sends it short commands and a steady heartbeat, and the guard stops the
motors by itself when:

- a burst's own time runs out (every drive command carries its length, at most MAX_BURST_S);
- the heartbeat stops for HEARTBEAT_TIMEOUT_S (a brain that hangs or is frozen);
- its input closes (a brain that exits or is killed outright: the pipe closes with it);
- it is told to stop or to quit, or it gets SIGTERM, SIGHUP or SIGINT.

It leaves all six pins driven low when it ends: outputs at 0, not released. (gpiozero, when
it closes a pin or when Python exits, turns the pin back into an input, which then floats on
the Pi's weak pull-down. So the guard sets every pin low and ends without running that.) It
caps the power at MAX_POWER whatever it is sent. It knows nothing about checks or people:
that is the brain's job (`wheels.py`).

The pins are the contract's (section 2), wired to one L298N:

    IN1, IN2   GPIO17, GPIO27   left side: direction     plain outputs
    IN3, IN4   GPIO22, GPIO23   right side: direction    plain outputs
    ENA        GPIO12           left side: power         PWM
    ENB        GPIO13           right side: power        PWM

Forward on a side is its first IN pin high and its second low; back is the reverse; stopped
is all low. A side's direction pins change only while its power pin is at 0. No ready-made
motor class is used, because those put the PWM on the direction pins.

`--pins gpio` uses gpiozero, which on a Pi 5 needs lgpio. They are imported here only, in
this process, and this process is started only when the wheels are switched on. `--pins
fake` moves nothing and can record every pin change to a file, for tests and laptops.

The wire format is one JSON object per line on standard input:

    {"op": "beat"}                                  the heartbeat, every HEARTBEAT_S
    {"op": "drive", "l": 0.2, "r": -0.2, "s": 0.25} left and right power; the sign is the
                                                    direction; s is the burst's length
    {"op": "stop"}
    {"op": "quit"}

On standard output: one line when ready, `{"ready": true, ...}` or `{"ready": false,
"error": "..."}`, then one line for each command it refused. What it does goes to standard
error, which is the brain's log.

This module imports nothing but the standard library at the top, so it starts fast and can
be imported by the brain for its constants without loading any pin library.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

# --------------------------------------------------------------------------- the constants

PINS = {"in1": 17, "in2": 27, "in3": 22, "in4": 23, "ena": 12, "enb": 13}
SIDES = {"left": ("in1", "in2", "ena"), "right": ("in3", "in4", "enb")}
DIRECTION_PINS = (PINS["in1"], PINS["in2"], PINS["in3"], PINS["in4"])
POWER_PINS = (PINS["ena"], PINS["enb"])

# A share of full power. With a 12 V pack on 6 V motors, 0.60 is about the motors' rated
# voltage on fresh cells. No setting and no command can go above it.
MAX_POWER = 0.60
# Where the wheel test starts, and the default working power.
LOWEST_POWER = 0.20
# The longest a single burst may run.
MAX_BURST_S = 0.5
# The brain beats every HEARTBEAT_S; the guard stops the motors after HEARTBEAT_TIMEOUT_S of
# silence.
HEARTBEAT_S = 0.1
HEARTBEAT_TIMEOUT_S = 0.35
PWM_HZ = 200
TICK_S = 0.01

BRAIN_DIR = Path(__file__).resolve().parents[2]


def describe_pins() -> str:
    return (f"GPIO{PINS['in1']} and GPIO{PINS['in2']} (left direction), GPIO{PINS['in3']} and "
            f"GPIO{PINS['in4']} (right direction) as plain outputs; GPIO{PINS['ena']} (left "
            f"power) and GPIO{PINS['enb']} (right power) as PWM at {PWM_HZ} Hz")


def _log(message: str) -> None:
    print(f"wheel guard: {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- the pins


class Pins(Protocol):
    def side(self, side: str, direction: int, power: float) -> None: ...

    def all_low(self) -> None: ...

    def close(self) -> None: ...


class FakePins:
    """Six pins that move nothing. Each change can be written to `record`, one JSON line, so a
    test in another process can see exactly what the pins did."""

    name = "fake"

    def __init__(self, record: Path | None = None,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.record = record
        self.now = now
        self.levels: dict[int, float] = {pin: 0 for pin in (*DIRECTION_PINS, *POWER_PINS)}
        self.changes = 0
        self._write({"event": "start"})

    def _write(self, extra: dict[str, Any] | None = None) -> None:
        if self.record is None:
            return
        entry: dict[str, Any] = {"t": self.now(),
                                 "pins": {str(pin): level for pin, level in self.levels.items()}}
        if extra:
            entry.update(extra)
        with self.record.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry) + "\n")

    def side(self, side: str, direction: int, power: float) -> None:
        ina, inb, en = (PINS[name] for name in SIDES[side])
        self.levels[en] = 0
        self.levels[ina] = 1 if direction > 0 else 0
        self.levels[inb] = 1 if direction < 0 else 0
        if direction != 0 and power > 0:
            self.levels[en] = round(min(power, MAX_POWER), 4)
        self.changes += 1
        self._write()

    def all_low(self) -> None:
        for pin in self.levels:
            self.levels[pin] = 0
        self.changes += 1
        self._write()

    def close(self) -> None:
        self.all_low()

    def stopped(self) -> bool:
        return all(level == 0 for level in self.levels.values())


class GpioPins:
    """The real pins, through gpiozero (lgpio on a Pi 5). Four plain outputs and two PWM
    outputs, all starting low."""

    name = "gpio"

    def __init__(self) -> None:
        # lgpio keeps small notification files in its working folder: keep them out of the
        # repo. It reads this when it starts, so it is set before the import.
        os.environ.setdefault("LG_WD", tempfile.gettempdir())
        from gpiozero import Device, DigitalOutputDevice, PWMOutputDevice

        chosen = _pi5_chip_factory()
        extra: dict[str, Any] = {"pin_factory": chosen} if chosen is not None else {}
        self._dir: dict[int, Any] = {}
        self._pwm: dict[int, Any] = {}
        try:
            for pin in POWER_PINS:  # power first, so nothing can be enabled while setting up
                self._pwm[pin] = PWMOutputDevice(pin, initial_value=0, frequency=PWM_HZ,
                                                 **extra)
            for pin in DIRECTION_PINS:
                self._dir[pin] = DigitalOutputDevice(pin, initial_value=False, **extra)
        except Exception:
            self.close()
            raise
        factory = chosen if chosen is not None else Device.pin_factory
        self.factory = type(factory).__name__ if factory is not None else "unknown"

    def side(self, side: str, direction: int, power: float) -> None:
        ina, inb, en = (PINS[name] for name in SIDES[side])
        self._pwm[en].value = 0
        self._dir[ina].value = direction > 0
        self._dir[inb].value = direction < 0
        if direction != 0 and power > 0:
            self._pwm[en].value = min(power, MAX_POWER)

    def all_low(self) -> None:
        for device in self._pwm.values():
            device.value = 0
        for device in self._dir.values():
            device.value = False

    def close(self) -> None:
        """Only for a setup that failed half way. At the end of a run the guard calls
        `all_low()` and leaves the pins as driven-low outputs instead (see the module)."""
        try:
            self.all_low()
        finally:
            for device in [*self._pwm.values(), *self._dir.values()]:
                try:
                    device.close()
                except Exception:
                    pass


def _pi5_chip_factory() -> Any:
    """gpiozero 2.0.1 opens /dev/gpiochip4 on any Pi 5, but newer Pi 5 kernels put the header
    on /dev/gpiochip0. When chip 4 is missing and chip 0 is there, open chip 0 explicitly.
    None means: let gpiozero choose."""
    if Path("/dev/gpiochip4").exists() or not Path("/dev/gpiochip0").exists():
        return None
    try:
        from gpiozero.pins.lgpio import LGPIOFactory

        return LGPIOFactory(chip=0)
    except Exception:
        return None


# --------------------------------------------------------------------------- the logic


def _power(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    value = max(-MAX_POWER, min(MAX_POWER, value))
    return 0.0 if abs(value) < 0.01 else value


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        return None
    return min(value, MAX_BURST_S)


class GuardCore:
    """What the guard does with each command, and with time passing. No I/O beyond the pins,
    and time is read through `now`, so tests can drive it by hand."""

    def __init__(self, pins: Pins, now: Callable[[], float] = time.monotonic) -> None:
        self.pins = pins
        self.now = now
        self.last_beat = -math.inf
        self.burst_until = 0.0
        self.running = False
        self.last_stop = ""

    def handle(self, message: Mapping[str, Any]) -> str | None:
        """Apply one command. Returns why it was refused, or None."""
        op = message.get("op")
        if op == "beat":
            self.last_beat = self.now()
            return None
        if op == "stop":
            self.halt("told to stop")
            return None
        if op == "drive":
            now = self.now()
            if now - self.last_beat > HEARTBEAT_TIMEOUT_S:
                self.halt("a drive came without a heartbeat")
                return "refused: no heartbeat"
            left, right = _power(message.get("l")), _power(message.get("r"))
            seconds = _seconds(message.get("s"))
            if left is None or right is None or seconds is None:
                self.halt("a drive command it could not read")
                return "refused: a drive command it could not read"
            self.pins.side("left", (left > 0) - (left < 0), abs(left))
            self.pins.side("right", (right > 0) - (right < 0), abs(right))
            self.running = left != 0 or right != 0
            self.burst_until = now + seconds
            return None
        self.halt("a command it does not know")
        return "refused: a command it does not know"

    def tick(self) -> None:
        if not self.running:
            return
        now = self.now()
        if now >= self.burst_until:
            self.halt("the burst ended")
        elif now - self.last_beat > HEARTBEAT_TIMEOUT_S:
            self.halt("the heartbeat stopped")

    def halt(self, reason: str) -> None:
        was_running = self.running
        self.pins.all_low()
        self.running = False
        self.last_stop = reason
        if was_running and reason != "the burst ended":
            _log(f"motors stopped: {reason}")


EOF = object()


def _read_lines(stream: Any, lines: queue.Queue[Any]) -> None:
    """Standard input, one command a line, onto the queue. EOF when it closes."""
    try:
        while True:
            raw = stream.readline()
            if not raw:
                break
            try:
                message = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, bytes)
                                     else raw)
            except ValueError:
                message = {"op": "unreadable"}
            lines.put(message if isinstance(message, dict) else {"op": "unreadable"})
    except Exception:
        pass
    lines.put(EOF)


def serve(core: GuardCore, lines: queue.Queue[Any], stopping: threading.Event,
          reply: Callable[[dict[str, Any]], None],
          parent_alive: Callable[[], bool] = lambda: True) -> str:
    """The guard's loop. Returns why it ended."""
    while True:
        if stopping.is_set():
            return "it was told to stop by a signal"
        try:
            item = lines.get(timeout=TICK_S)
        except queue.Empty:
            item = None
        if item is EOF:
            return "the brain went away (its pipe closed)"
        if item is not None:
            if item.get("op") == "quit":
                return "the brain told it to quit"
            refusal = core.handle(item)
            if refusal:
                reply({"refused": refusal})
        core.tick()
        if not parent_alive():
            return "the brain went away"


def _say(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _parent_watch() -> Callable[[], bool]:
    if os.name != "posix":
        return lambda: True  # the pipe closing is the signal on Windows
    parent = os.getppid()
    return lambda: os.getppid() == parent


def _load_brain_env(env: dict[str, str]) -> None:
    """The brain's own settings file, for --pins-low run by a service. Real environment
    variables win."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return
    for name, value in dotenv_values(BRAIN_DIR / ".env").items():
        if value is not None:
            env.setdefault(name, value)


def pins_low(environ: Mapping[str, str]) -> int:
    """Drive the six pins low and exit. Used by the service when it stops, and by the brain
    if a guard died. Touches nothing at all unless the wheels are switched on."""
    env = dict(environ)
    _load_brain_env(env)
    if env.get("ARGOS_WHEELS", "").strip() != "1":
        _log("the wheels are off (ARGOS_WHEELS is not 1): no pin touched")
        return 0
    try:
        pins = GpioPins()  # every pin starts as an output at 0
        pins.all_low()
    except Exception as exc:
        _log(f"could not drive the pins low ({type(exc).__name__}: {exc})")
        return 1
    _log("all six wheel pins driven low")
    return 0  # not closed: the pins stay driven low (see the module)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m argos.body.guard",
                                     description="The wheel guard. Started by the brain.")
    parser.add_argument("--pins", choices=("gpio", "fake"), default="gpio")
    parser.add_argument("--record", type=Path, default=None,
                        help="with --pins fake: write every pin change to this file")
    parser.add_argument("--pins-low", action="store_true",
                        help="drive the six pins low and exit (only if ARGOS_WHEELS=1)")
    args = parser.parse_args(argv)
    if args.pins_low:
        return pins_low(os.environ)

    stopping = threading.Event()

    def on_signal(signum: int, frame: Any) -> None:
        stopping.set()

    for name in ("SIGTERM", "SIGHUP", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, on_signal)
            except (OSError, ValueError):
                pass

    try:
        pins: Pins = FakePins(args.record) if args.pins == "fake" else GpioPins()
    except Exception as exc:
        _say({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 2
    core = GuardCore(pins)
    lines: queue.Queue[Any] = queue.Queue()
    threading.Thread(target=_read_lines, args=(sys.stdin.buffer, lines), daemon=True,
                     name="guard-input").start()
    _say({"ready": True, "pins": args.pins, "factory": getattr(pins, "factory", args.pins),
          "pwm_hz": PWM_HZ, "max_power": MAX_POWER, "max_burst_s": MAX_BURST_S})
    reason = "it stopped for a reason it did not catch"
    try:
        reason = serve(core, lines, stopping, _say, _parent_watch())
    finally:
        try:
            pins.all_low()
        finally:
            if isinstance(pins, FakePins):
                pins._write({"event": "exit", "reason": reason})
            _log(f"ended, all pins driven low: {reason}")
    return 0


def run() -> None:
    """The process's entry. It ends with os._exit, after flushing, so that gpiozero's exit
    handler does not turn the driven-low pins back into floating inputs."""
    try:
        code = main()
    except SystemExit as exc:  # argparse: --help, or a bad argument
        code = exc.code if isinstance(exc.code, int) else 2
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    run()
