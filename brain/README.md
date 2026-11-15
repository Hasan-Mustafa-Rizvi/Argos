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
python -m argos --check     # try every part once and print one table; records nothing
python -m argos --wheel-test   # turn each wheel briefly, base lifted (ARGOS_WHEELS=1)
python -m argos --script    # play the story of contract/fixtures/demo_scenario.jsonl live
python -m argos --script --loop
```

On a new machine, run `--check` first: [FIRST_RUN.md](FIRST_RUN.md) is the sheet for the Pi.

Keys, in the terminal that started it (also over SSH, no Enter needed):

| Key | Does |
|---|---|
| `f` `h` `s` `m` | start a check: fall, call for help, stillness, manual |
| `y` | answer "I'm fine" |
| `p` | pat |
| `a` | acknowledge the alert (recorded as "Demo") |
| space or `x` | stop the wheels, at once; they stay off until the brain is started again |
| `q` | quit (the robot goes back to rest, the wheels stop) |
| `?` | show the keys |

The brain stops in order on `q`, Ctrl+C, a service stop (SIGTERM) and a dropped SSH session
(SIGHUP): the wheels first, then the robot rests and the records are flushed.

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

The full sequence, with the robot's software and the checks, is in
[FIRST_RUN.md](FIRST_RUN.md). The brain's own part:

```
sudo apt install -y git tmux libportaudio2 libgl1 libglib2.0-0   # sound; OpenCV's libraries
curl -LsSf https://astral.sh/uv/install.sh | sh && . "$HOME/.local/bin/env"
cd ~/Argos/brain                              # the repo, cloned at ~/Argos
uv venv --python 3.12 .venv                   # trixie's own Python is 3.13; uv brings 3.12
. .venv/bin/activate
uv pip install -r requirements.txt            # on Linux this brings gpiozero and lgpio too
python tools/fetch_models.py                  # the pose and speech models, into models/
cp .env.example .env
```

This user must be in the `audio`, `video`, `gpio` and `dialout` groups (`groups` shows them;
the first user of Raspberry Pi OS is). Under a user service the same groups apply.

### The robot's own software (Reachy Mini Lite)

The brain does not import the robot's Python package. It talks to the robot's daemon over
its HTTP API on `http://127.0.0.1:8000` (the daemon of a Lite listens there only). Install the
daemon in its own environment, following Pollen Robotics' guide (huggingface.co/docs/
reachy_mini, "Installation"):

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

Start the brain by hand and watch it before trusting a service (FIRST_RUN.md). `deploy/`
holds two user services, one for the daemon and one for the brain; how to install them is at
the top of `deploy/reachy-mini-daemon.service`. They assume the repo at `~/Argos`. A service
has no terminal, so its keys are off and the wheels never arm under it. When the keys or the
wheels are wanted, run `systemctl --user stop argos-brain` and start the brain by hand in an
SSH session (inside `tmux`, so it survives a dropped connection).

## Test

```
python -m pytest           # no key, camera, microphone, port, robot, GPIO or network needed
ruff check .
```

The wheel guard is tested as a real separate process with fake pins. Three tests that send
POSIX signals to it run on Linux only.

## Settings

Read from the environment, then from `brain/.env`. All are optional.

| Name | Default | What it does |
|---|---|---|
| `SUPABASE_URL` | none | The backend. With this and the key, records go to Supabase. |
| `SUPABASE_SERVICE_ROLE_KEY` | none | The backend's secret key (`sb_secret_...`, or the legacy service-role JWT). Brain only. |
| `CONTACT_LABEL` | `Family` | The contact's label in records, such as `Daughter`. Never a number or address. |
| `ARGOS_DRY_RUN` | dry-run | Always dry-run in this build. `0` is answered with a warning: real sending is not built. |
| `CHECK_TIMEOUT_S` | `10` | Seconds to wait for an answer after "Are you okay?" before escalating. |
| `ARGOS_CALL_AGENT` | off | `1`: the call agent (`call/`) runs and writes the call events. The brain then writes none of `call_placed`, `call_answered`, `call_failed`, `message_sent`, `email_sent`, and places nothing. |
| `SERIAL_PORT` | none | The sensor board: `COM5`, `/dev/ttyUSB0`, or `socket://127.0.0.1:7777` for the pretend board. Empty: no board. |
| `ARGOS_LIVE_VIEW` | off | `1` sends live view frames. Anything else is off. |
| `LIVE_VIEW_FPS` | `4` | Live view frames a second, at most 8. |
| `ARGOS_ROBOT` | `auto` | `auto` uses the daemon at `http://127.0.0.1:8000`; a URL uses that one; `off` means no robot. |
| `ARGOS_ROBOT_ANTENNA_PAT` | `1` | A press on an antenna during a check counts as a pat. |
| `ARGOS_HEAD_PAT` | `1` | A press on the head during a check counts as a pat. `0` turns it off; the antenna press stays. |
| `ARGOS_HEAD_PAT_MM` | `5` | How far a press must move the head from its resting position, in millimetres (1 to 50). Tune from `--check`. |
| `ARGOS_HEAD_PAT_DEG` | `5` | Or how far it must tilt it, in degrees (1 to 45). |
| `ARGOS_HEAD_PAT_HOLD_S` | `0.5` | How long a press must be held to count (0.2 to 3). A knock is shorter. |
| `ARGOS_WHEELS` | off | `1`: the real wheels (contract section 2). They arm only with a keyboard attached, never under a service or in a scripted run. `fake`: pretend wheels that move nothing and log each burst, for a laptop. Anything else: off, and no pin is touched. |
| `ARGOS_APPROACH_MAX_S` | `6` | An approach ends this long after it began, however far it got (1 to 15). |
| `ARGOS_APPROACH_REST_S` | `300` | No approach within this long of the end of the last one (30 to 86400). |
| `ARGOS_WHEELS_POWER` | `0.20` | Power for a burst forward, as a share of full (0.05 to 0.60). Never above 0.60, whatever is set. Find it with `--wheel-test`. |
| `ARGOS_WHEELS_TURN_POWER` | `0.20` | Power for a turn burst (same limits). Turning scrubs, so it usually needs more. |
| `ARGOS_WHEELS_INVERT_LEFT`, `ARGOS_WHEELS_INVERT_RIGHT` | off | `1` flips that side's forward, when its motor wires are the other way round. |
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
- `argos/body/`: the robot (`reachy.py`, poses in `poses.py`, the head press in
  `press.py`), the sensor board (`serial_link.py`), the wheels (`wheels.py`, with the guard
  process in `guard.py` and its client in `guard_client.py`), and the hub that drives any mix
  of them.
