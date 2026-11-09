#!/usr/bin/env python3
"""Short native compatibility check for the compact authored Zerg base."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scenario_package import build_native_map, ensure_park, resolve, session_environment  # noqa: E402
from test_enemy_base_bootstrap_native_live import free_ports  # noqa: E402
from test_enemy_base_production_native_live import stop  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be inside ignored run-data")
    runtime.mkdir(parents=True, exist_ok=True)
    plan = resolve("mt-zergling")
    scenario_path = Path(plan["scenario"])
    before = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    scenario = json.loads(scenario_path.read_text())
    if scenario.get("enemy_base") or scenario["park_defense"].get("spawn_policy") == "base_production":
        raise AssertionError("authored scenario unexpectedly switched to generated base policy")
    ensure_park(plan)
    native_map = build_native_map(plan, runtime / "mt-zergling.scm")
    ports = dict(zip(("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT", "BRIDGE_OPENBW_PORT",
                      "BRIDGE_CONTROLLER_PORT"), map(str, free_ports(4))))
    env = session_environment(plan, {"BRIDGE_MAP_FILE": str(native_map),
        "BRIDGE_SPAWN_JOURNAL": str(runtime / "spawn-queue.json"),
        "BRIDGE_RUNTIME_DIR": str(runtime / "native"),
        "BRIDGE_SERVER_DATA_DIR": str(runtime / "server"),
        "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_FRAME_MS": "10",
        "BRIDGE_DISABLE_ASSAULT_AI": "1", **ports})
    log = runtime / "session.log"
    checks = {}
    with log.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                content = log.read_text(errors="replace")
                checks = {"world_ready": "WORLD_READY entities=" in content,
                    "hatchery_native": "native target state id=scenario:western-hatchery proxy=openbw:" in content,
                    "pool_native": "native target state id=scenario:western-spawning-pool proxy=openbw:" in content,
                    "authored_status": "WORLD_SCENARIO_STATUS scenario=mt-zergling" in content,
                    "no_generated_enemy_train": "enemy production intent request=" not in content}
                if all(checks.values()) or process.poll() is not None:
                    break
                time.sleep(.25)
        finally:
            stop(process)
    checks["authored_source_unchanged"] = hashlib.sha256(scenario_path.read_bytes()).hexdigest() == before
    result = {"checks": checks, "source_sha256": before, "scenario": plan["scenario"]}
    (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    print("Evidence:", runtime)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
