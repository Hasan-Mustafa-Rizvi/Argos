"""The scripted run, against a fake store, compared with contract/fixtures/demo_scenario.jsonl.

Allowed differences: ids and timestamps; confidence values; no `call_answered` (no call is
placed); `"dry_run": true` and dry-run wording on the call and the email; the label "Demo" on
the acknowledgement; the wording of the summary. Anything else is a failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from argos import script
from argos.script import ScriptPlayer
from tests.conftest import Rig, make_rig

FIXTURE = Path(__file__).resolve().parents[2] / "contract" / "fixtures" / "demo_scenario.jsonl"


class StillFrames:
    """Stands in for the camera: a frame object that is not an image of anyone."""

    def latest(self) -> object:
        return "FAKE-FRAME"


def fixture() -> list[dict[str, Any]]:
    with FIXTURE.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="module")
def scripted() -> Rig:
    steps, length = script.from_fixture(FIXTURE)
    rig = make_rig(script=ScriptPlayer(steps, length), frames=StillFrames())

    def upload(incident_id: str, frame: object) -> str:
        path = f"incidents/{incident_id}/snapshot.jpg"
        rig.store.upload("snapshots", path, b"jpeg", "image/jpeg")
        return path

    rig.brain.uploader = upload
    rig.brain.start()
    rig.run_for(length + 1.0)
    return rig


def test_script_read_from_fixture_matches_built_in() -> None:
    steps, length = script.from_fixture(FIXTURE)
    assert steps == script.BUILT_IN
    assert length == script.BUILT_IN_LENGTH_S


def test_same_tables(scripted: Rig) -> None:
    fixture_tables = {line["table"] for line in fixture()}
    brain_tables = {op["table"] for op in scripted.store.ops if not op["table"].startswith(
        "storage:")}
    assert brain_tables == fixture_tables


def test_same_order_of_incident_statuses(scripted: Rig) -> None:
    expected = [line["row"]["status"] for line in fixture() if line["table"] == "incidents"]
    statuses: dict[str, str] = {}
    seen: list[str] = []
    for op in scripted.store.ops:
        if op["table"] != "incidents":
            continue
        if op["op"] == "insert":
            statuses[op["row"]["id"]] = op["row"]["status"]
            seen.append(op["row"]["status"])
        elif op["matched"] > 0:
            incident_id = op["filters"]["id"].removeprefix("eq.")
            statuses[incident_id] = op["patch"].get("status", statuses[incident_id])
            seen.append(statuses[incident_id])
    assert seen == expected


def test_same_order_of_event_kinds(scripted: Rig) -> None:
    expected = [line["row"]["kind"] for line in fixture() if line["table"] == "events"]
    expected.remove("call_answered")  # no call is placed, so nobody answers one
    assert scripted.event_kinds() == expected


def test_same_order_of_device_states(scripted: Rig) -> None:
    def collapse(states: list[str]) -> list[str]:
        return [s for i, s in enumerate(states) if i == 0 or states[i - 1] != s]

    expected = collapse([line["row"]["state"] for line in fixture() if line["table"] ==
                         "devices"])
    seen = collapse([op["patch"]["state"] for op in scripted.store.ops
                     if op["table"] == "devices" and "state" in op["patch"]])
    assert seen == expected


def test_same_columns_in_every_inserted_row(scripted: Rig) -> None:
    expected: dict[str, set[tuple[str, ...]]] = {}
    for line in fixture():
        if line["op"] == "insert":
            expected.setdefault(line["table"], set()).add(tuple(sorted(line["row"])))
    seen: dict[str, set[tuple[str, ...]]] = {}
    for op in scripted.store.ops:
        if op["op"] == "insert":
            seen.setdefault(op["table"], set()).add(tuple(sorted(op["row"])))
    assert seen == expected


def test_event_rows_match_except_allowed_differences(scripted: Rig) -> None:
    expected = [line["row"] for line in fixture() if line["table"] == "events"
                and line["row"]["kind"] != "call_answered"]
    for want, got in zip(expected, scripted.store.tables["events"], strict=True):
        kind = want["kind"]
        assert got["kind"] == kind
        want_detail, got_detail = dict(want["detail"]), dict(got["detail"])
        if kind == "trigger":
            want_detail.pop("confidence")
            got_detail.pop("confidence")
        if kind in ("call_placed", "email_sent"):
            assert got_detail.pop("dry_run") is True
            want_detail.pop("dry_run")
            assert "Dry run" in got["text"]
            assert got_detail == want_detail
            continue
        if kind == "acknowledged":
            assert got_detail == {"by": "Demo"}
            assert got["text"] == want["text"].replace("Daughter", "Demo")
            continue
        assert got_detail == want_detail
        assert got["text"] == want["text"]
        assert (got["incident_id"] is None) == (want["incident_id"] is None)


def test_final_incidents_match_except_allowed_differences(scripted: Rig) -> None:
    final: dict[str, dict[str, Any]] = {}
    for line in fixture():
        if line["table"] == "incidents":
            final[line["row"]["id"]] = line["row"]
    expected = list(final.values())
    got = scripted.store.tables["incidents"]
    assert len(got) == len(expected)
    ignore = {"id", "confidence", "started_at", "ended_at", "acknowledged_at", "summary",
              "snapshot_path", "acknowledged_by"}
    for want, have in zip(expected, got, strict=True):
        assert {k: v for k, v in have.items() if k not in ignore} == {
            k: v for k, v in want.items() if k not in ignore}
        assert (have["ended_at"] is None) == (want["ended_at"] is None)
        assert (have["summary"] is None) == (want["summary"] is None)
        assert (have["snapshot_path"] is None) == (want["snapshot_path"] is None)
        if have["snapshot_path"]:
            assert have["snapshot_path"] == f"incidents/{have['id']}/snapshot.jpg"
        if want["acknowledged_by"]:
            assert have["acknowledged_by"] == "Demo"
            assert have["ended_at"] == have["acknowledged_at"]


def test_escalation_waits_from_the_question(scripted: Rig) -> None:
    events = {e["kind"]: e for e in scripted.store.tables["events"][5:]}
    asked, escalated = events["asked"]["at"], events["escalated"]["at"]
    from datetime import datetime

    def parse(stamp: str) -> datetime:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))

    assert (parse(escalated) - parse(asked)).total_seconds() == pytest.approx(10.0, abs=0.11)
