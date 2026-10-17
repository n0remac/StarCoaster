#!/usr/bin/env python3
"""Focused licensed native check for Mt. Zergling park actions and edge routes."""

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
from scenario_package import build_native_map, ensure_park, resolve, session_environment  # noqa: E402


def main():
    plan = resolve("mt-zergling")
    ensure_park(plan)
    run = ROOT / "run-data" / f"mt-zergling-gameplay-live-{int(time.time())}"
    client = run / "client"
    (client / "plugin").mkdir(parents=True)
    (client / "plugin/rts-bridge.js").write_bytes((ROOT / "openrct2-plugin/rts-bridge.js").read_bytes())
    (client / "plugin/mt-zergling-gameplay-probe.js").write_bytes(
        (ROOT / "scripts/mt-zergling-gameplay-probe.js").read_bytes())
    scenario = json.loads(Path(plan["scenario"]).read_text())
    scenario["park_defense"]["initial_delay_frames"] = 100000
    scenario["park_defense"]["interval_frames"] = 100000
    scenario["park_defense"]["manual_cooldown_frames"] = 1
    scenario_path = run / "scenario.json"
    scenario_path.write_text(json.dumps(scenario))
    native_map = build_native_map(plan, run / "mt-zergling.scm")
    env = session_environment(plan, {"BRIDGE_SCENARIO_CONFIG": str(scenario_path),
        "BRIDGE_MAP_FILE": str(native_map), "BRIDGE_SPAWN_JOURNAL": str(run / "spawns.json"),
        "BRIDGE_SERVER_DATA_DIR": str(run / "server"), "BRIDGE_CLIENT_DATA_DIR": str(client),
        "BRIDGE_LAUNCH_CLIENT": "0", "OPENBW_LOCAL_PATH": str(run / "openbw-local.socket")})
    server_log = (run / "session.log").open("w")
    client_log = (run / "client.log").open("w")
    processes = []
    try:
        session = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        processes.append(session)
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            if "WORLD_READY" in (run / "session.log").read_text(errors="replace"):
                break
            if session.poll() is not None:
                raise RuntimeError("session stopped before world readiness")
            time.sleep(0.5)
        else:
            raise TimeoutError("world readiness")
        rct2 = Path(env["RCT2_DATA_DIR"])
        game_data = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
        player = subprocess.Popen([str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1",
            "--headless", "--port=11753", f"--rct2-data-path={rct2}",
            f"--openrct2-data-path={game_data}", f"--user-data-path={client}"],
            cwd=ROOT, env=env, stdout=client_log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(player)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            source = (run / "client.log").read_text(errors="replace")
            journal_path = run / "spawns.json.scenario.json"
            journal = json.loads(journal_path.read_text()) if journal_path.is_file() else {}
            waves = journal.get("waves") or []
            third = next((wave for wave in waves if wave.get("sequence") == 3), None)
            sixth = next((wave for wave in waves if wave.get("sequence") == 6), None)
            hydralisks = [unit for unit in (third or {}).get("units", [])
                          if unit.get("unit_type") == "zerg_hydralisk"]
            ultralisks = [unit for unit in (sixth or {}).get("units", [])
                          if unit.get("unit_type") == "zerg_ultralisk"]
            hydra_bound = any(unit.get("actor_id") and re.search(
                re.escape(unit["actor_id"]) + r",[^;\n]*,zerg_hydralisk,\d+,\d+,0,", source)
                for unit in hydralisks)
            ultra_bound = any(unit.get("actor_id") and re.search(
                re.escape(unit["actor_id"]) + r",[^;\n]*,zerg_ultralisk,\d+,\d+,0,", source)
                for unit in ultralisks)
            starts = {id: (int(x), int(y)) for id, x, y in re.findall(
                r"MT_GAMEPLAY_ZERG_START id=(\S+) x=(\d+) y=(\d+)", source)}
            moves = {id: (int(x), int(y)) for id, x, y in re.findall(
                r"MT_GAMEPLAY_ZERG_MOVED id=(\S+) x=(\d+) y=(\d+)", source)}
            edges = {"north": any(y <= 14 * 32 for x, y in starts.values()),
                     "south": any(y >= 187 * 32 for x, y in starts.values()),
                     "west": any(x <= 14 * 32 for x, y in starts.values()),
                     "east": any(x >= 187 * 32 for x, y in starts.values())}
            inward = {"north": False, "south": False, "west": False, "east": False}
            for id, (x, y) in starts.items():
                if id not in moves:
                    continue
                mx, my = moves[id]
                inward["north"] |= y <= 14 * 32 and my - y >= 64
                inward["south"] |= y >= 187 * 32 and y - my >= 64
                inward["west"] |= x <= 14 * 32 and mx - x >= 64
                inward["east"] |= x >= 187 * 32 and x - mx >= 64
            if journal.get("total_triggered", 0) >= 6 and all(edges.values()) \
                    and all(inward.values()) and hydra_bound and ultra_bound:
                break
            if player.poll() is not None or session.poll() is not None:
                raise RuntimeError("native session stopped before gameplay checks")
            time.sleep(0.5)
        checks = {"park_open": "MT_GAMEPLAY_PARK_OPEN accepted=true" in source,
                  "ride_create": "MT_GAMEPLAY_RIDECREATE accepted=true" in source,
                  "ride_place": "MT_GAMEPLAY_TRACKPLACE accepted=true" in source,
                  "operator_group": "PARK_OPERATOR_GROUP player=" in (run / "session.log").read_text(errors="replace"),
                  "six_manual_waves": journal.get("total_triggered", 0) >= 6,
                  "manual_wave_status_confirmed": len(set(re.findall(
                      r"MT_GAMEPLAY_WAVE_STATUS request=\S+ accepted=true wave=(\S+) reason=", source))) >= 6,
                  "four_edge_starts": all(edges.values()), "four_edge_inward_routes": all(inward.values())}
        checks["tier_three_native_hydralisk"] = len(hydralisks) == 2 and hydra_bound
        checks["tier_six_native_ultralisk"] = len(ultralisks) == 1 and ultra_bound
        (run / "verification.json").write_text(json.dumps({"checks": checks,
            "edge_starts": edges, "inward_routes": inward,
            "wave_sequences": [(wave["id"], wave.get("sequence"), wave.get("composition"))
                               for wave in waves]}, indent=2) + "\n")
        print(json.dumps({"run": str(run), "checks": checks}, indent=2))
        if not all(checks.values()):
            raise AssertionError(f"failed gameplay checks: {checks}")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        server_log.close()
        client_log.close()


if __name__ == "__main__":
    main()
