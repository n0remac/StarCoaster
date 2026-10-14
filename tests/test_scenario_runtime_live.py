#!/usr/bin/env python3
"""Two-client native Frontier wave, reinforcement, and restart verification."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios/frontier-outpost/scenario.json"
PARK = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
OPENRCT2_DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
SESSION_PORTS = (40010, 40011, 40012, 11753)


def wait_for_ports(seconds: int = 180) -> None:
    """The fixed native ports can remain in TIME_WAIT after a previous run."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        free = True
        for port in SESSION_PORTS:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    free = False
                    break
        if free:
            return
        time.sleep(1)
    raise TimeoutError(f"native session ports unavailable: {SESSION_PORTS}")


def wait_for(path: Path, pattern: str, process: subprocess.Popen, seconds: int,
             abort_pattern: str = "") -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        contents = path.read_text(errors="replace") if path.exists() else ""
        match = re.search(pattern, contents)
        if match:
            return match.group(0)
        if abort_pattern and re.search(abort_pattern, contents):
            raise RuntimeError(f"terminal state before {pattern}; see {path}")
        if process.poll() is not None:
            raise RuntimeError(f"session stopped before {pattern}; see {path}")
        time.sleep(0.25)
    raise TimeoutError(f"missing {pattern}; see {path}")


