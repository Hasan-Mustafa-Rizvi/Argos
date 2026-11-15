"""Any mix of bodies runs a full check. Start-up with incidents left open. The writer in an
outage. Sentences. Keys."""

from __future__ import annotations

import io
import json
import random
from typing import Any

import pytest

from argos import DEVICE_ID, text
from argos.body.reachy import RobotBody
from argos.body.serial_link import SensorBoard
from argos.brain import AnswerIn, TriggerIn
from argos.keyboard import Keyboard
from argos.machine import State
from argos.store import MemoryStore, StoreRejected
from argos.writer import RecordWriter
from tests.conftest import make_rig, seeded_store
from tests.test_robot import FakeReachy
from tests.test_serial import FakePort


def bodies_for(mix: str, clock: Any, ports: list[FakePort], robot: FakeReachy) -> list[Any]:
    bodies: list[Any] = []
    if "robot" in mix:
        bodies.append(RobotBody(robot, clock, rng=random.Random(1), threaded=False))
    if "board" in mix:
        def opener(url: str) -> FakePort:
            ports.append(FakePort())
            return ports[-1]

        bodies.append(SensorBoard("socket://127.0.0.1:7777", clock, opener=opener,
                                  threaded=False))
    return bodies


@pytest.mark.parametrize("mix", ["none", "robot", "board", "robot+board"])
def test_full_check_with_any_mix_of_bodies(mix: str) -> None:
    rig = make_rig()
    ports: list[FakePort] = []
    robot = FakeReachy()
    bodies = bodies_for(mix, rig.clock, ports, robot)
    rig.brain.bodies.bodies = bodies
    for body in bodies:
        body.clock = rig.clock
    rig.brain.start()
    board = next((b for b in bodies if isinstance(b, SensorBoard)), None)
    if board:
        ports[-1].feed({"t": "hello", "fw": "0.1.0", "caps": ["eyes", "touch", "buzzer"]})
        board.poll(rig.clock.now())

    def pump(seconds: float) -> None:
        for _ in range(int(seconds / 0.1)):
            rig.clock.advance(0.1)
            for body in bodies:
                if isinstance(body, SensorBoard):
                    ports[-1].feed({"t": "telemetry", "ms": 1, "temp_c": 23.4,
                                    "tilt_deg": 1.1, "touch": False})
                    body.poll(rig.clock.now())
                else:
                    body.update(rig.clock.now())
            rig.brain.step()

    pump(1.0)
    # One check that a pat stands down (from the board if there is one), one that escalates.
    rig.brain.post(TriggerIn("manual"))
    pump(2.0)
    if board:
        ports[-1].feed({"t": "event", "ms": 5, "kind": "pat"})
    else:
        rig.brain.post(AnswerIn("pat"))
    pump(1.0)
    assert rig.brain.state is State.CALM
    rig.brain.post(TriggerIn("help_call", 0.8))
    pump(10.5)
    assert rig.brain.state is State.ALERT
    rig.brain.key("a")
    pump(5.5)
    assert rig.brain.state is State.CALM
    statuses = [i["status"] for i in rig.store.tables["incidents"]]
    assert statuses == ["stood_down", "acknowledged"]
    caps = rig.store.tables["devices"][0]["caps"]
    if "robot" in mix:
        assert {"head", "antennas", "camera", "voice"} <= set(caps)
        assert robot.gotos, "the robot was moved"
    if board:
        assert {"eyes", "touch", "buzzer"} <= set(caps)
        sent_states = [c["state"] for c in ports[-1].written if c.get("cmd") == "state"]
        assert "checking" in sent_states and "alert" in sent_states and sent_states[-1] == "calm"
        reading = rig.store.tables["readings"][-1]
        assert reading["temp_c"] == 23.4 and reading["tilt_deg"] == 1.1
    if mix == "none":
        assert caps == []
        reading = rig.store.tables["readings"][-1]
        assert reading["person_present"] is False and reading["still_s"] == 0
        assert reading["temp_c"] is None and reading["tilt_deg"] is None


