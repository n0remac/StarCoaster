#!/usr/bin/env python3
"""Reproduce a dense 256x256 stock scenario through real native preflight."""

import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor


def metric(log, pattern):
    match = re.search(pattern, log)
    if not match:
        raise AssertionError("missing preflight metric: " + pattern)
    return tuple(int(value) for value in match.groups())


def main():
    if not os.environ.get("RCT2_DATA_DIR") or not os.environ.get("STARCRAFT_DATA_DIR"):
        raise SystemExit("Set RCT2_DATA_DIR and STARCRAFT_DATA_DIR to licensed local data")
    runtime = ROOT / "run-data" / f"dense-stock-handoff-{int(time.time())}"
    library = runtime / "library"
    library.mkdir(parents=True)
    supervisor = ParkSessionSupervisor(library, runtime, start_browser=False)
    try:
        started = time.monotonic()
        generation, plan = supervisor.prepare("Six Flags Great Adventure.SC6")
        elapsed = round(time.monotonic() - started, 3)
        log_path = runtime / "sessions" / generation / "preflight" / "session.log"
        log = log_path.read_text(errors="replace")
        scenario = json.loads(Path(plan["scenario"]).read_text())
        assert scenario["park_size"] == [256, 256], scenario["park_size"]
        entities, terrain, chunks = metric(log, r"WORLD_SNAPSHOT[^\n]* entities=(\d+) terrain=(\d+) chunks=(\d+)")
        transfer = metric(log, r"native snapshot transfer entities=\d+ terrain=\d+ chunks=\d+ payload_bytes=(\d+) max_chunk_bytes=(\d+)")
        navigation = metric(log, r"native navigation transfer bytes=(\d+) hex_bytes=(\d+) chunks=(\d+)")
        assert entities > 20000 and terrain == 65536 and chunks > 1000
        assert transfer[0] > 0 and transfer[1] < 1048576
        assert navigation[0] == 131072 and navigation[1] == 262144
        assert "WORLD_SCENARIO_STATUS" in log and "navigation-mask" in log
        report = {"scenario": "Six Flags Great Adventure.SC6", "dimensions": [256, 256],
                  "entities": entities, "terrain": terrain, "snapshot_chunks": chunks,
                  "snapshot_payload_bytes": transfer[0], "largest_chunk_bytes": transfer[1],
                  "collision_bytes": navigation[0], "collision_hex_bytes": navigation[1],
                  "collision_chunks": navigation[2], "preflight_seconds": elapsed,
                  "preflight_log": str(log_path)}
        (runtime / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"result": "PASS", "runtime": str(runtime), **report}))
    finally:
        supervisor.close()


if __name__ == "__main__":
    main()
