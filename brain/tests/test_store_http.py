"""The real Supabase store, against a fake HTTP server (httpx.MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from argos.store import StoreRejected, StoreUnavailable, SupabaseStore, auth_headers


class Server:
    def __init__(self, status: int = 201, headers: dict[str, str] | None = None,
                 body: object = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self.headers = headers or {}
        self.body = body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is not None:
            return httpx.Response(self.status, headers=self.headers, json=self.body)
        return httpx.Response(self.status, headers=self.headers)


def store(server: Server, key: str = "sb_secret_MARKER") -> SupabaseStore:
    return SupabaseStore("https://project.invalid", key, transport=httpx.MockTransport(server))


def test_secret_key_goes_on_apikey_only_and_legacy_jwt_also_on_authorization() -> None:
    assert auth_headers("sb_secret_MARKER") == {"apikey": "sb_secret_MARKER"}
    assert auth_headers("eyJMARKER") == {"apikey": "eyJMARKER",
                                         "Authorization": "Bearer eyJMARKER"}


def test_insert_never_overwrites_and_returns_nothing() -> None:
    server = Server(201)
    store(server).insert("events", [{"id": "e1", "kind": "asked"}])
    request = server.requests[0]
    assert request.method == "POST" and request.url.path == "/rest/v1/events"
    assert request.url.params["on_conflict"] == "id"
    assert "resolution=ignore-duplicates" in request.headers["prefer"]
    assert "return=minimal" in request.headers["prefer"]
    assert json.loads(request.content) == {"id": "e1", "kind": "asked"}
    assert request.headers["apikey"] == "sb_secret_MARKER"


def test_readings_batch_uses_their_own_key() -> None:
    server = Server(201)
    store(server).insert("readings", [{"device_id": "d", "at": "1"}, {"device_id": "d",
                                                                      "at": "2"}])
    request = server.requests[0]
    assert request.url.params["on_conflict"] == "device_id,at"
    assert len(json.loads(request.content)) == 2


def test_update_sends_only_the_patch_with_filters_and_counts() -> None:
    server = Server(204, headers={"Content-Range": "*/1"})
    matched = store(server).update(
        "incidents", {"id": "eq.i1", "status": "eq.escalated"}, {"summary": "Text."})
    request = server.requests[0]
    assert request.method == "PATCH"
    assert request.url.params["id"] == "eq.i1"
    assert request.url.params["status"] == "eq.escalated"
    assert json.loads(request.content) == {"summary": "Text."}
    assert "count=exact" in request.headers["prefer"]
    assert matched == 1
    assert store(Server(204, headers={"Content-Range": "*/0"})).update(
        "incidents", {"id": "eq.x"}, {"ended_at": "t"}) == 0


def test_select_and_upload() -> None:
    server = Server(200, body=[{"person_label": "Eleni"}])
    rows = store(server).select("devices", {"id": "eq.d"}, "person_label")
    assert rows == [{"person_label": "Eleni"}]
    assert server.requests[0].url.params["select"] == "person_label"
    upload = Server(200, body={"Key": "snapshots/incidents/i/snapshot.jpg"})
    store(upload).upload("snapshots", "incidents/i/snapshot.jpg", b"\xff\xd8jpeg", "image/jpeg")
    request = upload.requests[0]
    assert request.url.path == "/storage/v1/object/snapshots/incidents/i/snapshot.jpg"
    assert request.headers["content-type"] == "image/jpeg"
    assert request.content == b"\xff\xd8jpeg"


@pytest.mark.parametrize(("status", "error"), [(500, StoreUnavailable), (503, StoreUnavailable),
                                                (429, StoreUnavailable), (400, StoreRejected),
                                                (403, StoreRejected), (409, StoreRejected)])
def test_errors_are_sorted_into_retry_or_drop(status: int, error: type[Exception]) -> None:
    with pytest.raises(error) as caught:
        store(Server(status, body={"message": "nope"})).insert("events", [{"id": "e"}])
    assert "MARKER" not in str(caught.value)


def test_network_failure_is_unavailable_and_names_no_key() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    broken = SupabaseStore("https://project.invalid", "sb_secret_MARKER",
                           transport=httpx.MockTransport(down))
    with pytest.raises(StoreUnavailable) as caught:
        broken.select("devices", {"id": "eq.d"}, "person_label")
    assert "MARKER" not in str(caught.value)
