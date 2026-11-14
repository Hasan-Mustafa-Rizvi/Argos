"""Regenerates demo_scenario.jsonl, the scripted 90 second run described in CONTRACT.md.

Run:  python make_demo_scenario.py

The output is deterministic. There is no randomness, so two runs give the same file.
Edit this script and rerun it. Do not edit demo_scenario.jsonl by hand.

The run has two incidents:
  A. A call for help that stands down when the person answers.
  B. A fall with no answer, which escalates and is then acknowledged.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = datetime(2026, 11, 15, 19, 0, 0, tzinfo=timezone.utc)
END_MS = 90_000
HEARTBEAT_MS = 5_000

DEVICE = "a0000000-0000-4000-8000-000000000001"
INCIDENT_A = "b0000000-0000-4000-8000-00000000000a"
INCIDENT_B = "b0000000-0000-4000-8000-00000000000b"
PERSON = "Eleni"
CONTACT = "Daughter"

lines = []
_event_count = 0


def ts(offset_ms):
    stamp = BASE + timedelta(milliseconds=offset_ms)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{stamp.microsecond // 1000:03d}Z"


def add(offset_ms, table, op, row):
    lines.append({"offset_ms": offset_ms, "table": table, "op": op, "row": row})


def device(offset_ms, state):
    add(offset_ms, "devices", "upsert", {
        "id": DEVICE,
        "name": "Argos",
        "person_label": PERSON,
        "state": state,
        "last_seen_at": ts(offset_ms),
        "fw": "0.1.0",
        "caps": ["eyes", "touch", "buzzer", "temp", "imu"],
    })


def event(offset_ms, kind, text, detail=None, incident=None):
    global _event_count
    _event_count += 1
    add(offset_ms, "events", "insert", {
        "id": f"c0000000-0000-4000-8000-{_event_count:012d}",
        "device_id": DEVICE,
        "incident_id": incident,
        "at": ts(offset_ms),
        "kind": kind,
        "text": text,
        "detail": detail or {},
    })


def incident(offset_ms, op, **fields):
    row = {
        "id": None, "device_id": DEVICE, "trigger": None, "status": None,
        "confidence": None, "started_at": None, "ended_at": None,
        "stood_down_by": None, "summary": None, "snapshot_path": None,
        "acknowledged_by": None, "acknowledged_at": None,
    }
    row.update(fields)
    add(offset_ms, "incidents", op, row)


# State over time, used for heartbeats between the scripted moments.
A_START, A_END = 12_000, 17_300
B_START, B_ESCALATE, B_ACK = 38_000, 48_500, 70_000


def state_at(ms):
    if A_START <= ms < A_END:
        return "checking"
    if B_START <= ms < B_ESCALATE:
        return "checking"
    if B_ESCALATE <= ms < B_ACK:
        return "alert"
    return "calm"


def still_seconds(ms):
    # Normal small movements, then no movement from the fall until help is acknowledged.
    if B_START - 2_000 <= ms < B_ACK:
        return (ms - (B_START - 2_000)) // 1000
    return [2, 7, 1, 4, 9, 3][(ms // HEARTBEAT_MS) % 6]


# Start
device(0, "calm")
event(0, "device_online", "Argos is online.")

# Heartbeats and readings
for ms in range(0, END_MS + 1, HEARTBEAT_MS):
    if ms > 0:
        device(ms, state_at(ms))
    step = ms // HEARTBEAT_MS
    add(ms, "readings", "insert", {
        "device_id": DEVICE,
        "at": ts(ms),
        "temp_c": round(23.4 + [0.0, 0.1, 0.1, 0.0, -0.1, 0.0][step % 6], 1),
        "tilt_deg": [1.2, 1.4, 1.1, 1.3][step % 4],
        "person_present": True,
        "still_s": still_seconds(ms),
    })

# Incident A: a call for help, answered
a_base = dict(id=INCIDENT_A, trigger="help_call", confidence=0.84, started_at=ts(A_START))
incident(A_START, "insert", status="checking", **a_base)
device(A_START, "checking")
event(A_START, "trigger", "Argos heard a call for help.",
      {"trigger": "help_call", "confidence": 0.84}, INCIDENT_A)
event(12_500, "asked", "Argos asked: Are you okay?", {"said": "Are you okay?"}, INCIDENT_A)
event(17_000, "heard", f"{PERSON} answered: I'm fine, I just dropped my book.",
      {"said": "I'm fine, I just dropped my book."}, INCIDENT_A)
event(A_END, "stood_down", f"Argos stood down. {PERSON} answered.", {"by": "voice"}, INCIDENT_A)
incident(A_END, "upsert", status="stood_down", ended_at=ts(A_END), stood_down_by="voice", **a_base)
device(A_END, "calm")

# Incident B: a fall, no answer, escalation, acknowledgement
b_base = dict(id=INCIDENT_B, trigger="fall", confidence=0.91, started_at=ts(B_START))
SUMMARY = "A person is lying on the floor beside the armchair and did not respond when asked."
SNAPSHOT = f"incidents/{INCIDENT_B}/snapshot.jpg"
incident(B_START, "insert", status="checking", **b_base)
device(B_START, "checking")
event(B_START, "trigger", "Argos saw someone on the floor.",
      {"trigger": "fall", "confidence": 0.91}, INCIDENT_B)
event(38_500, "asked", "Argos asked: Are you okay?", {"said": "Are you okay?"}, INCIDENT_B)
event(B_ESCALATE, "escalated", "No answer after 10 seconds. Argos is calling for help.", {}, INCIDENT_B)
incident(B_ESCALATE, "upsert", status="escalated", **b_base)
device(B_ESCALATE, "alert")
incident(50_500, "upsert", status="escalated", summary=SUMMARY, snapshot_path=SNAPSHOT, **b_base)
event(51_000, "call_placed", f"FaceTime call placed to {CONTACT}.",
      {"channel": "facetime", "to": CONTACT, "dry_run": False}, INCIDENT_B)
event(52_000, "email_sent", f"Backup email sent to {CONTACT}.",
      {"to": CONTACT, "dry_run": False}, INCIDENT_B)
event(58_000, "call_answered", f"{CONTACT} answered the call.", {"to": CONTACT}, INCIDENT_B)
event(B_ACK, "acknowledged", f"{CONTACT} acknowledged. Help is on the way.", {"by": CONTACT}, INCIDENT_B)
incident(B_ACK, "upsert", status="acknowledged", summary=SUMMARY, snapshot_path=SNAPSHOT,
         ended_at=ts(B_ACK), acknowledged_by=CONTACT, acknowledged_at=ts(B_ACK), **b_base)
device(B_ACK, "calm")

# Stable sort keeps the order written above for lines that share an offset.
lines.sort(key=lambda line: line["offset_ms"])

out = Path(__file__).with_name("demo_scenario.jsonl")
with out.open("w", encoding="utf-8", newline="\n") as handle:
    for line in lines:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")

print(f"wrote {len(lines)} lines to {out.name}")
