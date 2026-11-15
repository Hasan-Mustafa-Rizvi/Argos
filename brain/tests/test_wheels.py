"""The wheels: rule 1 (they cannot hurt anyone) and rule 2 (the brain runs with them missing
or broken). No GPIO is touched: the guard runs as a real process with fake pins, and the pin
library is replaced by a fake that would show it was loaded."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

from argos.__main__ import build_wheels
from argos.body import guard
from argos.body.base import BodyHub
from argos.body.guard import (
    HEARTBEAT_TIMEOUT_S,
    MAX_BURST_S,
    MAX_POWER,
    PINS,
    FakePins,
    GuardCore,
)
from argos.body.guard_client import GuardMotors
from argos.body.wheels import (
    FRESH_S,
    MIN_APPROACH_GAP_S,
    MOTOR_ON_CAP_S,
    FakeMotors,
    Wheels,
    worst_case_m,
)
from argos.brain import AckIn, TriggerIn
from argos.clock import FakeClock
from argos.config import BRAIN_DIR, Settings
from argos.machine import State
from argos.senses.vision import Look, PersonPose
from tests.conftest import make_rig
from tests.test_vision import STANDING

PERSON = PersonPose({name: (x, y, 0.9) for name, (x, y) in STANDING.items()}, 640, 480)


def wheels_on(clock: FakeClock, power: float = 0.2, turn: float = 0.2,
              **kwargs: Any) -> tuple[Wheels, FakeMotors, dict[str, Any]]:
    motors = FakeMotors(clock)
    wheels = Wheels(motors, clock, power, turn, threaded=False, **kwargs)
    world: dict[str, Any] = {"check": "check-1", "look_t": None}
    wheels.open_check = lambda: world["check"]
    wheels.look = lambda: (Look(world["look_t"], PERSON) if world["look_t"] is not None
                           else None)
    wheels.start(lambda event: None)
    return wheels, motors, world


def fresh(clock: FakeClock, world: dict[str, Any]) -> None:
    clock.advance(0.05)
    world["look_t"] = clock.now()
    clock.advance(0.05)


# --------------------------------------------------------------------------- rule 1: off


FAKE_PIN_LIBRARY = {
    "gpiozero/__init__.py": "import pathlib\n"
                            "pathlib.Path(__file__).parent.parent.joinpath('LOADED').write_text"
                            "('gpiozero')\nraise ImportError('a fake pin library was loaded')\n",
    "lgpio.py": "import pathlib\n"
                "pathlib.Path(__file__).parent.joinpath('LOADED').write_text('lgpio')\n"
                "raise ImportError('a fake pin library was loaded')\n",
}


def fake_pin_library(root: Path) -> Path:
    for name, source in FAKE_PIN_LIBRARY.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root / "LOADED"


def test_with_the_wheels_off_no_pin_is_touched_and_no_pin_library_loads(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = fake_pin_library(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("gpiozero", "lgpio"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    started: list[Any] = []
    real_popen = subprocess.Popen

    def no_guard(*args: Any, **kwargs: Any) -> Any:
        if "argos.body.guard" in " ".join(map(str, args[0])):
            started.append(args)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", no_guard)
    clock = FakeClock()
    for value in (None, "0", "yes", "true", "on", "2"):
        env = {} if value is None else {"ARGOS_WHEELS": value}
        settings = Settings.from_env(env)
        assert settings.wheels == "off"
        assert build_wheels(settings, clock, keyboard=True, scripted=False,
                            platform="linux") is None
    rig = make_rig()  # a full check with no wheels
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9))
    rig.step()
    rig.run_for(10.2)
    rig.brain.post(AckIn("Demo"))
    rig.run_for(1.0)
    rig.brain.stop()
    assert rig.brain.state is State.CALM
    assert not marker.exists()
    assert "gpiozero" not in sys.modules and "lgpio" not in sys.modules
    assert started == []


def test_pins_low_with_the_wheels_off_loads_no_pin_library(tmp_path: Path) -> None:
    marker = fake_pin_library(tmp_path / "fake")
    env = {k: v for k, v in os.environ.items() if k != "ARGOS_WHEELS"}
    env["PYTHONPATH"] = str(tmp_path / "fake")
    done = subprocess.run([sys.executable, "-m", "argos.body.guard", "--pins-low"], cwd=BRAIN_DIR,
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "no pin touched" in done.stderr
    assert not marker.exists()


def test_wheels_do_not_arm_without_a_keyboard_or_in_a_scripted_run_or_on_windows() -> None:
    clock = FakeClock()
    settings = Settings.from_env({"ARGOS_WHEELS": "1"})
    assert build_wheels(settings, clock, keyboard=False, scripted=False, platform="linux") is None
    assert build_wheels(settings, clock, keyboard=True, scripted=True, platform="linux") is None
    assert build_wheels(settings, clock, keyboard=True, scripted=False, platform="win32") is None
    built = build_wheels(settings, clock, keyboard=True, scripted=False, platform="linux")
    assert built is not None and isinstance(built.motors, GuardMotors)  # not started yet
    pretend = build_wheels(Settings.from_env({"ARGOS_WHEELS": "fake"}), clock, keyboard=True,
                           scripted=False, platform="win32")
    assert pretend is not None and pretend.pretend


# --------------------------------------------------------------------------- rule 1: the layer


def test_no_burst_in_calm_or_alert_or_outside_an_approach() -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    fresh(clock, world)
    assert wheels.forward(0.3) == "no approach is open"
    world["check"] = None  # calm, or alert
    assert wheels.begin("check-1") == "no check is open"
    world["check"] = "check-1"
    assert wheels.begin("check-1") is None
    world["check"] = None
    assert wheels.forward(0.3) == "no check is open"
    world["check"] = "check-2"  # a later check: the old approach does not carry over
    assert wheels.forward(0.3) == "the approach was for another check"
    assert motors.drives() == []


def test_a_change_of_state_stops_the_base_at_once() -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    assert wheels.begin("check-1") is None
    fresh(clock, world)
    assert wheels.forward(0.3) is None
    clock.advance(0.1)
    wheels.show_state("alert")
    assert motors.commands[-1][:2] == ("stop", clock.now())
    assert wheels.moving_until() == clock.now()
    fresh(clock, world)
    assert wheels.forward(0.3) == "no approach is open"


@pytest.mark.parametrize("asked", [0.21, 0.6, 1.0, 5.0, 1e9, math.inf, math.nan, -3.0])
def test_power_never_exceeds_the_cap_whatever_is_asked(asked: float) -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock, power=asked, turn=asked)
    assert wheels.begin("check-1") is None
    for call in (lambda: wheels.forward(9.0), lambda: wheels.turn(+1, 9.0),
                 lambda: wheels.burst(asked, -asked, 9.0)):
        fresh(clock, world)
        call()
        clock.advance(1.0)
    for _, _, left, right, seconds in motors.drives():
        assert abs(left) <= MAX_POWER and abs(right) <= MAX_POWER
        assert seconds <= MAX_BURST_S


def test_the_settings_cannot_ask_for_more_than_the_cap() -> None:
    settings = Settings.from_env({"ARGOS_WHEELS_POWER": "0.95", "ARGOS_WHEELS_TURN_POWER": "3"})
    assert settings.wheels_power == MAX_POWER and settings.wheels_turn_power == MAX_POWER
    assert MAX_POWER <= 0.60


def test_the_motor_time_cap_holds_against_a_caller_that_misbehaves() -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock, power=0.6)
    assert wheels.begin("check-1") is None
    for _ in range(200):  # a caller that bursts as fast as the rules let it, for ever
        fresh(clock, world)
        wheels.forward(MAX_BURST_S)
        clock.advance(MAX_BURST_S)
    total = sum(seconds for *_, seconds in motors.drives())
    assert total <= MOTOR_ON_CAP_S + 1e-9
    # Nor can it open more approaches to get more motor time: not for a check that is not
    # the open one, and not twice for the same check, however long it waits.
    clock.advance(MIN_APPROACH_GAP_S + 1)
    for n in range(20):
        assert wheels.begin(f"made-up-{n}") == "that check is not the one open"
    assert wheels.begin("check-1") == "this check has had its approach"


def test_two_approaches_are_never_closer_than_the_floor() -> None:
    clock = FakeClock()
    wheels, _, world = wheels_on(clock)
    assert wheels.begin("check-1") is None
    wheels.end("done")
    world["check"] = "check-2"
    clock.advance(MIN_APPROACH_GAP_S - 1)
    assert wheels.begin("check-2") == "too soon after the last approach"
    clock.advance(1.0)
    assert wheels.begin("check-2") is None


def test_worst_case_distance_is_reported() -> None:
    assert worst_case_m() == pytest.approx(MOTOR_ON_CAP_S * MAX_POWER * 2.0)
    assert worst_case_m() < 1.5


def test_a_burst_needs_a_look_from_after_the_last_movement_and_younger_than_half_a_second(
) -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    head = {"until": 0.0}
    wheels.moved_until = lambda: max(wheels.moving_until(), head["until"])
    assert wheels.begin("check-1") is None
    assert wheels.forward(0.3) == "nobody is in view"
    fresh(clock, world)
    assert wheels.forward(0.3) is None
    clock.advance(0.4)
    assert wheels.forward(0.3) == "no fresh look since the body last moved"
    fresh(clock, world)
    head["until"] = clock.now() + 1.0  # the head turns after that look
    assert wheels.forward(0.3) == "no fresh look since the body last moved"
    clock.advance(1.1)
    fresh(clock, world)
    clock.advance(FRESH_S)
    assert wheels.forward(0.3) == "the newest look is too old"
    assert len(motors.drives()) == 1


def test_a_refused_request_during_a_burst_stops_the_base() -> None:
    """A caller asking for movement it may not have is confused: the base stops."""
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    assert wheels.begin("check-1") is None
    fresh(clock, world)
    assert wheels.forward(0.4) is None
    clock.advance(0.1)
    assert wheels.forward(0.4) == "no fresh look since the body last moved"
    assert motors.commands[-1][:2] == ("stop", clock.now())
    assert not motors.running()


def test_the_stop_key_stops_at_once_and_latches() -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    assert wheels.begin("check-1") is None
    fresh(clock, world)
    assert wheels.forward(0.4) is None
    clock.advance(0.1)
    wheels.latch()
    assert motors.commands[-1][:2] == ("stop", clock.now())
    clock.advance(MIN_APPROACH_GAP_S + 1)
    assert wheels.begin("check-2") == "the stop key was pressed"
    fresh(clock, world)
    assert wheels.forward(0.4) == "the stop key was pressed"
    assert len(motors.drives()) == 1


def test_the_stop_key_reaches_the_wheels_without_the_brain_queue() -> None:
    clock = FakeClock()
    wheels, motors, _ = wheels_on(clock)
    rig = make_rig(wheels=wheels)
    rig.brain.key(" ")  # no step(): the queue is never read
    assert wheels.latched
    assert motors.commands and motors.commands[-1][0] == "stop"
    wheels2, _, _ = wheels_on(clock)
    rig2 = make_rig(wheels=wheels2)
    rig2.brain.key("x")
    assert wheels2.latched


def test_the_ears_are_muted_through_each_burst_and_half_a_second_after() -> None:
    from argos.brain import Gate

    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    wheels.gate = Gate()
    wheels.gate.speaking_until = 99.0  # the voice's own field is left alone
    assert wheels.begin("check-1") is None
    fresh(clock, world)
    started = clock.now()
    assert wheels.forward(0.3) is None
    assert wheels.gate.motors_until == pytest.approx(started + 0.3 + 0.5)
    assert wheels.gate.speaking_until == 99.0
    clock.advance(0.1)
    wheels.halt("a test")  # cut short: deaf only half a second from now
    assert wheels.gate.motors_until == pytest.approx(clock.now() + 0.5)


# --------------------------------------------------------------------------- the guard's logic


def guard_core() -> tuple[GuardCore, FakePins, FakeClock]:
    clock = FakeClock()
    pins = FakePins()
    return GuardCore(pins, clock.now), pins, clock


def test_guard_refuses_a_drive_without_a_heartbeat() -> None:
    core, pins, clock = guard_core()
    assert core.handle({"op": "drive", "l": 0.3, "r": 0.3, "s": 0.4}) == "refused: no heartbeat"
    assert pins.stopped()


def test_guard_runs_a_burst_then_stops_by_itself() -> None:
    core, pins, clock = guard_core()
    core.handle({"op": "beat"})
    assert core.handle({"op": "drive", "l": 0.3, "r": -0.25, "s": 0.3}) is None
    assert pins.levels[PINS["ena"]] == 0.3 and pins.levels[PINS["enb"]] == 0.25
    assert pins.levels[PINS["in1"]] == 1 and pins.levels[PINS["in2"]] == 0  # left forward
    assert pins.levels[PINS["in3"]] == 0 and pins.levels[PINS["in4"]] == 1  # right back
    for _ in range(3):
        clock.advance(0.1)
        core.handle({"op": "beat"})
        core.tick()
    assert pins.stopped() and core.last_stop == "the burst ended"


def test_guard_stops_when_the_heartbeat_stops_before_the_burst_ends() -> None:
    core, pins, clock = guard_core()
    core.handle({"op": "beat"})
    core.handle({"op": "drive", "l": 0.3, "r": 0.3, "s": 10.0})  # asks for more than allowed
    assert core.burst_until == pytest.approx(MAX_BURST_S)
    clock.advance(HEARTBEAT_TIMEOUT_S + 0.01)
    core.tick()
    assert pins.stopped() and core.last_stop == "the heartbeat stopped"
    assert HEARTBEAT_TIMEOUT_S < MAX_BURST_S


@pytest.mark.parametrize("command", [
    {"op": "drive", "l": 5.0, "r": -5.0, "s": 0.2},
    {"op": "drive", "l": float("inf"), "r": 0.1, "s": 0.2},
    {"op": "drive", "l": "fast", "r": 0.1, "s": 0.2},
    {"op": "drive", "l": 0.1, "r": 0.1, "s": -1},
    {"op": "spin"},
    {"op": "unreadable"},
])
def test_guard_caps_or_refuses_what_it_cannot_trust(command: dict[str, Any]) -> None:
    core, pins, clock = guard_core()
    core.handle({"op": "beat"})
    core.handle(command)
    for pin in guard.POWER_PINS:
        assert pins.levels[pin] <= MAX_POWER
    if command.get("l") != 5.0:
        assert pins.stopped()


def test_the_gpio_pins_are_the_contracts_with_power_switched_off_while_direction_changes(
        monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[tuple[str, int, Any]] = []

    class Device:
        pin_factory = None

        def __init__(self, pin: int, initial_value: Any = 0, frequency: int | None = None) -> None:
            self.pin = pin
            self._value = initial_value
            log.append((type(self).__name__, pin, initial_value))

        @property
        def value(self) -> Any:
            return self._value

        @value.setter
        def value(self, value: Any) -> None:
            self._value = value
            log.append(("set", self.pin, value))

        def close(self) -> None:
            log.append(("close", self.pin, None))

    class DigitalOutputDevice(Device):
        pass

    class PWMOutputDevice(Device):
        pass

    fake = type(sys)("gpiozero")
    fake.Device = Device  # type: ignore[attr-defined]
    fake.DigitalOutputDevice = DigitalOutputDevice  # type: ignore[attr-defined]
    fake.PWMOutputDevice = PWMOutputDevice  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gpiozero", fake)
    pins = guard.GpioPins()
    made = [(kind, pin, value) for kind, pin, value in log if kind.endswith("Device")]
    assert made[:2] == [("PWMOutputDevice", 12, 0), ("PWMOutputDevice", 13, 0)]
    assert sorted(made[2:]) == [("DigitalOutputDevice", pin, False) for pin in (17, 22, 23, 27)]
    log.clear()
    pins.side("left", +1, 0.9)
    assert log == [("set", 12, 0), ("set", 17, True), ("set", 27, False), ("set", 12, MAX_POWER)]
    log.clear()
    pins.all_low()
    assert [entry[1] for entry in log[:2]] == [12, 13]  # power off first
    assert all(value in (0, False) for _, _, value in log)


# --------------------------------------------------------------------------- the guard, for real

SENDER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {brain!r})
    from argos.body.guard_client import GuardMotors
    motors = GuardMotors(pins="fake", record=__import__("pathlib").Path({record!r}))
    if {frozen!r}:
        motors._beat = lambda: None  # a brain that hangs: no heartbeat
    reason = motors.start()
    print("ready" if reason is None else "failed: " + reason, flush=True)
    motors.drive(0.3, 0.3, 0.5)
    print("driving", flush=True)
    while True:
        time.sleep(0.2)
        if not {frozen!r}:
            motors.drive(0.3, 0.3, 0.5)  # keeps the motors on for as long as it lives
""")


