# Hardware run: the brain's first time on the real robot

The log of the first run of `brain/` on the Raspberry Pi, the Reachy Mini Lite, its camera,
microphone and speaker, and the wheeled base. Written as it happens: if this session stops,
this file is where to pick up. Log headings are the laptop's local time (CST); times inside
the entries are the Pi's clock (MST), one hour behind the laptop, unless they say otherwise.

Task: `prompts/BRAIN_C_hardware_run.md`. Plan followed: `brain/FIRST_RUN.md` (now corrected).

## Where it stands (15 November, about 06:30 laptop time)

| Stage | State |
|---|---|
| 0. Questions to the owner | done |
| 1. The brain onto the Pi | done |
| 2. `--check` until honest | done: every row ok or off, except the microphone (hardware) |
| 3. One whole check by hand | done: press to stand down, no answer to escalate, dashboard acknowledgement, live view; no spoken "yes" (microphones dead) |
| 4. Repeatable | press: 10 of 10 in a row; escalations: all 6 went through (02:35, 02:44, 02:45, 02:50, 03:27, 03:39), but not as one run of five |
| 5. The whole chain | **dry-run only**, by the advisor's choice (4 AM): worked. The real call is for the morning |
| 6. The wheels | not started: the pull-down resistors are not fitted; the owner said not ready |

