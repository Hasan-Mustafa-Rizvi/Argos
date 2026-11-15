"""Pretend to be the sensor board, so a person can try the serial link by hand.

Windows has no pseudo-terminals, so this listens on a TCP port and the brain connects with
SERIAL_PORT=socket://127.0.0.1:7777 (pyserial opens that like a serial port).

    python tools/pretend_board.py                 # listens on 127.0.0.1:7777
    python tools/pretend_board.py --port 7778 --caps eyes,touch,buzzer,temp,imu,head

It sends `hello` when the brain connects and when asked with `ping`, and `telemetry` every
500 ms. It prints every command the brain sends. Type a letter and Enter:

    p  pat            t  tipped over      u  set upright
    s  go silent (stop telemetry, to test the 3 second disconnect)   r  resume
    x  send a line the brain must ignore  q  quit
"""

from __future__ import annotations

import argparse
import json
import random
import socket
import sys
import threading
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--caps", default="eyes,touch,buzzer,temp,imu")
    parser.add_argument("--fw", default="0.1.0-pretend")
    args = parser.parse_args()
    caps = [c for c in args.caps.split(",") if c]

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    print(f"pretend board listening on {args.host}:{args.port}; "
          f"set SERIAL_PORT=socket://{args.host}:{args.port}")

    state = {"conn": None, "silent": False, "touch": False, "quit": False}
    lock = threading.Lock()
    started = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def send(message: dict) -> None:
        line = json.dumps(message, separators=(",", ":")) + "\n"
        with lock:
            conn = state["conn"]
            if conn is None:
                return
            try:
                conn.sendall(line.encode("utf-8"))
            except OSError:
                state["conn"] = None

    def hello() -> None:
        send({"t": "hello", "fw": args.fw, "caps": caps})

    def telemetry_loop() -> None:
        while not state["quit"]:
            time.sleep(0.5)
            if state["conn"] is not None and not state["silent"]:
                send({"t": "telemetry", "ms": ms(), "temp_c": round(23.4 + random.uniform(-0.2,
                      0.2), 1), "tilt_deg": round(random.uniform(0.8, 1.6), 1),
                      "touch": state["touch"]})

    def reader(conn: socket.socket) -> None:
        buffer = b""
        while not state["quit"]:
            try:
                data = conn.recv(1024)
            except OSError:
                break
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                print(f"  brain > board: {raw.decode('utf-8', 'replace')}")
                try:
                    command = json.loads(raw)
                except ValueError:
                    continue
                if command.get("cmd") == "ping":
                    hello()
                elif command.get("cmd") == "head" and "head" not in caps:
                    send({"t": "err", "msg": "head: not supported"})
        print("brain disconnected; waiting for it to come back")
        with lock:
            state["conn"] = None

    def acceptor() -> None:
        while not state["quit"]:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            print("brain connected")
            with lock:
                state["conn"] = conn
            hello()
            threading.Thread(target=reader, args=(conn,), daemon=True).start()

    threading.Thread(target=telemetry_loop, daemon=True).start()
    threading.Thread(target=acceptor, daemon=True).start()

    for line in sys.stdin:
        key = line.strip()[:1].lower()
        if key == "p":
            state["touch"] = True
            send({"t": "event", "ms": ms(), "kind": "pat"})
            state["touch"] = False
        elif key == "t":
            send({"t": "event", "ms": ms(), "kind": "tipped"})
        elif key == "u":
            send({"t": "event", "ms": ms(), "kind": "upright"})
        elif key == "s":
            state["silent"] = True
            print("silent: the brain should report the board disconnected after 3 s")
        elif key == "r":
            state["silent"] = False
            print("talking again")
        elif key == "x":
            send({"t": "sparkle", "mood": "unknown message the brain must ignore"})
        elif key == "q":
            break
    else:
        # No more typed input (started in the background): keep pretending until Ctrl+C.
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
    state["quit"] = True
    server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
