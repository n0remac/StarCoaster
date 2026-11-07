#!/usr/bin/env python3
"""Stage an ordinary park, order one SCV through the player action, observe native delivery."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_existing_defense import prepare
from scenario_package import build_native_map, ensure_park


def ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be under ignored run-data")
    source = args.source.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    plan = prepare(str(source), runtime / "prepared")
    ensure_park(plan)
    build_native_map(plan)
    server = runtime / "server"
    (server / "plugin").mkdir(parents=True, exist_ok=True)
    (server / "plugin/economy_e4_native_route_probe.js").write_bytes(
        (ROOT / "tests/economy_e4_native_route_probe.js").read_bytes())
    selected_ports = ports(4)
    names = ("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT", "BRIDGE_OPENBW_PORT",
             "BRIDGE_CONTROLLER_PORT")
    env = os.environ.copy() | dict(zip(names, map(str, selected_ports)))
    env.update({"RCT2_DATA_DIR": "/home/pi/games/rct2",
                "STARCRAFT_DATA_DIR": "/home/pi/games/starcraft",
                "BRIDGE_MAP_FILE": plan["native_map"],
                "BRIDGE_SCENARIO_CONFIG": plan["scenario"],
                "BRIDGE_RULES_CONFIG": plan["mapping"],
                "BRIDGE_SPAWN_JOURNAL": str(runtime / "spawn-queue.json"),
                "BRIDGE_RUNTIME_DIR": str(runtime / "native"),
                "BRIDGE_SERVER_DATA_DIR": str(server),
                "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_FRAME_MS": "10",
                "BRIDGE_DISABLE_ASSAULT_AI": "1"})
    log_path = runtime / "session.log"
    process = None
    with log_path.open("w") as log:
        try:
            process = subprocess.Popen(["bash", "scripts/run-world-session.sh", plan["park"]],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("native route session exited before delivery")
                lines = log_path.read_text(errors="replace")
                balances = [(int(value), int(frame)) for value, frame in re.findall(
                    r"player resources owner=1 minerals=(\d+) gas=0[^\n]*frame=(\d+)", lines)]
                deposit = re.search(r"resource site=mineral-a generation=1[^\n]*amount=1492", lines)
                ordered = "ECONOMY_E4_NATIVE_GATHER worker=" in lines and "accepted=true" in lines
                delivered = next(((value, frame) for value, frame in balances if value > 50), None)
                if ordered and deposit and delivered:
                    scenario = json.loads(Path(plan["scenario"]).read_text())
                    report = {"result": "PASS", "scenario": scenario["scenario_id"],
                              "base_tile": scenario["economy"]["starting_entities"][0]["tile"],
                              "balances": balances, "delivery": delivered,
                              "source_sha256": before,
                              "source_unchanged": hashlib.sha256(source.read_bytes()).hexdigest() == before,
                              "log": str(log_path)}
                    (runtime / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
                    if not report["source_unchanged"]:
                        raise AssertionError("stock source changed")
                    print(json.dumps(report, indent=2), flush=True)
                    return
                time.sleep(.5)
            raise TimeoutError("SCV did not deliver native minerals within 180 seconds")
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
