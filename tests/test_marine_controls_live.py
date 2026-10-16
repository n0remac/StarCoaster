#!/usr/bin/env python3
"""Licensed Mt. Zergling check of the park action to native move-order path."""

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
    run = ROOT / "run-data" / f"marine-controls-live-{int(time.time())}"
    client = run / "client"
    (client / "plugin").mkdir(parents=True)
    for name in ("rts-bridge.js", "marine-controls-probe.js"):
        source = ROOT / ("openrct2-plugin" if name == "rts-bridge.js" else "scripts") / name
        (client / "plugin" / name).write_bytes(source.read_bytes())
    scenario = json.loads(Path(plan["scenario"]).read_text())
    scenario["park_defense"]["initial_delay_frames"] = 100000
    scenario["park_defense"]["interval_frames"] = 100000
    scenario_path = run / "scenario.json"
    scenario_path.write_text(json.dumps(scenario))
    native_map = build_native_map(plan, run / "mt-zergling.scm")
    env = session_environment(plan, {"BRIDGE_SCENARIO_CONFIG": str(scenario_path),
        "BRIDGE_MAP_FILE": str(native_map), "BRIDGE_SPAWN_JOURNAL": str(run / "spawns.json"),
        "BRIDGE_SERVER_DATA_DIR": str(run / "server"), "BRIDGE_CLIENT_DATA_DIR": str(client),
        "BRIDGE_LAUNCH_CLIENT": "0", "OPENBW_LOCAL_PATH": str(run / "openbw-local.socket")})
    processes = []
    logs = []
    try:
        for name in ("session", "client"):
            logs.append((run / f"{name}.log").open("w"))
        session = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=env, stdout=logs[0], stderr=subprocess.STDOUT,
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
        player = subprocess.Popen([str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1",
            "--headless", "--port=11753", f"--rct2-data-path={env['RCT2_DATA_DIR']}",
            f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
            f"--user-data-path={client}"], cwd=ROOT, env=env, stdout=logs[1],
            stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(player)
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            source = (run / "client.log").read_text(errors="replace")
            if "MARINE_CONTROL_PASS" in source:
                break
            if player.poll() is not None or session.poll() is not None:
                raise RuntimeError("native session stopped before redirect completed")
            time.sleep(0.5)
        else:
            raise TimeoutError("Marine did not reverse after second move order")
        server = (run / "session.log").read_text(errors="replace")
        actions = re.findall(r"WORLD_COMMAND_ACTION id=(\S+) request=[12] units=1 verb=move", server)
        sent = re.findall(r"WORLD_COMMAND_SENT id=(\S+) request=[12] queue=\d+", server)
        commands = re.findall(r"\[world-control\] command=(\S+) unit=\d+ verb=unit.move accepted=1"
                              r" frame=(\d+) order_before=(\S+) order_after=(\S+)", server)
        latency = int(re.search(r"MARINE_CONTROL_PASS x=\d+ redirect_ms=(\d+)", source).group(1))
        checks = {"both_actions_accepted": source.count("MARINE_CONTROL_ORDER request=") >= 2
                  and "MARINE_CONTROL_ORDER request=1 accepted=true" in source
                  and "MARINE_CONTROL_ORDER request=2 accepted=true" in source,
                  "park_delivery_in_order": len(actions) == 2 and actions == sent
                  and actions == [entry[0] for entry in commands[:2]],
                  "native_received_both": len(commands) >= 2,
                  "redirect_within_five_seconds": latency <= 5000,
                  "native_frames_ordered": len(commands) >= 2 and int(commands[1][1]) >= int(commands[0][1])
                  and commands[1][2] == "Move" and commands[1][3] == "Move"}
        (run / "verification.json").write_text(json.dumps({"checks": checks, "redirect_ms": latency,
            "park_actions": actions, "park_sent": sent, "native_orders": commands[:2]}, indent=2) + "\n")
        print(json.dumps({"run": str(run), "checks": checks, "redirect_ms": latency}))
        if not all(checks.values()):
            raise AssertionError(f"Marine controls checks failed: {checks}")
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
