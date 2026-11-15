"""The seven rules, the busy line, the acknowledgement, missing keys and old news, each on a
whole run of the call agent against fakes. No test touches the network or places a call."""

from __future__ import annotations

import json
import os
from datetime import timedelta

import pytest

from argos_call import config
from argos_call.state import Seconds
from tests.fakes import (
    FAKE_CHERT_KEY,
    FAKE_ELEVEN_KEY,
    FAKE_GEMINI_KEY,
    FAKE_LIVEKIT_SECRET,
    FAKE_NUMBER,
    FAKE_SUPABASE_KEY,
    FAKE_TOKEN,
    MARKER_FRAME_TEXT,
    MARKER_PHRASE,
    FakeChertServer,
    FakePhrases,
    env,
)
from tests.harness import BASE, escalated_incident, make_run

SECRETS = [FAKE_NUMBER, FAKE_NUMBER.lstrip("+"), FAKE_NUMBER[2:], FAKE_CHERT_KEY,
           FAKE_LIVEKIT_SECRET, FAKE_TOKEN, FAKE_SUPABASE_KEY, FAKE_GEMINI_KEY, FAKE_ELEVEN_KEY]


def creates(server: FakeChertServer) -> list[dict]:
    return server.creates()


def texts(server: FakeChertServer) -> list[dict]:
    return [r for r in server.requests if r["path"].endswith("/v1/shared-messages")]


# ---------------------------------------------------------------------- rule 1


@pytest.mark.parametrize("value", [None, "1", "", "yes", "true", "off", "00", " 1 "])
def test_rule1_anything_but_0_is_dry_run(tmp_path, value):
    run = make_run(tmp_path, ARGOS_DRY_RUN=value)
    assert run.settings.dry_run
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    assert run.server.requests == []  # nothing at all reached Chert
    sent = run.events("message_sent")
    placed = run.events("call_placed")
    assert len(sent) == 1 and sent[0]["detail"] == {"channel": "imessage", "to": "Daughter",
                                                    "dry_run": True}
    assert len(placed) == 1 and placed[0]["detail"] == {"channel": "facetime", "to": "Daughter",
                                                        "dry_run": True}
    assert "would text Daughter" in run.logs.getvalue()
    assert "would call Daughter" in run.logs.getvalue()


def test_rule1_only_0_sends(tmp_path):
    run = make_run(tmp_path, ARGOS_DRY_RUN="0")
    assert not run.settings.dry_run
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    assert len(texts(run.server)) == 1
    assert len(creates(run.server)) == 1
    assert run.events("call_placed")[0]["detail"]["dry_run"] is False
    assert run.events("message_sent")[0]["detail"]["dry_run"] is False


# ---------------------------------------------------------------------- rule 2


def test_rule2_past_the_budget_a_real_call_is_refused_without_the_demo_flag(tmp_path):
    Seconds(tmp_path).add(config.BUDGET_S, "2026-11-15T18:00:00.000Z", "test", "old")
    run = make_run(tmp_path)
    run.build(demo=False)
    escalated_incident(run.backend, BASE)
    run.once()
    assert creates(run.server) == []
    failed = run.events("call_failed")
    assert failed and failed[0]["detail"]["reason"] == "the test minutes are used up"


def test_rule2_the_demo_flag_allows_the_judged_demo_past_the_budget(tmp_path):
    Seconds(tmp_path).add(config.BUDGET_S, "2026-11-15T18:00:00.000Z", "test", "old")
    run = make_run(tmp_path)
    run.build(demo=True)
    escalated_incident(run.backend, BASE)
    run.once()
    assert len(creates(run.server)) == 1
    assert run.events("call_answered")


# ---------------------------------------------------------------------- rule 3


