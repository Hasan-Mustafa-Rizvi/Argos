"""The parts on their own: masking, Chert's client, the live view, the picture, hearing,
the rule 6 filter, the backend's requests, the state files and the settings."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from argos_call import config
from argos_call.answers import UNKNOWN, safe_reply
from argos_call.backend import Supabase
from argos_call.chert import ChertAPI, kind_of, place
from argos_call.clock import FakeClock
from argos_call.hearing import Utterances, is_ack
from argos_call.incident import Incident, clean, greeting, text_message
from argos_call.liveview import FrameGate, LiveView
from argos_call.picture import Picture, Screen
from argos_call.redact import MASK, MaskingFilter, Redactor
from argos_call.state import Handled, Seconds, StateError
from tests.fakes import FAKE_CHERT_KEY, FAKE_NUMBER, FAKE_TOKEN, env, marker_jpeg, speech_burst

# ---------------------------------------------------------------------- masking


@pytest.mark.parametrize("written", [
    "+15559876543", "15559876543", "5559876543", "+1 555 987 6543", "(555) 987-6543",
    "555.987.6543", "%2B15559876543", "+1-555-987-6543",
])
def test_the_number_is_masked_however_it_is_written(written):
    redactor = Redactor()
    redactor.add_phone(FAKE_NUMBER)
    assert "987" not in redactor.mask(f"calling {written} now").replace(MASK, "")


def test_keys_and_tokens_are_masked_even_unregistered():
    redactor = Redactor()
    text = f"key {FAKE_CHERT_KEY} token {FAKE_TOKEN} other sb_secret_abcdefgh12345678"
    masked = redactor.mask(text)
    assert FAKE_CHERT_KEY not in masked and FAKE_TOKEN not in masked
    assert "sb_secret_abcdefgh" not in masked


def test_log_records_and_their_exceptions_are_masked():
    redactor = Redactor()
    redactor.add_secret("s3cr3t-value-123")
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed with %s",
                               ("s3cr3t-value-123",), None)
    try:
        raise RuntimeError("boom s3cr3t-value-123")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    MaskingFilter(redactor).filter(record)
    assert "s3cr3t" not in record.getMessage()
    assert "s3cr3t" not in (record.exc_text or "")


# ---------------------------------------------------------------------- Chert


def _api(handler) -> ChertAPI:
    return ChertAPI("https://facetime.trychert.com/api", FAKE_CHERT_KEY, "p",
                    Redactor(), transport=httpx.MockTransport(handler))


def test_an_uncertain_answer_is_followed_only_by_the_same_request_with_the_same_key():
    seen: list[tuple[str | None, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers.get("idempotency-key"), request.content))
        if len(seen) < 2:
            return httpx.Response(503, json={"error": {"code": "unavailable"}})
        return httpx.Response(201, json={"data": {"id": "call-9"}})

    async def go():
        api = _api(handler)
        try:
            return await place(api, {"a": 1}, "argos-x-call-1", FakeClock(), lambda m: None)
        finally:
            await api.aclose()

    placement = asyncio.run(go())
    assert placement.outcome == "placed" and placement.call_id == "call-9"
    assert len(seen) == 2 and seen[0] == seen[1]


def test_redirects_are_not_followed_so_the_key_stays_with_chert():
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(307, headers={"location": "https://elsewhere.example/v1/calls"})

    async def go():
        api = _api(handler)
        try:
            return await api.create_call({}, "argos-key-123")
        finally:
            await api.aclose()

    asyncio.run(go())
    assert hosts == ["facetime.trychert.com"]


def test_only_chert_addresses_are_accepted_for_the_api(tmp_path):
    settings = config.from_env(env(tmp_path, CHERT_API_BASE="https://evil.example/api"))
    assert settings.chert_base in config.CHERT_BASES


def test_event_kinds_are_read_whatever_the_field():
    assert "bridge_ready" in kind_of({"type": "call.lifecycle", "name": "bridge_ready"})
    assert kind_of({"event_type": "Answered"}) == "answered"


# ---------------------------------------------------------------------- the live view


def _frame(seq: int) -> dict:
    return {"seq": seq, "at": "2026-11-15T19:00:00.000Z", "w": 32, "h": 24,
            "jpeg": base64.b64encode(marker_jpeg()).decode()}


def test_a_lower_seq_is_dropped_until_the_view_has_stopped():
    clock = FakeClock()
    gate = FrameGate(clock)
    assert gate.accept(_frame(10)) is not None
    assert gate.accept(_frame(9)) is None
    clock.advance(5.0)  # no frame for 5 seconds: the view has stopped, seq is forgotten
    assert gate.accept(_frame(0)) is not None


def test_the_live_view_reads_broadcast_frames_only():
    clock = FakeClock()
    shown: list[bytes] = []
    view = LiveView("https://x.supabase.co", "sb_secret_x", "dev", shown.append, clock)
    view.handle(json.dumps({"event": "phx_reply", "ref": "1",
                            "payload": {"status": "ok", "response": {}}}))
    view.handle(json.dumps({"event": "broadcast", "payload": {"event": "frame",
                                                              "payload": _frame(1)}}))
    view.handle(json.dumps({"event": "broadcast", "payload": {"event": "other",
                                                              "payload": _frame(2)}}))
    view.handle("not json")
    assert view.joined and len(shown) == 1


# ---------------------------------------------------------------------- the picture


def test_frames_arriving_are_shown_then_the_snapshot_then_the_card():
    clock = FakeClock()
    picture = Picture(320, 180)
    screen = Screen(picture, "3:41 PM", clock.now)
    assert screen.kind == "card"  # neither: the card
    screen.set_snapshot(marker_jpeg())
    assert screen.kind == "snapshot"  # no frames: the snapshot
    screen.live(marker_jpeg())
    assert screen.kind == "live" and screen.latest_live  # frames: shown
    clock.advance(5.0)
    screen.tick()
    assert screen.kind == "snapshot" and screen.latest_live is None
    assert len(picture.rgba()) == 320 * 180 * 4  # one fixed size, always


def test_an_unreadable_snapshot_leaves_the_card():
    screen = Screen(Picture(320, 180), "3:41 PM", FakeClock().now)
    screen.set_snapshot(b"not a jpeg")
    assert screen.kind == "card"


# ---------------------------------------------------------------------- hearing


def test_an_utterance_is_cut_from_speech_and_nothing_is_heard_while_argos_talks():
    clock = FakeClock()
    ears = Utterances(clock.now)
    ears.quiet_until = float("inf")  # Argos is talking
    ears.push(speech_burst())
    assert ears.out.empty()
    ears.quiet_until = 0.0
    ears.push(speech_burst())
    assert ears.out.qsize() == 1


@pytest.mark.parametrize("phrase,ack", [
    ("[unk] i'm on my way", True), ("acknowledge", True), ("i'll take it from here", True),
    ("[unk] right now", False), ("[unk]", False), ("", False),
])
def test_only_first_person_phrases_acknowledge(phrase, ack):
    assert is_ack(phrase) is ack


# ---------------------------------------------------------------------- rule 6


@pytest.mark.parametrize("reply", [
    "She is fine.", "She seems okay to me.", "Eleni is hurt.", "She might be unconscious.",
    "It looks like a stroke.", "You should lift her up.", "She is breathing.",
])
def test_a_reply_that_diagnoses_or_advises_becomes_i_dont_know(reply):
    assert safe_reply(reply) == UNKNOWN


@pytest.mark.parametrize("reply", [
    "At 3:41 PM I saw what looked like a fall. I asked if Eleni was okay and got no answer.",
    "I do not know. If you think it is needed, call emergency services.",
    "A person is lying on the floor next to the sofa.",
])
def test_a_reply_that_keeps_to_the_incident_is_spoken(reply):
    assert safe_reply(reply) == reply


def test_the_lines_carry_no_dash_and_no_pronoun_for_the_person():
    incident = Incident("x", "fall", datetime(2026, 11, 15, 21, 41, tzinfo=UTC),
                        person="Eleni — test")
    for line in (greeting(incident), text_message(incident)):
        assert "—" not in line and "–" not in line
        assert " she " not in f" {line.lower()} " and " he " not in f" {line.lower()} "
    assert clean("a — b – c") == "a, b, c"


# ---------------------------------------------------------------------- the backend


def test_the_acknowledgement_request_is_the_dashboards():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])  # no row back: someone was first

    async def go():
        backend = Supabase("https://x.supabase.co", "sb_secret_abcdefghijk", Redactor(),
                           transport=httpx.MockTransport(handler))
        try:
            return await backend.acknowledge("inc-1", "Daughter, by FaceTime",
                                             "2026-11-15T19:01:00.000Z")
        finally:
            await backend.aclose()

    assert asyncio.run(go()) is False
    request = seen[0]
    assert request.method == "PATCH" and request.url.path == "/rest/v1/incidents"
    assert dict(request.url.params) == {"id": "eq.inc-1", "status": "eq.escalated",
                                        "select": "id"}
    assert json.loads(request.content) == {"status": "acknowledged",
                                           "acknowledged_by": "Daughter, by FaceTime",
                                           "acknowledged_at": "2026-11-15T19:01:00.000Z"}
    assert request.headers["prefer"] == "return=representation"
    assert request.headers["apikey"] and "authorization" not in request.headers


def test_events_are_inserted_like_the_brain_does():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    async def go():
        backend = Supabase("https://x.supabase.co", "sb_secret_abcdefghijk", Redactor(),
                           transport=httpx.MockTransport(handler))
        try:
            await backend.add_event({"id": "e1", "kind": "call_placed"})
        finally:
            await backend.aclose()

    asyncio.run(go())
    assert seen[0].url.params["on_conflict"] == "id"
    assert seen[0].headers["prefer"] == "return=minimal,resolution=ignore-duplicates"


# ---------------------------------------------------------------------- the state files


def test_a_step_is_claimed_once_ever(tmp_path):
    handled = Handled(tmp_path)
    assert handled.claim("inc", "call", "t0")
    assert not handled.claim("inc", "call", "t1")
    assert not Handled(tmp_path).claim("inc", "call", "t2")  # after a restart too


def test_a_damaged_handled_list_is_refused_not_guessed(tmp_path):
    (tmp_path / "handled.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError):
        Handled(tmp_path).claim("inc", "call", "t0")


def test_the_seconds_file_refuses_past_the_budget_unless_demo(tmp_path):
    seconds = Seconds(tmp_path)
    seconds.add(1799, "t", "test", "c1")
    assert seconds.refuse(1800, demo=False) is None
    seconds.add(2, "t", "test", "c2")
    assert seconds.refuse(1800, demo=False)
    assert seconds.refuse(1800, demo=True) is None


# ---------------------------------------------------------------------- the settings


def test_secret_settings_never_show_in_repr(tmp_path):
    settings = config.from_env(env(tmp_path))
    text = repr(settings)
    assert FAKE_CHERT_KEY not in text and FAKE_NUMBER not in text
