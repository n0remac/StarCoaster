"""Resolve and prepare the existing packaged scenarios for project CLI commands."""

import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_INPUTS = ("scripts/park-assault-generator.js", "scripts/create-park-assault.py",
                    "scripts/park_navigation.py")


def resolve(scenario_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", scenario_id):
        raise ValueError("invalid scenario ID (use 1–64 lowercase letters, digits, or hyphens)")
    package = ROOT / "scenarios" / scenario_id
    scenario_path = package / "scenario.json"
    mapping_path = package / "mapping.json"
    metadata_path = package / "package.json"
    if not all(path.is_file() for path in (scenario_path, mapping_path, metadata_path)):
        raise ValueError(f"missing scenario package: {scenario_id}")
    scenario = json.loads(scenario_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    if scenario.get("scenario_id") != scenario_id:
        raise ValueError("incomplete or mismatched scenario package")

    def output_path(value, field):
        if not isinstance(value, str):
            raise ValueError(f"invalid package {field}")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "run-data":
            raise ValueError(f"{field} must be under run-data")
        return str(ROOT / relative)

    park = output_path(scenario.get("park_file"), "park_file")
    generator = metadata.get("generator")
    if not isinstance(generator, list) or not generator or not all(isinstance(part, str) for part in generator):
        raise ValueError("invalid package generator")
    if generator[0] != "scripts/create-park-assault.py" or generator[1:] not in (["--playable"], ["--example-defense"]):
        raise ValueError("unrecognized park generator")
    output = ROOT / "run-data/scenarios" / scenario_id
    return {"scenario_id": scenario_id, "scenario": str(scenario_path),
            "mapping": str(mapping_path), "park": park,
            "fixture": output_path(metadata.get("fixture"), "fixture"),
            "navigation": output_path(metadata.get("navigation"), "navigation"),
            "generator": ["python3", *generator],
            "native_map": str(output / "map" / f"{scenario_id}.scm"),
            "spawn_journal": str(output / "spawn-queue.json"),
            "server_data": str(output / "server"), "client_data": str(output / "client")}


def ensure_park(plan: dict, force: bool = False) -> None:
    park, fixture, navigation = (Path(plan[key]) for key in ("park", "fixture", "navigation"))
    inputs = [ROOT / path for path in GENERATOR_INPUTS]
    if force or any(not path.is_file() for path in (park, fixture, navigation)) or any(
            source.stat().st_mtime > park.stat().st_mtime for source in inputs):
        subprocess.run(plan["generator"], cwd=ROOT, check=True)
    if any(not path.is_file() for path in (park, fixture, navigation)):
        raise RuntimeError(f"park generator did not produce the complete {plan['scenario_id']} package")


def build_native_map(plan: dict, output_override=None) -> Path:
    output = Path(output_override or plan["native_map"])
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["python3", "scripts/create-world-base-map.py", "--scenario", plan["scenario"],
                    "--output", str(output)], cwd=ROOT, check=True)
    return output


def session_environment(plan: dict, overrides=None) -> dict:
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
    if overrides:
        env.update(overrides)
    return env
