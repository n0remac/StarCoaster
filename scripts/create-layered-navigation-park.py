#!/usr/bin/env python3
"""Build the ignored layered-navigation park from a copied Frontier save."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "run-data/frontier-playable/save/frontier-outpost-playable.park"
OUTPUT = ROOT / "run-data/layered-navigation"


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit("Generate Frontier Outpost first: scripts/project.sh park frontier-outpost")
    user = OUTPUT / "generator"
    plugin = user / "plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    (user / "config.ini").write_text("[network]\nadvertise = false\n")
    shutil.copy2(ROOT / "scripts/layered-navigation-generator.js", plugin / "layered-navigation-generator.js")
    saved = user / "save/layered-navigation.park"
    saved.unlink(missing_ok=True)
    log = OUTPUT / "generator.log"
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host", str(SOURCE),
               "--headless", "--address=127.0.0.1", "--port=11769",
               f"--rct2-data-path={os.environ.get('RCT2_DATA_DIR', '/home/pi/games/rct2')}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={user}"]
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                contents = log.read_text(errors="replace")
                if "LAYERED_NAV_FAILED " in contents:
                    raise RuntimeError(contents.split("LAYERED_NAV_FAILED ")[-1].splitlines()[0])
                if "LAYERED_NAV_SOURCE " in contents and saved.is_file() and saved.stat().st_size:
                    data, _ = json.JSONDecoder().raw_decode(contents.split("LAYERED_NAV_SOURCE ")[-1])
                    park = OUTPUT / "layered-navigation.park"
                    shutil.copy2(saved, park)
                    (OUTPUT / "source-elements.json").write_text(json.dumps(data, indent=2) + "\n")
                    print(json.dumps({"park": str(park), "ride_id": data["ride_id"],
                                      "elements": len(data["elements"])}, indent=2))
                    return
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 stopped; see {log}")
                time.sleep(.2)
            raise TimeoutError(f"Layered park generation timed out; see {log}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
