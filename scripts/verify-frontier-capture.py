#!/usr/bin/env python3
"""Summarize evidence from a real two-client Frontier Outpost recording."""

import json
from pathlib import Path
import re
import sys


SNAPSHOT = re.compile(r"RTS Bridge apply tick=\d+ seq=(\d+) session=([0-9a-f]{32}) center_z=\d+ units=([^\x1b\r\n]+)")
ACTOR = re.compile(r"openbw:(\d+),(\d+),(\d+),\d+,([^,]+),\d+,([^,]+),(\d+),(\d+),")
PARK_STATE = re.compile(r"FRONTIER_PARK_STATE carousel=(true|false) gate=(true|false)")


def snapshots(text):
    return {int(seq): (session, units) for seq, session, units in SNAPSHOT.findall(text)}


def main(directory):
    out = Path(directory)
    server = (out / "server.log").read_text(errors="replace")
    client = [(out / f"client-{letter}.log").read_text(errors="replace")
              if (out / f"client-{letter}.log").exists() else "" for letter in "ab"]
    a, b = [snapshots(text) for text in client]
    park_states = [PARK_STATE.findall(text) for text in client]
    park_sync = bool(park_states[0] and park_states[1]) and park_states[0][0] == park_states[1][0] \
        and park_states[0][-1] == park_states[1][-1]
    common = sorted(set(a) & set(b))
    matching = [seq for seq in common if a[seq] == b[seq]]
    mismatches = [seq for seq in common if a[seq] != b[seq]]
    first = min(a) if a else None
    initial = ACTOR.findall(a[first][1]) if first is not None else []
    traces = {}
    death_ids = set()
    marine_attack = 0
    zerg_damage = False
    for seq in sorted(a):
        for uid, x, y, motion, kind, hp, maximum in ACTOR.findall(a[seq][1]):
            uid, x, y, hp, maximum = int(uid), int(x), int(y), int(hp), int(maximum)
            traces.setdefault(uid, []).append((seq, x, y))
            if kind == "terran_marine" and motion == "attack":
                marine_attack += 1
            if kind == "zerg_zergling" and hp < maximum:
                zerg_damage = True
            if motion == "death":
                death_ids.add(uid)
    marine_displacement = {}
    for uid in range(1000, 1006):
        points = traces.get(uid, [])
        if points:
            x0, y0 = points[0][1:]
            marine_displacement[str(uid)] = max(round(((x - x0) ** 2 + (y - y0) ** 2) ** .5)
                                                for _, x, y in points)
    selection = [line for line in client[0].splitlines() if "selected Marines=" in line]
    full_selection = any(len(re.findall(r"openbw:1\d{3}", line)) == 6 for line in selection)
    commands = re.findall(r"\[world-control\] command=[^\s]+ unit=\d+ verb=([^ ]+) accepted=(\d)", server)
    carousel_removed = "WORLD_REMOVAL id=openrct2:ride:0#1 state=confirmed" in server
    wall_removed = "WORLD_REMOVAL id=openrct2:wall:31:896:1120:112:0#1 state=confirmed" in server
    # The ride occupies nine full tiles: x=576..671, y=544..639.
    demolition_seq = None
    wall_applied_seq = None
    latest_seq = 0
    for line in server.splitlines():
        match = SNAPSHOT.search(line)
        if match:
            latest_seq = int(match.group(1))
        if "WORLD_REMOVAL id=openrct2:ride:0#1 state=confirmed" in line:
            demolition_seq = latest_seq
        if "navigation-applied id=openrct2:wall:31:896:1120:112:0#1" in line:
            wall_applied_seq = latest_seq
    opened_footprint = []
    if demolition_seq is not None:
        for uid, points in traces.items():
            for seq, x, y in points:
                if seq > demolition_seq and 576 <= x < 672 and 544 <= y < 640:
                    opened_footprint.append({"unit": uid, "seq": seq, "x": x, "y": y})
    # This single wall tile blocks the direct west-to-east route. Count
    # observed actor positions on both sides, at the wall's y coordinate,
    # only after the native obstacle removal was applied.
    wall_applied = wall_applied_seq is not None
    opened_wall_crossings = []
    if wall_removed and wall_applied:
        for uid, points in traces.items():
            for (before_seq, before_x, before_y), (after_seq, after_x, after_y) in zip(points, points[1:]):
                if before_seq > wall_applied_seq and before_x < 896 <= after_x \
                        and 1088 <= before_y <= 1152 and 1088 <= after_y <= 1152:
                    opened_wall_crossings.append({"unit": uid, "before_seq": before_seq,
                                                   "after_seq": after_seq, "from": [before_x, before_y],
                                                   "to": [after_x, after_y]})
    result = {
        "status": "recorded", "scenario": "frontier-outpost",
        "initial_marines": sum(kind == "terran_marine" for _, _, _, _, kind, _, _ in initial),
        "initial_zerglings": sum(kind == "zerg_zergling" for _, _, _, _, kind, _, _ in initial),
        "native_navigation_ready": "WORLD_READY" in server and "navigation=native" in server,
        "six_marine_drag_selection": full_selection,
        "accepted_native_commands": {verb: sum(kind == verb and accepted == "1" for kind, accepted in commands)
                                     for verb in sorted({item[0] for item in commands})},
        "marine_displacement_pixels": marine_displacement,
        "marine_attack_snapshot_samples": marine_attack,
        "zergling_damage_observed": zerg_damage,
        "native_death_ids": sorted(death_ids),
        "carousel_demolition_confirmed": carousel_removed,
        "wall_demolition_confirmed": wall_removed,
        "wall_navigation_applied": wall_applied,
        "outcome": "victory" if "outcome=victory" in server else "defeat" if "outcome=defeat" in server else None,
        "client_a_snapshots": len(a), "client_b_snapshots": len(b),
        "shared_snapshot_sequences": len(common), "matching_snapshot_sequences": len(matching),
        "mismatched_sequences": mismatches[:20],
        "client_park_states": [{"initial": states[0] if states else None,
                                "final": states[-1] if states else None} for states in park_states],
        "park_change_synchronized": park_sync and (not carousel_removed
            or park_states[0][-1][0] == park_states[1][-1][0] == "false")
            and (not wall_removed or park_states[0][-1][1] == park_states[1][-1][1] == "false"),
        "opened_carousel_footprint_samples": opened_footprint[:12],
        "opened_wall_crossing_samples": opened_wall_crossings[:12],
        "video": next((item["filename"] for item in json.loads((out / "video-metadata.json").read_text()).get("outputs", [])
                       if item.get("filename")), None) if (out / "video-metadata.json").exists() else None,
        "input_method": "X11 graphical interface",
    }
    result["demonstration_complete"] = (result["native_navigation_ready"]
        and result["initial_marines"] == 6 and result["initial_zerglings"] == 12
        and full_selection and len(marine_displacement) == 6
        and all(value >= 100 for value in marine_displacement.values())
        and marine_attack > 0 and zerg_damage and bool(death_ids) and carousel_removed
        and result["outcome"] and bool(opened_footprint or opened_wall_crossings)
        and len(common) >= 10 and not mismatches)
    result["capture_complete"] = (result["native_navigation_ready"] and len(a) >= 10
                                  and (not b or len(common) >= 10 and not mismatches)
                                  and (not park_states[0] and not park_states[1]
                                       or result["park_change_synchronized"]))
    result["status"] = "passed" if result["demonstration_complete"] else "capture_only" if result["capture_complete"] else "incomplete"
    (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
