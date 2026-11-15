"""Settings, read once from the environment.

Only the names in the root `.env.example` and in `brain/.env.example` are read. Contact
details (`CONTACT_FACETIME_TO`, `CONTACT_EMAIL_TO`) are never read by this program: real
sending is not built, and a value that is never read cannot leak.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from argos import DEVICE_ID

log = logging.getLogger("argos.config")

BRAIN_DIR = Path(__file__).resolve().parent.parent


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
        log.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    if not low <= value <= high:
        clamped = min(high, max(low, value))
        log.warning("%s=%s is outside %s to %s; using %s", name, raw, low, high, clamped)
        return clamped
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _text(env, name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


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

    @property
    def backend_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def robot_url(self) -> str | None:
        if self.robot.lower() == "off":
            return None
        if self.robot.lower() in ("", "auto"):
            return "http://localhost:8000"
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
        )

    def describe(self) -> list[str]:
        """Lines for the start-up log. Says what is on, never a key or a contact value."""
        return [
            f"backend: {'on' if self.backend_configured else 'off (no SUPABASE settings)'}",
            f"escalation: dry-run, contact label {self.contact_label!r}",
            f"check timeout: {self.check_timeout_s:g} s",
            f"sensor board: {self.serial_port or 'none'}",
            f"robot: {self.robot_url or 'off'}",
            f"camera: {self.camera}; listening: {self.listen}",
            f"voice: {'ElevenLabs' if self.elevenlabs_api_key else 'no key'}; "
            f"Gemini: {self.gemini_model if self.gemini_api_key else 'no key'}",
            f"live view: {f'on at {self.live_view_fps:g} fps' if self.live_view else 'off'}",
        ]
