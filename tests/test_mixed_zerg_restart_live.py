#!/usr/bin/env python3
"""Verify a living mixed wave survives a same-session Go bridge restart."""

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
PORTS = (40010, 40011, 40012, 11753)
KINDS = ("zerg_zergling", "zerg_hydralisk", "zerg_ultralisk")


def wait_until(check, seconds: int, message: str):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.25)
    raise TimeoutError(message)


def wait_for_ports() -> None:
    def available():
        for port in PORTS:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    return False
        return True
    wait_until(available, 180, "native session ports remained occupied")


def bridge_pid(config: Path) -> int:
    rows = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True).splitlines()
    matches = []
    for row in rows:
        parts = row.strip().split(maxsplit=1)
        if len(parts) == 2 and "/build/world-bridge" in parts[1] and str(config) in parts[1]:
            matches.append(int(parts[0]))
    if len(matches) != 1:
        raise RuntimeError(f"expected one scenario bridge, found {matches}")
    return matches[0]


def read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def main() -> None:
    if not all(Path(os.environ.get(name, "")).is_dir()
               for name in ("RCT2_DATA_DIR", "STARCRAFT_DATA_DIR")) or not PARK.is_file():
        raise RuntimeError("licensed RCT2 and StarCraft data and the Frontier park are required")
    run = ROOT / "run-data" / f"mixed-zerg-restart-live-{int(time.time())}"
    run.mkdir()
    scenario = json.loads((ROOT / "scenarios/frontier-outpost/scenario.json").read_text())
    scenario.update(scenario_id="frontier-mixed-restart-live", display_name="Mixed Zerg Restart Live",
                    mode="park_defense", objectives=[], waves=[], victory={}, defeat={},
                    initial_ai={"strategy": "park_defense", "delay_frames": 0},
                    park_defense={"initial_delay_frames": 1, "interval_frames": 2880,
                                  "manual_cooldown_frames": 360,
                                  "spawn_zones": ["south-approach", "east-entrance"],
                                  "wave_tiers": [{"from_wave": 1, "groups": [
                                      {"unit_type": kind, "count": 1} for kind in KINDS]}]})
    scenario["starting_units"]["zerglings"] = []
    config = run / "scenario.json"
    config.write_text(json.dumps(scenario, indent=2) + "\n")
    native_map = run / "map.scm"
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", str(config),
                    "--output", str(native_map)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    wait_for_ports()
    queue_path = run / "spawn-queue.json"
    journal_path = Path(str(queue_path) + ".scenario.json")
    rules = ROOT / "scenarios/frontier-outpost/mapping.json"
    env = os.environ.copy() | {"BRIDGE_SCENARIO_CONFIG": str(config),
                               "BRIDGE_RULES_CONFIG": str(rules),
                               "BRIDGE_MAP_FILE": str(native_map),
                               "BRIDGE_SPAWN_JOURNAL": str(queue_path),
                               "BRIDGE_LAUNCH_CLIENT": "0",
                               "BRIDGE_DISABLE_ASSAULT_AI": "1",
                               "BRIDGE_SERVER_DATA_DIR": str(run / "server"),
                               "OPENBW_LOCAL_PATH": str(run / "openbw-local.socket")}
    processes = []
    streams = []

    def start(name: str, command: list[str]):
        stream = (run / f"{name}.log").open("w")
        streams.append(stream)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    report = {"status": "failed", "run_directory": str(run)}
    try:
        session = start("session", [str(ROOT / "scripts/run-world-session.sh"), str(PARK)])
        wait_until(lambda: "WORLD_READY" in read(run / "session.log"),
                   90, "world session not ready")

        def ready_wave():
            if not journal_path.exists():
                return None
            journal = json.loads(journal_path.read_text())
            waves = journal.get("waves") or []
            if len(waves) != 1:
                return None
            units = waves[0].get("units") or []
            if len(units) != 3 or [unit["unit_type"] for unit in units] != list(KINDS):
                return None
            if all(unit.get("actor_id") and unit["state"] in ("ready", "active") for unit in units):
                return journal
            return None

        before = wait_until(ready_wave, 75, "mixed native wave did not become ready")
        ids = [unit["actor_id"] for unit in before["waves"][0]["units"]]
        requests = [unit["attempts"][-1]["request_id"] for unit in before["waves"][0]["units"]]
        queue_before = json.loads(queue_path.read_text())["order"]
        old_bridge = bridge_pid(config)
        os.kill(old_bridge, signal.SIGTERM)
        wait_until(lambda: not Path(f"/proc/{old_bridge}").exists(), 8,
                   "original bridge did not stop")
        restart = start("bridge-restart", [str(ROOT / "build/world-bridge"),
                                           "--scenario", str(config), "--rules", str(rules),
                                           "--spawn-journal", str(queue_path)])
        wait_until(lambda: "actor reconcile living=" in read(run / "bridge-restart.log"),
                   90, "restart did not reconcile actors")
        after = json.loads(journal_path.read_text())
        after_units = after["waves"][0]["units"]
        report["checks"] = {
            "same_session": after["session"] == before["session"],
            "same_types": [unit["unit_type"] for unit in after_units] == list(KINDS),
            "same_actor_ids": [unit.get("actor_id") for unit in after_units] == ids,
            "same_request_ids": [unit["attempts"][-1]["request_id"] for unit in after_units] == requests,
            "no_duplicate_requests": json.loads(queue_path.read_text())["order"] == queue_before,
            "native_reconciliation": "actor reconcile living=" in read(run / "bridge-restart.log"),
        }
        client_dir = run / "client"
        (client_dir / "plugin").mkdir(parents=True)
        (client_dir / "plugin/rts-bridge.js").write_text(
            (ROOT / "openrct2-plugin/rts-bridge.js").read_text())
        (client_dir / "plugin/mixed-restart-observer.js").write_text('''
registerPlugin({name: "Mixed Zerg Restart Observer", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
        if (network.mode !== "client") return;
        var ticks = 0, last = "";
        context.subscribe("interval.tick", function () {
            if (++ticks % 20 !== 0 || !rtsBridge) return;
            var snapshot = rtsBridge.getActors();
            if (!snapshot || !Array.isArray(snapshot.units)) return;
            var actors = snapshot.units.filter(function (unit) {
                return /^openbw:30[0-9]+$/.test(unit.id) && unit.hp > 0;
            }).map(function (unit) { return unit.id + ":" + unit.kind; }).sort().join(",");
            if (actors && actors !== last) {
                console.log("MIXED_RESTART_ACTORS " + actors);
                last = actors;
            }
        });
    }});
''')
        client = start("client", [str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1",
                                  "--headless", "--port=11753",
                                  f"--rct2-data-path={env['RCT2_DATA_DIR']}",
                                  f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
                                  f"--user-data-path={client_dir}"])

        def has_all_actors():
            lines = [line for line in read(run / "client.log").splitlines()
                     if "MIXED_RESTART_ACTORS " in line]
            return any(all(f"{actor}:{kind}" in line
                           for actor, kind in zip(ids, KINDS)) for line in lines)

        report["checks"]["client_sees_same_enemy_types"] = bool(wait_until(
            has_all_actors, 60, "client did not observe all restored enemy types"))
        report.update(status="passed" if all(report["checks"].values()) else "failed",
                      actor_ids=ids, request_ids=requests,
                      log_paths=[str(run / "session.log"), str(run / "bridge-restart.log"),
                                 str(run / "client.log")])
    except Exception as error:
        report["error"] = str(error)
    finally:
        (run / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for process in reversed(processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for stream in streams:
            stream.close()
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
