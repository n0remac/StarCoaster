#!/usr/bin/env python3
"""Exercise a stock park whose geometry cannot hold the generated economy."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_existing_defense import prepare
from scenario_package import build_native_map, ensure_park, session_environment


def free_ports(count):
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
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    plan = prepare(str(args.source), runtime)
    scenario = json.loads(Path(plan["scenario"]).read_text())
    if (scenario["economy"]["layout_state"] != "blocked"
            or scenario["economy"]["starting_entities"]
            or scenario["initial_structures"]
            or scenario["economy"]["initial_balances"] != {"minerals": 0, "gas": 0}):
        raise AssertionError("expected finite blocked economy with no hidden actors or balance")
    print("STAGED", args.source.name, scenario["economy"]["blocked_reason"], flush=True)
    ensure_park(plan)
    build_native_map(plan)
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != source_hash:
        raise AssertionError("source park changed during staging")
    ports = free_ports(4)
    overrides = dict(zip(("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT",
                          "BRIDGE_OPENBW_PORT", "BRIDGE_CONTROLLER_PORT"), map(str, ports)))
    overrides.update({"BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVE_WASM": "0",
                      "BRIDGE_DISABLE_ASSAULT_AI": "1", "BRIDGE_FRAME_MS": "10",
                      "BRIDGE_RUNTIME_DIR": str(runtime / "native"),
                      "BRIDGE_SERVER_DATA_DIR": str(runtime / "server"),
                      "BRIDGE_SPAWN_JOURNAL": str(runtime / "spawn-queue.json")})
    environment = session_environment(plan, overrides)
    log_path = runtime / "native-session.log"
    with log_path.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=environment, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                data = log_path.read_text(errors="replace")
                if "WORLD_READY entities=" in data and "WORLD_SCENARIO_STATUS scenario=" in data:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"native process exited; see {log_path}")
                time.sleep(.25)
            else:
                raise TimeoutError(f"native readiness missing; see {log_path}")
            journal = json.loads(Path(plan["spawn_journal"] + ".scenario.json").read_text())
            if (journal.get("economy_ready_frame") or journal.get("next_automatic_frame")
                    or journal.get("waves") or "finite economy bootstrap ready" in data):
                raise AssertionError("blocked map started its economy or wave clock")
            report = {"source": str(args.source), "source_sha256": source_hash,
                      "layout_state": "blocked", "reason": scenario["economy"]["blocked_reason"],
                      "session": journal["session"], "last_frame": journal.get("last_frame"),
                      "next_automatic_frame": journal.get("next_automatic_frame", 0),
                      "log": str(log_path)}
            (runtime / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
