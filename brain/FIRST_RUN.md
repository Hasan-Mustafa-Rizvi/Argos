# First run on the Raspberry Pi

For whoever sits at the Pi with the robot for the first time. Nothing in `brain/` has run on
the real Pi, robot, camera, microphone, speaker or wheels yet: everything was built and
tested against fakes on a Windows laptop. Expect things to be wrong. `python -m argos
--check` is what tells you which.

Work in order. Do the wheels last, with the base lifted off the floor.

## 0. Before you start

- The Pi 5 on its own supply (the official 27 W USB-C one). The motors must never draw from
  the Pi.
- The robot (Reachy Mini Lite) plugged into the Pi by USB and powered.
- For the wheels, later: see section 6 for what to fit first (two resistors and a switch).
- You reach the Pi over SSH, and run everything inside `tmux`, so a dropped connection does
  not stop anything: `tmux new -s argos` (and `tmux attach -t argos` to come back).

## 1. From a fresh Pi to a running brain

Raspberry Pi OS 64-bit ("trixie"), with SSH on. As the Pi's normal user:

```
sudo apt update
sudo apt install -y git tmux libportaudio2 libgl1 libglib2.0-0
groups                                  # must list audio, video, gpio and dialout
sudo usermod -aG audio,video,gpio,dialout "$USER"   # only if one is missing; then log out and in
curl -LsSf https://astral.sh/uv/install.sh | sh
. "$HOME/.local/bin/env"
git clone https://github.com/Hasan-Mustafa-Rizvi/Argos.git ~/Argos
cd ~/Argos/brain
uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install -r requirements.txt      # on the Pi this brings gpiozero 2.0.1 and lgpio 0.2.2.0
python tools/fetch_models.py            # the pose model and the speech model, from their makers
cp .env.example .env
nano .env                               # type in what the owner gave you; never paste keys in chat
```

The folder must be `~/Argos`: the service files use that path, and Linux paths are
case-sensitive.

The robot's own software, in its own environment (Pollen Robotics' guide,
huggingface.co/docs/reachy_mini, "Installation"):

```
uv venv ~/reachy/.venv --python 3.12
uv pip install --python ~/reachy/.venv/bin/python reachy-mini
```

If that stops while building PyGObject, install the build packages Pollen's guide lists for
Linux, then run it again. Install the robot's USB rule from the same guide
(`99-reachy-mini.rules`), then unplug and replug the robot.

Start the daemon by hand, in its own tmux window (Ctrl+b then c makes one):

```
~/reachy/.venv/bin/reachy-mini-daemon --no-media --headless
```

`--no-media` matters: without it the daemon holds the camera and the microphones, and the
brain gets neither. Wait until it says it is running, then in another window:

```
cd ~/Argos/brain && . .venv/bin/activate
python -m argos --check
```

Fix what it says (section 3), run it again, and repeat until it is all ok, warn, off or
missing for parts you do not have. Then run the brain by hand (section 4). Only after that,
the services (section 5).

## 2. What `--check` prints when all is well

It asks you a few things on the way, in the terminal: to press the head, which way the head
turned, to stand on the robot's left, and whether you heard the speaker. Answer them. Then it
prints one table, like this (your numbers will differ):

