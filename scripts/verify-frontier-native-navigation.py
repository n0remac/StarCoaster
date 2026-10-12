#!/usr/bin/env python3
"""Check observed OpenBW positions from the opt-in native navigation run."""

import json
from pathlib import Path
import re
import sys


POSITION = re.compile(r"NATIVE_NAV_POSITION phase=(\d+) elapsed=(\d+) units=([^'\r\n]+)")
UNIT = re.compile(r"openbw:(1\d{3}):(\d+),(\d+)")


def crossings(rows, phase, boundary=896):
    tracks = {}
    for row in rows:
        if row["phase"] != phase:
            continue
        for uid, point in row["units"].items():
            tracks.setdefault(uid, []).append(point)
    result = []
    for uid, track in tracks.items():
        for (ax, ay), (bx, by) in zip(track, track[1:]):
            if (ax - boundary) * (bx - boundary) > 0 or ax == bx:
                continue
            fraction = (boundary - ax) / (bx - ax)
            if 0 <= fraction <= 1:
                result.append({"unit": uid, "y": round(ay + fraction * (by - ay))})
    return result


def main(directory):
    source = Path(directory)
    client = (source / "client.log").read_text(errors="replace")
    server = (source / "server.log").read_text(errors="replace")
    rows = []
    for match in POSITION.finditer(client):
        rows.append({"phase": int(match.group(1)), "elapsed_ms": int(match.group(2)),
                     "units": {int(uid): (int(x), int(y)) for uid, x, y in UNIT.findall(match.group(3))}})
    phase1 = [row for row in rows if row["phase"] == 1]
    phase2 = crossings(rows, 2)
    phase4 = crossings(rows, 4)
    carousel_before = [point for row in rows if row["phase"] < 6 for point in row["units"].values()
                       if 576 <= point[0] < 672 and 544 <= point[1] < 640]
    carousel_after = [{"phase": row["phase"], "unit": uid, "x": point[0], "y": point[1]}
                      for row in rows if row["phase"] == 6 for uid, point in row["units"].items()
                      if 576 <= point[0] < 672 and 544 <= point[1] < 640]
    starts = next((row["units"] for row in rows if len(row["units"]) == 6), {})
    phase1_ends = phase1[-1]["units"] if phase1 else {}
    displacements = {uid: round(((point[0] - starts[uid][0]) ** 2
                                + (point[1] - starts[uid][1]) ** 2) ** .5)
                     for uid, point in phase1_ends.items() if uid in starts}
    checks = {
        "carousel_avoidance": bool(phase1) and not carousel_before
            and all(point[1] < 700 for point in phase1_ends.values()),
        "legitimate_wall_opening": any(item["y"] < 512 or item["y"] >= 1280 for item in phase2),
        "blocked_corridor": bool(phase2) and all(item["y"] < 512 or item["y"] >= 1280 for item in phase2),
        "wall_demolition_opens_route": "WORLD_REMOVAL id=openrct2:wall:31:896:1120:112:1#1 state=confirmed" in server
            and any(1110 <= item["y"] <= 1160 for item in phase4),
        "carousel_demolition_opens_footprint": "WORLD_REMOVAL id=openrct2:ride:0#1 state=confirmed" in server
            and bool(carousel_after),
        "six_marines_move_without_stall": len(displacements) == 6 and min(displacements.values()) >= 240,
    }
    result = {"source": "OpenBW actor positions in live client snapshots", "checks": checks,
              "phase_rows": {str(n): sum(row["phase"] == n for row in rows) for n in range(8)},
              "pre_demolition_carousel_intrusions": len(carousel_before),
              "pre_demolition_wall_crossings": phase2, "post_demolition_wall_crossings": phase4,
              "post_demolition_carousel_samples": carousel_after[:12],
              "marine_displacements": displacements,
              "wall_removed": "NATIVE_NAV_WALL_REMOVED" in client,
              "carousel_removed": "NATIVE_NAV_CAROUSEL_REMOVED" in client}
    (source / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
