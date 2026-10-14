#!/usr/bin/env python3
"""Focused two-client Midway defense, outcome, and restart check."""
import argparse
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
sys.path.insert(0, str(ROOT / "tests"))
from scenario_package import resolve, ensure_park, build_native_map  # noqa: E402
from test_scenario_runtime_live import wait_for_ports, wait_for, bridge_pid  # noqa: E402


def native_wave_approaches(client_log, waves, fixture):
    """Require each wave to move from its spawn toward the exported wheel."""
    wheel = next(target for target in fixture["targets"] if target["id"] == "midway-wheel")
    center = wheel["structure_center"]
    actor_to_wave = {unit["actor_id"]: wave["id"] for wave in waves
                     for unit in wave["units"] if unit.get("actor_id")}
    tracks = {actor: [] for actor in actor_to_wave}
    for line in client_log.splitlines():
        if "RTS Bridge apply tick=" not in line:
            continue
        for match in re.finditer(r"(openbw:\d+),(-?\d+),(-?\d+),", line):
            if match[1] in tracks:
                tracks[match[1]].append((int(match[2]), int(match[3])))
    reached = {wave["id"]: False for wave in waves}
    for actor, points in tracks.items():
        if not points:
            continue
        origin = points[0]
        for x, y in points:
            moved = abs(x - origin[0]) + abs(y - origin[1]) >= 192
            near_wheel = (x - center["x"]) ** 2 + (y - center["y"]) ** 2 <= 320 ** 2
            if moved and near_wheel:
                reached[actor_to_wave[actor]] = True
                break
    return reached


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("victory", "defeat"), required=True)
    args = parser.parse_args()
    plan = resolve("midway-junction")
    ensure_park(plan)
    build_native_map(plan)
    run = ROOT / "run-data" / f"midway-live-{args.mode}-{int(time.time())}"
    run.mkdir(parents=True)
    env = os.environ.copy() | {
        "RCT2_DATA_DIR": os.environ.get("RCT2_DATA_DIR", str(Path.home()/"games/rct2")),
        "STARCRAFT_DATA_DIR": os.environ.get("STARCRAFT_DATA_DIR", str(Path.home()/"games/starcraft")),
        "BRIDGE_SCENARIO_CONFIG": plan["scenario"], "BRIDGE_RULES_CONFIG": plan["mapping"],
        "BRIDGE_MAP_FILE": plan["native_map"], "BRIDGE_SPAWN_JOURNAL": str(run/"spawn-queue.json"),
        "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(run/"server"),
        "OPENBW_LOCAL_PATH": str(run/"openbw-local.socket")}
    processes, streams = [], []
    def start(name, command):
        stream = (run/f"{name}.log").open("w"); streams.append(stream)
        proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(proc)
        return proc
    def client(name, commander=False):
        directory = run/name
        (directory/"plugin").mkdir(parents=True)
        (directory/"plugin/rts-bridge.js").write_text((ROOT/"openrct2-plugin/rts-bridge.js").read_text())
        if commander:
            (directory/"plugin/midway-defense-probe.js").write_text((ROOT/"scripts/midway-defense-probe.js").read_text())
        return start(name, [str(ROOT/"build/openrct2/openrct2-cli"), "join", "127.0.0.1", "--headless", "--port=11753",
            f"--rct2-data-path={env['RCT2_DATA_DIR']}",
            f"--openrct2-data-path={ROOT/'build/openrct2-stage/usr/local/share/openrct2'}",
            f"--user-data-path={directory}"])
    report = {"mode": args.mode, "run_directory": str(run), "checks": {}, "status": "failed"}
    try:
        wait_for_ports()
        session = start("session", [str(ROOT/"scripts/run-world-session.sh"), plan["park"]])
        wait_for(run/"session.log", r"WORLD_READY.*navigation=native", session, 90)
        a = client("client-a", args.mode == "victory")
        wait_for(run/"client-a.log", r"RTS Bridge apply tick=", a, 60)
        b = client("client-b")
        wait_for(run/"client-b.log", r"RTS Bridge apply tick=", b, 60)
        report["checks"]["two_clients_ready"] = True
        first = next(line for line in (run/"client-a.log").read_text(errors="replace").splitlines()
                     if "RTS Bridge apply tick=" in line)
        report["checks"]["starting_actors"] = all(f"openbw:{1000+i}," in first for i in range(6)) \
            and all(f"openbw:{2000+i}," in first for i in range(8))
        if args.mode == "victory":
            wait_for(run/"client-a.log", r"MIDWAY_SPAWN accepted=true", a, 60)
            wait_for(run/"session.log", r"wave=opening-assault state=ready", session, 90)
            old = bridge_pid(Path(plan["scenario"]))
            os.kill(old, signal.SIGTERM)
            for _ in range(40):
                if not Path(f"/proc/{old}").exists(): break
                time.sleep(.1)
            restart = start("bridge-restart", [str(ROOT/"build/world-bridge"), "--scenario", plan["scenario"],
                "--rules", plan["mapping"], "--spawn-journal", str(run/"spawn-queue.json")])
            wait_for(run/"bridge-restart.log", r"OpenBW ready targets=", restart, 90)
            report["checks"]["bridge_restart"] = True
            os.killpg(b.pid, signal.SIGTERM); b.wait(timeout=8)
            b = client("client-b-reconnect")
            wait_for(run/"client-b-reconnect.log", r"WORLD_SCENARIO_STATUS scenario=midway-junction", b, 60)
            report["checks"]["client_reconnect"] = True
            terminal = restart
            terminal_log = run/"bridge-restart.log"
        else:
            terminal = session
            terminal_log = run/"session.log"
        wait_for(terminal_log, rf"scenario midway-junction outcome={args.mode}", terminal, 180,
                 r"scenario midway-junction outcome=defeat" if args.mode == "victory" else "")
        journal = json.loads(Path(str(run/"spawn-queue.json")+".scenario.json").read_text())
        waves = journal["waves"]
        report["waves"] = [{"id": w["id"], "state": w["state"], "units": len(w.get("units", []))} for w in waves]
        report["checks"]["expected_outcome"] = journal["outcome"] == args.mode
        report["checks"]["wave_ids"] = [w["id"] for w in waves] == ["opening-assault", "northern-flank", "southern-assault"]
        if args.mode == "victory":
            log = (run/"client-a.log").read_text(errors="replace")
            scenario = json.loads(Path(plan["scenario"]).read_text())
            zone_names = ("east-entrance", "north-midway", "south-service")
            counts = (4, 3, 5)
            report["checks"]["wave_counts_and_origins"] = all(
                len(w["units"]) == count and all(
                    (attempt["x"], attempt["y"]) in
                    {(x*32+16, y*32+16) for x,y in scenario["spawn_zones"][zone]["tiles"]}
                    for unit in w["units"] for attempt in unit["attempts"])
                for w,zone,count in zip(waves,zone_names,counts))
            report["checks"]["wave_timing"] = (waves[1]["triggered_frame"] >= journal["start_frame"] + 900
                and waves[2]["triggered_frame"] > waves[1]["triggered_frame"])
            actors = [u["actor_id"] for w in waves for u in w["units"] if u.get("actor_id")]
            report["checks"]["all_waves_cleared"] = all(w["state"] == "cleared" for w in waves)
            report["checks"]["unique_native_actors"] = len(actors) == len(set(actors)) == 12
            requests = [a["request_id"] for w in waves for u in w["units"] for a in u["attempts"]]
            report["checks"]["no_duplicate_wave_requests"] = len(requests) == len(set(requests))
            fixture = json.loads(Path(plan["fixture"]).read_text())
            report["native_wave_approaches"] = {
                "client_a": native_wave_approaches(log, waves, fixture),
                "client_b": native_wave_approaches(
                    (run/"client-b-reconnect.log").read_text(errors="replace"), waves, fixture),
            }
            report["checks"]["native_wave_approaches"] = all(
                all(result.values()) for result in report["native_wave_approaches"].values())
            report["checks"]["spawn_move_hold_attack"] = all(f"MIDWAY_{verb} accepted=true" in log for verb in ("SPAWN","MOVE","HOLD","ATTACK"))
            report["checks"]["reinforcement_move"] = "MIDWAY_REINFORCEMENT_MOVE accepted=true" in log
            status = r"WORLD_SCENARIO_STATUS scenario=midway-junction wave=3/3 state=cleared outcome=victory"
            wait_for(run/"client-a.log", status, a, 45)
            wait_for(run/"client-b-reconnect.log", status, b, 45)
            report["checks"]["matching_client_status"] = True
        else:
            report["checks"]["wheel_destroyed"] = "target destroyed id=openrct2:ride:0#1" in terminal_log.read_text(errors="replace")
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
        print(json.dumps(report, indent=2))
        if report["status"] != "passed": raise AssertionError("Midway live checks failed")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (run/"verification.json").write_text(json.dumps(report, indent=2)+"\n")
        for proc in reversed(processes):
            if proc.poll() is None: os.killpg(proc.pid, signal.SIGTERM)
        for proc in reversed(processes):
            try: proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=5)
        for stream in streams: stream.close()


if __name__ == "__main__":
    main()