Left running for the morning: in tmux session `argos` on the Pi, window `daemon` (the
robot's daemon) and window `brain` (`ARGOS_CALL_AGENT=1 bash tools/demo.sh`, live view off).
The call agent is stopped.

## Report

### The Pi, and what was installed on it

- Raspberry Pi 5 Model B Rev 1.1, 4 cores, 7.9 GiB, Debian 13 (trixie), kernel
  6.18.60+rpt-rpi-2712, aarch64, glibc 2.41, system Python 3.13.5. Clock by NTP. Power
  5.16 V, never throttled; 37 to 46 °C. User `applepie` (already in audio, video, gpio,
  dialout); `sudo` needs a password, so the owner typed every `sudo` line.
- Installed by the owner (sudo): `tmux`, `libportaudio2`, and from Pollen's GStreamer page,
  step 1, the packages missing here: `libgstreamer-plugins-bad1.0-dev`,
  `libgstreamer-plugins-base1.0-dev`, `libgstreamer1.0-dev`, `libssl-dev`,
  `libgirepository1.0-dev`, `gstreamer1.0-nice`, `python3-gi-cairo`; the robot's USB rule
  `/etc/udev/rules.d/99-reachy-mini.rules`.
- Installed by me, no sudo: uv 0.13.8 in `~/.local/bin` (its installer); the repo cloned to
  `~/Argos` (at `9daaf15`, then fixes copied file by file); `~/Argos/brain/.venv` (Python
  3.12.16, `requirements.txt`, then `requirements-dev.txt` for pytest 9.2.0 and ruff 0.17.5);
  the two models; `brain/.env` from the template (mode 600; the owner typed the values);
  `~/reachy/.venv` with reachy-mini 1.14.0 (pycairo and PyGObject compiled on the Pi).
- Changed outside `~/Argos`: PipeWire's volume for the "Reachy Mini Audio" sink, 0.40 to
  1.00 (`wpctl set-volume`). `reachy-stream.service` (not ours; it held the camera and
  streamed it to the network on port 8080) was stopped by me at the owner's word and then
  disabled by Neel.
- One-off diagnostics, not in the repo: `~/Argos/brain/var/diag/` (`audio_test.py`,
  `mic_energy.py`, `press_watch.py`; `var/` is ignored by git).

### `--check`, first and last

Both are printed in full in the log below (03:05 and 03:55). First: 14 ok, 2 off, 1 warn,
3 FAIL (microphone, speaker not heard, Gemini HTTP 400). Last: 16 ok, 2 off, 1 FAIL
(microphone, hardware), 1 skip (camera sides, ok in the first run). Every fix after that (the
camera's MJPG, sound in its own process, the daemon's moves, the keyboard) came while the
brain was running and was proven in the brain itself; `--check` was not run again, because a
brain was running.

### Each stage, and the numbers

- **Stage 1.** The sheet was wrong on trixie's package name, on what `reachy-mini` 1.14 needs
  to build, and on `ARGOS_WHEELS` in `.env`; corrected. Another program held the camera.
- **Stage 2.** Faults: Gemini (a bug: the SDK sent our 8 s limit as a server deadline, and the
  API's minimum is 10 s), the speaker (mono went only to the left channel of a stereo-only
  card, and the card was at -23 dB), the microphone (dead: hardware). The first two fixed.
- **Stage 3.** A real fall seen by the camera (0.97) escalated, with the snapshot right way
  up and Gemini's summary on the dashboard; a dashboard acknowledgement reached the brain
  and it calmed. The head press, tuned: wobble at rest **0.06 to 0.08 mm / 0.07 to 0.09
  deg**; a firm press **7.1 mm / 2.5 deg** peak, **6.4 mm / 2.2 deg** held, at rest; **10.9
  mm** peak in the check pose; a gentle one 0.2 mm (does not count). **Settings kept at the
  defaults: `ARGOS_HEAD_PAT_MM=5`, `ARGOS_HEAD_PAT_DEG=5`, `ARGOS_HEAD_PAT_HOLD_S=0.5`.** A
  tap does not count. Head and camera sides: a positive head turn goes to the robot's left;
  the robot's left is the left of the picture. The live view: shown on the dashboard for the
  first time, the right way up; choppy at first (the camera gave 5 frames a second), fixed.
- **Stage 4.** 10 presses in a row, 10 stood down, 4 to 9 s after the check started. One of
  the ten knocked the audio board off USB for a second; the brain carried on.
- **Stage 5 (dry-run).** 03:39:07 a fall seen (0.75), 03:39:18 escalated ("the call agent
  places the call and records it"); the call agent (laptop 04:39:19): "escalated 1 s ago",
  the iMessage text, `message_sent` dry-run, "would call Son on FaceTime Video", its opening
  line, `call_placed` dry-run, both on the dashboard's timeline; 03:42:21 acknowledged by
  Hasan on the dashboard; the dog calmed (head pitch -1.0 deg, antennas -0.45 / 0.46 rad).
- **Other numbers.** One pose estimate on a 1920x1080 frame: **29 to 35 ms**. The brain's
  CPU: 16% of a core before the camera fix (5 frames a second), **51% of a core** after it
  with the live view at 8 a second. A check escalates 11 s after it starts. The Pi's clock is
  0.55 s ahead of the laptop's. The lowest wheel power: **not measured** (stage 6 not run).

### Every file changed in `brain/`

| File | Why |
|---|---|
| `argos/check.py` | Gemini deadline; Gemini's own reason in the row; settings row flags `ARGOS_WHEELS` in `.env` (FAIL for `1`) and names what came from the command line; wheel test hint |
| `argos/gemini.py` | `sdk_timeout_ms`: at least the API's 10 s minimum; the brain's own limits unchanged |
| `argos/voice.py` | `spread` (mono to both channels); `ProcessSpeaker` and `PlaybackFailed` (each line in its own process, time-limited); every failed line logged |
| `argos/playback.py` | new: plays one line and exits |
| `argos/senses/__init__.py` | the brain uses `ProcessSpeaker`; no device lookup in its own process |
| `argos/senses/camera.py` | MJPG on Linux; grab every frame, decode at most 12 a second |
| `argos/body/reachy.py` | stop a running move before a new one (the daemon dropped 1 move in 4); stops on their own connection; one retry on a dropped connection |
| `argos/keyboard.py` | terminal escape sequences dropped whole (an arrow key was an acknowledgement) |
| `tools/demo.sh` | new: the demo's start (wheels and listening off; started again after a crash) |
| `tests/test_check.py`, `tests/test_hearing_voice.py`, `tests/test_gemini_snapshot_live.py`, `tests/test_robot.py`, `tests/test_bodies_and_startup.py`, `tests/test_playback.py` (new) | tests for each of the above |
| `tests/test_wheels.py` | the guard's kill test accepts either correct exit reason (it failed the first time it ran on Linux; the motors did stop) |
| `FIRST_RUN.md`, `README.md`, `.env.example` | corrected from what the robot showed |
| `HARDWARE_RUN.md` | new: this file |

The Pi has the same files: see the last log entry for the hash comparison of every file in
`brain/`.

### Tests and lint

See the last log entry for the final counts on both machines.

### What still has not been seen

- **A real text and FaceTime call** (stage 5 was dry-run by choice; the real one is for the
  morning).
- **The microphones**: dead in hardware. No spoken "yes", no "help me" trigger, ever.
- **The wheels**: nothing of stage 6. The guard has never held real pins; the pins at boot,
  the lowest power, which way each side turns, and an approach are all unknown.
- **The live view at 8 frames a second** with the camera fix: on and sending, but the
  advisor's verdict on smoothness and delay was not given. Never seen on the venue's network.
- **The stillness trigger** (60 s without moving): not tried.
- **The camera's field of view**: not measured; `ARGOS_CAMERA_HFOV_DEG` is still the assumed
  70, which only sets how far the head turns toward a person.
- **`--check` after the last fixes**: not run (a brain was running).
- **The audio board's fault**: the microphones are dead, and pressing or moving the head
  knocked it off USB three times. Someone should open the head after the demo.

### Things the advisor should decide

- **A crash can lose the records of the last moments**, and a restarted brain then asks an
  already-answered check again; unanswered, it escalates (seen: an incident answered at
  03:08 escalated at 03:27). Asking again is the brain's rule for an open check, so it was
  left as it is. Sound can no longer crash the brain; with the call agent in real mode, a
  restart that asks again needs a press, or it calls.
- **The laptop's clock is not synchronised** (Windows: "Local CMOS Clock"). 0.55 s off now;
  sync it before the real call.
- **`--check` still opens the sound card itself**: it can still be aborted by the card
  dropping. It is a one-off run, so it was left.
- The robot's daemon sends telemetry to Pollen ("Telemetry sent: daemon_started") and
  announces itself on the network by mDNS. Not ours to change.

## The demo sheet

On the day, with the robot plugged into the Pi and switched on, the Pi on its own supply,
and **the motor battery off** (the wheels are not part of this demo).

### Start, in order

1. **Attach**, from the owner's laptop, and keep this window in front of you:

   ```
   ssh -t applepie@10.88.250.85 tmux attach -t argos
   ```

   If the Pi was rebooted and there is no session: `ssh applepie@10.88.250.85`, then
   `tmux new -s argos`, `Ctrl+b c` for a second window. `Ctrl+b 1` / `Ctrl+b 2` switch.

2. **Nothing else running.** If the brain from the night is still running in window 2,
   press `q` there and wait for "not starting it again". Then:

   ```
   pgrep -af "[p]ython -m argos"; fuser -v /dev/video0; ss -ltn | grep :8000
   ```

   The first two must print nothing. The last prints one line if the daemon (step 3) is
   still up from the night, which is fine.

3. **The robot's daemon**, in window 1, if it is not already running. Tell the person at the
   robot: the head moves.

   ```
   ~/reachy/.venv/bin/reachy-mini-daemon --no-media --headless
   ```

   Healthy: "Daemon started successfully", "Uvicorn running on http://127.0.0.1:8000", and
   the head does its wake-up move.

4. **The brain**, in window 2 (stopped in step 2). Tell the person at the robot: the head
   moves.

   ```
   cd ~/Argos/brain
   ARGOS_LIVE_VIEW=1 LIVE_VIEW_FPS=8 ARGOS_CALL_AGENT=1 bash tools/demo.sh
   ```

   Healthy start, in this order, with no other warning:

   ```
   argos: wheels: off (ARGOS_WHEELS is not 1): no pin is touched
   argos.senses: listening: off (ARGOS_LISTEN=off)
   argos.senses: speaker: each line plays in its own process (the robot's sound card)
   argos.brain: backend: on
   argos.brain: escalation: the call agent places the call and writes its events (ARGOS_CALL_AGENT=1)
   argos.brain: check timeout: 10 s
   argos.brain: live view: on at 8 fps
   argos.brain: head press as a pat: on; antenna press: on
   argos.brain: wheels: off
   argos.robot: robot attached at http://127.0.0.1:8000 (daemon 1.14.0)
   argos.liveview: live view on: 8.0 frames a second to the private topic
   argos.camera: camera '/dev/video0' open
   ```

   If it says "escalated in an earlier run ... starting in alert" or "still checking ...
   asking again", an old incident is open: acknowledge it on the dashboard, or answer the
   question with a press.

5. **The laptop's clock**: Windows Settings, Time & language, Date & time, "Sync now".

6. **The call agent**, on the laptop, from `call/`, as `call/README.md` says for the demo
   (the owner starts it, with `ARGOS_DRY_RUN=0` only when the real call is wanted):

   ```
   python -m argos_call check
   python -m argos_call run --demo
   ```

   Healthy: its first line says `mode: REAL: texts and calls go out` (or dry-run, if that is
   what you want), then "watching for escalations every 1.5 s", with no warning lines.

7. **The dashboard**, https://argos-is-furreal.health: the dog is online, and the live view
   shows the camera, the right way up.

### The check, in front of the judges

- **Start it**: lie down on the floor in the camera's view for 2 s (a `fall`), or press `m`
  in window 2.
- **"I'm fine"**: as soon as "Are you okay?" has finished, press the head **firmly** straight
  down and hold it about a second. It nods and stands down. Too soft or too late, and it
  escalates. A tap does nothing. There is no voice answer: the microphones are dead.
- **No answer**: touch nothing. About 10 s later it escalates: the antennas sway, the
  dashboard shows the alert, the call agent texts and FaceTimes the contact. Acknowledge by
  the contact's "I'm on my way", on the dashboard, or with `a` in window 2.

### When something goes wrong (each of these happened on the first night)

| What you see | What to do |
|---|---|
| The question is not heard | The brain logs "the line ... was not played". It happens when the audio board drops off USB (a press or a head move can do it); it is back within a second, and the next line plays. Carry on, and say the line yourself. If no line ever plays: `wpctl status`, then `wpctl set-volume <the Reachy Mini Audio sink> 1.0`. |
| The brain window shows "exited unexpectedly ... starting it again" | Nothing: it is back within 3 to 10 s. Then acknowledge or answer any old incident it picks up. The dashboard says Offline for those seconds. |
| "robot lost ... carrying on without it and retrying" | It retries every 10 s. If it keeps coming, look at window 1: if the daemon says error, `Ctrl+C` it and start it again (the head moves). |
| The daemon says `error` after the robot was switched off or unplugged | Always stop the daemon before that; now: `Ctrl+C`, start it again. |
| A check nobody wanted (someone lay down, or leaned over the robot) | Answer it with a press, or let it escalate and acknowledge. Keep people upright and a step back from the dog. |
| The live view is choppy or frozen | On a weak network, start the brain with `LIVE_VIEW_FPS=4` instead of 8. To check the camera's mode while the brain runs: `v4l2-ctl -d /dev/video0 --get-fmt-video --get-parm` must say MJPG at 60 fps. |
| The camera did not open | Another program holds it: `fuser -v /dev/video0`. |
| The press does not count | Press firmer and sooner, hold a full second. Not during the head's move. |
| The brain quit by itself | It was a terminal sequence taken as `q` (fixed). If it happens: start the brain again (step 4). |
| The phone does not ring | The call agent must say REAL; the brain must say "backend: on"; the laptop's and the Pi's clocks within 2 minutes (the call agent ignores older escalations). |
| The head press stands it down when nobody touched it | Never seen. Start the brain with `ARGOS_HEAD_PAT=0` in front of `bash tools/demo.sh`: a missed press is the safe mistake. |

### Stop

`q` in window 2 (the brain rests the head and stops; the script does not start it again),
then `Ctrl+C` in window 1 (the daemon puts the head to sleep).

## Log

### 02:23 — Before anything

- Read `AGENTS.md`, contract sections 1, 2 and 6, `FIRST_RUN.md`, `README.md`, `check.py`,
  `__main__.py`, and the demo section of `call/README.md`.
- Laptop: OpenSSH 10.2 is there, one SSH key, the brain's `.venv` exists.
- Found before touching the Pi (to fix as the stages reach them):
  - `FIRST_RUN.md` section 6, step 2, and the wheel test's own hint in `check.py`
    ("Set ARGOS_WHEELS=1 in brain/.env first") both tell you to put `ARGOS_WHEELS=1` in
    `.env`. It must never go there: once in the file it arms the wheels on every later start.
    A wheels run is started as `ARGOS_WHEELS=1 python -m argos ...`.
  - `FIRST_RUN.md` section 1 has `tmux new -s argos`; for this run the session is made
    detached (`tmux new -d -s argos`) and the owner attaches from his own window.
  - Section 5 (start at boot) is skipped today: the demo is started by hand.

### 02:30 — The owner's answers

- SSH: `applepie@10.88.250.85`, by key. Tested: `hostname` printed `applepie`, no prompt.
- The robot is plugged into the Pi by USB and switched on.
- The wheels are not on the base. The motors are wired to the L298N. **The pull-down
  resistors are not fitted**; the owner's practice instead is motor battery on last, off
  first, and it is off. **The wheels stage is not ready until the owner says so.** No
  `ARGOS_WHEELS=1` run of any kind (not even `--check`) until then: the task requires the
  resistors before any such run.
- The repo was not on the Pi; no `.env` values yet. The owner types them himself.

### 02:32 — What the Pi really is (read only)

| | |
|---|---|
| Board | Raspberry Pi 5 Model B Rev 1.1, 4 cores, 7.9 GiB RAM, 117 GB card (10% used) |
| OS | Debian GNU/Linux 13 (trixie), kernel 6.18.60+rpt-rpi-2712, `aarch64` |
| C library | glibc 2.41 (needs 2.34 or newer: fine) |
| Python | system 3.13.5; uv brings 3.12 (3.12.16) for the venvs |
| Groups | `applepie` is already in audio, video, gpio, dialout (no `usermod` needed) |
| USB | Reachy Mini Camera (38fb:1002), Reachy Mini Audio (38fb:1001), the motor board's serial (1a86:55d3, `/dev/ttyACM0`, `root:dialout rw`), behind a hub |
| Sound | card 2 "Reachy Mini Audio" for record and play; cards 0 and 1 are HDMI |
| Video | `/dev/video0`, `/dev/video1` (and the Pi's own codec nodes 19 to 35) |
| GPIO | `/dev/gpiochip0,4,10..13` present |
| Clock | NTP active, "System clock synchronized: yes". The Pi's zone is MST |
| Power | `throttled=0x0`, 37 °C, supply 5.16 V |
| Missing | `tmux`, `uv`, `libportaudio2` |
| Robot software | not installed; no daemon running; port 8000 free; no reachy/argos services |
| sudo | needs a password: every `sudo` step is typed by the owner in his own window |

Sheet corrections found here:
- On trixie, `libglib2.0-0` is `libglib2.0-0t64` (already installed). `git`, `libgl1`,
  `build-essential`, `pkg-config`, `libglib2.0-dev`, `libcairo2-dev` were already there.
- `reachy-mini` from ready-made packages only resolves to the old 1.3.1. The current 1.14.0
  needs `pycairo` 1.29.2 and `pygobject` 3.46.0 built from source. The brain reads
  `target_head_pose` and `no_media`, so the current daemon is wanted.
- Pollen's Linux list (their GStreamer page, step 1) is what lets those two build. Their
  steps 2 and 3 (Rust and the WebRTC plugin) are only for streaming media and are not needed
  with `--no-media`. Of their list, missing on this Pi: `libgstreamer-plugins-bad1.0-dev`,
  `libgstreamer-plugins-base1.0-dev`, `libgstreamer1.0-dev`, `libssl-dev`,
  `libgirepository1.0-dev`, `gstreamer1.0-nice`, `python3-gi-cairo`.
- The USB rule (`99-reachy-mini.rules`) was not installed. The serial port is already usable
  by the `dialout` group.

### 02:36 — Clone and compare

- uv 0.13.8 installed by the sheet's installer into `~/.local/bin` (Pollen's notice of
  October 2026 asks for uv 0.13.4 or newer: fine).
- `git clone` of the public repo into `~/Argos`: at `9daaf15`, the same commit as the laptop.
- SHA-256 of every file in `brain/`, laptop against Pi: all 62 tracked files identical. Only
  this file (`HARDWARE_RUN.md`, new) is not on the Pi yet; it is copied at the end.
- `~/reachy/.venv` made with Python 3.12.16 (empty so far).
- Started on the Pi: the brain's venv, `requirements.txt`, the models, and `brain/.env`
  copied from the template with mode 600 (not opened).

### 02:40 — The brain's install on the Pi: done

- `uv pip install -r requirements.txt` took 59 s, every package from a ready-made wheel,
  including the two GPIO ones: gpiozero 2.0.1, lgpio 0.2.2.0. Also mediapipe 1.2.3,
  numpy 2.5.4, vosk 0.3.45, sounddevice 0.5.6, google-genai 3.3.0, httpx 0.28.1.
- `tools/fetch_models.py`: `pose_landmarker_lite.task` (5.6 MB) and
  `vosk-model-small-en-us-0.15` (40 MB zip, unpacked).
- `brain/.env` made from the template, mode 600. Told the owner he can type his values in.
- Waiting on the owner's sudo block (tmux, libportaudio2, Pollen's build packages, the USB
  rule) before installing `reachy-mini`.

### 02:45 — The robot's software

- The owner ran the sudo block (no errors) and the robot's USB was replugged. The USB rule
  took: the motor board's and the audio card's USB nodes are now `crw-rw-rw- root dialout`.
- `uv pip install --python ~/reachy/.venv/bin/python reachy-mini`: 28 s. reachy-mini 1.14.0,
  reachy-mini-motor-controller 1.5.6, reachy-mini-rust-kinematics 1.0.3, pycairo 1.29.2 and
  pygobject 3.46.0 (both compiled on the Pi without trouble once the packages were in).
- The daemon's own `--help` (1.14.0): `--no-media` ("Disable all media (camera, audio,
  WebRTC)") and `--headless` exist, as the sheet says. Worth knowing:
  - `--wake-up-on-start` is the default: **the head moves when the daemon starts**, and
    `--goto-sleep-on-stop` is the default: it moves again when the daemon stops. Warn the
    person at the robot before either.
  - The HTTP API binds to 127.0.0.1 on a Lite unless `--fastapi-host` says otherwise.
  - Datasets are not preloaded by default; a background update check runs every 24 h
    (`--dataset-update-interval 0` turns it off).
  - Importing it prints two onnxruntime warnings about `/sys/class/drm/card0/1`: harmless.

