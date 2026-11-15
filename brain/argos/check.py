"""`python -m argos --check`: try every part once, quickly, and print one table.

For the first run on a new machine. Each part is tried once, with a time limit, so nothing
can hang the check. Each row of the table names the part, says whether it works, what was
seen, and, when it does not work, one plain line on what to do.

What it never does:
- Write a record. No row, no event, no local log. The backend is only read.
- Keep a picture or a sound. The one camera frame and the moment of sound are held in
  memory and dropped. The only file it may leave behind is the spoken question in the voice
  cache, which the brain keeps anyway.
- Print the value of a setting. Rows name settings, never what they hold. As a last guard,
  every line goes through `Redactor`, which puts a setting's name where its value would be.
- Turn a wheel. `python -m argos --wheel-test` is a separate, explicit run for that, with
  the base lifted off the floor (`wheel_test`).

The parts a person must watch (a press on the head, which way the head turns, which side of
the picture is the robot's left, whether the speaker was heard) are asked about only when it
runs in a terminal. Everything the check touches outside Python goes through `Hardware`, so
the tests can stand in for every device and every network service.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

import httpx

from argos import text
from argos.approach import deaf_s_max
from argos.body import poses
from argos.body.guard import LOWEST_POWER, MAX_BURST_S, MAX_POWER, describe_pins
from argos.body.press import HeadDiff, head_diff, mean, size
from argos.body.reachy import ReachyClient, RobotRefused, RobotUnavailable
from argos.body.wheels import FakeMotors, worst_case_m
from argos.clock import Clock
from argos.config import BRAIN_DIR, DEFAULT_ROBOT_URL, Settings

log = logging.getLogger("argos.check")

OK, OFF, MISSING, FAIL, WARN, SKIP = "ok", "off", "missing", "FAIL", "warn", "skip"

IMPORTANT = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY",
             "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "CONTACT_LABEL")
NOD = poses.Pose(pitch=8.0)
NOD_S = 0.6
TURN_YAW_DEG = 20.0
REST_WATCH_S = 2.0
PRESS_WATCH_S = 4.0
MIC_S = 1.5
POWER_STEP = 0.05
SAMPLE_S = 0.05


@dataclass
class Row:
    part: str
    result: str
    seen: str
    todo: str = ""


# --------------------------------------------------------------------------- the world outside


def sntp_offset(host: str, timeout_s: float) -> float:
    """Seconds to add to this machine's clock to match a network time server (SNTP)."""
    address = socket.getaddrinfo(host, 123, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        sent = time.time()
        sock.sendto(b"\x1b" + 47 * b"\0", address)
        data, _ = sock.recvfrom(512)
        received = time.time()
    if len(data) < 48:
        raise ValueError("short answer")
    seconds, fraction = struct.unpack("!II", data[40:48])
    server = seconds - 2208988800 + fraction / 2**32
    return server - (sent + received) / 2


def run_command(args: list[str], timeout_s: float) -> tuple[int, str]:
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def list_processes() -> list[tuple[int, str]]:
    """Every running program's id and command line, as far as this user may see them."""
    found: list[tuple[int, str]] = []
    if sys.platform.startswith("linux"):
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if raw:
                found.append((int(entry.name),
                              raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()))
        return found
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                  "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
        _, output = run_command(["powershell", "-NoProfile", "-Command", script], 20.0)
    else:
        _, output = run_command(["ps", "-axo", "pid=,command="], 10.0)
    for line in output.splitlines():
        parts = line.strip().split(None, 1) if "\t" not in line else line.split("\t", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            found.append((int(parts[0]), parts[1].strip()))
    return found


def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_env_file(path: Path = BRAIN_DIR / ".env") -> dict[str, str]:
    """The settings given a value in the .env file itself (not the environment). Held in memory
    to be looked at; never printed."""
    if not path.exists():
        return {}
    try:
        from dotenv import dotenv_values

        values = dotenv_values(path)
    except Exception:
        return {}
    return {name: value.strip() for name, value in values.items() if (value or "").strip()}


class SoundDeviceAudio:
    """The machine's sound devices, through sounddevice."""

    def pick(self, spec: str, kind: str, robot: bool) -> int | str | None:
        from argos.senses.hearing import pick_device

        return pick_device(spec, kind, robot)

    def name(self, device: int | str | None, kind: str) -> str:
        import sounddevice as sd

        return str(sd.query_devices(device, kind)["name"])

    def record(self, device: int | str | None, seconds: float) -> bytes:
        import sounddevice as sd

        rate = 16000
        try:
            data = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16",
                          device=device, blocking=True)
        except Exception:
            rate = int(sd.query_devices(device, "input")["default_samplerate"])
            data = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16",
                          device=device, blocking=True)
        return bytes(data.tobytes())

    def play(self, device: int | str | None, pcm: bytes, rate: int) -> None:
        from argos.voice import SoundDeviceSpeaker

        SoundDeviceSpeaker(device).play(pcm, rate)


def _open_camera(device: int | str, width: int, height: int) -> Any:
    from argos.senses.camera import open_capture

    return open_capture(device, width, height)


def _pose_estimator(path: Path) -> Any:
    from argos.senses.vision import MediaPipePose

    return MediaPipePose(path)


def _speech_model(path: Path) -> Any:
    import vosk

    vosk.SetLogLevel(-1)
    return vosk.Model(str(path))


def gemini_ping(api_key: str, model: str, timeout_s: float) -> Callable[[], str]:
    """One small text request, with no picture. The check's own limit for this row stays
    around it (`PROBES`); the SDK gets at least the API's minimum deadline."""
    from google import genai
    from google.genai import types

    from argos.gemini import sdk_timeout_ms

    client = genai.Client(api_key=api_key,
                          http_options=types.HttpOptions(timeout=sdk_timeout_ms(timeout_s)))

    def ping() -> str:
        response = client.models.generate_content(
            model=model, contents="Reply with the single word: ok",
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="minimal")),
        )
        return response.text or ""

    return ping


def _guard() -> Any:
    from argos.body.guard_client import GuardMotors

    return GuardMotors(pins="gpio")


def _say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


@dataclass
class Hardware:
    """Everything the check touches outside Python."""

    clock: Clock = field(default_factory=Clock)
    transport: httpx.BaseTransport | None = None  # every HTTP request goes through this
    open_camera: Callable[[int | str, int, int], Any] = _open_camera
    audio: Any = field(default_factory=SoundDeviceAudio)
    sntp: Callable[[str, float], float] = sntp_offset
    run: Callable[[list[str], float], tuple[int, str]] = run_command
    processes: Callable[[], list[tuple[int, str]]] = list_processes
    pose_estimator: Callable[[Path], Any] = _pose_estimator
    speech_model: Callable[[Path], Any] = _speech_model
    gemini: Callable[[str, str, float], Callable[[], str]] = gemini_ping
    guard: Callable[[], Any] = _guard
    read_file: Callable[[str], str | None] = read_text
    env_file: Callable[[], Mapping[str, str]] = read_env_file
    gpio_present: Callable[[], bool] = lambda: any(Path("/dev").glob("gpiochip*"))
    platform: str = sys.platform
    interactive: bool = False
    ask: Callable[[str], str] = input
    say: Callable[[str], None] = _say

    @classmethod
    def real(cls) -> Hardware:
        try:
            interactive = sys.stdin is not None and sys.stdin.isatty()
        except (AttributeError, ValueError):
            interactive = False
        return cls(interactive=interactive)