def records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def wait_for(condition: Any, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def start_sender(tmp_path: Path, frozen: bool = False) -> tuple[subprocess.Popen[str], Path]:
    record = tmp_path / "pins.jsonl"
    script = tmp_path / "sender.py"
    script.write_text(SENDER.format(brain=str(BRAIN_DIR), record=str(record), frozen=frozen),
                      encoding="utf-8")
    sender = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, cwd=tmp_path)
    assert sender.stdout is not None
    assert sender.stdout.readline().strip() == "ready"
    assert sender.stdout.readline().strip() == "driving"
    return sender, record


def running(entry: dict[str, Any]) -> bool:
    return any(level != 0 for level in entry["pins"].values())


def test_killing_the_brain_outright_stops_the_motors(tmp_path: Path) -> None:
    sender, record = start_sender(tmp_path)
    try:
        assert wait_for(lambda: any(running(e) for e in records(record)))
        time.sleep(0.6)  # longer than one burst: only the sender keeps them on
        assert running(records(record)[-1])
        sender.kill()  # outright: no handler runs, nothing is said to the guard
        killed = time.monotonic()
        assert wait_for(lambda: any(e.get("event") == "exit" for e in records(record)))
    finally:
        sender.kill()
        sender.wait(10)
    entries = records(record)
    exit_entry = entries[-1]
    assert exit_entry["event"] == "exit"
    # Either sign may come first: the pipe closing, or the parent changing (on the Pi, the
    # parent check won the race the first time this test ran on Linux). Both stop the motors.
    assert exit_entry["reason"] in ("the brain went away (its pipe closed)",
                                    "the brain went away")
    assert not running(exit_entry)
    first_stop = next(e for e in entries if e["t"] >= killed - 1 and not running(e))
    assert first_stop["t"] - killed < 1.0