def test_rule3_three_arrivals_and_a_restart_give_one_text_and_one_call(tmp_path):
    never = FakePhrases(ack_on=lambda n: False)  # nobody acknowledges: it stays escalated
    run = make_run(tmp_path, phrases=never, answers=None)
    run.build()
    incident_id = escalated_incident(run.backend, BASE)
    run.once()
    run.once()  # the same record again
    assert run.backend.incidents[incident_id]["status"] == "escalated"
    restarted = make_run(tmp_path, phrases=never, answers=None)  # a restart: same files
    restarted.server, restarted.backend = run.server, run.backend
    restarted.build()
    restarted.once()  # and a third time
    assert len(texts(run.server)) == 1
    keys = {r["key"] for r in creates(run.server)}
    assert keys == {f"argos-{incident_id}-call-1"}
    handled = json.loads((tmp_path / "handled.json").read_text())
    assert handled[incident_id]["text"]["outcome"] == "sent"
    assert handled[incident_id]["call"]["outcome"] == "answered"


def test_rule3_an_incident_escalated_three_minutes_before_start_is_ignored(tmp_path):
    run = make_run(tmp_path)
    run.build()
    escalated_incident(run.backend, BASE - timedelta(minutes=3))
    run.once()
    run.once()
    assert run.server.requests == []
    assert run.events() == []
    assert "old news" in run.logs.getvalue()


def test_old_news_age_comes_from_the_escalated_event_not_the_start(tmp_path):
    run = make_run(tmp_path)
    run.build()
    # Started ten minutes ago (a long stillness check), escalated 30 seconds ago: call.
    fresh = escalated_incident(run.backend, BASE - timedelta(seconds=30),
                               started_at=BASE - timedelta(minutes=10))
    run.once()
    assert len(creates(run.server)) == 1
    # Started one minute ago but its escalated event is three minutes old: ignore.
    run2 = make_run(tmp_path / "second")
    (tmp_path / "second").mkdir(exist_ok=True)
    run2.build()
    escalated_incident(run2.backend, BASE - timedelta(minutes=3),
                       started_at=BASE - timedelta(minutes=1))
    run2.once()
    assert run2.server.requests == []
    assert fresh


# ---------------------------------------------------------------------- rule 4


def test_rule4_no_number_key_or_token_in_any_log_record_or_error(tmp_path):
    server = FakeChertServer(echo_secrets=True, refuse="Outbound video is not enabled")
    server.refuse_message = "Recipient has not texted the line in the last 24 hours"
    run = make_run(tmp_path, server=server)
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    written = run.everything_written()
    assert "was refused" in written and "call_failed" in written  # the errors were recorded
    for secret in SECRETS:
        assert secret not in written, f"a secret leaked: {secret[:6]}..."


def test_rule4_a_placed_call_whose_records_repeat_the_number_and_token(tmp_path):
    server = FakeChertServer(ready_after_polls=2, echo_secrets=True)
    run = make_run(tmp_path, server=server)
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    assert run.events("call_answered")
    written = run.everything_written()
    for secret in SECRETS:
        assert secret not in written, f"a secret leaked: {secret[:6]}..."


# ---------------------------------------------------------------------- rule 5


def test_rule5_a_whole_call_leaves_only_the_two_state_files_and_no_marker(tmp_path, monkeypatch):
    folder = tmp_path / "empty"
    folder.mkdir()
    monkeypatch.chdir(folder)  # anything written by mistake to "here" would show up too
    run = make_run(folder)
    run.build(live=True)
    escalated_incident(run.backend, BASE)
    run.once()
    assert run.lives and run.lives[0].started and run.lives[0].stopped
    assert run.answers.cameras[0] is not None  # Gemini was shown the marker frame, in memory
    assert run.answers.calls == 2 and run.backend.incidents  # the marker phrase was spoken
    assert sorted(os.listdir(folder)) == ["handled.json", "seconds.json"]
    for name, text in run.files().items():
        assert MARKER_PHRASE not in text, name
        assert MARKER_FRAME_TEXT.decode() not in text, name
    assert MARKER_PHRASE not in run.logs.getvalue()
    assert MARKER_FRAME_TEXT.decode() not in run.logs.getvalue()


# ---------------------------------------------------------------------- the busy line


def test_busy_every_time_gives_call_failed_and_the_program_keeps_running(tmp_path):
    run = make_run(tmp_path, server=FakeChertServer(busy=True))
    run.build()
    incident_id = escalated_incident(run.backend, BASE)
    run.once()
    attempts = creates(run.server)
    assert [r["key"] for r in attempts] == [f"argos-{incident_id}-call-{n}" for n in (1, 2, 3)]
    failed = run.events("call_failed")
    assert len(failed) == 1 and failed[0]["detail"]["reason"] == "the line was busy"
    assert not run.events("call_placed")
    escalated_incident(run.backend, BASE)  # still watching: the next look runs normally
    run.once()
    assert len(run.events("message_sent")) == 2


