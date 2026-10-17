#!/usr/bin/env python3
"""Check native actor and two-camera evidence in a mixed Frontier recording."""

import json
import math
from pathlib import Path
import re
import sys


SNAPSHOT = re.compile(r"RTS Bridge apply tick=\d+ seq=(\d+) [^\n]*? units=([^\x1b\r\n]+)")
KINDS = ("zerg_zergling", "zerg_hydralisk", "zerg_ultralisk")


def snapshots(path: Path):
    result = {}
    for sequence, payload in SNAPSHOT.findall(path.read_text(errors="replace")):
        actors = {}
        for item in payload.split(";"):
            fields = item.split(",")
            if len(fields) < 10 or not fields[0].startswith("openbw:"):
                continue
            try:
                actors[fields[0]] = {"x": int(fields[1]), "y": int(fields[2]),
                    "motion": fields[4], "kind": fields[6], "hp": int(fields[7]),
                    "maximum": int(fields[8]), "owner": int(fields[9])}
            except ValueError:
                continue
        result[int(sequence)] = actors
    return result


def verify(directory: Path):
    report_path = directory / "verification.json"
    report = json.loads(report_path.read_text())
    heavy_defense = json.loads((directory / "run.json").read_text()).get(
        "capture_config", {}).get("mixed_zerg_heavy_defense", False)
    clients = [snapshots(directory / f"client-{name}.log") for name in "ab"]
    server = (directory / "server.log").read_text(errors="replace")
    kinds_together = []
    attack = {kind: set() for kind in KINDS}
    death = {kind: set() for kind in KINDS}
    damaged = {kind: set() for kind in KINDS + ("terran_marine",)}
    directions = {kind: set() for kind in KINDS}
    native_damage = {"hydralisk_ranged": None, "ultralisk_melee": None}
    previous = {}
    for sequence in sorted(set(clients[0]) & set(clients[1])):
        first, second = clients[0][sequence], clients[1][sequence]
        if first != second:
            continue
        living = {row["kind"] for row in first.values() if row["hp"] > 0 and row["owner"] == 0}
        if all(kind in living for kind in KINDS):
            kinds_together.append(sequence)
        for actor_id, row in first.items():
            kind = row["kind"]
            if kind in KINDS:
                if row["motion"] == "attack":
                    attack[kind].add(actor_id)
                if row["motion"] == "death":
                    death[kind].add(actor_id)
                if row["hp"] < row["maximum"]:
                    damaged[kind].add(actor_id)
            elif kind == "terran_marine" and row["hp"] < row["maximum"]:
                damaged[kind].add(actor_id)
        living = [row for row in first.values() if row["hp"] > 0 and row["owner"] == 0]
        for actor_id, marine in first.items():
            if marine["kind"] != "terran_marine" or actor_id not in previous \
                    or not 0 < marine["hp"] < previous[actor_id]:
                continue
            distance = lambda enemy: math.hypot(enemy["x"] - marine["x"],
                                                enemy["y"] - marine["y"])
            zerglings = [enemy for enemy in living if enemy["kind"] == "zerg_zergling"]
            hydralisks = [enemy for enemy in living if enemy["kind"] == "zerg_hydralisk"]
            ultralisks = [enemy for enemy in living if enemy["kind"] == "zerg_ultralisk"]
            loss = previous[actor_id] - marine["hp"]
            if native_damage["hydralisk_ranged"] is None and loss == 10 \
                    and any(enemy["motion"] == "attack" and 70 < distance(enemy) <= 180
                            for enemy in hydralisks) \
                    and all(distance(enemy) > 70 for enemy in zerglings) \
                    and all(distance(enemy) > 180 for enemy in ultralisks):
                native_damage["hydralisk_ranged"] = {
                    "sequence": sequence, "marine": actor_id, "hp_before": previous[actor_id],
                    "hp_after": marine["hp"]}
            if native_damage["ultralisk_melee"] is None and loss == 20 \
                    and any(enemy["motion"] == "attack" and distance(enemy) <= 64
                            for enemy in ultralisks) \
                    and not zerglings \
                    and all(enemy["motion"] != "attack" or distance(enemy) > 100
                            for enemy in hydralisks):
                native_damage["ultralisk_melee"] = {
                    "sequence": sequence, "marine": actor_id, "hp_before": previous[actor_id],
                    "hp_after": marine["hp"]}
        previous = {actor_id: row["hp"] for actor_id, row in first.items()}
    for actor_id in {actor_id for frame in clients[0].values() for actor_id in frame}:
        positions = [(frame[actor_id]["x"], frame[actor_id]["y"], frame[actor_id]["kind"])
                     for frame in clients[0].values() if actor_id in frame]
        for (ax, ay, kind), (bx, by, _) in zip(positions, positions[1:]):
            if kind not in KINDS:
                continue
            if bx > ax + 2:
                directions[kind].add("east")
            if bx < ax - 2:
                directions[kind].add("west")
            if by > ay + 2:
                directions[kind].add("south")
            if by < ay - 2:
                directions[kind].add("north")
    camera = [(directory / f"client-{name}.log").read_text(errors="replace")
              for name in "ab"]
    checks = {
        "native_navigation_ready": report.get("native_navigation_ready", False),
        "two_client_snapshots_match": report.get("matching_snapshot_sequences", 0) >= 10
            and not report.get("mismatched_sequences"),
        "three_enemy_kinds_together": bool(kinds_together),
        "hydralisk_attack_animation": bool(attack["zerg_hydralisk"]),
        "ultralisk_attack_animation": bool(attack["zerg_ultralisk"]),
        "enemy_hp_loss": any(damaged[kind] for kind in KINDS),
        "marine_hp_loss": bool(damaged["terran_marine"]),
        "native_death_animation": any(death[kind] for kind in KINDS),
        "multiple_movement_directions": any(len(value) >= 2 for value in directions.values()),
        "two_camera_angles": "MIXED_ZERG_CAMERA_READY angle=0" in camera[0]
            and "MIXED_ZERG_CAMERA_READY angle=1" in camera[1],
        "original_art_video": (directory / "combined.mp4").is_file()
            and (directory / "combined.mp4").stat().st_size > 0,
        "native_ultralisk_spawn": bool(re.search(r"type=zerg_ultralisk x=\d+ y=\d+", server)),
        "native_hydralisk_ranged_damage": native_damage["hydralisk_ranged"] is not None,
        "native_ultralisk_melee_damage": native_damage["ultralisk_melee"] is not None,
    }
    if heavy_defense:
        # The crowded death capture does not isolate individual hits; the
        # lighter fixture checks both weapons with attacker spacing.
        checks.pop("native_hydralisk_ranged_damage")
        checks.pop("native_ultralisk_melee_damage")
        checks["hydralisk_death_animation"] = bool(death["zerg_hydralisk"])
        checks["ultralisk_death_animation"] = bool(death["zerg_ultralisk"])
    report["mixed_zerg_capture"] = {"checks": checks,
        "heavy_defense_fixture": heavy_defense,
        "simultaneous_sequences": kinds_together[:12],
        "attack_actors": {kind: sorted(ids) for kind, ids in attack.items()},
        "death_actors": {kind: sorted(ids) for kind, ids in death.items()},
        "damaged_actors": {kind: sorted(ids) for kind, ids in damaged.items()},
        "native_damage_samples": native_damage,
        "movement_directions": {kind: sorted(value) for kind, value in directions.items()}}
    report["capture_complete"] = all(checks.values())
    report["status"] = "passed" if report["capture_complete"] else "incomplete"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report["mixed_zerg_capture"]


if __name__ == "__main__":
    result = verify(Path(sys.argv[1]))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if all(result["checks"].values()) else 1)
