#!/usr/bin/env python3
"""Verify park construction, clearance, 20 OpenBW actors and three native demolitions."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from park_navigation import ParkGrid, Point
from park_assault_artifacts import draw_diagnostics


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"
OUT = DATA / "headless"
TARGETS = {"carousel-1", "shop-1", "ride-2"}


def command(*args: str) -> None:
    subprocess.run([sys.executable, *args] if args[0].endswith(".py") else list(args),
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def analyze(bw_log: str, server_log: str, output: Path = OUT) -> dict:
    initialized = "[park-assault] initialized zerglings=20 squads=8,6,6 targets=3" in bw_log
    targets = re.findall(r"\[park-assault\] target-created id=([a-z0-9-]+) proxy=(\d+) hp=(\d+)", bw_log)
    destroyed = re.findall(r"\[park-assault\] target-destroyed id=([a-z0-9-]+) proxy=(\d+) frame=(\d+)", bw_log)
    orders = re.findall(r"\[park-assault\] attack-order id=(\d+) target=([a-z0-9-]+) accepted=(\d+)", bw_log)
    moves = re.findall(r"\[park-assault\] move-order id=(\d+) .* accepted=(\d+)", bw_log)
    attacks = re.findall(r"\[park-assault\] attack-frame id=(\d+) target=([a-z0-9-]+)", bw_log)
    damage = re.findall(r"\[park-assault\] target-damage id=([a-z0-9-]+) from=(\d+) to=(\d+)", bw_log)
    native = re.findall(r"PARK_ASSAULT_DEMOLITION_SUCCEEDED id=([a-z0-9-]+) ride=(\d+) revision=(\d+)", server_log)
    revisions = re.findall(r"\[park-assault\] navigation-revision=(\d+) cleared=([a-z0-9-]+)", bw_log)
    payloads = [int(value) for value in re.findall(r"snapshot-bytes=(\d+)", bw_log)]
    planning = [int(value) for value in re.findall(r"\[park-assault\] route .* microseconds=(\d+)", bw_log)]

    grid = ParkGrid.load(DATA / "navigation-elements.json", DATA / "fixture.json", radius=8)
    offset = grid.fixture["transform"]
    observed = {}
    last_position = {}
    trajectory_failures = []
    for line in bw_log.splitlines():
        update = re.search(r"\[park-assault\] navigation-revision=(\d+) cleared=([a-z0-9-]+)", line)
        if update:
            try:
                grid.clear_target(update[2], grid.revision)
                if grid.revision != int(update[1]):
                    trajectory_failures.append(f"revision gap at {update[2]}")
            except ValueError as error:
                trajectory_failures.append(str(error))
            continue
        position = re.search(r"\[park-assault\] position id=(\d+) x=(\d+) y=(\d+) frame=(\d+) revision=(\d+)", line)
        if not position:
            continue
        unit_id, bw_x, bw_y, frame, revision = map(int, position.groups())
        park = Point(bw_x + offset["x"], bw_y + offset["y"])
        observed.setdefault(unit_id, []).append({"frame": frame, "bw_x": bw_x, "bw_y": bw_y,
                                                  "park_x": park.x, "park_y": park.y,
                                                  "revision": revision})
        current = grid.cell(park)
        if revision != grid.revision or not grid.passable(current):
            trajectory_failures.append(f"unit {unit_id} blocked at frame {frame} ({park.x},{park.y}) rev {revision}")
        previous = last_position.get(unit_id)
        if previous and previous[1] == revision and not grid.line_clear(previous[0], current):
            trajectory_failures.append(f"unit {unit_id} crossed obstacle by frame {frame}")
        last_position[unit_id] = current, revision

    (output / "observed-paths.json").write_text(json.dumps(observed, indent=2) + "\n")
    (output / "target-events.json").write_text(json.dumps({"created": targets, "damage": damage,
                                                        "destroyed": destroyed, "native": native}, indent=2) + "\n")
    (output / "navigation-events.json").write_text(json.dumps(revisions, indent=2) + "\n")
    (output / "violations.json").write_text(json.dumps(trajectory_failures, indent=2) + "\n")
    errors = []
    if not initialized or len(observed) != 20:
        errors.append("OpenBW did not initialize and report all 20 Zerglings")
    if {id for id, _, hp in targets if int(hp) == 1000} != TARGETS:
        errors.append("three independent 1000 HP Barracks proxies were not present")
    if [id for id, _, _ in destroyed] != ["carousel-1", "shop-1", "ride-2"] and {id for id, _, _ in destroyed} != TARGETS:
        errors.append("three targets did not die in OpenBW")
    if {int(id) for id, _, accepted in orders if accepted == "1"} != set(observed):
        errors.append("not all 20 Zerglings accepted a normal attack order")
    if {int(id) for id, accepted in moves if accepted == "1"} != set(observed):
        errors.append("not all 20 Zerglings accepted a movement order")
    if {int(id) for id, _ in attacks} != set(observed):
        errors.append("not all 20 Zerglings produced real attack frames")
    if {id for id, before, after in damage if int(after) < int(before)} != TARGETS:
        errors.append("normal weapon damage was not observed for all targets")
    if {id for id, _, _ in native} != TARGETS or len(native) != 3:
        errors.append("three native OpenRCT2 demolitions were not confirmed exactly once")
    if [int(revision) for revision, _ in revisions] != [2, 3, 4]:
        errors.append("confirmed demolition revisions did not reach OpenBW in order")
    if trajectory_failures or "COLLISION_VIOLATION" in bw_log:
        errors.append("observed unit trajectories intersected exported obstacles")
    if not payloads or max(payloads) > 32768:
        errors.append("snapshot payload exceeds the transport limit or was not measured")
    if "PARK_ASSAULT_DEMOLITION_FAILED" in server_log or "dropped invalid snapshot" in server_log:
        errors.append("OpenRCT2 rejected a snapshot or native demolition")
    if "dropped oversized snapshot" in bw_log or "RTS Bridge dropped oversized" in server_log:
        errors.append("bridge dropped an oversized packet")
    report = {"status": "failed" if errors else "passed", "scenario": "park-assault",
              "live_openrct2": False, "zergling_ids": sorted(observed), "target_ids": sorted(TARGETS),
              "attack_orders": len(orders), "attack_frames": len(attacks),
              "target_damage_events": len(damage), "native_demolitions": native,
              "navigation_revisions": revisions, "observed_samples": sum(map(len, observed.values())),
              "trajectory_violations": trajectory_failures,
              "max_snapshot_bytes": max(payloads) if payloads else None,
              "max_planning_microseconds": max(planning) if planning else None,
              "errors": errors}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-fixtures", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.reuse_fixtures:
        command("scripts/create-park-assault.py")
        command("scripts/create-park-assault.py", "--probe-demolition")
        command("scripts/create-park-assault-map.py")
        command("scripts/export-park-assault-navigation.py")
    command("scripts/build-bridge-module.sh")
    env = os.environ.copy() | {"RCT2_DATA_DIR": os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"),
                               "STARCRAFT_DATA_DIR": os.environ.get("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft"),
                               "BRIDGE_SCENARIO": "park_assault", "BRIDGE_FRAME_MS": "12",
                               "BRIDGE_SERVER_DATA_DIR": str(OUT / "server-data"),
                               "OPENRCT2_PORT": "11762", "BRIDGE_BWAPI_RUNTIME_DIR": str(OUT / "openbw")}
    running = []
    try:
        with (OUT / "server.log").open("w") as server_stream, (OUT / "bwapi.log").open("w") as bw_stream:
            server = subprocess.Popen([str(ROOT / "scripts/run-openrct2-host.sh"), str(DATA / "save/frontier-outpost.park")],
                                      cwd=ROOT, env=env, stdout=server_stream, stderr=subprocess.STDOUT)
            running.append(server)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if "PARK_ASSAULT_READY" in (OUT / "server.log").read_text(errors="replace"):
                    break
                if server.poll() is not None:
                    raise RuntimeError("OpenRCT2 host exited before fixture validation")
                time.sleep(0.2)
            else:
                raise TimeoutError("OpenRCT2 did not validate the park fixture")
            bw = subprocess.Popen([str(ROOT / "scripts/run-bwapi.sh")], cwd=ROOT, env=env,
                                  stdout=bw_stream, stderr=subprocess.STDOUT)
            running.append(bw)
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                server_log = (OUT / "server.log").read_text(errors="replace")
                bw_log = (OUT / "bwapi.log").read_text(errors="replace")
                if server_log.count("PARK_ASSAULT_DEMOLITION_SUCCEEDED") >= 3 \
                        and bw_log.count("[park-assault] navigation-revision=") >= 3:
                    time.sleep(0.2)
                    break
                if server.poll() is not None or bw.poll() is not None:
                    raise RuntimeError("headless OpenRCT2 or OpenBW process exited early")
                time.sleep(0.2)
            else:
                raise TimeoutError("three confirmed native demolitions did not finish")
    except BaseException as error:
        (OUT / "verification.json").write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise
    finally:
        for process in reversed(running):
            process.terminate()
        for process in reversed(running):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    report = analyze((OUT / "bwapi.log").read_text(errors="replace"),
                     (OUT / "server.log").read_text(errors="replace"))
    draw_diagnostics(OUT)
    (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise RuntimeError("Park assault headless verification failed; see verification.json")


if __name__ == "__main__":
    main()
