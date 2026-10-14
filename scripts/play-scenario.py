#!/usr/bin/env python3
"""Resolve a scenario package and reuse the existing world session launcher."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def resolve(scenario_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", scenario_id):
        raise ValueError("invalid scenario ID")
    package = ROOT / "scenarios" / scenario_id
    scenario_path = package / "scenario.json"
    mapping_path = package / "mapping.json"
    metadata_path = package / "package.json"
    scenario = json.loads(scenario_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    if scenario.get("scenario_id") != scenario_id or not mapping_path.is_file():
        raise ValueError("incomplete or mismatched scenario package")
    park_relative = Path(scenario["park_file"])
    if park_relative.is_absolute() or ".." in park_relative.parts or park_relative.parts[0] != "run-data":
        raise ValueError("park_file must be under run-data")
    generator = metadata.get("generator")
    if not isinstance(generator, list) or not generator or not all(isinstance(part, str) for part in generator):
        raise ValueError("invalid package generator")
    if generator[0] != "scripts/create-park-assault.py":
        raise ValueError("unrecognized park generator")
    for key in ("fixture", "navigation"):
        value = Path(metadata[key])
        if value.is_absolute() or ".." in value.parts or value.parts[0] != "run-data":
            raise ValueError(f"invalid package {key}")
    output = ROOT / "run-data/scenarios" / scenario_id
    return {"scenario_id": scenario_id, "scenario": str(scenario_path),
            "mapping": str(mapping_path), "park": str(ROOT / park_relative),
            "fixture": str(ROOT / metadata["fixture"]),
            "navigation": str(ROOT / metadata["navigation"]),
            "generator": ["python3", *generator],
            "native_map": str(output / "map" / f"{scenario_id}.scm"),
            "spawn_journal": str(output / "spawn-queue.json"),
            "server_data": str(output / "server"), "client_data": str(output / "client")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_id")
    parser.add_argument("--plan", action="store_true", help="print resolved package without starting engines")
    args = parser.parse_args()
    plan = resolve(args.scenario_id)
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    park, fixture, navigation = (Path(plan[key]) for key in ("park", "fixture", "navigation"))
    source_inputs = [ROOT / "scripts/park-assault-generator.js", ROOT / "scripts/create-park-assault.py",
                     ROOT / "scripts/park_navigation.py"]
    if any(not path.is_file() for path in (park, fixture, navigation)) or any(
            input_path.stat().st_mtime > park.stat().st_mtime for input_path in source_inputs):
        subprocess.run(plan["generator"], cwd=ROOT, check=True)
    native_map = Path(plan["native_map"])
    native_map.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", plan["scenario"],
                    "--output", str(native_map)], cwd=ROOT, check=True)
    env = os.environ.copy()
    env.setdefault("RCT2_DATA_DIR", str(Path.home() / "games/rct2"))
    env.setdefault("STARCRAFT_DATA_DIR", str(Path.home() / "games/starcraft"))
    env["BRIDGE_MAP_FILE"] = plan["native_map"]
    env["BRIDGE_SCENARIO_CONFIG"] = plan["scenario"]
    env["BRIDGE_RULES_CONFIG"] = plan["mapping"]
    env["BRIDGE_SPAWN_JOURNAL"] = plan["spawn_journal"]
    env.setdefault("BRIDGE_SERVER_DATA_DIR", plan["server_data"])
    env.setdefault("BRIDGE_CLIENT_DATA_DIR", plan["client_data"])
    env.setdefault("BRIDGE_LAUNCH_CLIENT", "1" if env.get("DISPLAY") else "0")
    os.execvpe(str(ROOT / "scripts/run-world-session.sh"),
               [str(ROOT / "scripts/run-world-session.sh"), plan["park"]], env)


if __name__ == "__main__":
    main()
