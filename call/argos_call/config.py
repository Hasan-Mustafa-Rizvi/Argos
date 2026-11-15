"""Settings, read once: from the environment, then from `call/.env.local`. A real environment
variable wins over the file.

The names shared with the other parts are those in the repo's root `.env.example`. The ones
only this part reads are in `call/.env.example`. Every key, secret and the contact's number is
handed to the redactor here, before anything can print it, and none of them appears in
`repr()` of the settings.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from argos_call import DEVICE_ID
from argos_call.redact import Redactor

log = logging.getLogger("argos_call.config")

CALL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = CALL_DIR / ".env.local"

# The two addresses Chert's own pages give for its API. The key is sent to these only.
CHERT_BASES = ("https://facetime.trychert.com/api", "https://app.trychert.com/api")

TEST_LIMIT_S = 60.0
CALL_LIMIT_S = 240.0
BUDGET_S = 30 * 60.0


def _text(env: Mapping[str, str | None], name: str, default: str = "") -> str:
    value = env.get(name)
    if value is None:
        return default
    value = value.strip().strip('"').strip("'").strip()
    return value or default


def _number(env: Mapping[str, str | None], name: str, default: float, low: float,
            high: float) -> float:
    raw = _text(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        log.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    return min(high, max(low, value))


def _path(env: Mapping[str, str | None], name: str, default: str) -> Path:
    path = Path(_text(env, name, default)).expanduser()
    return path if path.is_absolute() else CALL_DIR / path


@dataclass(frozen=True)
class Settings:
    device_id: str
    dry_run: bool
    contact_label: str
    # Backend
    supabase_url: str
    supabase_key: str = field(repr=False)
    # Chert
    chert_api_key: str = field(repr=False)
    chert_project_id: str = ""
    chert_line_id: str = ""
    chert_base: str = CHERT_BASES[0]
    contact_facetime_to: str = field(default="", repr=False)
    # LiveKit
    livekit_url: str = ""
    livekit_api_key: str = field(default="", repr=False)
    livekit_api_secret: str = field(default="", repr=False)
    # Voice and model
    elevenlabs_api_key: str = field(default="", repr=False)
    elevenlabs_voice_id: str = field(default="", repr=False)
    elevenlabs_model: str = "eleven_flash_v2_5"
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    # Local
    state_dir: Path = CALL_DIR / "var"
    poll_s: float = 1.5
    vosk_model: Path = CALL_DIR / "models" / "vosk-model-small-en-us-0.15"

    # ------------------------------------------------------------------ what is there

    @property
    def backend_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def chert_configured(self) -> bool:
        return bool(self.chert_api_key and self.chert_project_id and self.contact_facetime_to)

    @property
    def livekit_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def voice_configured(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def can_call_for_real(self) -> tuple[bool, str]:
        """Whether a real call may be placed, and if not, why. Rule 1 comes first."""
        if self.dry_run:
            return False, "dry-run (ARGOS_DRY_RUN is not 0)"
        if not self.chert_configured:
            return False, "no CHERT_API_KEY, CHERT_PROJECT_ID or CONTACT_FACETIME_TO"
        if not self.livekit_configured:
            return False, "no LIVEKIT_URL, LIVEKIT_API_KEY or LIVEKIT_API_SECRET"
        if not self.voice_configured:
            return False, "no ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID: a silent call is dropped"
        return True, ""

    def missing(self) -> list[str]:
        """One line per missing setting: its name and what still runs without it."""
        lines = []
        if not self.chert_api_key:
            lines.append("CHERT_API_KEY is empty: dry-run only. Make a project key with "
                         "facetime:read and facetime:write at https://app.trychert.com/developer")
        if not self.chert_project_id:
            lines.append("CHERT_PROJECT_ID is empty: dry-run only")
        if not self.contact_facetime_to:
            lines.append("CONTACT_FACETIME_TO is empty: dry-run only")
        for name, value in (("LIVEKIT_URL", self.livekit_url),
                            ("LIVEKIT_API_KEY", self.livekit_api_key),
                            ("LIVEKIT_API_SECRET", self.livekit_api_secret)):
            if not value:
                lines.append(f"{name} is empty: dry-run only")
        for name, value in (("ELEVENLABS_API_KEY", self.elevenlabs_api_key),
                            ("ELEVENLABS_VOICE_ID", self.elevenlabs_voice_id)):
            if not value:
                lines.append(f"{name} is empty: no real call (the agent could not speak)")
        if not self.gemini_api_key:
            lines.append("GEMINI_API_KEY is empty: the call still speaks, shows and takes an "
                         "acknowledgement; it cannot answer questions")
        if not self.supabase_url or not self.supabase_key:
            lines.append("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is empty: no escalations "
                         "are read and no events are written; the made-up escalation still runs")
        return lines

    def describe(self) -> list[str]:
        """Start-up lines. Says what is on, never a value."""
        mode = "DRY-RUN, nothing real is sent" if self.dry_run else "REAL: texts and calls go out"
        return [
            f"mode: {mode}",
            f"contact: {self.contact_label!r} (the number goes to Chert only)",
            f"backend: {'on' if self.backend_configured else 'off'}",
            f"chert: {'key set' if self.chert_api_key else 'no key'}, "
            f"line {'set' if self.chert_line_id else 'found at start'}, {self.chert_base}",
            f"livekit: {'set' if self.livekit_configured else 'not set'}",
            f"voice: {'ElevenLabs ' + self.elevenlabs_model if self.voice_configured else 'none'}",
            f"answers: {'Gemini ' + self.gemini_model if self.gemini_configured else 'off'}",
            f"state files: {self.state_dir}",
        ]


def read_env(environ: Mapping[str, str] | None = None,
             env_file: Path | None = ENV_FILE) -> dict[str, str | None]:
    """The file's values, overlaid by the real environment."""
    merged: dict[str, str | None] = {}
    if env_file is not None and env_file.exists():
        merged.update(dotenv_values(env_file))
    merged.update(os.environ if environ is None else environ)
    return merged


