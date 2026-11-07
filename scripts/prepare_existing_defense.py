#!/usr/bin/env python3
"""Prepare the default StarCraft gameplay layer for an OpenRCT2 map."""
import hashlib
import json
import shutil
from contextlib import nullcontext
from pathlib import Path

from scenario_package import ROOT, SUPPORTED_PARK_FORMATS, inspect_existing_park


def prepare(source: str, workspace: Path | None = None, timing=None) -> dict:
    directory = workspace.resolve() if workspace is not None else None
    if directory is not None and not directory.is_relative_to((ROOT / "run-data").resolve()):
        raise ValueError("session workspace must be inside run-data")
    with timing.stage("source_validation") if timing else nullcontext():
        original = Path(source).expanduser().resolve(strict=True)
        if original.suffix.lower() not in SUPPORTED_PARK_FORMATS or not original.is_file():
            raise ValueError("source must be a supported OpenRCT2 scenario or save")
    identity = hashlib.sha256(str(original).encode()).hexdigest()[:16]
    scenario_id = f"park-defense-{identity}"
    directory = directory or ROOT / "run-data" / scenario_id
    with timing.stage("source_staging") if timing else nullcontext():
        source_copy = directory / "source" / original.name
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        if not source_copy.is_file() or source_copy.stat().st_size != original.stat().st_size or source_copy.stat().st_mtime_ns != original.stat().st_mtime_ns:
            shutil.copy2(original, source_copy)
    with timing.stage("source_inspection") if timing else nullcontext():
        inspected = inspect_existing_park(source_copy)
        width, height = inspected
        if width > 256 or height > 256:
            raise ValueError(f"existing park exceeds 256x256 native map: {width}x{height}")
        validated_source_sha256 = hashlib.sha256(source_copy.read_bytes()).hexdigest()
        layout = getattr(inspected, "economy_layout", None) or {
            "policy_version": 1, "state": "blocked", "reason": "economy_geometry_unavailable",
            "starting_entities": [], "defense_sites": []}
        if layout.get("policy_version") != 1 or layout.get("state") not in ("ready", "blocked"):
            raise ValueError("invalid generated economy layout")
        ready = layout["state"] == "ready"
        entities = layout.get("starting_entities", []) if ready else []
        bases = [entity for entity in entities if entity.get("type") == "terran_command_center"]
        if ready and len(bases) != 1:
            raise ValueError("generated economy layout missing Command Center")
    scenario = {
        "version": 2, "scenario_id": scenario_id, "mode": "park_defense",
        "display_name": f"StarCraft Defense: {original.stem}"[:128],
        "park_file": str((directory / "save" / f"{scenario_id}{original.suffix.lower()}").relative_to(ROOT)),
        "park_size": [width, height], "starting_units": {"marines": [], "zerglings": []},
        "economy": {"version": 1, "mode": "finite", "layout_policy": "generated",
                    "layout_state": layout["state"], "policy_version": layout["policy_version"],
                    "layout_seed": validated_source_sha256[:16],
                    "blocked_reason": layout.get("reason", "") if not ready else "",
                    "initial_balances": {"minerals": 50 if ready else 0, "gas": 0},
                    "starting_entities": entities},
        "initial_structures": ([{"id": bases[0]["id"], "type": "terran_command_center",
                                 "faction": "terran", "tile": bases[0]["tile"]}] if ready else []),
        "objectives": [],
        "initial_ai": {"strategy": "park_defense", "delay_frames": 0},
        "spawn_zones": {},
        "park_defense": {"initial_delay_frames": 7200, "interval_frames": 2880,
                         "manual_cooldown_frames": 360,
                         "spawn_policy": "automatic_perimeter", "spawn_zones": [],
                         "wave_tiers": [
                             {"from_wave": 1, "groups": [{"unit_type": "zerg_zergling", "count": 8}]},
                             {"from_wave": 3, "groups": [{"unit_type": "zerg_zergling", "count": 7},
                                                         {"unit_type": "zerg_hydralisk", "count": 2}]},
                             {"from_wave": 6, "groups": [{"unit_type": "zerg_zergling", "count": 7},
                                                         {"unit_type": "zerg_hydralisk", "count": 2},
                                                         {"unit_type": "zerg_ultralisk", "count": 1}]}]},
        "waves": [], "victory": {}, "defeat": {}
    }
    scenario_path = directory / "scenario.json"
    mapping_path = directory / "mapping.json"
    metadata_path = directory / "package.json"
    with timing.stage("package_staging") if timing else nullcontext():
        scenario_path.write_text(json.dumps(scenario, indent=2) + "\n")
        mapping_path.write_text('{"rules": []}\n')
        metadata_path.write_text(json.dumps({"generator": "existing-park",
                                             "source": str(source_copy.relative_to(ROOT)),
                                             "economy_layout": {"policy_version": layout["policy_version"],
                                                 "state": layout["state"], "seed": validated_source_sha256[:16],
                                                 "defense_sites": layout.get("defense_sites", []),
                                                 "candidates_checked": layout.get("candidates_checked", 0),
                                                 "route_checks": layout.get("route_checks", 0)}}, indent=2) + "\n")
    output = (ROOT / "run-data/scenarios" / scenario_id) if workspace is None else directory
    return {"scenario_id": scenario_id, "scenario": str(scenario_path),
            "mapping": str(mapping_path),
            "park": str(directory / "save" / f"{scenario_id}{original.suffix.lower()}"),
            "fixture": None, "navigation": None, "generator": None, "layout": None,
            "source": str(source_copy), "validated_source_sha256": validated_source_sha256,
            "native_map": str(output / "map" / f"{scenario_id}.scm"),
            "spawn_journal": str(output / "spawn-queue.json"),
            "server_data": str(output / "server"), "client_data": str(output / "client")}
