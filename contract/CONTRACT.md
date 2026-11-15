# Argos contract

Version 0.6 · Sat Nov 14 2026

Changed in 0.6: the wheeled base is specified (section 2): the wiring, and the rules for
moving. `ARGOS_CALL_AGENT=1` tells the brain that the call agent writes the call events.

Changed in 0.5: escalation is carried by a call agent, a separate part that runs on a laptop
and learns of incidents from the backend. New event `message_sent`. The call agent may
acknowledge an incident on the contact's word (section 4) and may show the live view to the
contact during the call (section 6). No record changed shape.

Changed in 0.4.1: a reader of the live view forgets the last `seq` once the view has stopped
(section 6). The dashboard listens for record changes on the private channel
`records:<device id>` (section 4). Nothing the brain sends changed.

Changed in 0.4: a pat may be a press on the head or on an antenna. `asked` may say that the
line was not spoken. The brain may acknowledge from its own keyboard. The robot sits on a
wheeled base that the brain will drive: that interface is not written yet. No record changed
shape.

Changed in 0.3: the body is a Reachy Mini Lite driven by the brain on a Raspberry Pi 5, and
the serial link in section 2 is now an optional sensor board. `last_seen_at` may be null.
`ended_at` on an acknowledgement is set by the brain. `room_alert` no longer carries a
temperature. A rule for the last line of a fixture. No record changed shape, and the
fixtures are unchanged.

Changed in 0.2: section 6, the live view, is new. Section 4 gains the live view row and the
second factor. The privacy rule in section 3 now says plainly that it is about what is
stored. Nothing in sections 1, 2, 3 or 5 changed shape, so the fixtures are unchanged.

This file is the agreement between the three software parts: the firmware on the dog, the
brain on the laptop, and the dashboard. Each part is built against this file and the fixtures
next to it, so the parts can be built at the same time.

**Change rule.** Only Hasan changes this file. If something here is wrong or cannot be built,
say so and stop. Do not work around it in code.

**Compatibility rule for every reader.** Ignore fields you do not know. Ignore message types
and event kinds you do not know. Never crash on them.

---

## 1. Vocabulary

**Device state.** What Argos is doing right now.

| State | Meaning |
|---|---|
| `calm` | Watching. Nothing is wrong. |
| `checking` | Something was noticed. Argos has asked "Are you okay?" and is waiting. |
| `alert` | No answer came. Argos has escalated and is waiting for a person to acknowledge. |

`offline` is not stored. The dashboard shows it when `last_seen_at` is more than 15 seconds old.

**Trigger.** Why a check started.

| Trigger | Source |
|---|---|
| `fall` | Camera sees a person on the floor |
| `help_call` | Microphone hears a call for help |
| `stillness` | A person is present and has not moved for too long |
| `manual` | The hidden demo button |

**Incident.** One full cycle: a trigger, the check, and how it ended.

```
            trigger
calm ───────────────▶ checking ──── answer or pat ────▶ calm        incident: stood_down
                          │
                          └── no answer in 10 s ──▶ alert           incident: escalated
                                                      │
                                                      └── acknowledged ──▶ calm
                                                                    incident: acknowledged
```

The 10 second wait is a setting (`CHECK_TIMEOUT_S`), not a constant.

---

## 2. The body

The brain is a program on a Raspberry Pi 5. The body is a **Reachy Mini Lite** plugged into
it: a head that moves, two antennas, a camera, microphones and a speaker. The brain drives
it through the robot's own software, on the same machine. There is no message format to
agree for that: the brain's body driver decides what each state looks like, such as where
the head turns and what the antennas do.

**A pat is a press on the robot's head or on one of its antennas.** Both can be pushed by
hand. The brain senses that from the motors, as a part sitting away from where it was told
to be, and treats it as an answer during a check.

**The base.** The robot rides on four fixed wheels with tank steering, driven from the same
Raspberry Pi: four DC gear motors, two per side, through one L298N driver. There are no
encoders and no distance sensor. The brain decides when to move, and only the camera tells
it where the person is.

