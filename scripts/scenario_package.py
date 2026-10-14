"""Resolve and prepare the existing packaged scenarios for project CLI commands."""

import json
import os
from pathlib import Path
import re
import subprocess
from park_layout import load as load_layout


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_INPUTS = ("scripts/park-assault-generator.js", "scripts/create-park-assault.py",
                    "scripts/park_navigation.py", "scripts/park_layout.py")


def resolve(scenario_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", scenario_id):
        raise ValueError("invalid scenario ID (use 1–64 lowercase letters, digits, or hyphens)")
    package = ROOT / "scenarios" / scenario_id
    if not package.resolve().is_relative_to((ROOT / "scenarios").resolve()):
        raise ValueError("unsafe scenario package path")
    scenario_path = package / "scenario.json"
    mapping_path = package / "mapping.json"
    metadata_path = package / "package.json"
    if not all(path.is_file() for path in (scenario_path, mapping_path, metadata_path)):
        raise ValueError(f"missing scenario package: {scenario_id}")
    scenario = json.loads(scenario_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    if scenario.get("scenario_id") != scenario_id:
        raise ValueError("incomplete or mismatched scenario package")

    def output_path(value, field, isolated=False):
        if not isinstance(value, str):
            raise ValueError(f"invalid package {field}")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "run-data":
            raise ValueError(f"{field} must be under run-data")
        target = ROOT / relative
        base = ROOT / "run-data" / scenario_id if isolated else ROOT / "run-data"
        if not target.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"unsafe {field} output location")
        return str(target)

    generator = metadata.get("generator")
    layout = None
    if generator == "layout-v1":
        value = metadata.get("layout")
        if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError("invalid layout path")
        layout = package / value
        if not layout.resolve().is_relative_to(package.resolve()) or not layout.is_file():
            raise ValueError("missing or unsafe layout file")
        load_layout(layout)
        command = ["python3", "scripts/create-park-assault.py", "--layout", str(layout), "--scenario-id", scenario_id]
    elif isinstance(generator, list) and generator in (["scripts/create-park-assault.py", "--playable"],
                                                     ["scripts/create-park-assault.py", "--example-defense"]):
        command = ["python3", *generator]
    else:
        raise ValueError("unrecognized park generator")
    isolated = layout is not None
    park = output_path(scenario.get("park_file"), "park_file", isolated)
    if isolated and park != str(ROOT / "run-data" / scenario_id / "save" / f"{scenario_id}.park"):
        raise ValueError("layout park output does not match generator")
    fixture = output_path(metadata.get("fixture"), "fixture", isolated)
    navigation = output_path(metadata.get("navigation"), "navigation", isolated)
    if isolated and (fixture != str(ROOT / "run-data" / scenario_id / "fixture.json") or
                     navigation != str(ROOT / "run-data" / scenario_id / "navigation-elements.json")):
        raise ValueError("layout export output does not match generator")
    output = ROOT / "run-data/scenarios" / scenario_id
    return {"scenario_id": scenario_id, "scenario": str(scenario_path),
            "mapping": str(mapping_path), "park": park,
            "fixture": fixture, "navigation": navigation,
            "generator": command, "layout": str(layout) if layout else None,
            "native_map": str(output / "map" / f"{scenario_id}.scm"),
            "spawn_journal": str(output / "spawn-queue.json"),
            "server_data": str(output / "server"), "client_data": str(output / "client")}


def ensure_park(plan: dict, force: bool = False) -> None:
    park, fixture, navigation = (Path(plan[key]) for key in ("park", "fixture", "navigation"))
    inputs = [ROOT / path for path in GENERATOR_INPUTS if (ROOT / path).exists()]
    if plan.get("layout"):
        inputs.append(Path(plan["layout"]))
    if force or any(not path.is_file() for path in (park, fixture, navigation)) or any(
            source.stat().st_mtime > min(path.stat().st_mtime for path in (park, fixture, navigation)) for source in inputs):
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