def from_env(env: Mapping[str, str | None], redactor: Redactor | None = None) -> Settings:
    base = _text(env, "CHERT_API_BASE", CHERT_BASES[0]).rstrip("/")
    if base not in CHERT_BASES:
        log.warning("CHERT_API_BASE is not one of Chert's own addresses; using %s",
                    CHERT_BASES[0])
        base = CHERT_BASES[0]
    settings = Settings(
        device_id=DEVICE_ID,
        dry_run=_text(env, "ARGOS_DRY_RUN") != "0",
        contact_label=_text(env, "CONTACT_LABEL", "Family"),
        supabase_url=_text(env, "SUPABASE_URL").rstrip("/"),
        supabase_key=_text(env, "SUPABASE_SERVICE_ROLE_KEY"),
        chert_api_key=_text(env, "CHERT_API_KEY"),
        chert_project_id=_text(env, "CHERT_PROJECT_ID"),
        chert_line_id=_text(env, "CHERT_LINE_ID"),
        chert_base=base,
        contact_facetime_to=_text(env, "CONTACT_FACETIME_TO"),
        livekit_url=_text(env, "LIVEKIT_URL").rstrip("/"),
        livekit_api_key=_text(env, "LIVEKIT_API_KEY"),
        livekit_api_secret=_text(env, "LIVEKIT_API_SECRET"),
        elevenlabs_api_key=_text(env, "ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_text(env, "ELEVENLABS_VOICE_ID"),
        elevenlabs_model=_text(env, "ELEVENLABS_MODEL", "eleven_flash_v2_5"),
        gemini_api_key=_text(env, "GEMINI_API_KEY"),
        gemini_model=_text(env, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
        state_dir=_path(env, "ARGOS_CALL_STATE_DIR", "var"),
        poll_s=_number(env, "ARGOS_CALL_POLL_S", 1.5, 0.5, 10.0),
        vosk_model=_path(env, "ARGOS_VOSK_MODEL", "models/vosk-model-small-en-us-0.15"),
    )
    if redactor is not None:
        register(settings, redactor)
    return settings


def register(settings: Settings, redactor: Redactor) -> None:
    redactor.add_phone(settings.contact_facetime_to)
    redactor.add_all([
        settings.supabase_key, settings.chert_api_key, settings.livekit_api_key,
        settings.livekit_api_secret, settings.elevenlabs_api_key, settings.elevenlabs_voice_id,
        settings.gemini_api_key,
    ])