- `argos/approach.py`: during a check, turning toward the person and coming a little closer.
- `argos/check.py`: `--check` and `--wheel-test`.
- `argos/senses/`: camera, pose-based fall and stillness, listening. `argos/voice.py`,
  `argos/gemini.py`, `argos/snapshot.py`, `argos/liveview.py`.
- `tools/pretend_board.py`: pretends to be the sensor board on a TCP port.

## The wheels

Four fixed wheels, tank steering, two DC motors a side through one L298N on the Pi's pins
(contract section 2). The rules, and where each is kept:

- Off unless `ARGOS_WHEELS=1`. Off means no pin is claimed or touched and the pin library is
  never loaded. On, they still arm only when the brain runs in a terminal (so the stop key is
  at hand), never under a service and never in a scripted run (`__main__.py`).
- The pins belong to a small separate process, the guard (`body/guard.py`). On a Pi 5 a pin
  keeps its last level when the program that set it dies, so the brain never touches a pin:
  it sends the guard short bursts and a heartbeat. The guard stops the motors when a burst
  ends, when the heartbeat stops for 0.35 s, when the brain's pipe closes (the brain exited or
  was killed), and on SIGTERM, SIGHUP or SIGINT. It ends with all six pins driven low.
- A burst happens only in an approach for the check that is open, only toward a person seen
  in a frame captured after the body last moved and less than half a second old
  (`body/wheels.py`). Never in calm or alert. One approach per check; none on a check resumed
  after a restart, none in a scripted run, none within `ARGOS_APPROACH_REST_S` of the last.
- Power is capped at 0.60 of full in code, in the brain and again in the guard. A burst is at
  most 0.5 s. The motors run at most 1.2 s in one approach, a constant no setting raises. The
  furthest one approach could go: 1.2 s at 0.60 of about 2 m/s, about 1.4 m, on fresh cells and
  a hard floor. Nothing senses a stair or a table edge: that distance is the only protection.
- It stops at once when the check ends, on the stop key (space or `x`, straight to the wheels,
  latched until restart), and when the brain stops; and at the next look when the person is
  out of view or close. It never searches for a person.
- Ears: the listener is muted through each burst and half a second after, with quiet gaps of
  1.5 s between bursts. With the defaults the ears are shut for at most 3.2 s of a check's
  wait. Eyes: no frame taken while the body moves is used, and a camera move is not counted as
  the person moving.

## Privacy, in this program

- Nothing about what Argos saw is stored unless a check failed. A frame is held in memory from
  the trigger, dropped when the check stands down, and becomes the snapshot only after the
  incident is escalated. The recorder refuses a summary or a snapshot path on an incident it
  has not escalated.
- The live view is sent only with `ARGOS_LIVE_VIEW=1`, to the private broadcast topic, and is
  never written anywhere.
- Speech is matched against a fixed list of phrases; nothing else is ever turned into text.
- Keys and contact details never appear in records or logs. The contact's number and address
  are not read at all by this build. A setting that cannot be used is logged by name, never
  with its value.
- The cache holds only Argos's own spoken lines. The local log holds only what was recorded.
- `--check` records nothing and keeps nothing: one camera frame and a moment of sound are held
  in memory and dropped, and no setting's value is printed. With the live view on, it sends
  that one frame to the private live view topic, as the live view itself would.
- An approach of the wheels records nothing new: it is not an event.