| L298N pin | Pi pin (BCM) | What it does |
|---|---|---|
| IN1, IN2 | GPIO17, GPIO27 | Left side: direction |
| IN3, IN4 | GPIO22, GPIO23 | Right side: direction |
| ENA | GPIO12 | Left side: power, by PWM. The jumper on ENA is removed. |
| ENB | GPIO13 | Right side: power, by PWM. The jumper on ENB is removed. |
| GND | a Pi GND pin | Common ground. Required. |

The motors have their own battery, not the Pi's. The Pi's pins are 3.3 V.

**Rules for moving, absolute.**

1. Off unless `ARGOS_WHEELS=1`. A missing value means off.
2. The base moves only while a check is open, only toward a person the camera sees at that
   moment, slowly, in short bursts, and for no longer than `ARGOS_APPROACH_MAX_S` in total.
   "At that moment" means a frame taken after the last burst ended and less than half a
   second old. It never moves in `calm` or in `alert`. One approach per check; none on a
   check resumed after a restart, none in a scripted run, and none within
   `ARGOS_APPROACH_REST_S` of the last.
3. It stops at once when the person is lost from view, when it is close, when the check
   ends, on the stop key, and when the brain stops for any reason. The pins are held by a
   separate guard that stops the motors when the brain goes quiet or dies.
4. Everything works with the wheels switched off, missing or broken.

The brain must run with no body at all, and on a laptop.

### The optional sensor board: the serial link

A small board on a USB cable can add what the robot lacks: room temperature, tilt, and a
touch pad for a pat. It is optional. Everything works without it.

USB serial, 115200 baud, UTF-8. One JSON object per line, ending in `\n`. A line is at most
256 bytes. Sample lines are in `examples/serial.jsonl`, where each sample is wrapped as
`{"dir": ..., "line": ...}` to show its direction. Only the `line` part travels on the wire.

### Dog to laptop

| `t` | Fields | When |
|---|---|---|
| `hello` | `fw` (string), `caps` (array of strings) | Once at boot, and in reply to `ping` |
| `telemetry` | `ms` (uptime), `temp_c`, `tilt_deg`, `touch` (bool) | Every 500 ms |
| `event` | `ms`, `kind` | When it happens |
| `err` | `msg` | A command could not be carried out |

`caps` lists what this board can do, from: `eyes`, `touch`, `buzzer`, `temp`, `imu`, `head`,
`tail`. The brain must work with any subset.

Event kinds from the dog: `pat` (the touch pad was pressed), `tipped` (the dog fell over),
`upright` (it was set back up).

### Laptop to dog

| `cmd` | Fields | Effect |
|---|---|---|
| `state` | `state`: `calm`, `checking` or `alert` | The dog shows that state with its eyes, and its buzzer if it has one. This is the only command a body must support. |
| `head` | `deg`: -60 to 60, 0 is straight ahead | Turn the head. Ignored without the `head` cap. |
| `tail` | `on`: bool | Wag. Ignored without the `tail` cap. |
| `buzz` | `ms`: 1 to 2000 | One beep |
| `ping` | none | The dog answers with `hello` |

The firmware decides what each state looks like. The laptop never sends colors or pins.

If the brain hears nothing from the board for 3 seconds it treats it as disconnected and
keeps running. Detection, voice and escalation must all work with no board attached.

In the tables above, "dog" means this board and "laptop" means the brain.

---

## 3. Brain and backend: the records

The brain is the only writer, with one exception in section 4. All times are ISO 8601 in UTC.
Column names are exactly as written here.

### `devices`: one row per dog

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | The demo dog is `a0000000-0000-4000-8000-000000000001` |
| `name` | text | "Argos" |
| `person_label` | text | Who it watches, as a display label. Never a real full name. |
| `state` | text | `calm`, `checking` or `alert` |
| `last_seen_at` | timestamp, nullable | Heartbeat. The brain updates it every 5 seconds. Null until the brain first reports. |
| `fw` | text, nullable | A version label for the body, if it reports one |
| `caps` | text array | What the body can do: the sensor board's `caps`, plus `head`, `antennas`, `camera`, `voice` when the robot is attached. Empty with no body. |

