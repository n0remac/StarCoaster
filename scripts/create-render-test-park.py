#!/usr/bin/env python3
"""Build the controlled scenery park from OpenRCT2's pinned BigMapTest save."""

import os
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-generator"
PARK = DATA / "save/bridge-render-test.park"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("render", "ride-siege"), default="render")
    parser.add_argument("--probe-demolition", action="store_true")
    args = parser.parse_args()
    if args.probe_demolition and args.scenario != "ride-siege":
        parser.error("--probe-demolition requires --scenario ride-siege")
    data = DATA if args.scenario == "render" else ROOT / "run-data/ride-siege-generator"
    park = PARK if args.scenario == "render" else data / "save/bridge-ride-siege.park"
    rct2_data = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    if not (rct2_data / "Data/g1.dat").is_file():
        raise RuntimeError(f"Missing RCT2 graphics at {rct2_data / 'Data/g1.dat'}")
    (data / "plugin").mkdir(parents=True, exist_ok=True)
    source = (ROOT / "scripts/render-test-park.js").read_text()
    mode = "ride-siege-probe" if args.probe_demolition else args.scenario
    source = source.replace('var fixtureMode = "render";', f'var fixtureMode = "{mode}";')
    (data / "plugin/render-test-park.js").write_text(source)
    (data / "config.ini").write_text("[network]\nadvertise = false\n")
    if not args.probe_demolition:
        park.unlink(missing_ok=True)
    elif not park.is_file():
        raise RuntimeError(f"Create {park} before the demolition probe")
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host",
               str(park if args.probe_demolition else ROOT / "upstream/openrct2/test/tests/testdata/parks/BigMapTest.sv6"),
               "--headless", "--address=127.0.0.1", "--port=11754",
               f"--rct2-data-path={rct2_data}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={data}"]
    with (data / ("demolition-probe.log" if args.probe_demolition else "generator.log")).open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                contents = (data / ("demolition-probe.log" if args.probe_demolition else "generator.log")).read_text(errors="replace")
                if args.probe_demolition and "RIDE_SIEGE_PROBE " in contents:
                    result, _ = json.JSONDecoder().raw_decode(contents.split("RIDE_SIEGE_PROBE ")[-1])
                    if result["error"] or not result["removed"] or result["tracks_before"] != 9:
                        raise RuntimeError(f"Ride demolition probe failed: {result}")
                    print(json.dumps(result))
                    return
                if park.is_file() and park.stat().st_size > 0 and not args.probe_demolition:
                    if args.scenario == "ride-siege":
                        if "RIDE_SIEGE_METADATA " not in contents:
                            time.sleep(0.2)
                            continue
                        metadata, _ = json.JSONDecoder().raw_decode(contents.split("RIDE_SIEGE_METADATA ")[-1])
                        (data / "fixture.json").write_text(json.dumps(metadata, indent=2) + "\n")
                    print(park)
                    return
                if "RIDE_SIEGE_FAILED" in contents or "RIDE_SIEGE_PROBE_FAILED" in contents:
                    raise RuntimeError(contents.splitlines()[-1])
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 exited; see {data / 'generator.log'}")
                time.sleep(0.2)
            raise RuntimeError(f"Park generation timed out; see {data / 'generator.log'}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