# --------------------------------------------------------------------------- shared state


@dataclass
class Context:
    settings: Settings
    env: Mapping[str, str]
    hw: Hardware
    unreadable: list[str] = field(default_factory=list)
    robot: ReachyClient | None = None
    rest: HeadDiff | None = None
    wobble: tuple[float, float] | None = None
    estimator: Any = None
    frame: Any = None
    ask_audio: bytes | None = None

    def is_set(self, name: str) -> bool:
        return bool((self.env.get(name) or "").strip())

    def where(self, name: str, path: Path) -> str:
        """A file the brain expects, named without printing a setting's value."""
        if self.is_set(name):
            return f"the path in {name}"
        try:
            return path.relative_to(BRAIN_DIR).as_posix()
        except ValueError:
            return str(path)


class Redactor:
    """Puts `<NAME>` wherever a setting's value would appear in printed text."""

    PLAIN = {"auto", "true", "false", "fake", "none", "off", "yes"}

    def __init__(self, env: Mapping[str, str], names: Iterable[str]) -> None:
        pairs: list[tuple[str, str]] = []
        for name in names:
            value = (env.get(name) or "").strip()
            if len(value) < 4 or value.lower() in self.PLAIN or _is_number(value):
                continue
            pairs.append((value, name))
            if "://" in value:
                pairs.append((value.split("://", 1)[1].rstrip("/"), name))
        self.pairs = sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)

    def __call__(self, line: str) -> str:
        for value, name in self.pairs:
            if value in line:
                line = line.replace(value, f"<{name}>")
        return line


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- the rows


def probe_settings(ctx: Context) -> Row:
    names = Settings.names()
    present = [name for name in names if ctx.is_set(name)]
    missing = [name for name in IMPORTANT if not ctx.is_set(name)]
    env_file = (BRAIN_DIR / ".env").exists()
    seen = [f"brain/.env {'found' if env_file else 'not found'}.",
            f"{len(present)} of the {len(names)} settings are set"
            + (f": {', '.join(present)}." if present else ".")]
    if missing:
        seen.append(f"Not set: {', '.join(missing)}.")
    # Which of those came from the command line rather than the file: an ARGOS_WHEELS=0 typed
    # before --check was once taken for a value in brain/.env.
    from_file = ctx.hw.env_file()
    elsewhere = [name for name in present if name not in from_file] if from_file else []
    if elsewhere:
        seen.append("Given on the command line or in the environment, not in brain/.env: "
                    f"{', '.join(elsewhere)}.")
    result, todo = OK, ""
    if ctx.unreadable:
        seen.append(f"Could not use (defaults taken): {', '.join(ctx.unreadable)}.")
        result, todo = WARN, ("Fix those in brain/.env: each must be a number in its range "
                              "(README.md, Settings).")
    elif not env_file and not present:
        result, todo = WARN, "Copy brain/.env.example to brain/.env and fill in what you have."
    # ARGOS_WHEELS belongs on the command line of the one run that needs it, never in the file:
    # there it would arm the wheels on every later start. The value is looked at, not printed.
    in_file = (from_file.get("ARGOS_WHEELS") or "").strip()
    if in_file:
        arms = in_file.lower() == "1"
        seen.append("ARGOS_WHEELS has a value in brain/.env"
                    + (" that switches the wheels on at every start." if arms else "."))
        result = FAIL if arms else WARN
        todo = ("Empty the ARGOS_WHEELS line in brain/.env. Give it only on the command line of "
                "the run that needs it: ARGOS_WHEELS=1 python -m argos." + (f" {todo}" if todo
                                                                           else ""))
    return Row("settings", result, " ".join(seen), todo)


def probe_python(ctx: Context) -> Row:
    version = platform.python_version()
    seen = f"Python {version} on {platform.system()} {platform.machine()}."
    if not version.startswith("3.12."):
        return Row("python", WARN, seen,
                   "Use Python 3.12 (uv venv --python 3.12 .venv): the brain is built and "
                   "tested on it.")
    return Row("python", OK, seen)


def http_date_offset(url: str, transport: httpx.BaseTransport | None) -> float:
    from email.utils import parsedate_to_datetime

    with httpx.Client(timeout=3.0, transport=transport) as client:
        sent = time.time()
        response = client.head(url)
        received = time.time()
    stamp = parsedate_to_datetime(response.headers["date"]).timestamp()
    return stamp + 0.5 - (sent + received) / 2  # the Date header has whole seconds


def probe_clock(ctx: Context) -> Row:
    offset: float | None = None
    source = ""
    try:
        offset, source = ctx.hw.sntp("pool.ntp.org", 2.0), "a network time server"
    except Exception:
        pass
    if offset is None and ctx.settings.backend_configured:
        try:
            offset = http_date_offset(ctx.settings.supabase_url, ctx.hw.transport)
            source = "the backend's clock"
        except Exception:
            pass
    kept = ""
    if ctx.hw.platform.startswith("linux"):
        try:
            code, out = ctx.hw.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                   3.0)
            if code == 0 and out.strip() in ("yes", "no"):
                kept = (" The system keeps its clock in step." if out.strip() == "yes" else
                        " The system says its clock is NOT kept in step.")
        except Exception:
            pass
    if offset is None:
        return Row("clock", WARN, "Could not reach a time server to compare." + kept,
                   "Connect to the network; then timedatectl should say: System clock "
                   "synchronized: yes.")
    gap = abs(offset)
    seen = f"{gap:.1f} s {'ahead of' if offset < 0 else 'behind'} {source}.{kept}"
    if gap > 60:
        return Row("clock", FAIL, seen,
                   "Set the time: sudo timedatectl set-ntp true, wait a minute, run --check "
                   "again. Records carry wrong times and secure connections can fail.")
    if gap > 2:
        return Row("clock", WARN, seen,
                   "sudo timedatectl set-ntp true: records will carry times a little off.")
    return Row("clock", OK, seen)


THROTTLE = {0: "under-voltage", 1: "frequency capped", 2: "throttled",
            3: "soft temperature limit"}


def probe_power(ctx: Context) -> Row:
    model = (ctx.hw.read_file("/proc/device-tree/model") or "").strip("\x00 \n")
    if "Raspberry Pi" not in model:
        return Row("power", SKIP, "Not a Raspberry Pi: nothing to read.")
    try:
        _, out = ctx.hw.run(["vcgencmd", "get_throttled"], 3.0)
    except FileNotFoundError:
        return Row("power", WARN, f"{model}. vcgencmd is missing, so power cannot be read.",
                   "sudo apt install -y raspi-utils, then run --check again.")
    found = re.search(r"0x[0-9a-fA-F]+", out)
    if found is None:
        return Row("power", WARN, f"{model}. vcgencmd gave no reading.",
                   "Run vcgencmd get_throttled by hand to see why.")
    flags = int(found.group(0), 16)
    now = [name for bit, name in THROTTLE.items() if flags & (1 << bit)]
    ever = [name for bit, name in THROTTLE.items() if flags & (1 << (bit + 16))]
    volts = ""
    try:
        _, out = ctx.hw.run(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 3.0)
        if reading := re.search(r"=\s*([0-9.]+)\s*V", out):
            volts = f" The supply reads {float(reading.group(1)):.2f} V."
    except Exception:
        pass
    seen = f"{model}.{volts}"
    if "under-voltage" in now or "under-voltage" in ever:
        when = "now" if "under-voltage" in now else "since it started"
        return Row("power", FAIL, f"{seen} Under-voltage {when}.",
                   "Use the official 27 W USB-C supply for the Pi. The motors must have their "
                   "own battery, never the Pi's supply.")
    if now or ever:
        return Row("power", WARN, f"{seen} Since it started: {', '.join(sorted(set(now + ever)))}.",
                   "Cool it (a fan or a heatsink): seeing and listening slow down when it is "
                   "throttled.")
    return Row("power", OK, f"{seen} No under-voltage or throttling since it started.")


