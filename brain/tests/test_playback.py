"""Sound is played in a process of its own, which may die or hang without touching the brain.

On the real robot the sound card dropped off USB when the head was pressed, and PortAudio
aborted the whole brain while opening it. These tests stand in for that with real child
processes that abort, hang, or play.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from argos.brain import TriggerIn
from argos.machine import State
from argos.voice import PlaybackFailed, ProcessSpeaker, Voice
from tests.conftest import make_rig
from tests.test_hearing_voice import FakeTTS

PY = sys.executable
# The way PortAudio ended the brain: an abort (SIGABRT) once the sound has been sent.
ABORTS = [PY, "-c", "import os, sys; sys.stdin.buffer.read(); "
          "os.abort() if os.name != 'nt' else os._exit(134)"]
HANGS = [PY, "-c", "import time; time.sleep(60)"]
PLAYS = [PY, "-c", "import sys; data = sys.stdin.buffer.read(); sys.exit(0 if data else 5)"]


def test_a_playback_process_that_aborts_is_a_failed_line_not_a_dead_brain() -> None:
    with pytest.raises(PlaybackFailed, match="ended with"):
        ProcessSpeaker(command=ABORTS).play(b"\x00\x01" * 800, 16000)


def test_a_playback_process_that_hangs_is_stopped_in_time() -> None:
    started = time.monotonic()
    with pytest.raises(PlaybackFailed, match="not finished"):
        ProcessSpeaker(command=HANGS, start_s=0.5).play(b"\x00\x01" * 1600, 16000)
    assert time.monotonic() - started < 3.0


def test_a_playback_process_that_plays_is_a_spoken_line() -> None:
    ProcessSpeaker(command=PLAYS).play(b"\x00\x01" * 800, 16000)


def test_the_voice_carries_on_after_the_player_dies(tmp_path: Path) -> None:
    spoken: list[bool] = []
    voice = Voice(None, tmp_path, FakeTTS(), ProcessSpeaker(command=ABORTS),  # type: ignore[arg-type]
                  threaded=False)
    from argos.clock import FakeClock

    voice.clock = FakeClock()
    voice.say("ask", on_spoken=spoken.append)
    voice.say("stood_down", on_spoken=spoken.append)
    assert spoken == [False, False]


@pytest.mark.parametrize("command", [ABORTS, HANGS], ids=["dies", "hangs"])
def test_the_brain_keeps_running_and_records_spoken_false(tmp_path: Path,
                                                          command: list[str]) -> None:
    voice = Voice(None, tmp_path, FakeTTS(), ProcessSpeaker(command=command, start_s=0.5),
                  threaded=False)  # type: ignore[arg-type]
    rig = make_rig(voice=voice)
    voice.clock = rig.clock
    rig.brain.start()
    rig.brain.post(TriggerIn("manual"))
    rig.step()
    rig.step()
    asked = next(e for e in rig.store.tables["events"] if e["kind"] == "asked")
    assert asked["detail"]["spoken"] is False
    rig.run_for(10.5)
    assert rig.brain.state is State.ALERT  # the check went on and escalated as it should


def test_the_playback_module_refuses_no_sound() -> None:
    from argos.config import BRAIN_DIR

    done = subprocess.run([PY, "-m", "argos.playback", "--rate", "16000"], input=b"",
                          capture_output=True, cwd=BRAIN_DIR, timeout=60)
    assert done.returncode == 2


def test_the_brain_process_never_loads_the_audio_library_with_listening_off() -> None:
    """Nothing in the brain's own process may open the sound card: the speaker is a process
    of its own, and with ARGOS_LISTEN=off nothing listens."""
    from argos.config import BRAIN_DIR

    script = (
        "import sys\n"
        "from argos.clock import Clock\n"
        "from argos.config import Settings\n"
        "from argos.senses import _listener, _voice\n"
        "settings = Settings.from_env({'ARGOS_LISTEN': 'off'})\n"
        "voice = _voice(settings, Clock(), True)\n"
        "assert _listener(settings, Clock(), True) is None\n"
        "voice.stop()\n"
        "print('sounddevice' in sys.modules, '_sounddevice' in sys.modules)\n"
    )
    done = subprocess.run([PY, "-c", script], capture_output=True, text=True, cwd=BRAIN_DIR,
                          timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["False", "False"]


def test_the_speaker_command_picks_the_robot_card_in_its_own_process() -> None:
    speaker: Any = ProcessSpeaker("auto", robot=True)
    assert speaker.command[1:] == ["-m", "argos.playback", "--out", "auto", "--robot"]
    assert ProcessSpeaker("3", robot=False).command[-2:] == ["--out", "3"]


# --------------------------------------------------------------------------- the demo's start


@pytest.mark.skipif(os.name != "posix", reason="bash and signals: on the Pi")
def test_the_demo_start_restarts_after_a_crash_and_stops_on_a_clean_exit(tmp_path: Path) -> None:
    """tools/demo.sh: a brain that aborts is started again; one that exits cleanly (q, Ctrl+C)
    is not. Every start has the wheels and listening off, whatever the caller said."""
    from argos.config import BRAIN_DIR

    starts = tmp_path / "starts"
    fake = tmp_path / "python"
    fake.write_text("#!/usr/bin/env bash\n"
                    f'echo "$ARGOS_WHEELS $ARGOS_LISTEN $*" >> "{starts}"\n'
                    f'if [ "$(wc -l < "{starts}")" -lt 3 ]; then kill -ABRT $$; fi\n'
                    "exit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    env = {**os.environ, "ARGOS_DEMO_PYTHON": str(fake), "ARGOS_DEMO_WAIT_S": "0",
           "ARGOS_WHEELS": "1", "ARGOS_LISTEN": "auto"}
    done = subprocess.run(["bash", str(BRAIN_DIR / "tools" / "demo.sh"), "--log-level", "INFO"],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    assert starts.read_text().splitlines() == ["0 off -m argos --log-level INFO"] * 3
    assert done.stdout.count("exited unexpectedly (code 134") == 2
    assert "not starting it again" in done.stdout
