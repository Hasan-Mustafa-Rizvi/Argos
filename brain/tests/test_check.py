"""`python -m argos --check` and `--wheel-test`, against fakes for every device and service.

No robot, camera, microphone, speaker, GPIO or network is touched: everything the check
reaches outside Python goes through `Hardware`, and here every part of it is a fake.
"""

from __future__ import annotations

import io
import math
import os
import random
import re
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from argos import DEVICE_ID
from argos.body.guard import MAX_BURST_S, MAX_POWER
from argos.check import (
    FAIL,
    MISSING,
    OK,
    PROBES,
    Hardware,
    Redactor,
    key_kind,
    run_check,
    wheel_test,
)
from argos.clock import FakeClock
from argos.config import BRAIN_DIR
from argos.senses.vision import PersonPose
from tests.test_vision import STANDING

PARTS = [part for part, _, _ in PROBES]


def files_under(root: Path) -> set[str]:
    skip = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv"}
    found = set()
    for path in root.rglob("*"):
        if not any(part in skip for part in path.parts):
            found.add(str(path))
    return found


class World:
    """Every network service the check talks to: the robot's daemon, the backend, the live
    view and ElevenLabs."""

    def __init__(self, clock: FakeClock, robot: bool = True, refuse_target: bool = False) -> None:
        self.clock = clock
        self.robot = robot
        self.refuse_target = refuse_target
        self.target_set = False
        self.press: tuple[float, float] | None = None
        self.requests: list[httpx.Request] = []
        self.rng = random.Random(4)

    def head(self, pressed: bool) -> dict[str, float]:
        wobble = lambda: self.rng.uniform(-0.0002, 0.0002)  # noqa: E731
        z = 0.008 - 0.0015 + wobble() - (0.009 if pressed else 0.0)
        return {"x": wobble(), "y": wobble(), "z": z, "roll": wobble(),
                "pitch": math.radians(-1.0) + wobble(), "yaw": wobble()}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path, params = request.url.host, request.url.path, request.url.params
        if host == "127.0.0.1":
            if not self.robot:
                raise httpx.ConnectError("refused", request=request)
            if path == "/api/daemon/status":
                return httpx.Response(200, json={
                    "robot_name": "reachy_mini", "state": "running", "wireless_version": False,
                    "simulation_enabled": False, "mockup_sim_enabled": False, "no_media": True,
                    "version": "1.9.0", "backend_status": {"ready": True,
                                                           "motor_control_mode": "disabled"}})
            if path == "/api/motors/status":
                return httpx.Response(200, json={"mode": "disabled"})
            if path in ("/api/motors/set_mode/enabled", "/api/move/goto"):
                self.target_set = True
                return httpx.Response(200, json={"status": "ok"})
            if path == "/api/state/full":
                wants_target = params.get("with_target_head_pose") == "true"
                if wants_target and (self.refuse_target or not self.target_set):
                    return httpx.Response(500, json={"detail": "Internal Server Error"})
                now = self.clock.now()
                pressed = self.press is not None and self.press[0] <= now < self.press[1]
                body: dict[str, Any] = {"head_pose": self.head(pressed),
                                        "antennas_position": [0.01, -0.01],
                                        "target_antennas_position": [0.0, 0.0]}
                if wants_target:
                    body["target_head_pose"] = {"x": 0.0, "y": 0.0, "z": 0.008, "roll": 0.0,
                                                "pitch": 0.0, "yaw": 0.0}
                return httpx.Response(200, json=body)
        if host == "backend.invalid":
            if path == "/rest/v1/devices" and request.method == "GET":
                return httpx.Response(200, json=[{"id": DEVICE_ID}])
            if path.startswith("/realtime/v1/api/broadcast/"):
                return httpx.Response(202)
            return httpx.Response(404, json={"message": "no"})
        if host == "api.elevenlabs.io":
            return httpx.Response(200, content=b"\x01\x00" * 16000)
        raise httpx.ConnectError("no network in tests", request=request)


