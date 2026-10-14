#!/usr/bin/env python3
"""Check native readiness and synchronized client evidence for a packaged scenario."""

import json
from pathlib import Path
import re
import sys


SNAPSHOT = re.compile(r"RTS Bridge apply tick=\d+ seq=(\d+) session=([0-9a-f]{32}) center_z=\d+ units=([^\x1b\r\n]+)")
STATUS = re.compile(r"WORLD_SCENARIO_STATUS scenario=([a-z0-9-]+) wave=\d+/\d+ state=\w+ outcome=(victory|defeat)?")


def snapshots(log):
    return {int(seq): (session, units) for seq, session, units in SNAPSHOT.findall(log)}


def verify(directory):
    out = Path(directory)
    config = json.loads((out / "scenario-config.json").read_text())
    scenario_id = config["scenario_id"]
    server = (out / "server.log").read_text(errors="replace")
    clients = [(out / f"client-{letter}.log").read_text(errors="replace")
               for letter in "ab" if (out / f"client-{letter}.log").is_file()]
    if not clients:
        raise ValueError("no client logs")
    streams = [snapshots(log) for log in clients]
    status = [STATUS.findall(log) for log in clients]
    common = sorted(set(streams[0]) & set(streams[1])) if len(streams) == 2 else []
    first_match = next((i for i, seq in enumerate(common) if streams[0][seq] == streams[1][seq]), len(common))
    joined = common[first_match:]
    mismatches = [seq for seq in joined if streams[0][seq] != streams[1][seq]]
    screenshots = [name for name in (f"client-{letter}-{point}.png" for letter in "ab" for point in ("initial", "final"))
                   if (out / name).is_file()]
    valid_images = all((out / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for name in screenshots)
    expected_images = 2 * len(clients)
    identities_match = all(rows and all(item[0] == scenario_id for item in rows) for rows in status)
    outcomes = [outcome for rows in status for _, outcome in rows if outcome]
    outcome = outcomes[-1] if outcomes else None
    result = {
        "scenario": scenario_id,
        "display_name": config.get("display_name"),
        "native_navigation_ready": "WORLD_READY" in server and "navigation=native" in server,
        "scenario_status_synchronized": identities_match,
        "client_snapshots": [len(stream) for stream in streams],
        "shared_snapshot_sequences": len(common),
        "matching_snapshot_sequences": len(joined) - len(mismatches),
        "mismatched_sequences": mismatches[:20],
        "screenshots": screenshots,
        "valid_screenshots": len(screenshots) == expected_images and valid_images,
        "outcome": outcome,
        "outcome_observed": outcome is not None,
    }
    result["capture_complete"] = (result["native_navigation_ready"] and identities_match
                                  and all(count >= 10 for count in result["client_snapshots"])
                                  and result["valid_screenshots"]
                                  and (len(clients) == 1 or len(joined) >= 10 and not mismatches))
    result["status"] = "passed" if result["capture_complete"] else "incomplete"
    (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1]), indent=2))
