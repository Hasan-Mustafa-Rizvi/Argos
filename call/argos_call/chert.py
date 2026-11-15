"""Chert's FaceTime API, over plain HTTP.

Base address `https://facetime.trychert.com/api` (Chert's FaceTime pages) or
`https://app.trychert.com/api` (its agent handbook); both answer the same API. Every request
carries the project key and the project id; every POST carries an idempotency key:

    Authorization: Bearer <CHERT_API_KEY>      (project key, facetime:read and facetime:write)
    X-Chert-Project-Id: <CHERT_PROJECT_ID>
    Idempotency-Key: <8 to 200 characters>     (POST only)

Redirects are never followed, so the key cannot be carried to another host. Every message
built from an answer is masked, because an answer can repeat what was sent.

What a call request can come back as, in plain words:

- `placed`: HTTP 201. Allocated, not yet answered. `call_id` is Chert's id for it.
- `waiting`: HTTP 202 with `queued: true`. The line is busy and Chert holds a place in its
  queue. Nothing is placed: we ask about the receipt until it is `ready`, then send the very
  same request again, with the same key, within its 20 second turn.
- `busy`: the line is in use and no queue place was given (or the wait ran out).
- `refused`: any other 4xx. `reason` says why, masked.
- `uncertain`: no answer, or a 5xx. Only the same request with the same key may follow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from argos_call.clock import Clock
from argos_call.redact import Redactor

log = logging.getLogger("argos_call.chert")

QUEUE_POLL_S = 2.0
QUEUE_WAIT_S = 150.0  # Chert holds a place for about two minutes; a little margin
TERMINAL = {
    "ended", "completed", "complete", "failed", "canceled", "cancelled", "rejected",
    "declined", "busy", "no_answer", "unanswered", "timeout", "timed_out", "expired",
    "missed", "terminated", "error", "hung_up",
}
BUSY_WORDS = ("busy", "in_use", "in_call", "occupied")


@dataclass
class Placement:
    outcome: str  # placed, waiting, busy, refused, uncertain
    call_id: str | None = None
    queue_id: str | None = None
    reason: str = ""
    status: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    waited: bool = False  # this outcome came after a wait in Chert's busy queue


@dataclass
class Sent:
    ok: bool
    status: int
    reason: str = ""
    message_id: str | None = None


def _data(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        inner = body.get("data")
        if isinstance(inner, dict):
            return inner
        return body
    return {}


def _items(body: Any) -> list[dict[str, Any]]:
    """`{"data": {"items": [...]}}`, `{"data": [...]}` or `[...]`."""
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        inner = body.get("data", body)
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
        if isinstance(inner, dict):
            for key in ("items", "events", "calls", "lines", "messages"):
                if isinstance(inner.get(key), list):
                    return [item for item in inner[key] if isinstance(item, dict)]
    return []


def error_of(response: httpx.Response) -> tuple[str, str]:
    """(code, message) from `{"error": {"code": ..., "message": ...}}`, as plain strings."""
    try:
        body = response.json()
    except ValueError:
        return "", ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("code") or ""), str(error.get("message") or "")
    if isinstance(error, str):
        return error, str(body.get("message") or "")
    return "", ""


def kind_of(event: dict[str, Any]) -> str:
    """An event's type, whatever the field is called. Several naming fields are joined, so a
    match on any of them is found."""
    names = []
    for key in ("type", "event_type", "event", "name", "kind", "code", "phase"):
        value = event.get(key)
        if isinstance(value, str) and value and value.lower() not in names:
            names.append(value.lower())
    return "|".join(names)


def is_terminal(call: dict[str, Any]) -> bool:
    status = str(call.get("status") or call.get("state") or "").lower()
    if status in TERMINAL:
        return True
    return bool(call.get("ended_at") or call.get("terminal") is True)


class ChertAPI:
    def __init__(
        self,
        base: str,
        api_key: str,
        project_id: str,
        redactor: Redactor,
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.redactor = redactor
        self._client = httpx.AsyncClient(
            base_url=base.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "X-Chert-Project-Id": project_id,
                     "User-Agent": "argos-call"},
            timeout=timeout_s,
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ plumbing

    def _why(self, response: httpx.Response) -> str:
        """Why Chert said no, masked first and only then cut to length, so a secret can
        never be half-cut out of reach of the mask."""
        code, message = error_of(response)
        parts = [f"HTTP {response.status_code}"]
        if code:
            parts.append(code)
        if message:
            parts.append(message)
        return self.redactor.mask(": ".join(parts))[:240]

    async def _get(self, path: str, **params: Any) -> httpx.Response:
        return await self._client.get(path, params=params or None)

    async def _post(self, path: str, body: dict[str, Any], key: str) -> httpx.Response:
        return await self._client.post(path, json=body, headers={"Idempotency-Key": key})

    async def _get_json(self, path: str) -> Any:
        try:
            response = await self._get(path)
        except httpx.HTTPError as exc:
            raise ChertError(f"GET {path}: {type(exc).__name__}") from None
        if response.status_code >= 400:
            raise ChertError(f"GET {path}: {self._why(response)}")
        try:
            return response.json()
        except ValueError:
            raise ChertError(f"GET {path}: the answer was not JSON") from None

    # ------------------------------------------------------------------ reads

    async def lines(self) -> list[dict[str, Any]]:
        return _items(await self._get_json("/v1/lines"))

    async def calls(self) -> list[dict[str, Any]]:
        return _items(await self._get_json("/v1/calls"))

    async def call(self, call_id: str) -> dict[str, Any]:
        return _data(await self._get_json(f"/v1/calls/{call_id}"))

    async def events(self, call_id: str) -> list[dict[str, Any]]:
        return _items(await self._get_json(f"/v1/calls/{call_id}/events"))

    async def queue(self, queue_id: str) -> dict[str, Any]:
        return _data(await self._get_json(f"/v1/calls/queue/{queue_id}"))

    # ------------------------------------------------------------------ writes

    async def create_call(self, body: dict[str, Any], key: str) -> Placement:
        try:
            response = await self._post("/v1/calls", body, key)
        except httpx.HTTPError as exc:
            return Placement("uncertain", reason=f"no answer from Chert ({type(exc).__name__})")
        status = response.status_code
        try:
            data = _data(response.json())
        except ValueError:
            data = {}
        if status == 201 or (status == 200 and data.get("id") and not data.get("queued")):
            return Placement("placed", call_id=str(data.get("id") or ""), status=status, data=data)
        if status == 202 or data.get("queued") is True:
            queue_id = data.get("queue_id") or data.get("id")
            if isinstance(data.get("queue"), dict):
                queue_id = data["queue"].get("id") or queue_id
            return Placement("waiting", queue_id=str(queue_id or ""), status=status, data=data)
        if status >= 500 or status in (408, 429):
            return Placement("uncertain", reason=self._why(response), status=status)
        code, _ = error_of(response)
        if any(word in code.lower() for word in BUSY_WORDS):
            return Placement("busy", reason=self._why(response), status=status)
        return Placement("refused", reason=self._why(response), status=status)

    async def end_call(self, call_id: str, key: str) -> int:
        try:
            response = await self._post(f"/v1/calls/{call_id}/end", {}, key)
        except httpx.HTTPError as exc:
            log.warning("could not ask Chert to end the call (%s)", type(exc).__name__)
            return 0
        if response.status_code >= 400:
            log.warning("Chert refused to end the call: %s", self._why(response))
        return response.status_code

    async def cancel_queue(self, queue_id: str) -> None:
        try:
            await self._client.delete(f"/v1/calls/queue/{queue_id}")
        except httpx.HTTPError:
            pass

    async def send_message(self, line_id: str, recipient: str, text: str, key: str) -> Sent:
        """An iMessage on the shared line. `recipient` goes to Chert and nowhere else."""
        body = {"line_id": line_id, "recipient": recipient, "text": text}
        try:
            response = await self._post("/v1/shared-messages", body, key)
        except httpx.HTTPError as exc:
            return Sent(False, 0, f"no answer from Chert ({type(exc).__name__})")
        if response.status_code >= 300:
            return Sent(False, response.status_code, self._why(response))
        try:
            data = _data(response.json())
        except ValueError:
            data = {}
        return Sent(True, response.status_code, message_id=str(data.get("id") or "") or None)


class ChertError(Exception):
    """A read from Chert failed. The message is masked by whoever logs it."""


async def place(api: ChertAPI, body: dict[str, Any], key: str, clock: Clock,
                say: Any = None, wait_s: float = QUEUE_WAIT_S) -> Placement:
    """One call attempt, with Chert's busy queue: ask, and if told to wait, ask about the
    receipt until it is ready, then send the same request again with the same key.
    `say` gets each outcome in plain words."""
    report = say or (lambda message: log.info("%s", message))
    placement = await api.create_call(body, key)
    for _ in range(2):  # an uncertain answer may only be followed by the very same request
        if placement.outcome != "uncertain":
            break
        report(f"no clear answer from Chert ({placement.reason}); asking again with the same key")
        await clock.sleep(2.0)
        placement = await api.create_call(body, key)
    if placement.outcome != "waiting":
        return placement
    if not placement.queue_id:
        return Placement("busy", reason="Chert said wait but gave no receipt", waited=True)
    report("waiting: the line is busy and Chert is holding our place (up to two minutes)")
    deadline = clock.now() + wait_s
    while clock.now() < deadline:
        await clock.sleep(QUEUE_POLL_S)
        try:
            receipt = await api.queue(placement.queue_id)
        except ChertError as exc:
            report(f"could not read the queue receipt ({api.redactor.mask(exc)}); still waiting")
            continue
        state = str(receipt.get("state") or receipt.get("status") or "").lower()
        if state == "ready":
            report("the line is ready: sending the same request again")
            again = await api.create_call(body, key)
            if again.outcome == "uncertain":
                again = await api.create_call(body, key)
            if again.outcome == "waiting":
                return Placement("busy", reason="the line was ready but Chert queued us again",
                                 waited=True)
            again.waited = True
            return again
        if state in ("expired", "cancelled", "canceled", "failed"):
            return Placement("busy", reason=f"the wait ended without a call ({state})",
                             waited=True)
    await api.cancel_queue(placement.queue_id)
    return Placement("busy", reason="the line stayed busy for two minutes", waited=True)
