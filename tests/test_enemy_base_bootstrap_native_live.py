#!/usr/bin/env python3
"""Short, isolated B1 native colony bootstrap probe on one ordinary park."""

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
from prepare_existing_defense import prepare  # noqa: E402
from scenario_package import build_native_map, ensure_park  # noqa: E402


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
    parser.add_argument("--expect-blocked", action="store_true")
    parser.add_argument("--fixture-no-colony", action="store_true",
                        help="test-only blocked colony on an otherwise valid Terran park")
    parser.add_argument("--restart-bridge", action="store_true")
    args = parser.parse_args()
    source, runtime = args.source.resolve(strict=True), args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be under ignored run-data")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    runtime.mkdir(parents=True, exist_ok=True)
    plan = prepare(str(source), runtime / "prepared")
    scenario = json.loads(Path(plan["scenario"]).read_text())
    if args.fixture_no_colony:
        if not args.expect_blocked or scenario["economy"]["layout_state"] != "ready":
            parser.error("blocked colony fixture requires a ready Terran economy and --expect-blocked")
        base = scenario["enemy_base"]
        base.update({"layout_state": "blocked", "blocked_reason": "no_valid_perimeter_site",
                     "initial_minerals": 0, "minimum_supply": 0, "max_train_orders": 0,
                     "structures": [], "supply_tile": [], "assembly_tile": [],
                     "approach_tile": [], "terran_approach_tile": []})
        scenario["initial_structures"] = [item for item in scenario["initial_structures"]
                                           if item["faction"] != "zerg"]
        Path(plan["scenario"]).write_text(json.dumps(scenario, indent=2) + "\n")
        metadata_path = Path(plan["scenario"]).parent / "package.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["enemy_base_layout"] = {"policy_version": base["policy_version"], "state": "blocked",
                                         "reason": "no_valid_perimeter_site", "structures": []}
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    expected_state = "blocked" if args.expect_blocked else "ready"
    if scenario["enemy_base"]["layout_state"] != expected_state:
        raise RuntimeError("enemy site state differs from expectation: " +
                           scenario["enemy_base"]["layout_state"])
    ensure_park(plan)
    build_native_map(plan)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise AssertionError("source park changed")
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
    log = runtime / "session.log"
    result = {"source_sha256": before, "scenario": plan["scenario"],
              "enemy_base": scenario["enemy_base"], "checks": {}}
    restarted = None
    with log.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 70
            while time.monotonic() < deadline:
                content = log.read_text(errors="replace")
                checks = {"world_ready": "WORLD_READY entities=" in content,
                    "status_accepted": "WORLD_SCENARIO_STATUS scenario=" in content
                        and "WORLD_SCENARIO_STATUS_ERROR" not in content,
                    "no_free_waves": "scenario spawn request=" not in content}
                if args.expect_blocked:
                    checks.update({"blocked_status": "enemy_base=blocked" in content and
                        "enemy_reason=" + scenario["enemy_base"]["blocked_reason"] in content,
                        "no_colony_targets": "native target state id=scenario:enemy-" not in content})
                else:
                    checks.update({"publisher_validated": "enemy base native role=publisher accepted=true" in content,
                        "controller_validated": "enemy base native role=controller accepted=true" in content,
                        "hatchery_bound": "native target state id=scenario:enemy-hatchery proxy=openbw:" in content,
                        "pool_bound": "native target state id=scenario:enemy-spawning-pool proxy=openbw:" in content,
                        "native_status": "enemy_base=native_validated" in content})
                result["checks"] = checks
                if all(checks.values()):
                    break
                if process.poll() is not None:
                    break
                time.sleep(.25)
            if args.restart_bridge and not args.expect_blocked and all(result["checks"].values()):
                before_native = re.search(
                    r'enemy base native role=publisher accepted=true hatchery=(\d+) pool=(\d+) overlord=(\d+)',
                    content)
                old_bridge = int((runtime / "bridge.pid").read_text())
                os.kill(old_bridge, signal.SIGTERM)
                restart_log = runtime / "restart.log"
                with restart_log.open("w") as restarted_stream:
                    restarted = subprocess.Popen([str(ROOT / "build/world-bridge"),
                        "--park", "127.0.0.1:" + env["STARCOASTER_BRIDGE_PORT"],
                        "--openbw", "127.0.0.1:" + env["BRIDGE_OPENBW_PORT"],
                        "--controller", "127.0.0.1:" + env["BRIDGE_CONTROLLER_PORT"],
                        "--scenario", plan["scenario"], "--rules", plan["mapping"],
                        "--spawn-journal", env["BRIDGE_SPAWN_JOURNAL"]], cwd=ROOT, env=env,
                        stdout=restarted_stream, stderr=subprocess.STDOUT, start_new_session=True)
                    deadline = time.monotonic() + 50
                    while time.monotonic() < deadline:
                        resumed = restart_log.read_text(errors="replace")
                        after_native = re.search(
                            r'enemy base native role=publisher accepted=true hatchery=(\d+) pool=(\d+) overlord=(\d+)',
                            resumed)
                        host_after = log.read_text(errors="replace")
                        if ("OpenBW ready targets=" in resumed and host_after.count("WORLD_READY entities=") >= 2 and after_native and
                                "enemy base native role=controller accepted=true" in resumed):
                            break
                        if restarted.poll() is not None or process.poll() is not None:
                            break
                        time.sleep(.25)
                    result["checks"]["restart_native_ids_stable"] = bool(
                        before_native and after_native and before_native.groups() == after_native.groups())
                    result["checks"]["restart_world_ready"] = ("OpenBW ready targets=" in resumed and
                        host_after.count("WORLD_READY entities=") >= 2)
                    result["checks"]["restart_both_validated"] = bool(after_native and
                        "enemy base native role=controller accepted=true" in resumed and
                        host_after.count("enemy_base=native_validated") >= 2)
                    result["checks"]["restart_no_free_waves"] = "scenario spawn request=" not in resumed
        finally:
            if restarted is not None:
                os.killpg(restarted.pid, signal.SIGTERM)
                try:
                    restarted.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(restarted.pid, signal.SIGKILL)
                    restarted.wait()
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    result["source_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == before
    (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["checks"], indent=2), flush=True)
    print("Evidence:", runtime, flush=True)
    if not all(result["checks"].values()) or not result["source_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
