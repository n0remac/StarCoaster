#!/usr/bin/env python3
"""Verify a live Frontier cliff detour, slope ascent, and native attack."""

import json
from pathlib import Path
import re
import sys


POSITION = re.compile(r"RIDGE_POSITION phase=(\d+) elapsed=(\d+) units=([^'\r\n]+)")
UNIT = re.compile(r"openbw:(\d+):(\d+),(\d+),(\d+),([a-z_]+)")


def main(directory):
    directory = Path(directory)
    client_path = directory / "client.log"
    if not client_path.exists():
        client_path = directory / "client-a.log"
    client = client_path.read_text(errors="replace")
    server = (directory / "server.log").read_text(errors="replace")
    rows = []
    for match in POSITION.finditer(client):
        units = {int(uid): (int(x), int(y), int(hp), motion)
                 for uid, x, y, hp, motion in UNIT.findall(match.group(3))}
        rows.append({"phase": int(match.group(1)), "elapsed_ms": int(match.group(2)),
                     "units": units})
    route = [row for row in rows if row["phase"] in (1, 2) and 1000 in row["units"]]
    below = [row for row in route if row["phase"] == 1 and row["units"][1000][0] < 13 * 32]
    ascent = [row["units"][1000] for row in route if row["phase"] == 2]
    slope = [point for point in ascent if 14 * 32 <= point[0] < 19 * 32
             and (29 * 32 <= point[1] < 30 * 32 or 35 * 32 <= point[1] < 36 * 32)]
    high = [row["units"][1000] for row in rows if row["phase"] in (2, 3)
            and 1000 in row["units"] and 19 * 32 < row["units"][1000][0] < 25 * 32
            and 30 * 32 <= row["units"][1000][1] < 35 * 32]
    cliff_crossings = []
    for a, b in zip(ascent, ascent[1:]):
        if (a[0] - 14 * 32) * (b[0] - 14 * 32) <= 0 and a[0] != b[0]:
            fraction = (14 * 32 - a[0]) / (b[0] - a[0])
            y = round(a[1] + fraction * (b[1] - a[1]))
            if 30 * 32 <= y < 35 * 32:
                cliff_crossings.append(y)
    attacks = [row for row in rows if row["phase"] >= 3
               for uid, point in row["units"].items()
               if (1000 <= uid <= 1005 and point[3] == "attack")
               or ((2000 <= uid <= 2011 or 3001 <= uid <= 3005) and point[2] < 35)]
    hashes = re.findall(r"(?:controller|publisher) navigation hash=([0-9a-f]{16})", server)
    checks = {
        "both_native_participants_ready": len(hashes) >= 2 and hashes[0] == hashes[1]
            and "WORLD_READY" in server,
        "starts_on_raised_marine_platform": bool(rows) and 1000 in rows[0]["units"]
            and 15 * 32 <= rows[0]["units"][1000][0] < 18 * 32,
        "descends_below_cliff": bool(below),
        "ascends_a_slope": bool(slope) and bool(high),
        "cannot_cross_cliff_directly": bool(ascent) and not cliff_crossings,
        "engages_after_ascent": bool(attacks) and "RIDGE_SEQUENCE_COMPLETE failed=" not in client,
    }
    result = {"source": "OpenBW actor positions from connected OpenRCT2 client",
              "checks": checks, "samples": len(rows), "ascent_slope_samples": slope[:8],
              "ascent_high_samples": high[:8], "cliff_crossings": cliff_crossings,
              "attack_samples": len(attacks),
              "marine_route": [{"phase": row["phase"], "elapsed_ms": row["elapsed_ms"],
                                "x": row["units"][1000][0], "y": row["units"][1000][1]}
                               for row in route]}
    (directory / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "marine_route"}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