def test_a_brain_that_hangs_stops_the_motors_through_the_heartbeat(tmp_path: Path) -> None:
    sender, record = start_sender(tmp_path, frozen=True)
    try:
        assert wait_for(lambda: any(running(e) for e in records(record)))
        assert wait_for(lambda: not running(records(record)[-1]), timeout=5.0)
        entries = records(record)
        began = next(e["t"] for e in entries if running(e))
        stopped = next(e["t"] for e in entries if e["t"] > began and not running(e))
        assert stopped - began < MAX_BURST_S  # the heartbeat, not the end of the burst
        assert sender.poll() is None  # the sender is still alive, only silent
    finally:
        sender.kill()
        sender.wait(10)
        stderr = sender.stderr.read() if sender.stderr else ""
    assert "motors stopped: the heartbeat stopped" in stderr


def test_a_normal_close_stops_the_guard_with_every_pin_low(tmp_path: Path) -> None:
    record = tmp_path / "pins.jsonl"
    motors = GuardMotors(pins="fake", record=record)
    assert motors.start() is None
    assert motors.alive()
    assert motors.drive(0.2, -0.2, 0.3)
    assert wait_for(lambda: any(running(e) for e in records(record)))
    motors.close()
    entries = records(record)
    assert entries[-1]["event"] == "exit"
    assert entries[-1]["reason"] == "the brain told it to quit"
    assert not running(entries[-1])
    assert not motors.alive()