def test_tipped_board_records_device_tipped() -> None:
    rig = make_rig()
    ports: list[FakePort] = []
    bodies = bodies_for("board", rig.clock, ports, FakeReachy())
    rig.brain.bodies.bodies = bodies
    rig.brain.start()
    ports[-1].feed({"t": "hello", "fw": "0.1.0", "caps": ["imu"]},
                   {"t": "event", "ms": 9120, "kind": "tipped"})
    bodies[0].poll(rig.clock.now())
    rig.step()
    tipped = [e for e in rig.store.tables["events"] if e["kind"] == "device_tipped"]
    assert len(tipped) == 1 and tipped[0]["detail"] == {}


# --------------------------------------------------------------------------- start-up


def open_incident(store: MemoryStore, status: str, incident_id: str = "old-1") -> None:
    store.tables["incidents"].append({
        "id": incident_id, "device_id": DEVICE_ID, "trigger": "fall", "status": status,
        "confidence": 0.9, "started_at": "2026-11-15T18:00:00.000Z", "ended_at": None,
        "stood_down_by": None, "summary": None, "snapshot_path": None,
        "acknowledged_by": None, "acknowledged_at": None,
    })


def test_start_with_an_unacknowledged_escalation_is_an_alert() -> None:
    store = seeded_store()
    open_incident(store, "escalated")
    rig = make_rig(store=store)
    rig.brain.start()
    assert rig.brain.state is State.ALERT
    assert store.tables["devices"][0]["state"] == "alert"
    assert "call_placed" not in rig.event_kinds()  # nothing is re-sent
    store.update("incidents", {"id": "eq.old-1"}, {"status": "acknowledged",
                                                     "acknowledged_by": "Daughter",
                                                     "acknowledged_at": "2026-11-15T19:00:03.000Z"})
    rig.run_for(2.5)
    assert rig.brain.state is State.CALM
    assert store.row("incidents", "old-1")["ended_at"] == "2026-11-15T19:00:03.000Z"


def test_start_with_an_interrupted_check_asks_again_in_the_same_incident() -> None:
    store = seeded_store()
    open_incident(store, "checking")
    rig = make_rig(store=store)
    rig.brain.start()
    rig.step()
    assert rig.brain.state is State.CHECKING
    assert len(store.tables["incidents"]) == 1  # no new incident
    asked = [e for e in store.tables["events"] if e["kind"] == "asked"]
    assert asked and asked[0]["incident_id"] == "old-1"
    rig.run_for(10.2)
    assert store.row("incidents", "old-1")["status"] == "escalated"


# --------------------------------------------------------------------------- the writer


def test_device_writes_merge_while_offline_and_land_last() -> None:
    store = MemoryStore()
    store.tables["devices"].append({"id": "d", "state": "calm"})
    store.tables["incidents"].append({"id": "i", "status": "checking", "summary": None,
                                      "snapshot_path": None})
    writer = RecordWriter(store, threaded=False)
    store.fail = True
    writer.update("devices", {"id": "eq.d"}, {"state": "checking", "last_seen_at": "1"},
                  merge_key="device")
    writer.insert("events", {"id": "e1"})
    writer.update("devices", {"id": "eq.d"}, {"state": "calm"}, merge_key="device")
    writer.update("incidents", {"id": "eq.i", "status": "eq.checking"},
                  {"status": "stood_down"})
    writer.update("devices", {"id": "eq.d"}, {"last_seen_at": "3"}, merge_key="device")
    assert writer.pending == 3
    store.fail = False
    assert writer.flush()
    assert [op["table"] for op in store.ops] == ["events", "incidents", "devices"]
    assert store.ops[-1]["patch"] == {"state": "calm", "last_seen_at": "3"}


def test_readings_kept_for_an_hour_and_sent_as_one_batch() -> None:
    store = MemoryStore()
    writer = RecordWriter(store, threaded=False)
    store.fail = True
    for i in range(800):
        writer.insert("readings", {"device_id": "d", "at": f"{i:05d}"})
    assert writer.pending == 720
    store.fail = False
    writer.flush()
    assert len(store.tables["readings"]) == 720
    assert store.tables["readings"][0]["at"] == "00080"
    assert len([op for op in store.ops if op["table"] == "readings"]) == 720


def test_refused_write_is_dropped_and_does_not_block() -> None:
    class Refusing(MemoryStore):
        def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
            if table == "events" and rows[0]["id"] == "bad":
                raise StoreRejected("HTTP 400")
            super().insert(table, rows)

    store = Refusing()
    writer = RecordWriter(store, threaded=False)
    writer.insert("events", {"id": "bad"})
    writer.insert("events", {"id": "good"})
    assert [r["id"] for r in store.tables["events"]] == ["good"]
    assert writer.pending == 0


