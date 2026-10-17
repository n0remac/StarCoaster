#!/usr/bin/env python3
"""Verify native Hydralisk and Ultralisk damage to the Frontier carousel."""

import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
PARK = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
SCENARIO = ROOT / "scenarios/frontier-outpost/scenario.json"
PORTS = (40010, 40011, 40012, 11753)


def wait_for_ports() -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        for port in PORTS:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    break
        else:
            return
        time.sleep(1)
    raise TimeoutError("native session ports remained occupied")


def verify_log(log: str, unit_type: str, scenario_id: str) -> dict:
    actor = "openbw:3001"
    checks = {
        "native_unit_created": bool(re.search(r"index=0 type=" + unit_type + r" x=\d+", log)),
        "native_actor_bound": bool(re.search(
            r"actor binding id=" + actor + r" participant=controller native=\d+ active=true", log)),
        "combat_demolition_confirmed": "combat demolition synchronized id=openrct2:ride:0#1" in log,
        "objective_defeat": f"scenario {scenario_id} outcome=defeat" in log,
    }
    last_snapshot = None
    last_hp = None
    damage = []
    for line in log.splitlines():
        if "RTS Bridge apply tick=" in line:
            sequence = re.search(r"seq=(\d+)", line)
            zergling = re.search(r"openbw:2000,[^;\r\n]+", line)
            spawned = re.search(r"openbw:3001,[^;\r\n\x1b]+", line)
            if sequence and zergling and spawned:
                zergling_fields = zergling.group().split(",")
                spawned_fields = spawned.group().split(",")
                if len(zergling_fields) >= 5 and len(spawned_fields) >= 11:
                    last_snapshot = (int(sequence.group(1)), zergling_fields[4],
                                     spawned_fields[4], spawned_fields[6], spawned_fields[9])
        if "native target state id=openrct2:ride:0#1" in line:
            hp = re.search(r"hp=(\d+)", line)
            if hp:
                current_hp = int(hp.group(1))
                if (last_hp is not None and current_hp < last_hp and last_snapshot
                        and last_snapshot[1] == "walk" and last_snapshot[2] == "attack"
                        and last_snapshot[3] == unit_type and last_snapshot[4] == "0"):
                    damage.append({"snapshot_sequence": last_snapshot[0],
                                   "carousel_hp_before": last_hp,
                                   "carousel_hp_after": current_hp})
                last_hp = current_hp
    checks["unit_damaged_carousel_before_zergling_attack"] = bool(damage)
    checks["carousel_reached_zero_hp"] = last_hp == 0
    return {"checks": checks, "isolated_native_damage_samples": damage}


def run_unit(root: Path, unit_type: str) -> dict:
    name = unit_type.removeprefix("zerg_")
    out = root / name
    out.mkdir()
    scenario = json.loads(SCENARIO.read_text())
    scenario_id = f"frontier-{name}-structure-live"
    scenario.update(scenario_id=scenario_id, display_name=f"{name.title()} Structure Live Test")
    scenario["initial_ai"]["delay_frames"] = 0
    scenario["waves"] = [{"id": f"{name}-objective", "trigger": {"type": "on_ready"},
                          "groups": [{"unit_type": unit_type, "count": 1,
                                      "spawn_zone": "south-approach"}]}]
    config = out / "scenario.json"
    config.write_text(json.dumps(scenario, indent=2) + "\n")
    native_map = out / "map.scm"
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", str(config),
                    "--output", str(native_map)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    wait_for_ports()
    environment = os.environ.copy() | {
        "BRIDGE_SCENARIO_CONFIG": str(config),
        "BRIDGE_RULES_CONFIG": str(ROOT / "scenarios/frontier-outpost/mapping.json"),
        "BRIDGE_MAP_FILE": str(native_map),
        "BRIDGE_SPAWN_JOURNAL": str(out / "spawn-queue.json"),
        "BRIDGE_LAUNCH_CLIENT": "0",
        "BRIDGE_SERVER_DATA_DIR": str(out / "server"),
        "OPENBW_LOCAL_PATH": str(out / "openbw-local.socket"),
    }
    log_path = out / "session.log"
    with log_path.open("w") as stream:
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), str(PARK)],
                                   cwd=ROOT, env=environment, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                log = log_path.read_text(errors="replace")
                if f"scenario {scenario_id} outcome=defeat" in log:
                    break
                if process.poll() is not None or "invalid scenario configuration" in log:
                    break
                time.sleep(1)
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    result = verify_log(log_path.read_text(errors="replace"), unit_type, scenario_id)
    result.update(unit_type=unit_type, log=str(log_path),
                  status="passed" if all(result["checks"].values()) else "failed")
    (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    if not all((Path(os.environ.get(name, "")).is_dir()
                for name in ("RCT2_DATA_DIR", "STARCRAFT_DATA_DIR"))) or not PARK.is_file():
        raise RuntimeError("licensed RCT2 and StarCraft data and the Frontier park are required")
    root = ROOT / "run-data" / f"zerg-structure-assault-live-{int(time.time())}"
    root.mkdir()
    results = [run_unit(root, unit) for unit in ("zerg_hydralisk", "zerg_ultralisk")]
    passed = all(result["status"] == "passed" for result in results)
    report = {"status": "passed" if passed else "failed", "results": results}
    (root / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"run_directory": str(root), "status": report["status"],
                      "checks": [result["checks"] for result in results]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