### 02:47 — Another program holds the robot's camera

- `reachy-stream.service`, an enabled **user service that is not ours** ("Reachy Mini camera
  MJPEG stream on :8080", `~/.config/systemd/user/reachy-stream.service`, `Restart=on-failure`,
  `WantedBy=default.target`). Main process `/usr/bin/python3 /home/applepie/reachy_stream.py`,
  started 01:34 Pi time (it was not running at 01:26). It runs `ffmpeg` on the robot's camera
  (`/dev/video0`, MJPEG 1920x1080 at 30 fps) and listens on `0.0.0.0:8080`.
- While it runs the brain gets no camera. It also appears to stream the dog's camera to
  anyone on the network with no sign-in, which is at odds with contract section 6.
- Not touched; its file not read. Asked the owner.
- 02:52: the owner (and Neel) said stop it. `systemctl --user stop reachy-stream`: now
  inactive, still enabled (it comes back at the next boot or login). No `reachy_stream` or
  `ffmpeg` left, nobody holds `/dev/video0` or `/dev/video1`, nothing on 8080.
- 02:55: Neel disabled it himself. `systemctl --user is-enabled reachy-stream` now says
  `not-found` (the unit is gone from the user's units), so it will not come back after a
  reboot. Still nothing on the camera or on 8080.
- PipeWire's `wireplumber` holds the robot sound card's control device (`controlC2`); normal,
  to be seen in `--check`.

### 02:48 — tmux

- Session `argos` on the Pi, history 20000 lines. Window `daemon` (the start command typed,
  Enter not pressed) and window `brain` (in `~/Argos/brain`, venv active).
- The owner attaches with `ssh -t applepie@10.88.250.85 tmux attach -t argos`
  (`Ctrl+b 1` / `Ctrl+b 2` switch windows; `Ctrl+b d` detaches and leaves it running).
- Lesson: a command typed into a tmux window ahead of time picked up stray characters from
  the owner's terminal when he attached (its replies to tmux's queries), and the first start
  failed. Do not pre-type; clear the line (`Ctrl+U`) before typing.

