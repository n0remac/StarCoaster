#!/usr/bin/env python3
"""Build an ignored 256x256 OpenRCT2 scale fixture from local test data."""

import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "upstream/openrct2/test/tests/testdata/parks/BigMapTest.sv6"
OUTPUT = ROOT / "run-data/world-256-park"


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"Missing local OpenRCT2 fixture: {SOURCE}")
    user = OUTPUT / "generator"
    plugin = user / "plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    (user / "config.ini").write_text("[network]\nadvertise = false\n")
    (plugin / "world-256-park-generator.js").write_text(
        (ROOT / "scripts/world-256-park-generator.js").read_text())
    saved = user / "save/world-256-scale.park"
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
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                contents = log.read_text(errors="replace")
                if "WORLD256_GENERATOR_FAILED " in contents:
                    raise RuntimeError(contents.split("WORLD256_GENERATOR_FAILED ")[-1].splitlines()[0])
                if "WORLD256_GENERATED " in contents and saved.is_file() and saved.stat().st_size:
                    result, _ = json.JSONDecoder().raw_decode(contents.split("WORLD256_GENERATED ")[-1])
                    output = OUTPUT / "world-256-scale.park"
                    saved.replace(output)
                    (OUTPUT / "fixture.json").write_text(json.dumps(result, indent=2) + "\n")
                    print(json.dumps({"park": str(output), **result}))
                    return
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 stopped; see {log}")
                time.sleep(.2)
            raise TimeoutError(f"256 park generation timed out; see {log}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
