"""Start the brain:  python -m argos   (add --script to play the demo story).

    python -m argos --check        try every part once and print one table (writes nothing)
    python -m argos --wheel-test   turn each wheel briefly, with the base lifted (ARGOS_WHEELS=1)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from typing import Any

from argos.body.base import Body, BodyHub
from argos.body.press import HeadPress
from argos.body.reachy import ReachyClient, RobotBody
from argos.body.serial_link import SensorBoard
from argos.body.wheels import Wheels
from argos.brain import Brain, ThreadRunner
from argos.clock import Clock
from argos.config import BRAIN_DIR, Settings
from argos.escalation import make_escalator
from argos.keyboard import Keyboard, attached, help_text
from argos.locallog import LocalLog
from argos.records import Recorder
from argos.script import FIXTURE, ScriptPlayer, load
from argos.store import SupabaseStore
from argos.writer import RecordWriter

log = logging.getLogger("argos")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m argos", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--script", action="store_true",
                        help="play the story of contract/fixtures/demo_scenario.jsonl")
    parser.add_argument("--loop", action="store_true", help="with --script: play it again and "
                        "again")
    parser.add_argument("--no-keys", action="store_true", help="do not read the keyboard (the "
                        "wheels then stay off)")
    parser.add_argument("--check", action="store_true",
                        help="try every part once, print one table, and exit; records nothing")
    parser.add_argument("--wheel-test", action="store_true",
                        help="turn each side of the base briefly at the lowest power and up; "
                        "lift the base off the floor first")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING or ERROR")
    return parser.parse_args(argv)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # Libraries that log request URLs or headers at INFO are kept quiet.
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def load_env_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Real environment variables win over the file.
    load_dotenv(BRAIN_DIR / ".env", override=False)


def build_bodies(settings: Settings, clock: Clock) -> list[Body]:
    bodies: list[Body] = []
    if settings.robot_url:
        press = (HeadPress(settings.head_pat_mm, settings.head_pat_deg, settings.head_pat_hold_s)
                 if settings.head_pat else None)
        bodies.append(RobotBody(ReachyClient(settings.robot_url), clock,
                                antenna_pat=settings.robot_antenna_pat, head_press=press))
    else:
        log.info("robot: off (ARGOS_ROBOT=off)")
    if settings.serial_port:
        bodies.append(SensorBoard(settings.serial_port, clock))
    else:
        log.info("SERIAL_PORT is empty: no sensor board")
    return bodies


def build_wheels(settings: Settings, clock: Clock, keyboard: bool, scripted: bool,
                 platform: str = sys.platform) -> Wheels | None:
    """The wheels, or None. Built only when every rule allows it; nothing here loads a pin
    library or touches a pin (the guard process does, once started)."""
    if settings.wheels == "off":
        log.info("wheels: off (ARGOS_WHEELS is not 1): no pin is touched")
        return None
    if scripted:
        log.info("wheels: not used in a scripted run")
        return None
    if not keyboard:
        log.warning("wheels: switched on, but no keyboard is attached (a service, piped input "
                    "or --no-keys), so they stay off: the stop key must be at hand")
        return None
    if settings.wheels == "fake":
        from argos.body.wheels import FakeMotors

        motors: Any = FakeMotors(clock)
    else:
        if not platform.startswith("linux"):
            log.warning("wheels: switched on, but this machine has no GPIO pins (it is not "
                        "Linux). Running without wheels.")
            return None
        from argos.body.guard_client import GuardMotors

        motors = GuardMotors(pins="gpio")
    return Wheels(motors, clock, settings.wheels_power, settings.wheels_turn_power,
                  invert_left=settings.wheels_invert_left,
                  invert_right=settings.wheels_invert_right, pretend=settings.wheels == "fake")


def install_signal_handlers(brain: Brain) -> None:
    """A service stop (SIGTERM) and a dropped SSH session (SIGHUP) end the brain in order:
    the wheels stop first, the robot rests, the records are flushed."""

    def stop(signum: int, frame: Any) -> None:
        log.info("signal %s: stopping", signum)
        brain.quit.set()

    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, stop)
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env_file()
    if args.check or args.wheel_test:
        setup_logging(args.log_level or "ERROR")
        from argos.check import Hardware, run_check, wheel_test

        hardware = Hardware.real()
        if args.wheel_test:
            return wheel_test(os.environ, hardware)
        return run_check(os.environ, hardware)
    setup_logging(args.log_level or "INFO")
    settings = Settings.from_env(os.environ)
    clock = Clock()

    local_log = LocalLog(settings.log_dir)
    store = None
    if settings.backend_configured:
        store = SupabaseStore(settings.supabase_url, settings.supabase_key)
    else:
        log.warning("no backend settings (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY): recording to "
                    "the local log only, in %s", settings.log_dir)
    writer = RecordWriter(store, note=lambda message: local_log.note(clock.iso(), message))
    recorder = Recorder(settings.device_id, clock, writer, local_log)
    escalator = make_escalator(settings, recorder)
    keys_on = not args.no_keys
    wheels = build_wheels(settings, clock, keyboard=keys_on and attached(),
                          scripted=args.script)
    bodies = build_bodies(settings, clock)
    # The hub tells the robot when any part moves, the wheels included (no pat then).
    hub = BodyHub(bodies + ([wheels] if wheels is not None else []), clock.now)

    script = None
    if args.script:
        steps, length = load(FIXTURE)
        script = ScriptPlayer(steps, length, loop=args.loop)
        log.info("scripted run: %d steps over %g s%s", len(steps), length,
                 ", looping" if args.loop else "")

    senses = None
    try:
        from argos.senses import build_senses

        senses = build_senses(settings, clock, hub, store)
    except ImportError as exc:
        log.warning("senses unavailable (%s): keyboard and sensor board only", exc)

    brain = Brain(
        settings, clock, recorder, writer, hub, escalator, ThreadRunner(), store=store,
        voice=senses.voice if senses else None,
        vision=senses.vision if senses else None,
        frames=senses.frames if senses else None,
        judge=senses.judge if senses else None,
        uploader=senses.uploader if senses else None,
        script=script,
        wheels=wheels,
    )
    install_signal_handlers(brain)

    keyboard = None
    if keys_on:
        keyboard = Keyboard(brain.key)
        print(help_text(), flush=True)
    try:
        brain.start()
        if senses:
            senses.start(brain)
        if keyboard:
            keyboard.start()
        brain.run()
    except KeyboardInterrupt:
        log.info("stopping")
        brain.quit.set()
    finally:
        brain.stop()  # for any reason at all: the wheels stop first
        if keyboard:
            keyboard.stop()
        if senses:
            senses.stop()
        local_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