```
part            result  what was seen, and what to do
--------------  ------  ------------------------------------------------------------------
settings        ok      brain/.env found. 9 of the 50 settings are set: SUPABASE_URL,
                        SUPABASE_SERVICE_ROLE_KEY, CONTACT_LABEL, ELEVENLABS_API_KEY,
                        ELEVENLABS_VOICE_ID, GEMINI_API_KEY, ARGOS_LIVE_VIEW, ...
python          ok      Python 3.12.x on Linux aarch64.
clock           ok      0.1 s behind a network time server. The system keeps its clock in
                        step.
power           ok      Raspberry Pi 5 Model B Rev 1.1. The supply reads 5.10 V. No
                        under-voltage or throttling since it started.
another brain   ok      No other brain is running.
robot daemon    ok      Reachy Mini Lite, named 'reachy_mini', daemon 1.x. The motors were
                        enabled; they are on now, and the head nodded.
head at rest    ok      Over 2 s (37 readings) the head was at most 1.7 mm and 1.0 deg from
                        the commanded pose, and wobbled 0.30 mm and 0.20 deg around its own
                        resting difference. The antennas sat up to 0.01 rad from where they
                        are held.
head press      ok      While pressed the head moved up to 9.2 mm and 2.1 deg from rest, and
                        held at least 8.0 mm and 1.5 deg for the hold time. With the current
                        settings this press counts.
head direction  ok      A positive head turn goes to the robot's left, as the brain assumes.
pose model      ok      Found at models/pose_landmarker_lite.task, and it loads.
camera          ok      The robot's camera: a 640x480 picture. A person is in the middle third
                        of it. One pose estimate takes 45 ms, so seeing at the brain's rate
                        uses about 36% of one processor core.
camera sides    ok      The robot's left is the left of the picture, as the brain assumes.
speech model    ok      Found at models/vosk-model-small-en-us-0.15, and it loads.
microphone      ok      Reachy Mini Audio: heard -46 dBFS on average and -30 dBFS at the
                        loudest, over 1.5 s.
ElevenLabs      ok      Spoke the question (1.0 s of audio); it is now kept in the voice cache.
speaker         ok      Reachy Mini Audio: played the question. It was heard.
backend         ok      Read this device's row with the secret key.
Gemini          ok      Answered one small request (text only; no picture was sent).
live view       ok      On. Sent one camera frame to the private live view topic; nothing was
                        kept.
wheels          off     Off (ARGOS_WHEELS is not 1): no pin is touched. When on, they use
                        GPIO17 and GPIO27 (left direction), GPIO22 and GPIO23 (right
                        direction) as plain outputs; GPIO12 (left power) and GPIO13 (right
                        power) as PWM at 200 Hz.

20 ok, 1 off. Nothing was recorded, and no picture or sound was kept.
```

It writes no record, keeps no picture and no sound, and prints no setting's value (only
names). The one file it may leave is the spoken question in the voice cache, which the brain
keeps anyway. It moves the robot's head a little (a nod, and one turn if you say so). It never
turns a wheel: that is `--wheel-test`, below.

## 3. Each row, when it is not ok

Every row that is not ok says what to do in its own line, after `->`. The usual causes:

| Row | When it is not ok |
|---|---|
| settings | `brain/.env` missing: `cp .env.example .env`. "Could not use": that setting must be a number in its range (README, Settings). |
| python | Not 3.12: make the venv with `uv venv --python 3.12 .venv`. |
| clock | More than a few seconds off: `sudo timedatectl set-ntp true`, wait a minute. A Pi has no clock battery, so it starts with an old time until the network corrects it. |
| power | Under-voltage: the wrong supply, or something drawing from the Pi's 5 V. Use the official 27 W supply; the motors have their own battery. Throttled: add a heatsink or fan. |
| another brain | The service or another terminal is running one: `systemctl --user stop argos-brain`, or `q` in that terminal. Two brains fight over the camera and the records. |
| robot daemon | No answer: start the daemon (section 1) and wait 20 s. "Holds the camera": restart it with `--no-media`. Refused or error: `journalctl --user -u reachy-mini-daemon -n 50`, check the robot's power and USB. |
| head at rest | "No head press reading": this daemon does not report the head's commanded pose; the head press cannot work and the antenna press still does. Update the daemon (`uv pip install --python ~/reachy/.venv/bin/python -U reachy-mini`) or set `ARGOS_HEAD_PAT=0`. "Wobble too large": see section 4b. |
| head press | See section 4b. |
| head direction | FAIL: the head turns right where the brain expects left. Do not switch the wheels on; tell the brain's maintainer (`body/poses.py`). |
| pose model, speech model | Missing: `python tools/fetch_models.py` (needs the network once). Does not load: delete the file or folder and fetch again. |
| camera | Did not open: the daemon without `--no-media` holds it, or it is unplugged; `v4l2-ctl --list-devices` lists cameras. "Not found by name": set `ARGOS_CAMERA` to its `/dev/videoN`. Warn on the processor share: see section 7. |
| camera sides | FAIL: the picture is mirrored. Do not switch the wheels on: they would turn away from the person. Tell the brain's maintainer. |
| microphone, speaker | Nothing opened: `arecord -l` and `aplay -l` must list "Reachy Mini Audio"; the user must be in `audio`. If they are listed but fail while `wpctl status` shows the card, PipeWire is holding it: set `ARGOS_AUDIO_IN=pipewire` and `ARGOS_AUDIO_OUT=pipewire` and make the robot's card PipeWire's default (`wpctl status`, then `wpctl set-default <id>` for its sink and for its source). Silence: unmute it in `alsamixer` (F6 to pick the card). Not heard: turn it up in `alsamixer`. |
| ElevenLabs | 401: the key. 404: the voice id. 402 or 429: credit or quota. Without it the question is a beep, unless the line is already cached. |
| backend | "The public key": `SUPABASE_SERVICE_ROLE_KEY` must be the secret key (`sb_secret_...`). Refused: the wrong project's key or address. Device row missing: ask Hasan. |
| Gemini | The key, the model name, or the quota, as the row says. Without it the summary is a fixed sentence. |
| live view | 403: the private channel refused the key; ask Hasan to check the live view's access rules. |
| wheels | Section 6. |