def test_retried_insert_never_overwrites() -> None:
    store = MemoryStore()
    store.insert("incidents", [{"id": "i", "status": "acknowledged"}])
    store.insert("incidents", [{"id": "i", "status": "checking"}])
    assert store.row("incidents", "i")["status"] == "acknowledged"


# --------------------------------------------------------------------------- text and keys


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("A person — lying down", "A person, lying down"),
        ("Fell – near the chair.", "Fell, near the chair."),
        ("Ends with a dash —", "Ends with a dash"),
        ("Plain-hyphen stays", "Plain-hyphen stays"),
    ],
)
def test_clean_removes_em_and_en_dashes(raw: str, cleaned: str) -> None:
    assert text.clean(raw) == cleaned


def test_sentences_have_no_dashes_and_name_the_person() -> None:
    person = text.Person("Eleni")
    sentences = [
        text.trigger(kind, person) for kind in ("fall", "help_call", "stillness", "manual")
    ] + [text.heard(person, "I'm fine"), text.stood_down(person, "pat"),
         text.escalated(10), text.call_placed_dry_run("Daughter"),
         text.email_sent_dry_run("Daughter"), text.acknowledged("Demo"),
         *(text.fixed_summary(k) for k in ("fall", "help_call", "stillness", "manual"))]
    for sentence in sentences:
        assert "—" not in sentence and "–" not in sentence
    assert text.heard(text.Person(), "yes") == "The person answered: yes"
    assert "Eleni" in text.trigger("stillness", person)


def test_keyboard_reads_lines_when_there_is_no_terminal() -> None:
    keys: list[str] = []
    keyboard = Keyboard(keys.append, stream=io.StringIO("f\nY\n\nzzz\na\nq\n"))
    keyboard._run()
    assert keys == ["f", "y", "a", "q"]


def test_keys_drive_the_brain() -> None:
    rig = make_rig()
    rig.brain.start()
    rig.brain.key("h")
    rig.step()
    assert rig.brain.state is State.CHECKING
    rig.brain.key("y")
    rig.step()
    assert rig.brain.state is State.CALM
    heard = [e for e in rig.store.tables["events"] if e["kind"] == "heard"]
    assert heard[0]["detail"] == {"said": "I'm fine"}
    assert json.dumps(rig.store.tables["incidents"][0]["confidence"]) == "null"
    rig.brain.key("q")
    rig.step()
    assert rig.brain.quit.is_set()


@pytest.mark.parametrize(("sent", "keys"), [
    ("\x1b[A", []),                      # up arrow: was "a", an acknowledgement
    ("\x1b[H\x1b[F", []),                # Home and End: were "h" and "f", checks started
    ("\x1bOP\x1bOS", []),                # F1 and F4: were "p" (a pat) and "s"
    ("\x1b[<64;10;5M", []),              # a mouse report: was "m"
    ("\x1b[?1;2c", []),                  # a terminal's answer to a query
    ("\x1bP1$r2 q\x1b\\", []),           # a terminal string reply, ending in "q" before ST
    ("\x1b]11;rgb:0000/0000/0000\x07", []),
    ("m\x1b[Ay", ["m", "y"]),            # real keys around a sequence still count
    ("Q", ["q"]),                        # caps lock still works
])
def test_terminal_escape_sequences_are_never_keys(sent: str, keys: list[str]) -> None:
    """On the Pi the brain quit by itself; an arrow key could have acknowledged an alert."""
    got: list[str] = []
    keyboard = Keyboard(got.append, stream=io.StringIO(""))
    keyboard._feed(sent)
    assert got == keys


def test_an_escape_sequence_split_across_reads_is_still_dropped() -> None:
    got: list[str] = []
    keyboard = Keyboard(got.append, stream=io.StringIO(""))
    keyboard._feed("\x1b")
    keyboard._feed("[")
    keyboard._feed("A")
    keyboard._feed("a")
    assert got == ["a"]


def test_a_lone_escape_key_does_not_swallow_the_next_key_after_a_pause() -> None:
    got: list[str] = []
    keyboard = Keyboard(got.append, stream=io.StringIO(""))
    keyboard._feed("\x1b")
    keyboard._idle()
    keyboard._feed("m")
    assert got == ["m"]