class FakeCapture:
    def __init__(self, image: Any) -> None:
        self.image = image
        self.released = False

    def read(self) -> tuple[bool, Any]:
        return True, self.image

    def release(self) -> None:
        self.released = True


class FakeEstimator:
    def __init__(self, shift: float = 0.0) -> None:
        self.shift = shift

    def estimate(self, image: Any, t_ms: int) -> PersonPose:
        return PersonPose({name: (x + self.shift, y, 0.9) for name, (x, y) in STANDING.items()},
                          640, 480)


class FakeAudio:
    def __init__(self) -> None:
        self.played: list[int] = []
        self.recorded = 0

    def pick(self, spec: str, kind: str, robot: bool) -> int:
        return 3

    def name(self, device: Any, kind: str) -> str:
        return "Reachy Mini Audio"

    def record(self, device: Any, seconds: float) -> bytes:
        self.recorded += 1
        noise = np.random.default_rng(1).integers(-300, 300, int(seconds * 16000))
        return noise.astype("<i2").tobytes()

    def play(self, device: Any, pcm: bytes, rate: int) -> None:
        self.played.append(len(pcm))


def broken(*args: Any, **kwargs: Any) -> Any:
    raise OSError("not here")


def missing_hardware(clock: FakeClock, world: World) -> Hardware:
    class NoAudio:
        pick = name = record = play = staticmethod(broken)

    return Hardware(clock=clock, transport=httpx.MockTransport(world), open_camera=broken,
                    audio=NoAudio(), sntp=broken, run=lambda args, t: broken(),
                    processes=broken, pose_estimator=broken, speech_model=broken,
                    gemini=broken, guard=lambda: pytest.fail("no guard may start"),
                    read_file=lambda path: None, gpio_present=lambda: False,
                    platform="linux", interactive=False, ask=lambda q: pytest.fail("no question"),
                    say=lambda message: None)


def present_hardware(clock: FakeClock, world: World, answers: list[str] | None = None,
                     said: list[str] | None = None) -> Hardware:
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    replies = list(answers or [])

    def ask(question: str) -> str:
        return replies.pop(0) if replies else ""

    def run(args: list[str], timeout: float) -> tuple[int, str]:
        if args[:2] == ["vcgencmd", "get_throttled"]:
            return 0, "throttled=0x0"
        if args[:2] == ["vcgencmd", "pmic_read_adc"]:
            return 0, "EXT5V_V volt(24)=5.10000000V"
        if args[0] == "timedatectl":
            return 0, "yes"
        if args[0] == "systemctl":
            return 3, "inactive"
        raise FileNotFoundError(args[0])

    return Hardware(clock=clock, transport=httpx.MockTransport(world),
                    open_camera=lambda d, w, h: FakeCapture(image), audio=FakeAudio(),
                    sntp=lambda host, t: 0.1, run=run,
                    processes=lambda: [(1, "python -m argos_call"), (2, "bash")],
                    pose_estimator=lambda path: FakeEstimator(-200),
                    speech_model=lambda path: object(),
                    gemini=lambda key, model, t: (lambda: "ok"),
                    read_file=lambda path: "Raspberry Pi 5 Model B Rev 1.0\x00",
                    gpio_present=lambda: True, platform="linux",
                    interactive=answers is not None, ask=ask,
                    say=(said.append if said is not None else (lambda message: None)))


def models(tmp: Path) -> dict[str, str]:
    pose = tmp / "pose.task"
    pose.write_bytes(b"model")
    vosk = tmp / "vosk"
    vosk.mkdir()
    return {"ARGOS_POSE_MODEL": str(pose), "ARGOS_VOSK_MODEL": str(vosk)}


def rows_of(table: str) -> dict[str, str]:
    """{part: result} from the printed table."""
    found = {}
    for line in table.splitlines():
        for part in [*PARTS, "head press", "head direction", "camera sides"]:
            if line.startswith(part + " "):
                found[part] = line[len(part):].split()[0]
    return found


# --------------------------------------------------------------------------- everything missing