# ---------------------------------------------------------------------- the acknowledgement


def test_the_call_acknowledges_with_the_label_and_three_columns_only(tmp_path):
    run = make_run(tmp_path)
    run.build()
    incident_id = escalated_incident(run.backend, BASE)
    run.once()
    assert run.backend.updates == [{
        "incident_id": incident_id, "filter_status": "escalated",
        "patch": {"status": "acknowledged", "acknowledged_by": "Daughter, by FaceTime",
                  "acknowledged_at": run.backend.updates[0]["patch"]["acknowledged_at"]}}]
    assert set(run.backend.updates[0]["patch"]) == {"status", "acknowledged_by",
                                                    "acknowledged_at"}
    assert run.events("acknowledged") == []  # the brain writes that, not the call agent
    assert run.caller and run.caller.last_talk and run.caller.last_talk.acknowledged == "done"


def test_an_already_acknowledged_incident_is_reported_as_done_by_someone_else(tmp_path):
    run = make_run(tmp_path)
    run.build()
    incident_id = escalated_incident(run.backend, BASE)
    original = run.backend.acknowledge

    async def someone_was_first(iid: str, by: str, at: str) -> bool:
        run.backend.incidents[iid]["status"] = "acknowledged"  # the dashboard got there first
        return await original(iid, by, at)

    run.backend.acknowledge = someone_was_first  # type: ignore[method-assign]
    run.once()
    assert run.caller and run.caller.last_talk and run.caller.last_talk.acknowledged == "already"
    # The update was filtered to `escalated`, matched nothing, and wrote nothing of ours.
    assert run.backend.updates[0]["filter_status"] == "escalated"
    assert "acknowledged_by" not in run.backend.incidents[incident_id]
    assert run.events("acknowledged") == []


# ---------------------------------------------------------------------- missing keys


@pytest.mark.parametrize("missing", ["CHERT_API_KEY", "CHERT_PROJECT_ID", "CONTACT_FACETIME_TO",
                                     "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"])
def test_no_chert_or_livekit_setting_means_dry_run_only(tmp_path, missing):
    run = make_run(tmp_path, **{missing: None})
    real, why = run.settings.can_call_for_real()
    assert not real and why
    assert any(line.startswith(missing) for line in run.settings.missing())
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    assert creates(run.server) == []
    assert run.events("call_placed")[0]["detail"]["dry_run"] is True


@pytest.mark.parametrize("missing", ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"])
def test_no_elevenlabs_setting_means_no_real_call(tmp_path, missing):
    run = make_run(tmp_path, **{missing: None})
    real, why = run.settings.can_call_for_real()
    assert not real and "ELEVENLABS" in why
    run.build()
    escalated_incident(run.backend, BASE)
    run.once()
    assert creates(run.server) == []


def test_no_gemini_key_the_call_still_speaks_shows_and_acknowledges(tmp_path):
    run = make_run(tmp_path, answers=None, GEMINI_API_KEY=None)
    assert any(line.startswith("GEMINI_API_KEY") for line in run.settings.missing())
    assert run.settings.can_call_for_real()[0]
    run.build(live=False)
    incident_id = escalated_incident(run.backend, BASE, snapshot=b"not a real jpeg")
    run.once()
    talk = run.caller.last_talk if run.caller else None
    assert talk is not None and talk.greetings == 1  # it spoke
    assert run.caller.picture.kind == "card"  # it showed (an unreadable snapshot: the card)
    assert run.backend.incidents[incident_id]["status"] == "acknowledged"  # by the phrases
    assert run.events("call_answered")


def test_no_backend_settings_are_reported_and_the_made_up_escalation_still_runs(tmp_path):
    settings = config.from_env(env(tmp_path, SUPABASE_URL=None, SUPABASE_SERVICE_ROLE_KEY=None))
    assert not settings.backend_configured
    assert any("made-up escalation still runs" in line for line in settings.missing())
