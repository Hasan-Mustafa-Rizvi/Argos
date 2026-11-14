# Argos contract

Version 0.1 · Sat Nov 14 2026

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

## 2. Dog and laptop: the serial link

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

`caps` lists what this body can do, from: `eyes`, `touch`, `buzzer`, `temp`, `imu`, `head`,
`tail`. The brain must work with any subset. A body with no `head` is valid.

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

If the laptop hears nothing from the dog for 3 seconds it treats the body as disconnected and
keeps running. Detection, voice and escalation must all work with no body attached.

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
| `last_seen_at` | timestamp | Heartbeat. The brain updates it every 5 seconds. |
| `fw` | text, nullable | From the dog's `hello` |
| `caps` | text array | From the dog's `hello`. Empty when no body is attached. |

### `incidents`: one row per check cycle

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `device_id` | uuid | |
| `trigger` | text | Section 1 |
| `status` | text | `checking`, `stood_down`, `escalated` or `acknowledged` |
| `confidence` | number 0 to 1, nullable | From the detector. Null for `manual`. |
| `started_at` | timestamp | |
| `ended_at` | timestamp, nullable | Set on `stood_down` and on `acknowledged` |
| `stood_down_by` | text, nullable | `voice` or `pat` |
| `summary` | text, nullable | One or two sentences on what Argos saw. Only on escalated incidents. |
| `snapshot_path` | text, nullable | Storage path of one still image. Only on escalated incidents. |
| `acknowledged_by` | text, nullable | A contact label such as "Daughter" |
| `acknowledged_at` | timestamp, nullable | |

**Privacy rule, absolute.** `summary` and `snapshot_path` are written only after an incident
reaches `escalated`. A stood-down incident never has an image or a description stored.

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
| `asked` | `{"said": "Are you okay?"}` |
| `heard` | `{"said": "I'm fine"}` |
| `pat` | `{}` |
| `stood_down` | `{"by": "voice"}` |
| `escalated` | `{}` |
| `call_placed` | `{"channel": "facetime", "to": "Daughter", "dry_run": false}` |
| `call_answered` | `{"to": "Daughter"}` |
| `call_failed` | `{"to": "Daughter", "reason": "..."}` |
| `email_sent` | `{"to": "Daughter", "dry_run": false}` |
| `acknowledged` | `{"by": "Daughter"}` |
| `room_alert` | `{"temp_c": 31.2}` |
| `device_tipped` | `{}` |

`to` and `by` are always labels. Phone numbers and email addresses never appear in any record.

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

There is no anonymous access. Everyone signs in. Two demo accounts exist so a judge can open
either view with one tap.

| | Family | Clinician |
|---|---|---|
| Device state and last seen | Yes | Yes |
| Incident list: trigger, status, times | Yes | Yes |
| Timeline (`events`) | Yes | Yes |
| Incident `summary` | Yes | Yes |
| Incident snapshot image | **Yes** | **No** |
| Sensor history (`readings`) | **No** | **Yes** |
| Acknowledge an incident | Yes | Yes |

**The one write the dashboard makes:** acknowledging an escalated incident. It sets `status`
to `acknowledged`, fills `acknowledged_by` and `acknowledged_at`, and the brain returns the
device to `calm`. The dashboard writes nothing else.

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
When the last line has been applied, start again from the top.

In replay mode `snapshot_path` points at no real file. Show a placeholder image.

`fixtures/make_demo_scenario.py` regenerates the file. Edit the script, not the output.
