# Argos brain

The program that is Argos's brain. It decides what state Argos is in, records what happens
to the backend, moves the robot, sees, listens and speaks. It runs on a Raspberry Pi 5 with
the robot plugged in, and on a Windows laptop for development and as the fallback.

It runs with any part missing: no robot, no sensor board, no camera, no microphone, no
network, no keys. Each missing part is logged once and the brain carries on with what it has.
The keyboard always works.

## Run it

```
python -m argos             # the brain
python -m argos --script    # play the story of contract/fixtures/demo_scenario.jsonl live
python -m argos --script --loop
```

Keys, in the terminal that started it (also over SSH, no Enter needed):

| Key | Does |
|---|---|
| `f` `h` `s` `m` | start a check: fall, call for help, stillness, manual |
| `y` | answer "I'm fine" |
| `p` | pat |
| `a` | acknowledge the alert (recorded as "Demo") |
| `q` | quit (the robot goes back to rest) |
| `?` | show the keys |

## Install

Python 3.12 on both machines. Every library installs from a ready-made wheel; no compiler.

### Windows laptop

```
cd brain
uv venv --python 3.12 .venv          # or: py -3.12 -m venv .venv
.venv\Scripts\activate
uv pip install -r requirements-dev.txt
python tools/fetch_models.py         # pose model and speech model, into brain/models/
copy .env.example .env               # then fill in what you have
```

### Raspberry Pi 5 (Raspberry Pi OS 64-bit, "trixie")

```
sudo apt install -y libportaudio2 libgl1      # sound devices; OpenCV's GL library
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/ARGOS/brain
uv venv --python 3.12 .venv                   # trixie's own Python is 3.13; uv brings 3.12
. .venv/bin/activate
uv pip install -r requirements.txt
python tools/fetch_models.py
cp .env.example .env
```

### The robot's own software (Reachy Mini Lite)

The brain does not import the robot's Python package. It talks to the robot's daemon over
its HTTP API on `http://localhost:8000`. Install the daemon in its own environment, following
Pollen Robotics' guide (huggingface.co/docs/reachy_mini, "Installation"):

```
uv venv ~/reachy/.venv --python 3.12
uv pip install --python ~/reachy/.venv/bin/python "reachy-mini"
```

On Linux the robot's package builds PyGObject from source, so Pollen's guide has you install
build packages first (`libgirepository1.0-dev`, `libcairo2-dev`, the GStreamer packages) and
the USB rules for the robot (the `99-reachy-mini.rules` file and the `dialout` group). That
compiler need belongs to the robot's software, not to the brain. Start the daemon with
`--no-media`, so the camera and the audio card are left to the brain:

```
~/reachy/.venv/bin/reachy-mini-daemon --no-media --headless
```

On Windows the same daemon installs from wheels. To try the brain with no robot at all:
`reachy-mini-daemon --mockup-sim --no-media --headless` gives a robot that accepts every move
and reports its joints, with no physics, camera or sound.

### Start at boot on the Pi

`deploy/` holds two user services, one for the daemon and one for the brain. How to install
them is at the top of `deploy/reachy-mini-daemon.service`. A service has no terminal, so its
keys are off; when the keys are wanted, run `systemctl --user stop argos-brain` and start the
brain by hand in an SSH session (inside `tmux`, so it survives a dropped connection).

## Test

```
python -m pytest           # no key, camera, microphone, port, robot or network needed
ruff check .
```

## Settings

Read from the environment, then from `brain/.env`. All are optional.

