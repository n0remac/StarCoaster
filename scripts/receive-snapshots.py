#!/usr/bin/env python3
"""M0 smoke receiver: require a real moving unit over the loopback stream."""

import argparse
import json
import socket
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=39999)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    deadline = time.monotonic() + args.seconds

    connection = None
    while connection is None and time.monotonic() < deadline:
        try:
            connection = socket.create_connection(("127.0.0.1", args.port), timeout=1)
        except OSError:
            time.sleep(0.25)
    if connection is None:
        print("FAIL: no publisher accepted a localhost connection", file=sys.stderr)
        return 1

    session = None
    previous_seq = 0
    first_position = None
    moved = False
    count = 0
    connection.settimeout(1)
    pending = b""
    with connection:
        while time.monotonic() < deadline:
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            pending += chunk
            if len(pending) > 4096 and b"\n" not in pending:
                print("FAIL: oversized snapshot", file=sys.stderr)
                return 1
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                if len(raw) > 4096:
                    print("FAIL: oversized snapshot", file=sys.stderr)
                    return 1
                data = json.loads(raw)
                if data.get("v") != 1 or data.get("kind") != "units.snapshot":
                    print("FAIL: wrong protocol version or message kind", file=sys.stderr)
                    return 1
                if session is None:
                    session = data["session"]
                if data["session"] != session or data["seq"] <= previous_seq:
                    print("FAIL: session changed or sequence did not increase", file=sys.stderr)
                    return 1
                previous_seq = data["seq"]
                count += 1
                for unit in data["units"]:
                    position = (unit["x"], unit["y"])
                    if first_position is None:
                        first_position = position
                    moved |= position != first_position
                    print(
                        f"session={session} seq={previous_seq} tick={data['bw_tick']} "
                        f"id={unit['id']} x={unit['x']} y={unit['y']} motion={unit['motion']}"
                    )
                if moved and count >= 3:
                    print(f"PASS: {count} snapshots; reported unit position changed (publisher not authenticated)")
                    return 0

    print(f"FAIL: {count} snapshots; no moving unit observed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
