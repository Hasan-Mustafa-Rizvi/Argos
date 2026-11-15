"""One FaceTime call, from an empty room to a freed one.

Order, as Chert's outbound guide asks:

1. Make the room. Put the agent in it with one unmuted audio track (silence) and one video
   track (the picture), both flowing before anything is requested.
2. Mint the bridge token. Ask Chert for the call, with the busy queue (`chert.place`).
3. Watch the call. Speak only after Chert reports `bridge_ready`, and greet once per call
   however many times the signal shows up.
4. End it: when the conversation is done, when the person hangs up, at the time limit, or on
   any error. Ending sits in a `finally`, so a crash still ends the call and frees the room.
5. Add the seconds to the seconds file and print the total.

The limit counts from the moment Chert allocates the call: 60 seconds for a test, 4 minutes
otherwise. It is checked against the program's clock, so tests can run it without sleeping.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from argos_call import chert as chert_mod
from argos_call.clock import Clock
from argos_call.state import Seconds

log = logging.getLogger("argos_call.session")

READY_POLL_S = 0.5
CALL_POLL_S = 2.0
END_WAIT_S = 15.0
CLOSING_LEAD_S = 30.0
AGENT_TOKEN_TTL = datetime.timedelta(minutes=10)
# Chert takes at most two hours and needs more than 90 seconds left when the call is
# allocated. LiveKit's default is six hours, so the lifetime is always set.
BRIDGE_TOKEN_TTL = datetime.timedelta(minutes=30)
READY_WORDS = ("bridge_ready", "call.started")
ANSWER_WORDS = ("answer", "bridge_ready", "call.started", "connected")
END_WORDS = ("ended", "failed", "hangup", "hung_up", "terminated", "cancel", "completed",
             "rejected", "declined", "missed", "no_answer", "timeout")

Say = Callable[[str], None]


class RoomsLike(Protocol):
    url: str

    async def create(self, name: str) -> None: ...

    async def delete(self, name: str) -> None: ...

    def token(self, identity: str, room: str, ttl: Any, name: str = "") -> str: ...


class AgentLike(Protocol):
    identity: str
    on_participant: Any

    async def join(self, url: str, token: str) -> None: ...

    async def say(self, pcm: bytes) -> None: ...

    async def leave(self) -> None: ...


class Conversation(Protocol):
    """What happens once the bridge is ready. `run` returns when the agent is done talking
    (the call is then ended by us). `closing` is said before the limit."""

    async def run(self, agent: Any) -> None: ...

    async def closing(self, agent: Any) -> None: ...


@dataclass
class Plan:
    kind: str  # "test", "incident" or "demo"
    limit_s: float
    attempt_key: str  # Chert's idempotency key for this attempt
    destination: str = field(repr=False)
    line_id: str = ""
    video: bool = True
    room: str = ""
    tries: int = 1  # attempts when Chert says busy without a queue receipt
    retry_wait_s: float = 5.0

    def __post_init__(self) -> None:
        if not self.room:
            self.room = f"argos-{self.kind}-{uuid.uuid4().hex[:10]}"


@dataclass
class Result:
    outcome: str = "not placed"  # placed, waiting, busy, refused, uncertain, not placed
    call_id: str | None = None
    reason: str = ""
    answered: bool = False
    bridge_ready: bool = False
    ended_by: str = ""
    seconds: float = 0.0
    total_seconds: float = 0.0
    chert_events: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)


class Session:
    def __init__(
        self,
        chert: chert_mod.ChertAPI,
        rooms: RoomsLike,
        make_agent: Callable[[str], AgentLike],
        clock: Clock,
        seconds: Seconds,
        say: Say,
        on_answered: Callable[[], Awaitable[None] | None] | None = None,
        on_placed: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> None:
        self.chert = chert
        self.rooms = rooms
        self.make_agent = make_agent
        self.clock = clock
        self.seconds = seconds
        self.say = say
        self.on_answered = on_answered
        self.on_placed = on_placed

    def body(self, plan: Plan, bridge_token: str, agent_identity: str) -> dict[str, Any]:
        return {
            "direction": "outbound",
            "mode": "customer_managed",
            "line_id": plan.line_id,
            "destination": plan.destination,
            "destination_type": "phone",
            "media": {"audio": True, "video": plan.video},
            "livekit_url": self.rooms.url,
            "participant_token": bridge_token,
            "remote_participant_identity": agent_identity,
            "when_busy": "queue",
        }

    async def run(self, plan: Plan, conversation: Conversation) -> Result:
        result = Result()
        suffix = plan.room.rsplit("-", 1)[-1]
        agent = self.make_agent(f"argos-agent-{suffix}")
        bridge_identity = f"chert-bridge-{suffix}"
        allocated_at: float | None = None
        joined = False
        bridge_left = asyncio.Event()

        def participant(remote: Any, present: bool) -> None:
            if getattr(remote, "identity", "") == bridge_identity:
                self.say("the bridge joined the room" if present else "the bridge left the room")
                if not present:
                    bridge_left.set()

        agent.on_participant = participant
        try:
            await self.rooms.create(plan.room)
            await agent.join(self.rooms.url,
                             self.rooms.token(agent.identity, plan.room, AGENT_TOKEN_TTL))
            joined = True
            bridge_token = self.rooms.token(bridge_identity, plan.room, BRIDGE_TOKEN_TTL)
            body = self.body(plan, bridge_token, agent.identity)
            placement = chert_mod.Placement("busy")
            for attempt in range(1, max(1, plan.tries) + 1):
                key = plan.attempt_key if plan.tries <= 1 else f"{plan.attempt_key}-{attempt}"
                placement = await chert_mod.place(self.chert, body, key, self.clock, self.say)
                # One waiting attempt only: after a wait in Chert's queue, never try again.
                if placement.outcome != "busy" or placement.waited or attempt == plan.tries:
                    break
                self.say(f"busy: {placement.reason}; trying again in {plan.retry_wait_s:.0f} s "
                         f"(attempt {attempt + 1} of {plan.tries})")
                await self.clock.sleep(plan.retry_wait_s)
            result.outcome = placement.outcome
            result.reason = placement.reason
            if placement.outcome != "placed" or not placement.call_id:
                self.say(f"{placement.outcome}: {placement.reason or 'no call was placed'}")
                return result
            result.call_id = placement.call_id
            allocated_at = self.clock.now()
            self.say("placed: Chert allocated the call and is dialling")
            if self.on_placed is not None:
                maybe = self.on_placed(placement.call_id)
                if asyncio.iscoroutine(maybe):
                    await maybe
            await self._watch(plan, conversation, agent, result, allocated_at, bridge_left)
            return result
        except asyncio.CancelledError:
            result.ended_by = result.ended_by or "stopped"
            raise
        except Exception as exc:
            result.ended_by = result.ended_by or "error"
            result.reason = result.reason or f"error: {type(exc).__name__}"
            log.error("the call stopped on an error (%s)", type(exc).__name__)
            return result
        finally:
            if result.call_id:
                await self._end(result, plan)
            if joined:
                await agent.leave()
            else:
                await _quietly(agent.leave())
            await self.rooms.delete(plan.room)
            if allocated_at is not None:
                result.seconds = max(0.0, self.clock.now() - allocated_at)
                result.total_seconds = self.seconds.add(result.seconds, self.clock.iso(),
                                                        plan.kind, result.call_id)
                self.say(f"ended ({result.ended_by or 'done'}). seconds used: this call "
                         f"{result.seconds:.0f}, all calls {result.total_seconds:.0f} "
                         f"({result.total_seconds / 60:.1f} of 50 minutes)")

    async def _watch(self, plan: Plan, conversation: Conversation, agent: Any, result: Result,
                     allocated_at: float, bridge_left: asyncio.Event) -> None:
        assert result.call_id is not None
        call_id = result.call_id
        greeted = False
        closing_said = False
        talk: asyncio.Task[None] | None = None
        closing: asyncio.Task[None] | None = None
        next_call_poll = 0.0
        seen: set[str] = set()
        try:
            while True:
                elapsed = self.clock.now() - allocated_at
                if elapsed >= plan.limit_s:
                    result.ended_by = "limit"
                    self.say(f"limit: {plan.limit_s:.0f} seconds reached; ending the call")
                    return
                if (greeted and not closing_said and plan.limit_s > 2 * CLOSING_LEAD_S
                        and elapsed >= plan.limit_s - CLOSING_LEAD_S):
                    closing_said = True
                    if talk is not None and not talk.done():
                        talk.cancel()
                    closing = asyncio.create_task(conversation.closing(agent))
                if closing is not None and closing.done():
                    result.ended_by = "limit"
                    return
                # Chert's events: bridge_ready, answered, ended.
                try:
                    events = await self.chert.events(call_id)
                except chert_mod.ChertError as exc:
                    log.info("could not read the call's events (%s)",
                             self.chert.redactor.mask(exc))
                    events = []
                for event in events:
                    kind = chert_mod.kind_of(event)
                    if kind and kind not in seen:
                        seen.add(kind)
                        result.chert_events.append(kind)
                        self.say(f"chert event: {kind}")
                    if not result.answered and any(w in kind for w in ANSWER_WORDS):
                        result.answered = True
                        self.say("answered")
                        if self.on_answered is not None:
                            maybe = self.on_answered()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                    if any(w in kind for w in READY_WORDS):
                        result.bridge_ready = True
                    if any(w in kind for w in END_WORDS) and "bridge" not in kind:
                        result.ended_by = result.ended_by or "chert"
                if result.ended_by == "chert":
                    self.say("the call ended on Chert's side")
                    return
                if result.bridge_ready and not greeted:
                    greeted = True
                    self.say("bridge ready: speaking")
                    talk = asyncio.create_task(conversation.run(agent))
                if talk is not None and talk.done() and not closing_said:
                    if not talk.cancelled() and talk.exception() is not None:
                        log.error("the conversation stopped (%s)",
                                  type(talk.exception()).__name__)
                    result.ended_by = result.ended_by or "agent"
                    return
                if bridge_left.is_set() and greeted:
                    result.ended_by = "hung up"
                    self.say("the person hung up")
                    return
                if self.clock.now() >= next_call_poll:
                    next_call_poll = self.clock.now() + CALL_POLL_S
                    try:
                        record = await self.chert.call(call_id)
                    except chert_mod.ChertError:
                        record = {}
                    status = str(record.get("status") or record.get("state") or "")
                    if status and (not result.statuses or result.statuses[-1] != status):
                        result.statuses.append(status)
                        self.say(f"chert status: {status}")
                    if record and chert_mod.is_terminal(record):
                        result.ended_by = result.ended_by or "chert"
                        self.say("the call is over on Chert's side")
                        return
                await self.clock.sleep(READY_POLL_S if not greeted else 1.0)
        finally:
            for task in (talk, closing):
                if task is not None and not task.done():
                    task.cancel()
                    await _quietly(task)

    async def _end(self, result: Result, plan: Plan) -> None:
        """Ask Chert to end the call (a separate key), then watch until it is over."""
        assert result.call_id is not None
        call_id = result.call_id
        try:
            record = await self.chert.call(call_id)
        except Exception:
            record = {}
        if not (record and chert_mod.is_terminal(record)):
            status = await self.chert.end_call(call_id, f"{plan.attempt_key}-end")
            self.say(f"asked Chert to end the call (HTTP {status})")
        deadline = self.clock.now() + END_WAIT_S
        while self.clock.now() < deadline:
            try:
                record = await self.chert.call(call_id)
            except Exception:
                record = {}
            if record and chert_mod.is_terminal(record):
                status = str(record.get("status") or record.get("state") or "")
                if status and (not result.statuses or result.statuses[-1] != status):
                    result.statuses.append(status)
                self.say(f"ended on Chert: {status or 'terminal'}")
                timing = {k: v for k, v in record.items()
                          if isinstance(v, (str, int, float)) and any(
                              w in k for w in ("_at", "status", "reason", "duration", "seconds",
                                               "media", "direction"))}
                log.info("chert's record of the call: %s", timing)
                return
            await self.clock.sleep(1.0)
        self.say("Chert has not confirmed the end yet; its own 5 minute limit still applies")


async def end_stale_calls(chert: chert_mod.ChertAPI, say: Say) -> int:
    """At start: end any call of ours that Chert still shows as active."""
    try:
        calls = await chert.calls()
    except chert_mod.ChertError as exc:
        say(f"could not list calls on Chert ({chert.redactor.mask(exc)})")
        return 0
    ended = 0
    for record in calls:
        call_id = str(record.get("id") or "")
        if call_id and not chert_mod.is_terminal(record):
            status = await chert.end_call(call_id, f"argos-stale-end-{call_id}")
            say(f"ended a call still open from before ({call_id[:8]}, HTTP {status})")
            ended += 1
    return ended


async def _quietly(awaitable: Any) -> None:
    try:
        await awaitable
    except (asyncio.CancelledError, Exception):
        pass
