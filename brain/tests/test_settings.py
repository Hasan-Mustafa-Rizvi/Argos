"""Settings: defaults, the dry-run rule, and the list of names in brain/.env.example."""

from __future__ import annotations

import re
from pathlib import Path

from argos.config import Settings

BRAIN = Path(__file__).resolve().parents[1]
ROOT = BRAIN.parent


def names_in(path: Path) -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", path.read_text(encoding="utf-8"), re.M))


def names_read() -> set[str]:
    source = (BRAIN / "argos" / "config.py").read_text(encoding="utf-8")
    return set(re.findall(r'env, "([A-Z][A-Z0-9_]*)"', source))


def test_env_example_lists_exactly_the_names_read() -> None:
    assert names_in(BRAIN / ".env.example") == names_read()


def test_env_example_has_no_values() -> None:
    for line in (BRAIN / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            assert re.fullmatch(r"[A-Z][A-Z0-9_]*=", line), line


def test_root_names_are_reused_and_contacts_are_not_read() -> None:
    root = names_in(ROOT / ".env.example")
    read = names_read()
    assert "CONTACT_FACETIME_TO" not in read and "CONTACT_EMAIL_TO" not in read
    assert {"SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ARGOS_DRY_RUN", "CHECK_TIMEOUT_S",
            "SERIAL_PORT", "ARGOS_LIVE_VIEW", "LIVE_VIEW_FPS"} <= root & read


def test_defaults_with_nothing_set() -> None:
    settings = Settings.from_env({})
    assert settings.dry_run is True and not settings.dry_run_off_requested
    assert settings.check_timeout_s == 10.0
    assert not settings.backend_configured
    assert settings.serial_port == ""
    assert settings.live_view is False
    assert settings.live_view_fps == 4.0
    assert settings.robot_url == "http://127.0.0.1:8000"  # the daemon binds 127.0.0.1 only
    assert settings.contact_label == "Family"


def test_values_are_checked() -> None:
    settings = Settings.from_env({"LIVE_VIEW_FPS": "30", "CHECK_TIMEOUT_S": "soon",
                                  "ARGOS_ROBOT": "off", "ARGOS_DRY_RUN": "0"})
    assert settings.live_view_fps == 8.0  # never more than 8
    assert settings.check_timeout_s == 10.0
    assert settings.robot_url is None
    assert settings.dry_run is True and settings.dry_run_off_requested
    describe = "\n".join(settings.describe())
    assert "dry-run" in describe


def test_describe_never_prints_a_key() -> None:
    settings = Settings.from_env({"SUPABASE_URL": "https://x.invalid",
                                  "SUPABASE_SERVICE_ROLE_KEY": "MARKER-KEY",
                                  "GEMINI_API_KEY": "MARKER-GEMINI",
                                  "ELEVENLABS_API_KEY": "MARKER-ELEVEN"})
    text = "\n".join(settings.describe())
    assert "MARKER" not in text
