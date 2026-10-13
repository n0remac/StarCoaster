#!/usr/bin/env python3
"""Compare world.v1 terrain export against native elements of the saved park."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run-data" / f"terrain-export-{int(time.time())}"
PARK = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
ELEMENTS = ROOT / "run-data/frontier-playable/navigation-elements.json"


def main():
    if not PARK.is_file() or not ELEMENTS.is_file():
        raise SystemExit("Generate Frontier first with scripts/project.sh park")
    if not os.environ.get("RCT2_DATA_DIR"):
        raise SystemExit("Set RCT2_DATA_DIR to licensed RCT2 data")
    RUN.mkdir(parents=True)
    native = json.loads(ELEMENTS.read_text())
    for field in ("elevation_rows", "slope_rows", "water_rows"):
        if field not in native:
            raise SystemExit(f"Regenerate Frontier: missing {field} in native element export")
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 40010))
    server.listen(1)
    server.settimeout(40)
    env = os.environ.copy()
    env.update(BRIDGE_SCENARIO="world", BRIDGE_SERVER_DATA_DIR=str(RUN / "server"))
    with (RUN / "openrct2.log").open("w") as log:
        process = subprocess.Popen([str(ROOT / "scripts/run-openrct2-host.sh"), str(PARK)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            connection, _ = server.accept()
            connection.settimeout(40)
            reader = connection.makefile("rb")
            terrain = []
            while True:
                raw = reader.readline()
                if not raw:
                    raise RuntimeError("OpenRCT2 disconnected during terrain export")
                packet = json.loads(raw)
                if packet["kind"] == "world.snapshot.chunk":
                    terrain.extend(packet["payload"].get("terrain", []))
                ack = {"v": 1, "kind": "world.ack", "session": packet["session"],
                       "op_id": "terrain-probe", "source": "bridge",
                       "revision": packet["revision"],
                       "payload": {"op_id": packet["op_id"], "accepted": True}}
                connection.sendall((json.dumps(ack) + "\n").encode())
                if packet["kind"] == "world.snapshot.end":
                    if packet["payload"]["terrain"] != len(terrain):
                        raise AssertionError("terrain snapshot count changed in flight")
                    break
            by_position = {(cell["x"], cell["y"]): cell for cell in terrain}
            bounds = native["bounds"]
            paths = {}
            for element in native["elements"]:
                if element["type"] == "footpath":
                    paths.setdefault((element["x"], element["y"]), []).append({
                        "base_height": element["z"],
                        "slope_direction": element["slope_direction"]})
            checked = 0
            sloped = 0
            for y in range(bounds["min_y"], bounds["max_y"] + 1):
                for x in range(bounds["min_x"], bounds["max_x"] + 1):
                    cell = by_position[(x, y)]
                    row, column = y - bounds["min_y"], x - bounds["min_x"]
                    expected = (native["elevation_rows"][row][column],
                                native["slope_rows"][row][column],
                                native["water_rows"][row][column],
                                paths.get((x, y), []))
                    actual = (cell["height"], cell["slope"], cell["water"],
                              cell.get("ground_paths", []))
                    if actual != expected:
                        raise AssertionError(f"native terrain mismatch at {x},{y}: {actual} != {expected}")
                    checked += 1
                    sloped += cell["slope"] != 0
            report = {"checked_tiles": checked, "sloped_tiles": sloped,
                      "path_tiles": len(paths), "exported_tiles": len(terrain)}
            (RUN / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({"result": "PASS", "run_dir": str(RUN), **report}))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            server.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}; run directory: {RUN}", file=sys.stderr)
        raise
