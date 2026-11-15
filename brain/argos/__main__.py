"""Start the brain:  python -m argos   (add --script to play the demo story)."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from argos.body.base import Body, BodyHub
from argos.body.reachy import ReachyClient, RobotBody
from argos.body.serial_link import SensorBoard
from argos.brain import Brain, ThreadRunner
from argos.clock import Clock
from argos.config import BRAIN_DIR, Settings
from argos.escalation import make_escalator
from argos.keyboard import Keyboard, help_text
from argos.locallog import LocalLog
from argos.records import Recorder
from argos.script import FIXTURE, ScriptPlayer, load
from argos.store import SupabaseStore
from argos.writer import RecordWriter

log = logging.getLogger("argos")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m argos", description=__doc__)
    parser.add_argument("--script", action="store_true",
                        help="play the story of contract/fixtures/demo_scenario.jsonl")
    parser.add_argument("--loop", action="store_true", help="with --script: play it again and "
                        "again")
    parser.add_argument("--no-keys", action="store_true", help="do not read the keyboard")
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING or ERROR")
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
        bodies.append(RobotBody(ReachyClient(settings.robot_url), clock,
                                antenna_pat=settings.robot_antenna_pat))
    else:
        log.info("robot: off (ARGOS_ROBOT=off)")
    if settings.serial_port:
        bodies.append(SensorBoard(settings.serial_port, clock))
    else:
        log.info("SERIAL_PORT is empty: no sensor board")
    return bodies


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env_file()
    setup_logging(args.log_level)
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
    hub = BodyHub(build_bodies(settings, clock), clock.now)

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
    )

    keyboard = None
    if not args.no_keys:
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
        brain.stop()
    finally:
        if keyboard:
            keyboard.stop()
        if senses:
            senses.stop()
        local_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
