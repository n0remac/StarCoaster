#!/usr/bin/env python3
"""Exercise live victory, client reconnect, and a fresh Frontier session."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "build/openrct2-stage/usr/local/share/openrct2"
OUT = ROOT / "run-data/frontier-lifecycle"
PARK = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
SCENARIO = ROOT / "scenarios/frontier-outpost.json"


def wait_for(path: Path, pattern: str, process: subprocess.Popen, seconds: int) -> str:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        contents = path.read_text(errors="replace") if path.exists() else ""
        match = re.search(pattern, contents)
        if match:
            return match.group(0)
        if process.poll() is not None:
            raise RuntimeError(f"process exited before {pattern}; see {path}")
        time.sleep(0.25)
    raise TimeoutError(f"missing {pattern}; see {path}")


def cycle(number: int, scenario: Path, map_file: Path, rct2: Path, starcraft: Path) -> dict:
    output = OUT / f"cycle-{number}"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy() | {
        "RCT2_DATA_DIR": str(rct2), "STARCRAFT_DATA_DIR": str(starcraft),
        "BRIDGE_SCENARIO_CONFIG": str(scenario),
        "BRIDGE_RULES_CONFIG": str(ROOT / "scenarios/frontier-outpost-mapping.json"),
        "BRIDGE_MAP_FILE": str(map_file), "BRIDGE_DISABLE_ASSAULT_AI": "1",
        "BRIDGE_LAUNCH_CLIENT": "0", "BRIDGE_SERVER_DATA_DIR": str(output / "server-data"),
        "OPENBW_LOCAL_PATH": str(output / "openbw-local.socket"),
        "BRIDGE_BWAPI_RUNTIME_DIR": str(output / "bwapi"),
    }
    processes = []
    streams = []

    def start(name: str, command: list[str], extra: dict | None = None) -> subprocess.Popen:
        stream = (output / f"{name}.log").open("w")
        streams.append(stream)
        process = subprocess.Popen(command, cwd=ROOT, env=env | (extra or {}),
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        return process

    def client(name: str, commander: bool) -> subprocess.Popen:
        directory = output / name
        (directory / "plugin").mkdir(parents=True, exist_ok=True)
        (directory / "plugin/rts-bridge.js").write_text(
            "var STARCOASTER_WORLD_BRIDGE = true;\n" +
            (ROOT / "openrct2-plugin/rts-bridge.js").read_text())
        (directory / "plugin/frontier-lifecycle-probe.js").write_text(
            f"var LIFECYCLE_COMMANDER = {'true' if commander else 'false'};\n" +
            (ROOT / "scripts/frontier-lifecycle-probe.js").read_text())
        return start(name, [str(ROOT / "build/openrct2/openrct2-cli"), "join", "127.0.0.1",
                            "--headless", "--port=11753", f"--rct2-data-path={rct2}",
                            f"--openrct2-data-path={DATA}", f"--user-data-path={directory}"])

    try:
        session = start("session", [str(ROOT / "scripts/run-world-session.sh"), str(PARK)])
        wait_for(output / "session.log", r"WORLD_READY.*navigation=native", session, 90)
        a = client("client-a", True)
        b = client("client-b", False)
        initial = r"LIFECYCLE_ACTORS [0-9a-f]{32} marines=6 zerglings=1 unique=7"
        first = wait_for(output / "client-a.log", initial, a, 60)
        wait_for(output / "client-b.log", initial, b, 60)
        wait_for(output / "client-a.log", r"LIFECYCLE_ATTACK accepted=true", a, 30)
        wait_for(output / "session.log", r"outcome=victory marines=6 zerglings=0", session, 100)
        os.killpg(b.pid, signal.SIGTERM)
        b.wait(timeout=10)
        # Reuse the client data directory to exercise the normal reconnect path.
        reconnect_dir = output / "client-b"
        b = start("client-b-reconnect", [str(ROOT / "build/openrct2/openrct2-cli"), "join",
                                          "127.0.0.1", "--headless", "--port=11753",
                                          f"--rct2-data-path={rct2}", f"--openrct2-data-path={DATA}",
                                          f"--user-data-path={reconnect_dir}"])
        after = wait_for(output / "client-b-reconnect.log",
                         r"LIFECYCLE_ACTORS [0-9a-f]{32} marines=6 zerglings=0 unique=6", b, 60)
        if first.split()[1] != after.split()[1]:
            raise RuntimeError("client reconnect changed the authoritative session")
        return {"session": first.split()[1], "victory": True, "reconnected_actor_count": 6,
                "log_directory": str(output)}
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


def main() -> None:
    rct2 = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    starcraft = Path(os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"))
    if not rct2.is_dir() or not starcraft.is_dir() or not PARK.is_file():
        raise RuntimeError("Install game data and generate the playable park first")
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads(SCENARIO.read_text())
    config["starting_units"]["zerglings"] = [[24, 32]]
    scenario = OUT / "victory-scenario.json"
    scenario.write_text(json.dumps(config, indent=2) + "\n")
    map_file = OUT / "victory.scm"
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", str(scenario),
                    "--output", str(map_file)], cwd=ROOT, check=True)
    results = [cycle(number, scenario, map_file, rct2, starcraft) for number in (1, 2)]
    if results[0]["session"] == results[1]["session"]:
        raise RuntimeError("scenario restart reused the previous session")
    report = {"status": "passed", "cycles": results}
    (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