@pytest.mark.skipif(os.name != "posix", reason="signals to another process: POSIX only")
@pytest.mark.parametrize("name", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_a_terminate_or_hang_up_ends_the_guard_cleanly(tmp_path: Path, name: str) -> None:
    import signal

    record = tmp_path / "pins.jsonl"
    motors = GuardMotors(pins="fake", record=record)
    assert motors.start() is None
    motors.drive(0.3, 0.3, 0.5)
    assert motors._proc is not None
    os.kill(motors._proc.pid, getattr(signal, name))
    assert wait_for(lambda: any(e.get("event") == "exit" for e in records(record)))
    exit_entry = records(record)[-1]
    assert exit_entry["reason"] == "it was told to stop by a signal"
    assert not running(exit_entry)
    motors.close()


def test_the_brain_handles_terminate_and_hang_up(monkeypatch: pytest.MonkeyPatch) -> None:
    import signal

    from argos.__main__ import install_signal_handlers

    rig = make_rig()
    installed: dict[int, Any] = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: installed.update({sig: handler}))
    install_signal_handlers(rig.brain)
    assert signal.SIGTERM in installed
    if hasattr(signal, "SIGHUP"):
        assert signal.SIGHUP in installed
    installed[signal.SIGTERM](signal.SIGTERM, None)
    assert rig.brain.quit.is_set()


