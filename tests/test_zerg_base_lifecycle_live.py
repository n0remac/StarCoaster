#!/usr/bin/env python3
"""Licensed native combat, bridge restart, and client rejoin check for the Zerg base."""

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


def wait_for(path, marker, processes, limit):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        content = path.read_text(errors="replace") if path.is_file() else ""
        if marker in content:
            return content
        if any(process.poll() is not None for process in processes):
            raise RuntimeError(f"process exited while waiting for {marker}; see {path}")
        time.sleep(.5)
    raise TimeoutError(f"missing {marker}; see {path}")


def start_client(run, name, env, driver=False):
    data = run / name
    (data / "plugin").mkdir(parents=True)
    (data / "plugin/rts-bridge.js").write_bytes((ROOT / "openrct2-plugin/rts-bridge.js").read_bytes())
    prefix = "var STARCOASTER_ZERG_BASE_DRIVER = true;\nvar STARCOASTER_ZERG_BASE_LIFECYCLE = true;\n" if driver else ""
    (data / "plugin/zerg-base-capture-probe.js").write_text(prefix + (
        ROOT / "scripts/zerg-base-capture-probe.js").read_text())
    log = (run / f"{name}.log").open("w")
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1", "--headless",
               "--port=11753", f"--rct2-data-path={env['RCT2_DATA_DIR']}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={data}"]
    return subprocess.Popen(command, env=env, cwd=ROOT, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True), log


def main():
    plan = resolve("mt-zergling")
    ensure_park(plan)
    run = ROOT / "run-data" / f"zerg-base-lifecycle-{int(time.time())}"
    run.mkdir(parents=True)
    native_map = build_native_map(plan, run / "mt-zergling.scm")
    env = session_environment(plan, {"BRIDGE_MAP_FILE": str(native_map),
        "BRIDGE_SPAWN_JOURNAL": str(run / "spawns.json"),
        "BRIDGE_SERVER_DATA_DIR": str(run / "server"), "BRIDGE_LAUNCH_CLIENT": "0",
        "BRIDGE_DISABLE_ASSAULT_AI": "1", "OPENBW_LOCAL_PATH": str(run / "openbw-local.socket")})
    processes, logs = [], []
    try:
        server_log = (run / "server.log").open("w")
        logs.append(server_log)
        session = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   env=env, cwd=ROOT, stdout=server_log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        processes.append(session)
        wait_for(run / "server.log", "WORLD_READY", [session], 85)
        commander, log = start_client(run, "client-a", env, driver=True)
        processes.append(commander); logs.append(log)
        observer, log = start_client(run, "client-b", env)
        processes.append(observer); logs.append(log)
        for name in ("client-a", "client-b"):
            wait_for(run / f"{name}.log", "ZERG_BASE_HEALTH id=scenario:western-spawning-pool owner=0 hp=750",
                     [session, commander, observer], 35)
        wait_for(run / "server.log", "WORLD_REMOVAL id=scenario:western-spawning-pool state=confirmed",
                 [session, commander, observer], 95)
        wait_for(run / "client-b.log", "ZERG_BASE_PRESENT id=scenario:western-spawning-pool present=false",
                 [session, commander, observer], 20)
        before = (run / "server.log").read_text(errors="replace")
        old = re.findall(r"native target state id=scenario:western-hatchery proxy=(openbw:\d+) hp=(\d+)", before)
        process_list = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
        bridge = next((int(row.split(None, 1)[0]) for row in process_list.splitlines()
                       if row.strip().endswith(str(ROOT / "build/world-bridge") +
                                                " --scenario " + plan["scenario"] +
                                                " --rules " + plan["mapping"] +
                                                " --spawn-journal " + env["BRIDGE_SPAWN_JOURNAL"])), None)
        if bridge is None:
            raise RuntimeError("could not identify the active world bridge")
        os.kill(bridge, signal.SIGTERM)
        restart_log = (run / "restart.log").open("w")
        logs.append(restart_log)
        restarted = subprocess.Popen([str(ROOT / "build/world-bridge"), "--scenario", plan["scenario"],
            "--rules", plan["mapping"], "--spawn-journal", env["BRIDGE_SPAWN_JOURNAL"]],
            env=env, cwd=ROOT, stdout=restart_log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(restarted)
        wait_for(run / "restart.log", "OpenBW ready targets=3", [session, restarted], 70)
        os.killpg(observer.pid, signal.SIGTERM)
        observer.wait(timeout=8)
        rejoined, log = start_client(run, "client-b-rejoin", env)
        processes.append(rejoined); logs.append(log)
        wait_for(run / "client-b-rejoin.log", "ZERG_BASE_PRESENT id=scenario:western-spawning-pool present=false",
                 [session, restarted, rejoined], 45)
        after = (run / "restart.log").read_text(errors="replace")
        joined = (run / "client-b-rejoin.log").read_text(errors="replace")
        new = re.findall(r"native target state id=scenario:western-hatchery proxy=(openbw:\d+) hp=(\d+)", after)
        checks = {
            "native_both_initially": "type=Zerg_Hatchery hp=1250" in before
                and "type=Zerg_Spawning_Pool hp=750" in before,
            "both_clients_initial_owner": all("ZERG_BASE_HEALTH id=scenario:western-spawning-pool owner=0 hp=750"
                                              in (run / f"client-{letter}.log").read_text(errors="replace")
                                              for letter in "ab"),
            "combat_destroyed_pool": "WORLD_REMOVAL id=scenario:western-spawning-pool state=confirmed" in before,
            "both_clients_saw_removal": all("ZERG_BASE_PRESENT id=scenario:western-spawning-pool present=false"
                                            in (run / f"client-{letter}.log").read_text(errors="replace")
                                            for letter in "ab"),
            "same_hatchery_after_bridge_restart": bool(old and new) and old[-1] == new[-1],
            "no_pool_resurrection": "scenario:western-spawning-pool" not in after
                and "ZERG_BASE_PRESENT id=scenario:western-spawning-pool present=false" in joined,
            "no_hatchery_duplicate": before.count("target id=scenario:western-hatchery proxy=") == 1
                and "target id=scenario:western-hatchery proxy=" not in after,
            "rejoined_client_kept_hatchery": "ZERG_BASE_PRESENT id=scenario:western-hatchery present=true" in joined,
        }
        (run / "verification.json").write_text(json.dumps({"checks": checks,
            "hatchery_before": old, "hatchery_after": new}, indent=2) + "\n")
        print(json.dumps({"run": str(run), "checks": checks}, indent=2))
        if not all(checks.values()):
            raise AssertionError(checks)
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
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
