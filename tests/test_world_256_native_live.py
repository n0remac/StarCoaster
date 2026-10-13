#!/usr/bin/env python3
"""Exercise a 256x256 map through two native OpenBW participants.

Requires STARCRAFT_DATA_DIR and built native engines. Results and process logs
stay in ignored run-data; this probe never replaces the live park tests.
"""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run-data" / f"world-256-native-{int(time.time())}"
SESSION = "world256probe"


def message(kind, operation, payload, revision=1):
    return {"v": 1, "kind": kind, "session": SESSION, "op_id": operation,
            "source": "bridge", "revision": revision, "payload": payload}


class Peer:
    def __init__(self, connection):
        self.connection = connection
        self.reader = connection.makefile("rb")

    def send(self, kind, operation, payload, revision=1):
        self.connection.sendall((json.dumps(message(kind, operation, payload, revision),
                                            separators=(",", ":")) + "\n").encode())

    def until(self, wanted, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.connection.settimeout(max(0.1, deadline - time.monotonic()))
            line = self.reader.readline()
            if not line:
                raise RuntimeError("native participant disconnected")
            packet = json.loads(line)
            if wanted(packet):
                return packet
        raise TimeoutError("native participant did not send expected message")


def main():
    if not os.environ.get("STARCRAFT_DATA_DIR"):
        raise SystemExit("Set STARCRAFT_DATA_DIR to licensed StarCraft data")
    RUN.mkdir(parents=True)
    scenario = RUN / "scenario.json"
    scenario.write_text(json.dumps({"version": 1, "park_size": [256, 256],
                                    "starting_units": {"marines": [[252, 252]],
                                                       "zerglings": [[2, 2]]}}))
    native_map = RUN / "world-256.scm"
    subprocess.run(["python3", str(ROOT / "scripts/create-world-base-map.py"),
                    "--scenario", str(scenario), "--output", str(native_map)], check=True)
    servers = []
    processes = []
    logs = []
    try:
        for port in (40011, 40012):
            server = socket.socket()
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", port))
            server.listen(1)
            server.settimeout(40)
            servers.append(server)
        for role, slot, race in (("publisher", 0, "Zerg"), ("controller", 1, "Terran")):
            log = (RUN / f"{role}.log").open("w")
            logs.append(log)
            env = os.environ.copy()
            env.update(BRIDGE_SCENARIO="world", BRIDGE_WORLD_ROLE=role,
                       BRIDGE_MAP_FILE=str(native_map), BRIDGE_BWAPI_MENU="MULTI_PLAYER",
                       BRIDGE_BWAPI_SLOT=str(slot), BRIDGE_BWAPI_RACE=race,
                       BRIDGE_BWAPI_RUNTIME_DIR=str(RUN / role),
                       OPENBW_LAN_MODE="LOCAL", OPENBW_LOCAL_PATH=str(RUN / "openbw-local.socket"))
            processes.append(subprocess.Popen([str(ROOT / "scripts/run-bwapi.sh")],
                                              cwd=ROOT, env=env, stdout=log,
                                              stderr=subprocess.STDOUT, start_new_session=True))
        publisher = Peer(servers[0].accept()[0])
        controller = Peer(servers[1].accept()[0])
        hello = publisher.until(lambda packet: packet["kind"] == "world.hello")
        controller.until(lambda packet: packet["kind"] == "world.hello")
        dimensions = hello["payload"]["map_width"], hello["payload"]["map_height"]
        if dimensions != (256, 256):
            raise AssertionError(f"native map dimensions: {dimensions}")
        controller.send("world.hello", "probe:controller", {"role": "controller"})
        publisher.send("world.snapshot.begin", "probe:begin", {"width": 256, "height": 256,
                                                                  "chunks": 1})
        publisher.send("world.snapshot.chunk", "probe:chunk", {"index": 0, "entities": [],
                                                                  "terrain": []})
        publisher.send("world.snapshot.end", "probe:end", {"entities": 0, "terrain": 0})
        ready = publisher.until(lambda packet: packet["kind"] == "world.ready")
        if ready["payload"]["navigation"] != "native":
            raise AssertionError(f"native navigation failed: {ready['payload']}")
        start = publisher.until(lambda packet: packet["kind"] == "combat.snapshot"
                                and any(unit["id"] == "openbw:1000" for unit in packet["payload"]["units"]))
        marine = next(unit for unit in start["payload"]["units"] if unit["id"] == "openbw:1000")
        expected_start = (252 * 32 + 16, 252 * 32 + 16)
        if (marine["x"], marine["y"]) != expected_start:
            raise AssertionError(f"unscaled Marine placement failed: {marine}")
        target = (254 * 32 + 16, 252 * 32 + 16)
        controller.send("combat.command", "probe:move", {"command_id": SESSION + ":1",
                        "verb": "unit.move", "unit_ids": ["openbw:1000"],
                        "x": target[0], "y": target[1], "player_id": 1, "request_id": 1})
        result = controller.until(lambda packet: packet["kind"] == "combat.result")
        if not result["payload"]["accepted"]:
            raise AssertionError(f"native move rejected: {result['payload']}")
        arrived = publisher.until(lambda packet: packet["kind"] == "combat.snapshot"
                                  and any(unit["id"] == "openbw:1000"
                                          and abs(unit["x"] - target[0]) <= 12
                                          and abs(unit["y"] - target[1]) <= 12
                                          for unit in packet["payload"]["units"]), timeout=40)
        arrived_marine = next(unit for unit in arrived["payload"]["units"]
                              if unit["id"] == "openbw:1000")
        # A 256x256 park has over 65,000 blocked tile overlays in this update.
        # Native VF4 variants must be shared; one clone per tile exceeds 0x8000.
        started = time.monotonic()
        chunks = 256 * 256 // 128
        publisher.send("world.snapshot.begin", "probe:large:begin",
                       {"width": 256, "height": 256, "chunks": chunks}, 2)
        for index in range(chunks):
            cells = [{"x": i % 256, "y": i // 256, "walkable": False}
                     for i in range(index * 128, (index + 1) * 128)]
            publisher.send("world.snapshot.chunk", f"probe:large:{index}",
                           {"index": index, "entities": [], "terrain": cells}, 2)
        publisher.send("world.snapshot.end", "probe:large:end",
                       {"entities": 0, "terrain": 256 * 256}, 2)
        large_ready = publisher.until(lambda packet: packet["kind"] == "world.ready"
                                      and packet["revision"] == 2, timeout=90)
        elapsed = round(time.monotonic() - started, 3)
        if large_ready["payload"]["navigation"] != "native":
            raise AssertionError(f"large collision mask failed: {large_ready['payload']}")
        report = {"native_map": [256, 256], "marine_start": expected_start,
                  "marine_arrived": [arrived_marine["x"], arrived_marine["y"]],
                  "destination": target, "blocked_tiles": 256 * 256,
                  "large_mask_seconds": elapsed, "navigation": "native"}
        (RUN / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"result": "PASS", "run_dir": str(RUN), **report}))
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        for server in servers:
            server.close()
        for log in logs:
            log.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}; run directory: {RUN}", file=sys.stderr)
        raise
