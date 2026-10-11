#!/usr/bin/env python3
"""Prove the carousel proxy dies from eight normal OpenBW Zergling attacks."""

import json
import os
from pathlib import Path
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "run-data/ride-siege-headless"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["python3", str(ROOT / "scripts/create-ride-siege-map.py")], check=True)
    env = os.environ.copy() | {
        "BRIDGE_SCENARIO": "ride_siege", "BRIDGE_FRAME_MS": "15",
        "BRIDGE_SIEGE_START_FRAME": "48",
        "BRIDGE_BWAPI_RUNTIME_DIR": str(OUTPUT / "openbw"),
    }
    env.setdefault("STARCRAFT_DATA_DIR", "/home/pi/games/starcraft")
    log_path = OUTPUT / "bwapi.log"
    with log_path.open("w") as log:
        process = subprocess.Popen([str(ROOT / "scripts/run-bwapi.sh")], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                data = log_path.read_text(errors="replace")
                if "[siege] target-destroyed id=" in data:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"OpenBW exited early; see {log_path}")
                time.sleep(0.1)
            else:
                raise RuntimeError(f"proxy did not die; see {log_path}")
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
    data = log_path.read_text(errors="replace")
    created = re.search(r"target-created id=(\d+) owner=(\d+) kind=Terran_Missile_Turret hp=(\d+)", data)
    death = re.findall(r"target-destroyed id=(\d+) frame=(\d+)", data)
    orders = re.findall(r"attack-order id=(\d+) target=(\d+) accepted=1", data)
    damage = re.findall(r"target-damage id=(\d+) from=(\d+) to=(\d+) frame=(\d+)", data)
    attacks = re.findall(r"attack-frame id=(\d+) target=(\d+) frame=(\d+)", data)
    if not created or int(created[3]) != 200 or len(death) != 1 or death[0][0] != created[1]:
        raise RuntimeError("structure identity, HP, or terminal event invalid")
    if len({x[0] for x in orders}) != 8 or any(x[1] != created[1] for x in orders):
        raise RuntimeError("not all eight Zerglings accepted attack orders")
    if not damage or not attacks or any(int(to) >= int(before) for _, before, to, _ in damage):
        raise RuntimeError("normal weapon damage was not observed")
    report = {"target_id": int(created[1]), "owner": int(created[2]), "initial_hp": 200,
              "zergling_ids": sorted({int(x[0]) for x in orders}), "damage_events": len(damage),
              "attack_frames": len(attacks), "destroyed_bw_frame": int(death[0][1])}
    (OUTPUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
