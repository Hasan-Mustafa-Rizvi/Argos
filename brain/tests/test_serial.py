"""The sensor board's serial link, against contract/examples/serial.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from argos.body.base import Connected, Disconnected, Pat, Telemetry, Tipped, Upright
from argos.body.serial_link import (
    SensorBoard,
    cmd_buzz,
    cmd_head,
    cmd_ping,
    cmd_state,
    cmd_tail,
    encode,
    parse_line,
)
from argos.clock import FakeClock

EXAMPLES = Path(__file__).resolve().parents[2] / "contract" / "examples" / "serial.jsonl"


def examples() -> list[dict[str, Any]]:
    with EXAMPLES.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def wire(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


@pytest.mark.parametrize("sample", [s for s in examples() if s["dir"] == "dog>laptop"])
def test_every_board_line_parses(sample: dict[str, Any]) -> None:
    assert parse_line(wire(sample["line"])) == sample["line"]


def build(command: dict[str, Any]) -> dict[str, Any]:
    makers = {
        "state": lambda c: cmd_state(c["state"]),
        "head": lambda c: cmd_head(c["deg"]),
        "tail": lambda c: cmd_tail(c["on"]),
        "buzz": lambda c: cmd_buzz(c["ms"]),
        "ping": lambda c: cmd_ping(),
    }
    return makers[command["cmd"]](command)


@pytest.mark.parametrize("sample", [s for s in examples() if s["dir"] == "laptop>dog"])
def test_every_brain_line_is_produced_exactly(sample: dict[str, Any]) -> None:
    assert encode(build(sample["line"])) == wire(sample["line"])


@pytest.mark.parametrize(
    "raw",
    [
        b"not json at all",
        b"[1, 2, 3]",
        b'{"no_t": 1}',
        b'{"t": 5}',
        b"\xff\xfe\xfd",
        b'{"t":"telemetry","pad":"' + b"x" * 300 + b'"}',
        b"",
    ],
)
def test_unusable_lines_are_ignored(raw: bytes) -> None:
    assert parse_line(raw) is None


def test_commands_stay_in_range() -> None:
    assert cmd_head(200) == {"cmd": "head", "deg": 60}
    assert cmd_buzz(0) == {"cmd": "buzz", "ms": 1}
    assert cmd_buzz(10_000) == {"cmd": "buzz", "ms": 2000}
    with pytest.raises(ValueError):
        cmd_state("offline")


class FakePort:
    def __init__(self) -> None:
        self.incoming = b""
        self.written: list[dict[str, Any]] = []
        self.closed = False

    @property
    def in_waiting(self) -> int:
        return len(self.incoming)

    def read(self, size: int = 1) -> bytes:
        data, self.incoming = self.incoming[:size], self.incoming[size:]
        return data

    def write(self, data: bytes) -> int:
        assert data.endswith(b"\n") and len(data) <= 257
        self.written.append(json.loads(data))
        return len(data)

    def close(self) -> None:
        self.closed = True

    def feed(self, *messages: dict[str, Any] | bytes) -> None:
        for message in messages:
            self.incoming += message if isinstance(message, bytes) else wire(message)


class Board:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.ports: list[FakePort] = []
        self.events: list[Any] = []
        self.board = SensorBoard("socket://127.0.0.1:7777", self.clock, opener=self.open,
                                 threaded=False)

    def open(self, url: str) -> FakePort:
        port = FakePort()
        self.ports.append(port)
        return port

    @property
    def port(self) -> FakePort:
        return self.ports[-1]

    def poll(self, seconds: float = 0.0, dt: float = 0.05) -> None:
        if seconds <= 0:
            self.board.poll(self.clock.now())
            return
        for _ in range(int(round(seconds / dt))):
            self.clock.advance(dt)
            self.board.poll(self.clock.now())


def test_ping_on_connect_then_hello_sets_caps() -> None:
    rig = Board()
    rig.board.start(rig.events.append)
    assert rig.port.written == [{"cmd": "ping"}]
    rig.port.feed({"t": "hello", "fw": "0.1.0", "caps": ["eyes", "touch", "buzzer"]})
    rig.poll()
    assert rig.board.connected
    assert rig.board.caps() == ["eyes", "touch", "buzzer"]
    assert rig.board.fw() == "0.1.0"
    assert any(isinstance(e, Connected) for e in rig.events)
    assert {"cmd": "state", "state": "calm"} in rig.port.written


def test_events_and_telemetry_reach_the_brain() -> None:
    rig = Board()
    rig.board.start(rig.events.append)
    rig.port.feed(
        {"t": "hello", "fw": "0.1.0", "caps": ["touch"]},
        {"t": "telemetry", "ms": 1500, "temp_c": 23.4, "tilt_deg": 1.2, "touch": False},
        {"t": "event", "ms": 2510, "kind": "pat"},
        {"t": "event", "ms": 9120, "kind": "tipped"},
        {"t": "event", "ms": 11480, "kind": "upright"},
        {"t": "err", "msg": "head: not supported"},
        {"t": "sparkle", "mood": "unknown"},
        b"garbage line\n",
        {"t": "telemetry", "ms": 2000, "temp_c": "hot", "tilt_deg": None, "extra": 1},
    )
    rig.poll(0.5)
    kinds = [type(e) for e in rig.events]
    assert Pat in kinds and Tipped in kinds and Upright in kinds
    telemetry = [e for e in rig.events if isinstance(e, Telemetry)]
    assert telemetry[0].temp_c == 23.4 and telemetry[0].tilt_deg == 1.2
    assert telemetry[1].temp_c is None and telemetry[1].tilt_deg is None


def test_state_command_on_change_and_buzz_only_with_buzzer() -> None:
    rig = Board()
    rig.board.start(rig.events.append)
    rig.port.feed({"t": "hello", "fw": "0.1.0", "caps": ["eyes"]})
    rig.poll()
    rig.board.show_state("checking", look_yaw_deg=30)
    assert rig.port.written[-1] == {"cmd": "state", "state": "checking"}
    assert not any(c.get("cmd") == "head" for c in rig.port.written)  # no head cap
    assert rig.board.beep(200) is False
    rig.port.feed({"t": "hello", "fw": "0.1.0", "caps": ["eyes", "buzzer", "head"]})
    rig.poll()
    assert rig.board.beep(200) is True
    assert rig.port.written[-1] == {"cmd": "buzz", "ms": 200}
    rig.board.show_state("checking", look_yaw_deg=35)
    assert rig.port.written[-1] == {"cmd": "head", "deg": 35}


def test_three_seconds_of_silence_disconnects_and_reconnects() -> None:
    rig = Board()
    rig.board.start(rig.events.append)
    rig.port.feed({"t": "hello", "fw": "0.1.0", "caps": ["touch"]})
    rig.poll()
    rig.poll(2.9)
    assert rig.board.connected
    rig.poll(0.2)
    assert not rig.board.connected
    assert isinstance(rig.events[-1], Disconnected)
    assert rig.ports[0].closed
    assert rig.board.caps() == []
    rig.poll(2.1)  # reopened after two seconds, with a fresh ping
    assert len(rig.ports) == 2
    assert rig.port.written == [{"cmd": "ping"}]
    rig.port.feed({"t": "hello", "fw": "0.1.0", "caps": ["touch"]})
    rig.poll(0.05)
    assert rig.board.connected


def test_port_that_cannot_open_is_retried_quietly() -> None:
    clock = FakeClock()
    attempts: list[str] = []

    def opener(url: str) -> FakePort:
        attempts.append(url)
        raise OSError("no such port")

    board = SensorBoard("COM99", clock, opener=opener, threaded=False)
    board.start(lambda e: None)
    for _ in range(100):
        clock.advance(0.05)
        board.poll(clock.now())
    assert 2 <= len(attempts) <= 4
    assert board.caps() == [] and not board.beep(100)
    board.show_state("alert")  # nothing to write to, and nothing fails
