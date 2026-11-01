#!/usr/bin/env python3
"""Verify an edited authoritative save gets a new native cache identity and geometry."""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from park_session_supervisor import ParkSessionSupervisor
from single_map_cache import SingleMapCache
from tests.test_park_supervisor_cache_native_live import free_ports, select


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-park", type=Path, required=True)
    parser.add_argument("--replacement-park", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if not runtime.is_relative_to((ROOT / "run-data").resolve()):
        parser.error("runtime must be inside run-data")
    runtime.mkdir(parents=True, exist_ok=True)
    temp = runtime / "tmp"
    temp.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(temp)
    tempfile.tempdir = str(temp)
    for key, port in zip(("OPENRCT2_PORT", "STARCOASTER_BRIDGE_PORT",
                          "BRIDGE_OPENBW_PORT", "BRIDGE_CONTROLLER_PORT"), free_ports(4)):
        os.environ[key] = str(port)
    library = runtime / "library"
    library.mkdir(exist_ok=True)
    name = "Edited Save.park"
    shutil.copy2(args.initial_park.resolve(strict=True), library / name)
    cache = SingleMapCache(args.cache_root)
    supervisor = ParkSessionSupervisor(library, runtime, start_browser=False, cache=cache)
    try:
        first = select(supervisor, name, "")
        first_size = json.loads(Path(supervisor.plan["scenario"]).read_text())["park_size"]
        saved = runtime / "saved" / name
        saved.parent.mkdir(exist_ok=True)
        shutil.copy2(args.replacement_park.resolve(strict=True), saved)
        second = select(supervisor, name, first["generation"])
        second_size = json.loads(Path(supervisor.plan["scenario"]).read_text())["park_size"]
        records = [json.loads(line) for line in (runtime / "load-timings.jsonl").read_text().splitlines()]
        if first_size == second_size or records[0]["cache_key"] == records[1]["cache_key"]:
            raise RuntimeError("edited save reused the old geometry or cache key")
        if [record["cache_outcome"] for record in records] != ["built", "built"]:
            raise RuntimeError("edited save did not build its own validated package")
        if any(record["stages"]["session_startup"]["status"] != "ok" for record in records):
            raise RuntimeError("edited save did not reach native readiness")
        result = {"status": "ready", "first_generation": first["generation"],
                  "second_generation": second["generation"], "first_size": first_size,
                  "second_size": second_size, "first_key": records[0]["cache_key"],
                  "second_key": records[1]["cache_key"],
                  "timings": str(runtime / "load-timings.jsonl")}
        (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        supervisor.close()


if __name__ == "__main__":
    raise SystemExit(main())