BRAIN_COMMAND = re.compile(r"(?:^|\s)-m\s+argos(?:\s|$)")
GUARD_COMMAND = re.compile(r"argos\.body\.guard")


def probe_other_brain(ctx: Context) -> Row:
    me = os.getpid()
    found: list[str] = []
    listed = True
    try:
        programs = ctx.hw.processes()
    except Exception:
        programs, listed = [], False
    for pid, command in programs:
        if pid == me:
            continue
        if BRAIN_COMMAND.search(command) and "--check" not in command \
                and "--wheel-test" not in command:
            found.append(f"a brain (process {pid})")
        elif GUARD_COMMAND.search(command) and "--pins-low" not in command:
            found.append(f"a wheel guard (process {pid})")
    if ctx.hw.platform.startswith("linux"):
        for scope in (["--user"], []):
            try:
                _, out = ctx.hw.run(["systemctl", *scope, "is-active", "argos-brain"], 3.0)
            except Exception:
                continue
            if out.strip() == "active":
                found.append("the argos-brain service" + (" (user)" if scope else ""))
                break
    if found:
        return Row("another brain", FAIL, f"Already running: {', '.join(found)}.",
                   "Stop it first, or the two fight over the camera, the microphone and the "
                   "records: systemctl --user stop argos-brain, or press q in its terminal.")
    if not listed:
        return Row("another brain", WARN, "Could not list the running programs.",
                   "Make sure no other brain runs: systemctl --user status argos-brain.")
    return Row("another brain", OK, "No other brain is running.")


def _robot_where(ctx: Context) -> str:
    raw = (ctx.env.get("ARGOS_ROBOT") or "").strip().lower()
    if raw in ("", "auto"):
        return f"the default address {DEFAULT_ROBOT_URL.removeprefix('http://')}"
    return "the address in ARGOS_ROBOT"


def probe_robot(ctx: Context) -> Row:
    url = ctx.settings.robot_url
    if url is None:
        return Row("robot daemon", OFF, "Off (ARGOS_ROBOT=off): the brain runs without the robot.")
    where = _robot_where(ctx)
    client = ReachyClient(url, timeout_s=2.0, transport=ctx.hw.transport)
    try:
        status = client.status()
    except RobotRefused as exc:
        return Row("robot daemon", FAIL,
                   f"The daemon at {where} answered with an error (HTTP {exc.status}).",
                   "Restart it: systemctl --user restart reachy-mini-daemon, then run --check "
                   "again.")
    except RobotUnavailable:
        return Row("robot daemon", FAIL, f"No answer from the Reachy Mini daemon at {where}.",
                   "Start it (systemctl --user start reachy-mini-daemon, or by hand: "
                   "~/reachy/.venv/bin/reachy-mini-daemon --no-media --headless), wait 20 s, "
                   "run --check again.")
    state = status.get("state")
    if state != "running":
        error = f" ({status.get('error')})" if status.get("error") else ""
        return Row("robot daemon", FAIL, f"The daemon at {where} is {state}{error}.",
                   "Wait for it to finish starting and run --check again. If it says error, "
                   "read its log: journalctl --user -u reachy-mini-daemon -n 50.")
    kind = "Reachy Mini Wireless" if status.get("wireless_version") else "Reachy Mini Lite"
    if status.get("mockup_sim_enabled"):
        kind += ", a pretend robot (--mockup-sim)"
    elif status.get("simulation_enabled"):
        kind += ", simulated"
    backend = status.get("backend_status") if isinstance(status.get("backend_status"),
                                                         dict) else {}
    mode = backend.get("motor_control_mode")
    try:
        mode = client.motors_mode() or mode
    except RobotUnavailable:
        pass
    nodded = True
    try:
        client.enable_motors()
        client.goto(poses.clamp(NOD), NOD_S)
        ctx.hw.clock.sleep(NOD_S + 0.2)
        client.goto(poses.REST, NOD_S)
        ctx.hw.clock.sleep(NOD_S + 0.5)
    except RobotUnavailable:
        nodded = False
    seen = (f"{kind}, named '{status.get('robot_name') or 'unnamed'}', daemon "
            f"{status.get('version') or 'of unknown version'}. The motors were "
            f"{mode or 'in an unknown mode'}")
    if not nodded:
        return Row("robot daemon", FAIL, seen + "; the nod was refused.",
                   "Check the robot is powered and its USB cable is in, then restart the "
                   "daemon.")
    ctx.robot = client
    seen += "; they are on now, and the head nodded."
    if not status.get("no_media", False):
        return Row("robot daemon", WARN,
                   seen + " The daemon holds the camera and the microphones (no --no-media).",
                   "Restart the daemon with --no-media (deploy/reachy-mini-daemon.service has "
                   "it), or the brain gets no camera and no microphone.")
    return Row("robot daemon", OK, seen)


def _suggest(wobble: float, pressed: float | None, low: float, high: float) -> float:
    value = 3.0 * wobble
    if pressed is not None:
        value = max(value, 0.5 * pressed)
    return min(high, max(low, math.ceil(value * 2) / 2))


def probe_head_rest(ctx: Context) -> Row:
    if ctx.robot is None:
        return Row("head at rest", SKIP, "No robot to read.")
    diffs: list[HeadDiff] = []
    antennas: list[float] = []
    refused = measured_only = False
    start = ctx.hw.clock.now()
    while ctx.hw.clock.now() - start < REST_WATCH_S:
        try:
            reading = ctx.robot.pose_reading()
        except RobotUnavailable:
            return Row("head at rest", FAIL, "The daemon stopped answering while being read.",
                       "Restart the daemon and run --check again.")
        refused = refused or reading.head_refused
        if reading.head is not None:
            diffs.append(head_diff(*reading.head))
        elif reading.head_measured is not None:
            measured_only = True
        if reading.antennas is not None:
            antennas.append(max(abs(p - t) for p, t in zip(*reading.antennas, strict=True)))
        ctx.hw.clock.sleep(SAMPLE_S)
    if not diffs:
        why = ("it refuses the commanded head pose" if refused else
               "it reports where the head is but not where it was told to be" if measured_only
               else "it does not report the head's pose")
        return Row("head at rest", FAIL,
                   f"No head press reading: {why}. The head press cannot work; the antenna "
                   "press still does.",
                   "Update the daemon (in ~/reachy/.venv: uv pip install -U reachy-mini), or "
                   "set ARGOS_HEAD_PAT=0 so the brain stops trying.")
    rest = mean(diffs)
    raw_mm = max(size(d)[0] for d in diffs)
    raw_deg = max(size(d)[1] for d in diffs)
    wob_mm = max(size(d, rest)[0] for d in diffs)
    wob_deg = max(size(d, rest)[1] for d in diffs)
    ctx.rest, ctx.wobble = rest, (wob_mm, wob_deg)
    ant = (f" The antennas sat up to {max(antennas):.2f} rad from where they are held."
           if antennas else "")
    seen = (f"Over {REST_WATCH_S:g} s ({len(diffs)} readings) the head was at most "
            f"{raw_mm:.1f} mm and {raw_deg:.1f} deg from the commanded pose, and wobbled "
            f"{wob_mm:.2f} mm and {wob_deg:.2f} deg around its own resting difference.{ant}")
    s = ctx.settings
    if wob_mm > s.head_pat_mm / 2 or wob_deg > s.head_pat_deg / 2:
        return Row("head at rest", WARN,
                   seen + " That wobble is too large for the current press settings: no head "
                   "press will be sensed.",
                   f"Set ARGOS_HEAD_PAT_MM={_suggest(wob_mm, None, 1, 50):g} and "
                   f"ARGOS_HEAD_PAT_DEG={_suggest(wob_deg, None, 1, 45):g} or higher, then "
                   "measure a press (FIRST_RUN.md, tuning the head press).")
    return Row("head at rest", OK, seen)