def wait_for_new_status(path: Path, pattern: str, previous: int,
                        process: subprocess.Popen, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        contents = path.read_text(errors="replace") if path.exists() else ""
        if len(re.findall(pattern, contents)) > previous:
            return
        if process.poll() is not None:
            raise RuntimeError(f"client stopped before restored status; see {path}")
        time.sleep(0.25)
    raise TimeoutError(f"missing restored status; see {path}")


def bridge_pid(scenario_path: Path) -> int:
    rows = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True).splitlines()
    matches = []
    for row in rows:
        parts = row.strip().split(maxsplit=1)
        if len(parts) == 2 and "/build/world-bridge" in parts[1] and str(scenario_path) in parts[1]:
            matches.append(int(parts[0]))
    if len(matches) != 1:
        raise RuntimeError(f"expected one scenario bridge, found {matches}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphical", action="store_true",
                        help="run both clients under Xvfb and capture their terminal screens")
    args = parser.parse_args()
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", str(Path.home() / "games/rct2")))
    starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft")))
    if not rct2.is_dir() or not starcraft.is_dir() or not PARK.is_file():
        raise RuntimeError("licensed game data and generated Frontier park are required")
    run = ROOT / "run-data" / f"scenario-runtime-live-{int(time.time())}"
    run.mkdir(parents=True)
    native_map = run / "frontier.scm"
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", str(SCENARIO),
                    "--output", str(native_map)], cwd=ROOT, check=True)
    journal = run / "spawn-queue.json"
    mapping = ROOT / "scenarios/frontier-outpost/mapping.json"
    env = os.environ.copy() | {"RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
        "BRIDGE_SCENARIO_CONFIG": str(SCENARIO), "BRIDGE_RULES_CONFIG": str(mapping),
        "BRIDGE_MAP_FILE": str(native_map), "BRIDGE_SPAWN_JOURNAL": str(journal),
        "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(run / "server"),
        "OPENBW_LOCAL_PATH": str(run / "openbw-local.socket")}
    processes, streams = [], []

    def start(name: str, command: list[str], extra_env: dict | None = None) -> subprocess.Popen:
        stream = (run / f"{name}.log").open("w")
        streams.append(stream)
        process = subprocess.Popen(command, cwd=ROOT, env=env | (extra_env or {}), stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    def client(name: str, commander: bool) -> subprocess.Popen:
        directory = run / name
        (directory / "plugin").mkdir(parents=True, exist_ok=True)
        (directory / "plugin/rts-bridge.js").write_text(
                        (ROOT / "openrct2-plugin/rts-bridge.js").read_text())
        (directory / "plugin/scenario-defense-probe.js").write_text(
            f"var SCENARIO_PROBE_COMMANDER = {'true' if commander else 'false'};\n" +
            (ROOT / "scripts/scenario-defense-probe.js").read_text())
        display = ":95" if name == "client-a" else ":96"
        executable = "openrct2" if args.graphical else "openrct2-cli"
        options = [] if args.graphical else ["--headless"]
        return start(name, [str(ROOT / "build/openrct2" / executable), "join", "127.0.0.1",
                            *options, "--port=11753", f"--rct2-data-path={rct2}",
                            f"--openrct2-data-path={OPENRCT2_DATA}", f"--user-data-path={directory}"],
                     {"DISPLAY": display} if args.graphical else None)

    report = {"status": "failed", "run_directory": str(run), "tests": {},
              "client_mode": "graphical" if args.graphical else "headless", "capture_paths": []}
    try:
        wait_for_ports()
        if args.graphical:
            for suffix, display in (("a", ":95"), ("b", ":96")):
                start("display-" + suffix, ["Xvfb", display, "-screen", "0",
                                           "1280x800x24", "-nolisten", "tcp"])
            time.sleep(1)
        session = start("session", [str(ROOT / "scripts/run-world-session.sh"), str(PARK)])
        wait_for(run / "session.log", r"WORLD_READY.*navigation=native", session, 90)
        a = client("client-a", True)
        wait_for(run / "client-a.log", r"RTS Bridge apply tick=", a, 60)
        initial_snapshot = next(line for line in (run / "client-a.log").read_text(
            errors="replace").splitlines() if "RTS Bridge apply tick=" in line)
        starting_marine_ids = sorted(set(re.findall(r"openbw:100[0-5](?=,)", initial_snapshot)))
        starting_zergling_ids = sorted(set(re.findall(r"openbw:20(?:0[0-9]|1[01])(?=,)", initial_snapshot)))
        if len(starting_marine_ids) != 6 or len(starting_zergling_ids) != 12:
            raise AssertionError("first native client snapshot lacks the six/twelve starting actors")
        report["tests"]["starting_actors"] = "passed"
        report["starting_actor_ids"] = {"marines": starting_marine_ids,
                                        "zerglings": starting_zergling_ids}
        b = client("client-b", False)
        wait_for(run / "client-b.log", r"RTS Bridge apply tick=", b, 60)
        wait_for(run / "session.log", r"wave=opening-zerg-wave state=ready", session, 90)
        wait_for(run / "client-a.log", r"SCENARIO_MANUAL_SPAWN accepted=true", a, 60)
        wait_for(run / "client-a.log", r"SCENARIO_DEFEND_ORDER accepted=true", a, 60)
        wait_for(run / "session.log", r"wave=southern-wave state=ready", session, 90)
        if re.search(r"scenario frontier-outpost outcome=", (run / "session.log").read_text()):
            raise AssertionError("premature outcome before dependent wave")
        report["tests"]["opening_and_timed_waves"] = "passed"
        report["tests"]["no_premature_victory"] = "passed"
        report["tests"]["manual_marine_and_order"] = "passed"
        # Rejoin the second client before a Go-only bridge restart.
        os.killpg(b.pid, signal.SIGTERM)
        try:
            b.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(b.pid, signal.SIGKILL)
            b.wait(timeout=5)
        b = client("client-b-reconnect", False)
        wait_for(run / "client-b-reconnect.log", r"WORLD_SCENARIO_STATUS scenario=frontier-outpost", b, 60)
        terminal_status = (r"WORLD_SCENARIO_STATUS scenario=frontier-outpost "
                           r"wave=3/3 state=cleared outcome=victory")
        before_restart = (run / "session.log").read_text(errors="replace")
        final_before_restart = "wave=final-wave state=ready" in before_restart
        victory_before_restart = "scenario frontier-outpost outcome=victory" in before_restart
        status_counts = {
            name: len(re.findall(terminal_status, (run / f"{name}.log").read_text(errors="replace")))
            for name in ("client-a", "client-b-reconnect")}
        order_before_restart = json.loads(journal.read_text()).get("order", [])
        original = bridge_pid(SCENARIO)
        os.kill(original, signal.SIGTERM)
        for _ in range(40):
            if not Path(f"/proc/{original}").exists():
                break
            time.sleep(0.1)
        restart = start("bridge-restart", [str(ROOT / "build/world-bridge"), "--scenario", str(SCENARIO),
                                          "--rules", str(mapping), "--spawn-journal", str(journal)])
        wait_for(run / "bridge-restart.log", r"OpenBW ready targets=", restart, 90)
        report["tests"]["bridge_restart"] = "passed"
        if not final_before_restart:
            wait_for(run / "bridge-restart.log", r"wave=final-wave state=ready", restart, 150,
                     r"scenario frontier-outpost outcome=defeat")
        report["tests"]["dependent_wave"] = "passed"
        if not victory_before_restart:
            wait_for(run / "bridge-restart.log", r"scenario frontier-outpost outcome=(victory|defeat)",
                     restart, 150)
        report["tests"]["terminal_outcome"] = "passed"
        for name, process in (("client-a", a), ("client-b-reconnect", b)):
            path = run / f"{name}.log"
            if victory_before_restart:
                wait_for_new_status(path, terminal_status, status_counts[name], process, 45)
            else:
                wait_for(path, terminal_status, process, 30, r"outcome=defeat")
        scenario_journal = json.loads(Path(str(journal) + ".scenario.json").read_text())
        queue = json.loads(journal.read_text())
        waves = scenario_journal["waves"]
        assert [wave["id"] for wave in waves] == [
            "opening-zerg-wave", "southern-wave", "final-wave"]
        assert waves[1]["triggered_frame"] >= scenario_journal["start_frame"] + 300
        assert waves[2]["triggered_frame"] > waves[1]["triggered_frame"]
        assert all(wave["state"] == "cleared" for wave in waves)
        assert scenario_journal.get("outcome") == "victory"
        requests = [attempt["request_id"] for wave in waves for unit in wave["units"]
                    for attempt in unit["attempts"]]
        actors = [unit["actor_id"] for wave in waves for unit in wave["units"]
                  if unit.get("actor_id")]
        assert len(requests) == len(set(requests))
        assert len(actors) == len(set(actors))
        if victory_before_restart:
            assert queue.get("order", []) == order_before_restart, "restart issued duplicate requests"
        assert len(waves[0]["units"]) == 5 and len(waves[1]["units"]) == 2
        assert len(waves[2]["units"]) == 3
        session_events = ((run / "session.log").read_text(errors="replace") +
                          (run / "bridge-restart.log").read_text(errors="replace"))
        assert "navigation initialized" in session_events, "native navigation was not initialized"
        assert "actor reconcile living=" in (run / "bridge-restart.log").read_text(
            errors="replace"), "missing restart actor reconciliation"
        assert any(f"actor despawn id={actor}" in session_events for actor in actors), "no native actor deaths"
        assert all(unit["state"] == "dead" for wave in waves for unit in wave["units"]), "unresolved wave actor"
        assert "SCENARIO_DEFEND_ORDER accepted=true" in (run / "client-a.log").read_text(
            errors="replace")
        report["tests"].update({"frame_order_and_victory": "passed",
                                "unique_native_ids": "passed", "two_client_status": "passed",
                                "native_navigation_and_combat": "passed"})
        if args.graphical:
            for name, display in (("client-a", ":95"), ("client-b", ":96")):
                capture = run / f"{name}-victory.png"
                subprocess.run(["scrot", "-z", "-o", str(capture)],
                               cwd=ROOT, env=env | {"DISPLAY": display}, check=True)
                report["capture_paths"].append(str(capture))
            report["tests"]["two_graphical_client_victory"] = "passed"
        report.update({"status": "passed", "commit_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "scenario_hash": scenario_journal["definition_hash"],
            "session_id": scenario_journal["session"], "start_frame": scenario_journal["start_frame"],
            "last_frame": scenario_journal["last_frame"], "waves": waves,
            "outcome": scenario_journal.get("outcome"), "request_ids": queue.get("order", []),
            "actor_ids": actors,
            "log_paths": [str(run / "session.log"), str(run / "bridge-restart.log"),
                          str(run / "client-a.log"), str(run / "client-b-reconnect.log")]})
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for stream in streams:
            stream.close()
        (run / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
