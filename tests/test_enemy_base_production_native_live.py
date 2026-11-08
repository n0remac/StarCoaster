#!/usr/bin/env python3
"""Focused B2 native train, morph, pair, and bridge reconnect probe."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_existing_defense import prepare  # noqa: E402
from scenario_package import build_native_map, ensure_park  # noqa: E402
from test_enemy_base_bootstrap_native_live import free_ports  # noqa: E402


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    source, runtime = args.source.resolve(strict=True), args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be in ignored run-data")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    runtime.mkdir(parents=True, exist_ok=True)
    plan = prepare(str(source), runtime / "prepared")
    scenario = json.loads(Path(plan["scenario"]).read_text())
    if scenario["enemy_base"]["layout_state"] != "ready":
        raise AssertionError("native probe requires a ready colony")
    ensure_park(plan)
    build_native_map(plan)
    names = ("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT", "BRIDGE_OPENBW_PORT",
             "BRIDGE_CONTROLLER_PORT")
    env = os.environ.copy() | dict(zip(names, map(str, free_ports(len(names)))))
    env.update({"RCT2_DATA_DIR": os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"),
                "STARCRAFT_DATA_DIR": os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"),
                "BRIDGE_MAP_FILE": plan["native_map"], "BRIDGE_SCENARIO_CONFIG": plan["scenario"],
                "BRIDGE_RULES_CONFIG": plan["mapping"],
                "BRIDGE_SPAWN_JOURNAL": str(runtime / "spawn-queue.json"),
                "BRIDGE_RUNTIME_DIR": str(runtime / "native"),
                "BRIDGE_SERVER_DATA_DIR": str(runtime / "server"),
                "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_FRAME_MS": "10",
                "BRIDGE_DISABLE_ASSAULT_AI": "1",
                "BRIDGE_TEST_BRIDGE_PID_FILE": str(runtime / "bridge.pid")})
    log, restart_log = runtime / "session.log", runtime / "restart.log"
    restarted = None
    checks = {}
    with log.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 55
            content = ""
            while time.monotonic() < deadline:
                content = log.read_text(errors="replace")
                if ("enemy production receipt request=" in content and
                        "actor morph id=" in content and "type=zerg_egg" in content):
                    break
                if process.poll() is not None:
                    break
                time.sleep(.25)
            checks["funded_train"] = bool(re.search(
                r"enemy train request=enemy-train:[^ ]+:1 accepted=1 reason= minerals=300->250", content))
            egg = re.search(r"actor morph id=(openbw:\d+) from=zerg_larva "
                            r"type=zerg_egg phase=incomplete generation=(\d+)", content)
            checks["larva_egg_canonical_binding"] = bool(egg)
            if not all(checks.values()):
                raise AssertionError("initial funded train or egg morph missing")
            os.kill(int((runtime / "bridge.pid").read_text()), signal.SIGTERM)
            with restart_log.open("w") as resumed_stream:
                restarted = subprocess.Popen([str(ROOT / "build/world-bridge"),
                    "--park", "127.0.0.1:" + env["STARCOASTER_BRIDGE_PORT"],
                    "--openbw", "127.0.0.1:" + env["BRIDGE_OPENBW_PORT"],
                    "--controller", "127.0.0.1:" + env["BRIDGE_CONTROLLER_PORT"],
                    "--scenario", plan["scenario"], "--rules", plan["mapping"],
                    "--spawn-journal", env["BRIDGE_SPAWN_JOURNAL"]], cwd=ROOT, env=env,
                    stdout=resumed_stream, stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 60
                resumed = ""
                while time.monotonic() < deadline:
                    resumed = restart_log.read_text(errors="replace")
                    content = log.read_text(errors="replace")
                    if ("actor morph id=" in resumed and "type=zerg_zergling" in resumed and
                            "native_validated" in content and
                            "enemy production receipt request=" in resumed):
                        break
                    if process.poll() is not None or restarted.poll() is not None:
                        break
                    time.sleep(.25)
                combined = content + "\n" + resumed
                checks["bridge_reconnected"] = "OpenBW ready targets=" in resumed
                checks["egg_zergling_same_identity"] = bool(egg and re.search(
                    r"actor morph id=" + re.escape(egg.group(1)) +
                    r" from=zerg_egg type=zerg_zergling phase=incomplete generation=" +
                    egg.group(2), combined) and re.search(
                    r"actor morph id=" + re.escape(egg.group(1)) +
                    r" from=zerg_zergling type=zerg_zergling phase=complete generation=" +
                    egg.group(2), combined))
                actor_ids = re.findall(r"actor spawn id=(openbw:\d+) generation=\d+ type=zerg_zergling", combined)
                checks["paired_birth"] = bool(egg and any(actor != egg.group(1) for actor in actor_ids))
                native_orders = re.findall(r"\[world\] enemy train request=(enemy-train:[^ ]+) accepted=1", content)
                checks["native_orders_once"] = len(native_orders) == len(set(native_orders))
                native_actor_ids = re.findall(r"\[world\] actor-spawn id=(openbw:\d+) native=", content)
                checks["native_actor_ids_once"] = len(native_actor_ids) == len(set(native_actor_ids))
                checks["production_resumed_after_reconnect"] = bool(re.search(
                    r"enemy production receipt request=enemy-train:[^ ]+:3 accepted=true", resumed))
                checks["no_free_wave"] = "scenario spawn request=" not in combined
                journal = json.loads((runtime / "spawn-queue.json.scenario.json").read_text())
                orders = journal["enemy_production"]["orders"]
                checks["durable_orders"] = bool(orders and orders[0]["state"] == "accepted" and
                                                  len({order["request_id"] for order in orders}) == len(orders))
        finally:
            stop(restarted)
            stop(process)
    checks["source_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == before
    result = {"checks": checks, "source_sha256": before, "scenario": plan["scenario"]}
    (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    print("Evidence:", runtime)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