def step_head_press(ctx: Context) -> Row:
    if ctx.robot is None or ctx.rest is None or ctx.wobble is None:
        return Row("head press", SKIP, "No head reading at rest, so a press cannot be measured.")
    if not ctx.hw.interactive:
        return Row("head press", SKIP, "Not run in a terminal, so nobody could be asked to "
                   "press the head.", "Run python -m argos --check in a terminal to measure it.")
    answer = ctx.hw.ask("\nHead press: put a hand on top of the robot's head. Press Enter, then "
                        "press the head down gently and hold it until told to let go (type s "
                        "and Enter to skip): ")
    if answer.strip().lower().startswith("s"):
        return Row("head press", SKIP, "Skipped.")
    ctx.hw.say("Press now, and hold...")
    diffs: list[HeadDiff] = []
    start = ctx.hw.clock.now()
    while ctx.hw.clock.now() - start < PRESS_WATCH_S:
        try:
            reading = ctx.robot.pose_reading()
        except RobotUnavailable:
            break
        if reading.head is not None:
            diffs.append(head_diff(*reading.head))
        ctx.hw.clock.sleep(SAMPLE_S)
    ctx.hw.say("Let go.")
    if not diffs:
        return Row("head press", FAIL, "No readings came while the head was pressed.",
                   "Run --check again; if it repeats, use the antenna press.")
    sizes = [size(d, ctx.rest) for d in diffs]
    s = ctx.settings
    held = max(1, math.ceil(s.head_pat_hold_s / SAMPLE_S))
    by_mm = sorted((m for m, _ in sizes), reverse=True)
    by_deg = sorted((g for _, g in sizes), reverse=True)
    held_mm = by_mm[min(held, len(by_mm)) - 1]
    held_deg = by_deg[min(held, len(by_deg)) - 1]
    counts = held_mm >= s.head_pat_mm or held_deg >= s.head_pat_deg
    wob_mm, wob_deg = ctx.wobble
    sug_mm = _suggest(wob_mm, held_mm, 1, 50)
    sug_deg = _suggest(wob_deg, held_deg, 1, 45)
    seen = (f"While pressed the head moved up to {by_mm[0]:.1f} mm and {by_deg[0]:.1f} deg from "
            f"rest, and held at least {held_mm:.1f} mm and {held_deg:.1f} deg for the hold time. "
            f"With the current settings this press {'counts' if counts else 'does NOT count'}.")
    # A press must stand well clear of the wobble, so that a setting can sit between them.
    clear = held_mm >= max(2.0, 6 * wob_mm) or held_deg >= max(2.0, 6 * wob_deg)
    if counts and clear:
        return Row("head press", OK, seen)
    if not clear:
        return Row("head press", WARN, seen + " The press is hardly bigger than the wobble.",
                   "Press a little firmer and run --check again; if it stays like this, rely "
                   "on the antenna press.")
    return Row("head press", WARN, seen,
               f"Set ARGOS_HEAD_PAT_MM={sug_mm:g} and ARGOS_HEAD_PAT_DEG={sug_deg:g} in "
               "brain/.env, then run --check again to confirm.")


def step_head_direction(ctx: Context) -> Row | None:
    if ctx.robot is None or not ctx.hw.interactive:
        return None
    answer = ctx.hw.ask("\nHead direction: the head will turn a little to one side and back. "
                        "Press Enter and watch it (s and Enter to skip): ")
    if answer.strip().lower().startswith("s"):
        return Row("head direction", SKIP, "Skipped.")
    try:
        ctx.robot.goto(poses.clamp(poses.Pose(yaw=TURN_YAW_DEG)), NOD_S * 1.5)
        ctx.hw.clock.sleep(NOD_S * 1.5 + 0.6)
        ctx.robot.goto(poses.REST, NOD_S * 1.5)
        ctx.hw.clock.sleep(NOD_S * 1.5 + 0.3)
    except RobotUnavailable:
        return Row("head direction", FAIL, "The turn was refused.", "Run --check again.")
    side = ctx.hw.ask("Which way did it turn: to the robot's own (l)eft, or its own (r)ight? "
                      "[l/r] ").strip().lower()
    if side.startswith("l"):
        return Row("head direction", OK,
                   "A positive head turn goes to the robot's left, as the brain assumes.")
    if side.startswith("r"):
        return Row("head direction", FAIL,
                   "A positive head turn goes to the robot's RIGHT. The brain assumes left, "
                   "so it would look away from the person.",
                   "Do not switch the wheels on. Tell the brain's maintainer (body/poses.py).")
    return Row("head direction", SKIP, "No answer given.")


def probe_pose_model(ctx: Context) -> Row:
    path = ctx.settings.pose_model
    where = ctx.where("ARGOS_POSE_MODEL", path)
    if not path.exists():
        return Row("pose model", MISSING, f"Not found at {where}.",
                   "Download it: python tools/fetch_models.py (once, with a network).")
    try:
        ctx.estimator = ctx.hw.pose_estimator(path)
    except Exception as exc:
        return Row("pose model", FAIL, f"Found at {where}, but it did not load "
                   f"({type(exc).__name__}: {str(exc)[:120]}).",
                   "Delete the file and run python tools/fetch_models.py again.")
    return Row("pose model", OK, f"Found at {where}, and it loads.")


def _third(pose: Any) -> str:
    middle = pose.center_x()
    if middle is None:
        return "picture"
    if middle < pose.width / 3:
        return "left third"
    if middle > pose.width * 2 / 3:
        return "right third"
    return "middle third"


def _camera_name(ctx: Context, device: int | str) -> str:
    raw = (ctx.env.get("ARGOS_CAMERA") or "").strip().lower()
    if raw not in ("", "auto"):
        return "The camera in ARGOS_CAMERA"
    if isinstance(device, str):
        return "The robot's camera"
    if ctx.hw.platform.startswith("linux"):
        return "Camera 0 (the robot's camera was not found by name)"
    return "Camera 0"


def _grab(ctx: Context, device: int | str) -> Any:
    capture = ctx.hw.open_camera(device, ctx.settings.camera_width, ctx.settings.camera_height)
    image = None
    try:
        good = 0
        for _ in range(12):  # the first frames of a camera can be dark or empty
            ok, frame = capture.read()
            if ok and frame is not None:
                image, good = frame, good + 1
                if good >= 3:
                    break
    finally:
        capture.release()
    return image