## 4. Run the brain by hand, and watch it

```
cd ~/Argos/brain && . .venv/bin/activate
python -m argos
```

The keys work in the terminal. Try, and watch the robot and the log:

1. `m`: a check. The head turns toward you and lifts; "Are you okay?" plays. Say "I'm fine",
   or press `y`: it stands down with a nod.
2. `m` again, and say nothing: after 10 seconds it escalates, the antennas sweep, the
   dashboard shows the alert. Press `a` to acknowledge (recorded as "Demo").
3. While it is calm (and 30 s after the last check), say "help me" clearly: a call for help
   should start a check by itself. `h` does the same from the keyboard.
4. A pat: `m`, wait for the question to finish, then press the head down gently and hold it
   about a second (section 4b), or push an antenna aside: it stands down "by pat".
5. `q` quits. Ctrl+C, a service stop and a dropped SSH session also stop it cleanly.

### 4b. Tuning the head press

The head press is sensed from the difference between where the head was told to be and where
its motors say it is. After every move the brain waits half a second, learns the resting
difference, and then counts a change from rest of at least `ARGOS_HEAD_PAT_MM` millimetres,
or `ARGOS_HEAD_PAT_DEG` degrees, held for `ARGOS_HEAD_PAT_HOLD_S` seconds (defaults 5, 5 and
0.5). Nothing is sensed while the head or the wheels move, or for half a second after, so do
not press until the question has finished.

1. Run `python -m argos --check` in a terminal with the robot attached.
2. Read the "head at rest" row: the wobble, in mm and deg. If it says the wobble is too large,
   set the two values it suggests in `brain/.env` and run again.
3. When asked, press the head down gently and hold it until told to let go. The "head press"
   row says how far a held press moved it, whether that counts with the current settings, and
   suggests `ARGOS_HEAD_PAT_MM` and `ARGOS_HEAD_PAT_DEG` if it does not: about half of what
   your press reached, and at least three times the wobble.
4. Put the suggested values in `brain/.env`; run `--check` again until the row says the
   press counts.
5. Try it in the brain (section 4, step 4). Also try a quick tap on the head: that must NOT
   stand it down. And sit a check out without touching anything: it must escalate.
6. If it ever stands down "by pat" when nobody touched it, raise both values, or set
   `ARGOS_HEAD_PAT=0`. A missed press is the safe mistake; a false one silences a real alert.

Write down the numbers you measured (wobble, press, chosen settings) for the team.

## 5. Start at boot

Only once section 4 went well:

```
mkdir -p ~/.config/systemd/user && cp ~/Argos/brain/deploy/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now reachy-mini-daemon argos-brain
sudo loginctl enable-linger "$USER"
systemctl --user status reachy-mini-daemon argos-brain
journalctl --user -u argos-brain -f
```

Stop the daemon you started by hand first, or the service's daemon cannot start. Reboot once
and check both come up by themselves, and that `--check`'s "another brain" row now names the
service (stop it with `systemctl --user stop argos-brain` before running a brain by hand).

Under the service there are no keys, and the wheels never arm: the stop key must be at hand
whenever they can move. For the wheels, stop the service and run the brain by hand.

## 6. The wheels, for the first time

### Fit these first

- **A pull-down resistor on each enable pin**: 10 kOhm from ENA (GPIO12) to GND and from ENB
  (GPIO13) to GND, at the L298N. The L298N is powered by the motor battery, so it is awake
  while the Pi is off or still booting. Then nothing holds the enable pins, and an input
  left floating on the L298N can read as high. The Pi's own weak pull-downs only act once
  it has booted.
- **A switch on the motor battery**, within reach. There is no other off switch on the motors,
  and this is the one thing that works if everything else is wrong.
- The jumpers on ENA and ENB removed (contract section 2), and a ground wire from the L298N's
  GND to a Pi GND pin. Never connect the L298N's 5 V pin to the Pi.

After a boot, before any brain runs, check the six pins: `pinctrl get 12,13,17,22,23,27`.
Each should read as an input pulled down and low (`pd | lo`). Write down what it says.