| Name | Default | What it does |
|---|---|---|
| `SUPABASE_URL` | none | The backend. With this and the key, records go to Supabase. |
| `SUPABASE_SERVICE_ROLE_KEY` | none | The backend's secret key (`sb_secret_...`, or the legacy service-role JWT). Brain only. |
| `CONTACT_LABEL` | `Family` | The contact's label in records, such as `Daughter`. Never a number or address. |
| `ARGOS_DRY_RUN` | dry-run | Always dry-run in this build. `0` is answered with a warning: real sending is not built. |
| `CHECK_TIMEOUT_S` | `10` | Seconds to wait for an answer after "Are you okay?" before escalating. |
| `SERIAL_PORT` | none | The sensor board: `COM5`, `/dev/ttyUSB0`, or `socket://127.0.0.1:7777` for the pretend board. Empty: no board. |
| `ARGOS_LIVE_VIEW` | off | `1` sends live view frames. Anything else is off. |
| `LIVE_VIEW_FPS` | `4` | Live view frames a second, at most 8. |
| `ARGOS_ROBOT` | `auto` | `auto` uses the daemon at `http://localhost:8000`; a URL uses that one; `off` means no robot. |
| `ARGOS_ROBOT_ANTENNA_PAT` | `1` | A press on an antenna during a check counts as a pat. |
| `ARGOS_ACK_POLL_S` | `2` | While in alert, how often to look for the dashboard's acknowledgement. |
| `ARGOS_LOG_DIR` | `var/log` | The local record log (one JSON line per record, UTF-8). |
| `ARGOS_CACHE_DIR` | `var/cache` | The cached voice lines. |
| `ARGOS_CAMERA` | `auto` | `auto` (the robot's camera on Linux, else device 0), `off`, a device number, a path, or `name:<text>`. On Windows with the robot plugged in, set the robot camera's number (often `1`). |
| `ARGOS_CAMERA_WIDTH`, `ARGOS_CAMERA_HEIGHT` | `640`, `480` | Size asked of the camera. |
| `ARGOS_CAMERA_HFOV_DEG` | `70` | The camera's horizontal field of view, to turn the head toward the person. |
| `ARGOS_DETECT_FPS` | `8` | Frames a second given to the pose model. |
| `ARGOS_POSE_MODEL` | `models/pose_landmarker_lite.task` | The pose model file. |
| `ARGOS_PERSON_MIN_SCORE` | `0.5` | How visible a body must be to count as a person. |
| `ARGOS_FALL_ANGLE_DEG` | `60` | How far from upright the torso must be to count as lying. |
| `ARGOS_FALL_HOLD_S` | `2` | How long someone must be lying before it is a fall. |
| `ARGOS_STILLNESS_S` | `60` | Seconds without moving before a stillness check. |
| `ARGOS_STILL_MOVE` | `0.04` | Movement, as a share of body size, that counts as moving. |
| `ARGOS_TRIGGER_COOLDOWN_S` | `30` | After a check ends, the camera and microphone stay quiet this long. |
| `ARGOS_LISTEN` | `auto` | `off` turns listening off. |
| `ARGOS_VOSK_MODEL` | `models/vosk-model-small-en-us-0.15` | The speech model folder. |
| `ARGOS_AUDIO_IN`, `ARGOS_AUDIO_OUT` | `auto` | `auto` is the robot's audio card when the robot is in use, else the default device. Or a device number, or part of a device name. |
| `ARGOS_HELP_MIN_CONF` | `0.6` | How sure the recogniser must be of "help" to start a check. |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | none | The voice. Without them only cached lines are spoken. |
| `ELEVENLABS_MODEL` | `eleven_flash_v2_5` | The ElevenLabs model. |
| `GEMINI_API_KEY` | none | The Gemini check and summary. Without it, the summary is a fixed sentence. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | The Gemini model. |
| `ARGOS_GEMINI_TIMEOUT_S` | `8` | Time limit for the Gemini check. |
| `ARGOS_SUMMARY_TIMEOUT_S`, `ARGOS_SNAPSHOT_TIMEOUT_S` | `10`, `10` | Time limits for the summary and the snapshot after an escalation. One attempt each. |

## How it fits together

- `argos/machine.py`: the state machine of contract section 1. No I/O; time is passed in.
- `argos/brain.py`: one thread owns the machine. Everything else posts inputs to it.
- `argos/records.py`, `argos/writer.py`, `argos/store.py`: rows of contract section 3. Inserted
  once, then only changed columns, with a filter on the expected status, through an ordered
  queue that keeps writes during an outage and sends them when the backend is back.
- `argos/body/`: the robot (`reachy.py`, poses in `poses.py`), the sensor board
  (`serial_link.py`), and the hub that drives any mix of them.
- `argos/senses/`: camera, pose-based fall and stillness, listening. `argos/voice.py`,
  `argos/gemini.py`, `argos/snapshot.py`, `argos/liveview.py`.
- `tools/pretend_board.py`: pretends to be the sensor board on a TCP port.

## Privacy, in this program

- Nothing about what Argos saw is stored unless a check failed. A frame is held in memory from
  the trigger, dropped when the check stands down, and becomes the snapshot only after the
  incident is escalated. The recorder refuses a summary or a snapshot path on an incident it
  has not escalated.
- The live view is sent only with `ARGOS_LIVE_VIEW=1`, to the private broadcast topic, and is
  never written anywhere.
- Speech is matched against a fixed list of phrases; nothing else is ever turned into text.
- Keys and contact details never appear in records or logs. The contact's number and address
  are not read at all by this build.
- The cache holds only Argos's own spoken lines. The local log holds only what was recorded.