### 03:00 — The daemon runs

- Started by the owner from the `daemon` window; the head did its wake-up motion. Log:
  "Daemon started successfully", "Uvicorn running on http://127.0.0.1:8000".
- `/api/daemon/status`: state running, version 1.14.0, `no_media: true`, motors enabled,
  control loop 49.8 Hz, no errors.
- Worth knowing: the daemon registers itself on the network by mDNS ("reachy_mini on port
  8000") and sends telemetry to Pollen ("Telemetry sent: daemon_started"). Not ours to change.

### 03:05 — `--check`, first run

Started as `ARGOS_WHEELS=0 python -m argos --check` in the `brain` window. The owner and Neel
answered: the head direction `l`, Neel on the robot's left, the speaker "not heard".

```
part            result  what was seen, and what to do
--------------  ------  -------------------------------------------------------------------------------
settings        ok      brain/.env found. 7 of the 50 settings are set: SUPABASE_URL,
                        SUPABASE_SERVICE_ROLE_KEY, CONTACT_LABEL, ELEVENLABS_API_KEY,
                        ELEVENLABS_VOICE_ID, GEMINI_API_KEY, ARGOS_WHEELS.
python          ok      Python 3.12.16 on Linux aarch64.
clock           ok      0.0 s ahead of a network time server. The system keeps its clock in step.
power           ok      Raspberry Pi 5 Model B Rev 1.1. The supply reads 5.16 V. No under-voltage or
                        throttling since it started.
another brain   ok      No other brain is running.
robot daemon    ok      Reachy Mini Lite, named 'reachy_mini', daemon 1.14.0. The motors were enabled;
                        they are on now, and the head nodded.
head at rest    ok      Over 2 s (38 readings) the head was at most 3.3 mm and 3.8 deg from the
                        commanded pose, and wobbled 0.06 mm and 0.07 deg around its own resting
                        difference. The antennas sat up to 0.00 rad from where they are held.
head press      warn    While pressed the head moved up to 0.2 mm and 0.4 deg from rest, and held at
                        least 0.2 mm and 0.3 deg for the hold time. With the current settings this
                        press does NOT count. The press is hardly bigger than the wobble.
                        -> Press a little firmer and run --check again; if it stays like this, rely on
                           the antenna press.
head direction  ok      A positive head turn goes to the robot's left, as the brain assumes.
pose model      ok      Found at models/pose_landmarker_lite.task, and it loads.
camera          ok      The robot's camera: a 1920x1080 picture. Nobody is in it. One pose estimate
                        takes 35 ms, so seeing at the brain's rate uses about 28% of one processor
                        core.
camera sides    ok      The robot's left is the left of the picture, as the brain assumes.
speech model    ok      Found at models/vosk-model-small-en-us-0.15, and it loads.
microphone      FAIL    Reachy Mini Audio: USB Audio (hw:2,0): heard -120 dBFS on average and -120 dBFS
                        at the loudest, over 1.5 s. That is silence.
                        -> It gives nothing: check it is not muted (alsamixer) and that it is the
                           robot's (ARGOS_AUDIO_IN).
ElevenLabs      ok      Spoke the question (0.9 s of audio); it is now kept in the voice cache.
speaker         FAIL    Reachy Mini Audio: USB Audio (hw:2,0): played the question. It was not heard.
                        -> Turn the volume up (alsamixer, the robot's card) and check ARGOS_AUDIO_OUT
                           names the robot's card.
backend         ok      Read this device's row with the secret key.
Gemini          FAIL    Gemini refused or failed: ClientError (HTTP 400).
                        -> Check the network and GEMINI_API_KEY.
live view       off     Off (ARGOS_LIVE_VIEW is not 1): no frames are sent.
wheels          off     Off (ARGOS_WHEELS is not 1): no pin is touched. When on, they use GPIO17 and
                        GPIO27 (left direction), GPIO22 and GPIO23 (right direction) as plain outputs;
                        GPIO12 (left power) and GPIO13 (right power) as PWM at 200 Hz.
14 ok, 2 off, 1 warn, 3 FAIL. Nothing was recorded, and no picture or sound was kept.
```

Also printed between rows: MediaPipe/LiteRT start-up lines and a `SyntaxWarning` from
google-genai 3.3.0 under Python 3.12. Noise, not faults.

What each row that is not ok turned out to be:

- **settings: `ARGOS_WHEELS` is set in `brain/.env`.** The `ARGOS_WHEELS=0` on the command line
  won, so nothing was armed. Told the owner to empty that line. `--check` should flag this
  itself (code fix below).
- **head press (warn):** a gentle press moved the head 0.2 mm and 0.4 deg: the motors hold
  it stiffly (the daemon sets P=300 on the six head motors). The setting's floor is 1 mm and
  1 deg, so a press must reach at least that. To retry with a firmer press; the antenna
  press is the fallback. The resting difference (3.3 mm, 3.8 deg) is steady and harmless:
  the wobble around it is 0.06 mm and 0.07 deg.
- **camera:** 1920x1080, not the 640x480 asked for: the camera offers only 1920x1080,
  3264x2448, 3840x2160 and 3840x2592 (MJPG or YUYV). 1920x1080 is its smallest. A pose
  estimate still takes 35 ms (28% of a core at 8 per second).
- **Gemini, HTTP 400: a bug in the brain.** Google's message: "Manually set deadline 8s is
  too short. Minimum allowed deadline is 10s." The SDK turns the client time limit
  (`ARGOS_GEMINI_TIMEOUT_S`, default 8) into a server deadline, and the API refuses one under
  10 s. The brain's own Gemini check during an incident would fail the same way every time.
  The key and the model are fine.
- **speaker, not heard: two causes.** (1) The card takes only stereo at 16 kHz in both
  directions (`/proc/asound/card2/stream0`); the brain plays mono, which lands on the left
  channel only. A test beep on the left only and on the right only was not heard; on both it
  was, but "really faint". (2) The card's playback level is 62% (-23 dB): that is PipeWire's
  stored volume (0.40) for this card. Capture level is 100%, switches on.
- **microphone, silence:** every sample is exactly zero, on both channels, in a quiet room
  and while Neel counted out loud; the same through PipeWire (`pw-cat --record`), and the
  same with the card playing at the same time. The chip (XMOS XVF3800, firmware 2.1.2, which
  meets Pollen's minimum of 2.1.0) reports its routing at the defaults (`AUDIO_MGR_OP_L` =
  (8, 0); `AUDIO_MGR_OP_R` = (8, 0), set by Pollen), microphone gain 90, 4 microphones, and
  **speech energy 0 on all four beams while Neel talked, with the direction stuck at exactly
  0.0**. Pollen's code writes nothing to the chip on start; on a Lite it records through
  PipeWire. So the microphones are not reaching the chip's processing: hardware, or a chip
  that started badly. Asked for a full power cycle of the robot.
- One-off test scripts, kept out of the repo: `~/Argos/brain/var/diag/audio_test.py` (levels
  per channel, beeps per channel) and `mic_energy.py` (reads the chip only). Nothing recorded
  was kept.

### 03:25 — Code fixes after the first `--check`

All on the laptop, tested, then copied to the Pi one file at a time (hashes identical):

| File | Change |
|---|---|
| `argos/voice.py` | `spread()`: a mono line is played on both channels of a card that has two. The robot's card is stereo only and its speaker was not heard from one channel. |
| `argos/gemini.py` | `sdk_timeout_ms()`: the SDK is given at least 10 s (`SERVER_MIN_DEADLINE_S`), the API's minimum deadline. The brain's own limits around each call (`call_with_timeout` with `ARGOS_GEMINI_TIMEOUT_S` 8 s, `ARGOS_SUMMARY_TIMEOUT_S` 10 s) are unchanged. |
| `argos/check.py` | The Gemini ping uses the same SDK deadline. The settings row is FAIL when `brain/.env` holds `ARGOS_WHEELS=1` (WARN for any other value there), with the fix; the value is never printed (`read_env_file`, `Hardware.env_file`). The Gemini row quotes Google's own reason, redacted. "The key is not valid" now needs "api key" in Google's message (it fired on any 400 mentioning "key"). The wheel test's hint no longer says to put `ARGOS_WHEELS=1` in `brain/.env`. |
| `tests/test_check.py` | The fakes never read a real `.env` (`env_file=dict`). New: the wheels-in-file row (two cases), `read_env_file`, the Gemini reason, the wheel test's hint. |
| `tests/test_hearing_voice.py` | New: a mono line reaches both channels. |
| `tests/test_gemini_snapshot_live.py` | New: the SDK deadline is at least 10 s, and longer limits pass through. |

Laptop: `pytest` 305 passed, 3 skipped (the Linux-only guard tests); `ruff check .` clean.

### 03:35 — The robot power-cycled; the microphones are still silent

- Neel switched the robot off and on and replugged its USB. The daemon was still running
  and went to `state: error` ("Motor communication error! Check connections and power
  supply"): **stop the daemon before power-cycling the robot**, and start it again after.
- After the power cycle: the card's capture is still exact zeros on both channels; the chip's
  speech energy is 0 on all beams; its direction stays exactly 0.0.
- Conclusion: the robot's microphones do not reach its XVF3800. Hardware; nothing in
  settings or code can fix it. Asked the owner whether a USB microphone is at hand
  (`ARGOS_AUDIO_IN` can name any input device) and whether someone can look at the head.

### 03:45 — The mute pin (advisor's ten-minute look)

- Seeed's wiki for the XVF3800: X0D30 is "Mute LED + mic mute control (high = mute)", X0D31
  "Amplifier enable (low = enabled)", X0D33 "WS2812 LED power control (high = on)". Seeed's
  `python_control/xvf_host.py`: `GPO_READ_VALUES` returns the pins "in order of Pin X0D11,
  X0D30, X0D31, X0D33 and X0D39". (Pollen's code has no mute handling at all.)
- Read on the robot (read only, after the power cycle): `GPO_READ_VALUES` = (0, 0, 0, 1, 0).
  **X0D30 = 0: not muted.** X0D31 = 0 (amplifier on, which matches the beep being heard),
  X0D33 = 1 (LED power on).
- Not the mute, so nothing was written. **The microphones are out for today.** The demo
  runs without hearing: a check starts from the keyboard (or the camera), and is answered
  by a press on the head or an antenna (or `y`).

### 03:55 — `--check`, second run (after the fixes and the robot's power cycle)

Firm head press by Neel; head turned left on a positive turn; speaker heard; camera sides
skipped (it was ok in the first run).

```
part            result  what was seen, and what to do
--------------  ------  -------------------------------------------------------------------------------
settings        ok      brain/.env found. 7 of the 50 settings are set: SUPABASE_URL,
                        SUPABASE_SERVICE_ROLE_KEY, CONTACT_LABEL, ELEVENLABS_API_KEY,
                        ELEVENLABS_VOICE_ID, GEMINI_API_KEY, ARGOS_WHEELS.
python          ok      Python 3.12.16 on Linux aarch64.
clock           ok      0.0 s behind a network time server. The system keeps its clock in step.
power           ok      Raspberry Pi 5 Model B Rev 1.1. The supply reads 5.17 V. No under-voltage or
                        throttling since it started.
another brain   ok      No other brain is running.
robot daemon    ok      Reachy Mini Lite, named 'reachy_mini', daemon 1.14.0. The motors were enabled;
                        they are on now, and the head nodded.
head at rest    ok      Over 2 s (38 readings) the head was at most 2.1 mm and 2.7 deg from the
                        commanded pose, and wobbled 0.08 mm and 0.09 deg around its own resting
                        difference. The antennas sat up to 0.00 rad from where they are held.
head press      ok      While pressed the head moved up to 7.1 mm and 2.5 deg from rest, and held at
                        least 6.4 mm and 2.2 deg for the hold time. With the current settings this
                        press counts.
head direction  ok      A positive head turn goes to the robot's left, as the brain assumes.
pose model      ok      Found at models/pose_landmarker_lite.task, and it loads.
camera          ok      The robot's camera: a 1920x1080 picture. A person is in the right third of it.
                        One pose estimate takes 29 ms, so seeing at the brain's rate uses about 23% of
                        one processor core.
camera sides    skip    Skipped.
speech model    ok      Found at models/vosk-model-small-en-us-0.15, and it loads.
microphone      FAIL    Reachy Mini Audio: USB Audio (hw:2,0): heard -92 dBFS on average and -90 dBFS
                        at the loudest, over 1.5 s. That is silence.
                        -> It gives nothing: check it is not muted (alsamixer) and that it is the
                           robot's (ARGOS_AUDIO_IN).
ElevenLabs      ok      Spoke the question (0.9 s of audio); it is already in the voice cache.
speaker         ok      Reachy Mini Audio: USB Audio (hw:2,0): played the question. It was heard.
backend         ok      Read this device's row with the secret key.
Gemini          ok      Answered one small request (text only; no picture was sent).
live view       off     Off (ARGOS_LIVE_VIEW is not 1): no frames are sent.
wheels          off     Off (ARGOS_WHEELS is not 1): no pin is touched. When on, they use GPIO17 and
                        GPIO27 (left direction), GPIO22 and GPIO23 (right direction) as plain outputs;
                        GPIO12 (left power) and GPIO13 (right power) as PWM at 200 Hz.
16 ok, 2 off, 1 FAIL, 1 skip. Nothing was recorded, and no picture or sound was kept.
```

- **Correction:** `ARGOS_WHEELS` in the settings list came from the `ARGOS_WHEELS=0` typed
  before `--check`, not from `brain/.env`; the first run's alarm was mine. The new file check
  found no value for it in the file. `check.py` now says which names came from the command
  line or the environment rather than the file (test added; 306 passed, ruff clean; copied,
  hashes identical).
- Head press measured: **at rest wobble 0.08 mm / 0.09 deg; a firm press 7.1 mm / 2.5 deg
  peak, 6.4 mm / 2.2 deg held.** Counts with the defaults (5 mm, 5 deg, 0.5 s). A gentle
  press (first run: 0.2 mm) does not: the press must be firm.
- Microphone: now ±1 bit (-90 dBFS) instead of exact zeros; still no sound.

### 04:00 — Stage 3, first start of the brain

- `ARGOS_WHEELS=0 python -m argos` in the `brain` window. Healthy start: "wheels: off",
  "backend: on", "escalation: dry-run, contact label 'Son'", "check timeout: 10 s", "robot
  attached ... (daemon 1.14.0)", "camera '/dev/video0' open", "head press as a pat: on;
  antenna press: on", "live view: off".
- **The camera started a check by itself** before anyone pressed `m`: 02:35:01 Pi time
  "fall seen (0.97)", check `fall`; nobody answered; 02:35:12 "escalated incident", "dry run:
  would call and email Son now; nothing is sent". A real escalated incident is now in the
  backend. No call agent on this laptop (checked). Asked what was in front of the camera.
- The owner: it moves and speaks, but **the volume is very low**. Raised the robot card's
  playback: PipeWire's volume for the "Reachy Mini Audio" sink 0.40 → 1.00 (`wpctl
  set-volume`), which puts the card's `PCM` control at 100% (0 dB) from 62% (-23 dB). PipeWire
  keeps the 1.00 across restarts.

### 04:10 — The fall was real, and the whole path worked

- The advisor: someone was lying on the floor in front of the robot. **On the dashboard the
  snapshot is the right way up, Gemini's summary matches it, and the detection, the summary,
  the snapshot and the timeline all arrived.** First time any of this ran for real.
- He acknowledged from the dashboard. Brain log: `02:42:11 acknowledged by Hasan` (Pi time;
  escalated at 02:35:12). The brain polls for it every 2 s.
- Afterwards the robot read steady over 3 s: head pitch -0.8 deg, yaw 0.2 deg (its resting
  offset), antennas -0.45 / 0.46 rad (the calm pose is -0.45 / 0.45). Calm.
- The summary and the snapshot log nothing when they work, so the brain's log shows only:
  fall seen, check, escalated, dry run, acknowledged.
- Times (Pi clock, MST): fall seen and check 02:35:01; escalated 02:35:12 (11 s: the 10 s
  wait plus the question); acknowledged 02:42:11.

### 04:15 — Stage 3: the head press as the answer

Brain log (Pi time), all started with `m`, each escalation acknowledged on the dashboard:

```
02:44:43 check b82ed3ae: manual
02:44:54 escalated incident b82ed3ae          (press too late and too soft)
02:45:08 acknowledged by Hasan
02:45:11 check 40fd6b21: manual
02:45:22 escalated incident 40fd6b21          (press too late and too soft)
02:45:28 acknowledged by Hasan
02:45:31 Gemini summary failed (ServerError); using the fixed sentence
02:45:57 check 17214102: manual
02:46:03 head pressed and held: taken as a pat
02:46:03 stood down by pat
```

- The owner: in the first two, Neel waited too long after the question and pressed too
  softly, so it escalated first. **A firm press held about a second, soon after the
  question ends, works.** The press can only count from about 1.5 s after the check starts
  (the head's 1 s move, then 0.5 s quiet, then rest learned) until the 10 s wait runs out.
- The Gemini `ServerError` (a 5xx from Google) on one summary was handled as designed: the
  fixed sentence went in its place. Not our fault, and not retried (one attempt by rule).
- Manual checks (`m`) are not held back by the 30 s quiet time; only the camera and the
  microphone are.
- A read-only watcher (`var/diag/press_watch.py`, tmux window `watch`) reads the head the
  way the brain does, 10 times a second, and prints for each still stretch the largest press
  and the largest press held for 0.5 s. A first glimpse in the check pose (z 8 mm, pitch -8
  deg, yaw 7 deg): a press peaking at 7.7 mm / 6.2 deg.

### 04:30 — Sheet 4b's tap test and three firm presses

```
02:50:48 check 80d431f7: manual      tap only
02:50:59 escalated incident 80d431f7   -> the tap did NOT count (right)
02:51:15 acknowledged by Hasan
02:51:25 check 3ea2ac52: manual      firm press
02:51:29 stood down by pat             4 s after the start
02:51:36 check dfa80faa: manual      firm press
02:51:39 stood down by pat             3 s
02:51:44 check 2a406cb8: manual      firm press
02:51:47 stood down by pat             3 s
```

- Tap: escalated, as it must. Firm presses: 3 of 3 (4 of 4 counting 02:46:03). Settings
  kept at the defaults: `ARGOS_HEAD_PAT_MM=5`, `ARGOS_HEAD_PAT_DEG=5`, `ARGOS_HEAD_PAT_HOLD_S=0.5`.
- The watcher caught one firm press in the check pose: **peak 10.9 mm / 5.1 deg** (about
  twice the 5 mm threshold). At rest the head reads 0.0 to 0.1 mm / 0.1 deg from rest. The
  other presses ended the still stretch before its 1.5 s settling allowance was over.

### 04:35 — The daemon was dropping one move in four (fixed)

- The watcher showed the head commanded to pitch -3 deg (the calm "sign of life" pose)
  through the whole tap check, instead of the check pose, and held in the alert pose for 7 s
  after the 02:51:15 acknowledgement instead of going to rest.
- The daemon's source (1.14.0, `daemon/backend/abstract.py`): a move is refused while
  another runs (`MoveBusyError`, logged as "Rejecting move request: another move is
  running"). `POST /api/move/goto` answers 200 anyway: the move runs as a background task.
  **Its log had 115 refusals out of 470 gotos.** Causes: a state change sent mid-move (a
  check during the sign of life, calm after an acknowledgement mid-sway), and each step of
  a sequence (the alert sway, the stand-down nod) sent at its predecessor's planned end, a
  few ms before the daemon's move really ends.
- Fix in `argos/body/reachy.py`: `ReachyClient.stop_moves()` (`GET /api/move/running`, then
  `POST /api/move/stop` for each; a refusal there is not an error), and `RobotBody._send()`
  calls it first when the last move may still run (`MOVE_GAP_S` = 0.25 s past its planned
  end). A move after a pause stops nothing.
- Tests (`tests/test_robot.py`): `FakeReachy.stop_moves`; a `BusyReachy` that drops
  overlapping moves like the real daemon; a check during the sign of life still looks up;
  every alert step and the calm after it arrive; a move after a pause stops nothing; the HTTP
  client's stop calls. **Both behaviour tests fail with the fix switched off** and pass with
  it. Laptop: 310 passed, 3 skipped; ruff clean. Copied; hashes identical. Refusals counted
  at 115 before the restart, to compare.

### 04:40 — Live view on, first time

- Quit the brain with `q` (02:56:08) and started it again as
  `ARGOS_WHEELS=0 ARGOS_LIVE_VIEW=1 python -m argos`, with the driver fix in.
- Log: "live view: on at 4 fps", "live view on: 4.0 frames a second to the private topic",
  camera open, no warnings after 40 s.
- With the live view on: the brain uses 16% of one core, the Pi is at 46.1 °C,
  `throttled=0x0`, load average 0.33.
- **The owner: the dog's camera shows on the dashboard, the right way up.** First time ever
  seen. **But a bit choppy.**
- The move fix on the real daemon: from the first `POST /api/move/stop` on, **11 gotos, 0
  refused** (11 refusals still visible in the log from before it). Small sample; stage 4 adds
  more. (Counting refusals over the whole tmux history was unreliable: older lines had
  scrolled out.)
- A slip: one command wrote a temporary copy of the daemon log to `/tmp` on the Pi (outside
  `~/Argos`); the next command deleted it.

### 04:50 — Why the live view is choppy: the camera gave 5 frames a second

- `v4l2-ctl --get-fmt-video --get-parm` while the brain held the camera: **YUYV
  (uncompressed) 1920x1080 at 5 fps.** The camera offers 1920x1080 at 60 fps in MJPG, but
  OpenCV keeps whatever format the camera was left in, and uncompressed 1080p is limited to
  5 fps over USB 2. So the live view sampled 4 frames a second out of 5 unevenly spaced ones
  (choppy), and the pose model, set to 8 a second, saw at most 5 (also why the brain used
  only 16% of a core).
- Fix in `argos/senses/camera.py`: on Linux, `open_capture` asks for MJPG (before the size);
  the camera loop `grab()`s every frame (cheap, so the newest is fresh) but `retrieve()`s
  (decodes) at most `MAX_DECODE_FPS` = 12 a second; a capture without grab and retrieve (the
  test fakes) is simply read.
- Tests (`tests/test_gemini_snapshot_live.py`): a 120 fps fake capture is grabbed every
  frame and decoded at most about 12 a second; on Linux the camera is asked for MJPG before
  its size. Laptop: 312 passed, 3 skipped; ruff clean. Copied; hashes identical.
- The running brain still has the old camera code until it is restarted.

### 05:00 — Restart for stage 5 (dry-run), with the camera fix

- The advisor's command, as one restart: `ARGOS_WHEELS=0 ARGOS_LIVE_VIEW=1 LIVE_VIEW_FPS=8
  ARGOS_CALL_AGENT=1 python -m argos`. Log: "escalation: the call agent places the call and
  writes its events (ARGOS_CALL_AGENT=1)", "live view: on at 8 fps".
- **That first start quit by itself** 9 s later (`03:04:15 quit`, no key shown), and logged
  "no microphone (Error querying device -1)": just after the old brain let go of the sound
  card, it was briefly missing from the audio library's list. Seconds later it was listed
  again (device 0, 2 in, 2 out, nobody holding it).
- Started again at the owner's word (03:05:28): healthy, no microphone warning, process 17848.
- **Camera now: MJPG 1920x1080 at 60 fps** (was YUYV at 5). The brain now uses **51% of one
  core** (was 16%: the pose model now really gets 8 frames a second, and the live view sends
  8). 45.5 °C, `throttled=0x0`, load average 1.05.

### 05:05 — Why it quit: terminal escape sequences were taken as keys (fixed)

- `keyboard.py` handed every character to the brain, lower-cased, including the characters
  of a terminal's escape sequences. So an up arrow (`ESC [ A`) was `a`, which acknowledges;
  Home (`ESC [ H`) was `h` and End (`ESC [ F`) `f`, both starting checks; F1 (`ESC O P`) was
  `p`, a pat that stands a check down; a mouse report (`ESC [ < ... M`) was `m`. Something of
  that kind sent the `q`. (The owner's terminal had already put stray characters into the
  daemon window once.)
- Fix: `Keyboard._feed()` drops escape sequences whole (CSI, SS3, and the string kinds DCS,
  OSC, SOS, PM, APC up to BEL or ESC \), keeping its place when a sequence is split across
  reads; `_idle()` lets a lone Escape key go after 0.1 s of nothing. Plain keys, and Caps
  Lock, work as before. Windows keeps its own handling.
- Tests (`tests/test_bodies_and_startup.py`): nine sequences that must not be keys, keys
  around a sequence, a sequence split across reads, a lone Escape. Laptop: 323 passed, 3
  skipped; ruff clean. Copied; hashes identical. It takes effect at the next start.

### 05:10 — The brain crashed: the sound card dropped off USB during a head press

Brain window (Pi time):

```
03:08:15 argos.vision: fall seen (0.69)            (someone leaning over the robot)
03:08:16 check ed25bf86: fall
03:08:22 head pressed and held: taken as a pat
03:08:22 stood down by pat
ALSA lib confmisc.c:165:(snd_config_get_card) Cannot get card index for 2
Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
python: src/hostapi/alsa/pa_linux_alsa.c:2178: PaAlsaStream_Initialize: Assertion
  `self->capture.nfds || self->playback.nfds' failed.
Aborted
```

- Kernel log: `03:08:21 usb 1-1.1: USB disconnect, device number 34`, `03:08:22 new high-speed
  USB device number 35` (Reachy Mini Audio, same serial). **Only the audio board** dropped: the
  camera (1-1.4) and the motor board (1-1.2) kept their numbers; the daemon stayed running.
- The brain went to play the stand-down line into a card that had vanished a second before;
  PortAudio's assertion aborted the whole process. Python cannot catch that.
- History since boot: the whole hub (1-1) dropped at 01:10, 01:22, 01:36 and 01:56 (replugs
  and the power cycle). The audio board alone: first at 03:08:21 (a head press), then again
  at about 03:27:31 (during the alert sway, nobody touching it). None of the six presses
  between 02:44 and 02:51 dropped it. **Pressing or moving the head can knock the audio
  board's USB link for about a second.** With the dead microphones: the audio board, or its
  cable in the head, is flaky. Hardware.

### 05:30 — Sound in a process of its own; listening off; a start that restarts itself

Per the advisor's three steps:

- **`argos/playback.py` (new):** plays one line from raw PCM on stdin and exits; picks the
  device itself each time (so a re-numbered card is found by name); exit 0 only if played.
- **`argos/voice.py`:** `ProcessSpeaker` runs it per line, with a limit of the line's length
  plus 5 s, killed after. Anything but a clean exit raises `PlaybackFailed`; the line counts
  as not spoken (`asked` gets `"spoken": false`) and each failure is logged. The sound goes
  in and errors come out on threads of their own, with the limit on `wait()`: on Windows
  `communicate()` writes the input with no time limit, and a hung player held the voice for
  60 s in the first version of the test.
- **`argos/senses/__init__.py`:** the brain uses `ProcessSpeaker`; it no longer looks up the
  device in its own process. With `ARGOS_LISTEN=off` nothing in the brain's process loads the
  audio library (tested in a fresh Python).
- **`tools/demo.sh` (new):** the demo's start. It forces `ARGOS_WHEELS=0` and
  `ARGOS_LISTEN=off`, starts the brain again after an unexpected exit (3 s, or 10 s if it died
  within 10 s of starting), and stops for good on a clean exit (`q`, Ctrl+C, a stop signal).
- **`tests/test_playback.py` (new):** a player that aborts, one that hangs (stopped in time),
  one that plays; the voice carries on after the player dies; the brain keeps running and
  records `spoken: false` with a dying and with a hanging player, and still escalates; the
  playback module refuses no sound; the brain's process never loads the audio library with
  listening off; and (Linux only) `demo.sh` restarts after two aborts, stops on a clean exit,
  and passes wheels 0 and listening off even when the caller set `ARGOS_WHEELS=1`.
- `pytest` and `ruff` installed into `~/Argos/brain/.venv` on the Pi (`requirements-dev.txt`),
  so the Linux-only tests run there. **First full run on the Pi: 335 passed, 1 failed:**
  `test_killing_the_brain_outright_stops_the_motors`. The guard did stop the motors and exit;
  it gave the reason "the brain went away" (its parent changed) where the test expected
  "... (its pipe closed)". Both are correct exits and either can come first. The test now
  accepts either; its safety checks (stopped within 1 s, not running at exit) are unchanged.
  Pi: 336 passed, then the guard tests 5 times in a row, 43 of 43 each time; ruff clean.

### 05:40 — First start through `tools/demo.sh`

- 03:26:52: listening off, live view off, escalation dry-run (no call agent for this test).
- **It resumed the stale check:** "incident ed25bf86 was still checking when the brain last
  stopped: asking again". That check had stood down at 03:08:22, but the brain aborted
  before its records reached the backend. Nobody answered the new question, and at
  **03:27:05 it escalated an already-answered incident from 19 minutes before** (dry-run).
  Asking again is the brain's rule for a check left open (a person may still need help), so
  it is left as it is: reported to the advisor. With sound out of the brain's process, the
  crash that loses those records should not recur. Demo sheet: if a restarted brain asks
  again, answer it with a press.
- **"robot lost (POST /api/move/goto: ReadError)" every ~10 s** (03:27:11, :22, 03:28:27,
  :44, :55): caused by the move fix. A stop for a move that ended between listing and
  stopping is refused by the daemon with HTTP 500 (`KeyError: Running move ... not found`),
  its server then closes the connection, and the next goto on that kept-alive connection
  fails. Fix in `reachy.py`: each stop goes on its own connection (`Connection: close`), and
  a call that hits a dropped connection is tried once more on a fresh one before the robot
  counts as lost (every call is safe to repeat). Three tests added. Laptop 335 passed, 4
  skipped; ruff clean; Pi: robot and playback tests 28 passed; hashes identical.

### 05:45 — A crash on purpose: the restart, and the open alert picked up

```
03:28:58 kill -ABRT 19763 (the brain, only that process)
tools/demo.sh: line 44: 19763 Aborted   ARGOS_WHEELS=0 ARGOS_LISTEN=off "$PYTHON" -m argos
03:28:58 the brain exited unexpectedly (code 134, start 1): starting it again in 3 s.
03:29:02 listening: off (ARGOS_LISTEN=off)
03:29:02 speaker: each line plays in its own process (the robot's sound card)
03:29:02 robot attached at http://127.0.0.1:8000 (daemon 1.14.0)
03:29:02 incident ed25bf86 escalated in an earlier run and is not acknowledged: starting in alert
```

- Back in 4 s, straight into alert, **no second escalation** (no new "escalated", no new
  "would call"): the call agent sees nothing new.
- With the connection fix: 30 s of alert sway, **no "robot lost"**; the daemon's last 600 log
  lines: 33 gotos, **0 refused**, 12 stops that came just after their move ended (harmless).

### 05:50 — Ten visitor presses: 10 of 10, one USB drop, no crash

```
03:32:47 ignored trigger: a alert incident is already open   (m before the acknowledgement)
03:33:08 acknowledged by Hasan                                (the stale ed25bf86, from the dashboard)
check  started   stood down by pat   seconds
  1    03:33:15  03:33:20            5
  2    03:33:24  03:33:28            4
  3    03:33:32  03:33:36            4
  4    03:33:40  03:33:49            9
  5    03:33:55  03:34:01            6    <- audio board off USB 03:33:59, back 03:34:00
  6    03:34:07  03:34:12            5
  7    03:34:16  03:34:20            4
  8    03:34:26  03:34:31            5
  9    03:34:36  03:34:40            4
 10    03:34:45  03:34:50            5
```

- **10 of 10 stood down by pat**, 4 to 9 s after `m` (median 5 s); none escalated.
- **The audio board dropped once in ten presses** (kernel: `03:33:59 usb 1-1.1: USB disconnect,
  device number 36`, back as 37 at 03:34:00). **The brain did not crash**: the same process
  (20052, started 03:29:02) ran throughout, and no line failed to play in this window (the
  question of check 5 had played before the drop; its stand-down line played after the card
  was back).
- So far: the audio board has dropped 3 times by itself (03:08:21, about 03:27:31, 03:33:59),
  each during a press or a head move, each back within a second.

### 06:00 — Stage 5 (dry-run only), set up

- The advisor: dry-run only tonight (4 AM; the contact is asleep). The real call is in the
  morning. He starts the call agent on his laptop in dry-run himself.
- Brain restarted with `q` (the script stopped: "not starting it again"), then
  `ARGOS_CALL_AGENT=1 bash tools/demo.sh` at 03:37:41, live view off (phone hotspot): listening
  off, speaker in its own process, "escalation: the call agent places the call and writes its
  events (ARGOS_CALL_AGENT=1)", backend on, robot attached, camera open. Process 21137.
- Clocks: **the Pi is 0.55 s ahead of the laptop** (three readings over SSH, round trip 0.3 s);
  the Pi keeps time by NTP ("System clock synchronized: yes"). **The laptop's clock is not
  synchronised** (`w32tm`: "Source: Local CMOS Clock", "Leap Indicator: 3 (not
  synchronized)"). Fine tonight (the call agent ignores escalations over 2 minutes old), but
  worth syncing before the demo: Windows Settings, Time & language, "Sync now".

### 06:15 — Stage 5 (dry-run): the whole chain worked

The alert came from the camera seeing someone on the floor, not from `m`. Brain (Pi time):

```
03:39:07 argos.vision: fall seen (0.75)
03:39:07 check 7b6e50ed: fall
03:39:18 escalated incident 7b6e50ed
03:39:18 escalated: the call agent places the call and records it (ARGOS_CALL_AGENT=1)
03:42:21 acknowledged by Hasan
```

- The call agent, on the advisor's laptop in dry-run, read out by him: at 04:39:19 laptop
  time (03:39:19 on the Pi's clock, give or take its 0.55 s lead) "incident 7b6e50ed escalated
  1 s ago (fall)"; the text it would send to Son over iMessage; event `message_sent` with
  `dry_run: true`; "would call Son on FaceTime Video"; its opening line; event `call_placed`
  with `dry_run: true`. Both events showed on the dashboard's timeline. The brain wrote none of
  the call events itself, as it must with the switch on.
- Acknowledged on the dashboard at 03:42:21; the dog calmed: three readings, head pitch -1.0
  deg, yaw 0.3 deg, z -0.8 mm, antennas -0.45 / 0.46 rad (the calm pose). The call agent was
  then stopped by the advisor. No audio board drop since 03:37.
- The brain was left running for the morning, as asked: `ARGOS_CALL_AGENT=1 bash
  tools/demo.sh`, live view off (processes 21134 and 21137).

### 06:30 — Final state

- `FIRST_RUN.md` corrected throughout (trixie's package name; Pollen's build packages and the
  USB rule; the daemon's head moves and stopping it before unplugging; other programs on the
  camera; `ARGOS_WHEELS` only on the command line, never in `.env`, and no wheels run before
  the resistors; `tools/demo.sh`; the press must be firm and soon; the volume; the dead
  microphones; the sound card dropping off USB; the measured answers of its section 7).
  `README.md` and `.env.example` likewise.
- The tmux window `watch` (the finished press watcher) closed. Session `argos` now has window
  1 `daemon` and window 2 `brain`, both running.
- **Tests: laptop 335 passed, 4 skipped (the Linux-only ones); Pi 339 passed, 0 skipped.
  `ruff check .`: no problems on either.** The guard's tests also ran 5 times in a row on the
  Pi, 43 of 43 each time.
- **Every file in `brain/`, 66 of them, compared by SHA-256 between the laptop and the Pi
  (leaving out `.venv`, `var`, `models`, `.env` and caches): identical.** This file was copied
  once more after this entry, and its hash checked again.
