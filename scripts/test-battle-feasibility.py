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
ATTACK_FRAME = re.compile(
    r"\[battle\] attack-frame frame=(\d+) id=(\d+) owner=(\d+) kind=(\w+).*orderTarget=(-?\d+) order=(\w+)"
)
SPAWNED = re.compile(r"\[battle\] spawned marines=(\d+) zerglings=(\d+)")
OUTCOME = re.compile(r"\[battle\] outcome frame=(\d+) zerg_alive=(\d+) terran_alive=(\d+) result=(\w+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--probe-enemy-orders", action="store_true")
    parser.add_argument("--log-name", default="")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not os.environ.get("STARCRAFT_DATA_DIR"):
        parser.error("set STARCRAFT_DATA_DIR to the directory containing your own MPQs")
    if args.log_name and not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", args.log_name):
        parser.error("--log-name must be 1–40 letters, digits, underscores, or hyphens")

    output_dir = ROOT / "run-data" / "battle-feasibility"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / ((args.log_name or ("enemy-order-probe" if args.probe_enemy_orders else "bwapi")) + ".log")
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
    attack_frames = [ATTACK_FRAME.search(line) for line in lines]
    attack_frames = [match for match in attack_frames if match]
    spawned = [SPAWNED.search(line) for line in lines]
    spawned = [match for match in spawned if match]
    outcomes = [OUTCOME.search(line) for line in lines]
    outcomes = [match for match in outcomes if match]
    registered_ids = [match.group(1) for match in registered]
    created_kinds = [match.group(2) for match in created]
    owners_by_kind = {kind: {match.group(1) for match in created if match.group(2) == kind}
                      for kind in ("zerg_zergling", "terran_marine")}
    damaged_kinds = {match.group(3) for match in damage if int(match.group(5)) < int(match.group(4))}
    damaged_ids = {match.group(1) for match in damage if int(match.group(5)) < int(match.group(4))}
    registered_marine_ids = {match.group(1) for match in registered if match.group(3) == "terran_marine"}
    registered_zerg_ids = {match.group(1) for match in registered if match.group(3) == "zerg_zergling"}
    marine_attack_frames = [match for match in attack_frames
                            if match.group(4) == "terran_marine" and match.group(2) in registered_marine_ids
                            and match.group(5) in registered_zerg_ids and match.group(6) == "AttackUnit"]
    orders = [line for line in lines if "[battle] attack-move" in line and "accepted=1" in line]
    hostile = [line for line in lines if "[battle] hostility" in line]
    bidirectional = all(any(f"phase={phase}" in line and "zerg_to_terran=1" in line
                            and "terran_to_zerg=1" in line for line in hostile)
                        for phase in ("initial", "before-contact", "after-contact"))
    guard = any("kind=terran_marine" in line and "order=PlayerGuard" in line
                for line in lines if "[battle] state" in line)
    combat_deaths = [match for match in destroyed if match.group(1) in damaged_ids]
    no_scripted_death = not any("[bridge] scenario death" in line or "[battle] scripted" in line
                                for line in lines)
    enemy_probes = [line for line in lines if "enemy-marine-attack-probe" in line]
    ownership_preserved = not args.probe_enemy_orders or (
        len(enemy_probes) == 4 and all("accepted=0 error=Unit_Not_Owned" in line for line in enemy_probes))
    passed = (created_kinds.count("zerg_zergling") == 8
              and created_kinds.count("terran_marine") == 4
              and len(spawned) == 1 and spawned[0].groups() == ("4", "8")
              and len(owners_by_kind["zerg_zergling"]) == 1
              and len(owners_by_kind["terran_marine"]) == 1
              and owners_by_kind["zerg_zergling"] != owners_by_kind["terran_marine"]
              and len(registered_ids) == 12 and len(set(registered_ids)) == 12
              and len(orders) == 8 and bidirectional and guard and marine_attack_frames
              and damaged_kinds == {"zerg_zergling", "terran_marine"}
              and bool(combat_deaths) and no_scripted_death and ownership_preserved
              and len(outcomes) == 1 and outcomes[0].group(4) in ("zerg", "terran"))
    def result(value: bool) -> str:
        return "PASS" if value else "FAIL"

    print(f"Marines created: {created_kinds.count('terran_marine')}")
    print(f"Zerglings created: {created_kinds.count('zerg_zergling')}")
    print(f"Unique stable IDs: {result(len(registered_ids) == 12 and len(set(registered_ids)) == 12)}")
    print(f"Mutual hostility: {result(bidirectional)}")
    print(f"Zerg attack orders: {result(len(orders) == 8)}")
    print(f"Marine guard and attacks: {result(bool(guard and marine_attack_frames))}")
    print(f"Marine damage received: {result('terran_marine' in damaged_kinds)}")
    print(f"Zergling damage received: {result('zerg_zergling' in damaged_kinds)}")
    print(f"Combat deaths: {result(bool(combat_deaths and no_scripted_death))}")
    print(f"Battle conclusion: {result(len(outcomes) == 1 and outcomes[0].group(4) in ('zerg', 'terran'))}")
    if args.probe_enemy_orders:
        print(f"Enemy command restriction: {result(ownership_preserved)}")
    if args.probe_enemy_orders:
        for line in lines:
            if "enemy-marine-attack-probe" in line:
                print(line)
    print(f"Log: {log_path}")
    print("BATTLE FEASIBILITY: PASS" if passed else "BATTLE FEASIBILITY: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
