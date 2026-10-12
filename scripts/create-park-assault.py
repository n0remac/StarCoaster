#!/usr/bin/env python3
"""Generate Frontier Outpost and probe native demolition in a throwaway process."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from park_navigation import ParkGrid


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-assault"
PARK = DATA / "save/frontier-outpost.park"
SOURCE = ROOT / "upstream/openrct2/test/tests/testdata/parks/BigMapTest.sv6"


def wait_for_marker(log: Path, marker: str, park: Path | None, process: subprocess.Popen) -> dict:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        contents = log.read_text(errors="replace")
        if "PARK_ASSAULT_FAILED " in contents:
            raise RuntimeError(contents.split("PARK_ASSAULT_FAILED ")[-1].splitlines()[0])
        if marker in contents:
            payload = contents.split(marker)[-1]
            result, _ = json.JSONDecoder().raw_decode(payload)
            if park is None or (park.is_file() and park.stat().st_size > 0):
                return result
        if process.poll() is not None:
            raise RuntimeError(f"OpenRCT2 exited early; see {log}")
        time.sleep(0.2)
    raise TimeoutError(f"Park generation timed out; see {log}")


def run(probe: bool) -> dict:
    output = DATA / ("demolition-probe" if probe else "generator")
    (output / "plugin").mkdir(parents=True, exist_ok=True)
    (output / "config.ini").write_text("[network]\nadvertise = false\n")
    source = (ROOT / "scripts/park-assault-generator.js").read_text()
    if probe:
        source = source.replace("var probe = false;", "var probe = true;")
    (output / "plugin/park-assault-generator.js").write_text(source)
    log = output / "openrct2.log"
    if not probe:
        PARK.unlink(missing_ok=True)
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host", str(PARK if probe else SOURCE),
               "--headless", "--address=127.0.0.1", "--port=11761",
               f"--rct2-data-path={os.environ.get('RCT2_DATA_DIR', '/home/pi/games/rct2')}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={output}"]
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        try:
            return wait_for_marker(log, "PARK_ASSAULT_PROBE " if probe else "PARK_ASSAULT_METADATA ",
                                   None if probe else output / "save/frontier-outpost.park", process)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-demolition", action="store_true")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    if args.probe_demolition:
        if not PARK.is_file():
            raise RuntimeError(f"Generate {PARK} first")
        result = run(True)
        if len(result) != 3 or any(row["error"] or not row["removed"] or row["before"] < 1 or row["after"]
                                   for row in result):
            raise RuntimeError(f"Native demolition probe failed: {result}")
        (DATA / "demolition-probe.json").write_text(json.dumps(result, indent=2) + "\n")
    else:
        result = run(False)
        generated = DATA / "generator/save/frontier-outpost.park"
        PARK.parent.mkdir(parents=True, exist_ok=True)
        generated.replace(PARK)
        contents = (DATA / "generator/openrct2.log").read_text(errors="replace")
        if "PARK_ASSAULT_NAV " not in contents:
            raise RuntimeError("OpenRCT2 did not export navigation elements")
        raw = contents.split("PARK_ASSAULT_NAV ")[-1]
        navigation, _ = json.JSONDecoder().raw_decode(raw)
        (DATA / "navigation-elements.json").write_text(json.dumps(navigation, separators=(",", ":")) + "\n")
        grid = ParkGrid(navigation, result, validate_approaches=False)
        for target in result["targets"]:
            actual = {(element["x"], element["y"]) for element in navigation["elements"]
                      if element["type"] == "track" and element["ride_id"] == target["ride_id"]}
            if actual != {(tile["x"], tile["y"]) for tile in target["footprint_tiles"]}:
                raise ValueError(f"track footprint mismatch for {target['id']}")
            target["attack_approaches"] = grid.select_attack_approaches(target["id"])
        (DATA / "fixture.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
