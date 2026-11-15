"""The call itself: silent until ready, one greeting, the limit, a crash, the busy line."""

from __future__ import annotations

import asyncio

import pytest

from argos_call import session
from argos_call.clock import FakeClock
from argos_call.state import Seconds
from tests.fakes import FakeAgent, FakeChertServer, FakeRooms, chert_api


class Talk:
    """Says one line when run; never finishes on its own if `hold` is set."""

    def __init__(self, hold: bool = False, crash: bool = False,
                 hold_closing: bool = False) -> None:
        self.runs = 0
        self.closings = 0
        self.hold = hold
        self.crash = crash
        self.hold_closing = hold_closing

    async def run(self, agent: FakeAgent) -> None:
        self.runs += 1
        await agent.say(b"\x00\x01" * 10)
        if self.crash:
            raise RuntimeError("boom")
        if self.hold:
            await asyncio.Event().wait()

    async def closing(self, agent: FakeAgent) -> None:
        self.closings += 1
        await agent.say(b"\x02\x03")
        if self.hold_closing:
            await asyncio.Event().wait()


def run_call(server: FakeChertServer, talk: Talk, tmp_path, limit: float = 60.0,
             kind: str = "test"):
    clock = FakeClock()
    rooms = FakeRooms()
    agents: list[FakeAgent] = []

    def make(identity: str) -> FakeAgent:
        agents.append(FakeAgent(identity))
        return agents[-1]

    async def go():
        api = chert_api(server)
        runner = session.Session(api, rooms, make, clock, Seconds(tmp_path), lambda m: None)
        plan = session.Plan(kind=kind, limit_s=limit, attempt_key="argos-incident-call-1",
                            destination="+15559876543", line_id="line-1")
        try:
            return await runner.run(plan, talk)
        finally:
            await api.aclose()

    result = asyncio.run(go())
    return result, rooms, agents[0], clock


def test_silent_until_bridge_ready_then_one_greeting(tmp_path):
    server = FakeChertServer(ready_after_polls=4)
    server.ready_twice = True
    talk = Talk()
    result, rooms, agent, _ = run_call(server, talk, tmp_path)
    assert result.outcome == "placed"
    assert result.bridge_ready
    assert talk.runs == 1  # the signal arrived on several polls, and twice in one poll
    assert len(agent.said) == 1
    assert server.ended  # we ended it once the line was said
    assert rooms.deleted == rooms.created
    assert agent.left


def test_nothing_is_said_when_the_bridge_never_gets_ready(tmp_path):
    server = FakeChertServer(ready_after_polls=10_000)
    talk = Talk()
    result, _, agent, clock = run_call(server, talk, tmp_path, limit=60)
    assert talk.runs == 0
    assert agent.said == []
    assert result.ended_by == "limit"
    assert server.ended


def test_the_agent_says_goodbye_before_the_limit_and_ends_the_call(tmp_path):
    server = FakeChertServer(ready_after_polls=1)
    talk = Talk(hold=True)
    result, rooms, agent, clock = run_call(server, talk, tmp_path, limit=240, kind="incident")
    assert result.ended_by == "limit"
    assert talk.closings == 1  # it says it has to hang up, 30 seconds before the limit
    assert server.ended
    assert 200 <= result.seconds <= 240
    assert rooms.deleted == rooms.created and agent.left


def test_a_call_nobody_ends_is_ended_by_the_hard_limit(tmp_path):
    server = FakeChertServer(ready_after_polls=1)
    talk = Talk(hold=True, hold_closing=True)
    result, rooms, agent, clock = run_call(server, talk, tmp_path, limit=240, kind="incident")
    assert result.ended_by == "limit"
    assert server.ended
    assert 240 <= result.seconds < 260  # the limit, plus the end being confirmed
    assert rooms.deleted == rooms.created and agent.left


def test_a_crash_still_ends_the_call_and_frees_the_room(tmp_path):
    server = FakeChertServer(ready_after_polls=1)
    talk = Talk(crash=True)
    result, rooms, agent, _ = run_call(server, talk, tmp_path)
    assert server.ended
    assert rooms.deleted == rooms.created
    assert agent.left
    assert Seconds(tmp_path).used() > 0


def test_seconds_add_up_across_runs(tmp_path):
    for _ in range(3):
        server = FakeChertServer(ready_after_polls=1)
        run_call(server, Talk(), tmp_path)
    data = Seconds(tmp_path)
    assert len(__import__("json").loads(data.path.read_text())["calls"]) == 3
    assert data.used() > 3


def test_busy_line_waits_then_places(tmp_path):
    server = FakeChertServer(ready_after_polls=1, queue_then_ready=True)
    result, _, _, _ = run_call(server, Talk(), tmp_path)
    assert result.outcome == "placed"
    creates = server.creates()
    assert len(creates) == 2  # the receipt said ready, so the same request went again
    assert creates[0]["key"] == creates[1]["key"] == "argos-incident-call-1"
    assert creates[0]["body"] == creates[1]["body"]


def test_busy_every_time_places_nothing_and_counts_no_seconds(tmp_path):
    server = FakeChertServer(busy=True)
    result, rooms, agent, _ = run_call(server, Talk(), tmp_path)
    assert result.outcome == "busy"
    assert "line_in_use" in result.reason
    assert result.seconds == 0
    assert not server.ended
    assert rooms.deleted == rooms.created and agent.left


def test_refused_video_reports_why(tmp_path):
    server = FakeChertServer(refuse="Outbound video is not enabled for this line")
    result, _, _, _ = run_call(server, Talk(), tmp_path)
    assert result.outcome == "refused"
    assert "video_not_enabled" in result.reason


@pytest.mark.parametrize("words", ["call.ended", "call.failed"])
def test_person_hangs_up(tmp_path, words):
    server = FakeChertServer(ready_after_polls=1, end_after_polls=3)
    result, rooms, agent, _ = run_call(server, Talk(hold=True), tmp_path, limit=240)
    assert result.ended_by == "chert"
    assert rooms.deleted == rooms.created and agent.left