### `incidents`: one row per check cycle

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `device_id` | uuid | |
| `trigger` | text | Section 1 |
| `status` | text | `checking`, `stood_down`, `escalated` or `acknowledged` |
| `confidence` | number 0 to 1, nullable | From the detector. Null for `manual`. |
| `started_at` | timestamp | |
| `ended_at` | timestamp, nullable | Set on `stood_down`. On `acknowledged` the brain sets it to the same instant as `acknowledged_at`, when it sees the acknowledgement. |
| `stood_down_by` | text, nullable | `voice` or `pat` |
| `summary` | text, nullable | One or two sentences on what Argos saw. Only on escalated incidents. |
| `snapshot_path` | text, nullable | Storage path of one still image, `incidents/<incident id>/snapshot.jpg` in the private `snapshots` store. Only on escalated incidents. |
| `acknowledged_by` | text, nullable | A contact label such as "Daughter" |
| `acknowledged_at` | timestamp, nullable | |

**Privacy rule, absolute.** `summary` and `snapshot_path` are written only after an incident
reaches `escalated`. A stood-down incident never has an image or a description stored. This
rule is about what is stored. The live view in section 6 is never stored at all.

### `events`: the timeline, append only

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `device_id` | uuid | |
| `incident_id` | uuid, nullable | Null for events outside an incident |
| `at` | timestamp | |
| `kind` | text | See below |
| `text` | text | A finished sentence a person can read. The dashboard can always show this, even for a kind it does not know. |
| `detail` | json | Structured fields for that kind |

| `kind` | `detail` |
|---|---|
| `device_online` | `{}` |
| `trigger` | `{"trigger": "...", "confidence": 0.91}` |
| `asked` | `{"said": "Are you okay?"}`. Carries `"spoken": false` when the line was not played, whether or not a beep went out. |
| `heard` | `{"said": "I'm fine"}` |
| `pat` | `{}` |
| `stood_down` | `{"by": "voice"}` |
| `escalated` | `{}` |
| `call_placed` | `{"channel": "facetime", "to": "Daughter", "dry_run": false}` |
| `call_answered` | `{"to": "Daughter"}` |
| `call_failed` | `{"to": "Daughter", "reason": "..."}` |
| `message_sent` | `{"channel": "imessage", "to": "Daughter", "dry_run": false}` |
| `email_sent` | `{"to": "Daughter", "dry_run": false}` |
| `acknowledged` | `{"by": "Daughter"}` |
| `room_alert` | `{}`. Neither the detail nor the sentence states a temperature, because family reads events and does not read sensor readings. |
| `device_tipped` | `{}` |

`to` and `by` are always labels. Phone numbers and email addresses never appear in any record.

The `call_` and `message_` events are written by the part that places the call: the call
agent when it is running, otherwise the brain in dry-run.

### `readings`: sensor history

One row every 5 seconds.

| Column | Type | Notes |
|---|---|---|
| `device_id` | uuid | |
| `at` | timestamp | |
| `temp_c` | number, nullable | Room temperature |
| `tilt_deg` | number, nullable | How far the dog is from upright |
| `person_present` | bool | The camera sees a person |
| `still_s` | integer | Seconds since the person last moved. 0 when no person is present. |

---

## 4. Who sees what

There is no anonymous access. Everyone signs in. There are two kinds of session:

- **Real account.** Email and password, then a second factor from an authenticator app.
  Reads live records.
- **Demo.** Opens with one tap so a judge can see either view. Plays the scripted run in
  section 5. A demo session never reads live records and never receives the live view.

| | Family | Clinician |
|---|---|---|
| Live view (section 6), real account with second factor only | **Yes** | **No** |
| Device state and last seen | Yes | Yes |
| Incident list: trigger, status, times | Yes | Yes |
| Timeline (`events`) | Yes | Yes |
| Incident `summary` | Yes | Yes |
| Incident snapshot image | **Yes** | **No** |
| Sensor history (`readings`) | **No** | **Yes** |
| Acknowledge an incident | Yes | Yes |

