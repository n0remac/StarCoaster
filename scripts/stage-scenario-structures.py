#!/usr/bin/env python3
"""Stage declarative structures in a derived park using OpenRCT2's own map API."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def stage(source: Path, destination: Path, scenario_path: Path) -> None:
    scenario = json.loads(scenario_path.read_text())
    catalog = {item["id"]: item for item in json.loads(
        (ROOT / "bridge-protocol/starcraft-types.json").read_text())["buildings"]}
    specs = []
    for item in scenario.get("initial_structures", []):
        building = catalog[item["type"]]
        specs.append({**item, "object_id": building["object_id"],
                      "width": building["width"], "height": building["height"],
                      "owner": {"zerg": 0, "terran": 1}[item["faction"]]})
    if not specs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    data = destination.parent.parent / "structure-stage"
    # Staging runs before the gameplay host installs its construction objects.
    # Give this isolated OpenRCT2 process the scenario's required objects too.
    game_dir = os.environ.get("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))
    for building_type in dict.fromkeys(item["type"] for item in specs):
        subprocess.run(["python3", str(ROOT / "scripts/install-starcraft-construction-object.py"),
                        str(data), "--game-dir", game_dir, "--building-type", building_type],
                       cwd=ROOT, check=True)
    (data / "plugin").mkdir(parents=True, exist_ok=True)
    (data / "config.ini").write_text("[network]\nadvertise = false\n")
    script = (ROOT / "scripts/stage-scenario-structures.js").read_text().replace(
        "__STARCOASTER_STRUCTURES__", json.dumps(specs, separators=(",", ":")))
    (data / "plugin/stage-scenario-structures.js").write_text(script)
    staged = data / "save/scenario-structures.park"
    staged.unlink(missing_ok=True)
    command = [str(ROOT / "build/openrct2/openrct2-cli"), "host", str(source), "--headless",
               "--address=127.0.0.1", "--port=11761",
               f"--rct2-data-path={os.environ.get('RCT2_DATA_DIR', str(Path.home() / 'games/rct2'))}",
               f"--openrct2-data-path={ROOT / 'build/openrct2-stage/usr/local/share/openrct2'}",
               f"--user-data-path={data}"]
    log = data / "stage.log"
    with log.open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, cwd=ROOT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                content = log.read_text(errors="replace")
                if "SCENARIO_STRUCTURES_FAILED " in content:
                    raise RuntimeError(content.split("SCENARIO_STRUCTURES_FAILED ")[-1].splitlines()[0])
                if "SCENARIO_STRUCTURES_STAGED " in content and staged.is_file() and staged.stat().st_size:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    staged.replace(destination)
                    return
                if process.poll() is not None:
                    raise RuntimeError(f"OpenRCT2 exited while staging structures; see {log}")
                time.sleep(.2)
            raise TimeoutError(f"OpenRCT2 structure staging timed out; see {log}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("scenario", type=Path)
    arguments = parser.parse_args()
    stage(arguments.source, arguments.destination, arguments.scenario)