### Then, base lifted

1. Lift the base onto a box, so that no wheel touches anything. Motor battery on.
2. In `brain/.env`: `ARGOS_WHEELS=1`. Leave `ARGOS_WHEELS_POWER` empty for now (0.20).
3. `python -m argos --check`: the wheels row must say the guard started and held the six
   pins. Nothing turns.
4. `python -m argos --wheel-test`. It asks you to confirm the base is lifted, then runs each
   side forward and back for half a second, starting at power 0.20. Answer whether each side
   moved: on "n" it tries again 0.05 higher, up to the cap of 0.60. Answer "r" if a side went
   back first. Then it runs a turn to the left (left wheels back, right wheels forward).
5. Set what it suggests in `brain/.env`: `ARGOS_WHEELS_POWER`, an `ARGOS_WHEELS_INVERT_LEFT=1`
   or `ARGOS_WHEELS_INVERT_RIGHT=1` for a side that went back first (or swap that side's two
   motor wires), and `ARGOS_WHEELS_TURN_POWER` a little higher than the forward power.
6. Still lifted: `python -m argos`, press `m`, and watch. After the question the head turns
   level and straight, then short bursts, with quiet gaps of 1.5 s. Press space: the wheels
   stop at once and stay off until you quit and start the brain again. Quit with `q`.

### Then on the floor

Only in a clear space, at least 2 m from any stair or table edge. One approach can cover at
most about 1.4 m (1.2 s of motor time at the 0.60 cap); with tired cells or a low power,
much less. Hand on the battery switch.

1. A person sits or lies on the floor about 1.5 m away, in view.
2. `python -m argos`, then `m`. After the question it should turn to put them in the middle of
   the picture, then come forward in short bursts, and stop when they reach the bottom or a
   side of the picture.
3. Check each stop: they say "I'm fine" during an approach (it stops at once); press space
   (it stops and stays off); they move out of view (it stops at the next look and does not
   search); quit with `q` mid-approach.
4. Measure how far one approach went, and on which floor. If the turns do not move it (the
   log says "the base did not turn"), raise `ARGOS_WHEELS_TURN_POWER` by 0.05 and try again,
   never above what the wheel test needed plus 0.15.

Write down: the lowest power that moved it lifted, the powers you settled on, how far one
approach went, and whether turning worked on the real floor.

## 7. What only the hardware can answer

Settle these on the robot and write the answers down for the team.

1. **The head's readings.** The daemon reports the head in metres and radians, worked out from
   its six motors 50 times a second; the brain asks 10 times a second. `--check` prints the
   wobble at rest and the size of a press. Unknown until then: both numbers.
2. **The camera.** The Lite's camera is most likely a 120 degree (diagonal) wide lens, about
   102 degrees across, but the 640x480 picture may crop it. The brain assumes 70
   (`ARGOS_CAMERA_HFOV_DEG`); that only sets how far the head turns toward a person, and the
   wheels steer by thirds of the picture, not by angle. To measure: put two objects at the
   left and right edges of the picture, at a distance D from the camera, W apart; the field of
   view is 2 x atan(W / 2D). Which way is left: the "head direction" and "camera sides" rows
   of `--check`.
3. **The pins at boot.** `pinctrl get 12,13,17,22,23,27` after a boot (above).
4. **The power.** The lowest power that moves the base on fresh cells, and on tired ones
   (AAA cells sag hard under four motors). The cap stays 0.60 in code.
5. **Turning.** Whether turns work at your power on the venue's floor (section 6).
6. **Keeping up.** With the brain running and `ARGOS_LIVE_VIEW=1`, for two minutes: the
   brain's CPU in `top` (press `1` for each core), `vcgencmd measure_temp`, and `--check`'s
   power row afterwards. The camera row gives one pose estimate's time. If the brain uses more
   than about 80% of a core, or the Pi throttles: `ARGOS_DETECT_FPS=4` and `LIVE_VIEW_FPS=2`.

## 8. If something goes wrong with the wheels

- Space (or `x`) in the brain's terminal stops them and keeps them off.
- If the brain dies, its guard process stops the motors by itself within a third of a second,
  and leaves all six pins low.
- If anything ever keeps a motor running: the battery switch. Then drive the pins low by hand:
  `pinctrl set 12,13,17,22,23,27 op dl`, or
  `cd ~/Argos/brain && .venv/bin/python -m argos.body.guard --pins-low`.