def probe_camera(ctx: Context) -> Row:
    from argos.senses.camera import resolve

    spec = ctx.settings.camera
    device = resolve(spec)
    if device is None:
        if spec.strip().lower() == "off":
            return Row("camera", OFF, "Off (ARGOS_CAMERA=off): no fall or stillness checks.")
        return Row("camera", MISSING, "No camera matched the name in ARGOS_CAMERA.",
                   "Check it is plugged in: v4l2-ctl --list-devices")
    name = _camera_name(ctx, device)
    try:
        image = _grab(ctx, device)
    except Exception:
        return Row("camera", FAIL, f"{name} did not open.",
                   "Plug it in. A daemon started without --no-media holds the robot's camera. "
                   "On Windows set ARGOS_CAMERA to the robot camera's number (often 1).")
    if image is None:
        return Row("camera", FAIL, f"{name} opened but gave no picture.",
                   "Unplug it and plug it back in, and make sure nothing else is using it.")
    height, width = image.shape[:2]
    ctx.frame = image
    seen = f"{name}: a {width}x{height} picture."
    if ctx.estimator is None:
        return Row("camera", WARN, seen + " With no pose model nobody can be seen in it.",
                   "See the pose model row.")
    ctx.estimator.estimate(image, 1)  # the first estimate includes setting up
    started = time.perf_counter()
    pose = ctx.estimator.estimate(image, 1000)
    took = time.perf_counter() - started
    if pose is not None and pose.score >= ctx.settings.person_min_score:
        seen += f" A person is in the {_third(pose)} of it."
    else:
        seen += " Nobody is in it."
    load = took * ctx.settings.detect_fps
    seen += (f" One pose estimate takes {took * 1000:.0f} ms, so seeing at the brain's rate "
             f"uses about {load * 100:.0f}% of one processor core.")
    if load > 0.6:
        return Row("camera", WARN, seen,
                   "Lower ARGOS_DETECT_FPS (or the camera size) so the Pi keeps up while it "
                   "also listens and sends the live view.")
    return Row("camera", OK, seen)


def step_camera_side(ctx: Context) -> Row | None:
    if ctx.frame is None or ctx.estimator is None or not ctx.hw.interactive:
        return None
    answer = ctx.hw.ask("\nCamera sides: stand on the robot's own LEFT, a step or two away, "
                        "where its camera can see you, and press Enter (s and Enter to skip): ")
    if answer.strip().lower().startswith("s"):
        return Row("camera sides", SKIP, "Skipped.")
    from argos.senses.camera import resolve

    device = resolve(ctx.settings.camera)
    try:
        image = _grab(ctx, device) if device is not None else None
    except Exception:
        image = None
    if image is None:
        return Row("camera sides", FAIL, "The camera gave no picture this time.",
                   "Run --check again.")
    pose = ctx.estimator.estimate(image, 5000)
    if pose is None or pose.score < ctx.settings.person_min_score or pose.center_x() is None:
        return Row("camera sides", WARN, "Nobody was found in the picture.",
                   "Stand further back, in the light, and run --check again.")
    if pose.center_x() < pose.width / 2:
        return Row("camera sides", OK,
                   "The robot's left is the left of the picture, as the brain assumes.")
    return Row("camera sides", FAIL,
               "The robot's left is the RIGHT of the picture: the picture is mirrored. The "
               "approach would turn away from the person, and the head would look away.",
               "Do not switch the wheels on. Tell the brain's maintainer.")


def probe_speech_model(ctx: Context) -> Row:
    if ctx.settings.listen.lower() == "off":
        return Row("speech model", OFF, "Listening is off (ARGOS_LISTEN=off).")
    path = ctx.settings.vosk_model
    where = ctx.where("ARGOS_VOSK_MODEL", path)
    if not path.exists():
        return Row("speech model", MISSING, f"Not found at {where}.",
                   "Download it: python tools/fetch_models.py (once, with a network).")
    try:
        model = ctx.hw.speech_model(path)
        del model
    except Exception as exc:
        return Row("speech model", FAIL, f"Found at {where}, but it did not load "
                   f"({type(exc).__name__}).",
                   "Delete the folder and run python tools/fetch_models.py again.")
    return Row("speech model", OK, f"Found at {where}, and it loads.")


def levels(pcm: bytes) -> tuple[float, float]:
    """Average and peak level, in dB below full scale."""
    import numpy as np

    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2").astype(np.float64)
    if samples.size == 0:
        return -120.0, -120.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))

    def db(value: float) -> float:
        return 20 * math.log10(value / 32768.0) if value > 0 else -120.0

    return db(rms), db(peak)


def probe_microphone(ctx: Context) -> Row:
    if ctx.settings.listen.lower() == "off":
        return Row("microphone", OFF, "Listening is off (ARGOS_LISTEN=off).")
    robot = ctx.settings.robot_url is not None
    try:
        device = ctx.hw.audio.pick(ctx.settings.audio_in, "input", robot)
        name = ctx.hw.audio.name(device, "input")
        pcm = ctx.hw.audio.record(device, MIC_S)
    except Exception as exc:
        return Row("microphone", FAIL, f"No microphone could be opened ({type(exc).__name__}).",
                   "Plug the robot in (its microphones are a USB sound card), check arecord -l "
                   "lists it, and that this user is in the audio group (run: groups).")
    average, peak = levels(pcm)
    del pcm  # the moment of sound is not kept
    seen = (f"{name}: heard {average:.0f} dBFS on average and {peak:.0f} dBFS at the loudest, "
            f"over {MIC_S:g} s.")
    if peak <= -90:
        return Row("microphone", FAIL, seen + " That is silence.",
                   "It gives nothing: check it is not muted (alsamixer) and that it is the "
                   "robot's (ARGOS_AUDIO_IN).")
    return Row("microphone", OK, seen)


def _voice_cache(ctx: Context) -> Path:
    from argos.voice import Voice

    s = ctx.settings
    voice = Voice(ctx.hw.clock, s.cache_dir / "voice", None, None,
                  cache_key=f"{s.elevenlabs_voice_id}|{s.elevenlabs_model}", threaded=False)
    return voice.cache_path("ask")


ELEVEN_REASONS = {
    401: ("the key was refused", "Check ELEVENLABS_API_KEY."),
    402: ("the account is out of credit", "Top up the ElevenLabs account."),
    403: ("the key may not do this", "Give the key text-to-speech access."),
    404: ("the voice was not found", "Check ELEVENLABS_VOICE_ID."),
    422: ("the request was refused (the model or the voice)",
          "Check ELEVENLABS_VOICE_ID and ELEVENLABS_MODEL."),
    429: ("too many requests, or over the quota", "Wait a minute and run --check again."),
}


