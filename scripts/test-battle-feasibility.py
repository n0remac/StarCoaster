#!/usr/bin/env python3
"""Gate battle work on genuine damage and deaths for both factions in OpenBW."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
CREATED = re.compile(r"\[battle\] created candidate_id=-?\d+ owner=(\d+) kind=(\w+)")
REGISTERED = re.compile(r"\[battle\] registered id=(\d+) owner=(\d+) kind=(\w+)")
DAMAGE = re.compile(r"\[battle\] damage id=(\d+) owner=(\d+) kind=(\w+) from=(\d+) to=(\d+)")
DESTROYED = re.compile(r"\[battle\] destroyed id=(\d+) owner=(\d+) kind=(\w+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--probe-enemy-orders", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not os.environ.get("STARCRAFT_DATA_DIR"):
        parser.error("set STARCRAFT_DATA_DIR to the directory containing your own MPQs")

    output_dir = ROOT / "run-data" / "battle-feasibility"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / ("enemy-order-probe.log" if args.probe_enemy_orders else "bwapi.log")
    env = os.environ.copy()
    env["BRIDGE_SCENARIO"] = "battle"
    if args.probe_enemy_orders:
        env["BRIDGE_PROBE_ENEMY_ORDERS"] = "1"
    else:
        env.pop("BRIDGE_PROBE_ENEMY_ORDERS", None)
    with log_path.open("w") as log:
        process = subprocess.Popen([str(ROOT / "scripts" / "run-bwapi.sh")],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=args.seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    lines = log_path.read_text().splitlines()
    created = [CREATED.search(line) for line in lines]
    created = [match for match in created if match]
    registered = [REGISTERED.search(line) for line in lines]
    registered = [match for match in registered if match]
    damage = [DAMAGE.search(line) for line in lines]
    damage = [match for match in damage if match]
    destroyed = [DESTROYED.search(line) for line in lines]
    destroyed = [match for match in destroyed if match]
    registered_ids = [match.group(1) for match in registered]
    created_kinds = [match.group(2) for match in created]
    owners_by_kind = {kind: {match.group(1) for match in created if match.group(2) == kind}
                      for kind in ("zerg_zergling", "terran_marine")}
    damaged_kinds = {match.group(3) for match in damage if int(match.group(5)) < int(match.group(4))}
    destroyed_kinds = {match.group(3) for match in destroyed}
    orders = [line for line in lines if "[battle] attack-move" in line and "accepted=1" in line]
    hostile = [line for line in lines if "[battle] hostility" in line]
    bidirectional = any("zerg_to_terran=1" in line and "terran_to_zerg=1" in line for line in hostile)
    passed = (created_kinds.count("zerg_zergling") == 8
              and created_kinds.count("terran_marine") == 4
              and len(owners_by_kind["zerg_zergling"]) == 1
              and len(owners_by_kind["terran_marine"]) == 1
              and owners_by_kind["zerg_zergling"] != owners_by_kind["terran_marine"]
              and len(registered_ids) == 12 and len(set(registered_ids)) == 12
              and len(orders) == 8 and bidirectional
              and damaged_kinds == {"zerg_zergling", "terran_marine"}
              and bool(destroyed_kinds))
    print(f"Created: {created_kinds.count('zerg_zergling')} Zerglings, "
          f"{created_kinds.count('terran_marine')} Marines; unique registered IDs: {len(set(registered_ids))}")
    print(f"Accepted Zergling attack orders: {len(orders)}; bidirectional hostility: {bidirectional}")
    print(f"Damage to: {', '.join(sorted(damaged_kinds)) or 'none'}; "
          f"combat deaths: {len(destroyed)}")
    if args.probe_enemy_orders:
        for line in lines:
            if "enemy-marine-attack-probe" in line:
                print(line)
    print(f"Log: {log_path}")
    print("PASS: genuine two-sided OpenBW combat" if passed else "FAIL: battle feasibility gate")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
