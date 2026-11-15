"""The five rules, as far as Stage 1 can reach them, plus acknowledgement handling."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, MutableMapping
from typing import Any

import pytest

from argos import text
from argos.brain import AckIn, AnswerIn, TriggerIn
from argos.config import Settings
from argos.escalation import make_escalator
from argos.locallog import MemoryLog
from argos.machine import State
from argos.records import PrivacyError, Recorder
from argos.store import MemoryStore
from tests.conftest import BASE_ENV, EMAIL_MARKER, FACETIME_MARKER, Rig, make_rig


class FakeFrames:
    """A camera that returns recognisable bytes, so a leak would be easy to spot."""

    BYTES = b"\xff\xd8FAKE-IMAGE-BYTES-OF-A-PERSON"

    def latest(self) -> bytes:
        return self.BYTES


def escalate(rig: Rig, trigger: str = "fall") -> str:
    rig.brain.post(TriggerIn(trigger, 0.9))
    rig.step()
    incident_id = rig.brain.machine.incident_id
    assert incident_id
    rig.run_for(10.1)
    assert rig.brain.state is State.ALERT
    return incident_id


# --------------------------------------------------------------------------- rule 1


def test_rule1_stood_down_check_leaves_nothing() -> None:
    rig = make_rig(frames=FakeFrames(), uploader=lambda i, f: f"incidents/{i}/snapshot.jpg")
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9))
    rig.step()
    assert rig.brain.held_frame == FakeFrames.BYTES  # held in memory from the trigger
    rig.run_for(2.0)
    rig.brain.post(AnswerIn("voice", "I'm fine"))
    rig.step()
    rig.run_for(15.0)
    assert rig.brain.held_frame is None  # dropped the moment the check stood down
    written = [op.get("row") or op.get("patch") or {} for op in rig.store.ops]
    written += [entry.get("row") or entry.get("patch") or {} for entry in rig.log.entries()]
    for data in written:
        assert data.get("summary") is None
        assert data.get("snapshot_path") is None
    assert "FAKE-IMAGE" not in rig.everything_written()
    assert rig.store.files == {}
    incident = rig.incident()
    assert incident["status"] == "stood_down"
    assert incident["summary"] is None and incident["snapshot_path"] is None


def test_rule1_report_only_after_escalated() -> None:
    uploads: list[str] = []

    rig = make_rig(frames=FakeFrames())

    def uploader(incident_id: str, frame: Any) -> str:
        status = rig.store.row("incidents", incident_id)["status"]
        uploads.append(status)
        path = f"incidents/{incident_id}/snapshot.jpg"
        rig.store.upload("snapshots", path, frame, "image/jpeg")
        return path

    rig.brain.uploader = uploader
    rig.brain.start()
    incident_id = escalate(rig)
    rig.step()  # the follow-up report is written
    assert uploads == ["escalated"]  # no upload was attempted before escalation
    escalated_at = None
    report_at = None
    for index, op in enumerate(rig.store.ops):
        if op["table"] != "incidents" or op["op"] != "update":
            continue
        if op["patch"].get("status") == "escalated":
            escalated_at = index
        if "summary" in op["patch"] or "snapshot_path" in op["patch"]:
            report_at = index
            assert set(op["patch"]) <= {"summary", "snapshot_path"}
    assert escalated_at is not None and report_at is not None and report_at > escalated_at
    incident = rig.incident(incident_id)
    assert incident["snapshot_path"] == f"incidents/{incident_id}/snapshot.jpg"
    assert incident["summary"] == text.fixed_summary("fall")
    assert rig.brain.held_frame is None
    # The image went to storage only; never to a table or the local log.
    tables_and_log = "\n".join([str(rig.store.tables), *rig.log.lines])
    assert "FAKE-IMAGE" not in tables_and_log


def test_recorder_refuses_report_before_escalation() -> None:
    from argos.clock import FakeClock
    from argos.writer import RecordWriter

    store = MemoryStore()
    log = MemoryLog()
    recorder = Recorder("dev", FakeClock(), RecordWriter(store, threaded=False), log)
    recorder.incident_opened("inc", "fall", 0.9, "2026-11-15T19:00:00.000Z")
    with pytest.raises(PrivacyError):
        recorder.incident_report("inc", "A summary", "incidents/inc/snapshot.jpg")
    assert "A summary" not in "\n".join(log.lines)


def test_summary_write_does_not_undo_acknowledgement() -> None:
    rig = make_rig(runner=_HeldRunner())
    rig.brain.start()
    incident_id = escalate(rig)
    # The dashboard acknowledges before the summary is written.
    rig.store.update("incidents", {"id": f"eq.{incident_id}", "status": "eq.escalated"},
                     {"status": "acknowledged", "acknowledged_by": "Daughter",
                      "acknowledged_at": "2026-11-15T19:00:30.000Z"})
    rig.brain.runner.release()  # now the follow-up finishes and the summary is written
    rig.step()
    incident = rig.incident(incident_id)
    assert incident["summary"] == text.fixed_summary("fall")
    assert incident["status"] == "acknowledged"
    assert incident["acknowledged_by"] == "Daughter"


class _HeldRunner:
    """Holds background jobs until `release()`, to order them against other writes."""

    def __init__(self) -> None:
        self.jobs: list[Any] = []

    def submit(self, job: Any, name: str) -> None:
        if name == "follow-up":
            self.jobs.append(job)
        else:
            job()

    def release(self) -> None:
        while self.jobs:
            self.jobs.pop(0)()


# --------------------------------------------------------------------------- rule 3


@pytest.mark.parametrize("value", [None, "1", "0"])
def test_rule3_dry_run_whatever_the_setting(value: str | None) -> None:
    calls: list[Any] = []

    class RecordingSender:
        dry_run = False

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append(("made", args, kwargs))

        def escalate(self, incident_id: str) -> None:
            calls.append(("escalate", incident_id))

    env = {} if value is None else {"ARGOS_DRY_RUN": value}
    rig = make_rig(env=env)
    rig.brain.escalator = make_escalator(rig.settings, rig.brain.recorder,
                                         real_sender=RecordingSender)
    rig.brain.start()
    escalate(rig)
    assert calls == []
    sent = [e for e in rig.store.tables["events"] if e["kind"] in ("call_placed", "email_sent")]
    assert [e["kind"] for e in sent] == ["call_placed", "email_sent"]
    for event in sent:
        assert event["detail"]["dry_run"] is True
        assert event["detail"]["to"] == "Daughter"
        assert "Dry run" in event["text"]
    if value == "0":
        assert any("not built yet" in line for line in rig.log.lines)


def test_rule3_real_sender_stub_raises() -> None:
    from argos.escalation import RealSender

    with pytest.raises(NotImplementedError):
        RealSender().escalate("inc")


# --------------------------------------------------------------------------- rule 4


class SpyEnviron(MutableMapping[str, str]):
    """os.environ stand-in that remembers which names were read."""

    def __init__(self, data: dict[str, str]) -> None:
        self.data = dict(data)
        self.read: set[str] = set()

    def __getitem__(self, key: str) -> str:
        self.read.add(key)
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        self.read.add(key)
        return self.data.get(key, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.read.add(key)
        return key in self.data

    def __setitem__(self, key: str, value: str) -> None:
        self.data[key] = value

    def __delitem__(self, key: str) -> None:
        del self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


def test_rule4_contact_values_never_read_or_written(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = SpyEnviron({**BASE_ENV, "CONTACT_FACETIME_TO": FACETIME_MARKER,
                      "CONTACT_EMAIL_TO": EMAIL_MARKER})
    monkeypatch.setattr(os, "environ", spy)
    settings = Settings.from_env(os.environ)
    rig = make_rig(env={"CONTACT_LABEL": settings.contact_label})
    rig.brain.start()
    incident_id = escalate(rig)
    rig.step()
    rig.brain.post(AckIn("Demo"))
    rig.run_for(6.0)
    assert rig.incident(incident_id)["status"] == "acknowledged"
    assert "CONTACT_FACETIME_TO" not in spy.read
    assert "CONTACT_EMAIL_TO" not in spy.read
    everything = rig.everything_written()
    assert FACETIME_MARKER not in everything
    assert EMAIL_MARKER not in everything


def test_rule4_markers_never_reach_python_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    rig = make_rig(env={"CONTACT_FACETIME_TO": FACETIME_MARKER,
                        "CONTACT_EMAIL_TO": EMAIL_MARKER})
    rig.brain.start()
    escalate(rig)
    assert FACETIME_MARKER not in caplog.text and EMAIL_MARKER not in caplog.text
    assert "MARKER-KEY" not in caplog.text  # nor the backend key


# --------------------------------------------------------------------------- rule 5


def test_rule5_runs_with_nothing_and_a_failing_store() -> None:
    store = MemoryStore()
    store.fail = True  # every write and read raises
    env = {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": "", "SERIAL_PORT": ""}
    rig = make_rig(env=env, store=store)
    rig.brain.start()
    incident_id = escalate(rig, "manual")
    rig.step()
    rig.brain.post(AckIn("Demo"))
    rig.run_for(1.0)
    assert rig.brain.state is State.CALM
    kinds = [entry.get("row", {}).get("kind") for entry in rig.log.entries()]
    for kind in ("device_online", "trigger", "asked", "escalated", "call_placed",
                 "email_sent", "acknowledged"):
        assert kind in kinds
    assert rig.writer.pending > 0  # kept for when the backend comes back
    assert incident_id


def test_rule5_backend_returns_and_catches_up() -> None:
    store = MemoryStore()
    rig = make_rig(store=store)
    store.fail = True
    rig.brain.start()
    rig.brain.post(TriggerIn("help_call", 0.8))
    rig.step()
    rig.run_for(3.0)
    rig.brain.post(AnswerIn("pat"))
    rig.step()
    store.fail = False
    rig.run_for(5.1)  # the next heartbeat flushes everything that waited
    assert rig.writer.pending == 0
    incident = store.tables["incidents"][0]
    assert incident["status"] == "stood_down"
    assert incident["stood_down_by"] == "pat"
    assert [e["kind"] for e in store.tables["events"]] == [
        "device_online", "trigger", "asked", "pat", "stood_down"]
    device_updates = [op for op in store.ops if op["table"] == "devices"]
    assert device_updates[-1]["patch"]["state"] == "calm"  # the truth as it is now


# --------------------------------------------------------------------------- acknowledgement


def test_dashboard_acknowledgement_returns_to_calm_with_its_label() -> None:
    rig = make_rig()
    rig.brain.start()
    incident_id = escalate(rig)
    rig.store.update("incidents", {"id": f"eq.{incident_id}", "status": "eq.escalated"},
                     {"status": "acknowledged", "acknowledged_by": "Daughter",
                      "acknowledged_at": "2026-11-15T19:01:10.000Z"})
    rig.run_for(2.5)  # the brain polls while in alert
    assert rig.brain.state is State.CALM
    ack = [e for e in rig.store.tables["events"] if e["kind"] == "acknowledged"]
    assert len(ack) == 1
    assert ack[0]["detail"] == {"by": "Daughter"}
    assert ack[0]["text"] == "Daughter acknowledged. Help is on the way."
    incident = rig.incident(incident_id)
    assert incident["ended_at"] == "2026-11-15T19:01:10.000Z" == incident["acknowledged_at"]
    states = [op["patch"].get("state") for op in rig.store.ops if op["table"] == "devices"]
    assert [s for s in states if s][-1] == "calm"


def test_keyboard_acknowledgement_is_recorded_as_demo() -> None:
    rig = make_rig(env={"CONTACT_LABEL": "Daughter"})
    rig.brain.start()
    incident_id = escalate(rig)
    rig.brain.key("a")
    rig.step()
    ack = [e for e in rig.store.tables["events"] if e["kind"] == "acknowledged"][0]
    assert ack["detail"] == {"by": "Demo"}
    incident = rig.incident(incident_id)
    assert incident["acknowledged_by"] == "Demo"
    assert incident["ended_at"] == incident["acknowledged_at"]
    assert rig.brain.state is State.CALM


def test_trigger_during_check_is_logged_not_recorded() -> None:
    rig = make_rig()
    rig.brain.start()
    rig.brain.post(TriggerIn("fall", 0.9))
    rig.step()
    rig.brain.post(TriggerIn("help_call", 0.9))
    rig.step()
    assert len(rig.store.tables["incidents"]) == 1
    assert rig.event_kinds().count("trigger") == 1
    assert any("ignored trigger" in line for line in rig.log.lines)


def test_no_dashes_reach_a_record() -> None:
    rig = make_rig(store=None)
    rig.store.tables["devices"][0]["person_label"] = "Eleni — Mum"
    rig.brain.start()
    rig.brain.post(TriggerIn("stillness", 0.7))
    rig.step()
    rig.brain.post(AnswerIn("voice", "I'm fine – really"))
    rig.step()
    everything = rig.everything_written()
    assert "—" not in everything and "–" not in everything


def test_local_log_is_utf8_with_lf(tmp_path: Any) -> None:
    from argos.locallog import LocalLog

    log = LocalLog(tmp_path)
    log.write({"at": "x", "note": "café"})
    log.write({"at": "y", "note": "two"})
    log.close()
    data = next(tmp_path.iterdir()).read_bytes()
    assert b"\r\n" not in data
    assert data.count(b"\n") == 2
    assert "café".encode() in data


def test_writes_do_not_block_on_a_hanging_backend() -> None:
    """With the threaded writer, a backend that hangs never slows the brain."""
    from argos.writer import RecordWriter

    gate = threading.Event()

    class HangingStore(MemoryStore):
        def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
            gate.wait(5)
            super().insert(table, rows)

        def update(self, table: str, filters: Any, patch: dict[str, Any]) -> int:
            gate.wait(5)
            return super().update(table, filters, patch)

    store = HangingStore()
    writer = RecordWriter(store, threaded=True)
    import time

    started = time.monotonic()
    for i in range(50):
        writer.insert("events", {"id": str(i)})
    assert time.monotonic() - started < 0.5
    gate.set()
    assert writer.flush(5.0)
    writer.close()
    assert len(store.tables["events"]) == 50
