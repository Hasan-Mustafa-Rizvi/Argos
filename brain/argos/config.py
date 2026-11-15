"""Settings, read once from the environment.

Only the names in the root `.env.example` and in `brain/.env.example` are read. Contact
details (`CONTACT_FACETIME_TO`, `CONTACT_EMAIL_TO`) are never read by this program: real
sending is not built, and a value that is never read cannot leak.

A value that cannot be used is reported by name only, never with what it holds: a key pasted
into the wrong line must not reach a log.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from argos import DEVICE_ID
from argos.body.guard import LOWEST_POWER, MAX_POWER

log = logging.getLogger("argos.config")

BRAIN_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ROBOT_URL = "http://127.0.0.1:8000"


def _text(env: Mapping[str, str], name: str, default: str = "") -> str:
    value = env.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = _text(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        log.warning("%s is not a number; using %s", name, default)
        return default
    if value != value:  # NaN compares unequal to itself
        log.warning("%s is not a number; using %s", name, default)
        return default
    if not low <= value <= high:
        clamped = min(high, max(low, value))
        log.warning("%s is outside %s to %s; using %s", name, low, high, clamped)
        return clamped
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _text(env, name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _wheels(env: Mapping[str, str]) -> str:
    """"on" only for exactly `ARGOS_WHEELS=1` (contract section 2). "fake" is a pretend base
    that moves nothing, for a laptop. Anything else, or nothing, is "off"."""
    raw = _text(env, "ARGOS_WHEELS").lower()
    if raw == "1":
        return "on"
    if raw == "fake":
        return "fake"
    return "off"


def _path(env: Mapping[str, str], name: str, default: str) -> Path:
    path = Path(_text(env, name, default)).expanduser()
    return path if path.is_absolute() else BRAIN_DIR / path


@dataclass(frozen=True)
class Settings:
    device_id: str
    # Backend
    supabase_url: str
    supabase_key: str
    # Escalation. `dry_run` is always True in this build: real sending is not built.
    dry_run: bool
    dry_run_off_requested: bool
    contact_label: str
    check_timeout_s: float
    ack_poll_s: float
    # Bodies
    serial_port: str
    robot: str
    robot_antenna_pat: bool
    # Local files
    log_dir: Path
    cache_dir: Path
    # Camera and detection
    camera: str
    camera_width: int
    camera_height: int
    camera_hfov_deg: float
    detect_fps: float
    pose_model: Path
    person_min_score: float
    fall_angle_deg: float
    fall_hold_s: float
    stillness_s: float
    still_move: float
    trigger_cooldown_s: float
    # Listening and voice
    listen: str
    vosk_model: Path
    audio_in: str
    audio_out: str
    help_min_conf: float
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    # Gemini
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_s: float
    summary_timeout_s: float
    snapshot_timeout_s: float
    # Live view
    live_view: bool
    live_view_fps: float
    # The head press as a pat
    head_pat: bool
    head_pat_mm: float
    head_pat_deg: float
    head_pat_hold_s: float
    # The wheels and the approach. Power is a share of full, and never above MAX_POWER.
    wheels: str  # "on", "fake" or "off"
    wheels_power: float
    wheels_turn_power: float
    wheels_invert_left: bool
    wheels_invert_right: bool
    approach_max_s: float
    approach_rest_s: float
    # The call agent (call/) writes the call events instead of the brain
    call_agent: bool

    @property
    def backend_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def robot_url(self) -> str | None:
        if self.robot.lower() == "off":
            return None
        if self.robot.lower() in ("", "auto"):
            # The daemon listens on 127.0.0.1 only. "localhost" can resolve to ::1 first, which
            # on Windows costs a timeout before the right address is tried.
            return DEFAULT_ROBOT_URL
        return self.robot.rstrip("/")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        dry_raw = _text(env, "ARGOS_DRY_RUN")
        return cls(
            device_id=DEVICE_ID,
            supabase_url=_text(env, "SUPABASE_URL").rstrip("/"),
            supabase_key=_text(env, "SUPABASE_SERVICE_ROLE_KEY"),
            dry_run=True,
            dry_run_off_requested=dry_raw == "0",
            contact_label=_text(env, "CONTACT_LABEL", "Family"),
            check_timeout_s=_number(env, "CHECK_TIMEOUT_S", 10.0, 1.0, 600.0),
            ack_poll_s=_number(env, "ARGOS_ACK_POLL_S", 2.0, 0.5, 60.0),
            serial_port=_text(env, "SERIAL_PORT"),
            robot=_text(env, "ARGOS_ROBOT", "auto"),
            robot_antenna_pat=_flag(env, "ARGOS_ROBOT_ANTENNA_PAT", True),
            log_dir=_path(env, "ARGOS_LOG_DIR", "var/log"),
            cache_dir=_path(env, "ARGOS_CACHE_DIR", "var/cache"),
            camera=_text(env, "ARGOS_CAMERA", "auto"),
            camera_width=int(_number(env, "ARGOS_CAMERA_WIDTH", 640, 160, 1920)),
            camera_height=int(_number(env, "ARGOS_CAMERA_HEIGHT", 480, 120, 1080)),
            camera_hfov_deg=_number(env, "ARGOS_CAMERA_HFOV_DEG", 70.0, 20.0, 180.0),
            detect_fps=_number(env, "ARGOS_DETECT_FPS", 8.0, 1.0, 30.0),
            pose_model=_path(env, "ARGOS_POSE_MODEL", "models/pose_landmarker_lite.task"),
            person_min_score=_number(env, "ARGOS_PERSON_MIN_SCORE", 0.5, 0.0, 1.0),
            fall_angle_deg=_number(env, "ARGOS_FALL_ANGLE_DEG", 60.0, 30.0, 89.0),
            fall_hold_s=_number(env, "ARGOS_FALL_HOLD_S", 2.0, 0.5, 30.0),
            stillness_s=_number(env, "ARGOS_STILLNESS_S", 60.0, 5.0, 3600.0),
            still_move=_number(env, "ARGOS_STILL_MOVE", 0.04, 0.005, 0.5),
            trigger_cooldown_s=_number(env, "ARGOS_TRIGGER_COOLDOWN_S", 30.0, 0.0, 3600.0),
            listen=_text(env, "ARGOS_LISTEN", "auto"),
            vosk_model=_path(env, "ARGOS_VOSK_MODEL", "models/vosk-model-small-en-us-0.15"),
            audio_in=_text(env, "ARGOS_AUDIO_IN", "auto"),
            audio_out=_text(env, "ARGOS_AUDIO_OUT", "auto"),
            help_min_conf=_number(env, "ARGOS_HELP_MIN_CONF", 0.6, 0.0, 1.0),
            elevenlabs_api_key=_text(env, "ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=_text(env, "ELEVENLABS_VOICE_ID"),
            elevenlabs_model=_text(env, "ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            gemini_api_key=_text(env, "GEMINI_API_KEY"),
            gemini_model=_text(env, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_timeout_s=_number(env, "ARGOS_GEMINI_TIMEOUT_S", 8.0, 1.0, 60.0),
            summary_timeout_s=_number(env, "ARGOS_SUMMARY_TIMEOUT_S", 10.0, 1.0, 60.0),
            snapshot_timeout_s=_number(env, "ARGOS_SNAPSHOT_TIMEOUT_S", 10.0, 1.0, 60.0),
            live_view=_text(env, "ARGOS_LIVE_VIEW") == "1",
            live_view_fps=_number(env, "LIVE_VIEW_FPS", 4.0, 0.5, 8.0),
            head_pat=_flag(env, "ARGOS_HEAD_PAT", True),
            head_pat_mm=_number(env, "ARGOS_HEAD_PAT_MM", 5.0, 1.0, 50.0),
            head_pat_deg=_number(env, "ARGOS_HEAD_PAT_DEG", 5.0, 1.0, 45.0),
            head_pat_hold_s=_number(env, "ARGOS_HEAD_PAT_HOLD_S", 0.5, 0.2, 3.0),
            wheels=_wheels(env),
            wheels_power=_number(env, "ARGOS_WHEELS_POWER", LOWEST_POWER, 0.05, MAX_POWER),
            wheels_turn_power=_number(env, "ARGOS_WHEELS_TURN_POWER", LOWEST_POWER, 0.05,
                                      MAX_POWER),
            wheels_invert_left=_flag(env, "ARGOS_WHEELS_INVERT_LEFT", False),
            wheels_invert_right=_flag(env, "ARGOS_WHEELS_INVERT_RIGHT", False),
            approach_max_s=_number(env, "ARGOS_APPROACH_MAX_S", 6.0, 1.0, 15.0),
            approach_rest_s=_number(env, "ARGOS_APPROACH_REST_S", 300.0, 30.0, 86400.0),
            call_agent=_text(env, "ARGOS_CALL_AGENT") == "1",
        )

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Every setting name this program reads, in the order it reads them."""
        recorder = _NameRecorder()
        cls.from_env(recorder)
        return tuple(recorder.read)

    def describe(self) -> list[str]:
        """Lines for the start-up log. Says what is on, never a key or a contact value."""
        escalation = (
            "escalation: the call agent places the call and writes its events "
            "(ARGOS_CALL_AGENT=1); the brain records none of them"
            if self.call_agent else f"escalation: dry-run, contact label {self.contact_label!r}"
        )
        wheels = {"on": "on (they arm only when a keyboard is attached)",
                  "fake": "pretend (ARGOS_WHEELS=fake): nothing moves",
                  "off": "off"}[self.wheels]
        return [
            f"backend: {'on' if self.backend_configured else 'off (no SUPABASE settings)'}",
            escalation,
            f"check timeout: {self.check_timeout_s:g} s",
            f"sensor board: {self.serial_port or 'none'}",
            f"robot: {self.robot_url or 'off'}",
            f"camera: {self.camera}; listening: {self.listen}",
            f"voice: {'ElevenLabs' if self.elevenlabs_api_key else 'no key'}; "
            f"Gemini: {self.gemini_model if self.gemini_api_key else 'no key'}",
            f"live view: {f'on at {self.live_view_fps:g} fps' if self.live_view else 'off'}",
            f"head press as a pat: {'on' if self.head_pat else 'off'}; "
            f"antenna press: {'on' if self.robot_antenna_pat else 'off'}",
            f"wheels: {wheels}",
        ]


class _NameRecorder(dict[str, str]):
    """A stand-in environment, empty, that remembers which names were asked for."""

    def __init__(self) -> None:
        super().__init__()
        self.read: list[str] = []

    def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
        if key not in self.read:
            self.read.append(key)
        return default
