#!/usr/bin/env python3
"""Verify 1:1 boundaries, native movement and two-client 256x256 capture."""

import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile


SNAPSHOT = re.compile(r"RTS Bridge apply tick=\d+ seq=(\d+) session=([0-9a-f]{32}) center_z=\d+ units=([^'\r\n]+)")
ACTOR = re.compile(r"openbw:(\d+),(\d+),(\d+),\d+,([^,]+),(\d+),([^,]+),(\d+),")
POSITION = re.compile(r"WORLD256_POSITION phase=(\d+) elapsed=(\d+) near=(\d+),(\d+) far=(\d+),(\d+)")
PARK_TICK = re.compile(r"RTS Bridge apply tick=(\d+)")


def dimensions(path):
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["smpq", "-q", "-x", str(path), "staredit/scenario.chk"],
                       cwd=directory, check=True)
        chk = (Path(directory) / "staredit/scenario.chk").read_bytes()
    cursor = 0
    while cursor + 8 <= len(chk):
        kind, size = struct.unpack_from("<4sI", chk, cursor)
        if kind == b"DIM ":
            return struct.unpack_from("<HH", chk, cursor + 8)
        cursor += 8 + size
    raise ValueError("native CHK has no DIM section")


def snapshots(text):
    return {int(seq): (session, units) for seq, session, units in SNAPSHOT.findall(text)}


def main(directory):
    out = Path(directory).resolve()
    server = (out / "server.log").read_text(errors="replace")
    client_a = (out / "client-a.log").read_text(errors="replace")
    client_b = (out / "client-b.log").read_text(errors="replace")
    a, b = snapshots(client_a), snapshots(client_b)
    common = sorted(set(a) & set(b))
    initial = {int(uid): (int(x), int(y)) for uid, x, y, *_ in ACTOR.findall(a[min(a)][1])} if a else {}
    rows = [(int(phase), int(elapsed), int(nx), int(ny), int(fx), int(fy))
            for phase, elapsed, nx, ny, fx, fy in POSITION.findall(client_a)]
    hashes = re.findall(r"(?:publisher|controller) navigation hash=([0-9a-f]{16})", server)
    final_near = max((row[2] for row in rows), default=0)
    final_far = max((row[4] for row in rows), default=0)
    cross_map = [(x, y) for phase, _, _, _, x, y in rows if phase >= 2]
    performance = json.loads((out / "performance.json").read_text())
    ticks = [[int(value) for value in PARK_TICK.findall(text)] for text in (client_a, client_b)]
    tick_rates = [round((values[-1] - values[0]) / performance["recording_seconds"], 2)
                  if len(values) >= 2 else 0 for values in ticks]
    views = [list(out.glob(f"client-{letter}-t*-rot*.png")) for letter in "ab"]
    checks = {
        "native_map_256": dimensions(out / "world-256-scale.scm") == (256, 256),
        "full_park_snapshot": "terrain=65536" in server and "WORLD_READY entities=2 targets=2" in server,
        "native_geometry_matches": len(hashes) >= 2 and hashes[0] == hashes[1],
        "unscaled_opposite_positions": initial.get(1000) == (5 * 32 + 16, 5 * 32 + 16)
            and initial.get(1001) == (250 * 32 + 16, 250 * 32 + 16),
        "both_boundary_commands": final_near >= 7 * 32 and final_far >= 252 * 32,
        "distant_pathfinding_progress": any(x < 245 * 32 and y < 245 * 32 for x, y in cross_map),
        "command_acknowledgments": client_a.count("WORLD256_ORDER ") >= 3
            and "accepted=false" not in client_a,
        "two_clients_match": len(common) >= 10 and all(a[seq] == b[seq] for seq in common),
        "opposite_boundary_cameras": "WORLD256_CAMERA boundary=far" in client_a
            and "WORLD256_CAMERA boundary=near" in client_b,
        "screenshots_and_video": all(len(group) >= 2 for group in views)
            and (out / "combined.mp4").stat().st_size > 0,
        "startup_and_memory_measured": performance["startup_to_world_ready_seconds"] > 0
            and performance["memory_at_ready"]["total_rss_kib"] > 0
            and performance.get("navigation_initialization_ms") is not None,
        "probe_complete": "WORLD256_SEQUENCE_COMPLETE elapsed=" in client_a,
    }
    result = {"status": "passed" if all(checks.values()) else "incomplete",
              "scenario": "world-256-scale", "checks": checks,
              "native_dimensions": [256, 256], "initial_actor_positions": initial,
              "snapshot_entities": 2, "snapshot_terrain_tiles": 65536,
              "navigation_hashes": hashes[:2], "shared_snapshot_sequences": len(common),
              "mismatched_sequences": [seq for seq in common if a[seq] != b[seq]][:20],
              "observed_near_x": final_near, "observed_far_edge_x": final_far,
              "distant_route_samples": cross_map[:12], "camera_screenshots": [len(group) for group in views],
              "client_park_tick_hz": tick_rates,
              "video": "combined.mp4", "capture_complete": all(checks.values())}
    (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