def test_with_everything_missing_every_row_prints_and_nothing_is_left(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = files_under(tmp_path) | files_under(BRAIN_DIR)
    clock = FakeClock()
    world = World(clock, robot=False)
    env = {"ARGOS_LOG_DIR": str(tmp_path / "log"), "ARGOS_CACHE_DIR": str(tmp_path / "cache"),
           "ARGOS_POSE_MODEL": str(tmp_path / "none.task"),
           "ARGOS_VOSK_MODEL": str(tmp_path / "none-vosk")}
    out = io.StringIO()
    code = run_check(env, missing_hardware(clock, world), out)
    table = out.getvalue()
    found = rows_of(table)
    for part in PARTS:
        assert part in found, f"no row for {part}"
    assert "check of this part failed" not in table  # no part crashed
    assert found["robot daemon"] == FAIL and found["camera"] == FAIL
    assert found["backend"] == MISSING and found["Gemini"] == MISSING
    assert found["wheels"] == "off"
    assert code == 1
    writes = [r for r in world.requests if r.method in ("POST", "PATCH", "PUT", "DELETE")
              and "/rest/" in r.url.path]
    assert writes == []  # no record
    assert files_under(tmp_path) | files_under(BRAIN_DIR) == before  # no new file


def test_no_value_of_any_setting_is_printed(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World(clock, robot=False)
    env = {
        "SUPABASE_URL": "https://marker-url-value.invalid",
        "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_MARKERKEYVALUE",
        "GEMINI_API_KEY": "MARKER-GEMINI-VALUE", "GEMINI_MODEL": "MARKER-MODEL-VALUE",
        "ELEVENLABS_API_KEY": "MARKER-ELEVEN-VALUE", "ELEVENLABS_VOICE_ID": "MARKER-VOICE-ID",
        "ELEVENLABS_MODEL": "MARKER-ELEVEN-MODEL", "CONTACT_LABEL": "MARKER-CONTACT",
        "CONTACT_FACETIME_TO": "MARKER-FACETIME", "CONTACT_EMAIL_TO": "MARKER-EMAIL",
        "ARGOS_ROBOT": "http://marker-robot.invalid:8000", "ARGOS_CAMERA": "MARKER-CAMERA",
        "ARGOS_AUDIO_IN": "MARKER-AUDIO-IN", "ARGOS_AUDIO_OUT": "MARKER-AUDIO-OUT",
        "SERIAL_PORT": "MARKER-SERIAL", "ARGOS_LIVE_VIEW": "1", "ARGOS_WHEELS": "1",
        "ARGOS_POSE_MODEL": str(tmp_path / "MARKER-POSE.task"),
        "ARGOS_VOSK_MODEL": str(tmp_path / "MARKER-VOSK"),
        "ARGOS_LOG_DIR": str(tmp_path / "MARKER-LOG"),
        "ARGOS_CACHE_DIR": str(tmp_path / "MARKER-CACHE"),
        "CHECK_TIMEOUT_S": "MARKER-NOT-A-NUMBER",
    }
    said: list[str] = []
    hardware = missing_hardware(clock, world)
    hardware.say = said.append
    out = io.StringIO()
    run_check(env, hardware, out)
    printed = out.getvalue() + "\n".join(said)
    assert "MARKER" not in printed
    assert "marker" not in printed.lower()
    assert "CHECK_TIMEOUT_S" in printed  # named as unusable, without its value


def test_redactor_names_a_setting_where_its_value_would_be() -> None:
    redact = Redactor({"SUPABASE_URL": "https://abc.supabase.co", "CHECK_TIMEOUT_S": "10",
                       "ARGOS_CAMERA": "auto"}, ["SUPABASE_URL", "CHECK_TIMEOUT_S",
                                                 "ARGOS_CAMERA"])
    assert redact("POST https://abc.supabase.co/rest") == "POST <SUPABASE_URL>/rest"
    assert redact("host abc.supabase.co") == "host <SUPABASE_URL>"
    assert redact("waits 10 s, camera auto") == "waits 10 s, camera auto"


@pytest.mark.parametrize(
    ("key", "kind"),
    [("sb_secret_abc", "secret"), ("sb_publishable_abc", "publishable"),
     ("x." + "eyJyb2xlIjoic2VydmljZV9yb2xlIn0" + ".y", "secret"),
     ("x." + "eyJyb2xlIjoiYW5vbiJ9" + ".y", "publishable"), ("nonsense", "unknown")],
)
def test_the_kind_of_backend_key_is_told_without_printing_it(key: str, kind: str) -> None:
    assert key_kind(key) == kind


# --------------------------------------------------------------------------- everything present


def test_with_everything_present_every_row_is_ok_and_nothing_is_recorded(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World(clock)
    env = {"SUPABASE_URL": "https://backend.invalid", "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_K",
           "GEMINI_API_KEY": "G", "ELEVENLABS_API_KEY": "E", "ELEVENLABS_VOICE_ID": "V",
           "CONTACT_LABEL": "Daughter", "ARGOS_LIVE_VIEW": "1", "ARGOS_WHEELS": "fake",
           "ARGOS_CAMERA": "0", "ARGOS_CACHE_DIR": str(tmp_path / "cache"),
           "ARGOS_LOG_DIR": str(tmp_path / "log"), **models(tmp_path)}
    hardware = present_hardware(clock, world)
    out = io.StringIO()
    code = run_check(env, hardware, out)
    found = rows_of(out.getvalue())
    for part in PARTS:
        if part == "settings":
            continue
        assert found[part] == OK, f"{part}: {out.getvalue()}"
    assert code == 0
    assert "A person is in the left third" in out.getvalue()
    paths = [(r.method, r.url.path) for r in world.requests if r.url.host == "backend.invalid"]
    assert ("GET", "/rest/v1/devices") in paths
    assert not any(method != "GET" and path.startswith("/rest/") for method, path in paths)
    # The only file left is the spoken question, in the voice cache.
    left = [p for p in (tmp_path / "cache").rglob("*") if p.is_file()]
    assert len(left) == 1 and left[0].suffix == ".pcm"
    assert not (tmp_path / "log").exists()
    assert hardware.audio.played and hardware.audio.recorded == 1


def test_head_press_is_measured_and_settings_suggested(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World(clock)
    said: list[str] = []
    answers = ["", "", "l"]  # start the press, start the turn, it turned to the left

    def ask_and_press(question: str) -> str:
        if question.strip().startswith("Head press"):
            world.press = (clock.now(), clock.now() + 3.0)
        return answers.pop(0) if answers else "s"

    hardware = present_hardware(clock, world, answers=[], said=said)
    hardware.ask = ask_and_press
    env = {"ARGOS_CAMERA": "off", "ARGOS_LISTEN": "off", "ARGOS_HEAD_PAT_MM": "20",
           "ARGOS_CACHE_DIR": str(tmp_path / "cache"), **models(tmp_path)}
    out = io.StringIO()
    run_check(env, hardware, out)
    table = out.getvalue()
    found = rows_of(table)
    assert found["head at rest"] == OK
    assert found["head press"] == "warn"  # 9 mm does not reach a 20 mm setting
    assert "does NOT count" in table
    suggested = re.search(r"ARGOS_HEAD_PAT_MM=([0-9.]+)", " ".join(table.split()))
    assert suggested and 4.0 <= float(suggested.group(1)) <= 5.5  # about half the 9 mm held
    assert found["head direction"] == OK


def test_a_daemon_that_refuses_the_commanded_pose_is_reported_not_lost(tmp_path: Path) -> None:
    clock = FakeClock()
    world = World(clock, refuse_target=True)
    env = {"ARGOS_CAMERA": "off", "ARGOS_LISTEN": "off", **models(tmp_path)}
    out = io.StringIO()
    run_check(env, present_hardware(clock, world), out)
    found = rows_of(out.getvalue())
    assert found["robot daemon"] == OK
    assert found["head at rest"] == FAIL
    assert "refuses the commanded head pose" in out.getvalue()
    assert "antenna press still does" in out.getvalue()


def test_another_brain_and_its_service_are_found() -> None:
    clock = FakeClock()
    world = World(clock, robot=False)
    hardware = present_hardware(clock, world)
    hardware.processes = lambda: [(os.getpid(), "python -m argos --check"),
                                  (4242, "/home/x/Argos/brain/.venv/bin/python -m argos")]
    out = io.StringIO()
    run_check({"ARGOS_CAMERA": "off", "ARGOS_LISTEN": "off"}, hardware, out)
    assert rows_of(out.getvalue())["another brain"] == FAIL
    assert "process 4242" in out.getvalue()


# --------------------------------------------------------------------------- the wheel test


def test_wheel_test_is_refused_with_the_wheels_off() -> None:
    clock = FakeClock()
    hardware = missing_hardware(clock, World(clock))
    hardware.interactive = True
    out = io.StringIO()
    assert wheel_test({}, hardware, out) == 1
    assert "no pin may be touched" in out.getvalue()


def test_wheel_test_needs_a_person_at_the_keyboard() -> None:
    clock = FakeClock()
    hardware = missing_hardware(clock, World(clock))
    out = io.StringIO()
    assert wheel_test({"ARGOS_WHEELS": "1"}, hardware, out) == 1
    assert "needs a person at the keyboard" in out.getvalue()


def test_wheel_test_steps_up_the_power_until_a_side_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    from argos.body import wheels

    made: list[Any] = []
    real = wheels.FakeMotors

    def record(clock: Any) -> Any:
        made.append(real(clock))
        return made[-1]

    monkeypatch.setattr("argos.check.FakeMotors", record)
    clock = FakeClock()
    said: list[str] = []
    # lifted; left: no, no, yes; right: went back first; the turn: yes
    hardware = present_hardware(clock, World(clock), answers=["", "n", "n", "y", "r", "y"],
                                said=said)
    out = io.StringIO()
    wheel_test({"ARGOS_WHEELS": "fake"}, hardware, out)
    table = out.getvalue()
    assert "LIFT THE BASE" not in table  # it was asked, not printed in the table
    assert "Moved at power 0.30" in table
    assert "ARGOS_WHEELS_INVERT_RIGHT=1" in table
    assert "ARGOS_WHEELS_POWER=0.30" in table
    drives = made[0].drives()
    assert drives, "the pretend motors were driven"
    for _, _, left, right, seconds in drives:
        assert abs(left) <= MAX_POWER and abs(right) <= MAX_POWER and seconds <= MAX_BURST_S
    assert made[0].closed


def test_wheel_test_stops_when_asked() -> None:
    clock = FakeClock()
    hardware = present_hardware(clock, World(clock), answers=["q"])
    out = io.StringIO()
    wheel_test({"ARGOS_WHEELS": "fake"}, hardware, out)
    assert "Stopped before any wheel turned" in out.getvalue()


def test_the_command_line_runs_the_check_with_the_environment(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import argos.__main__ as entry
    import argos.check as check

    seen: dict[str, Any] = {}
    monkeypatch.setattr(entry, "load_env_file", lambda: None)
    monkeypatch.setattr(check.Hardware, "real", classmethod(lambda cls: "HARDWARE"))
    monkeypatch.setattr(check, "run_check",
                        lambda env, hw: seen.update(env=env, hw=hw, what="check") or 0)
    monkeypatch.setattr(check, "wheel_test",
                        lambda env, hw: seen.update(env=env, hw=hw, what="wheels") or 0)
    assert entry.main(["--check"]) == 0
    assert seen["what"] == "check" and seen["hw"] == "HARDWARE" and seen["env"] is os.environ
    assert entry.main(["--wheel-test"]) == 0
    assert seen["what"] == "wheels"


def test_the_table_ends_by_saying_nothing_was_kept() -> None:
    clock = FakeClock()
    out = io.StringIO()
    run_check({"ARGOS_CAMERA": "off"}, missing_hardware(clock, World(clock, robot=False)), out)
    last = out.getvalue().strip().splitlines()[-1]
    assert last.endswith("Nothing was recorded, and no picture or sound was kept.")
