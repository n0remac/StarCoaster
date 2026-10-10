#!/usr/bin/env python3
"""Build the controlled scenery park from OpenRCT2's pinned BigMapTest save."""

import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "run-data/park-generator"
PARK = DATA / "save/bridge-render-test.park"


def main() -> None:
    rct2_data = Path(os.environ.get("RCT2_DATA_DIR", "/home/pi/games/rct2"))
    if not (rct2_data / "Data/g1.dat").is_file():
        raise RuntimeError(f"Missing RCT2 graphics at {rct2_data / 'Data/g1.dat'}")
    (DATA / "plugin").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "scripts/render-test-park.js", DATA / "plugin/render-test-park.js")
    (DATA / "config.ini").write_text("[network]\nadvertise = false\n")
    PARK.unlink(missing_ok=True)
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host",
               str(ROOT / "upstream/openrct2/test/tests/testdata/parks/BigMapTest.sv6"),
               "--headless", "--address=127.0.0.1", "--port=11754",
               f"--rct2-data-path={rct2_data}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={DATA}"]
    with (DATA / "generator.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if PARK.is_file() and PARK.stat().st_size > 0:
                    print(PARK)
                    return
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 exited; see {DATA / 'generator.log'}")
                time.sleep(0.2)
            raise RuntimeError(f"Park generation timed out; see {DATA / 'generator.log'}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