**How live records reach the dashboard.** It reads the tables, and listens for changes on a
private channel with the topic `records:<device id>`. Joining needs a member's session that
has passed its second factor. What arrives is still decided table by table, by the rules
above.

**The one write the dashboard makes:** acknowledging an escalated incident. It sets `status`
to `acknowledged` and fills `acknowledged_by` and `acknowledged_at`. The brain then sets
`ended_at`, records the `acknowledged` event and returns the device to `calm`. The
dashboard writes nothing else. The brain may make the same acknowledgement itself from its
own keyboard, for a demo with no network, with the label "Demo". The call agent may make it
when the contact says so on the call, with the contact's label followed by ", by FaceTime".

---

## 5. Fixtures

`fixtures/demo_scenario.jsonl` is a scripted 90 second run with two incidents: one that
stands down and one that escalates and is acknowledged. The dashboard is built against it
first, and keeps it afterwards as a replay mode for when the network fails.

Each line:

```json
{"offset_ms": 12000, "table": "events", "op": "insert", "row": { ... }}
```

- `offset_ms`: when to apply the line, counted from the start of the replay.
- `table`: `devices`, `incidents`, `events` or `readings`.
- `op`: `insert`, or `upsert` matched on `id`.
- `row`: exactly the columns in section 3.

Timestamps inside rows are written against the base time `2026-11-15T19:00:00Z`. On replay,
shift every timestamp by the same amount so the base lands on the moment the replay started.
When the last line has been applied, start again from the top. So the last line is never
seen for long: a fixture's last lines must leave things as its first lines set them.

In replay mode `snapshot_path` points at no real file. Show a placeholder image.

`fixtures/make_demo_scenario.py` regenerates the file. Edit the script, not the output.

The fixtures carry no live view frames. In replay the centre panel shows its demo state.

---

## 6. The live view

The live view is what the dog's camera sees, shown in the centre of the dashboard.

**Three rules, absolute.**

1. **Never stored.** No frame is written to a table, to storage, to a log or to disk, by the
   brain, the backend or the dashboard. The only stored image is still the one snapshot on an
   escalated incident.
2. **Second factor only.** A frame reaches a browser only for a real account whose session
   has passed its second factor, and whose role is `family` for that device. This is enforced
   by the backend's access rules, not by the dashboard hiding a panel.
   One more reader is allowed: the call agent, during the call it places for an escalated
   incident, may show the frames to the emergency contact on that call. It reads them with
   the backend's secret key on its own machine, keeps none, and stops when the call ends.
3. **Off unless switched on.** The brain sends frames only when `ARGOS_LIVE_VIEW=1`. A
   missing value means off.

**How frames travel.** The brain publishes to a private live channel. Nothing is kept by the
channel: a browser that is not listening at that moment never gets the frame.

| | |
|---|---|
| Channel topic | `view:<device id>` |
| Channel kind | Private broadcast. Joining needs a signed-in session that passes rule 2. |
| Event name | `frame` |
| Rate | `LIVE_VIEW_FPS`, default 4, never more than 8 |

Each `frame` message:

```json
{"seq": 1042, "at": "2026-11-15T19:00:12.250Z", "w": 320, "h": 240, "jpeg": "<base64>"}
```

| Field | Type | Notes |
|---|---|---|
| `seq` | integer | Counts up from 0 each time the brain starts. A reader drops a frame whose `seq` is lower than the last one shown, until the view has stopped (below); then it forgets the last `seq` and takes the next frame, whatever its number. |
| `at` | timestamp | When the frame was captured. |
| `w`, `h` | integer | Size in pixels. The long side is at most 480. |
| `jpeg` | text | One JPEG image, base64. The whole message stays under 100 KB. |

**For the reader.**

- Extra fields in a frame are ignored. The 5 seconds below are counted from when frames
  arrive, never from `at`.
- No frame for 5 seconds means the view has stopped. Show the last frame faded and say how
  long ago it was. Everything else on the dashboard keeps working.
- The reader never asks for a frame and never writes to the channel.
- Frames are for looking at. Detection runs in the brain on the camera directly, never on
  these frames.