def probe_elevenlabs(ctx: Context) -> Row:
    from argos.voice import ElevenLabs, VoiceRefused

    s = ctx.settings
    path = _voice_cache(ctx)
    if not (s.elevenlabs_api_key and s.elevenlabs_voice_id):
        missing = [n for n in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID") if not ctx.is_set(n)]
        if path.exists():
            ctx.ask_audio = path.read_bytes()
            have = "The question is in the voice cache, so it can still be spoken."
        else:
            have = "Nothing is cached, so the question will be a beep."
        return Row("ElevenLabs", MISSING, f"Not set: {', '.join(missing)}. {have}",
                   "Put the ElevenLabs key and voice id in brain/.env.")
    tts = ElevenLabs(s.elevenlabs_api_key, s.elevenlabs_voice_id, s.elevenlabs_model,
                     timeout_s=10.0, transport=ctx.hw.transport)
    try:
        data = tts.synthesize(text.ASK_LINE)
    except VoiceRefused as exc:
        reason, todo = ELEVEN_REASONS.get(exc.status, (f"HTTP {exc.status}",
                                                       "Run --check again."))
        return Row("ElevenLabs", FAIL, f"ElevenLabs refused the request: {reason}.", todo)
    except (httpx.HTTPError, RuntimeError) as exc:
        return Row("ElevenLabs", FAIL, f"Could not reach ElevenLabs ({type(exc).__name__}).",
                   "Check the network.")
    kept = "it is already in the voice cache"
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            kept = "it is now kept in the voice cache"
        except OSError:
            kept = "the voice cache could not be written"
    ctx.ask_audio = data
    return Row("ElevenLabs", OK,
               f"Spoke the question ({len(data) / 2 / 16000:.1f} s of audio); {kept}.")


def beep_pcm(seconds: float = 0.3, hz: float = 880.0, rate: int = 16000) -> bytes:
    import numpy as np

    t = np.arange(int(seconds * rate)) / rate
    tone = 0.25 * np.sin(2 * math.pi * hz * t) * np.minimum(1.0, (seconds - t) * 20)
    return bytes((tone * 32767).astype("<i2").tobytes())


def probe_speaker(ctx: Context) -> Row:
    robot = ctx.settings.robot_url is not None
    try:
        device = ctx.hw.audio.pick(ctx.settings.audio_out, "output", robot)
        name = ctx.hw.audio.name(device, "output")
        pcm, what = (ctx.ask_audio, "the question") if ctx.ask_audio else (beep_pcm(), "a beep")
        ctx.hw.audio.play(device, pcm, 16000)
    except Exception as exc:
        return Row("speaker", FAIL, f"No speaker could be used ({type(exc).__name__}).",
                   "Plug the robot in (its speaker is on the same USB sound card), check aplay "
                   "-l lists it, and that this user is in the audio group (run: groups).")
    return Row("speaker", OK, f"{name}: played {what}.")


def step_speaker_heard(ctx: Context, rows: list[Row]) -> None:
    row = next((r for r in rows if r.part == "speaker"), None)
    if row is None or row.result != OK:
        return
    if not ctx.hw.interactive:
        row.seen += " Nobody was asked whether it was heard."
        return
    heard = ctx.hw.ask("\nDid you hear it come from the robot? [y/n] ").strip().lower()
    if heard.startswith("n"):
        row.result = FAIL
        row.seen += " It was not heard."
        row.todo = ("Turn the volume up (alsamixer, the robot's card) and check ARGOS_AUDIO_OUT "
                    "names the robot's card.")
    elif heard.startswith("y"):
        row.seen += " It was heard."


def key_kind(key: str) -> str:
    """"secret", "publishable" or "unknown", from the key alone. Nothing is printed."""
    if key.startswith("sb_secret_"):
        return "secret"
    if key.startswith("sb_publishable_"):
        return "publishable"
    parts = key.split(".")
    if len(parts) == 3:
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
        except (ValueError, TypeError):
            return "unknown"
        role = claims.get("role") if isinstance(claims, dict) else None
        if role == "service_role":
            return "secret"
        if role == "anon":
            return "publishable"
    return "unknown"


def probe_backend(ctx: Context) -> Row:
    from argos.store import StoreRejected, StoreUnavailable, SupabaseStore

    s = ctx.settings
    if not s.backend_configured:
        missing = [n for n in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not ctx.is_set(n)]
        return Row("backend", MISSING,
                   f"Not set: {', '.join(missing)}. Records go to the local log only.",
                   "Put SUPABASE_URL and the secret key (SUPABASE_SERVICE_ROLE_KEY) in brain/.env.")
    kind = key_kind(s.supabase_key)
    if kind == "publishable":
        return Row("backend", FAIL,
                   "SUPABASE_SERVICE_ROLE_KEY holds the public key (publishable or anon). It "
                   "cannot read or write the brain's records.",
                   "Use the secret key (sb_secret_...): Supabase dashboard, Project settings, "
                   "API keys.")
    store = SupabaseStore(s.supabase_url, s.supabase_key, timeout_s=5.0,
                          transport=ctx.hw.transport)
    try:
        rows = store.select("devices", {"id": f"eq.{s.device_id}"}, "id")
    except StoreRejected as exc:
        status = re.search(r"HTTP (\d+)", str(exc))
        return Row("backend", FAIL,
                   f"The backend refused the key ({status.group(0) if status else 'refused'}).",
                   "Check that SUPABASE_SERVICE_ROLE_KEY is this project's secret key and that "
                   "SUPABASE_URL is this project's address.")
    except StoreUnavailable:
        return Row("backend", FAIL, "Could not reach the backend.",
                   "Check the network and SUPABASE_URL.")
    finally:
        store.close()
    if not rows:
        return Row("backend", FAIL, "Reached the backend, but this device's row is not there.",
                   f"Ask Hasan to add the device row ({s.device_id}).")
    note = "" if kind == "secret" else " The key's kind was not recognised, but it works."
    return Row("backend", OK, "Read this device's row with the secret key." + note)


def gemini_reason(exc: BaseException) -> tuple[str, str]:
    code = getattr(exc, "code", None)
    message = str(getattr(exc, "message", "") or exc).lower()
    if isinstance(exc, ImportError):
        return "the google-genai package is missing", "uv pip install -r requirements.txt"
    if code == 400 and ("api key" in message or "api_key" in message):
        return "the key is not valid", "Check GEMINI_API_KEY."
    if code in (401, 403):
        return "the key may not use this model", "Check GEMINI_API_KEY and GEMINI_MODEL."
    if code == 404:
        return "the model was not found", "Check GEMINI_MODEL, or leave it empty for the default."
    if code == 429:
        return "over the quota or the rate limit", "Wait a minute, or use a key on a paid plan."
    if "timeout" in type(exc).__name__.lower() or "timed out" in message:
        return "no answer in time", "Check the network and run --check again."
    # Google's own words say what is wrong, where the code alone does not (on the Pi: "Manually
    # set deadline 8s is too short"). They never hold the key, and the table is redacted anyway.
    said = " ".join(str(getattr(exc, "message", "") or "").split())[:160]
    return (f"{type(exc).__name__}{f' (HTTP {code})' if code else ''}"
            + (f'; Google says: "{said}"' if said else ""),
            "Check the network and GEMINI_API_KEY.")


def probe_gemini(ctx: Context) -> Row:
    s = ctx.settings
    if not s.gemini_api_key:
        return Row("Gemini", MISSING, "Not set: GEMINI_API_KEY. No Gemini check, and the "
                   "summary is a fixed sentence.", "Put the Gemini key in brain/.env.")
    try:
        ctx.hw.gemini(s.gemini_api_key, s.gemini_model, s.gemini_timeout_s)()
    except Exception as exc:
        reason, todo = gemini_reason(exc)
        return Row("Gemini", FAIL, f"Gemini refused or failed: {reason}.", todo)
    return Row("Gemini", OK, "Answered one small request (text only; no picture was sent).")


def probe_live_view(ctx: Context) -> Row:
    from argos.liveview import Broadcaster, encode_frame

    s = ctx.settings
    if not s.live_view:
        return Row("live view", OFF, "Off (ARGOS_LIVE_VIEW is not 1): no frames are sent.")
    if not s.backend_configured:
        return Row("live view", FAIL, "On, but there are no backend settings to send through.",
                   "Put SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in brain/.env.")
    if ctx.frame is not None:
        image, what = ctx.frame, "one camera frame"
    else:
        import numpy as np

        image, what = np.full((240, 320, 3), 96, dtype=np.uint8), "one grey test picture"
    message = encode_frame(image, 0, ctx.hw.clock.iso())
    if message is None:
        return Row("live view", FAIL, "On, but the frame could not be made small enough.",
                   "Lower ARGOS_CAMERA_WIDTH and ARGOS_CAMERA_HEIGHT.")
    sender = Broadcaster(s.supabase_url, s.supabase_key, s.device_id, timeout_s=5.0,
                         transport=ctx.hw.transport)
    try:
        sent = sender.send(message)
    finally:
        sender.close()
    if not sent:
        return Row("live view", FAIL, f"On, but {what} could not be sent ({sender.last_error}).",
                   "HTTP 403 means the private channel refused the key: ask Hasan to check the "
                   "live view's access rules. Otherwise check the network.")
    return Row("live view", OK, f"On. Sent {what} to the private live view topic; nothing was "
               "kept.")


def probe_wheels(ctx: Context) -> Row:
    s = ctx.settings
    pins = describe_pins()
    limits = (f" Power is capped at {MAX_POWER:.2f} of full; one approach could cover at most "
              f"about {worst_case_m():.1f} m; it can keep the ears shut for at most "
              f"{deaf_s_max(s.approach_max_s):.1f} s of a check's wait.")
    if s.wheels == "off":
        return Row("wheels", OFF, f"Off (ARGOS_WHEELS is not 1): no pin is touched. When on, "
                   f"they use {pins}.")
    if s.wheels == "fake":
        return Row("wheels", OK, "Pretend (ARGOS_WHEELS=fake): nothing moves; bursts are only "
                   "logged." + limits)
    if not ctx.hw.platform.startswith("linux"):
        return Row("wheels", FAIL, "On, but this machine has no GPIO pins (it is not Linux).",
                   "Use the wheels on the Pi, or set ARGOS_WHEELS=fake on a laptop.")
    if not ctx.hw.gpio_present():
        return Row("wheels", FAIL, "On, but no GPIO device was found (/dev/gpiochip*).",
                   "This must run on the Raspberry Pi the motors are wired to.")
    motors = ctx.hw.guard()
    reason = motors.start()
    motors.close()
    if reason:
        return Row("wheels", FAIL, f"On, but the guard could not take the pins: {reason}.",
                   "On the Pi: uv pip install -r requirements.txt (brings gpiozero and lgpio), "
                   "and check this user is in the gpio group (run: groups).")
    return Row("wheels", OK,
               f"On. The guard started, held {pins} all low, and let them go. They arm only "
               "when the brain runs in a terminal; space or x stops them." + limits)


# --------------------------------------------------------------------------- running it


PROBES: list[tuple[str, Callable[[Context], Row], float]] = [
    ("settings", probe_settings, 5.0),
    ("python", probe_python, 5.0),
    ("clock", probe_clock, 10.0),
    ("power", probe_power, 10.0),
    ("another brain", probe_other_brain, 25.0),
    ("robot daemon", probe_robot, 15.0),
    ("head at rest", probe_head_rest, 10.0),
    ("pose model", probe_pose_model, 30.0),
    ("camera", probe_camera, 25.0),
    ("speech model", probe_speech_model, 30.0),
    ("microphone", probe_microphone, 10.0),
    ("ElevenLabs", probe_elevenlabs, 15.0),
    ("speaker", probe_speaker, 15.0),
    ("backend", probe_backend, 10.0),
    ("Gemini", probe_gemini, 15.0),
    ("live view", probe_live_view, 10.0),
    ("wheels", probe_wheels, 20.0),
]


def limited(part: str, probe: Callable[[Context], Row], ctx: Context, limit_s: float) -> Row:
    """One row, within a time limit. Whatever goes wrong inside becomes a row, never a crash."""
    result: list[Row] = []
    error: list[BaseException] = []

    def run() -> None:
        try:
            result.append(probe(ctx))
        except Exception as exc:
            error.append(exc)

    thread = threading.Thread(target=run, name=f"check-{part}", daemon=True)
    thread.start()
    thread.join(limit_s)
    if result:
        return result[0]
    if error:
        return Row(part, FAIL, f"The check of this part failed ({type(error[0]).__name__}).",
                   "Run --check again; if it repeats, tell the brain's maintainer.")
    return Row(part, FAIL, f"No answer within {limit_s:g} s.",
               "Something is stuck: try again, then look at this part by hand.")


def print_table(rows: list[Row], out: TextIO, redact: Callable[[str], str],
                width: int | None = None) -> None:
    width = width or max(80, min(110, shutil.get_terminal_size((100, 24)).columns))
    part_w = max(len(row.part) for row in rows) + 2
    result_w = 8
    text_w = max(30, width - part_w - result_w)
    out.write(f"\n{'part':<{part_w}}{'result':<{result_w}}what was seen, and what to do\n")
    out.write(f"{'-' * (part_w - 2):<{part_w}}{'-' * (result_w - 2):<{result_w}}"
              f"{'-' * text_w}\n")
    for row in rows:
        lines = textwrap.wrap(redact(row.seen), text_w) or [""]
        if row.todo:
            lines += textwrap.wrap("-> " + redact(row.todo), text_w, subsequent_indent="   ")
        out.write(f"{row.part:<{part_w}}{row.result:<{result_w}}{lines[0]}\n")
        for line in lines[1:]:
            out.write(f"{'':<{part_w + result_w}}{line}\n")
    counts = {name: sum(1 for row in rows if row.result == name)
              for name in (OK, OFF, MISSING, WARN, FAIL, SKIP)}
    summary = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
    out.write(f"\n{summary}. Nothing was recorded, and no picture or sound was kept.\n")
    out.flush()


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def read_settings(env: Mapping[str, str]) -> tuple[Settings, list[str]]:
    """The settings, and the names of any that could not be used. The config log, which may
    name a setting, is caught here and never printed."""
    capture = _Capture()
    config_log = logging.getLogger("argos.config")
    propagate = config_log.propagate
    config_log.addHandler(capture)
    config_log.propagate = False
    try:
        settings = Settings.from_env(env)
    finally:
        config_log.removeHandler(capture)
        config_log.propagate = propagate
    unreadable = sorted({str(record.args[0]) for record in capture.records
                         if isinstance(record.args, tuple) and record.args})
    return settings, unreadable


def run_check(env: Mapping[str, str], hw: Hardware, out: TextIO | None = None) -> int:
    """Every row, then the table. 1 if any part failed, else 0."""
    out = out or sys.stdout
    settings, unreadable = read_settings(env)
    ctx = Context(settings, env, hw, unreadable)
    redact = Redactor(env, Settings.names())
    rows: list[Row] = []

    def add(row: Row | None) -> None:
        if row is not None:
            rows.append(row)
            hw.say(redact(f"  {row.part:<15} {row.result}"))

    hw.say("Argos check: each part once. Nothing is recorded and nothing is kept.")
    for part, probe, limit_s in PROBES:
        add(limited(part, probe, ctx, limit_s))
        if part == "head at rest":
            add(_guarded("head press", step_head_press, ctx))
            add(_guarded("head direction", step_head_direction, ctx))
        elif part == "camera":
            add(_guarded("camera sides", step_camera_side, ctx))
        elif part == "speaker":
            step_speaker_heard(ctx, rows)
    if ctx.robot is not None:
        ctx.robot.close()
    ctx.frame = None
    ctx.ask_audio = None
    print_table(rows, out, redact)
    return 1 if any(row.result == FAIL for row in rows) else 0


def _guarded(part: str, step: Callable[[Context], Row | None], ctx: Context) -> Row | None:
    """An interactive step: no time limit (a person is answering), but never a crash."""
    try:
        return step(ctx)
    except (EOFError, KeyboardInterrupt):
        return Row(part, SKIP, "Stopped before an answer was given.")
    except Exception as exc:
        return Row(part, FAIL, f"The check of this part failed ({type(exc).__name__}).",
                   "Run --check again.")


# --------------------------------------------------------------------------- the wheel test


def _drive_side(motors: Any, side: str, direction: int, power: float) -> None:
    value = direction * power
    left, right = (value, 0.0) if side == "left" else (0.0, value)
    motors.drive(left, right, MAX_BURST_S)


def wheel_test(env: Mapping[str, str], hw: Hardware, out: TextIO | None = None) -> int:
    """Turn each side forward and back, at the lowest power and up, with the base lifted.

    Refused unless ARGOS_WHEELS=1 (or `fake`), and unless a person is at the keyboard. It
    drives the motors through the guard, so the guard's own caps hold: power at most
    MAX_POWER, each run at most MAX_BURST_S, and it stops if this program stops."""
    out = out or sys.stdout
    settings, unreadable = read_settings(env)
    ctx = Context(settings, env, hw, unreadable)
    redact = Redactor(env, Settings.names())
    rows = [probe_settings(ctx)]
    result = _wheel_runs(ctx)
    rows.extend(result)
    print_table(rows, out, redact)
    return 1 if any(row.result == FAIL for row in rows) else 0


def _wheel_runs(ctx: Context) -> list[Row]:
    s, hw = ctx.settings, ctx.hw
    if s.wheels == "off":
        return [Row("wheel test", FAIL, "The wheels are off (ARGOS_WHEELS is not 1), so no pin "
                    "may be touched.", "Start it as ARGOS_WHEELS=1 python -m argos --wheel-test "
                    "(on the command line only, never in brain/.env).")]
    if not hw.interactive:
        return [Row("wheel test", FAIL, "Not run in a terminal: the wheel test needs a person "
                    "at the keyboard.", "Run python -m argos --wheel-test in a terminal.")]
    if s.wheels == "fake":
        motors: Any = FakeMotors(hw.clock)
        hw.say("Pretend wheels (ARGOS_WHEELS=fake): nothing will move; this is a rehearsal.")
    else:
        if not hw.platform.startswith("linux") or not hw.gpio_present():
            return [Row("wheel test", FAIL, "This machine has no GPIO pins.",
                        "Run the wheel test on the Raspberry Pi the motors are wired to.")]
        motors = hw.guard()
    answer = hw.ask(
        "\nLIFT THE BASE OFF THE FLOOR, so that no wheel touches anything. The wheels will "
        f"turn, one side at a time, forward then back, {MAX_BURST_S:g} s each, starting at "
        f"power {LOWEST_POWER:.2f}. Keep a hand near the battery switch.\n"
        "Press Enter when the base is lifted, or q and Enter to stop: ")
    if answer.strip().lower().startswith("q"):
        return [Row("wheel test", SKIP, "Stopped before any wheel turned.")]
    reason = motors.start()
    if reason:
        return [Row("wheel test", FAIL, f"The guard could not take the pins: {reason}.",
                    "See the wheels row of python -m argos --check.")]
    found: dict[str, tuple[float | None, bool]] = {}
    turned = ""
    try:
        for side in ("left", "right"):
            power = LOWEST_POWER
            while True:
                hw.say(f"The {side} side at power {power:.2f}: forward, then back.")
                _drive_side(motors, side, +1, power)
                hw.clock.sleep(MAX_BURST_S + 0.6)
                _drive_side(motors, side, -1, power)
                hw.clock.sleep(MAX_BURST_S + 0.6)
                said = hw.ask(f"Did the {side.upper()} wheels turn forward first, then back? "
                              "[y = yes / r = back first / n = they did not move / q = stop] "
                              ).strip().lower()
                if said.startswith("q"):
                    raise KeyboardInterrupt
                if said.startswith(("y", "r")):
                    found[side] = (power, said.startswith("r"))
                    break
                if power >= MAX_POWER - 1e-9:
                    found[side] = (None, False)
                    break
                power = min(MAX_POWER, round(power + POWER_STEP, 2))
        if all(found.get(side, (None, False))[0] is not None for side in ("left", "right")):
            power = max(found["left"][0] or 0.0, found["right"][0] or 0.0)
            hw.say(f"Both sides together, as a turn to the robot's left, at power {power:.2f}.")
            left = -power * (-1 if found["left"][1] else 1)
            right = power * (-1 if found["right"][1] else 1)
            motors.drive(left, right, MAX_BURST_S)
            hw.clock.sleep(MAX_BURST_S + 0.6)
            said = hw.ask("Did the left wheels go back and the right wheels forward? [y/n] ")
            turned = "y" if said.strip().lower().startswith("y") else "n"
    except KeyboardInterrupt:
        hw.say("Stopped.")
    finally:
        motors.stop()
        motors.close()
    return _wheel_rows(found, turned)


def _wheel_rows(found: dict[str, tuple[float | None, bool]], turned: str) -> list[Row]:
    rows: list[Row] = []
    for side in ("left", "right"):
        if side not in found:
            rows.append(Row(f"wheels {side}", SKIP, "Not tried."))
            continue
        power, backwards = found[side]
        if power is None:
            rows.append(Row(f"wheels {side}", FAIL,
                            f"Did not move even at the cap ({MAX_POWER:.2f}).",
                            "Check the wiring to the L298N, its jumpers, and the motor battery "
                            "(tired AAA cells sag hard under four motors)."))
            continue
        invert = side.upper()
        todo = (f"Set ARGOS_WHEELS_INVERT_{invert}=1 in brain/.env (or swap that side's two "
                "motor wires on the L298N)." if backwards else "")
        rows.append(Row(f"wheels {side}", WARN if backwards else OK,
                        f"Moved at power {power:.2f}"
                        + ("; it went back first, so its wires are the other way round." if
                           backwards else "; forward is forward."), todo))
    powers = [found[side][0] for side in ("left", "right") if side in found]
    if len(powers) == 2 and all(p is not None for p in powers):
        lowest = max(p for p in powers if p is not None)
        rows.append(Row("wheels power", OK,
                        f"The lowest power that moved both sides, lifted: {lowest:.2f}.",
                        f"Set ARGOS_WHEELS_POWER={lowest:.2f}, and ARGOS_WHEELS_TURN_POWER a "
                        "little higher after one try on the floor: turning scrubs."))
    if turned == "n":
        rows.append(Row("wheels turn", FAIL, "The turn did not go as expected.",
                        "The left and right sides may be swapped: IN1/IN2 and ENA must be the "
                        "left side (contract section 2)."))
    elif turned == "y":
        rows.append(Row("wheels turn", OK, "A turn to the left drove the left side back and the "
                        "right side forward."))
    return rows
