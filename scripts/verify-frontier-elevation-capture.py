#!/usr/bin/env python3
"""Check sampled native paint heights in a real graphical Frontier recording."""

import json
from pathlib import Path
import re
import sys


SNAPSHOT = re.compile(r"RTS Bridge apply tick=\d+ seq=(\d+) session=([0-9a-f]{32}) center_z=\d+ units=([^'\r\n]+)")
ACTOR = re.compile(r"openbw:(\d+),(\d+),(\d+),\d+,([^,]+),(\d+),([^,]+),(\d+),")


def read_actors(path):
    snapshots = {}
    for seq, session, units in SNAPSHOT.findall(path.read_text(errors="replace")):
        snapshots[int(seq)] = (session, units)
    actors = {}
    for seq, (_, units) in sorted(snapshots.items()):
        for uid, x, y, motion, z, kind, hp in ACTOR.findall(units):
            actors.setdefault(int(uid), []).append((seq, int(x), int(y), int(z), motion, kind, int(hp)))
    return snapshots, actors


def main(directory, mode):
    directory = Path(directory)
    a, actors = read_actors(directory / "client-a.log")
    b, _ = read_actors(directory / "client-b.log")
    common = sorted(set(a) & set(b))
    first_match = next((index for index, seq in enumerate(common) if a[seq] == b[seq]), len(common))
    joined = common[first_match:]
    later_mismatches = [seq for seq in joined if a[seq] != b[seq]]
    views = {int(match.group(1)) for path in directory.glob("client-a-t*-rot*.png")
             if (match := re.search(r"rot([0-3])\.png$", path.name))}
    checks = {"graphical_video": (directory / "combined.mp4").stat().st_size > 0,
              "two_clients_match": len(joined) >= 10 and not later_mismatches,
              "two_camera_rotations": len(views) >= 2}
    if mode == "marine":
        track = actors.get(1000, [])
        heights = [point[3] for point in track]
        checks.update(hilltop_start=bool(track) and track[0][3] == 128,
                      flat_ground=112 in heights,
                      slope_interpolation=any(112 < z < 128 for z in heights),
                      hilltop_return=bool(track) and any(z == 128 for z in heights[len(heights)//3:]),
                      no_height_pop=all(abs(a[3] - b[3]) <= 16 for a, b in zip(track, track[1:])))
        samples = {"marine_heights": sorted(set(heights)), "marine_points": len(track)}
    elif mode == "zerg":
        zergs = [point for uid, track in actors.items() if 2000 <= uid <= 2011 for point in track]
        marines = [point for uid, track in actors.items() if 1000 <= uid <= 1005 for point in track]
        climbing = sorted({point[0] for point in zergs if 25 * 32 <= point[1] < 26 * 32
                           and 30 * 32 <= point[2] < 35 * 32 and 112 < point[3] < 128})
        elevated = [point for point in zergs if 14 * 32 <= point[1] < 25 * 32
                    and 30 * 32 <= point[2] < 35 * 32 and point[3] == 128]
        attacks = [point for point in zergs if point[4] == "attack" and point[3] == 128]
        checks.update(low_start=any(point[3] == 112 for point in zergs),
                      slope_interpolation=bool(climbing),
                      reaches_hilltop=bool(elevated),
                      combat_on_hilltop=bool(attacks) and any(point[6] < 40 for point in marines),
                      no_height_pop=all(abs(a[3] - b[3]) <= 16 for uid, track in actors.items()
                                        if 2000 <= uid <= 2011 for a, b in zip(track, track[1:])))
        samples = {"zerg_slope_sequences": climbing[:12], "zerg_high_samples": len(elevated),
                   "zerg_high_attack_samples": len(attacks), "marine_damaged_samples":
                       sum(point[6] < 40 for point in marines)}
    else:
        raise ValueError("mode must be marine or zerg")
    result = {"mode": mode, "source": "two graphical OpenRCT2 clients with native painter logs",
              "checks": checks, "shared_snapshots": len(common), "rotations": sorted(views),
              "join_convergence_sequence": joined[0] if joined else None,
              "initial_join_mismatches": first_match,
              "post_convergence_mismatches": later_mismatches[:12],
              "samples": samples}
    (directory / f"elevation-{mode}-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