# --------------------------------------------------------------------------- rule 2


BLOCK_PIN_LIBRARY = ("import sys, runpy; sys.modules['gpiozero'] = None; "
                     "runpy.run_module('argos.body.guard', run_name='__main__')")


@pytest.mark.parametrize("launcher", [
    [sys.executable, "-c", BLOCK_PIN_LIBRARY],  # the pin library is missing
    [sys.executable, "-c", "import sys; sys.exit(3)"],  # the guard fails to start
], ids=["no pin library", "guard dies at start"])
def test_with_the_wheels_broken_the_brain_says_so_once_and_a_full_check_runs(
        launcher: list[str], caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    motors = GuardMotors(pins="gpio", launcher=launcher, recover=False)
    rig = make_rig()
    wheels = Wheels(motors, rig.clock, 0.2, 0.2, threaded=False)
    rig = make_rig(wheels=wheels, bodies=[wheels])
    wheels.clock = rig.clock
    rig.brain.start()
    assert not wheels.ready and wheels.broken
    rig.brain.post(TriggerIn("help_call", 0.8))
    rig.step()
    rig.run_for(10.2)
    assert rig.brain.state is State.ALERT
    rig.brain.post(AckIn("Demo"))
    rig.run_for(1.0)
    assert rig.brain.state is State.CALM
    assert rig.event_kinds()[:3] == ["device_online", "trigger", "asked"]
    said = [r.getMessage() for r in caplog.records if r.name == "argos.wheels"
            and r.levelname == "WARNING"]
    assert len(said) == 1 and "Running without wheels" in said[0]
    rig.brain.stop()


def test_a_guard_that_dies_mid_run_turns_the_wheels_off(tmp_path: Path) -> None:
    record = tmp_path / "pins.jsonl"
    motors = GuardMotors(pins="fake", record=record)
    assert motors.start() is None
    assert motors._proc is not None
    motors._proc.kill()
    assert wait_for(lambda: not motors.alive())
    assert motors.drive(0.2, 0.2, 0.3) is False
    motors.close()


def test_a_body_hub_with_wheels_reports_their_movement() -> None:
    clock = FakeClock()
    wheels, motors, world = wheels_on(clock)
    hub = BodyHub([wheels], clock.now)
    assert wheels.begin("check-1") is None
    fresh(clock, world)
    assert wheels.forward(0.3) is None
    assert hub.moving_until() == pytest.approx(clock.now() + 0.3)
