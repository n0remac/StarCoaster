#!/usr/bin/env python3
"""Summarize a recorded Mt. Zergling playthrough from native journals and client logs."""

from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys


ACTOR = re.compile(r"(openbw:\d+),(\d+),(\d+),\d+,([a-z_]+),\d+,(zerg_zergling|terran_marine),")
PATCH = re.compile(r"park patch synchronized id=\S+ revision=(\d+) hash=([0-9a-f]{16}) frame=(\d+)")


def verify(directory: Path) -> dict:
    basic = json.loads((directory / "verification.json").read_text())
    runtime = json.loads((directory / "spawn-queue.json.scenario.json").read_text())
    scenario = json.loads((directory / "scenario-config.json").read_text())
    server = (directory / "server.log").read_text(errors="replace")
    client = (directory / "client-a.log").read_text(errors="replace")
    trajectories = defaultdict(list)
    attacks = {"zerg_zergling": 0, "terran_marine": 0}
    max_zerglings = 0
    for line in client.splitlines():
        if "RTS Bridge apply tick=" not in line:
            continue
        rows = ACTOR.findall(line)
        max_zerglings = max(max_zerglings, sum(kind == "zerg_zergling" for _, _, _, _, kind in rows))
        for actor_id, x, y, order, kind in rows:
            if kind == "zerg_zergling":
                trajectories[actor_id].append((int(x), int(y)))
            if order == "attack":
                attacks[kind] += 1
    moved = sum(any(abs(x - rows[0][0]) + abs(y - rows[0][1]) > 128 for x, y in rows)
                for rows in trajectories.values())
    waves = runtime.get("waves") or []
    periodic = [wave for wave in waves if wave["origin"] == "periodic"]
    manual = [wave for wave in waves if wave["origin"] == "manual"]
    actor_ids = [unit["actor_id"] for wave in waves for unit in wave["units"] if unit.get("actor_id")]
    interval = scenario["park_defense"]["interval_frames"]
    patches = PATCH.findall(server)
    confirmed_patches = [(revision, digest, frame) for revision, digest, frame in patches
                         if all(f"[{role}] navigation-mask hash={digest} frame={frame} accepted=1" in server
                                for role in ("world", "world-control"))]
    probe = re.search(r"MT_ZERGLING_CONSTRUCTION_ATTEMPT zerglings=(\d+)", client)
    duration = float(json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
        str(directory / "combined.mp4")]))["format"]["duration"])
    checks = {
        "graphical_capture_and_two_clients": basic["capture_complete"]
            and not basic["mismatched_sequences"] and basic["matching_snapshot_sequences"] >= 10,
        "at_least_five_waves_with_manual": len(waves) >= 5 and len(periodic) >= 2 and bool(manual),
        "automatic_interval_unaffected_by_manual": len(periodic) >= 2
            and all(right["triggered_frame"] - left["triggered_frame"] == interval
                    for left, right in zip(periodic, periodic[1:])),
        "all_native_actor_identities_unique": len(actor_ids) == len(set(actor_ids))
            and len(actor_ids) >= len(waves) * scenario["park_defense"]["units_per_wave"],
        "construction_confirmed_during_combat": bool(probe) and int(probe.group(1)) > 0
            and "MT_ZERGLING_CONSTRUCTION_BUILD x=110 y=110 accepted=true" in client
            and bool(confirmed_patches),
        "multiple_zerglings_navigate_and_fight": max_zerglings >= 2 and moved >= 2
            and attacks["zerg_zergling"] > 0 and attacks["terran_marine"] > 0,
        "park_defense_has_no_rts_outcome": runtime.get("outcome", "") == "" and basic["outcome"] is None,
        "six_minute_video": duration >= 350,
        "no_bridge_or_action_errors": "scenario runtime unhealthy" not in server
            and "WORLD_WAVE_STATUS_ERROR" not in server
            and "WORLD_SPAWN_STATUS_ERROR" not in server,
    }
    result = {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
              "wave_ids": [wave["id"] for wave in waves],
              "periodic_trigger_frames": [wave["triggered_frame"] for wave in periodic],
              "manual_trigger_frames": [wave["triggered_frame"] for wave in manual],
              "unique_zergling_actors": len(trajectories), "max_simultaneous_zerglings": max_zerglings,
              "zerglings_moving_over_four_tiles": moved, "attack_snapshot_mentions": attacks,
              "confirmed_construction_patches": confirmed_patches,
              "matching_client_snapshot_sequences": basic["matching_snapshot_sequences"],
              "video_duration_seconds": duration}
    (directory / "mt-zergling-live-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    report = verify(Path(sys.argv[1]))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
